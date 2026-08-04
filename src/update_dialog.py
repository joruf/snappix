"""
User-facing update check.

The check runs off the GUI thread: GitHub can take seconds or hang until the
timeout, and a frozen window during a routine "is there a newer version?" reads
as a crash.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from src.constants import APP_NAME
from src.updater import UpdateInfo, apply, check, restart


class _CheckWorker(QObject):
    """
    Class _CheckWorker

    Runs one repository check on a worker thread.
    """

    finished = Signal(object)

    def run(self) -> None:
        """
        Performs the check and emits its result.

        Returns:
            None
        """

        self.finished.emit(check())


def check_for_updates(parent: QWidget | None = None) -> None:
    """
    Checks for a newer version and offers to install it.

    Args:
        parent: Optional parent widget for the dialogs.

    Returns:
        None
    """

    thread = QThread()
    worker = _CheckWorker()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)

    def on_finished(info: UpdateInfo) -> None:
        """
        Reports the outcome and offers to apply an available update.

        Args:
            info: Result of the repository check.

        Returns:
            None
        """

        thread.quit()
        thread.wait()
        # Keep both alive until the thread has actually stopped.
        worker.deleteLater()
        thread.deleteLater()
        QApplication.restoreOverrideCursor()
        _present(parent, info)

    worker.finished.connect(on_finished)
    thread.start()


def _present(parent: QWidget | None, info: UpdateInfo) -> None:
    """
    Shows the result of a check and runs the update when confirmed.

    Args:
        parent: Optional parent widget.
        info: Result of the repository check.

    Returns:
        None
    """

    if info.error:
        QMessageBox.warning(
            parent,
            f"{APP_NAME} Update",
            f"Could not check for updates:\n{info.error}",
        )
        return

    if not info.available:
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
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.Yes,
    )
    if answer != QMessageBox.Yes:
        return

    success, message = apply()
    if not success:
        QMessageBox.warning(parent, f"{APP_NAME} Update", f"Update failed:\n{message}")
        return

    QMessageBox.information(
        parent,
        f"{APP_NAME} Update",
        f"Update installed.\n\n{message}\n\n{APP_NAME} restarts now.",
    )
    restart()
