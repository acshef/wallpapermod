from logging.config import dictConfig

from .config import CLIConfig
from .const import *
from .database import *


if __name__ == "__main__":
    try:
        config = CLIConfig.create()
        if config.print_config:
            config.print()
            exit()

        from wallpapermod import App

        if config.logging_config:
            dictConfig(config.logging_config)

        App(config).run()
    except KeyboardInterrupt:
        print("Aborted!")
