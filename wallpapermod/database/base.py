from sqlalchemy.ext.declarative import as_declarative

from .db import DB


@as_declarative(bind=DB)
class Base:
    pass
