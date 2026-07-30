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

    def test_default_window_width_fits_primary_capture_buttons_on_one_row(self) -> None:
        """
        Ensures the panel's default size uses CAPTURE_PANEL_START_WIDTH and
        wraps Scroll/Video/tools below Fullscreen/Area/Window.
        """

        from src.capture import CAPTURE_PANEL_START_WIDTH

        panel = CapturePanel()
        panel.set_video_capture_available(True)
        panel.show()
        panel._apply_initial_window_geometry()

        self.assertEqual(panel.width(), CAPTURE_PANEL_START_WIDTH)

        first_row_buttons = [
            button
            for button in (
                panel.capture_fullscreen_button,
                panel.capture_area_button,
                panel.capture_window_button,
            )
            if not button.isHidden()
        ]
        self.assertGreaterEqual(len(first_row_buttons), 2)
        reference = first_row_buttons[0].geometry()
        for button in first_row_buttons[1:]:
            self.assertTrue(_vertical_ranges_overlap(reference, button.geometry()))

        wrapped_buttons = [
            button
            for button in (
                panel.capture_scroll_button,
                panel.capture_video_button,
                panel.pick_color_button,
                panel.measure_box_button,
                panel.recognize_text_button,
                panel.open_editor_button,
            )
            if not button.isHidden()
        ]
        for button in wrapped_buttons:
            self.assertFalse(_vertical_ranges_overlap(reference, button.geometry()))
            self.assertGreater(button.geometry().y(), reference.y())

        layout = panel.layout()
        self.assertIsNotNone(layout)
        expected_height = layout.heightForWidth(panel.contentsRect().width())
        self.assertEqual(panel.height(), expected_height)

    def test_measure_box_button_is_between_color_picker_and_ocr(self) -> None:
        """
        Ensures MeasureBox sits between the color picker and OCR in the flow.
        """

        panel = CapturePanel()
        panel.set_text_recognition_available(True)
        buttons_flow = panel.capture_fullscreen_button.parentWidget()
        widgets = [
            buttons_flow.flow_layout.itemAt(index).widget()
            for index in range(buttons_flow.flow_layout.count())
        ]
        color_index = widgets.index(panel.pick_color_button)
        measure_index = widgets.index(panel.measure_box_button)
        ocr_index = widgets.index(panel.recognize_text_button)
        self.assertEqual(measure_index, color_index + 1)
        self.assertEqual(ocr_index, measure_index + 1)

    def test_measure_box_tooltip_includes_hotkey_and_usage(self) -> None:
        """
        Ensures the MeasureBox tooltip mentions the hotkey and short usage.
        """

        from src.capture import measure_box_button_tooltip

        panel = CapturePanel()
        panel.set_measure_box_hotkey("ctrl+shift+m")
        tip = panel.measure_box_button.toolTip()
        self.assertIn("Ctrl+Shift+M", tip)
        self.assertIn("drag to draw", tip)
        self.assertIn("Esc", tip)
        self.assertEqual(tip, measure_box_button_tooltip("ctrl+shift+m"))

    def test_unsupported_modes_are_hidden_not_just_disabled(self) -> None:
        """
        Ensures window/scroll buttons are hidden when the OS does not support them.
        """

        from src.paths import supports_scroll_capture, supports_window_capture

        panel = CapturePanel()
        panel.set_video_capture_available(False)
        self.assertEqual(panel.capture_window_button.isHidden(), not supports_window_capture())
        self.assertEqual(panel.capture_scroll_button.isHidden(), not supports_scroll_capture())
        self.assertTrue(panel.capture_video_button.isHidden())


if __name__ == "__main__":
    unittest.main()
