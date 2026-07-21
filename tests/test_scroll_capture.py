"""
Unit tests for scroll capture stitching helpers.
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QImage, QMouseEvent, QPainter, QPixmap, QColor

    from tests.qt_test_utils import ensure_qapp

    HAS_PYSIDE6 = True
except ModuleNotFoundError:
    HAS_PYSIDE6 = False


@unittest.skipUnless(HAS_PYSIDE6, "PySide6 is required for scroll capture tests")
class TestScrollCapture(unittest.TestCase):
    """
    Verifies vertical scroll stitching helpers.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures Qt application exists for pixmap operations.
        """

        cls._app = ensure_qapp()

    def test_stitch_vertical_pixmaps_combines_two_frames(self) -> None:
        """
        Ensures two frames are stitched into one taller pixmap.
        """

        from src.scroll_capture import stitch_vertical_pixmaps

        top = QPixmap(40, 30)
        top.fill(QColor(255, 0, 0))
        bottom = QPixmap(40, 30)
        bottom.fill(QColor(0, 0, 255))
        stitched = stitch_vertical_pixmaps([top, bottom])
        self.assertFalse(stitched.isNull())
        self.assertGreaterEqual(stitched.height(), 30)

    def test_find_vertical_overlap_rows_detects_shared_content(self) -> None:
        """
        Ensures overlapping frames report a positive overlap row count.
        """

        from src.scroll_capture import find_vertical_overlap_rows

        shared = QPixmap(60, 20)
        shared.fill(QColor(128, 128, 128))
        top_unique = QPixmap(60, 30)
        top_unique.fill(QColor(255, 0, 0))
        bottom_unique = QPixmap(60, 30)
        bottom_unique.fill(QColor(0, 0, 255))

        top_image = QImage(60, 50, QImage.Format.Format_ARGB32)
        top_painter = QPainter(top_image)
        top_painter.drawPixmap(0, 0, top_unique)
        top_painter.drawPixmap(0, 30, shared)
        top_painter.end()

        bottom_image = QImage(60, 50, QImage.Format.Format_ARGB32)
        bottom_painter = QPainter(bottom_image)
        bottom_painter.drawPixmap(0, 0, shared)
        bottom_painter.drawPixmap(0, 20, bottom_unique)
        bottom_painter.end()

        top = QPixmap.fromImage(top_image)
        bottom = QPixmap.fromImage(bottom_image)
        overlap = find_vertical_overlap_rows(top, bottom)
        self.assertGreater(overlap, 0)

    def test_find_vertical_overlap_from_rows_matches_pixmap_overlap(self) -> None:
        """
        Ensures row-based overlap estimation matches pixmap-based detection.
        """

        from src.scroll_capture import (
            _pixmap_to_gray_rows,
            dedupe_scroll_frames,
            find_vertical_overlap_from_rows,
            find_vertical_overlap_rows,
            measure_vertical_overlap,
            stitch_vertical_pixmaps,
        )

        shared = QPixmap(60, 20)
        shared.fill(QColor(128, 128, 128))
        top_unique = QPixmap(60, 30)
        top_unique.fill(QColor(255, 0, 0))
        bottom_unique = QPixmap(60, 30)
        bottom_unique.fill(QColor(0, 0, 255))

        top_image = QImage(60, 50, QImage.Format.Format_ARGB32)
        top_painter = QPainter(top_image)
        top_painter.drawPixmap(0, 0, top_unique)
        top_painter.drawPixmap(0, 30, shared)
        top_painter.end()

        bottom_image = QImage(60, 50, QImage.Format.Format_ARGB32)
        bottom_painter = QPainter(bottom_image)
        bottom_painter.drawPixmap(0, 0, shared)
        bottom_painter.drawPixmap(0, 20, bottom_unique)
        bottom_painter.end()

        top = QPixmap.fromImage(top_image)
        bottom = QPixmap.fromImage(bottom_image)
        overlap_from_pixmaps = find_vertical_overlap_rows(top, bottom)
        overlap_from_rows = find_vertical_overlap_from_rows(
            _pixmap_to_gray_rows(top),
            _pixmap_to_gray_rows(bottom),
        )
        self.assertEqual(overlap_from_rows, overlap_from_pixmaps)

    def test_stitch_vertical_pixmaps_returns_empty_for_no_frames(self) -> None:
        """
        Ensures empty frame list returns null pixmap.
        """

        from src.scroll_capture import stitch_vertical_pixmaps

        result = stitch_vertical_pixmaps([])
        self.assertTrue(result.isNull())

    def test_pixmap_to_png_bytes_encodes_png(self) -> None:
        """
        Ensures pixmap encoding produces non-empty PNG bytes.
        """

        from src.scroll_capture import pixmap_to_png_bytes

        pixmap = QPixmap(8, 8)
        pixmap.fill(QColor(0, 255, 0))
        png_bytes = pixmap_to_png_bytes(pixmap)
        self.assertTrue(png_bytes.startswith(b"\x89PNG"))

    def _build_scrolled_pair(self, shared_height: int, top_unique: int, bottom_unique: int) -> tuple[QPixmap, QPixmap]:
        """
        Builds two consecutive scroll frames with a known shared overlap region.

        Args:
            shared_height: Shared overlap height.
            top_unique: Unique top content height.
            bottom_unique: Unique bottom content height.

        Returns:
            tuple[QPixmap, QPixmap]: Upper and lower frame.
        """

        shared = QPixmap(80, shared_height)
        shared.fill(QColor(128, 128, 128))
        top_only = QPixmap(80, top_unique)
        top_only.fill(QColor(255, 0, 0))
        bottom_only = QPixmap(80, bottom_unique)
        bottom_only.fill(QColor(0, 0, 255))

        top_image = QImage(80, top_unique + shared_height, QImage.Format.Format_ARGB32)
        top_painter = QPainter(top_image)
        top_painter.drawPixmap(0, 0, top_only)
        top_painter.drawPixmap(0, top_unique, shared)
        top_painter.end()

        bottom_image = QImage(80, shared_height + bottom_unique, QImage.Format.Format_ARGB32)
        bottom_painter = QPainter(bottom_image)
        bottom_painter.drawPixmap(0, 0, shared)
        bottom_painter.drawPixmap(0, shared_height, bottom_only)
        bottom_painter.end()

        return QPixmap.fromImage(top_image), QPixmap.fromImage(bottom_image)

    def _build_scrolled_pair_with_fixed_header(
        self,
        fixed_header_height: int,
        shared_height: int,
        top_unique: int,
        bottom_unique: int,
    ) -> tuple[QPixmap, QPixmap]:
        """
        Builds two scroll frames with identical fixed browser chrome at the top.

        Args:
            fixed_header_height: Height of the non-scrolling title bar region.
            shared_height: Shared overlap height below the fixed header.
            top_unique: Unique top content height below the fixed header.
            bottom_unique: Unique bottom content height below the shared region.

        Returns:
            tuple[QPixmap, QPixmap]: Upper and lower frame.
        """

        chrome = QPixmap(80, fixed_header_height)
        chrome.fill(QColor(40, 40, 40))
        inner_first, inner_second = self._build_scrolled_pair(
            shared_height=shared_height,
            top_unique=top_unique,
            bottom_unique=bottom_unique,
        )
        frame_height = fixed_header_height + max(inner_first.height(), inner_second.height())

        def compose_with_chrome(inner: QPixmap) -> QPixmap:
            image = QImage(80, frame_height, QImage.Format.Format_ARGB32)
            painter = QPainter(image)
            painter.drawPixmap(0, 0, chrome)
            painter.drawPixmap(0, fixed_header_height, inner)
            remaining_height = frame_height - fixed_header_height - inner.height()
            if remaining_height > 0:
                filler = QPixmap(80, remaining_height)
                filler.fill(QColor(128, 128, 128))
                painter.drawPixmap(0, fixed_header_height + inner.height(), filler)
            painter.end()
            return QPixmap.fromImage(image)

        return compose_with_chrome(inner_first), compose_with_chrome(inner_second)

    def test_detect_fixed_header_rows_finds_browser_chrome(self) -> None:
        """
        Ensures identical top rows are detected as fixed browser chrome.
        """

        from src.scroll_capture import _detect_fixed_header_rows

        first, second = self._build_scrolled_pair_with_fixed_header(
            fixed_header_height=60,
            shared_height=20,
            top_unique=30,
            bottom_unique=25,
        )
        fixed_rows = _detect_fixed_header_rows(first, second)
        self.assertGreaterEqual(fixed_rows, 58)
        self.assertLessEqual(fixed_rows, 62)

    def test_stitch_vertical_pixmaps_skips_duplicate_fixed_header(self) -> None:
        """
        Ensures fixed browser chrome is not duplicated in the stitched image.
        """

        from src.scroll_capture import stitch_vertical_pixmaps

        fixed_header_height = 60
        shared_height = 20
        top_unique = 25
        bottom_unique = 25
        first, second = self._build_scrolled_pair_with_fixed_header(
            fixed_header_height=fixed_header_height,
            shared_height=shared_height,
            top_unique=top_unique,
            bottom_unique=bottom_unique,
        )
        stitched = stitch_vertical_pixmaps([first, second])
        expected_height = fixed_header_height + top_unique + shared_height + bottom_unique
        self.assertFalse(stitched.isNull())
        self.assertAlmostEqual(stitched.height(), expected_height, delta=3)

        stitched_image = stitched.toImage()
        header_color = stitched_image.pixelColor(10, 10)
        duplicate_chrome_row = fixed_header_height + top_unique + shared_height
        duplicate_color = stitched_image.pixelColor(10, duplicate_chrome_row)
        self.assertLess(header_color.red(), 80)
        self.assertGreater(duplicate_color.blue(), 100)
        self.assertNotAlmostEqual(duplicate_color.red(), header_color.red(), delta=8)

    def test_refine_stitch_overlap_at_seam_aligns_boundary_row(self) -> None:
        """
        Ensures seam refinement prefers overlap values that align the combined tail.
        """

        from src.scroll_capture import (
            _pixmap_to_gray_rows,
            _refine_stitch_overlap_at_seam,
            stitch_vertical_pixmaps,
        )

        first, second = self._build_scrolled_pair(shared_height=20, top_unique=30, bottom_unique=25)
        combined = stitch_vertical_pixmaps([first])
        bottom_rows = _pixmap_to_gray_rows(second)
        adjusted = _refine_stitch_overlap_at_seam(combined, bottom_rows, 19, second.height())
        self.assertEqual(adjusted, 20)

        exact = _refine_stitch_overlap_at_seam(combined, bottom_rows, 20, second.height())
        self.assertEqual(exact, 20)

    def test_append_vertical_frame_replaces_capture_artifact_seam_row(self) -> None:
        """
        Ensures the stitch seam uses the next frame row instead of a capture artifact tail.
        """

        from src.scroll_capture import _append_vertical_frame

        top = QPixmap(80, 40)
        top.fill(QColor(255, 255, 255))
        bottom = QPixmap(80, 40)
        bottom.fill(QColor(255, 255, 255))
        bottom_image = bottom.toImage()
        for column_index in range(80):
            bottom_image.setPixelColor(column_index, 12, QColor(0, 0, 0))
        bottom = QPixmap.fromImage(bottom_image)

        top_image = top.toImage()
        for column_index in range(80):
            top_image.setPixelColor(column_index, 39, QColor(30, 30, 30))
        top = QPixmap.fromImage(top_image)

        stitched = _append_vertical_frame(top, bottom, overlap=12)
        seam_color = stitched.toImage().pixelColor(10, 38)
        self.assertGreater(seam_color.red(), 200)
        self.assertGreater(stitched.toImage().pixelColor(10, 39).red(), 200)
        self.assertLess(stitched.toImage().pixelColor(10, 40).red(), 20)

    def test_stitch_vertical_pixmaps_uses_pairwise_overlap(self) -> None:
        """
        Ensures stitching consecutive frames produces the expected total height.
        """

        from src.scroll_capture import stitch_vertical_pixmaps

        first, second = self._build_scrolled_pair(shared_height=20, top_unique=30, bottom_unique=25)
        stitched = stitch_vertical_pixmaps([first, second])
        self.assertFalse(stitched.isNull())
        self.assertAlmostEqual(stitched.height(), 75, delta=3)

    def test_stitch_vertical_pixmaps_skips_duplicate_tail_frame(self) -> None:
        """
        Ensures duplicate trailing frames do not inflate stitched height.
        """

        from src.scroll_capture import stitch_vertical_pixmaps

        first, second = self._build_scrolled_pair(shared_height=20, top_unique=30, bottom_unique=25)
        duplicate = QPixmap(second)
        stitched = stitch_vertical_pixmaps([first, second, duplicate, duplicate])
        self.assertAlmostEqual(stitched.height(), 75, delta=3)

    def test_dedupe_scroll_frames_removes_stationary_tail(self) -> None:
        """
        Ensures near-duplicate trailing frames are removed before stitching.
        """

        from src.scroll_capture import dedupe_scroll_frames

        frame = QPixmap(80, 100)
        frame.fill(QColor(120, 120, 120))
        nearly_same = QPixmap(frame.size())
        nearly_same.fill(QColor(120, 120, 120))

        deduped = dedupe_scroll_frames([frame, nearly_same, nearly_same])
        self.assertEqual(len(deduped), 1)

    def test_measure_vertical_overlap_reports_new_content_rows(self) -> None:
        """
        Ensures overlap metrics include newly visible row counts.
        """

        from src.scroll_capture import measure_vertical_overlap

        top, bottom = self._build_scrolled_pair(shared_height=20, top_unique=30, bottom_unique=25)
        match = measure_vertical_overlap(top, bottom)
        self.assertGreater(match.overlap_rows, 0)
        self.assertGreater(match.new_content_rows, 0)
        self.assertLess(match.difference_score, 18.0)

    def test_frame_has_meaningful_new_content_accepts_page_down_overlap(self) -> None:
        """
        Ensures large page-down steps with high overlap still count as progress.
        """

        from src.scroll_capture import frame_has_meaningful_new_content

        frame_height = 260
        shared_height = 249
        top = QPixmap(80, frame_height)
        bottom = QPixmap(80, frame_height)
        top.fill(QColor(30, 30, 30))
        bottom.fill(QColor(30, 30, 30))

        top_image = top.toImage()
        bottom_image = bottom.toImage()
        for row_index in range(shared_height):
            for column_index in range(80):
                gray = 80 + (row_index % 17)
                top_image.setPixelColor(column_index, row_index, QColor(gray, gray, gray))
                bottom_image.setPixelColor(column_index, row_index, QColor(gray, gray, gray))
        for row_index in range(shared_height, frame_height):
            for column_index in range(80):
                top_image.setPixelColor(column_index, row_index, QColor(220, 40, 40))
        for row_index in range(frame_height - shared_height, frame_height):
            for column_index in range(80):
                bottom_image.setPixelColor(column_index, row_index, QColor(40, 40, 220))

        previous_frame = QPixmap.fromImage(top_image)
        current_frame = QPixmap.fromImage(bottom_image)
        self.assertTrue(frame_has_meaningful_new_content(previous_frame, current_frame))
        self.assertFalse(frame_has_meaningful_new_content(current_frame, current_frame))

    def test_is_scroll_position_unchanged_detects_bottom_with_noise(self) -> None:
        """
        Ensures noisy bottom captures still count as the same scroll position.
        """

        from src.scroll_capture import is_scroll_position_unchanged

        frame_height = 900
        shared_height = 894
        previous = QPixmap(120, frame_height)
        current = QPixmap(120, frame_height)
        previous_image = previous.toImage()
        current_image = current.toImage()
        for row_index in range(frame_height):
            for column_index in range(120):
                gray = 70 + ((row_index + column_index) % 23)
                previous_image.setPixelColor(column_index, row_index, QColor(gray, gray, gray))
                current_image.setPixelColor(column_index, row_index, QColor(gray, gray, gray))

        for row_index in range(frame_height - 6, frame_height):
            for column_index in range(120):
                current_image.setPixelColor(
                    column_index,
                    row_index,
                    QColor(140 + (column_index % 7), 140, 140),
                )

        previous_frame = QPixmap.fromImage(previous_image)
        current_frame = QPixmap.fromImage(current_image)
        self.assertTrue(is_scroll_position_unchanged(previous_frame, current_frame))

    def test_is_scroll_position_unchanged_allows_page_down_progress(self) -> None:
        """
        Ensures regular page-down movement is not treated as unchanged.
        """

        from src.scroll_capture import is_scroll_position_unchanged

        previous_frame, current_frame = self._build_scrolled_pair(
            shared_height=240,
            top_unique=20,
            bottom_unique=20,
        )
        self.assertFalse(is_scroll_position_unchanged(previous_frame, current_frame))

    def test_estimate_scroll_progress_rows_uses_lenient_fallback(self) -> None:
        """
        Ensures noisy frames still report realistic scroll progress rows.
        """

        from src.scroll_capture import estimate_scroll_progress_rows

        previous_frame, current_frame = self._build_scrolled_pair(
            shared_height=220,
            top_unique=20,
            bottom_unique=20,
        )
        progress_rows = estimate_scroll_progress_rows(previous_frame, current_frame)
        self.assertGreater(progress_rows, 3)
        self.assertLess(progress_rows, 40)

    def test_frame_has_meaningful_new_content_falls_back_to_lenient_overlap(self) -> None:
        """
        Ensures strict overlap failure does not treat every frame as fully new.
        """

        from src.scroll_capture import frame_has_meaningful_new_content, measure_vertical_overlap

        previous_frame, current_frame = self._build_scrolled_pair(
            shared_height=220,
            top_unique=20,
            bottom_unique=20,
        )
        strict_match = measure_vertical_overlap(previous_frame, current_frame)
        self.assertTrue(frame_has_meaningful_new_content(previous_frame, current_frame))
        self.assertLess(strict_match.new_content_rows, previous_frame.height())
