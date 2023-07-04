import enum, typing as t

from sqlalchemy import Enum as SAEnum
import sqlalchemy.types as types

from wallpapermod.const import *


class Rezzes(types.TypeDecorator):
    impl = types.String

    cache_ok = True

    def process_bind_param(self, value: list[Resolution], dialect):
        rezzes = list[str]()
        for x, y, *_ in value:
            rezzes.append(f"{x}x{y}")

        return ",".join(rezzes)

    def process_result_value(self, value: str, dialect):
        rezzes = list[Resolution]()
        if not value:
            return rezzes

        for res_str in str(value).split(","):
            x, y, *_ = res_str.split("x")
            rezzes.append((int(x), int(y)))
        return rezzes


def ValueEnum(enum_: t.Type[enum.Enum]):
    return SAEnum(enum_, values_callable=lambda x: [e.value for e in x])
