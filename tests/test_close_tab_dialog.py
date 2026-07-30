"""
Unit tests for the shared "Close Tab" confirmation dialog used by both the
Image and Video editors.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

try:
    from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

    from src.close_tab_dialog import confirm_close_tab
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


def _fake_exec_clicking(button_text: str):
    """
    Builds a fake ``QMessageBox.exec`` that simulates a click on the button
    with the given visible text, without spinning a real modal event loop.

    Args:
        button_text: Exact label of the button to "click".

    Returns:
        Callable: Replacement for QMessageBox.exec.
    """

    def _fake_exec(self) -> int:
        clicked = next(
            (button for button in self.buttons() if button.text() == button_text),
            None,
        )
        self.clickedButton = lambda: clicked
        return 0

    return _fake_exec


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for close-tab dialog tests")
class TestConfirmCloseTab(unittest.TestCase):
    """
    Verifies the dialog's button labels/icons and its True/False outcomes.
    """

    @classmethod
    def setUpClass(cls) -> None:
        ensure_qapp()

    def test_clicking_close_tab_returns_true(self) -> None:
        """
        Ensures choosing the destructive "Close Tab" button confirms closing.
        """

        parent = QWidget()
        with patch.object(QMessageBox, "exec", _fake_exec_clicking("Close Tab")):
            result = confirm_close_tab(parent, "This tab contains annotations. Close it anyway?")
        self.assertTrue(result)

    def test_clicking_cancel_returns_false(self) -> None:
        """
        Ensures choosing "Cancel" keeps the tab open.
        """

        parent = QWidget()
        with patch.object(QMessageBox, "exec", _fake_exec_clicking("Cancel")):
            result = confirm_close_tab(parent, "This tab contains annotations. Close it anyway?")
        self.assertFalse(result)

    def test_dialog_exposes_cancel_and_close_tab_buttons_with_icons(self) -> None:
        """
        Ensures the dialog uses the exact English "Cancel"/"Close Tab" labels
        (not the native Yes/No wording) and gives each button a distinct icon.
        """

        seen_buttons = {}

        def _capture_exec(self) -> int:
            for button in self.buttons():
                seen_buttons[button.text()] = button
            self.clickedButton = lambda: None
            return 0

        parent = QWidget()
        with patch.object(QMessageBox, "exec", _capture_exec):
            confirm_close_tab(parent, "message")

        self.assertEqual(set(seen_buttons.keys()), {"Cancel", "Close Tab"})
        for button in seen_buttons.values():
            self.assertFalse(button.icon().isNull())

    def test_cancel_sits_left_of_close_tab(self) -> None:
        """
        Ensures Cancel is the leftmost button.

        QMessageBox orders buttons by role using a platform-specific layout,
        which put the destructive "Close Tab" first; the dialog pins the order
        explicitly instead.
        """

        positions = {}

        def _capture_exec(self) -> int:
            self.show()
            QApplication.processEvents()
            self.layout().activate()
            QApplication.processEvents()
            for button in self.buttons():
                positions[button.text()] = button.x()
            self.hide()
            self.clickedButton = lambda: None
            return 0

        parent = QWidget()
        with patch.object(QMessageBox, "exec", _capture_exec):
            confirm_close_tab(parent, "message")

        self.assertIn("Cancel", positions)
        self.assertIn("Close Tab", positions)
        self.assertLess(positions["Cancel"], positions["Close Tab"])


if __name__ == "__main__":
    unittest.main()
