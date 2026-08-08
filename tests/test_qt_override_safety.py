"""
Tests for the guard that keeps Python exceptions out of Qt's C++ stack.

Qt calls ``boundingRect``, ``shape``, ``paint``, and ``itemChange`` from inside
its render and event loops. A raising override leaves PySide without a value to
return and the process dies -- that is the exact shape of the segfault recorded
in the crash log:

    AttributeError: Error calling Python override of QGraphicsRectItem::boundingRect()
    ...
    Fatal Python error: Segmentation fault

The bug behind it was small and local; the cost was the whole editor plus the
user's unsaved work. These tests pin the net down, including a check that every
override in the item modules actually carries it.
"""

from __future__ import annotations

import ast
import pathlib
import unittest
from unittest.mock import patch

try:
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath
    from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene

    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False

GUARDED_METHODS = {
    "boundingRect": "safe_bounding_rect",
    "shape": "safe_shape",
    "paint": "safe_paint",
    "itemChange": "safe_item_change",
}

ITEM_MODULES = [
    "src/shape_items.py",
    "src/annotation_shapes.py",
    "src/crop_item.py",
    "src/annotation_items.py",
]


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for Qt override safety tests")
class TestSafeOverrides(unittest.TestCase):
    """
    Verifies a failing override returns a usable value instead of unwinding.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for graphics items.
        """

        cls._app = ensure_qapp()

    def setUp(self) -> None:
        """
        Clears the per-session report set between tests.
        """

        from src.qt_safety import reset_reported_overrides

        reset_reported_overrides()

    def test_failing_bounding_rect_returns_empty_rect(self) -> None:
        """
        Ensures Qt receives a valid rectangle even when the override fails.
        """

        from src.qt_safety import safe_bounding_rect

        class Broken:
            @safe_bounding_rect
            def boundingRect(self):
                raise AttributeError("no attribute 'setFont'")

        self.assertEqual(Broken().boundingRect(), QRectF())

    def test_failing_shape_returns_empty_path(self) -> None:
        """
        Ensures hit-testing gets a valid path instead of a crash.
        """

        from src.qt_safety import safe_shape

        class Broken:
            @safe_shape
            def shape(self):
                raise RuntimeError("Internal C++ object already deleted")

        self.assertTrue(Broken().shape().isEmpty())

    def test_failing_paint_returns_none(self) -> None:
        """
        Ensures one bad frame does not take the process down.
        """

        from src.qt_safety import safe_paint

        class Broken:
            @safe_paint
            def paint(self, painter, option, widget=None):
                raise ZeroDivisionError("division by zero")

        self.assertIsNone(Broken().paint(None, None))

    def test_failing_item_change_passes_the_value_through(self) -> None:
        """
        Ensures a failed ``itemChange`` behaves as a no-op, which is what Qt
        expects: returning the incoming value leaves the change unmodified.
        """

        from src.qt_safety import safe_item_change

        class Broken:
            @safe_item_change
            def itemChange(self, change, value):
                raise ValueError("boom")

        marker = object()
        self.assertIs(Broken().itemChange("pos", marker), marker)

    def test_successful_override_is_untouched(self) -> None:
        """
        Ensures the guard does not alter normal results.
        """

        from src.qt_safety import safe_bounding_rect

        class Fine:
            @safe_bounding_rect
            def boundingRect(self):
                return QRectF(1.0, 2.0, 3.0, 4.0)

        self.assertEqual(Fine().boundingRect(), QRectF(1.0, 2.0, 3.0, 4.0))

    def test_failure_is_reported_once_per_override(self) -> None:
        """
        Ensures the crash log gets the traceback, but only once: Qt repaints
        constantly, and an unthrottled log would bury the first report.
        """

        from src.qt_safety import reported_override_failures, safe_bounding_rect

        class Broken:
            @safe_bounding_rect
            def boundingRect(self):
                raise AttributeError("boom")

        item = Broken()
        with patch("src.crash_log.log_exception") as logged:
            for _ in range(5):
                item.boundingRect()

        logged.assert_called_once()
        self.assertIn("Broken.boundingRect", reported_override_failures())

    def test_real_item_keeps_rendering_when_a_helper_fails(self) -> None:
        """
        Ensures the end-to-end case works: a broken helper deep inside
        ``boundingRect`` no longer kills the render pass.
        """

        from src.qt_safety import reported_override_failures
        from src.shape_items import PathShapeItem

        item = PathShapeItem("rect", QRectF(0.0, 0.0, 80.0, 60.0))
        scene = QGraphicsScene()
        scene.addItem(item)

        def boom(_self):
            raise AttributeError("'StyledTextItem' object has no attribute 'setFont'")

        target = QImage(200, 150, QImage.Format.Format_ARGB32)
        target.fill(QColor(0, 0, 0, 0))
        painter = QPainter(target)
        with patch.object(PathShapeItem, "_halo_extra_margin", boom):
            self.assertEqual(item.boundingRect(), QRectF())
            scene.render(painter)
        painter.end()

        self.assertIn("PathShapeItem.boundingRect", reported_override_failures())


class TestEveryOverrideIsGuarded(unittest.TestCase):
    """
    Verifies no annotation item ships an unguarded value-returning override.

    Static check on purpose: it also covers overrides a future change adds, which
    is the point -- one unguarded ``boundingRect`` is enough to bring back the
    segfault.
    """

    def test_item_overrides_carry_the_guard(self) -> None:
        """
        Ensures every boundingRect/shape/paint/itemChange has its decorator.
        """

        root = pathlib.Path(__file__).resolve().parent.parent
        unguarded: list[str] = []
        checked = 0
        for relative in ITEM_MODULES:
            path = root / relative
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                for member in node.body:
                    if not isinstance(member, ast.FunctionDef):
                        continue
                    expected = GUARDED_METHODS.get(member.name)
                    if expected is None:
                        continue
                    checked += 1
                    names = {
                        decorator.id
                        for decorator in member.decorator_list
                        if isinstance(decorator, ast.Name)
                    }
                    if expected not in names:
                        unguarded.append(f"{relative}:{node.name}.{member.name}")

        self.assertGreater(checked, 0, "no overrides found -- test lost its target")
        self.assertEqual(
            unguarded,
            [],
            "unguarded Qt overrides can segfault the editor; "
            f"decorate them from src.qt_safety: {unguarded}",
        )


if __name__ == "__main__":
    unittest.main()
