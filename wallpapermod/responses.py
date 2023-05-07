import textwrap

from .const import *
from .database import Submission

_HEADER = "Hello /u/{author}, thanks for [your submission]({permalink}) on /r/wallpaper."


_FOOTER = """

Please check out our [https://www.reddit.com/r/wallpaper/wiki/faq](FAQ).

-------------------------------------------------

^^BOOP! ^^BLEEP! ^^I ^^am ^^a ^^bot. ^^Concerns? ^^Message ^^[/r/wallpaper](/message/compose?to=%2Fr%2Fwallpaper&subject=Problem%20with%20wallpapermod%20bot).
"""


def wrap(msg: str):
    msg = textwrap.dedent(msg).strip()
    header = textwrap.dedent(_HEADER).strip()
    footer = textwrap.dedent(_FOOTER).strip()
    return f"{header}\n\n{msg}\n\n{footer}"


def make_response(submission: Submission) -> t.Optional[str]:
    assert isinstance(submission.result, PostResult)
    if submission.result not in _RESPONSES:
        return None

    if (
        submission.result is PostResult.SMALLER
        and len(submission.res) == 1
        and len(submission.images) == 1
    ):
        msg = _make_response_explicit_smaller(submission)
    else:
        msg = _RESPONSES[submission.result]

    return msg.format(author=submission.author, permalink=submission.permalink)


_RESPONSES = dict[PostResult, str](
    {
        PostResult.NO_RESOLUTION: wrap(
            """
            **Your submission has been removed** - Posts titles must contain the proper resolution (formatted like "[XXXXxYYYY]") and a description of the image (e.g. "[1920×1080] Red Rose").

            Reminder: your image(s) must be one of the accepted resolutions [available on the wiki](/r/wallpaper/wiki/resolutions).
            For mobile wallpapers, please visit /r/MobileWallpaper, /r/mobilewallpapers, /r/Verticalwallpapers, /r/WallpapersiPhone, or /r/iWallpaper instead.

            Please adjust your submission title and resubmit.
            """
        ),
        PostResult.UNSUPPORTED_RES: wrap(
            """
            **Your submission has been removed** - The resolution of your image(s) doesn't fall under a desktop monitor resolution.
            A list of these is [available on the wiki](/r/wallpaper/wiki/resolutions).
            /r/wallpaper requires an *exact* horizontal desktop resolution - simply having an appropriate aspect ratio (like 16:9 or 16:10) is not good enough!

            For mobile wallpapers, please visit /r/MobileWallpaper, /r/mobilewallpapers, /r/Verticalwallpapers, /r/WallpapersiPhone, or /r/iWallpaper instead.

            If you believe this resolution should be accepted, please [message the mods](/message/compose?to=%2Fr%2Fwallpaper&subject=New%20resolution%20request).
            """
        ),
        # PostResult.UNSUPPORTED_TYPE_OR_LINK,
        PostResult.LARGER: wrap(
            """
            The resolution of your image(s) doesn't match the resolution you put in the title of your post.
            This makes it harder for folks searching for their preferred resolution.
            In the future, please inspect your image so the correct resolution is in your post, or crop/resize your image before posting it.

            A list of acceptable resolutions is [available on the wiki](/r/wallpaper/wiki/resolutions).
            """
        ),
        PostResult.SMALLER: wrap(
            """
            **Your post has been removed** - The resolution of your image(s) doesn't match the resolution you put in the title of your post.
            This makes it harder for folks searching for their preferred resolution.
            In the future, please inspect your image so the correct resolution is in your post, or crop/resize your image before posting it.

            A list of acceptable resolutions is [available on the wiki](/r/wallpaper/wiki/resolutions).
            """
        ),
        # PostResult.UNSUPPORTED_MEDIA_TYPE,
        # PostResult.VALID,
    }
)


def _make_response_explicit_smaller(submission: Submission) -> str:
    return wrap(
        f"""
        **Your post has been removed** - The resolution of your image ({submission.images[0].x} x {submission.images[0].y}) doesn't match the resolution you put in the title of your post ({submission.res[0][0]} x {submission.res[0][1]}).
        This makes it harder for folks searching for their preferred resolution.
        In the future, please inspect your image so the correct resolution is in your post, or crop/resize your image before posting it.

        A list of acceptable resolutions is [available on the wiki](/r/wallpaper/wiki/resolutions).
    """
    )
