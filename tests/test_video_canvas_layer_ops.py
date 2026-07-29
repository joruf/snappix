"""
Unit tests for VideoCanvas layer operations added for Image/Video editor menu
parity: duplicate, layer arrange (bring/send), and scale selection.
"""

from __future__ import annotations

import unittest

try:
    from src.editor_canvas import Tool
    from src.video_canvas import VideoCanvas
    from src.video_models import VideoAnnotationModel
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


def _rect_annotation(**overrides) -> "VideoAnnotationModel":
    """
    Builds one visible rectangle annotation, with any field overridden.

    Args:
        overrides: Field values to override on the default rectangle model.

    Returns:
        VideoAnnotationModel: Sample annotation model.
    """

    defaults = dict(
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
    defaults.update(overrides)
    return VideoAnnotationModel(**defaults)


def _make_canvas() -> "VideoCanvas":
    """
    Builds a ready-to-use VideoCanvas widget for headless tests.

    Returns:
        VideoCanvas: Configured canvas instance.
    """

    canvas = VideoCanvas()
    canvas.resize(640, 480)
    canvas.set_video_size(640, 480)
    canvas.show()
    canvas.set_tool(Tool.SELECT)
    return canvas


def _select(canvas: "VideoCanvas", annotation: "VideoAnnotationModel") -> None:
    """
    Selects one annotation's graphics item on the canvas.

    Args:
        canvas: Video canvas under test.
        annotation: Annotation whose item should be selected.

    Returns:
        None
    """

    canvas._visible_items[annotation.annotation_id].setSelected(True)  # pylint: disable=protected-access


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for video canvas layer-op tests")
class TestVideoCanvasDuplicate(unittest.TestCase):
    """
    Verifies duplicate_selected_annotations.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = ensure_qapp()

    def test_duplicate_creates_offset_copy_and_selects_it(self) -> None:
        """
        Ensures duplicating a selected rectangle creates a new annotation
        offset by (16, 16) and leaves only the duplicate selected.
        """

        canvas = _make_canvas()
        original = _rect_annotation()
        canvas.set_annotations([original])
        _select(canvas, original)

        result = canvas.duplicate_selected_annotations()

        self.assertTrue(result)
        self.assertEqual(len(canvas.annotations()), 2)
        duplicate = next(a for a in canvas.annotations() if a.annotation_id != original.annotation_id)
        self.assertEqual(duplicate.x, original.x + 16.0)
        self.assertEqual(duplicate.y, original.y + 16.0)
        self.assertEqual(duplicate.width, original.width)
        self.assertTrue(canvas._visible_items[duplicate.annotation_id].isSelected())  # pylint: disable=protected-access
        self.assertFalse(canvas._visible_items[original.annotation_id].isSelected())  # pylint: disable=protected-access

    def test_duplicate_without_selection_is_a_no_op(self) -> None:
        """
        Ensures duplicating with nothing selected changes nothing.
        """

        canvas = _make_canvas()
        canvas.set_annotations([_rect_annotation()])

        result = canvas.duplicate_selected_annotations()

        self.assertFalse(result)
        self.assertEqual(len(canvas.annotations()), 1)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for video canvas layer-op tests")
class TestVideoCanvasLayerArrange(unittest.TestCase):
    """
    Verifies bring/send forward/backward/front/back reorder self._annotations,
    which drives both live paint order and export compositing order.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = ensure_qapp()

    def _three_stacked_annotations(self, canvas) -> list:
        bottom = _rect_annotation(x=0.0)
        middle = _rect_annotation(x=10.0)
        top = _rect_annotation(x=20.0)
        canvas.set_annotations([bottom, middle, top])
        return [bottom, middle, top]

    def test_bring_forward_moves_one_step_toward_front(self) -> None:
        """
        Ensures Bring Forward swaps the selected (middle) item with its
        immediate successor, moving it one step closer to the front (end of list).
        """

        canvas = _make_canvas()
        bottom, middle, top = self._three_stacked_annotations(canvas)
        _select(canvas, middle)

        changed = canvas.bring_selected_forward()

        self.assertTrue(changed)
        self.assertEqual(
            [a.annotation_id for a in canvas.annotations()],
            [bottom.annotation_id, top.annotation_id, middle.annotation_id],
        )

    def test_send_backward_moves_one_step_toward_back(self) -> None:
        """
        Ensures Send Backward swaps the selected (middle) item with its
        immediate predecessor, moving it one step closer to the back.
        """

        canvas = _make_canvas()
        bottom, middle, top = self._three_stacked_annotations(canvas)
        _select(canvas, middle)

        changed = canvas.send_selected_backward()

        self.assertTrue(changed)
        self.assertEqual(
            [a.annotation_id for a in canvas.annotations()],
            [middle.annotation_id, bottom.annotation_id, top.annotation_id],
        )

    def test_bring_to_front_moves_selection_to_the_end(self) -> None:
        """
        Ensures Bring to Front moves the selected (bottom) item to the very
        end of the annotation list (painted last / on top).
        """

        canvas = _make_canvas()
        bottom, middle, top = self._three_stacked_annotations(canvas)
        _select(canvas, bottom)

        changed = canvas.bring_selected_to_front()

        self.assertTrue(changed)
        self.assertEqual(
            [a.annotation_id for a in canvas.annotations()],
            [middle.annotation_id, top.annotation_id, bottom.annotation_id],
        )

    def test_send_to_back_moves_selection_to_the_start(self) -> None:
        """
        Ensures Send to Back moves the selected (top) item to the very start
        of the annotation list (painted first / at the bottom).
        """

        canvas = _make_canvas()
        bottom, middle, top = self._three_stacked_annotations(canvas)
        _select(canvas, top)

        changed = canvas.send_selected_to_back()

        self.assertTrue(changed)
        self.assertEqual(
            [a.annotation_id for a in canvas.annotations()],
            [top.annotation_id, bottom.annotation_id, middle.annotation_id],
        )

    def test_bring_forward_already_at_front_is_a_no_op(self) -> None:
        """
        Ensures Bring Forward on the frontmost item reports no change.
        """

        canvas = _make_canvas()
        _bottom, _middle, top = self._three_stacked_annotations(canvas)
        _select(canvas, top)

        changed = canvas.bring_selected_forward()

        self.assertFalse(changed)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for video canvas layer-op tests")
class TestVideoCanvasResizeSelection(unittest.TestCase):
    """
    Verifies resize_selected_annotations for both rect-style and
    point-list-style (polygon) annotations.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = ensure_qapp()

    def test_scale_up_grows_rect_around_its_center(self) -> None:
        """
        Ensures scaling up keeps the rectangle's center fixed while growing
        width/height by the given factor.
        """

        canvas = _make_canvas()
        annotation = _rect_annotation(x=100.0, y=100.0, width=40.0, height=20.0)
        canvas.set_annotations([annotation])
        _select(canvas, annotation)
        center_x = annotation.x + annotation.width / 2.0
        center_y = annotation.y + annotation.height / 2.0

        changed = canvas.resize_selected_annotations(2.0)

        self.assertTrue(changed)
        updated = canvas.annotations()[0]
        self.assertAlmostEqual(updated.width, 80.0)
        self.assertAlmostEqual(updated.height, 40.0)
        self.assertAlmostEqual(updated.x + updated.width / 2.0, center_x)
        self.assertAlmostEqual(updated.y + updated.height / 2.0, center_y)

    def test_scale_down_shrinks_polygon_points_around_their_center(self) -> None:
        """
        Ensures scaling a polygon rescales its stored point list around the
        polygon's own bounding-box center, not just the redundant x/y/width/height fields.
        """

        canvas = _make_canvas()
        points = [[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]]
        annotation = _rect_annotation(
            annotation_type=Tool.POLYGON,
            x=0.0,
            y=0.0,
            width=100.0,
            height=100.0,
            payload={"points": points},
        )
        canvas.set_annotations([annotation])
        _select(canvas, annotation)

        changed = canvas.resize_selected_annotations(0.5)

        self.assertTrue(changed)
        updated = canvas.annotations()[0]
        new_points = updated.payload["points"]
        # Original bounds were centered at (50, 50); half-scale keeps that
        # center and halves the spread.
        self.assertAlmostEqual(new_points[0][0], 25.0)
        self.assertAlmostEqual(new_points[0][1], 25.0)
        self.assertAlmostEqual(new_points[2][0], 75.0)
        self.assertAlmostEqual(new_points[2][1], 75.0)
        self.assertAlmostEqual(updated.width, 50.0)
        self.assertAlmostEqual(updated.height, 50.0)

    def test_resize_without_selection_is_a_no_op(self) -> None:
        """
        Ensures resizing with nothing selected changes nothing.
        """

        canvas = _make_canvas()
        annotation = _rect_annotation()
        canvas.set_annotations([annotation])

        changed = canvas.resize_selected_annotations(1.5)

        self.assertFalse(changed)
        self.assertEqual(canvas.annotations()[0].width, annotation.width)


if __name__ == "__main__":
    unittest.main()
