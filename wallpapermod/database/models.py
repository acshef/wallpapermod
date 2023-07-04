import datetime, re

import praw
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    ForeignKey,
    Text,
    text,
)
from sqlalchemy.orm import relationship

from .base import Base
from .customtypes import Rezzes, ValueEnum
from wallpapermod.const import *


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (Index("idx_u_submissions_postID", "postID", unique=True),)

    _res_pattern = re.compile(
        r"""
        (            # Capture group 1: Compulsory capture of the whole thing
            [\[\(\{] # Opening bracket
            \s?      # Optional whitespace char
            ([0-9]+) # Capture group 2: width dimension
            \s?      # Optional whitespace char
            [x*×]    # x-like character
            \s?      # Optional whitespace char
            ([0-9]+) # Capture group 3: height dimension
            \s?      # Optional whitespace char
            [\]\)\}] # Closing bracket
        )
    """,
        re.IGNORECASE | re.VERBOSE,
    )

    id = Column(Integer, primary_key=True)
    postID = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    author = Column(Text, nullable=True)  # Null if author was deleted
    permalink = Column(Text, nullable=False)
    res: list[Resolution] = Column(Rezzes, nullable=False)  # AxB[,CxD]
    dateSubmitted = Column(DateTime, nullable=False)
    dateProcessed = Column(DateTime, nullable=False)
    domain = Column(Text, nullable=False)
    removed = Column(Boolean, nullable=False, server_default=text("0"))
    result = Column(ValueEnum(PostResult), nullable=False)
    response = Column(Text, nullable=True)
    type = Column(ValueEnum(PostType), nullable=False, default=PostType.UNKNOWN)
    title_tokens: list["_TitleToken"]
    good_rezzes: set[Resolution]

    def parse_title(self, known_good_rezzes: t.Iterable[Resolution]):
        """
        Parses the title and populates self.title_tokens and self.res
        """
        rezzes = list[Resolution]()
        good_rezzes = set[Resolution]()
        title_tokens = list["_TitleToken"]()
        match = re.split(self._res_pattern, self.title)

        if len(match) == 1:
            title_tokens.append(_TitleToken(match[0]))
        elif (len(match) - 1) % 4 == 0:
            # There are 1+4n elements in the list, where n is the number of resolutions found.

            # The first element is always plain text (even if it's an empty string)
            plaintext = match.pop(0)
            if plaintext:
                # Only append if it's not the empty string
                title_tokens.append(_TitleToken(plaintext))

            # The 2nd, 6th, 10th, etc. element is always the full resolution string, e.g. "[1920x1080]"
            # The 3rd, 7th, 11th, etc. element is always the width resolution string, e.g. "1920"
            # The 4th, 8th, 12th, etc. element is always the height resolution string, e.g. "1080"
            # The 5th, 9th, 13th, etc. element is always plain text (even if it's an empty string)
            while len(match):
                res_str = match.pop(0)
                w = int(match.pop(0))
                h = int(match.pop(0))
                plaintext = match.pop(0)

                rezzes.append((w, h))

                # Calculate "scale" of resolution. 0 is a bad resolution, 1 is normal, 2 is dual monitor, 3 is triple monitor
                for scale in range(1, 4):
                    if (w // scale, h) in known_good_rezzes:
                        title_tokens.append(_TitleToken(res_str, w, h, scale))
                        good_rezzes.add((w, h))
                        break
                else:
                    title_tokens.append(_TitleToken(res_str, w, h, 0))

                # Only append the plaintext if it's not the empty string
                if plaintext:
                    title_tokens.append(_TitleToken(plaintext))

        self.res = rezzes
        self.title_tokens = title_tokens
        self.good_rezzes = good_rezzes

    def pretty_title(self) -> str:
        return "".join(str(token) for token in self.title_tokens)

    @classmethod
    def title_to_res_pairs(cls, title: str):
        matches = re.findall(cls._res_pattern, title)
        rezzes = list[Resolution]()
        for a, b, *_ in matches:
            rezzes.append((int(a), int(b)))

        return rezzes

    @classmethod
    def from_post(cls, post: praw.reddit.Submission, known_good_rezzes: t.Iterable[Resolution]):
        obj = cls(
            postID=post.id,
            title=post.title.strip(),
            author=post.author.name if post.author is not None else None,
            permalink=post.permalink,
            dateSubmitted=datetime.datetime.fromtimestamp(post.created_utc, datetime.timezone.utc),
            domain=post.domain,
        )
        obj.parse_title(known_good_rezzes)
        return obj

    images: list["Image"] = relationship(
        "Image", back_populates="submission", cascade="all, delete-orphan"
    )


class Image(Base):
    __tablename__ = "images"
    __table_args__ = (Index("idx_u_images_postID_url", "postID", "url", unique=True),)

    id = Column(Integer, primary_key=True)
    postID = Column(Text, ForeignKey("submissions.postID", ondelete="CASCADE"), nullable=False)
    url = Column(Text, nullable=False)
    format = Column(Text, nullable=False, default="")
    x = Column(Integer, nullable=False, default=0)
    y = Column(Integer, nullable=False, default=0)
    result = Column(ValueEnum(ImageResult), nullable=False)

    submission = relationship("Submission", back_populates="images", uselist=False)


class _TitleToken:
    def __init__(
        self,
        value: str,
        width: t.Optional[int] = None,
        height: t.Optional[int] = None,
        scale: t.Optional[int] = None,
    ):
        self.value = str(value)
        self.width = width
        self.height = height
        self.scale = scale

    def __str__(self) -> str:
        try:
            import colorama
        except:
            return self.value

        if self.scale is None:
            return self.value

        if self.scale <= 0:
            return colorama.Fore.RED + self.value + colorama.Style.RESET_ALL
        if self.scale == 1:
            return colorama.Fore.GREEN + self.value + colorama.Style.RESET_ALL
        if self.scale > 1:
            return colorama.Fore.BLUE + self.value + colorama.Style.RESET_ALL

        raise ValueError(f"Unknown scale {self.scale!r}")
