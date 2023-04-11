from sqlalchemy.schema import DropTable

from .models import (
    Submission,
    Image,
)
from .db import DB

__all__ = [
    "DB",
    "Submission",
    "Image",
    "drop_all",
    "create_all",
]


def drop_all():
    DB.execute(DropTable(Submission.__table__, if_exists=True))
    DB.execute(DropTable(Image.__table__, if_exists=True))
    DB.commit()


def create_all():
    engine = DB.get_bind()

    Submission.__table__.create(engine)
    Image.__table__.create(engine)
    DB.commit()
