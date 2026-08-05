"""
Tests for the user-facing update check.

The defect these guard against: the worker and its QThread were held in local
variables, so returning from the function dropped the last reference and Qt tore
down a running thread -- which aborts the process. Clicking "Check for Updates"
closed Snappix outright.
"""

from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QMessageBox

from src import update_dialog
from src.updater import UpdateInfo
from tests.qt_test_utils import ensure_qapp


class BridgeLifetimeTests(unittest.TestCase):
    """
    Class BridgeLifetimeTests

    Covers the objects that must outlive a single call.
    """

    def test_bridge_is_module_level(self) -> None:
        """
        A bridge created per call would be garbage collected while its thread is
        still running, which is what killed the process.

        Returns:
            None
        """

        ensure_qapp()
        first = update_dialog._bridge()
        self.assertIsNotNone(first)
        # Same object every time, and reachable from the module rather than a
        # local scope -- that is what keeps it alive while a thread uses it.
        self.assertIs(update_dialog._bridge(), first)
        self.assertIs(update_dialog._BRIDGE, first)

    def test_no_qthread_is_used(self) -> None:
        """
        A plain daemon thread keeps Qt object lifetimes out of local scopes.

        Returns:
            None
        """

        # Checked by namespace, not by scanning text: the module docstring
        # names QThread while explaining why it is not used.
        self.assertFalse(hasattr(update_dialog, "QThread"))
        self.assertTrue(hasattr(update_dialog, "threading"))


class CheckFlowTests(unittest.TestCase):
    """
    Class CheckFlowTests

    Covers each outcome of a check reaching the user without blocking.
    """

    def setUp(self) -> None:
        """
        Returns:
            None
        """

        self.app = ensure_qapp()
        if update_dialog._BUSY.locked():
            update_dialog._BUSY.release()

    def _run(self, info: UpdateInfo, answer=QMessageBox.StandardButton.No) -> dict:
        """
        Runs one full check with the dialogs stubbed out.

        Args:
            info: Result the check should report.
            answer: Button the confirmation dialog should return.

        Returns:
            dict: Which dialogs were shown.
        """

        shown: dict[str, str] = {}

        def note(kind):
            def handler(*args, **kwargs):
                shown[kind] = str(args[2]) if len(args) > 2 else ""
                return answer

            return handler

        with patch.object(QMessageBox, "information", side_effect=note("info")), \
             patch.object(QMessageBox, "warning", side_effect=note("warn")), \
             patch.object(QMessageBox, "question", side_effect=note("question")), \
             patch.object(update_dialog, "check", return_value=info), \
             patch.object(update_dialog, "_install") as install:
            update_dialog.check_for_updates(None)
            # No nested exec(): the suite shares one QApplication, and a nested
            # event loop there can outlive its quit() and hang the whole run.
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline and not (shown or install.called):
                self.app.processEvents()
                time.sleep(0.01)
            shown["installed"] = install.called
        return shown

    def test_up_to_date_reports_and_releases(self) -> None:
        """
        Returns:
            None
        """

        shown = self._run(UpdateInfo(available=False, local="abc1234567"))
        self.assertIn("info", shown)
        self.assertIn("up to date", shown["info"])
        self.assertFalse(update_dialog._BUSY.locked())

    def test_failed_check_warns_and_releases(self) -> None:
        """
        Returns:
            None
        """

        shown = self._run(UpdateInfo(error="offline"))
        self.assertIn("warn", shown)
        self.assertIn("offline", shown["warn"])
        self.assertFalse(update_dialog._BUSY.locked())

    def test_available_update_asks_first(self) -> None:
        """
        Returns:
            None
        """

        shown = self._run(
            UpdateInfo(available=True, local="aaa", remote="bbb", summary="newer work")
        )
        self.assertIn("question", shown)
        self.assertIn("newer work", shown["question"])

    def test_declining_the_update_installs_nothing(self) -> None:
        """
        Returns:
            None
        """

        shown = self._run(
            UpdateInfo(available=True, local="aaa", remote="bbb"),
            answer=QMessageBox.StandardButton.No,
        )
        self.assertFalse(shown["installed"])
        self.assertFalse(update_dialog._BUSY.locked())

    def test_accepting_the_update_starts_the_fetch(self) -> None:
        """
        Returns:
            None
        """

        shown = self._run(
            UpdateInfo(available=True, local="aaa", remote="bbb"),
            answer=QMessageBox.StandardButton.Yes,
        )
        self.assertTrue(shown["installed"])


class ReentrancyTests(unittest.TestCase):
    """
    Class ReentrancyTests

    Covers a second click while a check is still running.
    """

    def setUp(self) -> None:
        """
        Returns:
            None
        """

        ensure_qapp()
        if update_dialog._BUSY.locked():
            update_dialog._BUSY.release()

    def tearDown(self) -> None:
        """
        Returns:
            None
        """

        if update_dialog._BUSY.locked():
            update_dialog._BUSY.release()

    def test_second_call_while_busy_does_nothing(self) -> None:
        """
        Returns:
            None
        """

        update_dialog._BUSY.acquire()
        with patch.object(update_dialog, "check") as checker, \
             patch("threading.Thread") as thread:
            update_dialog.check_for_updates(None)
        checker.assert_not_called()
        thread.assert_not_called()

    def test_worker_thread_is_a_daemon(self) -> None:
        """
        A non-daemon thread would keep the process alive after the window closes.

        Returns:
            None
        """

        captured: dict[str, object] = {}
        real_thread = threading.Thread

        def spy(*args, **kwargs):
            captured.update(kwargs)
            return real_thread(target=lambda: None, daemon=True)

        with patch("threading.Thread", side_effect=spy), \
             patch.object(update_dialog, "check", return_value=UpdateInfo()):
            update_dialog.check_for_updates(None)

        self.assertTrue(captured.get("daemon"))
        self.assertEqual(captured.get("name"), "snappix-update-check")


if __name__ == "__main__":
    unittest.main()
