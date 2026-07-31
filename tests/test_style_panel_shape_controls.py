"""
Tests for the Style panel's per-object Thickness/Style/Radius controls: they
must show only the settings relevant to a single selected object, apply
edits directly to that selection, and hide entirely for an empty or
multi-object selection (since different objects can have different settings).
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPixmap

    from src.annotation_items import STROKE_STYLE_DASH
    from src.editor_window import EditorWindow
    from src.models import AnnotationModel
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


def _make_window() -> "EditorWindow":
    """
    Builds a plain EditorWindow over a solid test pixmap.

    Returns:
        EditorWindow: Editor instance ready for annotation tests.
    """

    pixmap = QPixmap(160, 120)
    pixmap.fill(QColor(230, 230, 230))
    return EditorWindow(pixmap)


def _rect_annotation(**overrides) -> "AnnotationModel":
    """
    Builds one rectangle annotation, with any field overridden.

    Args:
        overrides: Field values to override on the default rectangle model.

    Returns:
        AnnotationModel: Sample rectangle annotation.
    """

    defaults = dict(
        annotation_type="rect",
        x=10.0,
        y=10.0,
        width=40.0,
        height=20.0,
        stroke_rgba=[255, 0, 0, 255],
        fill_rgba=[255, 0, 0, 80],
        stroke_width=6.0,
        payload={"corner_radius": 8.0, "stroke_style": STROKE_STYLE_DASH},
    )
    defaults.update(overrides)
    return AnnotationModel(**defaults)


def _line_annotation(**overrides) -> "AnnotationModel":
    """
    Builds one line annotation, with any field overridden.

    Args:
        overrides: Field values to override on the default line model.

    Returns:
        AnnotationModel: Sample line annotation.
    """

    defaults = dict(
        annotation_type="line",
        x=10.0,
        y=20.0,
        width=60.0,
        height=0.0,
        stroke_rgba=[0, 0, 255, 255],
        fill_rgba=[0, 0, 0, 0],
        stroke_width=3.0,
    )
    defaults.update(overrides)
    return AnnotationModel(**defaults)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for style panel tests")
class TestStylePanelShapeControlVisibility(unittest.TestCase):
    """
    Verifies the Style tab and its shape controls show/hide correctly.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = ensure_qapp()

    def test_no_selection_hides_style_tab_and_resets_controls(self) -> None:
        """
        Ensures deselecting hides the Style tab and resets shape controls.
        """

        window = _make_window()
        window.canvas.load_annotations([_rect_annotation()])
        item = window.canvas._annotation_items()[0]  # pylint: disable=protected-access
        item.setSelected(True)
        window.canvas._refresh_selection_info()  # pylint: disable=protected-access
        item.setSelected(False)
        window.canvas._refresh_selection_info()  # pylint: disable=protected-access

        self.assertFalse(window._property_tabs.isTabVisible(window._PROPERTY_TAB_STYLE))  # pylint: disable=protected-access
        self.assertEqual(window.style_thickness_slider.value(), 0)
        window.close()

    def test_selecting_a_rect_shows_thickness_style_and_radius(self) -> None:
        """
        Ensures selecting a rectangle populates all three shape controls and
        shows the Style tab.
        """

        window = _make_window()
        window.canvas.load_annotations([_rect_annotation()])
        item = window.canvas._annotation_items()[0]  # pylint: disable=protected-access
        item.setSelected(True)
        window.canvas._refresh_selection_info()  # pylint: disable=protected-access

        self.assertTrue(window._property_tabs.isTabVisible(window._PROPERTY_TAB_STYLE))  # pylint: disable=protected-access
        self.assertFalse(window.style_thickness_slider.isHidden())
        self.assertFalse(window.style_stroke_style_combo.isHidden())
        self.assertFalse(window.style_radius_slider.isHidden())
        self.assertEqual(window.style_thickness_slider.value(), 6)
        self.assertEqual(window.style_stroke_style_combo.currentData(), STROKE_STYLE_DASH)
        self.assertEqual(window.style_radius_slider.value(), 8)
        window.close()

    def test_selecting_a_line_hides_radius_but_shows_thickness_and_style(self) -> None:
        """
        Ensures a shape type without corner radius (line) hides the Radius
        control while still showing Thickness and Style.
        """

        window = _make_window()
        window.canvas.load_annotations([_line_annotation()])
        item = window.canvas._annotation_items()[0]  # pylint: disable=protected-access
        item.setSelected(True)
        window.canvas._refresh_selection_info()  # pylint: disable=protected-access

        self.assertFalse(window.style_thickness_slider.isHidden())
        self.assertFalse(window.style_stroke_style_combo.isHidden())
        self.assertTrue(window.style_radius_slider.isHidden())
        window.close()

    def test_multi_selection_hides_the_entire_style_tab(self) -> None:
        """
        Ensures selecting two or more objects hides the Style tab entirely,
        rather than showing the first selected item's settings.
        """

        window = _make_window()
        window.canvas.load_annotations([_rect_annotation(x=10.0), _rect_annotation(x=60.0)])
        for item in window.canvas._annotation_items():  # pylint: disable=protected-access
            item.setSelected(True)
        window.canvas._refresh_selection_info()  # pylint: disable=protected-access

        self.assertFalse(window._property_tabs.isTabVisible(window._PROPERTY_TAB_STYLE))  # pylint: disable=protected-access
        window.close()

    def test_selecting_text_does_not_populate_shape_controls(self) -> None:
        """
        Ensures selecting a text annotation leaves the shape controls hidden
        (text border thickness stays in the Text tool popup, out of scope
        for this Style-panel consolidation).
        """

        window = _make_window()
        window.canvas.load_annotations(
            [
                AnnotationModel(
                    annotation_type="text",
                    x=10.0,
                    y=10.0,
                    width=40.0,
                    height=20.0,
                    stroke_rgba=[0, 0, 0, 255],
                    fill_rgba=[0, 0, 0, 0],
                    stroke_width=2.0,
                    text="Hello",
                    font_size=16,
                    font_family="Sans Serif",
                )
            ]
        )
        item = window.canvas._annotation_items()[0]  # pylint: disable=protected-access
        item.setSelected(True)
        window.canvas._refresh_selection_info()  # pylint: disable=protected-access

        self.assertTrue(window.style_thickness_slider.isHidden())
        self.assertTrue(window.style_stroke_style_combo.isHidden())
        self.assertTrue(window.style_radius_slider.isHidden())
        window.close()


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for style panel tests")
class TestStylePanelShapeControlApply(unittest.TestCase):
    """
    Verifies editing the Style panel's shape controls edits only the
    selection, independent of the corresponding tool's popup default.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = ensure_qapp()

    def test_thickness_slider_edits_only_the_selected_rect(self) -> None:
        """
        Ensures dragging the Style panel's Thickness slider changes only the
        selected rectangle's stroke width, and records one undo step.
        """

        window = _make_window()
        window.canvas.load_annotations([_rect_annotation(stroke_width=6.0)])
        item = window.canvas._annotation_items()[0]  # pylint: disable=protected-access
        item.setSelected(True)
        window.canvas._refresh_selection_info()  # pylint: disable=protected-access
        before = len(window._history)  # pylint: disable=protected-access

        window._style_thickness_changed(24)  # pylint: disable=protected-access

        self.assertEqual(int(item.pen().widthF()), 24)
        self.assertEqual(len(window._history), before + 1)  # pylint: disable=protected-access
        window.close()

    def test_stroke_style_combo_edits_only_the_selected_line(self) -> None:
        """
        Ensures changing the Style panel's Style combo changes the selected
        line's dash pattern.
        """

        window = _make_window()
        window.canvas.load_annotations([_line_annotation()])
        item = window.canvas._annotation_items()[0]  # pylint: disable=protected-access
        item.setSelected(True)
        window.canvas._refresh_selection_info()  # pylint: disable=protected-access

        dash_index = window.style_stroke_style_combo.findData(STROKE_STYLE_DASH)
        window.style_stroke_style_combo.setCurrentIndex(dash_index)

        self.assertEqual(item.pen().style(), Qt.PenStyle.DashLine)
        window.close()

    def test_radius_spin_edits_only_the_selected_rect_and_not_tool_default(self) -> None:
        """
        Ensures the Style panel's Radius spin changes only the selected
        rectangle's corner radius, leaving the Rect tool's own default radius
        (used for new draws) untouched.
        """

        window = _make_window()
        window._rect_corner_radius = 2.0  # pylint: disable=protected-access
        window.canvas.load_annotations([_rect_annotation(payload={"corner_radius": 2.0})])
        item = window.canvas._annotation_items()[0]  # pylint: disable=protected-access
        item.setSelected(True)
        window.canvas._refresh_selection_info()  # pylint: disable=protected-access

        window._style_corner_radius_changed(16.0)  # pylint: disable=protected-access

        self.assertAlmostEqual(item.corner_radius(), 16.0)
        self.assertAlmostEqual(window._rect_corner_radius, 2.0)  # pylint: disable=protected-access
        window.close()


if __name__ == "__main__":
    unittest.main()
