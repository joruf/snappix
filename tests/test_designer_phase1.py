"""
Phase 1 designer feature tests: brush, align, transform, eyedropper, export.
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QColor, QImage, QPixmap

    from src.annotation_items import (
        add_annotation_to_scene,
        annotation_from_item,
        transform_payload_from_item,
    )
    from src.brush_paint import paint_soft_brush_segment
    from src.editor_canvas import Tool
    from src.editor_window import EditorWindow
    from src.models import AnnotationModel
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


def _solid_pixmap(width: int, height: int, color: QColor | None = None) -> QPixmap:
    """
    Creates a plain screenshot image for editor tests.

    Args:
        width: Image width.
        height: Image height.
        color: Optional fill color.

    Returns:
        QPixmap: Generated pixmap.
    """

    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(color or QColor(255, 255, 255, 255))
    return QPixmap.fromImage(image)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for Phase 1 designer tests")
class TestDesignerPhase1(unittest.TestCase):
    """
    Verifies Phase 1 designer tools and export helpers.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures QApplication exists for Qt widgets.
        """

        cls._app = ensure_qapp()

    def test_soft_brush_stamp_paints_with_opacity(self) -> None:
        """
        Ensures soft brush painting writes translucent pixels.
        """

        image = QImage(64, 64, QImage.Format.Format_ARGB32)
        image.fill(QColor(0, 0, 0, 0))
        color = QColor(255, 0, 0, 128)
        painted = paint_soft_brush_segment(
            image,
            QPointF(32.0, 32.0),
            QPointF(32.0, 32.0),
            radius=8.0,
            color=color,
            hardness=50.0,
            erase=False,
        )
        self.assertTrue(painted)
        center = image.pixelColor(32, 32)
        self.assertGreater(center.alpha(), 0)
        self.assertEqual(center.red(), 255)

    def test_eraser_reduces_alpha(self) -> None:
        """
        Ensures eraser DestinationOut reduces painted alpha.
        """

        image = QImage(64, 64, QImage.Format.Format_ARGB32)
        image.fill(QColor(0, 120, 255, 255))
        paint_soft_brush_segment(
            image,
            QPointF(32.0, 32.0),
            QPointF(32.0, 32.0),
            radius=10.0,
            color=QColor(255, 255, 255, 255),
            hardness=100.0,
            erase=True,
        )
        center = image.pixelColor(32, 32)
        self.assertLess(center.alpha(), 255)

    def test_brush_stroke_records_one_history_entry(self) -> None:
        """
        Ensures one brush stroke creates a single undo step.
        """

        window = EditorWindow(_solid_pixmap(120, 80))
        before = len(window._history)  # pylint: disable=protected-access
        canvas = window.canvas
        canvas.set_tool(Tool.BRUSH)
        canvas.set_style(stroke_width=8.0, stroke_color=QColor(255, 0, 0, 255))
        canvas._brush_painting = True  # pylint: disable=protected-access
        canvas._brush_erase_mode = False  # pylint: disable=protected-access
        canvas._brush_stroke_dirty = False  # pylint: disable=protected-access
        canvas._paint_brush_segment(QPointF(10, 10), QPointF(20, 12))  # pylint: disable=protected-access
        canvas._paint_brush_segment(QPointF(20, 12), QPointF(40, 30))  # pylint: disable=protected-access
        canvas._emit_content_changed("Brush stroke")  # pylint: disable=protected-access
        self.assertEqual(len(window._history), before + 1)  # pylint: disable=protected-access
        self.assertEqual(window._history_labels[-1], "Brush stroke")  # pylint: disable=protected-access
        window.close()

    def test_stroke_width_slider_defers_history_while_dragging(self) -> None:
        """
        Ensures border width history is not pushed on every drag tick.
        """

        window = EditorWindow(_solid_pixmap(120, 80))
        annotation = AnnotationModel(
            annotation_type="rect",
            x=10.0,
            y=10.0,
            width=40.0,
            height=20.0,
            stroke_rgba=[255, 0, 0, 255],
            fill_rgba=[255, 0, 0, 80],
            stroke_width=2.0,
        )
        window.canvas.load_annotations([annotation])
        for item in window.canvas._annotation_items():  # pylint: disable=protected-access
            item.setSelected(True)
        before = len(window._history)  # pylint: disable=protected-access
        window.stroke_size_slider.setSliderDown(True)
        window._stroke_width_changed(12)  # pylint: disable=protected-access
        window._stroke_width_changed(18)  # pylint: disable=protected-access
        self.assertEqual(len(window._history), before)  # pylint: disable=protected-access
        window.stroke_size_slider.setSliderDown(False)
        window._stroke_width_committed()  # pylint: disable=protected-access
        self.assertEqual(len(window._history), before + 1)  # pylint: disable=protected-access
        self.assertEqual(window._history_labels[-1], "Change border width")  # pylint: disable=protected-access
        window.close()

    def test_align_and_distribute_selection(self) -> None:
        """
        Ensures align/distribute APIs reposition unlocked items.
        """

        window = EditorWindow(_solid_pixmap(300, 200))
        models = [
            AnnotationModel(
                annotation_type="rect",
                x=10.0,
                y=10.0,
                width=20.0,
                height=20.0,
                stroke_rgba=[255, 0, 0, 255],
                fill_rgba=[255, 0, 0, 80],
                stroke_width=2.0,
            ),
            AnnotationModel(
                annotation_type="rect",
                x=80.0,
                y=40.0,
                width=20.0,
                height=20.0,
                stroke_rgba=[0, 255, 0, 255],
                fill_rgba=[0, 255, 0, 80],
                stroke_width=2.0,
            ),
            AnnotationModel(
                annotation_type="rect",
                x=160.0,
                y=70.0,
                width=20.0,
                height=20.0,
                stroke_rgba=[0, 0, 255, 255],
                fill_rgba=[0, 0, 255, 80],
                stroke_width=2.0,
            ),
        ]
        window.canvas.load_annotations(models)
        items = window.canvas._annotation_items()  # pylint: disable=protected-access
        for item in items:
            item.setSelected(True)
        self.assertTrue(window.canvas.distribute_selected("horizontal"))
        centers = [
            window.canvas._item_scene_rect(item).center().x()  # pylint: disable=protected-access
            for item in items
        ]
        centers.sort()
        gap_a = centers[1] - centers[0]
        gap_b = centers[2] - centers[1]
        self.assertAlmostEqual(gap_a, gap_b, places=2)
        self.assertTrue(window.canvas.align_selected("left"))
        lefts = [window.canvas._item_scene_rect(item).left() for item in items]  # pylint: disable=protected-access
        self.assertAlmostEqual(min(lefts), max(lefts), places=2)
        window.close()

    def test_transform_payload_round_trip(self) -> None:
        """
        Ensures rotation and mirror survive annotation serialization.
        """

        window = EditorWindow(_solid_pixmap(200, 120))
        model = AnnotationModel(
            annotation_type="rect",
            x=30.0,
            y=20.0,
            width=40.0,
            height=24.0,
            stroke_rgba=[10, 20, 30, 255],
            fill_rgba=[10, 20, 30, 80],
            stroke_width=2.0,
            payload={"rotation": 15.0, "mirror_h": True, "skew_x": 5.0},
        )
        item = add_annotation_to_scene(window.canvas._scene, model)  # pylint: disable=protected-access
        self.assertIsNotNone(item)
        assert item is not None
        transform = transform_payload_from_item(item)
        self.assertAlmostEqual(float(transform["rotation"]), 15.0, places=2)
        self.assertTrue(transform["mirror_h"])
        self.assertAlmostEqual(float(transform["skew_x"]), 5.0, places=2)
        restored = annotation_from_item(item)
        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertAlmostEqual(float(restored.payload.get("rotation", 0.0)), 15.0, places=2)
        self.assertTrue(bool(restored.payload.get("mirror_h")))
        window.close()

    def test_eyedropper_samples_border_color(self) -> None:
        """
        Ensures eyedropper writes sampled screenshot color into stroke style.
        """

        pixmap = _solid_pixmap(80, 60, QColor(12, 34, 56, 255))
        window = EditorWindow(pixmap)
        window.canvas.set_eyedropper_target("stroke")
        window.canvas.set_tool(Tool.EYEDROPPER)
        window.canvas._sample_color_at(QPointF(10.0, 10.0))  # pylint: disable=protected-access
        stroke = window.canvas._style.stroke_color  # pylint: disable=protected-access
        self.assertEqual(stroke.red(), 12)
        self.assertEqual(stroke.green(), 34)
        self.assertEqual(stroke.blue(), 56)
        window.close()

    def test_export_scale_and_matte(self) -> None:
        """
        Ensures export scale and opaque matte options work.
        """

        window = EditorWindow(_solid_pixmap(50, 40, QColor(0, 0, 0, 0)))
        scaled = window.canvas.export_composited_pixmap(scale=2.0)
        self.assertEqual(scaled.width(), 100)
        self.assertEqual(scaled.height(), 80)
        matted = window.canvas.export_composited_pixmap(
            scale=1.0,
            background=QColor(255, 255, 255, 255),
        )
        pixel = matted.toImage().pixelColor(0, 0)
        self.assertEqual(pixel.red(), 255)
        self.assertEqual(pixel.alpha(), 255)
        window.set_export_scale(2.0)
        window.set_export_keep_transparency(False)
        exported = window._export_output_pixmap(for_jpeg=False)  # pylint: disable=protected-access
        self.assertEqual(exported.width(), 100)
        window.close()

    def test_eraser_and_eyedropper_tools_exist(self) -> None:
        """
        Ensures Phase 1 tools are registered in the toolbar.
        """

        window = EditorWindow(_solid_pixmap(80, 60))
        self.assertIn(Tool.ERASER, window._tool_buttons)  # pylint: disable=protected-access
        self.assertIn(Tool.EYEDROPPER, window._tool_buttons)  # pylint: disable=protected-access
        self.assertTrue(window.brush_hardness_label.text().endswith("%"))
        self.assertTrue(hasattr(window, "export_scale_combo"))
        window.close()


if __name__ == "__main__":
    unittest.main()
