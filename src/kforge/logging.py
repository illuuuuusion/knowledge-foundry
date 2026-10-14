"""Application logging; source contents and credentials are never logged here."""

import logging


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
