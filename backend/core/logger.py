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
    # INFO so uvicorn's startup banner ("Uvicorn running on...",
    # "Application startup complete.") reaches the console in frozen builds.
    # Regular backend loggers stay capped at ERROR via their own logger
    # level (see get_logger below), so this does not add general verbosity.
    handler.setLevel(logging.INFO)
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
    """Add any file handlers not yet on logger and lower its level to allow INFO through.

    Used by setup_logging() for the "backend"/"peach" parent loggers, and by
    configure_uvicorn_logging() for the uvicorn loggers directly (those live
    outside the "backend"/"peach" namespace, so they don't inherit the parent
    loggers' handlers via propagation and still need their own).
    """
    for h in _file_handlers:
        if h not in logger.handlers:
            logger.addHandler(h)
    if _file_handlers and logger.level > logging.INFO:
        logger.setLevel(logging.INFO)


def _attach_console_handler(logger: logging.Logger) -> None:
    """Add the dev or prod console handler to logger if it doesn't already have one.

    Called by setup_logging() on the "backend" and "peach" parent loggers only; every
    descendant logger (get_logger()-built or a plain logging.getLogger(name)) reaches
    this handler via propagation instead of getting its own copy. _get_dev_handler()/
    _get_prod_console_handler() are singletons, so the "already in logger.handlers"
    check below keeps repeat calls idempotent.
    """
    handler = _get_dev_handler() if _is_dev() else _get_prod_console_handler()
    if handler not in logger.handlers:
        logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Return a logger with propagation on and its level set for dev/prod filtering.

    Console and file handlers are NOT attached here, they live on the "backend"/
    "peach" parent loggers (see setup_logging()) and this logger's records reach
    them via propagation (propagate=True), so output works regardless of whether
    this logger is first created before or after setup_logging() runs.
    """
    logger = logging.getLogger(name)
    logger.propagate = True
    logger.setLevel(logging.DEBUG if _is_dev() else logging.ERROR)
    return logger


def setup_logging() -> None:
    """Create RotatingFileHandlers and attach them, plus the console handler, to the
    "backend" and "peach" parent loggers, once.

    Every logger named "backend.*" or "peach.*" propagates its records up to these
    parents by default (propagate=True), whether it was built via get_logger() or a
    plain logging.getLogger(name), and whether it was first created before or after
    this call. A single parent-level attachment therefore covers all of them,
    including ones that don't exist yet at call time, unlike the previous approach
    of sweeping logging.root.manager.loggerDict, which only reached loggers that
    already existed at the moment this function ran and silently dropped output
    from any backend/peach logger created afterward.

    Safe to call multiple times; only the first call has any effect. File handlers
    write to logs/ under the project root and are independent of stdout/stderr,
    they work correctly even in windowless frozen builds.
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

    for parent_name in ("backend", "peach"):
        parent_logger = logging.getLogger(parent_name)
        # Owns log routing for the whole backend/peach namespace from here down,
        # same as the propagate=False every individual child logger used to set
        # for itself, just moved to this one namespace root instead.
        parent_logger.propagate = False
        _attach_file_handlers(parent_logger)
        _attach_console_handler(parent_logger)
        # NOTSET (0) is what logging.getLogger("backend"/"peach") starts at if
        # nothing has set it yet. Left alone, a descendant logger with no level
        # of its own (a plain logging.getLogger(name) module, never routed
        # through get_logger()) would resolve its effective level past this
        # parent to root's default WARNING and drop INFO/DEBUG records even
        # though a handler now exists. Set explicitly here to match what
        # get_logger() itself sets a dev/prod logger's own level to.
        if parent_logger.level == logging.NOTSET:
            parent_logger.setLevel(logging.DEBUG if _is_dev() else logging.INFO)

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
            # uvicorn/uvicorn.error carry the startup banner at INFO level
            # ("Uvicorn running on...", "Application startup complete.") so a
            # tester running the packaged exe sees confirmation the server is
            # up. uvicorn.access stays at ERROR, per-request logging is off
            # in production by design.
            uvi.setLevel(logging.INFO if name != "uvicorn.access" else logging.ERROR)
            uvi.addHandler(_get_prod_console_handler())
        # Add file handlers to error loggers only; access logs are too chatty for files
        if name != "uvicorn.access":
            _attach_file_handlers(uvi)
