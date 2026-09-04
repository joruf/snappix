"""
Tests for how the crop frame looks and behaves.

Cropping is judged by eye, so the frame has to get out of the way of the part
being kept and make the discarded part unmistakable. The same item also serves
as the resize overlay for annotations, where a tinted interior is wanted -- so
the presentation is a mode, and these tests pin down that it stays one.
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QImage, QPixmap

    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


def _pixmap(width: int, height: int) -> "QPixmap":
    """
    Builds a plain document background.

    Args:
        width: Image width.
        height: Image height.

    Returns:
        QPixmap: Filled pixmap.
    """

    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor(235, 235, 235))
    return QPixmap.fromImage(image)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestCropFramePresentation(unittest.TestCase):
    """
    Verifies the frame drawn while cropping.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def _item(self):
        """
        Builds a crop frame in presentation mode.

        Returns:
            CropSelectionItem: Item under test.
        """

        from src.crop_item import CropSelectionItem

        item = CropSelectionItem(QRectF(0.0, 0.0, 300.0, 200.0))
        item.set_crop_presentation(True)
        return item

    def test_the_kept_area_is_not_tinted(self) -> None:
        """
        Ensures the picture inside the frame is judged unobstructed.

        A colour cast over the kept area is exactly what must not happen: it is
        the part whose colours are being assessed.
        """

        item = self._item()
        self.assertEqual(item.brush().style(), Qt.BrushStyle.NoBrush)

    def test_the_resize_overlay_keeps_its_tint(self) -> None:
        """
        Ensures the shared item still fills when used to resize annotations.
        """

        from src.crop_item import CropSelectionItem

        overlay = CropSelectionItem(QRectF(0.0, 0.0, 100.0, 80.0))
        self.assertFalse(overlay.crop_presentation())
        self.assertNotEqual(overlay.brush().style(), Qt.BrushStyle.NoBrush)

    def test_switching_back_restores_the_tint(self) -> None:
        """
        Ensures the mode is reversible rather than a one-way change.
        """

        item = self._item()
        item.set_crop_presentation(False)
        self.assertNotEqual(item.brush().style(), Qt.BrushStyle.NoBrush)

    def test_a_thirds_grid_is_drawn_inside_the_frame(self) -> None:
        """
        Ensures the composition aid appears where the composition is.
        """

        item = self._item()
        image = QImage(320, 220, QImage.Format.Format_RGB32)
        image.fill(QColor(0, 0, 0))
        self._paint(item, image)

        # A third across should carry a light vertical line; a point between
        # the thirds should not.
        on_grid = self._column_brightness(image, x=100)
        off_grid = self._column_brightness(image, x=140)
        self.assertGreater(on_grid, off_grid, "no thirds grid painted")

    def test_corners_are_marked(self) -> None:
        """
        Ensures the corners stay findable on a light picture.
        """

        item = self._item()
        image = QImage(320, 220, QImage.Format.Format_RGB32)
        image.fill(QColor(0, 0, 0))
        self._paint(item, image)

        corner = image.pixelColor(4, 1).lightness()
        middle_of_edge = image.pixelColor(150, 1).lightness()
        self.assertGreater(corner, middle_of_edge, "corner brackets missing")

    def test_the_resulting_pixel_size_is_shown(self) -> None:
        """
        Ensures the question "how much is left" is answered on screen.
        """

        item = self._item()
        item.setPos(QPointF(0.0, 60.0))
        image = QImage(340, 300, QImage.Format.Format_RGB32)
        image.fill(QColor(120, 120, 120))
        self._paint(item, image, offset=QPointF(0.0, 60.0))

        # The readout box is near-black; nothing else above the frame is.
        dark = sum(
            1
            for y in range(30, 58)
            for x in range(0, 120)
            if image.pixelColor(x, y).lightness() < 60
        )
        self.assertGreater(dark, 150, "no size readout painted")

    def test_the_readout_stays_clear_of_the_picture_when_there_is_room(self) -> None:
        """
        Ensures the readout does not cover the content it describes.

        The item's own rectangle always starts at zero, so deciding placement
        from it would push the readout inside the frame every time.
        """

        item = self._item()
        item.setPos(QPointF(0.0, 60.0))
        image = QImage(340, 300, QImage.Format.Format_RGB32)
        image.fill(QColor(120, 120, 120))
        self._paint(item, image, offset=QPointF(0.0, 60.0))

        inside_top_left = sum(
            1
            for y in range(66, 90)
            for x in range(6, 110)
            if image.pixelColor(x, y).lightness() < 60
        )
        self.assertLess(inside_top_left, 40, "readout sits on the kept area")

    def _paint(self, item, image, offset: "QPointF | None" = None) -> None:
        """
        Paints one item into an image.

        Args:
            item: Item to paint.
            image: Target image.
            offset: Optional translation applied before painting.

        Returns:
            None
        """

        from PySide6.QtGui import QPainter
        from PySide6.QtWidgets import QStyleOptionGraphicsItem

        painter = QPainter(image)
        if offset is not None:
            painter.translate(offset)
        item.paint(painter, QStyleOptionGraphicsItem(), None)
        painter.end()

    def _column_brightness(self, image, *, x: int) -> int:
        """
        Returns how much light sits in one column inside the frame.

        Args:
            image: Painted image.
            x: Column to sample.

        Returns:
            int: Summed lightness.
        """

        return sum(image.pixelColor(x, y).lightness() for y in range(40, 160))


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestCropShading(unittest.TestCase):
    """
    Verifies the area being discarded is clearly set apart.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def test_activating_the_tool_frames_the_whole_picture(self) -> None:
        """
        Ensures cropping starts from the full picture, with nothing to draw
        first.
        """

        from src.editor_canvas import EditorCanvas, Tool

        canvas = EditorCanvas()
        self.addCleanup(canvas.close)
        canvas.set_screenshot(_pixmap(480, 320))
        canvas.set_tool(Tool.CROP)

        self.assertTrue(canvas.has_pending_crop())
        self.assertEqual(
            canvas._crop_item.scene_rect(), QRectF(canvas.document_rect())
        )

    def test_the_canvas_turns_the_presentation_on(self) -> None:
        """
        Ensures the crop frame really uses the crop presentation.

        The item defaults to the tinted resize-overlay look, so forgetting to
        switch it leaves a colour cast over the very area being judged.
        """

        from src.editor_canvas import EditorCanvas, Tool

        canvas = EditorCanvas()
        self.addCleanup(canvas.close)
        canvas.set_screenshot(_pixmap(480, 320))
        canvas.set_tool(Tool.CROP)

        self.assertTrue(canvas._crop_item.crop_presentation())
        self.assertEqual(canvas._crop_item.brush().style(), Qt.BrushStyle.NoBrush)

    def test_the_handles_are_visible_without_selecting_first(self) -> None:
        """
        Ensures the frame can be grabbed straight away.
        """

        from src.editor_canvas import EditorCanvas, Tool

        canvas = EditorCanvas()
        self.addCleanup(canvas.close)
        canvas.set_screenshot(_pixmap(480, 320))
        canvas.set_tool(Tool.CROP)

        self.assertTrue(canvas._crop_item._always_show_handles)

    def test_only_the_discarded_area_is_dimmed(self) -> None:
        """
        Ensures the kept area is left at full brightness.
        """

        from src.editor_canvas import EditorCanvas, Tool

        canvas = EditorCanvas()
        self.addCleanup(canvas.close)
        canvas.set_screenshot(_pixmap(480, 320))
        canvas.set_tool(Tool.CROP)
        canvas._crop_item.setPos(QPointF(120.0, 80.0))
        canvas._crop_item.setRect(QRectF(0.0, 0.0, 240.0, 160.0))
        canvas._update_crop_shade()

        shade = canvas._crop_shade_item
        self.assertIsNotNone(shade)
        self.assertTrue(shade.path().contains(QPointF(20.0, 20.0)), "outside not dimmed")
        self.assertFalse(
            shade.path().contains(QPointF(240.0, 160.0)), "kept area dimmed"
        )

    def test_the_dimming_is_strong_enough_to_read_as_discarded(self) -> None:
        """
        Ensures the two areas are told apart at a glance.
        """

        from src.editor_canvas import CROP_SHADE_ALPHA

        self.assertGreaterEqual(CROP_SHADE_ALPHA, 140)
        self.assertLess(CROP_SHADE_ALPHA, 255, "discarded area must stay recognizable")


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestHandlesAreGrabbable(unittest.TestCase):
    """
    Verifies a click on a handle actually reaches the frame.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def test_every_handle_lies_inside_the_hit_area(self) -> None:
        """
        Ensures the handles are not holes in the item's hit shape.

        The shape is built by adding the handle rectangles and then the
        interior. With the default odd-even fill rule the two cancel wherever
        they overlap -- and the handles sit inside the frame, so each one
        became a hole and the click fell through to the picture below.
        """

        from src.crop_item import CropSelectionItem

        item = CropSelectionItem(QRectF(0.0, 0.0, 300.0, 200.0))
        item.set_crop_presentation(True)
        shape = item.shape()

        missed = [
            name
            for name, handle in item._handle_rects().items()
            if not shape.contains(handle.center())
        ]
        self.assertEqual(missed, [], "handles missing from the hit area")

    def test_the_resize_overlay_handles_are_grabbable_too(self) -> None:
        """
        Ensures annotations can still be resized; the same shape is used there.
        """

        from src.crop_item import CropSelectionItem

        overlay = CropSelectionItem(QRectF(0.0, 0.0, 120.0, 90.0))
        shape = overlay.shape()

        missed = [
            name
            for name, handle in overlay._handle_rects().items()
            if not shape.contains(handle.center())
        ]
        self.assertEqual(missed, [])

    def test_the_frame_is_the_topmost_item_at_each_handle(self) -> None:
        """
        Ensures the picture underneath does not win the click.
        """

        from src.editor_canvas import EditorCanvas, Tool

        canvas = EditorCanvas()
        self.addCleanup(canvas.close)
        canvas.set_screenshot(_pixmap(480, 320))
        canvas.resize(600, 440)
        canvas.show()
        self._app.processEvents()
        canvas.set_tool(Tool.CROP)
        self._app.processEvents()

        item = canvas._crop_item
        wrong = []
        for name, handle in item._handle_rects().items():
            view_point = canvas.mapFromScene(item.mapToScene(handle.center()))
            if canvas.itemAt(view_point) is not item:
                wrong.append(name)
        self.assertEqual(wrong, [], "clicks do not reach the crop frame")

    def test_the_interior_still_moves_the_frame(self) -> None:
        """
        Ensures the winding fill did not cost the drag-to-move area.
        """

        from src.crop_item import CropSelectionItem

        item = CropSelectionItem(QRectF(0.0, 0.0, 300.0, 200.0))
        item.set_crop_presentation(True)
        self.assertTrue(item.shape().contains(item.rect().center()))


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestCropKeepsTransparency(unittest.TestCase):
    """
    Verifies a see-through picture stays see-through after cropping.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def _cleared_pixmap(self) -> "QPixmap":
        """
        Builds a picture with a cleared middle, as the wand leaves it.

        Returns:
            QPixmap: Opaque picture with a transparent hole.
        """

        from PySide6.QtGui import QPainter

        image = QImage(400, 300, QImage.Format.Format_ARGB32)
        image.fill(QColor(200, 60, 60, 255))
        painter = QPainter(image)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(120, 90, 160, 120, QColor(0, 0, 0, 0))
        painter.end()
        return QPixmap.fromImage(image)

    def _canvas(self, pixmap):
        """
        Builds a canvas holding one picture with the crop tool active.

        Args:
            pixmap: Document background.

        Returns:
            EditorCanvas: Canvas under test.
        """

        from src.editor_canvas import EditorCanvas, Tool

        canvas = EditorCanvas()
        self.addCleanup(canvas.close)
        canvas.set_screenshot(pixmap)
        canvas.set_tool(Tool.CROP)
        return canvas

    def test_a_cleared_area_is_not_filled_in(self) -> None:
        """
        Ensures cropping does not paint white behind a cleared background.

        The fill sits under the picture, so an opaque one shows through every
        see-through area.
        """

        canvas = self._canvas(self._cleared_pixmap())
        canvas._crop_item.setPos(QPointF(50.0, 40.0))
        canvas._crop_item.setRect(QRectF(0.0, 0.0, 300.0, 220.0))
        canvas.apply_pending_crop()

        result = canvas.screenshot().toImage()
        self.assertEqual(result.pixelColor(150, 110).alpha(), 0, "hole was filled in")

    def test_the_opaque_part_stays_opaque(self) -> None:
        """
        Ensures the fix did not make the whole picture see-through.
        """

        canvas = self._canvas(self._cleared_pixmap())
        canvas._crop_item.setPos(QPointF(50.0, 40.0))
        canvas._crop_item.setRect(QRectF(0.0, 0.0, 300.0, 220.0))
        canvas.apply_pending_crop()

        result = canvas.screenshot().toImage()
        self.assertEqual(result.pixelColor(5, 5).alpha(), 255)

    def test_an_opaque_picture_still_gets_the_background_colour(self) -> None:
        """
        Ensures a screenshot cropped past its edge does not gain a see-through
        margin, which would be a different regression.
        """

        opaque = QImage(200, 150, QImage.Format.Format_RGB32)
        opaque.fill(QColor(40, 80, 160))
        canvas = self._canvas(QPixmap.fromImage(opaque))
        canvas._crop_item.setPos(QPointF(-20.0, -20.0))
        canvas._crop_item.setRect(QRectF(0.0, 0.0, 240.0, 190.0))
        canvas.apply_pending_crop()

        result = canvas.screenshot().toImage()
        self.assertEqual(result.pixelColor(2, 2).alpha(), 255, "margin turned see-through")

    def test_the_kept_pixels_are_unchanged(self) -> None:
        """
        Ensures cropping still returns the picture, not a recoloured copy.
        """

        canvas = self._canvas(self._cleared_pixmap())
        canvas._crop_item.setPos(QPointF(50.0, 40.0))
        canvas._crop_item.setRect(QRectF(0.0, 0.0, 300.0, 220.0))
        canvas.apply_pending_crop()

        result = canvas.screenshot().toImage()
        self.assertEqual(result.pixelColor(5, 5), QColor(200, 60, 60, 255))


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestCropRatioPresets(unittest.TestCase):
    """
    Verifies the ratio presets.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def _canvas(self):
        """
        Builds a canvas with an active crop frame.

        Returns:
            EditorCanvas: Canvas under test.
        """

        from src.editor_canvas import EditorCanvas, Tool

        canvas = EditorCanvas()
        self.addCleanup(canvas.close)
        canvas.set_screenshot(_pixmap(480, 320))
        canvas.set_tool(Tool.CROP)
        return canvas

    def test_a_chosen_ratio_reshapes_the_frame(self) -> None:
        """
        Ensures the preset takes effect immediately, not on the next drag.
        """

        canvas = self._canvas()
        canvas.set_crop_aspect_ratio(1.0)

        frame = canvas._crop_item.scene_rect()
        self.assertAlmostEqual(frame.width() / frame.height(), 1.0, places=3)

    def test_the_frame_never_leaves_the_picture(self) -> None:
        """
        Ensures a ratio change cannot crop in empty pixels.
        """

        canvas = self._canvas()
        for ratio in (1.0, 16.0 / 9.0, 9.0 / 16.0, 4.0 / 3.0):
            canvas.set_crop_aspect_ratio(ratio)
            frame = canvas._crop_item.scene_rect()
            self.assertTrue(
                QRectF(canvas.document_rect()).contains(frame),
                f"frame left the picture at ratio {ratio}",
            )

    def test_the_ratio_holds_for_a_whole_drag(self) -> None:
        """
        Ensures no modifier has to be held, which is easy to lose mid-drag.
        """

        canvas = self._canvas()
        canvas.set_crop_aspect_ratio(1.0)
        item = canvas._crop_item

        item._resizing = True
        item._active_handle = "bottom_right"
        item._resize_from_handle("bottom_right", QPointF(400.0, 120.0), lock_aspect_ratio=True)

        frame = item.scene_rect()
        self.assertAlmostEqual(frame.width() / frame.height(), 1.0, places=2)

    def test_free_lets_the_frame_take_any_shape(self) -> None:
        """
        Ensures the constraint can be released again.
        """

        canvas = self._canvas()
        canvas.set_crop_aspect_ratio(1.0)
        canvas.set_crop_aspect_ratio(None)

        self.assertIsNone(canvas.crop_aspect_ratio())
        self.assertIsNone(canvas._crop_item.fixed_aspect_ratio())

    def test_a_nonsense_ratio_is_ignored(self) -> None:
        """
        Ensures a stray value cannot collapse the frame.
        """

        canvas = self._canvas()
        before = canvas._crop_item.scene_rect()
        canvas._crop_item.set_fixed_aspect_ratio(0.0)
        canvas._crop_item.set_fixed_aspect_ratio(-3.0)

        self.assertEqual(canvas._crop_item.scene_rect(), before)

    def test_the_choice_survives_a_new_frame(self) -> None:
        """
        Ensures switching tools and back does not silently drop the ratio.
        """

        from src.editor_canvas import Tool

        canvas = self._canvas()
        canvas.set_crop_aspect_ratio(1.0)
        canvas.set_tool(Tool.SELECT)
        canvas.set_tool(Tool.CROP)

        frame = canvas._crop_item.scene_rect()
        self.assertAlmostEqual(frame.width() / frame.height(), 1.0, places=3)


if __name__ == "__main__":
    unittest.main()
