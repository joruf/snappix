"""
Tests for the freehand stroke tool: geometry, non-destructive smoothing, and the
object behaviour that separates it from the raster brush.

The geometry half runs without Qt so the smoothing maths can be checked on its
own; the rest uses the offscreen platform like the other editor tests.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.freehand import (
    FREEHAND_MIN_POINT_DISTANCE,
    average_window,
    MAX_SMOOTHING_PASSES,
    SMOOTHING_DEFAULT,
    clamp_smoothing,
    path_length,
    should_append_point,
    smooth_points,
    smoothing_passes,
    thin_points,
)

try:
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QColor, QImage, QPixmap

    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False

# A zigzag: every inner point is a hard corner, which is what smoothing rounds.
ZIGZAG = [(0.0, 0.0), (10.0, 20.0), (20.0, 0.0), (30.0, 20.0), (40.0, 0.0)]


class TestSmoothingGeometry(unittest.TestCase):
    """
    Verifies the smoothing maths without touching Qt.
    """

    def test_zero_amount_returns_the_recording(self) -> None:
        """
        Ensures the slider at 0 shows exactly what was drawn.
        """

        self.assertEqual(smooth_points(ZIGZAG, 0.0), ZIGZAG)

    def test_endpoints_never_move(self) -> None:
        """
        Ensures a smoothed stroke still starts and ends where it was drawn.
        """

        for amount in (0.25, 0.5, 1.0):
            smoothed = smooth_points(ZIGZAG, amount)
            self.assertEqual(smoothed[0], ZIGZAG[0], f"start moved at {amount}")
            self.assertEqual(smoothed[-1], ZIGZAG[-1], f"end moved at {amount}")

    def test_more_smoothing_shortens_the_path(self) -> None:
        """
        Ensures the slider has a visible, non-reversing effect.

        Smoothing pulls the detours out of a stroke, so the path gets shorter.
        A five-point sample saturates immediately, so this uses a stroke of the
        length a real drag produces; equal steps are allowed, longer ones are
        not.
        """

        shaky = [(float(i), 8.0 if i % 3 == 0 else -8.0) for i in range(60)]
        lengths = [path_length(smooth_points(shaky, a)) for a in (0.0, 0.25, 0.5, 1.0)]

        for previous, following in zip(lengths, lengths[1:]):
            self.assertLessEqual(following, previous, f"got longer: {lengths}")
        self.assertLess(lengths[-1], lengths[0] * 0.5, f"barely any effect: {lengths}")

    def test_amount_is_clamped(self) -> None:
        """
        Ensures a stray value cannot produce an endless smoothing run.
        """

        self.assertEqual(clamp_smoothing(-5.0), 0.0)
        self.assertEqual(clamp_smoothing(17.0), 1.0)
        self.assertEqual(clamp_smoothing("nonsense"), SMOOTHING_DEFAULT)
        self.assertEqual(smoothing_passes(1.0), MAX_SMOOTHING_PASSES)
        self.assertEqual(smoothing_passes(0.0), 0)

    def test_short_and_empty_strokes_survive(self) -> None:
        """
        Ensures a dot or a two-point flick cannot crash the smoothing.
        """

        self.assertEqual(smooth_points([], 1.0), [])
        self.assertEqual(smooth_points([(1.0, 1.0)], 1.0), [(1.0, 1.0)])
        self.assertEqual(
            smooth_points([(0.0, 0.0), (5.0, 5.0)], 1.0),
            [(0.0, 0.0), (5.0, 5.0)],
        )

    def test_shake_is_damped_not_just_corners_rounded(self) -> None:
        """
        Ensures an unsteady hand actually gets straightened.

        Corner cutting alone rounds each spike but keeps its height, so the
        stroke still looks shaky. The averaging pass is what removes the
        wobble, measured here as the deviation from the straight baseline the
        user was aiming for.
        """

        shaky = [(float(i), 7.0 if i % 3 == 0 else -7.0) for i in range(60)]

        def wobble(points):
            """Returns the mean distance from the intended straight line."""
            return sum(abs(y) for _x, y in points) / len(points)

        raw = wobble(shaky)
        mild = wobble(smooth_points(shaky, 0.3))
        strong = wobble(smooth_points(shaky, 1.0))

        self.assertLess(mild, raw * 0.75, f"barely damped: {raw} -> {mild}")
        self.assertLess(strong, mild, f"not monotonic: {mild} -> {strong}")

    def test_averaging_window_grows_with_the_amount(self) -> None:
        """
        Ensures the slider maps onto a widening window.
        """

        self.assertEqual(average_window(0.0), 1)
        self.assertGreater(average_window(1.0), average_window(0.3))
        self.assertEqual(average_window(1.0) % 2, 1, "window must stay odd")

    def test_repeated_smoothing_of_the_recording_is_stable(self) -> None:
        """
        Ensures sweeping the slider does not erode the stroke.

        Smoothing always starts from the recording, so asking for the same
        amount twice must give the same answer -- unlike applying the operation
        on top of its own result.
        """

        first = smooth_points(ZIGZAG, 0.5)
        second = smooth_points(ZIGZAG, 0.5)
        self.assertEqual(first, second)
        self.assertNotEqual(smooth_points(first, 0.5), first)


class TestPointThinning(unittest.TestCase):
    """
    Verifies the sampling filter used while a stroke is drawn.
    """

    def test_points_closer_than_one_step_are_dropped(self) -> None:
        """
        Ensures a drag does not record thousands of near-identical points.
        """

        crowded = [(0.0, 0.0), (0.4, 0.0), (0.8, 0.0), (1.2, 0.0), (30.0, 0.0)]
        self.assertEqual(thin_points(crowded), [(0.0, 0.0), (30.0, 0.0)])

    def test_the_last_point_is_always_kept(self) -> None:
        """
        Ensures the stroke ends where the pointer was released, even after a
        short final move.
        """

        trailing = [(0.0, 0.0), (30.0, 0.0), (30.4, 0.0)]
        self.assertEqual(thin_points(trailing)[-1], (30.4, 0.0))

    def test_shape_survives_thinning(self) -> None:
        """
        Ensures well-spaced points are left alone.
        """

        spaced = [(0.0, 0.0), (10.0, 0.0), (20.0, 10.0), (30.0, 0.0)]
        self.assertEqual(thin_points(spaced), spaced)

    def test_first_point_is_always_accepted(self) -> None:
        """
        Ensures a stroke can start anywhere.
        """

        self.assertTrue(should_append_point([], (5.0, 5.0)))
        self.assertFalse(
            should_append_point([(5.0, 5.0)], (5.0 + FREEHAND_MIN_POINT_DISTANCE / 4, 5.0))
        )


def _pixmap(width: int, height: int) -> "QPixmap":
    """
    Builds a plain canvas background.

    Args:
        width: Image width.
        height: Image height.

    Returns:
        QPixmap: Filled pixmap.
    """

    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor(240, 240, 240))
    return QPixmap.fromImage(image)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestFreehandItem(unittest.TestCase):
    """
    Verifies the scene item: smoothing is display-only, no vertex handles.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def _item(self, kind: str = "freehand"):
        """
        Builds a multi-point item over the zigzag.

        Args:
            kind: Annotation type.

        Returns:
            PolyPathItem: Item under test.
        """

        from src.shape_items import PolyPathItem

        return PolyPathItem(kind, [QPointF(x, y) for x, y in ZIGZAG])

    def test_freehand_is_a_recognized_poly_type(self) -> None:
        """
        Ensures the shared poly machinery accepts the new type, which is what
        gives it selection, moving, deleting, and saving for free.
        """

        from src.shape_items import SHAPE_POLY_TYPES

        self.assertIn("freehand", SHAPE_POLY_TYPES)

    def test_smoothing_never_touches_the_recording(self) -> None:
        """
        Ensures the slider is non-destructive.
        """

        item = self._item()
        recorded = item.points()

        item.set_smoothing(1.0)
        self.assertEqual(item.points(), recorded)
        self.assertGreater(len(item.display_points()), len(recorded))

        item.set_smoothing(0.0)
        self.assertEqual(item.display_points(), recorded)

    def test_only_freehand_carries_smoothing(self) -> None:
        """
        Ensures the click-placed poly shapes are unaffected.
        """

        self.assertTrue(self._item().is_freehand())
        polyline = self._item("polyline")
        self.assertFalse(polyline.is_freehand())
        self.assertEqual(polyline.smoothing(), 0.0)
        self.assertEqual(polyline.display_points(), polyline.points())

    def test_freehand_shows_no_vertex_handles(self) -> None:
        """
        Ensures a recorded stroke is edited as a whole.

        Hundreds of handles would bury the stroke, and no single recorded point
        is meaningful to drag.
        """

        self.assertIsNone(self._item().vertex_at(QPointF(0.0, 0.0)))
        self.assertEqual(self._item("polyline").vertex_at(QPointF(0.0, 0.0)), 0)

    def test_default_smoothing_is_applied_to_new_strokes(self) -> None:
        """
        Ensures a fresh stroke already looks smoothed.
        """

        self.assertEqual(self._item().smoothing(), SMOOTHING_DEFAULT)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestFreehandDrawing(unittest.TestCase):
    """
    Verifies drawing, selecting, moving, and deleting in the image editor.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def _canvas_with_stroke(self, steps: int = 40):
        """
        Draws one freehand stroke on a fresh canvas.

        Args:
            steps: Number of sampled positions.

        Returns:
            EditorCanvas: Canvas holding the committed stroke.
        """

        from src.editor_canvas import EditorCanvas, Tool

        canvas = EditorCanvas()
        self.addCleanup(canvas.close)
        canvas.set_screenshot(_pixmap(400, 300))
        canvas.resize(400, 300)
        canvas.set_tool(Tool.FREEHAND)
        canvas._begin_freehand_stroke(QPointF(20.0, 20.0))
        for index in range(1, steps):
            canvas._extend_freehand_stroke(
                QPointF(20.0 + index * 4.0, 20.0 + (index % 5) * 8.0)
            )
        canvas._finalize_poly_draw()
        self._app.processEvents()
        return canvas

    def test_dragging_produces_one_freehand_annotation(self) -> None:
        """
        Ensures a drag becomes a single object, not a pixel stroke.
        """

        annotations = self._canvas_with_stroke().collect_annotations()
        self.assertEqual(len(annotations), 1)
        self.assertEqual(annotations[0].annotation_type, "freehand")
        self.assertGreater(len(annotations[0].payload["points"]), 5)

    def test_a_tap_without_movement_creates_nothing(self) -> None:
        """
        Ensures a stray click does not litter the canvas with dots.
        """

        from src.editor_canvas import EditorCanvas, Tool

        canvas = EditorCanvas()
        self.addCleanup(canvas.close)
        canvas.set_screenshot(_pixmap(400, 300))
        canvas.set_tool(Tool.FREEHAND)
        canvas._begin_freehand_stroke(QPointF(20.0, 20.0))
        canvas._finalize_poly_draw()
        self._app.processEvents()

        self.assertEqual(canvas.collect_annotations(), [])

    def test_the_new_stroke_is_selected_and_movable(self) -> None:
        """
        Ensures the stroke behaves like any other annotation right away.
        """

        canvas = self._canvas_with_stroke()
        selected = canvas.selected_freehand_items()
        self.assertEqual(len(selected), 1)

        before = canvas.collect_annotations()[0]
        selected[0].moveBy(25.0, 15.0)
        self._app.processEvents()
        after = canvas.collect_annotations()[0]

        self.assertAlmostEqual(after.x, before.x + 25.0, delta=1.0)
        self.assertAlmostEqual(after.y, before.y + 15.0, delta=1.0)

    def test_the_stroke_can_be_deleted(self) -> None:
        """
        Ensures deleting works, which the raster brush cannot offer.
        """

        from PySide6.QtCore import Qt
        from PySide6.QtGui import QKeyEvent

        canvas = self._canvas_with_stroke()
        canvas.keyPressEvent(
            QKeyEvent(
                QKeyEvent.Type.KeyPress,
                Qt.Key.Key_Delete,
                Qt.KeyboardModifier.NoModifier,
            )
        )
        self._app.processEvents()
        self.assertEqual(canvas.collect_annotations(), [])

    def test_recorded_points_are_thinned_while_drawing(self) -> None:
        """
        Ensures crowded pointer positions do not all end up in the annotation.
        """

        from src.editor_canvas import EditorCanvas, Tool

        canvas = EditorCanvas()
        self.addCleanup(canvas.close)
        canvas.set_screenshot(_pixmap(400, 300))
        canvas.set_tool(Tool.FREEHAND)
        canvas._begin_freehand_stroke(QPointF(20.0, 20.0))
        for _ in range(50):
            # Same spot every time: a real drag reports this while the hand rests.
            canvas._extend_freehand_stroke(QPointF(20.2, 20.2))
        self.assertEqual(len(canvas._poly_draw_points), 1)

    def test_stroke_uses_the_active_stroke_color_and_width(self) -> None:
        """
        Ensures the stroke follows the shared style like every other tool.
        """

        canvas = self._canvas_with_stroke()
        annotation = canvas.collect_annotations()[0]
        self.assertEqual(len(annotation.stroke_rgba), 4)
        self.assertGreater(annotation.stroke_width, 0.0)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestSmoothingSlider(unittest.TestCase):
    """
    Verifies the Edit-panel slider and its history behaviour.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def _editor_with_stroke(self):
        """
        Opens an editor holding one selected freehand stroke.

        Returns:
            EditorWindow: Editor under test.
        """

        from src.editor_canvas import Tool
        from src.editor_window import EditorWindow

        editor = EditorWindow(_pixmap(400, 300))
        self.addCleanup(editor.close)
        editor.show()
        self._app.processEvents()

        canvas = editor.canvas
        canvas.set_tool(Tool.FREEHAND)
        canvas._begin_freehand_stroke(QPointF(20.0, 20.0))
        for index in range(1, 40):
            canvas._extend_freehand_stroke(
                QPointF(20.0 + index * 4.0, 20.0 + (index % 5) * 8.0)
            )
        canvas._finalize_poly_draw()
        self._app.processEvents()
        return editor

    def test_slider_appears_for_a_selected_stroke(self) -> None:
        """
        Ensures the control shows up where the other shape controls live.
        """

        editor = self._editor_with_stroke()
        self.assertTrue(editor.style_smoothing_slider.isVisible())

    def test_slider_shows_the_strokes_current_amount(self) -> None:
        """
        Ensures selecting a stroke does not silently reset its smoothing.
        """

        editor = self._editor_with_stroke()
        self.assertEqual(
            editor.style_smoothing_slider.value(),
            int(round(SMOOTHING_DEFAULT * 100)),
        )

    def test_dragging_the_slider_updates_the_stroke_live(self) -> None:
        """
        Ensures the preview is immediate and leaves the recording intact.
        """

        editor = self._editor_with_stroke()
        item = editor.canvas.selected_freehand_items()[0]
        recorded = len(item.points())

        editor.style_smoothing_slider.setValue(90)
        self._app.processEvents()
        self.assertGreater(len(item.display_points()), recorded)
        self.assertEqual(len(item.points()), recorded)

        editor.style_smoothing_slider.setValue(0)
        self._app.processEvents()
        self.assertEqual(len(item.display_points()), recorded)

    def test_a_slider_sweep_costs_one_history_entry(self) -> None:
        """
        Ensures sweeping the slider does not bury the undo history.

        The thickness slider writes history on every value change; doing that
        here would add one undo step per slider pixel.
        """

        editor = self._editor_with_stroke()
        before = len(editor._history)

        for value in range(10, 90, 10):
            editor.style_smoothing_slider.setValue(value)
            self._app.processEvents()
        self.assertEqual(
            len(editor._history), before, "slider drag wrote history entries"
        )

        editor.style_smoothing_slider.sliderReleased.emit()
        self._app.processEvents()
        self.assertEqual(len(editor._history), before + 1)

    def test_slider_is_hidden_for_other_annotation_types(self) -> None:
        """
        Ensures the control does not clutter the panel for shapes that have no
        recorded points.
        """

        editor = self._editor_with_stroke()
        editor.canvas._scene.clearSelection()
        self._app.processEvents()
        self.assertFalse(editor.style_smoothing_slider.isVisible())


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestFreehandToolLock(unittest.TestCase):
    """
    Verifies the tool draws once and only stays active when really locked.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def _editor(self):
        """
        Opens an editor window.

        Returns:
            EditorWindow: Editor under test.
        """

        from src.editor_window import EditorWindow

        editor = EditorWindow(_pixmap(500, 300))
        self.addCleanup(editor.close)
        editor.resize(1100, 700)
        editor.show()
        self._app.processEvents()
        return editor

    def _draw(self, canvas) -> None:
        """
        Draws one stroke on the canvas.

        Args:
            canvas: Target canvas.

        Returns:
            None
        """

        canvas._begin_freehand_stroke(QPointF(30.0, 60.0))
        for index in range(1, 40):
            canvas._extend_freehand_stroke(
                QPointF(30.0 + index * 4.0, 60.0 + (index % 5) * 8.0)
            )
        canvas._finalize_poly_draw()
        self._app.processEvents()
        self._app.processEvents()

    def test_a_single_click_draws_one_stroke_then_returns_to_select(self) -> None:
        """
        Ensures the tool is not permanently armed after one click.

        Left active, the next click on the canvas starts another stroke instead
        of selecting the one just drawn -- which also hides the Smoothing
        control, because that follows the selection.
        """

        from src.editor_canvas import Tool

        editor = self._editor()
        editor._on_tool_button_clicked(Tool.FREEHAND)
        self._app.processEvents()
        self.assertEqual(editor._one_shot_tool, Tool.FREEHAND)

        self._draw(editor.canvas)
        self.assertEqual(editor.canvas._tool, Tool.SELECT)

    def test_the_finished_stroke_stays_selected_with_its_slider(self) -> None:
        """
        Ensures the smoothing control is reachable right after drawing.
        """

        from src.editor_canvas import Tool

        editor = self._editor()
        editor._on_tool_button_clicked(Tool.FREEHAND)
        self._draw(editor.canvas)

        self.assertEqual(len(editor.canvas.selected_freehand_items()), 1)
        self.assertTrue(editor.style_smoothing_slider.isVisible())

    def test_locking_keeps_the_tool_for_repeated_strokes(self) -> None:
        """
        Ensures a real lock (double-click) still allows drawing several strokes.
        """

        from src.editor_canvas import Tool

        editor = self._editor()
        editor._toggle_tool_lock(Tool.FREEHAND)
        self._app.processEvents()
        self.assertEqual(editor._locked_tool, Tool.FREEHAND)

        self._draw(editor.canvas)
        self.assertEqual(editor.canvas._tool, Tool.FREEHAND)
        self._draw(editor.canvas)
        self.assertEqual(editor.canvas._tool, Tool.FREEHAND)
        self.assertEqual(len(editor.canvas.collect_annotations()), 2)

    def test_unlocking_returns_to_select(self) -> None:
        """
        Ensures the lock can be released the same way it was set.
        """

        from src.editor_canvas import Tool

        editor = self._editor()
        editor._toggle_tool_lock(Tool.FREEHAND)
        editor._toggle_tool_lock(Tool.FREEHAND)
        self._app.processEvents()

        self.assertIsNone(editor._locked_tool)
        self.assertEqual(editor.canvas._tool, Tool.SELECT)

    def test_both_editors_treat_the_tool_as_lockable(self) -> None:
        """
        Ensures the video editor behaves the same.
        """

        from src.editor_canvas import Tool
        from src.video_vector_toolbar import _LOCKABLE_TOOLS, _ONE_SHOT_ACTIONS

        self.assertIn(Tool.FREEHAND, _LOCKABLE_TOOLS)
        self.assertEqual(_ONE_SHOT_ACTIONS[Tool.FREEHAND], "Draw freehand")


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestFreehandPersistence(unittest.TestCase):
    """
    Verifies that strokes and their smoothing survive save and load.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def _project_with_stroke(self, smoothing: float):
        """
        Builds a project model holding one freehand annotation.

        Args:
            smoothing: Amount to store.

        Returns:
            ProjectModel: Project ready to save.
        """

        from src.models import AnnotationModel
        from src.storage import build_project_model

        return build_project_model(
            _pixmap(200, 120),
            [
                AnnotationModel(
                    annotation_type="freehand",
                    x=0.0,
                    y=0.0,
                    width=40.0,
                    height=20.0,
                    stroke_rgba=[255, 0, 0, 255],
                    fill_rgba=[0, 0, 0, 0],
                    stroke_width=3.0,
                    payload={
                        "points": [list(point) for point in ZIGZAG],
                        "smoothing": smoothing,
                    },
                )
            ],
        )

    def test_recording_and_amount_survive_a_round_trip(self) -> None:
        """
        Ensures the slider still works after reopening a project.
        """

        from src.storage import load_project, save_project

        with TemporaryDirectory() as directory:
            path = Path(directory) / "stroke.sfp"
            save_project(path, self._project_with_stroke(0.75))
            loaded = load_project(path)

        annotation = loaded.annotations[0]
        self.assertEqual(annotation.annotation_type, "freehand")
        self.assertEqual(len(annotation.payload["points"]), len(ZIGZAG))
        self.assertAlmostEqual(annotation.payload["smoothing"], 0.75, places=4)

    def test_a_file_without_smoothing_still_loads(self) -> None:
        """
        Ensures a project written before this feature existed opens cleanly.
        """

        from src.annotation_items import add_annotation_to_scene
        from src.models import AnnotationModel
        from PySide6.QtWidgets import QGraphicsScene

        annotation = AnnotationModel(
            annotation_type="freehand",
            x=0.0,
            y=0.0,
            width=40.0,
            height=20.0,
            stroke_rgba=[0, 0, 0, 255],
            fill_rgba=[0, 0, 0, 0],
            stroke_width=2.0,
            payload={"points": [list(point) for point in ZIGZAG]},
        )
        scene = QGraphicsScene()
        item = add_annotation_to_scene(scene, annotation)

        self.assertIsNotNone(item)
        self.assertEqual(item.smoothing(), SMOOTHING_DEFAULT)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestVideoEditorParity(unittest.TestCase):
    """
    Verifies the tool reached the video editor too.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def test_the_toolbar_button_is_shared_by_both_editors(self) -> None:
        """
        Ensures both editors offer the tool from one definition.
        """

        from src.editor_canvas import Tool
        from src.tool_categories import SHARED_SHAPE_TOOL_CATEGORIES

        lines = [group for group in SHARED_SHAPE_TOOL_CATEGORIES if group[0] == "Lines"]
        tools = [tool for tool, _label in lines[0][1]]
        self.assertIn(Tool.FREEHAND, tools)

    def test_video_annotations_of_this_type_are_rebuilt(self) -> None:
        """
        Ensures a saved video stroke reappears with its smoothing.

        The video canvas decided "is this multi-point?" from the *tool* set,
        which cannot contain freehand because freehand is drawn by dragging.
        """

        from src.video_canvas import build_annotation_item
        from src.video_models import VideoAnnotationModel

        annotation = VideoAnnotationModel(
            annotation_type="freehand",
            start_ms=0,
            end_ms=2000,
            x=0.0,
            y=0.0,
            width=40.0,
            height=20.0,
            stroke_rgba=[0, 0, 255, 255],
            fill_rgba=[0, 0, 0, 0],
            stroke_width=3.0,
            payload={
                "points": [list(point) for point in ZIGZAG],
                "smoothing": 0.6,
            },
        )
        item = build_annotation_item(annotation)

        self.assertIsNotNone(item)
        self.assertTrue(item.is_freehand())
        self.assertAlmostEqual(item.smoothing(), 0.6, places=4)

    def test_video_toolbar_exposes_the_same_slider(self) -> None:
        """
        Ensures the Edit panel matches between the editors.
        """

        from src.video_vector_toolbar import _SHAPE_SMOOTHING_SELECTION_TYPES

        self.assertIn("freehand", _SHAPE_SMOOTHING_SELECTION_TYPES)


if __name__ == "__main__":
    unittest.main()
