"""Logging configuration."""

import logging


def configure_logging(level: int = logging.INFO) -> None:
    """Set up console logging and quiet the chatty libraries."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    for noisy in ("httpx", "httpcore", "openai", "chromadb", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
