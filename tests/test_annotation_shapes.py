"""
Unit tests for step badges and styled text annotation items.
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtGui import QColor, QFont
    from PySide6.QtWidgets import QGraphicsScene

    from src.annotation_items import add_annotation_to_scene, annotation_from_item
    from src.annotation_shapes import (
        TEXT_STYLE_BOX,
        TEXT_STYLE_BUBBLE,
        TEXT_STYLE_PLAIN,
        StepBadgeItem,
        StyledTextItem,
        add_step_to_scene,
        add_styled_text_to_scene,
        annotation_from_step_item,
        annotation_from_styled_text_item,
        is_styled_text_annotation,
    )
    from src.models import AnnotationModel
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for annotation shape tests")
class TestAnnotationShapes(unittest.TestCase):
    """
    Verifies step badge and styled text serialization behavior.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures Qt application exists for graphics types.
        """

        cls._app = ensure_qapp()

    def test_step_badge_number_updates(self) -> None:
        """
        Ensures step badge label reflects number changes.
        """

        badge = StepBadgeItem(3)
        self.assertEqual(badge.step_number(), 3)
        badge.set_step_number(7)
        self.assertEqual(badge.step_number(), 7)

    def test_step_badge_roundtrip(self) -> None:
        """
        Ensures step badge annotations serialize and restore correctly.
        """

        scene = QGraphicsScene()
        annotation = AnnotationModel(
            annotation_type="step",
            x=20.0,
            y=30.0,
            width=36.0,
            height=36.0,
            stroke_rgba=[255, 255, 255, 240],
            fill_rgba=[231, 76, 60, 240],
            stroke_width=2.0,
            text="5",
            payload={"step_number": 5},
        )
        item = add_step_to_scene(scene, annotation)
        self.assertIsInstance(item, StepBadgeItem)
        self.assertEqual(item.step_number(), 5)

        restored = annotation_from_step_item(item)
        self.assertEqual(restored.annotation_type, "step")
        self.assertEqual(restored.payload.get("step_number"), 5)
        self.assertAlmostEqual(restored.x, 20.0)
        self.assertAlmostEqual(restored.y, 30.0)

    def test_styled_text_box_roundtrip(self) -> None:
        """
        Ensures boxed text annotations serialize and restore correctly.
        """

        scene = QGraphicsScene()
        font = QFont()
        font.setPointSize(16)
        font.setFamily("Sans Serif")
        font.setBold(True)
        item = StyledTextItem(
            text="Callout",
            text_style=TEXT_STYLE_BOX,
            font=font,
            text_color=QColor(10, 20, 30, 255),
            fill_color=QColor(240, 240, 240, 255),
            stroke_color=QColor(50, 60, 70, 255),
            stroke_width=2.0,
        )
        item.setPos(12.0, 18.0)
        scene.addItem(item)

        annotation = annotation_from_styled_text_item(item)
        self.assertEqual(annotation.annotation_type, "text")
        self.assertEqual(annotation.text, "Callout")
        self.assertEqual(annotation.payload.get("text_style"), TEXT_STYLE_BOX)
        self.assertTrue(annotation.font_bold)

        restored = add_styled_text_to_scene(scene, annotation)
        self.assertEqual(restored.text(), "Callout")
        self.assertEqual(restored.text_style(), TEXT_STYLE_BOX)

    def test_styled_text_bubble_is_detected(self) -> None:
        """
        Ensures speech bubble style is recognized as styled text.
        """

        annotation = AnnotationModel(
            annotation_type="text",
            x=0.0,
            y=0.0,
            width=80.0,
            height=40.0,
            stroke_rgba=[0, 0, 0, 255],
            fill_rgba=[255, 255, 255, 255],
            stroke_width=1.0,
            text="Hi",
            payload={"text_style": TEXT_STYLE_BUBBLE},
        )
        self.assertTrue(is_styled_text_annotation(annotation))

    def test_plain_text_is_not_styled(self) -> None:
        """
        Ensures plain text annotations are not treated as styled containers.
        """

        annotation = AnnotationModel(
            annotation_type="text",
            x=0.0,
            y=0.0,
            width=40.0,
            height=20.0,
            stroke_rgba=[0, 0, 0, 255],
            fill_rgba=[0, 0, 0, 0],
            stroke_width=1.0,
            text="Plain",
            payload={"text_style": TEXT_STYLE_PLAIN},
        )
        self.assertFalse(is_styled_text_annotation(annotation))

    def test_add_annotation_to_scene_routes_step_and_styled_text(self) -> None:
        """
        Ensures annotation_items delegates step and styled text correctly.
        """

        scene = QGraphicsScene()
        step_item = add_annotation_to_scene(
            scene,
            AnnotationModel(
                annotation_type="step",
                x=5.0,
                y=6.0,
                width=36.0,
                height=36.0,
                stroke_rgba=[255, 255, 255, 255],
                fill_rgba=[231, 76, 60, 255],
                stroke_width=2.0,
                text="2",
                payload={"step_number": 2},
            ),
        )
        self.assertIsInstance(step_item, StepBadgeItem)
        step_model = annotation_from_item(step_item)
        self.assertIsNotNone(step_model)
        assert step_model is not None
        self.assertEqual(step_model.annotation_type, "step")

        styled_item = add_annotation_to_scene(
            scene,
            AnnotationModel(
                annotation_type="text",
                x=8.0,
                y=9.0,
                width=60.0,
                height=30.0,
                stroke_rgba=[20, 20, 20, 255],
                fill_rgba=[255, 255, 255, 230],
                stroke_width=2.0,
                text="Boxed",
                payload={"text_style": TEXT_STYLE_BOX},
            ),
        )
        self.assertIsInstance(styled_item, StyledTextItem)
        styled_model = annotation_from_item(styled_item)
        self.assertIsNotNone(styled_model)
        assert styled_model is not None
        self.assertEqual(styled_model.payload.get("text_style"), TEXT_STYLE_BOX)
