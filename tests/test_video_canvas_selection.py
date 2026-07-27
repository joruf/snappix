"""
Unit tests for video canvas annotation selection behavior.
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QGraphicsItem

    from src.editor_canvas import Tool
    from src.video_canvas import VideoCanvas, build_annotation_item
    from src.video_models import VideoAnnotationModel
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for video canvas GUI tests")
class TestVideoCanvasSelection(unittest.TestCase):
    """
    Verifies video annotations can be selected and edited.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures Qt application exists for graphics view tests.
        """

        cls._app = ensure_qapp()

    def _sample_rect_annotation(self) -> VideoAnnotationModel:
        """
        Builds one visible rectangle annotation at the current playhead.

        Returns:
            VideoAnnotationModel: Sample annotation model.
        """

        return VideoAnnotationModel(
            annotation_type=Tool.RECT,
            start_ms=0,
            end_ms=5000,
            x=40.0,
            y=30.0,
            width=120.0,
            height=80.0,
            stroke_rgba=[231, 76, 60, 255],
            fill_rgba=[231, 76, 60, 70],
            stroke_width=3.0,
            text="",
            font_size=16,
            font_family="",
            font_bold=False,
            font_italic=False,
            font_underline=False,
            payload={},
        )

    def test_playhead_hides_out_of_range_annotations_by_default(self) -> None:
        """
        Ensures annotations outside the current playhead time are hidden by default.
        """

        canvas = VideoCanvas()
        canvas.resize(640, 480)
        canvas.set_video_size(640, 480)
        canvas.show()
        self._app.processEvents()
        early = VideoAnnotationModel(
            annotation_type=Tool.RECT,
            start_ms=0,
            end_ms=1000,
            x=10.0,
            y=10.0,
            width=40.0,
            height=30.0,
            stroke_rgba=[255, 0, 0, 255],
            fill_rgba=[255, 0, 0, 80],
            stroke_width=2.0,
        )
        late = VideoAnnotationModel(
            annotation_type=Tool.RECT,
            start_ms=5000,
            end_ms=7000,
            x=80.0,
            y=60.0,
            width=40.0,
            height=30.0,
            stroke_rgba=[0, 0, 255, 255],
            fill_rgba=[0, 0, 255, 80],
            stroke_width=2.0,
        )
        canvas.set_annotations([early, late])
        canvas._on_position_changed(6000)  # pylint: disable=protected-access

        self.assertNotIn(early.annotation_id, canvas._visible_items)  # pylint: disable=protected-access
        self.assertIn(late.annotation_id, canvas._visible_items)  # pylint: disable=protected-access

    def test_show_all_annotations_reveals_out_of_range_items(self) -> None:
        """
        Ensures the show-all mode displays every drawing object at once.
        """

        canvas = VideoCanvas()
        canvas.resize(640, 480)
        canvas.set_video_size(640, 480)
        canvas.show()
        self._app.processEvents()
        early = VideoAnnotationModel(
            annotation_type=Tool.RECT,
            start_ms=0,
            end_ms=1000,
            x=10.0,
            y=10.0,
            width=40.0,
            height=30.0,
            stroke_rgba=[255, 0, 0, 255],
            fill_rgba=[255, 0, 0, 80],
            stroke_width=2.0,
        )
        late = VideoAnnotationModel(
            annotation_type=Tool.RECT,
            start_ms=5000,
            end_ms=7000,
            x=80.0,
            y=60.0,
            width=40.0,
            height=30.0,
            stroke_rgba=[0, 0, 255, 255],
            fill_rgba=[0, 0, 255, 80],
            stroke_width=2.0,
        )
        canvas.set_annotations([early, late])
        canvas._on_position_changed(6000)  # pylint: disable=protected-access
        canvas.set_show_all_annotations(True)

        self.assertIn(early.annotation_id, canvas._visible_items)  # pylint: disable=protected-access
        self.assertIn(late.annotation_id, canvas._visible_items)  # pylint: disable=protected-access

    def test_build_annotation_item_is_selectable(self) -> None:
        """
        Ensures built video annotation items expose Qt selection flags.
        """

        annotation = self._sample_rect_annotation()
        item = build_annotation_item(annotation)
        self.assertIsNotNone(item)
        assert item is not None
        self.assertTrue(item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.assertTrue(item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)

    def test_canvas_keeps_selection_after_rebuild(self) -> None:
        """
        Ensures a selected annotation stays selected after visible-item rebuild.
        """

        canvas = VideoCanvas()
        canvas.resize(640, 480)
        canvas.set_video_size(640, 480)
        canvas.show()
        self._app.processEvents()
        annotation = self._sample_rect_annotation()
        canvas.set_annotations([annotation])
        canvas.set_tool(Tool.SELECT)

        item = canvas._visible_items[annotation.annotation_id]  # pylint: disable=protected-access
        item.setSelected(True)

        canvas.refresh_visible_items()

        rebuilt = canvas._visible_items[annotation.annotation_id]  # pylint: disable=protected-access
        self.assertTrue(rebuilt.isSelected())

    def test_move_syncs_geometry_back_to_model(self) -> None:
        """
        Ensures moving a selected annotation updates the backing model.
        """

        canvas = VideoCanvas()
        canvas.resize(640, 480)
        canvas.set_video_size(640, 480)
        canvas.show()
        self._app.processEvents()
        annotation = self._sample_rect_annotation()
        canvas.set_annotations([annotation])
        canvas.set_tool(Tool.SELECT)

        item = canvas._visible_items[annotation.annotation_id]  # pylint: disable=protected-access
        item.setPos(10.0, 20.0)

        changed = canvas._sync_visible_items_to_models()  # pylint: disable=protected-access
        self.assertTrue(changed)
        self.assertAlmostEqual(annotation.x, 50.0, delta=0.5)
        self.assertAlmostEqual(annotation.y, 50.0, delta=0.5)

    def test_finalize_annotation_selects_new_item(self) -> None:
        """
        Ensures newly drawn annotations become selected after creation.
        """

        canvas = VideoCanvas()
        canvas.resize(640, 480)
        canvas.set_video_size(640, 480)
        canvas.show()
        self._app.processEvents()
        canvas.set_annotations([])
        canvas._position_ms = 0  # pylint: disable=protected-access
        canvas._finalize_annotation(Tool.RECT, 10.0, 20.0, 100.0, 60.0)  # pylint: disable=protected-access

        self.assertEqual(len(canvas.annotations()), 1)
        annotation = canvas.annotations()[0]
        item = canvas._visible_items[annotation.annotation_id]  # pylint: disable=protected-access
        self.assertTrue(item.isSelected())

    def test_resize_overlay_appears_for_selected_rect(self) -> None:
        """
        Ensures Select mode shows resize handles for one selected rectangle.
        """

        canvas = VideoCanvas()
        canvas.resize(640, 480)
        canvas.set_video_size(640, 480)
        canvas.show()
        self._app.processEvents()
        annotation = self._sample_rect_annotation()
        canvas.set_annotations([annotation])
        canvas.set_tool(Tool.SELECT)

        item = canvas._visible_items[annotation.annotation_id]  # pylint: disable=protected-access
        item.setSelected(True)
        canvas._on_selection_changed()  # pylint: disable=protected-access

        self.assertIsNotNone(canvas._resize_overlay_item)  # pylint: disable=protected-access
        overlay_rect = canvas._resize_overlay_item.scene_rect()  # pylint: disable=protected-access
        self.assertAlmostEqual(overlay_rect.x(), 40.0, delta=0.5)
        self.assertAlmostEqual(overlay_rect.y(), 30.0, delta=0.5)
        self.assertAlmostEqual(overlay_rect.width(), 120.0, delta=0.5)
        self.assertAlmostEqual(overlay_rect.height(), 80.0, delta=0.5)

    def test_delete_key_removes_selected_annotation(self) -> None:
        """
        Ensures Delete removes selected annotations from the shared model list.
        """

        canvas = VideoCanvas()
        canvas.resize(640, 480)
        canvas.set_video_size(640, 480)
        canvas.show()
        self._app.processEvents()
        annotation = self._sample_rect_annotation()
        canvas.set_annotations([annotation])
        canvas.set_tool(Tool.SELECT)

        item = canvas._visible_items[annotation.annotation_id]  # pylint: disable=protected-access
        item.setSelected(True)
        canvas.setFocus()

        deleted = canvas.delete_selected_annotations()
        self.assertTrue(deleted)
        self.assertEqual(canvas.annotations(), [])

    def test_delete_key_ignores_unselected_annotations(self) -> None:
        """
        Ensures Delete does nothing when no annotation is selected.
        """

        canvas = VideoCanvas()
        canvas.resize(640, 480)
        canvas.set_video_size(640, 480)
        canvas.show()
        self._app.processEvents()
        annotation = self._sample_rect_annotation()
        canvas.set_annotations([annotation])
        canvas.set_tool(Tool.SELECT)

        deleted = canvas.delete_selected_annotations()
        self.assertFalse(deleted)
        self.assertEqual(len(canvas.annotations()), 1)

    def _sample_ellipse_annotation(self) -> VideoAnnotationModel:
        """
        Builds one visible ellipse annotation at the current playhead.

        Returns:
            VideoAnnotationModel: Sample ellipse annotation model.
        """

        return VideoAnnotationModel(
            annotation_type=Tool.ELLIPSE,
            start_ms=0,
            end_ms=5000,
            x=200.0,
            y=120.0,
            width=90.0,
            height=70.0,
            stroke_rgba=[52, 152, 219, 255],
            fill_rgba=[52, 152, 219, 70],
            stroke_width=3.0,
            text="",
            font_size=16,
            font_family="",
            font_bold=False,
            font_italic=False,
            font_underline=False,
            payload={},
        )

    def test_second_drawn_annotation_replaces_selection(self) -> None:
        """
        Ensures drawing a second shape selects it instead of keeping the first.
        """

        canvas = VideoCanvas()
        canvas.resize(640, 480)
        canvas.set_video_size(640, 480)
        canvas.show()
        self._app.processEvents()
        canvas.set_annotations([])
        canvas._position_ms = 0  # pylint: disable=protected-access

        canvas._finalize_annotation(Tool.RECT, 40.0, 30.0, 120.0, 80.0)  # pylint: disable=protected-access
        first = canvas.annotations()[0]
        canvas._finalize_annotation(Tool.ELLIPSE, 200.0, 120.0, 90.0, 70.0)  # pylint: disable=protected-access
        second = canvas.annotations()[1]

        self.assertTrue(canvas._visible_items[second.annotation_id].isSelected())  # pylint: disable=protected-access
        self.assertFalse(canvas._visible_items[first.annotation_id].isSelected())  # pylint: disable=protected-access

    def test_select_click_switches_active_annotation(self) -> None:
        """
        Ensures clicking another annotation selects it and shows its overlay.
        """

        canvas = VideoCanvas()
        canvas.resize(640, 480)
        canvas.set_video_size(640, 480)
        canvas.show()
        self._app.processEvents()
        rect = self._sample_rect_annotation()
        ellipse = self._sample_ellipse_annotation()
        canvas.set_annotations([rect, ellipse])
        canvas.set_tool(Tool.SELECT)

        rect_item = canvas._visible_items[rect.annotation_id]  # pylint: disable=protected-access
        ellipse_item = canvas._visible_items[ellipse.annotation_id]  # pylint: disable=protected-access
        rect_item.setSelected(True)
        canvas._on_selection_changed()  # pylint: disable=protected-access

        center = ellipse_item.mapToScene(ellipse_item.boundingRect().center())
        view_pos = canvas.mapFromScene(center)
        if hasattr(view_pos, "toPoint"):
            view_pos = view_pos.toPoint()
        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            view_pos,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        canvas._handle_select_mouse_press(event)  # pylint: disable=protected-access

        self.assertFalse(rect_item.isSelected())
        self.assertTrue(ellipse_item.isSelected())
        self.assertIs(canvas._resize_overlay_target, ellipse_item)  # pylint: disable=protected-access

    def test_delete_removes_currently_selected_annotation(self) -> None:
        """
        Ensures Delete removes the annotation that is actually selected.
        """

        canvas = VideoCanvas()
        canvas.resize(640, 480)
        canvas.set_video_size(640, 480)
        canvas.show()
        self._app.processEvents()
        rect = self._sample_rect_annotation()
        ellipse = self._sample_ellipse_annotation()
        canvas.set_annotations([rect, ellipse])
        canvas.set_tool(Tool.SELECT)

        ellipse_item = canvas._visible_items[ellipse.annotation_id]  # pylint: disable=protected-access
        canvas._scene.clearSelection()
        ellipse_item.setSelected(True)
        canvas._on_selection_changed()  # pylint: disable=protected-access

        deleted = canvas.delete_selected_annotations()
        self.assertTrue(deleted)
        remaining_ids = {annotation.annotation_id for annotation in canvas.annotations()}
        self.assertIn(rect.annotation_id, remaining_ids)
        self.assertNotIn(ellipse.annotation_id, remaining_ids)

    def test_poly_tools_enable_mouse_tracking_for_rubber_band(self) -> None:
        """
        Ensures bent-arrow/polyline/polygon tools track the cursor between clicks.
        """

        canvas = VideoCanvas()
        for tool in (Tool.BENT_ARROW, Tool.POLYLINE, Tool.POLYGON):
            with self.subTest(tool=tool):
                canvas.set_tool(tool)
                self.assertTrue(canvas.hasMouseTracking())
        canvas.set_tool(Tool.SELECT)
        self.assertFalse(canvas.hasMouseTracking())

    def test_poly_preview_follows_cursor_while_drawing(self) -> None:
        """
        Ensures the video poly rubber-band includes the live cursor point.
        """

        from src.shape_items import PolyPathItem

        canvas = VideoCanvas()
        canvas.set_tool(Tool.BENT_ARROW)
        canvas._append_poly_point(QPointF(20.0, 30.0))  # pylint: disable=protected-access
        self.assertIsNotNone(canvas._poly_preview)  # pylint: disable=protected-access
        preview = canvas._poly_preview  # pylint: disable=protected-access
        assert isinstance(preview, PolyPathItem)
        self.assertGreaterEqual(preview.zValue(), 50.0)

        canvas._update_poly_preview(QPointF(120.0, 80.0))  # pylint: disable=protected-access
        self.assertEqual(
            preview.points(),
            [QPointF(20.0, 30.0), QPointF(120.0, 80.0)],
        )
        # Committed vertices stay unchanged until the next click.
        self.assertEqual(canvas._poly_points, [QPointF(20.0, 30.0)])  # pylint: disable=protected-access

        move = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(50.0, 40.0),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        canvas.mouseMoveEvent(move)
        self.assertEqual(len(preview.points()), 2)
        self.assertEqual(preview.points()[0], QPointF(20.0, 30.0))
