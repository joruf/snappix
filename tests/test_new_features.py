"""
Tests for the feature round: capture modes, overlay readouts, document scaling,
sharing as a file, file-name templates, pinning, GIF export, and the German UI.

Everything here is written to pass on Linux and Windows: no shelling out to
platform tools, screens are faked rather than read from the machine, and the
file-name rules are asserted against the Windows constraints because they are
the stricter ones.
"""

from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

try:
    from PySide6.QtCore import QPoint, QRect
    from PySide6.QtGui import QColor, QImage, QPixmap

    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


def _pixmap(width: int, height: int, color: QColor | None = None) -> QPixmap:
    """
    Builds a filled pixmap.

    Args:
        width: Image width.
        height: Image height.
        color: Optional fill color.

    Returns:
        QPixmap: Filled pixmap.
    """

    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(color or QColor(200, 210, 220))
    return QPixmap.fromImage(image)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestCaptureModes(unittest.TestCase):
    """
    Verifies capturing one screen and repeating the last region.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def setUp(self) -> None:
        """
        Clears the stored region between tests.
        """

        import src.capture as capture

        capture._last_capture_region = QRect()

    def test_current_screen_crops_a_multi_monitor_desktop(self) -> None:
        """
        Ensures the reported problem is fixed: on two monitors, capturing the
        current screen returns one screen, not the whole virtual desktop.
        """

        import src.capture as capture
        from src.capture import DesktopSnapshot, crop_snapshot_to_rect

        # 2560x1440 twice, side by side -- the setup the fullscreen capture
        # produced a single 5120x1440 image for.
        desktop = DesktopSnapshot(
            pixmap=_pixmap(5120, 1440),
            virtual_geometry=QRect(0, 0, 5120, 1440),
        )
        right_screen = QRect(2560, 0, 2560, 1440)
        with patch.object(capture, "screen_rect_under_cursor", return_value=right_screen):
            crop = crop_snapshot_to_rect(desktop, capture.screen_rect_under_cursor())

        self.assertEqual((crop.width(), crop.height()), (2560, 1440))

    def test_region_outside_the_desktop_is_refused(self) -> None:
        """
        Ensures a stored region from a disconnected monitor cannot produce a
        bogus capture.
        """

        from src.capture import DesktopSnapshot, crop_snapshot_to_rect

        desktop = DesktopSnapshot(
            pixmap=_pixmap(1920, 1080),
            virtual_geometry=QRect(0, 0, 1920, 1080),
        )
        self.assertTrue(
            crop_snapshot_to_rect(desktop, QRect(4000, 4000, 300, 200)).isNull()
        )

    def test_region_partly_outside_is_clipped(self) -> None:
        """
        Ensures a region reaching past the edge yields the visible part.
        """

        from src.capture import DesktopSnapshot, crop_snapshot_to_rect

        desktop = DesktopSnapshot(
            pixmap=_pixmap(800, 600),
            virtual_geometry=QRect(0, 0, 800, 600),
        )
        crop = crop_snapshot_to_rect(desktop, QRect(700, 500, 400, 400))
        self.assertEqual((crop.width(), crop.height()), (100, 100))

    def test_last_region_is_remembered_and_repeatable(self) -> None:
        """
        Ensures the repeat action has something to repeat after one drag.
        """

        from src.capture import (
            has_last_capture_region,
            last_capture_region,
            remember_capture_region,
        )

        self.assertFalse(has_last_capture_region())
        remember_capture_region(QRect(120, 80, 640, 480))
        self.assertTrue(has_last_capture_region())
        self.assertEqual(last_capture_region(), QRect(120, 80, 640, 480))

    def test_empty_region_is_not_remembered(self) -> None:
        """
        Ensures a click without a drag does not arm the repeat action.
        """

        from src.capture import has_last_capture_region, remember_capture_region

        remember_capture_region(QRect(10, 10, 0, 0))
        self.assertFalse(has_last_capture_region())

    def test_offset_virtual_desktop_maps_coordinates(self) -> None:
        """
        Ensures a desktop whose origin is not (0,0) -- a monitor placed left of
        the primary one -- still crops the right pixels.
        """

        from src.capture import DesktopSnapshot, crop_snapshot_to_rect

        desktop = DesktopSnapshot(
            pixmap=_pixmap(3000, 1000),
            virtual_geometry=QRect(-1000, 0, 3000, 1000),
        )
        crop = crop_snapshot_to_rect(desktop, QRect(-1000, 0, 1000, 1000))
        self.assertEqual((crop.width(), crop.height()), (1000, 1000))


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestCapturePanelLayout(unittest.TestCase):
    """
    Verifies every capture button stays managed by the wrapping flow layout.

    Adding a button to the panel but not to ``_refresh_capture_button_flow``
    leaves it a child of the frame that the flow layout never positions: it
    keeps its previous geometry and is drawn on top of a neighbour or outside
    the panel. That is exactly what happened when the two new capture modes were
    added, and it is invisible to any test that only checks the buttons exist.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def _panel(self):
        """
        Builds a capture panel with its flow rebuilt.

        Returns:
            CapturePanel: Panel under test.
        """

        from src.capture import CapturePanel

        panel = CapturePanel()
        self.addCleanup(panel.close)
        panel.show()
        self._app.processEvents()
        panel._apply_initial_window_geometry()
        panel._refresh_capture_button_flow()
        self._app.processEvents()
        return panel

    def _resize(self, panel, width: int) -> None:
        """
        Resizes the panel and lets it settle.

        The panel pins its height inside the resize event, so no extra flush is
        needed -- that is exactly the behaviour under test.

        Args:
            panel: Panel under test.
            width: New window width.

        Returns:
            None
        """

        panel.resize(width, panel.height())
        self._app.processEvents()

    def test_every_visible_button_is_in_the_flow_layout(self) -> None:
        """
        Ensures no capture button is left unmanaged.
        """

        from PySide6.QtWidgets import QPushButton

        panel = self._panel()
        frame = panel.capture_fullscreen_button.parent()
        managed = {
            id(item.widget())
            for item in frame._flow_layout._items
            if item.widget() is not None
        }
        unmanaged = [
            button.text() or "icon"
            for button in frame.findChildren(QPushButton)
            if not button.isHidden() and id(button) not in managed
        ]
        self.assertEqual(unmanaged, [], "buttons missing from the flow layout")

    def test_new_capture_buttons_are_flow_candidates(self) -> None:
        """
        Ensures the two new modes are part of the rebuilt candidate list, not
        only of the initial construction list.
        """

        panel = self._panel()
        frame = panel.capture_fullscreen_button.parent()
        managed = {
            id(item.widget())
            for item in frame._flow_layout._items
            if item.widget() is not None
        }
        self.assertIn(id(panel.capture_screen_button), managed)
        self.assertIn(id(panel.capture_last_region_button), managed)

    def test_no_button_is_painted_outside_the_panel(self) -> None:
        """
        Ensures the panel grows to fit the buttons instead of clipping them.
        """

        from PySide6.QtWidgets import QPushButton

        panel = self._panel()
        frame = panel.capture_fullscreen_button.parent()
        overflowing = [
            f"{button.text() or 'icon'} bottom={button.geometry().bottom()}"
            for button in frame.findChildren(QPushButton)
            if not button.isHidden() and button.geometry().bottom() > frame.height()
        ]
        self.assertEqual(overflowing, [], "buttons reach past the panel edge")

    def test_width_change_keeps_the_smallest_possible_height(self) -> None:
        """
        Ensures widening or narrowing the panel leaves no empty band below the
        buttons: the flow rewraps and the window follows the new row count.
        """

        panel = self._panel()
        for width in (360, 420, 620, 1000):
            self._resize(panel, width)
            self.assertEqual(
                panel.height(),
                panel.minimumSizeHint().height(),
                f"height does not match the minimum at width {width}",
            )

    def test_panel_cannot_be_narrowed_below_its_startup_width(self) -> None:
        """
        Ensures the window cannot be squeezed into a sliver.

        Without a floor the flow layout stacks every button in its own row and
        the panel shoots up to nearly screen height -- narrowing the window made
        it taller and taller.
        """

        from src.capture import CAPTURE_PANEL_START_WIDTH

        panel = self._panel()
        self.assertGreaterEqual(panel.minimumWidth(), CAPTURE_PANEL_START_WIDTH)

        for width in (300, 200, 120):
            self._resize(panel, width)
            self.assertGreaterEqual(panel.width(), CAPTURE_PANEL_START_WIDTH)

    def test_narrowing_never_makes_the_panel_taller(self) -> None:
        """
        Ensures dragging the edge inward does not add button rows.
        """

        panel = self._panel()
        start_height = panel.height()

        for width in (400, 300, 150):
            self._resize(panel, width)
            self.assertLessEqual(
                panel.height(),
                start_height,
                f"panel grew taller when narrowed to {width}",
            )

    def test_height_stays_bounded_across_every_width(self) -> None:
        """
        Ensures no width turns the panel into a tall column of buttons.

        A row holding a 32 px icon button next to 25 px text buttons is 7 px
        taller, so the height varies slightly with the wrap; what must not
        happen is the panel growing by whole rows.
        """

        panel = self._panel()
        start_height = panel.height()

        heights = []
        for width in range(420, 1300, 40):
            self._resize(panel, width)
            heights.append(panel.height())

        self.assertLessEqual(
            max(heights),
            start_height + 10,
            f"panel height grew to {max(heights)} from {start_height}",
        )

    def test_height_is_pinned_while_the_width_changes(self) -> None:
        """
        Ensures the height is set during the drag, not once it ends.

        Publishing a size constraint lets the window manager clamp the height
        itself while it still owns the interactive resize; requesting a new
        geometry instead made every request the WM's new base and the window
        grew hundreds of pixels taller than its content.
        """

        panel = self._panel()

        for width in range(430, 700, 30):
            panel.resize(width, panel.height())
            self._app.processEvents()
            expected = panel.content_height()
            self.assertEqual(
                panel.minimumHeight(),
                expected,
                f"minimum height not applied at width {width}",
            )
            self.assertEqual(panel.height(), expected)

    def test_height_cannot_be_stretched_by_the_window_manager(self) -> None:
        """
        Ensures the panel keeps the smallest height its content allows.

        Its height follows entirely from how the buttons wrap, so there is
        nothing to drag vertically and a taller window is always empty space.
        """

        panel = self._panel()
        expected = panel.content_height()
        self.assertEqual(panel.minimumHeight(), expected)
        self.assertEqual(panel.maximumHeight(), expected)

        panel.resize(panel.width(), 600)
        self._app.processEvents()
        self.assertEqual(panel.height(), expected)

    def test_delay_row_does_not_absorb_vertical_space(self) -> None:
        """
        Ensures the frame holding the delay slider keeps its own height.

        With the default Preferred policy it soaked up whatever vertical slack
        the window had, so the panel stayed tall after the buttons below it had
        already rewrapped into fewer rows.
        """

        from PySide6.QtWidgets import QSizePolicy

        panel = self._panel()
        delay_frame = panel.delay_slider.parent()

        self.assertEqual(
            delay_frame.sizePolicy().verticalPolicy(),
            QSizePolicy.Policy.Maximum,
        )

        heights = []
        for width in (420, 600, 900, 1200):
            self._resize(panel, width)
            heights.append(delay_frame.height())
        self.assertEqual(
            len(set(heights)), 1, f"delay row height varied: {heights}"
        )

    def test_height_never_falls_back_to_the_constant_size_hint(self) -> None:
        """
        Ensures the panel cannot jump to full height while its edge is dragged.

        ``sizeHint()`` ignores height-for-width and reports one tall value for
        every width. Using it as a fallback stretched the panel whenever the
        layout reported no height-for-width mid-resize, which is what happened
        during an interactive drag.
        """

        panel = self._panel()
        panel.resize(620, 400)
        self._app.processEvents()
        panel._height_settle_timer.stop()

        with patch.object(
            type(panel.layout()), "hasHeightForWidth", return_value=False
        ):
            panel.shrink_height_to_content()
        self._app.processEvents()

        self.assertEqual(panel.height(), panel.minimumSizeHint().height())
        self.assertLess(panel.height(), panel.sizeHint().height())

    def test_buttons_do_not_overlap(self) -> None:
        """
        Ensures no two buttons share pixels, which is how the unmanaged button
        showed up: half-hidden behind its neighbour.
        """

        from PySide6.QtWidgets import QPushButton

        panel = self._panel()
        frame = panel.capture_fullscreen_button.parent()
        buttons = [
            button
            for button in frame.findChildren(QPushButton)
            if not button.isHidden()
        ]
        collisions = []
        for index, first in enumerate(buttons):
            for second in buttons[index + 1 :]:
                if first.geometry().intersects(second.geometry()):
                    collisions.append(
                        f"{first.text() or 'icon'} / {second.text() or 'icon'}"
                    )
        self.assertEqual(collisions, [], "overlapping capture buttons")


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestRegionOverlayReadouts(unittest.TestCase):
    """
    Verifies the size readout and magnifier drawn while picking a region.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def _overlay(self):
        """
        Builds a region overlay over an 800x600 desktop.

        Returns:
            RegionCaptureOverlay: Overlay under test.
        """

        from src.capture import RegionCaptureOverlay

        overlay = RegionCaptureOverlay(_pixmap(800, 600), QRect(0, 0, 800, 600))
        overlay.resize(800, 600)
        self.addCleanup(overlay.close)
        return overlay

    def test_size_readout_shows_the_selection_size(self) -> None:
        """
        Ensures the drag shows how many pixels are being captured.
        """

        overlay = self._overlay()
        overlay._start_point = QPoint(100, 100)
        overlay._current_point = QPoint(400, 300)
        overlay._cursor_point = QPoint(400, 300)
        overlay._dragging = True
        image = overlay.grab().toImage()

        # The readout box is dark; nothing else below the selection is.
        dark = sum(
            1
            for y in range(306, 340)
            for x in range(100, 320)
            if image.pixelColor(x, y).red() < 60
        )
        self.assertGreater(dark, 200, "no size readout painted below the selection")

    def test_magnifier_is_drawn_next_to_the_cursor(self) -> None:
        """
        Ensures the loupe appears, which is what makes pixel-exact edges pickable.
        """

        from src.capture import MAGNIFIER_GAP, MAGNIFIER_SIZE

        overlay = self._overlay()
        overlay._cursor_point = QPoint(300, 200)
        image = overlay.grab().toImage()

        loupe = QRect(
            300 + MAGNIFIER_GAP,
            200 + MAGNIFIER_GAP,
            MAGNIFIER_SIZE,
            MAGNIFIER_SIZE,
        )
        crosshair = sum(
            1
            for y in range(loupe.top(), loupe.bottom())
            for x in range(loupe.left(), loupe.right())
            if image.pixelColor(x, y).red() > 180 and image.pixelColor(x, y).green() < 110
        )
        self.assertGreater(crosshair, 50, "no magnifier crosshair painted")

    def test_magnifier_near_the_edge_does_not_crash(self) -> None:
        """
        Ensures the loupe flips instead of drawing past the screen edge.
        """

        overlay = self._overlay()
        for point in (QPoint(795, 595), QPoint(2, 2), QPoint(799, 0)):
            overlay._cursor_point = point
            self.assertFalse(overlay.grab().toImage().isNull())


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestDocumentScaling(unittest.TestCase):
    """
    Verifies resizing the document moves image and annotations together.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def _canvas(self):
        """
        Builds a canvas with three annotation kinds on an 800x600 document.

        Returns:
            EditorCanvas: Canvas under test.
        """

        from src.editor_canvas import EditorCanvas
        from src.models import AnnotationModel

        canvas = EditorCanvas()
        canvas.set_screenshot(_pixmap(800, 600))
        canvas.load_annotations(
            [
                AnnotationModel(
                    annotation_type="rect",
                    x=100.0, y=100.0, width=200.0, height=150.0,
                    stroke_rgba=[255, 0, 0, 255], fill_rgba=[255, 0, 0, 60],
                    stroke_width=4.0,
                ),
                AnnotationModel(
                    annotation_type="text",
                    x=50.0, y=400.0, width=200.0, height=40.0, text="Hallo",
                    stroke_rgba=[0, 0, 0, 255], fill_rgba=[255, 255, 255, 200],
                    stroke_width=2.0, font_size=20,
                ),
                AnnotationModel(
                    annotation_type="polyline",
                    x=0.0, y=0.0, width=100.0, height=50.0,
                    stroke_rgba=[0, 0, 255, 255], fill_rgba=[0, 0, 255, 0],
                    stroke_width=3.0,
                    payload={"points": [[10.0, 10.0], [60.0, 40.0], [120.0, 20.0]]},
                ),
            ]
        )
        return canvas

    def test_document_reaches_exactly_the_requested_size(self) -> None:
        """
        Ensures the auto-fit does not grow the document past the size asked for
        when an annotation's halo reaches over the edge.
        """

        canvas = self._canvas()
        self.assertTrue(canvas.scale_document(400, 300))
        self.assertEqual(
            (canvas.screenshot().width(), canvas.screenshot().height()), (400, 300)
        )

    def test_annotations_scale_with_the_image(self) -> None:
        """
        Ensures geometry, stroke width, and font size follow the new size, so
        the result looks like the original at another resolution.
        """

        canvas = self._canvas()
        before = {a.annotation_type: a for a in canvas.collect_annotations()}
        canvas.scale_document(400, 300)
        after = {a.annotation_type: a for a in canvas.collect_annotations()}

        self.assertAlmostEqual(after["rect"].x, before["rect"].x / 2, delta=1.0)
        self.assertAlmostEqual(after["rect"].width, before["rect"].width / 2, delta=1.0)
        self.assertAlmostEqual(
            after["rect"].stroke_width, before["rect"].stroke_width / 2, delta=0.6
        )
        self.assertLess(after["text"].font_size, before["text"].font_size)
        self.assertEqual(len(after["polyline"].payload["points"]), 3)

    def test_same_size_is_a_no_op(self) -> None:
        """
        Ensures confirming the dialog without a change does not touch history.
        """

        canvas = self._canvas()
        self.assertFalse(canvas.scale_document(800, 600))

    def test_scaling_up_and_back_keeps_the_annotation_count(self) -> None:
        """
        Ensures a round trip loses nothing.
        """

        canvas = self._canvas()
        canvas.scale_document(1600, 1200)
        canvas.scale_document(800, 600)
        self.assertEqual(len(canvas.collect_annotations()), 3)


class TestDocumentScaleMath(unittest.TestCase):
    """
    Verifies the size arithmetic without touching Qt widgets.
    """

    def test_aspect_ratio_follows_the_given_side(self) -> None:
        """
        Ensures the untouched side is derived from the ratio.
        """

        from src.document_scale import scaled_size

        self.assertEqual(scaled_size(1600, 900, target_width=800), (800, 450))
        self.assertEqual(scaled_size(1600, 900, target_height=450), (800, 450))

    def test_free_ratio_keeps_both_sides(self) -> None:
        """
        Ensures unlocking the ratio allows a non-uniform size.
        """

        from src.document_scale import scaled_size

        self.assertEqual(
            scaled_size(1600, 900, target_width=400, target_height=400, keep_aspect=False),
            (400, 400),
        )

    def test_sizes_are_clamped(self) -> None:
        """
        Ensures a stray value cannot request a gigapixel document.
        """

        from src.document_scale import MAX_DOCUMENT_SIZE, clamp_document_size

        self.assertEqual(clamp_document_size(0), 1)
        self.assertEqual(clamp_document_size(10**9), MAX_DOCUMENT_SIZE)
        self.assertEqual(clamp_document_size("nonsense"), 1)


class TestFilenameTemplate(unittest.TestCase):
    """
    Verifies capture file naming, including the Windows rules.
    """

    def test_placeholders_are_filled(self) -> None:
        """
        Ensures every documented placeholder resolves.
        """

        from src.post_capture_service import format_capture_filename

        name = format_capture_filename(
            "{year}-{month}-{day}_{time}_{counter}",
            datetime(2026, 3, 5, 14, 7, 9),
            counter=3,
        )
        self.assertEqual(name, "2026-03-05_14-07-09_3.png")

    def test_default_template_matches_the_previous_naming(self) -> None:
        """
        Ensures existing users keep the file names they already have.
        """

        from src.post_capture_service import build_capture_filename

        self.assertEqual(
            build_capture_filename(datetime(2026, 3, 5, 14, 7, 9)),
            "snappix_2026-03-05_14-07-09.png",
        )

    def test_windows_forbidden_characters_are_replaced(self) -> None:
        """
        Ensures a template with path or reserved characters cannot produce a
        file name Windows refuses -- the same folder is often synced between
        both systems.
        """

        from src.post_capture_service import format_capture_filename

        name = format_capture_filename('a<b>c:d"e/f\\g|h?i*j')
        self.assertNotIn("/", name[:-4])
        self.assertNotIn("\\", name)
        for character in '<>:"|?*':
            self.assertNotIn(character, name)

    def test_reserved_windows_names_are_escaped(self) -> None:
        """
        Ensures device names cannot become the file name.
        """

        from src.post_capture_service import sanitize_filename_stem

        self.assertEqual(sanitize_filename_stem("CON"), "CON_")
        self.assertEqual(sanitize_filename_stem("com1"), "com1_")

    def test_trailing_dots_and_spaces_are_trimmed(self) -> None:
        """
        Ensures Windows silently dropping them cannot desync the name.
        """

        from src.post_capture_service import sanitize_filename_stem

        self.assertEqual(sanitize_filename_stem("report. . "), "report")

    def test_empty_template_falls_back(self) -> None:
        """
        Ensures a cleared field cannot produce a nameless file.
        """

        from src.post_capture_service import format_capture_filename

        self.assertTrue(format_capture_filename("   ").endswith(".png"))
        self.assertGreater(len(format_capture_filename("   ")), 4)

    def test_existing_names_get_a_counter(self) -> None:
        """
        Ensures two captures in the same second do not overwrite each other.
        """

        from src.post_capture_service import resolve_unique_path

        with TemporaryDirectory() as directory:
            folder = Path(directory)
            stamp = datetime(2026, 3, 5, 14, 7, 9)
            first = resolve_unique_path(folder, "shot", stamp)
            first.write_bytes(b"x")
            second = resolve_unique_path(folder, "shot", stamp)
            self.assertNotEqual(first, second)
            self.assertFalse(second.exists())


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestShareAsFile(unittest.TestCase):
    """
    Verifies the image can leave Snappix as a file.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def tearDown(self) -> None:
        """
        Removes the session share directory.
        """

        from src.drag_export import cleanup_session_export_dir

        cleanup_session_export_dir()

    def test_clipboard_payload_carries_a_real_png_file(self) -> None:
        """
        Ensures pasting into a file manager or a mail attachment works, which
        needs text/uri-list rather than image data.
        """

        from PySide6.QtCore import QMimeData

        from src.drag_export import attach_image_file

        mime = QMimeData()
        path = attach_image_file(mime, _pixmap(40, 30), "beispiel")

        self.assertIsNotNone(path)
        self.assertTrue(mime.hasUrls())
        self.assertTrue(path.exists())
        self.assertEqual(path.read_bytes()[:4], b"\x89PNG")
        self.assertEqual(Path(mime.urls()[0].toLocalFile()), path)

    def test_file_names_are_made_safe(self) -> None:
        """
        Ensures a tab title with path characters cannot escape the directory.
        """

        from src.drag_export import write_shareable_png

        path = write_shareable_png(_pixmap(10, 10), "../../etc/passwd")
        self.assertIsNotNone(path)
        self.assertNotIn("..", path.name)
        self.assertTrue(path.name.endswith(".png"))

    def test_repeated_names_do_not_overwrite(self) -> None:
        """
        Ensures dragging twice offers two files, since the first drop may still
        be reading the earlier one.
        """

        from src.drag_export import write_shareable_png

        first = write_shareable_png(_pixmap(10, 10), "same")
        second = write_shareable_png(_pixmap(10, 10), "same")
        self.assertNotEqual(first, second)
        self.assertTrue(first.exists() and second.exists())

    def test_null_image_is_refused(self) -> None:
        """
        Ensures an empty tab produces no file and no drag.
        """

        from src.drag_export import write_shareable_png

        self.assertIsNone(write_shareable_png(QPixmap(), "leer"))

    def test_cleanup_removes_the_session_directory(self) -> None:
        """
        Ensures shared files do not pile up in the temp folder forever.
        """

        from src.drag_export import (
            cleanup_session_export_dir,
            session_export_dir,
            write_shareable_png,
        )

        path = write_shareable_png(_pixmap(10, 10), "temporaer")
        directory = session_export_dir()
        cleanup_session_export_dir()
        self.assertFalse(path.exists())
        self.assertFalse(directory.exists())


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestPinWindow(unittest.TestCase):
    """
    Verifies the floating reference window.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def _pin(self):
        """
        Builds a pin window.

        Returns:
            PinWindow: Window under test.
        """

        from src.pin_window import PinWindow

        window = PinWindow(_pixmap(240, 160))
        self.addCleanup(window.close)
        return window

    def test_window_stays_on_top_and_has_no_frame(self) -> None:
        """
        Ensures it behaves as a reference overlay, not a second editor window.
        """

        from PySide6.QtCore import Qt

        window = self._pin()
        flags = window.windowFlags()
        self.assertTrue(flags & Qt.WindowType.WindowStaysOnTopHint)
        self.assertTrue(flags & Qt.WindowType.FramelessWindowHint)

    def test_size_follows_the_image(self) -> None:
        """
        Ensures the window is exactly as large as the pinned image.
        """

        window = self._pin()
        self.assertEqual((window.width(), window.height()), (240, 160))

    def test_zoom_is_clamped_both_ways(self) -> None:
        """
        Ensures the window can neither vanish nor swallow the screen.
        """

        from src.pin_window import MAX_PIN_ZOOM, MIN_PIN_ZOOM

        window = self._pin()
        window.set_zoom(1000.0)
        self.assertEqual(window.zoom(), MAX_PIN_ZOOM)
        window.set_zoom(0.0)
        self.assertEqual(window.zoom(), MIN_PIN_ZOOM)

    def test_zoom_resizes_the_window(self) -> None:
        """
        Ensures zooming actually changes the visible size.
        """

        window = self._pin()
        window.set_zoom(2.0)
        self.assertEqual((window.width(), window.height()), (480, 320))

    def test_editor_keeps_a_reference_until_it_closes(self) -> None:
        """
        Ensures the pin does not disappear immediately: a parentless tool window
        is garbage-collected as soon as the creating method returns.
        """

        from src.editor_window import EditorWindow

        editor = EditorWindow(_pixmap(120, 90))
        self.addCleanup(editor.close)
        window = editor.pin_to_screen()

        self.assertIsNotNone(window)
        self.assertEqual(len(editor._pinned_windows), 1)
        window.close()
        self._app.processEvents()
        self.assertEqual(len(editor._pinned_windows), 0)


class TestGifExportCommand(unittest.TestCase):
    """
    Verifies the GIF export command line.
    """

    def test_palette_is_generated_from_the_clip(self) -> None:
        """
        Ensures the 256-color limit is handled with a generated palette; the
        default web palette bands screen recordings badly.
        """

        from src.video_recorder import build_gif_export_command

        command = build_gif_export_command(Path("in.mp4"), [], Path("out.gif"))
        joined = " ".join(command)
        self.assertIn("palettegen", joined)
        self.assertIn("paletteuse", joined)

    def test_gif_loops_and_has_no_audio(self) -> None:
        """
        Ensures the output is a looping, silent GIF.
        """

        from src.video_recorder import build_gif_export_command

        command = build_gif_export_command(Path("in.mp4"), [], Path("out.gif"))
        self.assertIn("-loop", command)
        self.assertEqual(command[command.index("-loop") + 1], "0")
        self.assertIn("-an", command)

    def test_width_is_capped_but_never_enlarged(self) -> None:
        """
        Ensures a small recording is not upscaled, which would only inflate the
        file without adding detail.
        """

        from src.video_recorder import DEFAULT_GIF_WIDTH, build_gif_export_command

        command = build_gif_export_command(Path("in.mp4"), [], Path("out.gif"))
        self.assertIn(f"min({DEFAULT_GIF_WIDTH},iw)", " ".join(command))

    def test_overlays_are_composited_before_the_palette(self) -> None:
        """
        Ensures annotations are burned in, and that the palette is computed from
        the annotated frames rather than the raw ones.
        """

        from src.video_recorder import OverlaySegment, build_gif_export_command

        command = build_gif_export_command(
            Path("in.mp4"),
            [OverlaySegment(png_path=Path("a.png"), start_s=0.5, end_s=2.0)],
            Path("out.gif"),
        )
        joined = " ".join(command)
        self.assertIn("overlay=enable='between(t,0.5,2.0)'", joined)
        self.assertLess(joined.index("overlay=enable"), joined.index("palettegen"))


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestGermanInterface(unittest.TestCase):
    """
    Verifies the interface language switch.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def tearDown(self) -> None:
        """
        Returns the interface to English.
        """

        from src.i18n import set_language

        set_language("en")

    def test_known_strings_translate(self) -> None:
        """
        Ensures the dictionary is wired up.
        """

        from src.i18n import set_language, translate

        set_language("de")
        self.assertEqual(translate("Capture Fullscreen"), "Vollbild aufnehmen")
        self.assertEqual(translate("Flatten Annotations"), "Anmerkungen einbrennen")

    def test_unknown_strings_are_left_alone(self) -> None:
        """
        Ensures user content and computed text pass through untouched -- the
        whole reason only exact matches are replaced.
        """

        from src.i18n import set_language, translate

        set_language("de")
        for text in ("Screenshot 2026-03-05.png", "Mein Projekt", "1920 x 1080 px"):
            self.assertEqual(translate(text), text)

    def test_english_leaves_everything_untouched(self) -> None:
        """
        Ensures switching back is complete.
        """

        from src.i18n import set_language, translate

        set_language("en")
        self.assertEqual(translate("Capture Fullscreen"), "Capture Fullscreen")

    def test_system_language_resolves_to_a_concrete_language(self) -> None:
        """
        Ensures the default follows the operating system.
        """

        from src.i18n import LANGUAGE_GERMAN, resolve_language

        with patch("src.i18n.system_language_is_german", return_value=True):
            self.assertEqual(resolve_language("system"), LANGUAGE_GERMAN)

    def test_invalid_language_falls_back(self) -> None:
        """
        Ensures a hand-edited config cannot break startup.
        """

        from src.i18n import DEFAULT_LANGUAGE, normalize_language

        self.assertEqual(normalize_language("klingon"), DEFAULT_LANGUAGE)

    def test_menus_and_tabs_translate(self) -> None:
        """
        Ensures the retrofit reaches menus and tab titles, which is the visible
        surface users judge the language by.
        """

        from src.editor_window import EditorWindow
        from src.i18n import set_language
        from src.i18n_widgets import translate_widget_tree

        set_language("de")
        editor = EditorWindow(_pixmap(120, 90))
        self.addCleanup(editor.close)
        translate_widget_tree(editor)

        titles = [
            action.menu().title()
            for action in editor.menuBar().actions()
            if action.menu() is not None
        ]
        self.assertEqual(titles, ["Datei", "Bearbeiten", "Ansicht", "Hilfe"])


class TestConfigRoundTrip(unittest.TestCase):
    """
    Verifies the new settings survive save and load.
    """

    def test_new_settings_persist(self) -> None:
        """
        Ensures language, file-name template, and the new hotkeys are stored.
        """

        from src.config import AppConfig, ConfigManager

        with TemporaryDirectory() as directory:
            manager = ConfigManager(Path(directory) / "config.json")
            manager.save(
                AppConfig(
                    language="de",
                    capture_filename_template="ticket_{date}_{counter}",
                    hotkey_capture_screen="ctrl+alt+s",
                    hotkey_capture_last_region="ctrl+alt+d",
                )
            )
            loaded = manager.load()

        self.assertEqual(loaded.language, "de")
        self.assertEqual(loaded.capture_filename_template, "ticket_{date}_{counter}")
        self.assertEqual(loaded.hotkey_capture_screen, "ctrl+alt+s")
        self.assertEqual(loaded.hotkey_capture_last_region, "ctrl+alt+d")

    def test_old_config_without_new_keys_still_loads(self) -> None:
        """
        Ensures an existing installation keeps working after the update.
        """

        import json

        from src.config import ConfigManager
        from src.i18n import DEFAULT_LANGUAGE
        from src.post_capture_service import DEFAULT_FILENAME_TEMPLATE

        with TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"theme": "dark", "hotkeys_enabled": True}))
            loaded = ConfigManager(path).load()

        self.assertEqual(loaded.language, DEFAULT_LANGUAGE)
        self.assertEqual(loaded.capture_filename_template, DEFAULT_FILENAME_TEMPLATE)


if __name__ == "__main__":
    unittest.main()
