"""
Unit tests for global hotkey conversion helpers.
"""

from __future__ import annotations

import unittest

from src.global_hotkeys import hotkey_spec_to_pynput


class TestGlobalHotkeys(unittest.TestCase):
    """
    Verifies hotkey string conversion for pynput.
    """

    def test_hotkey_spec_to_pynput_converts_modifiers(self) -> None:
        """
        Ensures modifier combinations convert to pynput syntax.
        """

        self.assertEqual(
            hotkey_spec_to_pynput("ctrl+shift+a"),
            "<ctrl>+<shift>+a",
        )

    def test_hotkey_spec_to_pynput_supports_function_keys(self) -> None:
        """
        Ensures function keys convert to pynput syntax.
        """

        self.assertEqual(
            hotkey_spec_to_pynput("ctrl+f1"),
            "<ctrl>+<f1>",
        )

    def test_hotkey_spec_to_pynput_rejects_invalid_values(self) -> None:
        """
        Ensures invalid hotkey strings are rejected.
        """

        self.assertIsNone(hotkey_spec_to_pynput(""))
        self.assertIsNone(hotkey_spec_to_pynput("invalid hotkey"))
