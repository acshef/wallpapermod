import datetime, logging, os.path, sys, typing as t

import praw
import bs4
from PIL import Image as PImage, UnidentifiedImageError
import requests
import yaml

from .config import CONFIG_SCHEMA
from .const import *
from .database import DB, Submission, Image
from .exceptions import PostResultError
from .external_links.imgur import Imgur
from .external_links.flickr import Flickr
from .logging_ import PrefixAdapter
from .responses import RESPONSES
from .util import count


if t.TYPE_CHECKING:
    from _typeshed import FileDescriptorOrPath


__version__ = "0.1.0"


class _BaseApp:
    def __init__(self, log: logging.Logger):
        self.config = self.read_config()
        self.log = log
        self.session = requests.Session()
        user_agent = f"script:{APP_NAME}:v{__version__} (Python {sys.version})"
        self.session.headers.update({"User-Agent": user_agent})
        self.log.info("Initializing connection to reddit")
        self.reddit = self.make_praw(self.config, self.session)
        self.subreddit: praw.reddit.Subreddit = self.reddit.subreddit(self.config["subreddit"])
        self.log.info(f"Reddit initialized read-only={self.reddit.read_only}")

    @staticmethod
    def read_config(file: t.Union["FileDescriptorOrPath", None] = None) -> dict:
        if file is None:
            for path in DEFAULT_CONFIG_PATHS:
                if os.path.isfile(path):
                    file = path
                    break
            else:
                raise ValueError(
                    f"Config path must be provided or default config file must exist, one of {DEFAULT_CONFIG_PATHS!r}"
                )

        with open(file, "rb") as fd:
            obj = yaml.safe_load(fd)
            return CONFIG_SCHEMA(obj)

    @staticmethod
    def make_praw(config: dict, session: requests.Session) -> praw.Reddit:
        praw_config = config["praw"]
        requestor_kwargs = praw_config.setdefault("requestor_kwargs", {})
        requestor_kwargs["session"] = session
        praw_config.setdefault("user_agent", session.headers["User-Agent"])
        return praw.Reddit(**praw_config)


class App(_BaseApp):
    def __init__(self, log: logging.Logger):
        super().__init__(log)
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

    def run(self, *, limit: t.Optional[int] = None):
        self.log.info("Beginning retrieval of posts")
        try:
            for post in self.subreddit.new(limit=limit):
                self.check_submission(post)
        except KeyboardInterrupt:
            print("Aborted!")

    def run_single(self, post_id: str):
        self.log.info(f"Retrieving post {post_id!r}")
        post = self.reddit.submission(id=post_id)
        self.check_submission(post)

    def check_submission(self, post: praw.reddit.Submission):
        log = PrefixAdapter(self.log, f"{post.id} -")

        self.log.info("")
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

            image_urls, special_type = self.get_image_urls(post)

            rezzes_str = ", ".join(f"{x}×{y}" for x, y in submission.res)
            log.info(f"Resolution (title): {rezzes_str}")
            if isinstance(image_urls, str):
                logmsg = "Image submission"
                if special_type:
                    logmsg += f" ({special_type})"
                log.info(logmsg)
                submission.type = PostType.IMAGE
                self.check_image(submission, image_urls)
            else:
                logmsg = "Gallery submission"
                if special_type:
                    logmsg += f" ({special_type})"
                logmsg += f" ({count(image_urls, 'image')})"
                log.info(logmsg)
                submission.type = PostType.GALLERY
                for image_url in image_urls:
                    self.check_image(submission, image_url)
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

        log.info(f"{color} {submission.result.value}")

        DB.add(submission)
        DB.commit()

    def respond(self, submission: Submission):
        if submission.result in (
            PostResult.NO_RESOLUTION,
            PostResult.UNSUPPORTED_RES,
            PostResult.SMALLER,
        ):
            response_text = RESPONSES[submission.result]
            # Add a comment, distinguish comment, sticky comment, remove the post
            pass
        if submission.result is PostResult.LARGER:
            response_text = RESPONSES[submission.result]
            # Add a comment, distinguish comment, sticky comment
            pass

        # Don't do anything for any other results (i.e. VALID or unsupported things)
        return

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

    def get_image_urls(self, post: praw.reddit.Submission) -> ImageURLCollection:
        if vars(post).get("is_gallery"):
            # This is a gallery post
            gallery_items = [i["media_id"] for i in post.gallery_data["items"]]
            return ImageURLCollection(
                [post.media_metadata[item]["s"]["u"] for item in gallery_items]
            )
        elif vars(post).get("post_hint") == "image":
            # This is a single image
            return ImageURLCollection(post.url)
        elif post.domain in ("imgur.com",):
            imgur = Imgur(self.config, self.session)
            urls = imgur.get_image_urls(post.url.strip())
            return ImageURLCollection(urls, "Imgur")
        elif post.domain in ("flickr.com",):
            flickr = Flickr(self.config, self.session)
            urls = flickr.get_image_urls(post.url.strip())
            return ImageURLCollection(urls, "Flickr")
        else:
            breakpoint()
            raise PostResultError(PostResult.UNSUPPORTED_TYPE_OR_LINK)

    def check_image(self, submission: Submission, image_url: str) -> Image:
        image = Image(postID=submission.postID, url=image_url)
        submission.images.append(image)
        image_resp = self.session.get(image_url, stream=True)
        try:
            pimage = PImage.open(image_resp.raw, formats=SUPPORTED_FORMATS)
        except UnidentifiedImageError:
            image.result = ImageResult.UNSUPPORTED_MEDIA_TYPE
            self.log.warning(f"Unsupported MimeType {image_resp.headers['Content-Type']!r}")
            return image

        image.x = pimage.width
        image.y = pimage.height
        image.format = pimage.format
        image.result = ImageResult.VALID
        self.log.info(f"Resolution ({pimage.format} image): {pimage.width}×{pimage.height}")

        good_rezzes = list(self.good_rezzes(submission))
        # Oh no, we're going to have a mismatch of some sort
        if (image.x, image.y) not in good_rezzes:
            # Image needs to be at least as big (in both dimensions) as ONE of the resolutions in the post title
            for x, y in good_rezzes:
                if image.x < x or image.y < y:
                    self.log.debug(f"Image ({image.x}×{image.y}) is smaller than title's ({x}×{y})")
                    image.result = ImageResult.SMALLER
                    break
                self.log.debug(f"Image ({image.x}×{image.y}) at least as big as title's ({x}×{y})")
            else:
                image.result = ImageResult.LARGER
        else:
            self.log.debug(f"Image ({image.x}×{image.y}) matches title resolution")

        return image
