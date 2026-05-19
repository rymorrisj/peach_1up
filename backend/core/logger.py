"""Unified logger for Peach 1UP backend."""

from __future__ import annotations

import logging
import os
import sys

_IS_DEV = os.environ.get("PEACH_ENV", "production") == "development"

_ANSI: dict[int, str] = {
    logging.DEBUG:    "\033[2;37m",
    logging.INFO:     "\033[32m",
    logging.WARNING:  "\033[33m",
    logging.ERROR:    "\033[31m",
    logging.CRITICAL: "\033[1;31m",
}
_RESET = "\033[0m"


class _ColourFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        colour = _ANSI.get(record.levelno, "")
        return f"{colour}{line}{_RESET}" if colour else line


def _make_dev_handler() -> logging.Handler:
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        _ColourFormatter(
            fmt="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    return handler


_dev_handler: logging.Handler | None = _make_dev_handler() if _IS_DEV else None


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.propagate = False
    if _IS_DEV:
        assert _dev_handler is not None
        logger.setLevel(logging.DEBUG)
        logger.addHandler(_dev_handler)
    else:
        logger.addHandler(logging.NullHandler())
        logger.setLevel(logging.CRITICAL)
    return logger


def configure_uvicorn_logging() -> None:
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvi = logging.getLogger(name)
        uvi.handlers.clear()
        uvi.propagate = False
        if _IS_DEV:
            assert _dev_handler is not None
            uvi.setLevel(logging.DEBUG)
            uvi.addHandler(_dev_handler)
        else:
            uvi.addHandler(logging.NullHandler())
            uvi.setLevel(logging.CRITICAL)
