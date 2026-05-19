"""Unified logger for Peach 1UP backend."""

from __future__ import annotations

import logging
import os
import sys

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


_dev_handler: logging.Handler | None = None


def _is_dev() -> bool:
    return os.environ.get("PEACH_ENV", "production") == "development"


def _get_dev_handler() -> logging.Handler:
    global _dev_handler
    if _dev_handler is None:
        _dev_handler = _make_dev_handler()
    return _dev_handler


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.propagate = False
    if _is_dev():
        logger.setLevel(logging.DEBUG)
        logger.addHandler(_get_dev_handler())
    else:
        logger.addHandler(logging.NullHandler())
        logger.setLevel(logging.CRITICAL)
    return logger


def configure_uvicorn_logging() -> None:
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvi = logging.getLogger(name)
        uvi.handlers.clear()
        uvi.propagate = False
        if _is_dev():
            uvi.setLevel(logging.DEBUG)
            uvi.addHandler(_get_dev_handler())
        else:
            uvi.addHandler(logging.NullHandler())
            uvi.setLevel(logging.CRITICAL)
