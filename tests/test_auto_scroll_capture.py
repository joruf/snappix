"""
Unit tests for automatic window scroll capture helpers.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

try:
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QColor, QImage, QPainter, QPixmap

    from src.auto_scroll_capture import (
        ScrollbarInfo,
        detect_vertical_scrollbar,
        frame_has_meaningful_new_content,
        frames_show_same_content,
        perform_auto_scroll_capture,
        _is_scrollbar_at_bottom,
        _is_scrollbar_at_top,
        _should_stop_without_scrollbar,
    )
    from tests.qt_test_utils import ensure_qapp

    HAS_PYSIDE6 = True
except ModuleNotFoundError:
    HAS_PYSIDE6 = False


@dataclass(slots=True)
class _SnapshotStub:
    """
    Provides one desktop snapshot for scroll capture tests.

    Attributes:
        pixmap: Desktop pixmap.
        virtual_geometry: Desktop bounds.
    """

    pixmap: QPixmap
    virtual_geometry: QRect


def _build_scrollable_document(width: int, total_height: int) -> QPixmap:
    """
    Creates one tall synthetic document with visually distinct horizontal bands.

    Args:
        width: Document width.
        total_height: Document height.

    Returns:
        QPixmap: Synthetic scrollable document.
    """

    image = QImage(width, total_height, QImage.Format.Format_ARGB32)
    image.fill(QColor(255, 255, 255, 255))
    painter = QPainter(image)
    band_height = 40
    colors = [
        QColor(231, 76, 60),
        QColor(241, 196, 15),
        QColor(46, 204, 113),
        QColor(52, 152, 219),
        QColor(155, 89, 182),
        QColor(44, 62, 80),
    ]
    y_pos = 0
    color_index = 0
    while y_pos < total_height:
        current_height = min(band_height, total_height - y_pos)
        painter.fillRect(0, y_pos, width, current_height, colors[color_index % len(colors)])
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(12, y_pos + 24, f"Band {color_index + 1}")
        y_pos += current_height
        color_index += 1
    painter.end()
    return QPixmap.fromImage(image)


class _ScrollSnapshotSimulator:
    """
    Simulates desktop captures while one window scrolls through a tall document.
    """

    def __init__(
        self,
        document: QPixmap,
        window_rect: QRect,
        step_rows: int,
    ) -> None:
        self._document = document
        self._window_rect = window_rect
        self._step_rows = step_rows
        self._offset_y = 0
        self._capture_calls = 0
        self._at_bottom = False

    def capture(self) -> _SnapshotStub:
        """
        Returns the next desktop snapshot for the current scroll offset.

        Returns:
            _SnapshotStub: Desktop snapshot stub.
        """

        self._capture_calls += 1
        content_width = max(24, self._window_rect.width() - 18)
        desktop = QPixmap(self._window_rect.width(), self._window_rect.height() + 200)
        desktop.fill(QColor(30, 30, 30))
        painter = QPainter(desktop)
        source_y = self._offset_y
        painter.fillRect(
            content_width,
            self._window_rect.y(),
            self._window_rect.width() - content_width,
            self._window_rect.height(),
            QColor(225, 225, 225),
        )
        painter.drawPixmap(
            0,
            self._window_rect.y(),
            self._document,
            0,
            source_y,
            content_width,
            self._window_rect.height(),
        )
        self._paint_scrollbar(painter)
        painter.end()
        return _SnapshotStub(
            pixmap=desktop,
            virtual_geometry=QRect(0, 0, desktop.width(), desktop.height()),
        )

    def scroll_down(self) -> None:
        """
        Advances the simulated scroll position by one step.

        Returns:
            None
        """

        max_offset = max(0, self._document.height() - self._window_rect.height())
        if self._offset_y >= max_offset:
            self._at_bottom = True
            return
        self._offset_y = min(self._offset_y + self._step_rows, max_offset)
        if self._offset_y >= max_offset:
            self._at_bottom = True

    def _paint_scrollbar(self, painter: QPainter) -> None:
        """
        Draws a scrollbar thumb that reflects the current scroll offset.

        Args:
            painter: Active painter targeting the desktop snapshot.

        Returns:
            None
        """

        viewport_height = self._window_rect.height()
        document_height = self._document.height()
        max_offset = max(0, document_height - viewport_height)
        if max_offset <= 0:
            return

        track_x = self._window_rect.width() - 14
        track_y = self._window_rect.y()
        thumb_height = max(36, int(viewport_height * viewport_height / document_height))
        scroll_ratio = self._offset_y / max_offset
        thumb_top = track_y + int((viewport_height - thumb_height) * scroll_ratio)
        painter.fillRect(track_x, track_y, 12, viewport_height, QColor(225, 225, 225, 255))
        painter.fillRect(track_x + 2, thumb_top, 8, thumb_height, QColor(130, 130, 130, 255))


def _window_with_scrollbar(
    width: int,
    height: int,
    thumb_top: int,
    thumb_height: int,
) -> QPixmap:
    """
    Creates a synthetic window pixmap with one right-side scrollbar.

    Args:
        width: Window width.
        height: Window height.
        thumb_top: Thumb top position.
        thumb_height: Thumb height.

    Returns:
        QPixmap: Synthetic window image.
    """

    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor(245, 245, 245, 255))
    painter = QPainter(image)
    track_x = width - 14
    painter.fillRect(track_x, 0, 14, height, QColor(220, 220, 220, 255))
    painter.fillRect(track_x + 2, thumb_top, 10, thumb_height, QColor(150, 150, 150, 255))
    painter.fillRect(20, 20, width - 40, height - 40, QColor(30, 120, 220, 255))
    painter.end()
    return QPixmap.fromImage(image)


class TestAutoScrollCapture(unittest.TestCase):
    """
    Verifies scrollbar detection and scroll progress helpers.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures Qt application exists for pixmap operations.
        """

        if HAS_PYSIDE6:
            cls._app = ensure_qapp()

    def test_detect_vertical_scrollbar_finds_track_and_thumb(self) -> None:
        """
        Ensures synthetic scrollbar geometry is detected.
        """

        if not HAS_PYSIDE6:
            self.skipTest("PySide6 is required for auto scroll capture tests")

        pixmap = _window_with_scrollbar(320, 480, 120, 80)
        scrollbar = detect_vertical_scrollbar(pixmap)
        self.assertIsNotNone(scrollbar)
        assert scrollbar is not None
        self.assertGreaterEqual(scrollbar.track_rect.width(), 10)
        self.assertIsNotNone(scrollbar.thumb_rect)

    def test_detect_vertical_scrollbar_returns_none_without_track(self) -> None:
        """
        Ensures plain content windows do not report a fake scrollbar.
        """

        if not HAS_PYSIDE6:
            self.skipTest("PySide6 is required for auto scroll capture tests")

        pixmap = QPixmap(320, 480)
        pixmap.fill(QColor(20, 120, 220))
        self.assertIsNone(detect_vertical_scrollbar(pixmap))

    def test_frames_show_same_content_detects_duplicate_frames(self) -> None:
        """
        Ensures duplicate consecutive frames are recognized as scroll end.
        """

        if not HAS_PYSIDE6:
            self.skipTest("PySide6 is required for auto scroll capture tests")

        frame = _window_with_scrollbar(300, 400, 100, 70)
        self.assertTrue(frames_show_same_content(frame, frame))
        self.assertFalse(frame_has_meaningful_new_content(frame, frame))

    def test_scrollbar_info_dataclass(self) -> None:
        """
        Ensures ScrollbarInfo stores track and thumb rectangles.
        """

        if not HAS_PYSIDE6:
            self.skipTest("PySide6 is required for auto scroll capture tests")

        info = ScrollbarInfo(track_rect=QRect(300, 0, 12, 400), thumb_rect=QRect(302, 40, 8, 80))
        self.assertEqual(info.track_rect.height(), 400)
        self.assertEqual(info.thumb_rect.height(), 80)

    def test_is_scrollbar_at_bottom_detects_thumb_at_track_end(self) -> None:
        """
        Ensures bottom-of-track scrollbar thumbs are recognized.
        """

        if not HAS_PYSIDE6:
            self.skipTest("PySide6 is required for auto scroll capture tests")

        info = ScrollbarInfo(
            track_rect=QRect(300, 0, 12, 400),
            thumb_rect=QRect(302, 360, 8, 40),
        )
        self.assertTrue(_is_scrollbar_at_bottom(info))

    def test_is_scrollbar_at_top_detects_thumb_at_track_start(self) -> None:
        """
        Ensures top-of-track scrollbar thumbs are recognized.
        """

        if not HAS_PYSIDE6:
            self.skipTest("PySide6 is required for auto scroll capture tests")

        info = ScrollbarInfo(
            track_rect=QRect(300, 0, 12, 400),
            thumb_rect=QRect(302, 0, 8, 80),
        )
        self.assertTrue(_is_scrollbar_at_top(info))

    def test_should_stop_without_scrollbar_after_stationary_frames(self) -> None:
        """
        Ensures repeated unchanged captures stop the scroll loop.
        """

        if not HAS_PYSIDE6:
            self.skipTest("PySide6 is required for auto scroll capture tests")

        frame = _window_with_scrollbar(300, 400, 100, 70)
        noisy_bottom = QPixmap(frame)
        image = noisy_bottom.toImage()
        for row_index in range(380, 400):
            for column_index in range(0, 280, 11):
                color = image.pixelColor(column_index, row_index)
                image.setPixelColor(
                    column_index,
                    row_index,
                    QColor(
                        min(255, color.red() + 8),
                        color.green(),
                        color.blue(),
                    ),
                )
        noisy_bottom = QPixmap.fromImage(image)

        should_stop, confirmations = _should_stop_without_scrollbar(
            frame,
            noisy_bottom,
            0,
        )
        self.assertFalse(should_stop)
        self.assertEqual(confirmations, 1)

        should_stop, confirmations = _should_stop_without_scrollbar(
            frame,
            noisy_bottom,
            confirmations,
        )
        self.assertTrue(should_stop)
        self.assertGreaterEqual(confirmations, 2)


@unittest.skipUnless(HAS_PYSIDE6, "PySide6 is required for auto scroll capture tests")
class TestAutoScrollCaptureIntegration(unittest.TestCase):
    """
    Verifies end-to-end scroll capture behavior with simulated desktop frames.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures Qt application exists for integration tests.
        """

        cls._app = ensure_qapp()

    @patch("src.auto_scroll_capture.restore_x11_window_focus")
    @patch("src.auto_scroll_capture.get_x11_focused_window_id", return_value="999")
    @patch("src.auto_scroll_capture.time.sleep")
    @patch("src.auto_scroll_capture._xdotool", return_value=True)
    @patch("src.auto_scroll_capture.which", return_value="/usr/bin/xdotool")
    def test_perform_auto_scroll_capture_stitches_full_document(
        self,
        _mock_which: MagicMock,
        mock_xdotool: MagicMock,
        _mock_sleep: MagicMock,
        _mock_focus_get: MagicMock,
        _mock_focus_restore: MagicMock,
    ) -> None:
        """
        Ensures simulated scroll capture merges all frames into one tall image.
        """

        document = _build_scrollable_document(320, 960)
        window_rect = QRect(0, 100, 320, 240)
        simulator = _ScrollSnapshotSimulator(document, window_rect, step_rows=120)

        def fake_scroll_down(_window_id: str, *_args: object) -> None:
            self.assertEqual(_window_id, "12345")
            simulator.scroll_down()

        with patch("src.auto_scroll_capture._scroll_window_down", side_effect=fake_scroll_down):
            result = perform_auto_scroll_capture(
                window_id="12345",
                window_rect=window_rect,
                capture_snapshot=simulator.capture,
            )

        self.assertTrue(result.succeeded, result.message)
        self.assertGreaterEqual(result.frame_count, 3)
        self.assertGreaterEqual(result.pixmap.height(), 900)
        self.assertLessEqual(result.pixmap.height(), 980)

    @patch("src.auto_scroll_capture.restore_x11_window_focus")
    @patch("src.auto_scroll_capture.get_x11_focused_window_id", return_value="999")
    @patch("src.auto_scroll_capture.time.sleep")
    @patch("src.auto_scroll_capture._xdotool", return_value=True)
    @patch("src.auto_scroll_capture.which", return_value="/usr/bin/xdotool")
    def test_perform_auto_scroll_capture_ignores_duplicate_tail_frames(
        self,
        _mock_which: MagicMock,
        _mock_xdotool: MagicMock,
        _mock_sleep: MagicMock,
        _mock_focus_get: MagicMock,
        _mock_focus_restore: MagicMock,
    ) -> None:
        """
        Ensures duplicate trailing frames do not append the last page multiple times.
        """

        document = _build_scrollable_document(280, 720)
        window_rect = QRect(0, 80, 280, 200)
        simulator = _ScrollSnapshotSimulator(document, window_rect, step_rows=100)

        def fake_scroll_down(_window_id: str, *_args: object) -> None:
            self.assertEqual(_window_id, "54321")
            simulator.scroll_down()

        with patch("src.auto_scroll_capture._scroll_window_down", side_effect=fake_scroll_down):
            result = perform_auto_scroll_capture(
                window_id="54321",
                window_rect=window_rect,
                capture_snapshot=simulator.capture,
            )

        self.assertTrue(result.succeeded, result.message)
        self.assertGreaterEqual(result.frame_count, 4)
        self.assertLessEqual(result.frame_count, 8)
        self.assertLessEqual(result.pixmap.height(), 760)
        self.assertGreaterEqual(result.pixmap.height(), 680)

    @patch("src.auto_scroll_capture.restore_x11_window_focus")
    @patch("src.auto_scroll_capture.get_x11_focused_window_id", return_value="999")
    @patch("src.auto_scroll_capture.time.sleep")
    @patch("src.auto_scroll_capture._xdotool", return_value=True)
    @patch("src.auto_scroll_capture.which", return_value="/usr/bin/xdotool")
    def test_perform_auto_scroll_capture_stops_after_short_two_page_document(
        self,
        _mock_which: MagicMock,
        _mock_xdotool: MagicMock,
        _mock_sleep: MagicMock,
        _mock_focus_get: MagicMock,
        _mock_focus_restore: MagicMock,
    ) -> None:
        """
        Ensures short two-page documents stop after a few frames instead of scrolling endlessly.
        """

        document = _build_scrollable_document(320, 480)
        window_rect = QRect(0, 100, 320, 240)
        simulator = _ScrollSnapshotSimulator(document, window_rect, step_rows=200)

        def fake_scroll_down(_window_id: str, *_args: object) -> None:
            simulator.scroll_down()

        with patch("src.auto_scroll_capture._scroll_window_down", side_effect=fake_scroll_down):
            result = perform_auto_scroll_capture(
                window_id="77777",
                window_rect=window_rect,
                capture_snapshot=simulator.capture,
            )

        self.assertTrue(result.succeeded, result.message)
        self.assertTrue(simulator._at_bottom)
        self.assertLessEqual(result.frame_count, 4)
        self.assertGreaterEqual(result.frame_count, 2)
        self.assertGreaterEqual(result.pixmap.height(), 430)
        self.assertLessEqual(result.pixmap.height(), 500)
