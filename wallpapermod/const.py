import enum, typing as t


Resolution = tuple[int, int]


APP_NAME = "wallpapermod"

DB_NAME = "db.sqlite"

DEFAULT_CONFIG_PATHS = ("config.yml", "config.yaml")


class ImageResult(enum.Enum):
    LARGER = "IMAGE LARGER THAN TITLE"
    SMALLER = "IMAGE SMALLER THAN TITLE"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED MEDIA TYPE"
    VALID = "VALID"


class PostResult(enum.Enum):
    LARGER = ImageResult.LARGER.value
    NO_RESOLUTION = "NO RESOLUTION IN TITLE"
    SMALLER = ImageResult.SMALLER.value
    UNSUPPORTED_MEDIA_TYPE = ImageResult.UNSUPPORTED_MEDIA_TYPE.value
    UNSUPPORTED_RES = "UNSUPPORTED RESOLUTION"
    UNSUPPORTED_TYPE_OR_LINK = "UNSUPPORTED POST TYPE OR LINK"
    VALID = "VALID"


class PostType(enum.Enum):
    GALLERY = "GALLERY"
    IMAGE = "IMAGE"
    UNKNOWN = "UNKNOWN"


class ImageURLCollection(t.NamedTuple):
    urls: t.Union[str, list[str]]
    special_type: str = None


SUPPORTED_FORMATS = [
    "BMP",
    "GIF",
    "JPEG",
    "PNG",
    "WEBP",
]
