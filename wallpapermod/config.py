import voluptuous as v


# https://praw.readthedocs.io/en/stable/getting_started/configuration/options.html
_praw_schema = v.Schema(
    {
        # Basic configuration options
        v.Optional("check_for_updates"): bool,
        v.Optional("user_agent"): str,
        # OAuth configuration options
        "client_id": str,
        "client_secret": str,
        "password": str,
        "username": str,
        # Reddit site configuration options
        v.Optional("comment_kind"): str,
        v.Optional("message_kind"): str,
        v.Optional("oauth_url"): v.Url(),
        v.Optional("reddit_url"): v.Url(),
        v.Optional("redditor_kind"): str,
        v.Optional("short_url"): v.Url(),
        v.Optional("submission_kind"): str,
        v.Optional("subreddit_kind"): str,
        # Miscellaneous configuration options
        v.Optional("check_for_async"): bool,
        v.Optional("ratelimit_seconds"): int,
        v.Optional("timeout"): int,
        v.Optional("warn_comment_sort"): bool,
    },
    required=True,
    extra=v.ALLOW_EXTRA,
)

_imgur_schema = v.Schema(
    {
        "client_id": str,
        "client_secret": str,
    },
    required=True,
)

_flickr_schema = v.Schema(
    {
        "key": str,
        "secret": str,
    },
    required=True,
)

CONFIG_SCHEMA = v.Schema(
    {
        "flickr": _flickr_schema,
        "imgur": _imgur_schema,
        "praw": _praw_schema,
        "subreddit": str,
    }
)
