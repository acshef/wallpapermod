import textwrap

from .const import *
from .database import Submission
from .config import _subredditstr


class Responder:
    header = "Hello /u/{author}, thanks for [your submission]({permalink}) on /r/wallpaper."
    footer = "\n\nPlease check out our [https://www.reddit.com/r/wallpaper/wiki/faq](FAQ).\n\n-------------------------------------------------\n\n^^BOOP! ^^BLEEP! ^^I ^^am ^^a ^^bot. ^^Concerns? ^^Message ^^[/r/{subreddit}](/message/compose?to=%2Fr%2F{subreddit}&subject=Problem%20with%20wallpapermod%20bot). ^^^^^^^^^^^^^^^^#!#!REASON={reason}!#!#"

    responses = dict[PostResult, str](
        {
            PostResult.NO_RESOLUTION: (
                """
                **Your submission has been removed** - Titles must contain the proper resolution (formatted like "[XXXXxYYYY]") and a description of the image (e.g. "[1920x1080] Red Rose").

                Images must be one of the accepted resolutions [available on the wiki](/r/wallpaper/wiki/resolutions).
                /r/wallpaper requires an *exact* horizontal desktop resolution - simply having an appropriate aspect ratio (like 16:9 or 16:10) is not good enough!

                For mobile wallpapers, please visit /r/MobileWallpaper, /r/mobilewallpapers, /r/Verticalwallpapers, /r/WallpapersiPhone, or /r/iWallpaper instead.

                Please adjust your submission title and resubmit.
                """
            ),
            PostResult.UNSUPPORTED_RES: (
                """
                **Your submission has been removed** - The resolution of your image(s) doesn't fall under a desktop monitor resolution.

                Images must be one of the accepted resolutions [available on the wiki](/r/wallpaper/wiki/resolutions).
                /r/wallpaper requires an *exact* horizontal desktop resolution - simply having an appropriate aspect ratio (like 16:9 or 16:10) is not good enough!

                For mobile wallpapers, please visit /r/MobileWallpaper, /r/mobilewallpapers, /r/Verticalwallpapers, /r/WallpapersiPhone, or /r/iWallpaper instead.

                If you believe this resolution should be accepted, please [message the mods](/message/compose?to=%2Fr%2Fwallpaper&subject=New%20resolution%20request).
                """
            ),
            # PostResult.UNSUPPORTED_TYPE_OR_LINK,
            PostResult.LARGER: (
                """
                The resolution of your image(s) doesn't match the resolution you put in the title of your post.
                This makes it harder for folks searching for their preferred resolution.
                In the future, please inspect your image so the correct resolution is in your post, or crop/resize your image before posting it.

                Images must be one of the accepted resolutions [available on the wiki](/r/wallpaper/wiki/resolutions).
                /r/wallpaper requires an *exact* horizontal desktop resolution - simply having an appropriate aspect ratio (like 16:9 or 16:10) is not good enough!

                For mobile wallpapers, please visit /r/MobileWallpaper, /r/mobilewallpapers, /r/Verticalwallpapers, /r/WallpapersiPhone, or /r/iWallpaper instead.
                """
            ),
            PostResult.SMALLER: (
                """
                **Your post has been removed** - The resolution of your image(s) doesn't match the resolution you put in the title of your post.
                This makes it harder for folks searching for their preferred resolution.
                In the future, please inspect your image so the correct resolution is in your post, or crop/resize your image before posting it.

                Images must be one of the accepted resolutions [available on the wiki](/r/wallpaper/wiki/resolutions).
                /r/wallpaper requires an *exact* horizontal desktop resolution - simply having an appropriate aspect ratio (like 16:9 or 16:10) is not good enough!

                For mobile wallpapers, please visit /r/MobileWallpaper, /r/mobilewallpapers, /r/Verticalwallpapers, /r/WallpapersiPhone, or /r/iWallpaper instead.
                """
            ),
            # PostResult.UNSUPPORTED_MEDIA_TYPE,
            # PostResult.VALID,
        }
    )

    def __init__(self, subreddit: str):
        self.subreddit = _subredditstr(subreddit)

    def make_response(self, submission: Submission) -> t.Optional[str]:
        assert isinstance(submission.result, PostResult)
        if submission.result not in self.responses:
            return None

        if (
            submission.result is PostResult.SMALLER
            and len(submission.res) == 1
            and len(submission.images) == 1
        ):
            msg = self._make_response_explicit_smaller(submission)
        else:
            msg = self.responses[submission.result]

        msg = self.wrap(msg)

        return msg.format(
            author=submission.author,
            permalink=submission.permalink,
            reason=submission.result.name,
            subreddit=self.subreddit,
        )

    @classmethod
    def wrap(cls, msg: str) -> str:
        msg = textwrap.dedent(msg).strip()
        header = textwrap.dedent(cls.header).strip()
        footer = textwrap.dedent(cls.footer).strip()
        return f"{header}\n\n{msg}\n\n{footer}"

    @staticmethod
    def _make_response_explicit_smaller(submission: Submission) -> str:
        return f"""
            **Your post has been removed** - The resolution of your image ({submission.images[0].x} x {submission.images[0].y}) doesn't match the resolution you put in the title of your post ({submission.res[0][0]} x {submission.res[0][1]}).
            This makes it harder for folks searching for their preferred resolution.
            In the future, please inspect your image so the correct resolution is in your post, or crop/resize your image before posting it.

            Images must be one of the accepted resolutions [available on the wiki](/r/wallpaper/wiki/resolutions).
            /r/wallpaper requires an *exact* horizontal desktop resolution - simply having an appropriate aspect ratio (like 16:9 or 16:10) is not good enough!

            For mobile wallpapers, please visit /r/MobileWallpaper, /r/mobilewallpapers, /r/Verticalwallpapers, /r/WallpapersiPhone, or /r/iWallpaper instead.
        """
