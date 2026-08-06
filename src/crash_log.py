"""
Crash and fault logging.

A crash reaches the user as "it closed while I moved something". This module's
job is to turn that into a file naming the exact frames, because a segfault
inside Qt kills the process without printing anything at all.

Four sources feed one log:

* **faulthandler** -- fatal signals (segfault, abort). These are the ones that
  leave no Python traceback on their own.
* **sys.excepthook** -- uncaught Python exceptions on the main thread.
* **threading.excepthook** -- the same on worker threads, which otherwise die
  silently.
* **Qt's message handler** -- Qt's own warnings. These matter most here: PySide
  prints "Internal C++ object already deleted" *before* the process dies, so the
  warning preceding a crash often names the cause the stack no longer can.

On top of that a short breadcrumb trail records what the user did. A segfault
deep inside Qt's scene graph produces a stack that says little about which
action triggered it; the breadcrumbs say "selected arrow, moved arrow".
"""

from __future__ import annotations

import sys
import threading
import traceback
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Deque

# Kept module-level and never closed: faulthandler writes into this descriptor
# from a signal handler, so it must outlive every frame it might have to dump.
_HANDLE = None
_BREADCRUMBS: Deque[str] = deque(maxlen=40)
_LOCK = threading.Lock()


def log_path() -> Path:
    """
    Returns the file crashes are recorded in.

    Returns:
        Path: Crash log location.
    """

    from src.paths import user_cache_dir

    return user_cache_dir() / "crash.log"


def breadcrumb(action: str) -> None:
    """
    Records one user action for the next crash report.

    Kept in memory only: writing every action to disk would turn each mouse drag
    into file I/O. The trail is flushed as part of a crash dump instead.

    Args:
        action: Short description, e.g. "move arrow".

    Returns:
        None
    """

    stamp = datetime.now().strftime("%H:%M:%S")
    with _LOCK:
        _BREADCRUMBS.append(f"{stamp} {action}")


def recent_breadcrumbs() -> list[str]:
    """
    Returns the recorded action trail, oldest first.

    Returns:
        list[str]: Recent user actions.
    """

    with _LOCK:
        return list(_BREADCRUMBS)


def _write(text: str) -> None:
    """
    Appends one block to the crash log.

    Args:
        text: Block to write.

    Returns:
        None
    """

    if _HANDLE is None:
        return
    try:
        _HANDLE.write(text)
        _HANDLE.flush()
    except (OSError, ValueError):
        # A full or unwritable disk must not turn a crash report into a crash.
        pass


def _dump(title: str, body: str) -> None:
    """
    Writes one titled crash block including the breadcrumb trail.

    Args:
        title: Block heading.
        body: Traceback or message text.

    Returns:
        None
    """

    trail = recent_breadcrumbs()
    lines = [
        f"\n----- {title} at {datetime.now().isoformat()} -----\n",
        body if body.endswith("\n") else body + "\n",
    ]
    if trail:
        lines.append("Recent actions (oldest first):\n")
        lines.extend(f"  {entry}\n" for entry in trail)
    _write("".join(lines))


def log_note(title: str, body: str) -> None:
    """
    Records a titled diagnostic block with the current breadcrumb trail.

    Used for degraded-but-survivable states that must stay diagnosable after the
    fact, such as a screen grab that came back empty.

    Args:
        title: Block heading.
        body: Detail text.

    Returns:
        None
    """

    _dump(title, body)


def log_exception(title: str) -> None:
    """
    Records the exception being handled, without letting it escape.

    Used at Python/Qt boundaries: an exception raised inside a Qt virtual
    override unwinds through C++ and takes the process down with a segfault, so
    those call sites swallow it and report it here instead.

    Args:
        title: Block heading describing where the failure happened.

    Returns:
        None
    """

    _dump(title, traceback.format_exc())


def _excepthook(exc_type, exc_value, exc_traceback) -> None:
    """
    Records an uncaught exception, then defers to the previous hook.

    Args:
        exc_type: Exception class.
        exc_value: Exception instance.
        exc_traceback: Traceback object.

    Returns:
        None
    """

    _dump(
        "Uncaught exception",
        "".join(traceback.format_exception(exc_type, exc_value, exc_traceback)),
    )
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


def _thread_excepthook(args) -> None:
    """
    Records an uncaught exception raised on a worker thread.

    Args:
        args: Payload from ``threading.excepthook``.

    Returns:
        None
    """

    _dump(
        f"Uncaught exception in thread {getattr(args.thread, 'name', '?')}",
        "".join(
            traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
        ),
    )


def install_qt_message_handler() -> None:
    """
    Routes Qt's own warnings and fatal messages into the crash log.

    Called separately from ``install`` because it needs Qt imported, which the
    very early startup path deliberately avoids.

    Returns:
        None
    """

    try:
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler
    except ImportError:
        return

    interesting = {QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg}

    def handler(mode, context, message) -> None:
        """
        Args:
            mode: Qt message severity.
            context: Qt log context.
            message: The message text.

        Returns:
            None
        """

        if mode in interesting:
            location = ""
            if getattr(context, "file", None):
                location = f" ({context.file}:{context.line})"
            _dump(f"Qt {mode.name}", f"{message}{location}")
        # Keep Qt's messages on stderr as well, so a terminal run still shows them.
        print(message, file=sys.stderr)

    qInstallMessageHandler(handler)


def install() -> Path | None:
    """
    Enables crash logging for this process.

    Never raises: diagnostics must not be the reason the app fails to start.

    Returns:
        Path | None: The log file in use, or None when it could not be opened.
    """

    global _HANDLE
    import faulthandler

    path: Path | None = None
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a", encoding="utf-8")
        handle.write(f"\n===== Snappix started {datetime.now().isoformat()} =====\n")
        handle.flush()
        _HANDLE = handle
        faulthandler.enable(file=handle, all_threads=True)
    except OSError:
        faulthandler.enable(all_threads=True)
        path = None

    sys.excepthook = _excepthook
    threading.excepthook = _thread_excepthook
    return path
