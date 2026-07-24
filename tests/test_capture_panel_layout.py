"""
Unit tests for the CapturePanel's toolbar layout.
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtWidgets import QFrame

    from src.capture import CapturePanel
    from src.flow_layout import FlowLayoutWidget
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


def _vertical_ranges_overlap(first, second) -> bool:
    """
    Checks whether two widget geometries occupy the same flow-layout row.

    Args:
        first: First widget's geometry rectangle.
        second: Second widget's geometry rectangle.

    Returns:
        bool: True when the two rectangles' vertical spans intersect.
    """

    return first.y() < second.y() + second.height() and second.y() < first.y() + first.height()


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for capture panel tests")
class TestCapturePanelLayout(unittest.TestCase):
    """
    Verifies the Open Editor link and capture buttons sit where the user expects.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for widget creation.
        """

        ensure_qapp()

    def test_open_editor_button_is_not_inside_the_delay_frame(self) -> None:
        """
        Ensures the Open Editor link lives outside the bordered delay frame.
        """

        panel = CapturePanel()
        delay_frame = panel.delay_slider.parentWidget()
        self.assertIsInstance(delay_frame, QFrame)
        self.assertIsNot(panel.open_editor_button.parentWidget(), delay_frame)

    def test_open_editor_button_is_the_last_button_in_the_flow(self) -> None:
        """
        Ensures the Open Editor link sits as the last item among the capture buttons.
        """

        panel = CapturePanel()
        buttons_flow = panel.capture_fullscreen_button.parentWidget()
        self.assertIs(panel.open_editor_button.parentWidget(), buttons_flow)
        last_item = buttons_flow.flow_layout.itemAt(buttons_flow.flow_layout.count() - 1)
        self.assertIs(last_item.widget(), panel.open_editor_button)

    def test_capture_buttons_live_in_a_bordered_flow_container(self) -> None:
        """
        Ensures the capture-mode buttons sit in a bordered frame using a flow layout.
        """

        panel = CapturePanel()
        buttons_flow = panel.capture_fullscreen_button.parentWidget()
        self.assertIsInstance(buttons_flow, FlowLayoutWidget)
        buttons_frame = buttons_flow.parentWidget()
        self.assertIsInstance(buttons_frame, QFrame)

    def test_capture_buttons_wrap_to_multiple_rows_when_narrow(self) -> None:
        """
        Ensures shrinking the panel wraps capture buttons onto more than one row.
        """

        panel = CapturePanel()
        buttons_flow = panel.capture_fullscreen_button.parentWidget()

        buttons_flow.setFixedWidth(900)
        buttons_flow.update_flow_geometry()
        wide_last_button_y = panel.pick_color_button.geometry().y()

        buttons_flow.setFixedWidth(260)
        buttons_flow.update_flow_geometry()
        narrow_last_button_y = panel.pick_color_button.geometry().y()

        self.assertEqual(wide_last_button_y, panel.capture_fullscreen_button.geometry().y())
        self.assertGreater(narrow_last_button_y, panel.capture_fullscreen_button.geometry().y())

    def test_default_window_width_fits_all_capture_buttons_on_one_row(self) -> None:
        """
        Ensures the panel's default size places all six capture buttons on one row
        with the Open Editor link wrapping onto the row below, and stays no taller
        than needed to show that layout.
        """

        panel = CapturePanel()
        panel.show()
        panel._apply_initial_window_geometry()

        capture_buttons = [
            panel.capture_fullscreen_button,
            panel.capture_area_button,
            panel.capture_window_button,
            panel.capture_scroll_button,
            panel.capture_video_button,
            panel.pick_color_button,
        ]
        reference = capture_buttons[0].geometry()
        for button in capture_buttons[1:]:
            self.assertTrue(_vertical_ranges_overlap(reference, button.geometry()))
        self.assertFalse(
            _vertical_ranges_overlap(reference, panel.open_editor_button.geometry())
        )
        self.assertGreater(panel.open_editor_button.geometry().y(), reference.y())
        self.assertEqual(panel.height(), panel.minimumSizeHint().height())


if __name__ == "__main__":
    unittest.main()
