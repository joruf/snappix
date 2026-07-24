"""
Regression tests for Marks tools with the Style color palette.
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QPixmap

    from src.annotation_items import add_annotation_to_scene, configure_graphics_item
    from src.annotation_shapes import StepBadgeItem
    from src.editor_window import EditorWindow
    from src.models import AnnotationModel
    from src.shape_items import PathShapeItem, SpotlightItem
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for Marks palette tests")
class TestMarksPaletteColors(unittest.TestCase):
    """
    Verifies Border/Fill palette updates for Marks container objects.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def test_border_palette_recolors_selected_cross(self) -> None:
        """
        Ensures Border palette changes the visible cross mark color.
        """

        pixmap = QPixmap(200, 150)
        pixmap.fill(QColor(240, 240, 240))
        window = EditorWindow(pixmap)
        item = add_annotation_to_scene(
            window.canvas.scene(),
            AnnotationModel(
                annotation_type="cross",
                x=20.0,
                y=20.0,
                width=40.0,
                height=40.0,
                stroke_rgba=[231, 76, 60, 255],
                fill_rgba=[231, 76, 60, 255],
                stroke_width=0.0,
            ),
        )
        assert isinstance(item, PathShapeItem)
        item.setSelected(True)
        window._apply_palette_color("stroke", QColor("#2ecc71"))  # pylint: disable=protected-access
        self.assertEqual(item.brush().color().name(), "#2ecc71")
        self.assertEqual(item.pen().style(), Qt.PenStyle.NoPen)
        window.close()

    def test_fill_palette_on_spotlight_does_not_crash(self) -> None:
        """
        Ensures Fill palette accepts QColor for spotlight without crashing.
        """

        pixmap = QPixmap(200, 150)
        pixmap.fill(QColor(240, 240, 240))
        window = EditorWindow(pixmap)
        spot = SpotlightItem(QRectF(0.0, 0.0, 60.0, 60.0), dim_alpha=150)
        configure_graphics_item(spot, "spotlight")
        spot.setPos(30.0, 30.0)
        window.canvas.scene().addItem(spot)
        spot.setSelected(True)
        # Palette keeps the current fill alpha; exercise the QColor setBrush path.
        window.canvas.set_style(  # pylint: disable=protected-access
            fill_color=QColor(0, 0, 0, 180),
            emit_history=False,
        )
        self.assertEqual(spot.dim_alpha(), 180)
        window._apply_palette_color("stroke", QColor("#e74c3c"))  # pylint: disable=protected-access
        self.assertEqual(spot.pen().color().name(), "#e74c3c")
        window.close()

    def test_fill_palette_recolors_selected_step(self) -> None:
        """
        Ensures Fill palette changes the step badge body color.
        """

        pixmap = QPixmap(200, 150)
        pixmap.fill(QColor(240, 240, 240))
        window = EditorWindow(pixmap)
        badge = StepBadgeItem(1)
        configure_graphics_item(badge, "step")
        window.canvas.scene().addItem(badge)
        badge.setSelected(True)
        window._apply_palette_color("fill", QColor("#3498db"))  # pylint: disable=protected-access
        self.assertEqual(badge.brush().color().name(), "#3498db")
        window.close()


if __name__ == "__main__":
    unittest.main()
