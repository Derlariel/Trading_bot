"""Central logging configuration."""
import logging
from logging.handlers import RotatingFileHandler

from config import settings


def get_logger(name: str) -> logging.Logger:
    """Return an idempotently configured application logger."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = RotatingFileHandler(settings.log_path, maxBytes=2_000_000, backupCount=3)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(logging.StreamHandler())
    return logger
