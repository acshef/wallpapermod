import logging


class PrefixAdapter(logging.LoggerAdapter):
    def __init__(self, logger: logging.Logger, prefix: str) -> None:
        super().__init__(logger)
        self.prefix = prefix.strip()

    def process(self, message, kwargs):
        return f"{self.prefix} {message.strip()}", kwargs
