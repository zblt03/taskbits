"""Entry point: ``python -m taskbits``."""

from __future__ import annotations

import argparse
import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from types import TracebackType

from taskbits import __version__, paths
from taskbits.single_instance import SingleInstance

log = logging.getLogger("taskbits")

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
LOG_MAX_BYTES = 1_000_000
LOG_BACKUPS = 3


def _log_uncaught(
    exc_type: type[BaseException],
    exc: BaseException,
    tb: TracebackType | None,
) -> None:
    """Send otherwise-silent crashes (there is no console under pythonw) to the log."""
    log.critical("Uncaught exception", exc_info=(exc_type, exc, tb))


def _log_uncaught_in_thread(args: threading.ExceptHookArgs) -> None:
    """Same as :func:`_log_uncaught`, for exceptions in background threads."""
    log.critical(
        "Uncaught exception in thread %s",
        args.thread.name if args.thread else "?",
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )


def setup_logging() -> None:
    """Log to a rotating file in %LOCALAPPDATA%\\taskbits and, if present, the console."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        paths.log_path(), maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(handler)
    if sys.stderr is not None:  # None when started with pythonw / as a windowed .exe
        console = logging.StreamHandler()
        console.setLevel(logging.WARNING)
        console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        root.addHandler(console)
    sys.excepthook = _log_uncaught
    threading.excepthook = _log_uncaught_in_thread


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, start the app and return a process exit code."""
    parser = argparse.ArgumentParser(
        prog="taskbits", description="Small widgets for the Windows 11 taskbar."
    )
    parser.add_argument(
        "--overlay",
        action="store_true",
        help="float over the taskbar instead of living inside it",
    )
    args = parser.parse_args(argv)
    setup_logging()

    instance = SingleInstance()
    if instance.already_running:
        log.info("Taskbits is already running; exiting")
        return 0

    from taskbits.app import run  # imported here so argument errors don't load Qt

    log.info("Taskbits %s starting", __version__)
    return run(embed=not args.overlay)


if __name__ == "__main__":
    raise SystemExit(main())
