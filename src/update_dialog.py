"""
User-facing update check.

Modelled on youtube-clipster: the network call and the fetch both run on a plain
daemon thread, and the result is handed back to the GUI thread through a signal.

Two things here are load-bearing and easy to get wrong:

* The bridge object lives at module level. An earlier version kept its worker and
  its ``QThread`` in local variables; when the function returned, Python dropped
  the last reference and Qt tore down a still-running thread, which aborts the
  whole process. Clicking "Check for Updates" simply closed Snappix.
* A ``threading.Thread`` marked daemon is used rather than ``QThread``, so no Qt
  object's lifetime is tied to a local scope in the first place.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from src.constants import APP_NAME
from src.updater import UpdateInfo, apply, check, restart


class _UpdateBridge(QObject):
    """
    Class _UpdateBridge

    Carries worker-thread results back into the GUI thread.

    Emitting a signal across threads queues the call onto the receiving thread's
    event loop, which is what makes it safe to touch widgets in the slots.
    """

    checked = Signal(object)
    applied = Signal(bool, str)


# Module level on purpose: the reference must outlive every call, or Qt tears
# down objects a running thread still uses. Created lazily rather than at import
# time, because a QObject built before QApplication exists is destroyed after Qt
# has already shut down, which crashes the interpreter on exit.
_BRIDGE: "_UpdateBridge | None" = None
_BUSY = threading.Lock()
_PARENT: QWidget | None = None


def _bridge() -> "_UpdateBridge":
    """
    Returns the shared bridge, creating and wiring it on first use.

    Returns:
        _UpdateBridge: The signal carrier back to the GUI thread.
    """

    global _BRIDGE
    if _BRIDGE is None:
        _BRIDGE = _UpdateBridge()
        _BRIDGE.checked.connect(_on_checked)
        _BRIDGE.applied.connect(_on_applied)
    return _BRIDGE


def check_for_updates(parent: QWidget | None = None) -> None:
    """
    Checks for a newer version and offers to install it.

    Args:
        parent: Optional parent widget for the dialogs.

    Returns:
        None
    """

    global _PARENT

    if not _BUSY.acquire(blocking=False):
        # A check is already running; a second click must not start another.
        return

    _PARENT = parent
    bridge = _bridge()
    QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)

    def work() -> None:
        """
        Talks to GitHub off the interface thread.

        Returns:
            None
        """

        try:
            bridge.checked.emit(check())
        except Exception as exc:  # noqa: BLE001
            bridge.checked.emit(UpdateInfo(error=str(exc)))

    threading.Thread(target=work, name="snappix-update-check", daemon=True).start()


def _install(info: UpdateInfo) -> None:
    """
    Fetches the new version off the interface thread.

    Args:
        info: The check result that offered this update.

    Returns:
        None
    """

    bridge = _bridge()
    QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)

    def work() -> None:
        """
        Returns:
            None
        """

        try:
            success, message = apply()
        except Exception as exc:  # noqa: BLE001
            success, message = False, str(exc)
        bridge.applied.emit(success, message)

    threading.Thread(target=work, name="snappix-update-apply", daemon=True).start()


def _on_checked(info: UpdateInfo) -> None:
    """
    Reports the outcome and offers to apply an available update.

    Args:
        info: Result of the repository check.

    Returns:
        None
    """

    QApplication.restoreOverrideCursor()
    parent = _PARENT

    if info.error:
        _BUSY.release()
        QMessageBox.warning(
            parent,
            f"{APP_NAME} Update",
            f"Could not check for updates:\n{info.error}",
        )
        return

    if not info.available:
        _BUSY.release()
        detail = f"\n\nInstalled commit: {info.local}" if info.local else ""
        QMessageBox.information(
            parent,
            f"{APP_NAME} Update",
            f"{APP_NAME} is up to date.{detail}",
        )
        return

    summary = f"\n\nLatest change:\n{info.summary}" if info.summary else ""
    answer = QMessageBox.question(
        parent,
        f"{APP_NAME} Update",
        (
            f"A newer version is available.\n\n"
            f"Installed: {info.local}\nAvailable: {info.remote}{summary}\n\n"
            "Install it now? Snappix will restart."
        ),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes,
    )
    if answer != QMessageBox.StandardButton.Yes:
        _BUSY.release()
        return

    # The lock stays held across the fetch: it is the same operation continuing.
    _install(info)


def _on_applied(success: bool, message: str) -> None:
    """
    Restarts when the update worked, reports the reason when it did not.

    Args:
        success: True when the new version was fetched.
        message: Output of the update, for the user.

    Returns:
        None
    """

    QApplication.restoreOverrideCursor()
    _BUSY.release()
    parent = _PARENT

    if not success:
        QMessageBox.warning(parent, f"{APP_NAME} Update", f"Update failed:\n{message}")
        return

    QMessageBox.information(
        parent,
        f"{APP_NAME} Update",
        f"Update installed.\n\n{message}\n\n{APP_NAME} restarts now.",
    )
    restart()
