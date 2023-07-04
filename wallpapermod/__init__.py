import base64, datetime, logging, pathlib, sys, threading, typing as t

import praw
import bs4
from PIL import Image as PImage, UnidentifiedImageError
import requests

from .config import Config
from .const import *
from .database import *
from .exceptions import *
from .external_links.imgur import Imgur
from .external_links.flickr import Flickr
from .logging_ import PrefixAdapter
from .responses import Responder
from .util import count


__version__ = "0.1.0"


_MAX_RESULT_LENGTH = max(len(x.value) for x in PostResult.__members__.values())


class App:
    def __init__(self, config: Config, log: logging.Logger = None):
        self.config = config
        self.log = log or logging.getLogger("app")
        self.session = requests.Session()
        author = base64.b64decode(b"ZG9vbWJveTEwMDA=").decode("utf-8")
        user_agent = f"script:{APP_NAME}:v{__version__} (Python {sys.version}) (by /u/{author})"
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
        self.moderators = set(x.name for x in self.subreddit.moderator())
        self.responder = Responder(self.config.subreddit)
        self.log.info(f"Reddit initialized read-only={self.reddit.read_only}")
        self.rezzes = self.get_rezzes()
        self._colorama_initted = False
        self._colorama_init_lock = threading.RLock()

    def colored(self, color: str, msg: t.Any) -> str:
        msg = str(msg)
        if not self.config.color:
            return msg

        try:
            import colorama
        except ImportError:
            return msg

        with self._colorama_init_lock:
            if not self._colorama_initted:
                colorama.init()
                self._colorama_initted = True
            return getattr(colorama.Fore, color.upper(), "") + msg + colorama.Style.RESET_ALL

    def get_rezzes(self) -> list[Resolution]:
        """
        Read the HTML of <https://www.reddit.com/r/wallpaper/wiki/resolutions>
        and return a list of supported resolutions
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
        self.init_db()

        if self.config.posts:
            self._run_specific(*self.config.posts)
            return

        self._run_loop()
        return

    def init_db(self):
        DB.configure(self.config.database)
        db_filepath = pathlib.Path(self.config.database)
        if not db_filepath.parent.exists():
            db_filepath.parent.mkdir(parents=True, exist_ok=True)
        if self.config.drop:
            self.log.info(f"Dropping and recreating database {self.config.database!r}")
            drop_all()
            create_all()

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
        """
        Standard output:
        ```
        YYYY-mm-dd HH:MM:SS,SSS - INFO    - [√] VALID               - https://www.reddit.com/r/wallpaper/comments/1a2b3c4d/title_here_1920x1080/
        ```
        Verbose output:
        ```
        YYYY-mm-dd HH:MM:SS,SSS - INFO    - 1a2b3c4d - Title: 'Title here [1920x1080]'
        YYYY-mm-dd HH:MM:SS,SSS - INFO    - 1a2b3c4d - Submitted: YYYY-mm-dd HH:MM:SS
        YYYY-mm-dd HH:MM:SS,SSS - INFO    - 1a2b3c4d - Domain: i.redd.it
        YYYY-mm-dd HH:MM:SS,SSS - INFO    - 1a2b3c4d - Resolution (title): 1920x1080
        YYYY-mm-dd HH:MM:SS,SSS - INFO    - 1a2b3c4d - Image submission
        YYYY-mm-dd HH:MM:SS,SSS - INFO    - 1a2b3c4d - └─ Resolution (JPEG image): 1920x1080
        YYYY-mm-dd HH:MM:SS,SSS - INFO    - 1a2b3c4d - [√] VALID
        ```
        """
        log = PrefixAdapter(self.log, f"{post.id:<7} -")

        submission = Submission.from_post(post, self.rezzes)
        dt_submitted = submission.dateSubmitted.astimezone().replace(tzinfo=None)
        permalink = post._reddit.config.reddit_url + post.permalink
        if self.config.verbose > 0:
            log.info(f"Title: {submission.title!r}")
            log.info(f"Submitted: {dt_submitted:%Y-%m-%d %H:%M:%S}")
            log.info(f"Domain: {submission.domain}")

        existing_submission = (
            DB.query(Submission).filter(Submission.postID == submission.postID).first()
        )
        if existing_submission:
            dt_processed = existing_submission.dateProcessed.astimezone().replace(tzinfo=None)
            if self.config.verbose > 0:
                log.info(
                    self.colored("blue", f"[\u2192] SKIPPED")
                    + f" - Already processed on {dt_processed:%Y-%m-%d %H:%M:%S}"
                )
            else:
                log.info(
                    self.colored("blue", f"[\u2192] {'SKIPPED':<{_MAX_RESULT_LENGTH}}")
                    + f" - {permalink}"
                )
            return

        if submission.author in self.moderators:
            submission.type = PostType.UNKNOWN
            submission.result = PostResult.MODPOST
        else:
            try:
                if not submission.res:
                    raise PostResultError(PostResult.NO_RESOLUTION)
                if not len(submission.good_rezzes):
                    raise PostResultError(PostResult.UNSUPPORTED_RES)

                image_urls, special_type = self.get_image_urls(post, log)

                rezzes_str = ", ".join(f"{x}×{y}" for x, y in submission.res)
                if self.config.verbose > 0:
                    log.info(f"Resolution (title): {rezzes_str}")
                if isinstance(image_urls, str):
                    if self.config.verbose > 0:
                        logmsg = "Image submission"
                        if special_type:
                            logmsg += f" ({special_type})"
                        log.info(logmsg)
                    submission.type = PostType.IMAGE
                    self.check_image(submission, image_urls, None, log)
                else:
                    if self.config.verbose > 0:
                        logmsg = "Gallery submission"
                        if special_type:
                            logmsg += f" ({special_type})"
                        logmsg += f" ({count(image_urls, 'image')})"
                        log.info(logmsg)
                    submission.type = PostType.GALLERY
                    num_images = len(image_urls)
                    for i, image_url in enumerate(image_urls):
                        self.check_image(submission, image_url, (i + 1) / num_images, log)
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

        char, color = (
            {
                PostResult.MODPOST: ("M", "blue"),
                PostResult.VALID: ("\u221A", "green"),  # Square root symbol
                PostResult.LARGER: ("!", "yellow"),
                PostResult.UNSUPPORTED_MEDIA_TYPE: ("?", "white"),
            }
        ).get(submission.result, ("X", "red"))

        self.respond(submission)
        if self.config.verbose > 0:
            log.info(self.colored(color, f"[{char}] {submission.result.value}"))
        else:
            log.info(
                self.colored(color, f"[{char}] {submission.result.value:<{_MAX_RESULT_LENGTH}}")
                + f" - {post._reddit.config.reddit_url}{post.permalink}"
            )

        DB.add(submission)
        DB.commit()

    def respond(self, submission: Submission):
        response_text = self.responder.make_response(submission)
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
        self,
        submission: Submission,
        image_url: str,
        index_pct: t.Union[int, None] = None,
        log: logging.Logger = None,
    ) -> Image:
        if log is None:
            log = self.log

        if index_pct == 1.0 or index_pct is None:
            log_prefix = "└─"
            log_prefix_debug = "   └─"
        else:
            log_prefix = "├─"
            log_prefix_debug = "│  └─"

        image = Image(postID=submission.postID, url=image_url)
        submission.images.append(image)
        image_resp = self.session.get(image_url, stream=True)
        try:
            pimage = PImage.open(image_resp.raw, formats=SUPPORTED_FORMATS)
        except UnidentifiedImageError:
            image.result = ImageResult.UNSUPPORTED_MEDIA_TYPE
            log.warning(f"{log_prefix} Unsupported MimeType {image_resp.headers['Content-Type']!r}")
            return image

        image.x = pimage.width
        image.y = pimage.height
        image.format = pimage.format
        image.result = ImageResult.VALID
        if self.config.verbose > 0:
            log.info(
                f"{log_prefix} Resolution ({pimage.format} image): {pimage.width}×{pimage.height}"
            )

        # Oh no, we're going to have a mismatch of some sort
        if (image.x, image.y) not in submission.good_rezzes:
            # Image needs to be at least as big (in both dimensions) as ONE of the resolutions in the post title
            satisfied = False
            for x, y in submission.good_rezzes:
                if image.x >= x and image.y >= y:
                    log.debug(
                        f"{log_prefix_debug} Image ({image.x}×{image.y}) at least as big as title's ({x}×{y})"
                    )
                    satisfied = True
                else:
                    log.debug(
                        f"{log_prefix_debug} Image ({image.x}×{image.y}) is smaller than title's ({x}×{y})"
                    )
            if satisfied > 0:
                image.result = ImageResult.LARGER
            else:
                image.result = ImageResult.SMALLER
        else:
            log.debug(f"{log_prefix_debug} Image ({image.x}×{image.y}) matches title resolution")

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
