"""
Tests for the annotation contrast halo.
"""

from __future__ import annotations

import unittest

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsScene

from src.annotation_items import ArrowItem, StrokeLineItem
from src.color_contrast import contrast_ratio, halo_color_for, halo_pen_width
from src.shape_items import PathShapeItem, PolyPathItem
from tests.qt_test_utils import ensure_qapp


def render_on(background: str, item, size: int = 200) -> "QColor":
    """
    Renders one item over a flat background and returns the result image.

    Args:
        background: Background color name.
        item: Graphics item to render.
        size: Square canvas edge length.

    Returns:
        QImage: Rendered image.
    """

    scene = QGraphicsScene()
    scene.setSceneRect(0.0, 0.0, float(size), float(size))
    scene.addItem(item)
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(background))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    scene.render(painter)
    painter.end()
    return pixmap.toImage()


def distinct_colors(image, x_range: range, y_range: range, threshold: int = 20) -> int:
    """
    Counts colors covering more than a threshold number of pixels in a region.

    Args:
        image: Image to sample.
        x_range: Horizontal sample range.
        y_range: Vertical sample range.
        threshold: Minimum pixel count for a color to be counted.

    Returns:
        int: Number of sufficiently present colors.
    """

    counts: dict[str, int] = {}
    for x in x_range:
        for y in y_range:
            name = image.pixelColor(x, y).name()
            counts[name] = counts.get(name, 0) + 1
    return len([name for name, count in counts.items() if count > threshold])


class HaloColorTests(unittest.TestCase):
    """
    Class HaloColorTests

    Covers the counter-color choice and the pen width derivation.
    """

    def setUp(self) -> None:
        """
        Returns:
            None
        """

        ensure_qapp()

    def test_dark_annotation_gets_a_light_halo(self) -> None:
        """
        Returns:
            None
        """

        self.assertEqual(halo_color_for(QColor("#000000")).name(), "#ffffff")

    def test_light_annotation_gets_a_dark_halo(self) -> None:
        """
        Returns:
            None
        """

        self.assertEqual(halo_color_for(QColor("#FFFFFF")).name(), "#000000")

    def test_halo_always_beats_the_alternative_in_contrast(self) -> None:
        """
        The halo must be whichever of black/white contrasts more with the
        annotation, since that is what guarantees one of the two is visible
        against any backdrop.

        Returns:
            None
        """

        for name in ("#E5484D", "#3B82F6", "#FFE500", "#808080", "#123456", "#EEEEEE"):
            color = QColor(name)
            chosen = halo_color_for(color)
            other = QColor("#000000") if chosen.name() == "#ffffff" else QColor("#ffffff")
            self.assertGreaterEqual(
                contrast_ratio(color, chosen),
                contrast_ratio(color, other),
                msg=f"wrong halo for {name}",
            )

    def test_halo_is_wider_than_the_stroke_it_backs(self) -> None:
        """
        Returns:
            None
        """

        for width in (0.0, 1.0, 2.0, 6.0, 20.0):
            self.assertGreater(halo_pen_width(width), width)

    def test_hairline_stroke_still_gets_a_usable_halo(self) -> None:
        """
        Returns:
            None
        """

        self.assertGreaterEqual(halo_pen_width(0.5), 2.5)


class HaloRenderTests(unittest.TestCase):
    """
    Class HaloRenderTests

    Covers the halo actually separating an annotation from a matching backdrop.
    """

    def setUp(self) -> None:
        """
        Returns:
            None
        """

        ensure_qapp()

    def _rect_item(self, halo: bool) -> PathShapeItem:
        """
        Builds one red rectangle outline with or without a halo.

        Args:
            halo: True to enable the contrast halo.

        Returns:
            PathShapeItem: Configured item.
        """

        item = PathShapeItem("rect", QRectF(50.0, 40.0, 100.0, 70.0))
        item.setPen(QPen(QColor("#E5484D"), 4.0))
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        item.set_halo_enabled(halo)
        return item

    def test_red_on_red_is_invisible_without_a_halo(self) -> None:
        """
        Returns:
            None
        """

        image = render_on("#E5484D", self._rect_item(False))
        self.assertEqual(distinct_colors(image, range(40, 165), range(30, 55)), 1)

    def test_halo_makes_red_on_red_visible(self) -> None:
        """
        Returns:
            None
        """

        image = render_on("#E5484D", self._rect_item(True))
        self.assertGreater(distinct_colors(image, range(40, 165), range(30, 55)), 1)

    def test_halo_does_not_alter_the_annotation_color(self) -> None:
        """
        The user's color is deliberate; the halo may only add an edge around it.

        Returns:
            None
        """

        image = render_on("#FFFFFF", self._rect_item(True))
        found = False
        for x in range(40, 165):
            for y in range(30, 60):
                if image.pixelColor(x, y).name() == "#e5484d":
                    found = True
                    break
        self.assertTrue(found, "the annotation's own color must survive unchanged")


class HaloItemTests(unittest.TestCase):
    """
    Class HaloItemTests

    Covers the halo flag across every stroked item class and its bounds growth.
    """

    def setUp(self) -> None:
        """
        Returns:
            None
        """

        ensure_qapp()

    def test_every_stroked_item_kind_supports_the_halo(self) -> None:
        """
        Returns:
            None
        """

        items = [
            PathShapeItem("rect", QRectF(0.0, 0.0, 100.0, 80.0)),
            PolyPathItem("polyline", [QPointF(0.0, 0.0), QPointF(50.0, 30.0)]),
            StrokeLineItem(0.0, 0.0, 100.0, 50.0),
            ArrowItem(0.0, 0.0, 100.0, 50.0),
        ]
        for item in items:
            self.assertFalse(item.halo_enabled(), msg=type(item).__name__)
            item.set_halo_enabled(True)
            self.assertTrue(item.halo_enabled(), msg=type(item).__name__)

    def test_bounds_grow_so_a_thick_halo_is_not_clipped(self) -> None:
        """
        Returns:
            None
        """

        item = PathShapeItem("rect", QRectF(0.0, 0.0, 100.0, 80.0))
        item.setPen(QPen(QColor("#E5484D"), 12.0))
        before = item.boundingRect().width()
        item.set_halo_enabled(True)
        self.assertGreater(item.boundingRect().width(), before)

    def test_thick_line_halo_fits_inside_the_bounds(self) -> None:
        """
        A line's bounds come from its hit-test shape, which pads by a fixed
        amount; a thick stroke pushes the halo past that padding.

        Returns:
            None
        """

        item = ArrowItem(0.0, 0.0, 100.0, 50.0)
        item.setPen(QPen(QColor("#E5484D"), 20.0))
        before = item.boundingRect().width()
        item.set_halo_enabled(True)
        self.assertGreater(item.boundingRect().width(), before)


class HaloPersistenceTests(unittest.TestCase):
    """
    Class HaloPersistenceTests

    Covers the halo flag surviving a save/load roundtrip.
    """

    def setUp(self) -> None:
        """
        Returns:
            None
        """

        ensure_qapp()
        self.scene = QGraphicsScene()

    def _stored(self, halo: bool):
        """
        Serializes one rectangle with the given halo setting.

        Args:
            halo: True to enable the halo before serializing.

        Returns:
            AnnotationModel: Serialized model.
        """

        from src.annotation_items import annotation_from_item, configure_graphics_item

        item = PathShapeItem("rect", QRectF(0.0, 0.0, 100.0, 80.0))
        self.scene.addItem(item)
        configure_graphics_item(item, "rect")
        item.set_halo_enabled(halo)
        return annotation_from_item(item)

    def test_halo_survives_a_roundtrip(self) -> None:
        """
        Returns:
            None
        """

        from src.annotation_items import add_annotation_to_scene

        model = self._stored(True)
        self.assertTrue(model.payload.get("halo"))
        restored = add_annotation_to_scene(self.scene, model)
        self.assertTrue(restored.halo_enabled())

    def test_projects_saved_before_halos_keep_their_look(self) -> None:
        """
        A missing key must not silently restyle an existing project.

        Returns:
            None
        """

        from src.annotation_items import add_annotation_to_scene

        model = self._stored(True)
        model.payload.pop("halo", None)
        restored = add_annotation_to_scene(self.scene, model)
        self.assertFalse(restored.halo_enabled())


class HaloToolDefaultTests(unittest.TestCase):
    """
    Class HaloToolDefaultTests

    Covers the halo behaving as a tool default, so a newly drawn annotation gets
    one without the user first selecting it and ticking a box.
    """

    def setUp(self) -> None:
        """
        Returns:
            None
        """

        ensure_qapp()
        from src.editor_window import EditorWindow

        pixmap = QPixmap(400, 300)
        pixmap.fill(QColor("#FFFFFF"))
        self.window = EditorWindow(pixmap)
        self.canvas = self.window.canvas

    def tearDown(self) -> None:
        """
        Returns:
            None
        """

        self.window.close()

    def _preview(self, tool: str):
        """
        Builds the in-progress item for one tool.

        Args:
            tool: Tool identifier to activate.

        Returns:
            QGraphicsItem: The preview item.
        """

        self.canvas.set_tool(tool)
        return self.canvas._create_preview_item(QPointF(10.0, 10.0))  # pylint: disable=protected-access

    def test_halo_is_on_by_default(self) -> None:
        """
        Returns:
            None
        """

        self.assertTrue(self.canvas.annotation_halo())
        self.assertTrue(self.window.style_halo_check.isChecked())

    def test_newly_drawn_annotations_get_a_halo(self) -> None:
        """
        Returns:
            None
        """

        from src.editor_canvas import Tool

        for tool in (Tool.RECT, Tool.ARROW, Tool.LINE):
            self.assertTrue(self._preview(tool).halo_enabled(), msg=str(tool))

    def test_unticking_the_box_changes_what_gets_drawn_next(self) -> None:
        """
        Returns:
            None
        """

        from src.editor_canvas import Tool

        self.window.style_halo_check.setChecked(False)
        self.assertFalse(self.canvas.annotation_halo())
        self.assertFalse(self._preview(Tool.ARROW).halo_enabled())

        self.window.style_halo_check.setChecked(True)
        self.assertTrue(self.canvas.annotation_halo())
        self.assertTrue(self._preview(Tool.ARROW).halo_enabled())

    def test_checkbox_shows_the_default_when_nothing_is_selected(self) -> None:
        """
        With no selection the box is not a neutral placeholder -- it states what
        the next annotation will look like.

        Returns:
            None
        """

        self.window.style_halo_check.setChecked(False)
        self.window._restore_style_shape_controls()  # pylint: disable=protected-access
        self.assertFalse(self.window.style_halo_check.isChecked())

        self.window.style_halo_check.setChecked(True)
        self.window._restore_style_shape_controls()  # pylint: disable=protected-access
        self.assertTrue(self.window.style_halo_check.isChecked())

    def test_preview_overlays_are_left_alone(self) -> None:
        """
        Crop and marquee overlays are plain Qt items without the mixin; applying
        the default must not crash on them.

        Returns:
            None
        """

        from src.editor_canvas import Tool

        for tool in (Tool.SELECT_RECT, Tool.BLUR):
            item = self._preview(tool)
            self.assertIsNotNone(item)
            self.assertFalse(hasattr(item, "halo_enabled"))


class HaloToolbarParityTests(unittest.TestCase):
    """
    Class HaloToolbarParityTests

    Covers both editors exposing the halo control under the same name.
    """

    def test_both_editors_expose_a_halo_checkbox(self) -> None:
        """
        Returns:
            None
        """

        import inspect

        from src import editor_window, video_vector_toolbar

        for module in (editor_window, video_vector_toolbar):
            source = inspect.getsource(module)
            self.assertIn("style_halo_check", source, msg=module.__name__)
            self.assertIn("_style_halo_toggled", source, msg=module.__name__)


if __name__ == "__main__":
    unittest.main()
