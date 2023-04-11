import logging, sys

from .const import *
from .database import *


if __name__ == "__main__":
    from wallpapermod import App

    logging.basicConfig(format="%(asctime)s - %(levelname)-8s - %(message)s", level=logging.INFO)
    log = logging.getLogger()

    app = App(log)

    DB.configure(DB_NAME)
    log.info(f"Dropping and recreating database {DB_NAME!r}")
    drop_all()
    create_all()

    _, *args = list(sys.argv)

    if len(args):
        app.run_single(args[0])
        exit()

    app.run(limit=1000)
