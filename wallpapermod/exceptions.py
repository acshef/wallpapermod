from .const import PostResult


class WallpapermodError(Exception):
    pass


class PostResultError(WallpapermodError):
    def __init__(self, postresult: PostResult):
        self.postresult = postresult
