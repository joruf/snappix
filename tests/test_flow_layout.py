"""
Unit tests for the toolbar flow layout.
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QPushButton, QWidget

    from src.flow_layout import (
        FlowLayout,
        FlowLayoutWidget,
        sort_widgets_by_area_descending,
        widget_layout_area,
    )
    from tests.qt_test_utils import ensure_qapp

    HAS_PYSIDE6 = True
except ModuleNotFoundError:
    HAS_PYSIDE6 = False


@unittest.skipUnless(HAS_PYSIDE6, "PySide6 is required for flow layout tests")
class TestFlowLayout(unittest.TestCase):
    """
    Verifies wrapped left-to-right flow layout behavior.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures Qt application exists for layout tests.
        """

        cls._app = ensure_qapp()

    def test_flow_layout_wraps_buttons_into_multiple_rows(self) -> None:
        """
        Ensures items wrap to the next row when width is limited.
        """

        container = QWidget()
        container.setFixedWidth(260)
        layout = FlowLayout(container, margin=0, horizontal_spacing=4, vertical_spacing=4)
        for index in range(4):
            button = QPushButton(f"Tool {index}")
            button.setFixedWidth(120)
            layout.addWidget(button)

        height_narrow = layout.heightForWidth(260)
        container_tall = QWidget()
        container_tall.setFixedWidth(520)
        layout_wide = FlowLayout(container_tall, margin=0, horizontal_spacing=4, vertical_spacing=4)
        for index in range(4):
            button = QPushButton(f"Tool {index}")
            button.setFixedWidth(120)
            layout_wide.addWidget(button)
        height_wide = layout_wide.heightForWidth(520)

        self.assertGreater(height_narrow, height_wide)

    def test_sort_widgets_by_area_descending_places_largest_first(self) -> None:
        """
        Ensures toolbar containers are ordered by descending area.
        """

        large = QPushButton("Large")
        large.setFixedSize(200, 80)
        medium = QPushButton("Medium")
        medium.setFixedSize(120, 60)
        small = QPushButton("Small")
        small.setFixedSize(60, 30)

        sorted_widgets = sort_widgets_by_area_descending([small, medium, large])
        self.assertEqual(sorted_widgets, [large, medium, small])
        self.assertGreater(widget_layout_area(large), widget_layout_area(medium))
        self.assertGreater(widget_layout_area(medium), widget_layout_area(small))

    def test_flow_layout_set_widgets_places_items_left_to_right(self) -> None:
        """
        Ensures set_widgets lays out items from left to right before wrapping.
        """

        container = QWidget()
        container.setFixedWidth(250)
        layout = FlowLayout(container, margin=0, horizontal_spacing=4, vertical_spacing=4)
        first = QPushButton("First")
        first.setFixedSize(100, 24)
        second = QPushButton("Second")
        second.setFixedSize(100, 24)
        third = QPushButton("Third")
        third.setFixedSize(100, 24)
        layout.set_widgets([first, second, third])
        layout.setGeometry(QRect(0, 0, 250, 100))

        self.assertLess(first.geometry().x(), second.geometry().x())
        self.assertEqual(first.geometry().y(), second.geometry().y())
        self.assertGreater(third.geometry().y(), second.geometry().y())

    def test_flow_layout_widget_reflows_when_width_changes(self) -> None:
        """
        Ensures the flow container increases height when width becomes narrower.
        """

        container = FlowLayoutWidget()
        container.setFixedWidth(520)
        buttons = []
        for index in range(4):
            button = QPushButton(f"Tool {index}")
            button.setFixedSize(120, 24)
            buttons.append(button)
        container.set_flow_widgets(buttons)

        wide_height = container.heightForWidth(520)
        narrow_height = container.heightForWidth(250)
        self.assertGreater(narrow_height, wide_height)

        container.setFixedWidth(250)
        container.update_flow_geometry()
        self.assertGreaterEqual(container.minimumHeight(), narrow_height)
        self.assertGreater(buttons[-1].geometry().y(), buttons[0].geometry().y())
