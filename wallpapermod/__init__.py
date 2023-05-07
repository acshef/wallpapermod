import datetime, logging, sys, typing as t

import praw
import bs4
from PIL import Image as PImage, UnidentifiedImageError
import requests

from .config import Config
from .const import *
from .database import DB, Submission, Image
from .exceptions import *
from .external_links.imgur import Imgur
from .external_links.flickr import Flickr
from .logging_ import PrefixAdapter
from .responses import make_response
from .util import count


__version__ = "0.1.0"


class App:
    def __init__(self, config: Config, log: logging.Logger):
        self.config = config
        self.log = log
        self.session = requests.Session()
        user_agent = f"script:{APP_NAME}:v{__version__} (Python {sys.version})"
        self.session.headers.update({"User-Agent": user_agent})
        self.log.info("Initializing connection to reddit")
        self.reddit = self.make_praw(
            self.config.reddit_username,
            self.config.reddit_password,
            self.config.reddit_client_id,
            self.config.reddit_client_secret,
            self.session,
            **self.config.praw_config or {},
        )
        self.subreddit: praw.reddit.Subreddit = self.reddit.subreddit(self.config.subreddit)
        self.log.info(f"Reddit initialized read-only={self.reddit.read_only}")
        self.rezzes = self.get_rezzes()

    def get_rezzes(self) -> list[Resolution]:
        """
        Read the HTML of <https://www.reddit.com/r/wallpaper/wiki/resolutions>
        """
        page = self.subreddit.wiki["resolutions"]
        bs = bs4.BeautifulSoup(page.content_html, "html.parser")
        table = None
        for t in bs.find_all("table"):
            try:
                for tr in t.findChild("thead").findChildren("tr"):
                    header_cells = tr.findChildren()
                    if len(header_cells) < 3:
                        continue
                    if (
                        "width" in header_cells[0].string.lower()
                        and "height" in header_cells[1].string.lower()
                        and "description" in header_cells[2].string.lower()
                    ):
                        table = t
                        break
            except Exception:
                continue
        if table is None:
            raise ValueError(
                f"Unable to find a table with the appropriate (Width,Height,Description) headers on Wiki page {page!s}"
            )

        rezzes = list[Resolution]()
        for tr in table.findChild("tbody").findChildren("tr"):
            row_cells = tr.findChildren()
            width = int(row_cells[0].string)
            height = int(row_cells[1].string)
            rezzes.append((width, height))

        return rezzes

    def run(self):
        if self.config.posts:
            self._run_specific(*self.config.posts)
            return

        self._run_loop()
        return

    def _run_loop(self):
        msg: str
        if self.config.count:
            msg = f"Beginning retrieval of {count(self.config.count, 'post')}"
        else:
            msg = "Beginning maximum retrieval of posts"

        if self.config.stop_after:
            if isinstance(self.config.stop_after, str):
                msg += f", stopping after post {self.config.stop_after!r}"
            elif isinstance(self.config.stop_after, datetime.datetime):
                msg += f", stopping after {self.config.stop_after}"
            else:
                raise ValueError(f"Unknown stop-after value {self.config.stop_after!r}")

        self.log.info(msg)

        for i, post in enumerate(self.subreddit.new(limit=None)):
            if self.config.count and i >= self.config.count:
                break
            if isinstance(self.config.stop_after, datetime.datetime):
                # Break if the post submission time is less than the config
                if post.created <= self.config.stop_after.timestamp():
                    break
            self.check_submission(post)
            if isinstance(self.config.stop_after, str):
                # Break if the post ID matches config
                if post.id == self.config.stop_after:
                    break

        if self.config.count:
            self.log.info(f"Finished retrieving {count(self.config.count, 'post')}")

        return

    def _run_specific(self, *post_ids: list[str]):
        if not post_ids:
            self.log.warning("No post IDs to check")
            return
        if len(post_ids) == 1:
            self.log.info("Will only check post with this ID: " + post_ids[0])
        else:
            self.log.info("Will only check posts with these IDs: " + ", ".join(post_ids))
        for post_id in post_ids:
            log = PrefixAdapter(self.log, f"{post_id:<7} -")
            log.info("Retrieving post")
            try:
                post = self.reddit.submission(id=post_id)
                if post.subreddit.display_name != self.config.subreddit:
                    raise WrongSubredditError(
                        f"Post {post_id} is from /r/{post.subreddit.display_name}, expected /r/{self.config.subreddit}"
                    )
            except Exception as exc:
                log.error(str(exc))
            else:
                self.check_submission(post)

    def check_submission(self, post: praw.reddit.Submission):
        log = PrefixAdapter(self.log, f"{post.id:<7} -")

        submission = Submission.from_post(post)
        dt_submitted = submission.dateSubmitted.astimezone().replace(tzinfo=None)
        log.info(f"Title: {submission.title!r}")
        log.info(f"Submitted: {dt_submitted}")
        log.info(f"Domain: {submission.domain}")

        existing_submission = (
            DB.query(Submission).filter(Submission.postID == submission.postID).first()
        )
        if existing_submission:
            dt_processed = existing_submission.dateProcessed.astimezone().replace(tzinfo=None)
            log.info(f"⏭  SKIPPED - Already processed on {dt_processed}")
            return

        try:
            if not submission.res:
                raise PostResultError(PostResult.NO_RESOLUTION)
            good_submission_rezzes = list(self.good_rezzes(submission))
            if not len(good_submission_rezzes):
                raise PostResultError(PostResult.UNSUPPORTED_RES)

            image_urls, special_type = self.get_image_urls(post, log)

            rezzes_str = ", ".join(f"{x}×{y}" for x, y in submission.res)
            log.info(f"Resolution (title): {rezzes_str}")
            if isinstance(image_urls, str):
                logmsg = "Image submission"
                if special_type:
                    logmsg += f" ({special_type})"
                log.info(logmsg)
                submission.type = PostType.IMAGE
                self.check_image(submission, image_urls, log)
            else:
                logmsg = "Gallery submission"
                if special_type:
                    logmsg += f" ({special_type})"
                logmsg += f" ({count(image_urls, 'image')})"
                log.info(logmsg)
                submission.type = PostType.GALLERY
                for image_url in image_urls:
                    self.check_image(submission, image_url, log)
        except PostResultError as exc:
            submission.result = exc.postresult
            submission.type = PostType.UNKNOWN
        else:
            # Each successive element has higher priority than the last, i.e. ImageResult.SMALLER trumps all.
            hierarchy = {
                ImageResult.VALID: 0,
                ImageResult.LARGER: 1,
                ImageResult.UNSUPPORTED_MEDIA_TYPE: 2,
                ImageResult.SMALLER: 3,
            }
            submission.result = PostResult.VALID
            for i in submission.images:
                # Convert PostResult to ImageResult
                current_score = hierarchy[ImageResult(submission.result.value)]
                new_score = hierarchy[i.result]
                if new_score > current_score:
                    # Convert ImageResult to PostResult
                    submission.result = PostResult(i.result.value)

        submission.dateProcessed = datetime.datetime.now(tz=datetime.timezone.utc)

        color = ""
        if submission.result is PostResult.VALID:
            color = "✅"
        elif submission.result is PostResult.LARGER:
            color = "🟨"
        elif submission.result is PostResult.UNSUPPORTED_MEDIA_TYPE:
            color = "⏭"
        else:
            color = "🟥"

        self.respond(submission)
        log.info(f"{color} {submission.result.value}")

        DB.add(submission)
        DB.commit()

    def respond(self, submission: Submission):
        response_text = make_response(submission)
        if response_text is None:
            # Don't do anything for any other results (i.e. VALID or unsupported things)
            return

        if submission.result in (
            PostResult.NO_RESOLUTION,
            PostResult.UNSUPPORTED_RES,
            PostResult.SMALLER,
        ):
            # Add a comment, distinguish comment, sticky comment, remove the post
            # submission.removed = True
            pass
        if submission.result is PostResult.LARGER:
            # Add a comment, distinguish comment, sticky comment
            pass

        # TODO: Swap this out for a permalink of the stickied comment
        # once commenting has been implemented
        submission.response = response_text

    def good_rezzes(self, submission: Submission) -> t.Iterator[Resolution]:
        """
        Yield all the KNOWN GOOD resolutions from the resolutions in the title
        """

        for w, h in submission.res:
            # If user is submitting a dual monitor wallpaper, they might put "[3840 x 1080]" in the
            # title, which isn't an accepted resolution. Half-width, e.g. 1920x1080, is. So check
            # for half and third widths.
            res_variants = [
                (w, h),
                (w // 2, h),
                (w // 3, h),
            ]
            if any(r in self.rezzes for r in res_variants):
                yield (w, h)

    def get_image_urls(
        self, post: praw.reddit.Submission, log: logging.Logger = None
    ) -> ImageURLCollection:
        if log is None:
            log = self.log

        if hasattr(post, "crosspost_parent"):
            _parent_kind, parent_id = post.crosspost_parent.split("_")
            parent = self.reddit.submission(parent_id)
            parent._fetch()
            return self.get_image_urls(parent, log)

        if vars(post).get("is_gallery"):
            # This is a gallery post
            gallery_items = [i["media_id"] for i in post.gallery_data["items"]]
            gallery_urls = list[str]()
            for item in gallery_items:
                media_item = post.media_metadata[item]
                media_item_status = media_item.get("status")
                if media_item_status != "valid":
                    log.warn(f"Media item {item!r} has status {media_item_status!r}")
                    continue
                gallery_urls.append(media_item["s"]["u"])
            return ImageURLCollection(gallery_urls)
        elif vars(post).get("post_hint") == "image" or vars(post).get("domain") == "i.redd.it":
            # This is a single image
            return ImageURLCollection(post.url)
        elif post.domain in ("imgur.com",):
            imgur = Imgur(self.config.imgur_client_id, self.session)
            urls = imgur.get_image_urls(post.url.strip())
            return ImageURLCollection(urls, "Imgur")
        elif post.domain in ("flickr.com",):
            flickr = Flickr(self.config.flickr_key, self.session)
            urls = flickr.get_image_urls(post.url.strip())
            return ImageURLCollection(urls, "Flickr")
        else:
            breakpoint()
            raise PostResultError(PostResult.UNSUPPORTED_TYPE_OR_LINK)

    def check_image(
        self, submission: Submission, image_url: str, log: logging.Logger = None
    ) -> Image:
        if log is None:
            log = self.log

        image = Image(postID=submission.postID, url=image_url)
        submission.images.append(image)
        image_resp = self.session.get(image_url, stream=True)
        try:
            pimage = PImage.open(image_resp.raw, formats=SUPPORTED_FORMATS)
        except UnidentifiedImageError:
            image.result = ImageResult.UNSUPPORTED_MEDIA_TYPE
            log.warning(f"Unsupported MimeType {image_resp.headers['Content-Type']!r}")
            return image

        image.x = pimage.width
        image.y = pimage.height
        image.format = pimage.format
        image.result = ImageResult.VALID
        log.info(f"Resolution ({pimage.format} image): {pimage.width}×{pimage.height}")

        good_rezzes = set(self.good_rezzes(submission))
        # Oh no, we're going to have a mismatch of some sort
        if (image.x, image.y) not in good_rezzes:
            # Image needs to be at least as big (in both dimensions) as ONE of the resolutions in the post title
            satisfied = False
            for x, y in good_rezzes:
                if image.x >= x and image.y >= y:
                    log.debug(f"Image ({image.x}×{image.y}) at least as big as title's ({x}×{y})")
                    satisfied = True
                else:
                    log.debug(f"Image ({image.x}×{image.y}) is smaller than title's ({x}×{y})")
            if satisfied > 0:
                image.result = ImageResult.LARGER
            else:
                image.result = ImageResult.SMALLER
        else:
            log.debug(f"Image ({image.x}×{image.y}) matches title resolution")

        return image

    @staticmethod
    def make_praw(
        username: str,
        password: str,
        client_id: str,
        client_secret: str,
        session: requests.Session,
        **kwargs,
    ) -> praw.Reddit:
        config = dict(kwargs)
        config.update(
            username=username,
            password=password,
            client_id=client_id,
            client_secret=client_secret,
        )
        requestor_kwargs = config.setdefault("requestor_kwargs", {})
        requestor_kwargs["session"] = session
        config.setdefault("user_agent", session.headers["User-Agent"])
        return praw.Reddit(**config)
