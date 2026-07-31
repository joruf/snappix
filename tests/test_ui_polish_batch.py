"""
Tests for the capture/editor UI polish pass: panel chrome, flow-layout spacing,
tool selection styling, and the degree-based corner radius control.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from PySide6.QtCore import QSize, Qt
    from PySide6.QtWidgets import QAbstractButton, QLabel, QWidget

    from src.annotation_items import (
        MAX_CORNER_RADIUS_DEGREES,
        clamp_corner_radius_degrees,
    )
    from src.capture import CapturePanel
    from src.editor_canvas import Tool
    from src.flow_layout import FlowLayoutWidget
    from src.theme import THEME_DARK, build_editor_accent_stylesheet
    from src.video_editor_window import VideoEditorWindow
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for UI tests")
class TestCapturePanelChrome(unittest.TestCase):
    """
    Verifies the capture panel drops its redundant title and stays compact.
    """

    @classmethod
    def setUpClass(cls) -> None:
        ensure_qapp()

    def test_panel_has_no_redundant_title_label(self) -> None:
        """
        Ensures the window title bar is the only place naming the app.
        """

        panel = CapturePanel()
        titles = [
            label
            for label in panel.findChildren(QLabel)
            if label.objectName() == "titleLabel"
        ]

        self.assertEqual(titles, [])

    def test_every_button_has_a_tooltip(self) -> None:
        """
        Ensures no capture action ships without an explanation.
        """

        panel = CapturePanel()
        missing = [
            button.text() or type(button).__name__
            for button in panel.findChildren(QAbstractButton)
            if not button.toolTip().strip()
        ]

        self.assertEqual(missing, [])

    def test_widening_collapses_the_height(self) -> None:
        """
        Ensures a wider panel gives its now-unneeded rows back.

        The action buttons flow-wrap, so a wider panel needs fewer rows and must
        not keep the taller geometry as an empty band.
        """

        from PySide6.QtWidgets import QApplication

        panel = CapturePanel()
        panel.show()
        QApplication.processEvents()

        panel.resize(360, 600)
        QApplication.processEvents()
        panel.shrink_height_to_content()
        narrow_height = panel.height()

        panel.resize(1400, panel.height())
        QApplication.processEvents()
        panel.shrink_height_to_content()
        wide_height = panel.height()
        panel.hide()

        self.assertLess(wide_height, narrow_height)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for UI tests")
class TestFlowLayoutSkipsHiddenWidgets(unittest.TestCase):
    """
    Verifies hidden widgets stop reserving space in the flow layout.

    The Edit panel hides the color groups that do not apply to the selection.
    While hidden widgets still counted, they left a wide blank band between the
    visible groups -- the gap between Fill and Thickness.
    """

    @classmethod
    def setUpClass(cls) -> None:
        ensure_qapp()

    def _sized_child(self, parent: QWidget, width: int) -> QWidget:
        child = QWidget(parent)
        child.setFixedSize(QSize(width, 20))
        return child

    def test_hidden_widget_does_not_occupy_a_slot(self) -> None:
        """
        Ensures a hidden widget leaves no gap between its neighbours.
        """

        container = FlowLayoutWidget(None, horizontal_spacing=4, vertical_spacing=2, margin=0)
        container.resize(1000, 60)
        first = self._sized_child(container, 100)
        hidden = self._sized_child(container, 300)
        last = self._sized_child(container, 100)
        hidden.hide()
        container.set_flow_widgets([first, hidden, last])
        container.update_flow_geometry()

        # last should sit right after first, not 300px further along.
        self.assertEqual(last.x(), first.x() + first.width() + 4)

    def test_visible_widget_still_occupies_its_slot(self) -> None:
        """
        Ensures the skip applies only to explicitly hidden widgets.
        """

        container = FlowLayoutWidget(None, horizontal_spacing=4, vertical_spacing=2, margin=0)
        container.resize(1000, 60)
        first = self._sized_child(container, 100)
        middle = self._sized_child(container, 300)
        last = self._sized_child(container, 100)
        container.set_flow_widgets([first, middle, last])
        container.update_flow_geometry()

        self.assertGreater(last.x(), first.x() + first.width() + 300)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for UI tests")
class TestSelectedToolStyling(unittest.TestCase):
    """
    Verifies a selected tool is outlined rather than filled with the accent.
    """

    def test_checked_tool_button_is_outlined_not_filled(self) -> None:
        """
        Ensures the accent appears as a border, not as the background.

        A solid accent fill hid each tool's own glyph colors and read as a
        pressed state instead of a selection.
        """

        sheet = build_editor_accent_stylesheet(THEME_DARK)
        start = sheet.index("#editorHost QToolButton:checked")
        rule = sheet[start : sheet.index("}", start)]

        self.assertIn("border: 2px solid", rule)
        self.assertNotIn("background: #2f7dd1", rule)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for UI tests")
class TestCornerRadiusDegrees(unittest.TestCase):
    """
    Verifies the corner radius is a whole-degree slider rather than a decimal
    spin box, in both editors.
    """

    @classmethod
    def setUpClass(cls) -> None:
        ensure_qapp()

    def test_clamp_keeps_values_inside_the_slider_range(self) -> None:
        """
        Ensures out-of-range and non-numeric values are handled.
        """

        self.assertEqual(clamp_corner_radius_degrees(-5), 0)
        self.assertEqual(clamp_corner_radius_degrees(0), 0)
        self.assertEqual(clamp_corner_radius_degrees(8.4), 8)
        self.assertEqual(clamp_corner_radius_degrees(8.6), 9)
        self.assertEqual(clamp_corner_radius_degrees(999), MAX_CORNER_RADIUS_DEGREES)
        self.assertEqual(clamp_corner_radius_degrees("nope"), 0)

    def test_video_editor_radius_slider_spans_zero_to_180(self) -> None:
        """
        Ensures the video editor exposes the documented degree range.
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "source.mp4"
            source.write_bytes(b"not-a-real-video")
            editor = VideoEditorWindow(str(source), 320, 240)
            toolbar = editor._vector_toolbar  # pylint: disable=protected-access

            self.assertEqual(toolbar.style_radius_slider.minimum(), 0)
            self.assertEqual(toolbar.style_radius_slider.maximum(), MAX_CORNER_RADIUS_DEGREES)
            self.assertEqual(toolbar.style_radius_slider.orientation(), Qt.Orientation.Horizontal)
            editor.close()

    def test_video_editor_radius_label_shows_degrees(self) -> None:
        """
        Ensures the value reads as degrees, not a bare decimal.
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "source.mp4"
            source.write_bytes(b"not-a-real-video")
            editor = VideoEditorWindow(str(source), 320, 240)
            toolbar = editor._vector_toolbar  # pylint: disable=protected-access

            toolbar.style_radius_slider.setValue(42)

            self.assertEqual(toolbar.style_radius_label.text(), "42°")
            editor.close()

    def test_edit_tab_is_named_edit_in_the_video_editor(self) -> None:
        """
        Ensures the panel rename reached the video editor too.
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "source.mp4"
            source.write_bytes(b"not-a-real-video")
            editor = VideoEditorWindow(str(source), 320, 240)
            tabs = editor._vector_toolbar._property_tabs  # pylint: disable=protected-access

            self.assertEqual(tabs.tabText(0), "Edit")
            editor.close()


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for UI tests")
class TestMeasureBoxCursor(unittest.TestCase):
    """
    Verifies the MeasureBox handle cursor does not leak onto the application.
    """

    @classmethod
    def setUpClass(cls) -> None:
        ensure_qapp()

    def test_handle_cursor_is_set_on_the_item_not_the_application(self) -> None:
        """
        Ensures hovering handles never touches the override-cursor stack.

        setOverrideCursor pushes; the hover handler ran on every mouse move
        while leaving popped only once, so the last resize cursor stayed on
        screen for the rest of the session.
        """

        from PySide6.QtWidgets import QApplication

        from src.measurebox.resizable_rect_item import ResizableRectItem

        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor

        item = ResizableRectItem(
            QRectF(0.0, 0.0, 120.0, 80.0), QColor('#ff0000'), QColor(0, 0, 0, 0)
        )
        before = QApplication.overrideCursor()

        for _ in range(25):
            item._set_cursor_for_handle("bottom_right")  # pylint: disable=protected-access

        self.assertIs(QApplication.overrideCursor(), before)
        self.assertEqual(item.cursor().shape(), Qt.CursorShape.SizeFDiagCursor)


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for UI tests")
class TestSelectionFooterFormatting(unittest.TestCase):
    """
    Verifies the footer reports whole pixels in the documented layout.
    """

    def test_pixels_are_whole_numbers(self) -> None:
        """
        Ensures scene-math fractions never reach the footer.
        """

        from src.selection_info import format_pixels

        self.assertEqual(format_pixels(195.4), "195")
        self.assertEqual(format_pixels(195.6), "196")
        self.assertEqual(format_pixels(10), "10")
        self.assertEqual(format_pixels("nope"), "0")

    def test_pair_carries_a_single_px_suffix(self) -> None:
        """
        Ensures the pair reads as one measurement, not two.
        """

        from src.selection_info import format_pixel_pair

        self.assertEqual(format_pixel_pair(10, 10), "10x10px")
        self.assertEqual(format_pixel_pair(30.2, 20.9), "30x21px")

    def test_rectangle_summary_uses_the_documented_layout(self) -> None:
        """
        Ensures the footer renders size(x/y) and pos(x/y) as specified.
        """

        from src.editor_window import format_selection_info

        summary = format_selection_info(
            {"type": "rect", "x": 30.0, "y": 20.4, "width": 10.0, "height": 10.0}
        )

        self.assertIn("size(x/y):10x10px", summary)
        self.assertIn("pos(x/y):30x20px", summary)

    def test_vertices_are_listed_for_polygon_shapes(self) -> None:
        """
        Ensures every corner of a vertex shape reaches the footer.
        """

        from src.selection_info import format_vertex_list

        rendered = format_vertex_list([(10, 10), (20, 30), (5.4, 7.6)])

        self.assertIn("pts(3)(x/y):", rendered)
        self.assertIn("10x10px", rendered)
        self.assertIn("20x30px", rendered)
        self.assertIn("5x8px", rendered)

    def test_long_vertex_lists_are_truncated(self) -> None:
        """
        Ensures a traced polyline cannot push everything else out of the bar.
        """

        from src.selection_info import MAX_LISTED_VERTICES, format_vertex_list

        points = [(index, index) for index in range(MAX_LISTED_VERTICES + 8)]
        rendered = format_vertex_list(points)

        self.assertIn(f"pts({len(points)})(x/y):", rendered)
        self.assertTrue(rendered.endswith("…"))

    def test_no_vertices_renders_nothing(self) -> None:
        """
        Ensures non-vertex shapes add no empty section.
        """

        from src.selection_info import format_vertex_list

        self.assertEqual(format_vertex_list(None), "")
        self.assertEqual(format_vertex_list([]), "")


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for UI tests")
class TestExportSubmenuAndZoomChrome(unittest.TestCase):
    """
    Verifies the File menu keeps exports in a submenu and zoom chrome is compact.
    """

    @classmethod
    def setUpClass(cls) -> None:
        ensure_qapp()

    def test_export_actions_live_in_an_export_submenu(self) -> None:
        """
        Ensures the File menu is not padded with six export entries.
        """

        from PySide6.QtGui import QColor, QPixmap

        from src.editor_window import EditorWindow

        pixmap = QPixmap(80, 60)
        pixmap.fill(QColor(220, 220, 220))
        window = EditorWindow(pixmap)

        entries = [action.text() for action in window.export_menu.actions()]

        self.assertIn("Export...", entries)
        self.assertIn("Export as PNG...", entries)
        self.assertIn("Export as PDF...", entries)
        self.assertIn("Batch Export...", entries)
        window.close()

    def test_zoom_reset_is_an_icon_button(self) -> None:
        """
        Ensures the text "Reset" was traded for a glyph to save toolbar width.
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "source.mp4"
            source.write_bytes(b"not-a-real-video")
            editor = VideoEditorWindow(str(source), 320, 240)

            self.assertEqual(editor.zoom_reset_button.text(), "")
            self.assertFalse(editor.zoom_reset_button.icon().isNull())
            self.assertNotEqual(editor.zoom_reset_button.toolTip().strip(), "")
            editor.close()

    def test_zoom_step_buttons_use_a_larger_glyph(self) -> None:
        """
        Ensures the bare "+" is legible next to the wider zoom slider.
        """

        from src.tool_icons import ZOOM_STEP_FONT_POINT_SIZE

        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "source.mp4"
            source.write_bytes(b"not-a-real-video")
            editor = VideoEditorWindow(str(source), 320, 240)

            self.assertEqual(
                editor.zoom_in_button.font().pointSize(), ZOOM_STEP_FONT_POINT_SIZE
            )
            self.assertTrue(editor.zoom_in_button.font().bold())
            editor.close()
