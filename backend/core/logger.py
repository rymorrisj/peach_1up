"""Unified logger for Peach 1UP backend."""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

_ANSI: dict[int, str] = {
    logging.DEBUG:    "\033[2;37m",
    logging.INFO:     "\033[32m",
    logging.WARNING:  "\033[33m",
    logging.ERROR:    "\033[31m",
    logging.CRITICAL: "\033[1;31m",
}
_RESET = "\033[0m"

_FILE_FMT = logging.Formatter(
    fmt="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

_CONSOLE_FMT = logging.Formatter(
    fmt="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


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


def _make_prod_console_handler() -> logging.Handler:
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.ERROR)
    handler.setFormatter(_CONSOLE_FMT)
    return handler


_dev_handler: logging.Handler | None = None
_prod_console_handler: logging.Handler | None = None

# Populated by setup_logging(); file handlers are attached to all backend loggers.
_file_handlers: list[logging.Handler] = []
_logging_setup_done = False


def _is_dev() -> bool:
    return os.environ.get("PEACH_ENV", "production") == "development"


def _get_dev_handler() -> logging.Handler:
    global _dev_handler
    if _dev_handler is None:
        _dev_handler = _make_dev_handler()
    return _dev_handler


def _get_prod_console_handler() -> logging.Handler:
    global _prod_console_handler
    if _prod_console_handler is None:
        _prod_console_handler = _make_prod_console_handler()
    return _prod_console_handler


def _attach_file_handlers(logger: logging.Logger) -> None:
    """Add any file handlers not yet on logger and lower its level to allow INFO through."""
    for h in _file_handlers:
        if h not in logger.handlers:
            logger.addHandler(h)
    if _file_handlers and logger.level > logging.INFO:
        logger.setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        _attach_file_handlers(logger)
        return logger
    logger.propagate = False
    if _is_dev():
        logger.setLevel(logging.DEBUG)
        logger.addHandler(_get_dev_handler())
    else:
        logger.setLevel(logging.ERROR)
        logger.addHandler(_get_prod_console_handler())
    _attach_file_handlers(logger)
    return logger


def setup_logging() -> None:
    """Create RotatingFileHandlers and attach them to all existing and future backend loggers.

    Safe to call multiple times; only the first call has any effect.
    File handlers write to logs/ under the project root and are independent
    of stdout/stderr — they work correctly even in windowless frozen builds.
    """
    global _logging_setup_done
    if _logging_setup_done:
        return

    from backend.core.settings import get_base_path
    logs_dir = get_base_path() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    app_h = RotatingFileHandler(
        logs_dir / "app.log",
        maxBytes=15 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    app_h.setLevel(logging.INFO)
    app_h.setFormatter(_FILE_FMT)

    err_h = RotatingFileHandler(
        logs_dir / "error.log",
        maxBytes=15 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    err_h.setLevel(logging.ERROR)
    err_h.setFormatter(_FILE_FMT)

    _file_handlers.extend([app_h, err_h])

    for log_name, log_obj in logging.root.manager.loggerDict.items():
        if isinstance(log_obj, logging.Logger) and (
            log_name.startswith("backend") or log_name.startswith("peach")
        ):
            _attach_file_handlers(log_obj)

    _logging_setup_done = True


def configure_uvicorn_logging() -> None:
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvi = logging.getLogger(name)
        uvi.handlers.clear()
        uvi.propagate = False
        if _is_dev():
            uvi.setLevel(logging.DEBUG)
            uvi.addHandler(_get_dev_handler())
        else:
            uvi.setLevel(logging.ERROR)
            uvi.addHandler(_get_prod_console_handler())
        # Add file handlers to error loggers only; access logs are too chatty for files
        if name != "uvicorn.access":
            _attach_file_handlers(uvi)
