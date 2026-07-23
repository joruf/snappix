"""
Regression tests: Capture chrome must stay off-screen during framebuffer grabs.

These tests lock the hide + compositor-settle contract so fullscreen, region,
window, scroll, delayed capture, and color pick cannot regress into including
the Capture panel in screenshots.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

try:
    from PySide6.QtCore import QEventLoop, QRect, QTimer
    from PySide6.QtGui import QColor, QPixmap
    from PySide6.QtWidgets import QApplication, QWidget

    from src.capture import (
        CAPTURE_UI_SETTLE_MS,
        CaptureDelayOverlay,
        CaptureMode,
        CaptureRequest,
        DesktopSnapshot,
        execute_capture_request,
        schedule_capture_after_ui_settle,
    )
    from tests.qt_test_utils import ensure_qapp

    HAS_PYSIDE6 = True
except ModuleNotFoundError:
    HAS_PYSIDE6 = False


def _solid_snapshot(width: int = 80, height: int = 60) -> DesktopSnapshot:
    """
    Builds a minimal desktop snapshot for capture tests.

    Args:
        width: Pixmap width.
        height: Pixmap height.

    Returns:
        DesktopSnapshot: Solid-color snapshot.
    """

    pixmap = QPixmap(width, height)
    pixmap.fill(QColor(10, 20, 30))
    return DesktopSnapshot(pixmap=pixmap, virtual_geometry=QRect(0, 0, width, height))


def _wait_past_settle(extra_ms: int = 80) -> None:
    """
    Blocks until after the capture UI settle timer would have fired.

    Args:
        extra_ms: Extra milliseconds beyond CAPTURE_UI_SETTLE_MS.

    Returns:
        None
    """

    loop = QEventLoop()
    QTimer.singleShot(CAPTURE_UI_SETTLE_MS + extra_ms, loop.quit)
    loop.exec()


@unittest.skipUnless(HAS_PYSIDE6, "PySide6 is required for capture settle tests")
class TestCaptureUiSettle(unittest.TestCase):
    """
    Verifies Capture panel hide settle timing before framebuffer grabs.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def test_settle_delay_is_long_enough_for_compositor(self) -> None:
        """
        Ensures settle delay stays above a floor that lets windows leave the screen.
        """

        self.assertGreaterEqual(CAPTURE_UI_SETTLE_MS, 100)

    def test_schedule_capture_after_ui_settle_defers_callback(self) -> None:
        """
        Ensures the settle helper does not invoke the callback synchronously.
        """

        called = {"value": False}

        def mark_called() -> None:
            called["value"] = True

        schedule_capture_after_ui_settle(mark_called)
        self.assertFalse(called["value"])
        _wait_past_settle()
        self.assertTrue(called["value"])

    @patch("src.capture.capture_full_screen")
    def test_immediate_fullscreen_capture_waits_for_settle(
        self,
        mock_capture: MagicMock,
    ) -> None:
        """
        Ensures fullscreen capture is deferred so hidden UI can leave the screen.
        """

        mock_capture.return_value = _solid_snapshot()
        captured = {"value": False}

        execute_capture_request(
            request=CaptureRequest(mode=CaptureMode.FULL_SCREEN, delay_seconds=0),
            on_capture=lambda _pixmap: captured.__setitem__("value", True),
            on_cancel=lambda: None,
        )
        QApplication.processEvents()
        self.assertFalse(mock_capture.called)
        self.assertFalse(captured["value"])

        _wait_past_settle()
        self.assertTrue(mock_capture.called)
        self.assertTrue(captured["value"])

    @patch("src.capture.capture_full_screen")
    def test_immediate_region_capture_waits_for_settle(
        self,
        mock_capture: MagicMock,
    ) -> None:
        """
        Ensures region capture snapshots only after the UI settle delay.
        """

        mock_capture.return_value = _solid_snapshot()
        with patch("src.capture.is_wayland_session", return_value=False):
            execute_capture_request(
                request=CaptureRequest(mode=CaptureMode.REGION, delay_seconds=0),
                on_capture=lambda _pixmap: None,
                on_cancel=lambda: None,
            )
            QApplication.processEvents()
            self.assertFalse(mock_capture.called)
            _wait_past_settle()
            self.assertTrue(mock_capture.called)

        from src import capture as capture_module

        for overlay in list(capture_module._ACTIVE_OVERLAYS):  # pylint: disable=protected-access
            overlay.close()
            capture_module._untrack_overlay(overlay)  # pylint: disable=protected-access

    @patch("src.capture.which", return_value="/usr/bin/xdotool")
    @patch("src.capture.is_wayland_session", return_value=False)
    @patch("src.capture.capture_full_screen")
    def test_immediate_window_capture_waits_for_settle(
        self,
        mock_capture: MagicMock,
        _mock_wayland: MagicMock,
        _mock_which: MagicMock,
    ) -> None:
        """
        Ensures window capture snapshots only after the UI settle delay.
        """

        mock_capture.return_value = _solid_snapshot()
        with patch("src.capture.subprocess.Popen") as mock_popen:
            process = MagicMock()
            process.poll.return_value = 1
            process.stdout = MagicMock()
            process.stdout.read.return_value = ""
            mock_popen.return_value = process

            execute_capture_request(
                request=CaptureRequest(mode=CaptureMode.WINDOW, delay_seconds=0),
                on_capture=lambda _pixmap: None,
                on_cancel=lambda: None,
            )
            QApplication.processEvents()
            self.assertFalse(mock_capture.called)
            _wait_past_settle()
            self.assertTrue(mock_capture.called)

        from src import capture as capture_module

        for overlay in list(capture_module._ACTIVE_OVERLAYS):  # pylint: disable=protected-access
            overlay.close()
            capture_module._untrack_overlay(overlay)  # pylint: disable=protected-access

    @patch("src.capture.execute_scroll_capture")
    def test_immediate_scroll_capture_waits_for_settle(
        self,
        mock_scroll: MagicMock,
    ) -> None:
        """
        Ensures scroll capture starts only after the UI settle delay.
        """

        execute_capture_request(
            request=CaptureRequest(mode=CaptureMode.SCROLL, delay_seconds=0),
            on_capture=lambda _pixmap: None,
            on_cancel=lambda: None,
        )
        QApplication.processEvents()
        self.assertFalse(mock_scroll.called)
        _wait_past_settle()
        self.assertTrue(mock_scroll.called)

    def test_all_immediate_modes_use_settle_scheduler(self) -> None:
        """
        Ensures every capture mode with delay=0 goes through settle, not a sync grab.
        """

        modes = (
            CaptureMode.FULL_SCREEN,
            CaptureMode.REGION,
            CaptureMode.WINDOW,
            CaptureMode.SCROLL,
        )
        with patch("src.capture.schedule_capture_after_ui_settle") as mock_schedule:
            for mode in modes:
                mock_schedule.reset_mock()
                execute_capture_request(
                    request=CaptureRequest(mode=mode, delay_seconds=0),
                    on_capture=lambda _pixmap: None,
                    on_cancel=lambda: None,
                )
                self.assertEqual(
                    mock_schedule.call_count,
                    1,
                    msg=f"mode={mode} must schedule settle before capture",
                )

    def test_delay_overlay_defers_finished_by_settle_ms(self) -> None:
        """
        Ensures countdown hide settles before the finished signal starts capture.
        """

        overlay = CaptureDelayOverlay(1)
        finished_at: list[int] = []
        loop = QEventLoop()
        timer = QTimer()
        timer.setInterval(10)
        elapsed = {"ms": 0}

        def on_tick() -> None:
            elapsed["ms"] += 10

        def on_finished() -> None:
            finished_at.append(elapsed["ms"])
            loop.quit()

        timer.timeout.connect(on_tick)
        overlay.finished.connect(on_finished)
        overlay.show()
        QApplication.processEvents()
        timer.start()
        overlay._remaining = 1  # pylint: disable=protected-access
        overlay._on_tick()  # pylint: disable=protected-access
        QTimer.singleShot(CAPTURE_UI_SETTLE_MS + 400, loop.quit)
        loop.exec()
        timer.stop()
        overlay.close()

        self.assertTrue(finished_at)
        self.assertGreaterEqual(finished_at[0], CAPTURE_UI_SETTLE_MS - 30)

    def test_delay_overlay_is_hidden_when_finished_fires(self) -> None:
        """
        Ensures delay chrome is invisible at the moment capture may begin.
        """

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
        QTimer.singleShot(CAPTURE_UI_SETTLE_MS + 400, loop.quit)
        loop.exec()
        self.assertTrue(states)
        self.assertFalse(states[0][0])
        self.assertFalse(states[0][1])
        overlay.close()


@unittest.skipUnless(HAS_PYSIDE6, "PySide6 is required for capture hide tests")
class TestCapturePanelHiddenBeforeCapture(unittest.TestCase):
    """
    Verifies AppController hides Capture chrome before any capture path runs.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def setUp(self) -> None:
        """
        Builds a minimal controller stub with real hide/start methods.
        """

        from run import AppController

        self.controller = object.__new__(AppController)
        self.controller._capture_in_progress = False
        self.controller._tray_available = False
        self.controller.tray_icon = MagicMock()
        self.controller.capture_panel = QWidget()
        self.controller.capture_panel.show()
        QApplication.processEvents()
        self.assertTrue(self.controller.capture_panel.isVisible())

    def test_hide_windows_for_capture_hides_panel(self) -> None:
        """
        Ensures the Capture panel is hidden and flushed before settle begins.
        """

        self.controller._hide_windows_for_capture()
        self.assertFalse(self.controller.capture_panel.isVisible())

    @patch("src.capture.execute_capture_request")
    def test_start_capture_hides_panel_before_execute(
        self,
        mock_execute: MagicMock,
    ) -> None:
        """
        Ensures every capture method hides the panel before execute_capture_request.
        """

        order: list[str] = []

        def record_hide() -> None:
            order.append("hide")
            self.controller.capture_panel.hide()
            QApplication.processEvents()

        def record_execute(**_kwargs) -> None:
            order.append("execute")
            self.assertFalse(self.controller.capture_panel.isVisible())

        self.controller._hide_windows_for_capture = record_hide  # type: ignore[method-assign]
        mock_execute.side_effect = record_execute

        for mode in (
            CaptureMode.FULL_SCREEN,
            CaptureMode.REGION,
            CaptureMode.WINDOW,
            CaptureMode.SCROLL,
        ):
            order.clear()
            self.controller._capture_in_progress = False
            self.controller.capture_panel.show()
            QApplication.processEvents()
            self.controller.start_capture(
                CaptureRequest(mode=mode, delay_seconds=0)
            )
            self.assertEqual(
                order,
                ["hide", "execute"],
                msg=f"mode={mode} must hide Capture panel before execute",
            )
            self.assertFalse(self.controller.capture_panel.isVisible())

    @patch("src.capture.execute_color_pick")
    @patch("src.capture.schedule_capture_after_ui_settle")
    def test_color_pick_hides_panel_then_settles(
        self,
        mock_schedule: MagicMock,
        mock_pick: MagicMock,
    ) -> None:
        """
        Ensures color pick hides the panel and only then schedules settle work.
        """

        order: list[str] = []

        def record_hide() -> None:
            order.append("hide")
            self.controller.capture_panel.hide()
            QApplication.processEvents()

        def record_schedule(callback) -> None:
            order.append("schedule")
            self.assertFalse(self.controller.capture_panel.isVisible())
            callback()

        self.controller._hide_windows_for_capture = record_hide  # type: ignore[method-assign]
        mock_schedule.side_effect = record_schedule

        self.controller.start_color_pick()

        self.assertEqual(order, ["hide", "schedule"])
        self.assertTrue(mock_pick.called)
        self.assertFalse(self.controller.capture_panel.isVisible())

    @patch("src.capture.execute_capture_request")
    def test_cancel_restores_capture_panel(
        self,
        mock_execute: MagicMock,
    ) -> None:
        """
        Ensures cancelling capture brings the Capture panel back.
        """

        def invoke_cancel(**kwargs) -> None:
            kwargs["on_cancel"]()

        mock_execute.side_effect = invoke_cancel
        self.controller.start_capture(
            CaptureRequest(mode=CaptureMode.FULL_SCREEN, delay_seconds=0)
        )
        self.assertTrue(self.controller.capture_panel.isVisible())
        self.assertFalse(self.controller._capture_in_progress)
