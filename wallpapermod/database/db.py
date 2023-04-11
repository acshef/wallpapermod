import typing as t

from sqlalchemy import event
from sqlalchemy.engine import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from wallpapermod.const import *


class _SessionProxy:
    def __init__(self, filename: t.Optional[str] = None):
        self._session = scoped_session(sessionmaker(autocommit=False, autoflush=False))
        if filename is not None:
            self.configure(filename)

    def configure(self, filename: str):
        self._session.configure(bind=self.create_engine(filename))

    def __getattr__(self, attr):
        return getattr(self._session, attr)

    @classmethod
    def create_engine(cls, filename: str):
        engine = create_engine(f"sqlite:///{filename}")
        event.listen(engine, "connect", lambda cxn, _: cxn.execute("pragma foreign_keys=ON"))
        return engine


DB = _SessionProxy()
