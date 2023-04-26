import argparse, json, os, pathlib, re

import configargparse

from .const import *


class ArgumentDefaultsHelpFormatter(argparse.ArgumentDefaultsHelpFormatter):
    def __init__(self, prog, indent_increment=2, max_help_position=80, width=None):
        super().__init__(prog, indent_increment, max_help_position, width)

    def _split_lines(self, text, width):
        lines = text.splitlines()
        # The textwrap module is used only for formatting help.
        # Delay its import for speeding up the common usage of argparse.
        import textwrap

        wrapped_lines = list()
        for line in lines:
            wrapped_lines.extend(textwrap.wrap(line, width))
        return wrapped_lines

    def _get_help_string(self, action):
        help = action.help
        if not (action.default is None and action.required and action.type is None):
            if "%(default)" not in action.help:
                if action.default is not argparse.SUPPRESS:
                    defaulting_nargs = [argparse.OPTIONAL, argparse.ZERO_OR_MORE]
                    if action.option_strings or action.nargs in defaulting_nargs:
                        help += "\n(default: %(default)s)"
        return help


def relative_path(path: t.Union[str, pathlib.Path]) -> str:
    abs_path = pathlib.Path(path).resolve()
    abs_cwd = pathlib.Path(os.getcwd()).resolve()
    return str(pathlib.Path(pathlib.PurePath(abs_path).relative_to(abs_cwd)))


def config_path(path: str) -> pathlib.Path:
    if isinstance(path, _defaultconfigstr):
        for dp_name in DEFAULT_CONFIG_PATHS:
            dp = pathlib.Path(dp_name)
            if dp.exists() and dp.is_file():
                return relative_path(dp)
        raise ValueError(
            f"Config file is required; no default config files exist ({DEFAULT_CONFIG_PATHS})"
        )
    return relative_path(path)


def subreddit(name: str) -> str:
    return re.sub(r"^/?r/", "", name)


class _defaultconfigstr(str):
    def __init__(self, paths: t.Iterable[str]):
        self.__paths = list(paths)

    def __str__(self):
        return " or ".join(self.__paths)


class _maskedstr(str):
    def __repr__(self):
        return "********"


class Config(argparse.Namespace):
    subreddit: str
    posts: list[str]
    count: t.Optional[int] = None

    reddit_username: str
    reddit_password: str
    reddit_client_id: str
    reddit_client_secret: str
    praw_config: dict

    flickr_key: str
    # flickr_secret: str

    imgur_client_id: str
    # imgur_client_secret: str

    database: pathlib.Path
    drop: bool

    print_config: bool

    def print(self):
        configdict = vars(self)
        longestklen = max(len(k) for k in configdict.keys())
        for k, v in configdict.items():
            print(f"{k:<{longestklen}} = {v!r}")

    @classmethod
    def create(cls) -> t.Self:
        parser = cls._create_parser()
        return parser.parse_args(namespace=cls())

    @staticmethod
    def _create_parser() -> configargparse.ArgumentParser:
        from wallpapermod import __version__

        parser = configargparse.ArgumentParser(
            prog=APP_NAME,
            description="A moderator for the subreddit /r/wallpaper <https://www.reddit.com/r/wallpaper> that validates image sizes",
            formatter_class=ArgumentDefaultsHelpFormatter,
            add_help=False,
        )
        parser.add_argument(
            "posts",
            help="If present, one or more specific posts to evaluate instead of the infinite loop",
            metavar="POST_ID",
            nargs="*",
        )
        parser.add_argument(
            "--config",
            "-c",
            is_config_file=True,
            default=_defaultconfigstr(DEFAULT_CONFIG_PATHS),
            help="Config file",
            type=config_path,
            metavar="FILEPATH",
        )

        parser.add_argument(
            "--count", "-n", type=int, required=False, help="Stop after the Nth post", metavar="N"
        )
        parser.add_argument(
            "--subreddit",
            "-r",
            type=subreddit,
            required=True,
            help="Subreddit to operate upon",
        )

        reddit_group = parser.add_argument_group(
            "Reddit",
            "For interfacing with Reddit API <https://www.reddit.com/prefs/apps#developed-apps>",
        )
        reddit_group.add_argument(
            "--username",
            required=True,
            help="Reddit username",
            metavar="NAME",
            dest="reddit_username",
        )
        reddit_group.add_argument(
            "--password",
            required=True,
            help="Reddit password",
            type=_maskedstr,
            metavar="PASSWORD",
            dest="reddit_password",
        )
        reddit_group.add_argument(
            "--client-id",
            required=True,
            help="Reddit API client ID",
            metavar="CLIENT_ID",
            dest="reddit_client_id",
        )
        reddit_group.add_argument(
            "--client-secret",
            required=True,
            help="Reddit API client secret",
            metavar="SECRET",
            type=_maskedstr,
            dest="reddit_client_secret",
        )
        reddit_group.add_argument(
            "--praw",
            help="JSON-formatted extra kwargs for PRAW config <https://praw.readthedocs.io/en/stable/getting_started/configuration.html>",
            metavar="JSON",
            type=json.loads,
            dest="praw_config",
        )

        flickr_grp = parser.add_argument_group(
            "Flickr", "For interfacing with Flickr API <https://www.flickr.com/services/apps>"
        )
        flickr_grp.add_argument(
            "--flickr-key",
            required=True,
            help="Flickr API key",
            metavar="KEY",
        )
        # flickr_grp.add_argument(
        #     "--flickr-secret",
        #     required=True,
        #     help="Flickr API secret",
        #     metavar="SECRET",
        #     type=_maskedstr,
        # )

        imgur_grp = parser.add_argument_group(
            "Imgur", "For interfacing with Imgur API <https://imgur.com/account/settings/apps>"
        )
        imgur_grp.add_argument(
            "--imgur-client-id",
            required=True,
            help="Imgur API client ID",
            metavar="CLIENT_ID",
        )
        # imgur_grp.add_argument(
        #     "--imgur-client-secret",
        #     required=True,
        #     help="Imgur API client secret",
        #     metavar="SECRET",
        #     type=_maskedstr,
        # )

        db_grp = parser.add_argument_group("database")
        db_grp.add_argument(
            "--db",
            default=DB_NAME,
            help="SQLite database file",
            type=relative_path,
            metavar="FILEPATH",
            dest="database",
        )
        db_grp.add_argument(
            "--drop",
            action="store_true",
            help="Drop and recreate the database",
        )

        other_grp = parser.add_argument_group("other options")
        other_grp.add_argument(
            "--print-config", action="store_true", help="Show the config and exit"
        )
        other_grp.add_argument("--help", "-h", "-?", action="help", help="Show help text and exit")
        other_grp.add_argument(
            "--version",
            "-v",
            action="version",
            help="Show program's version number and exit",
            version="v" + __version__,
        )

        return parser
