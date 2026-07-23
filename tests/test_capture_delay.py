"""
Unit tests for delayed capture countdown cancellation.
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from src.capture import CaptureDelayOverlay, CaptureMode, CaptureRequest, execute_capture_request
    from tests.qt_test_utils import ensure_qapp

    HAS_PYSIDE6 = True
except ModuleNotFoundError:
    HAS_PYSIDE6 = False


@unittest.skipUnless(HAS_PYSIDE6, "PySide6 is required for capture delay tests")
class TestCaptureDelayOverlay(unittest.TestCase):
    """
    Verifies Escape cancellation during capture delay countdown.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures Qt application exists for widget tests.
        """

        cls._app = ensure_qapp()

    def test_escape_cancels_delay_overlay(self) -> None:
        """
        Ensures Escape cancels the countdown before capture starts.
        """

        overlay = CaptureDelayOverlay(5)
        cancelled = {"value": False}
        finished = {"value": False}
        overlay.cancelled.connect(lambda: cancelled.__setitem__("value", True))
        overlay.finished.connect(lambda: finished.__setitem__("value", True))
        overlay.show()
        QApplication.processEvents()

        overlay._cancel()  # pylint: disable=protected-access
        QApplication.processEvents()

        self.assertTrue(cancelled["value"])
        self.assertFalse(finished["value"])
        self.assertFalse(overlay.isVisible())

    def test_execute_capture_request_delay_can_be_cancelled(self) -> None:
        """
        Ensures delayed capture invokes on_cancel when countdown is aborted.
        """

        captured = {"value": False}
        cancelled = {"value": False}

        execute_capture_request(
            request=CaptureRequest(mode=CaptureMode.FULL_SCREEN, delay_seconds=3),
            on_capture=lambda _pixmap: captured.__setitem__("value", True),
            on_cancel=lambda: cancelled.__setitem__("value", True),
        )
        QApplication.processEvents()

        from src import capture as capture_module

        self.assertTrue(capture_module._ACTIVE_OVERLAYS)  # pylint: disable=protected-access
        overlay = capture_module._ACTIVE_OVERLAYS[-1]  # pylint: disable=protected-access
        self.assertIsInstance(overlay, CaptureDelayOverlay)
        overlay._cancel()  # pylint: disable=protected-access
        QApplication.processEvents()

        self.assertTrue(cancelled["value"])
        self.assertFalse(captured["value"])

    def test_finish_hides_countdown_before_capture_signal(self) -> None:
        """
        Ensures countdown text is hidden before the finished signal fires.
        """

        from PySide6.QtCore import QEventLoop

        overlay = CaptureDelayOverlay(1)
        states: list[tuple[bool, bool]] = []
        loop = QEventLoop()

        def on_finished() -> None:
            states.append(
                (
                    overlay.isVisible(),
                    overlay._countdown_label.isVisible(),  # pylint: disable=protected-access
                )
            )
            loop.quit()

        overlay.finished.connect(on_finished)
        overlay.show()
        QApplication.processEvents()
        overlay._remaining = 1  # pylint: disable=protected-access
        overlay._on_tick()  # pylint: disable=protected-access
        QTimer.singleShot(500, loop.quit)
        loop.exec()
        self.assertTrue(states)
        self.assertFalse(states[0][0])
        self.assertFalse(states[0][1])
        self.assertFalse(overlay._countdown_label.text())  # pylint: disable=protected-access
        overlay.close()
