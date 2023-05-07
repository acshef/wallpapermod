import logging, pathlib

from .config import Config
from .const import *
from .database import *


if __name__ == "__main__":
    try:
        config = Config.create()
        if config.print_config:
            config.print()
            exit()

        from wallpapermod import App

        logging.basicConfig(
            format="%(asctime)s - %(levelname)-8s - %(message)s", level=logging.INFO
        )
        log = logging.getLogger()

        app = App(config, log)

        DB.configure(config.database)
        db_filepath = pathlib.Path(config.database)
        if not db_filepath.parent.exists():
            db_filepath.parent.mkdir(parents=True, exist_ok=True)
        if config.drop:
            log.info(f"Dropping and recreating database {config.database!r}")
            drop_all()
            create_all()

        app.run()
    except KeyboardInterrupt:
        print("Aborted!")
