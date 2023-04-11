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
from wallpapermod.const import PostType, PostResult, ImageResult


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (Index("idx_u_submissions_postID", "postID", unique=True),)

    id = Column(Integer, primary_key=True)
    postID = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    author = Column(Text, nullable=True)  # Null if author was deleted
    res: list[tuple[int, int]] = Column(Rezzes, nullable=False)  # AxB[,CxD]
    dateSubmitted = Column(DateTime, nullable=False)
    dateProcessed = Column(DateTime, nullable=False)
    domain = Column(Text, nullable=False)
    removed = Column(Boolean, nullable=False, server_default=text("0"))
    result = Column(ValueEnum(PostResult), nullable=False)
    response = Column(Text, nullable=True)
    type = Column(ValueEnum(PostType), nullable=False, default=PostType.UNKNOWN)

    # @property
    # def url(self) -> str:
    #     return f"https://reddit.com/r/wallpaper/{self.postID}"

    @staticmethod
    def title_to_res_pairs(title: str):
        matches = re.findall(
            r"""
                [\[\(\{] # Opening bracket
                \s?      # Optional whitespace char
                ([0-9]+) # Width dimension
                \s?      # Optional whitespace char
                [x*×]    # x-like character
                \s?      # Optional whitespace char
                ([0-9]+) # Height dimension
                \s?      # Optional whitespace char
                [\]\)\}] # Closing bracket
            """,
            title,
            re.IGNORECASE | re.VERBOSE,
        )
        rezzes = list[tuple[int, int]]()
        for a, b, *_ in matches:
            rezzes.append((int(a), int(b)))

        return rezzes

    @classmethod
    def from_post(cls, post: praw.reddit.Submission):
        obj = cls(
            postID=post.id,
            title=post.title.strip(),
            author=post.author.name if post.author is not None else None,
            dateSubmitted=datetime.datetime.fromtimestamp(post.created_utc, datetime.timezone.utc),
            domain=post.domain,
        )
        obj.res = cls.title_to_res_pairs(obj.title)
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
