"""Rotating application logs with consistent ISO timestamps."""

import logging
from logging.handlers import RotatingFileHandler

from .infra.settings import SettingsLoader


def configure_logging(debug: bool = False) -> None:
    """Configure rotating action and parser logs once per process."""
    directory = SettingsLoader().get("log_dir")
    directory.mkdir(parents=True, exist_ok=True)
    for name, filename in (
        ("valutatrade.actions", "actions.log"),
        ("valutatrade.parser", "parser.log"),
    ):
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG if debug else logging.INFO)
        if not logger.handlers:
            handler = RotatingFileHandler(
                directory / filename, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
            )
            formatter = logging.Formatter(
                "%(levelname)s %(asctime)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        logger.propagate = False
