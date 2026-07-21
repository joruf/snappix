"""
Unit tests for configuration persistence.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.config import (
    DEFAULT_HOTKEY_CAPTURE_REGION,
    AppConfig,
    ConfigManager,
    normalize_hotkey_spec,
    normalize_post_capture_action,
)
from src.theme import THEME_LIGHT


class TestConfigManager(unittest.TestCase):
    """
    Verifies load and save behavior for app settings.
    """

    def test_load_returns_defaults_for_missing_file(self) -> None:
        """
        Ensures missing config file uses default values.
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.json"
            manager = ConfigManager(config_path)
            config = manager.load()
            self.assertFalse(config.autostart_enabled)
            self.assertEqual(config.theme, "dark")
            self.assertTrue(config.hotkeys_enabled)
            self.assertEqual(config.hotkey_capture_region, DEFAULT_HOTKEY_CAPTURE_REGION)

    def test_load_returns_defaults_for_invalid_json(self) -> None:
        """
        Ensures invalid JSON does not crash and falls back.
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.json"
            config_path.write_text("{invalid", encoding="utf-8")
            manager = ConfigManager(config_path)
            config = manager.load()
            self.assertFalse(config.autostart_enabled)
            self.assertEqual(config.theme, "dark")
            self.assertTrue(config.hotkeys_enabled)
            self.assertEqual(config.hotkey_capture_region, DEFAULT_HOTKEY_CAPTURE_REGION)

    def test_save_and_load_roundtrip(self) -> None:
        """
        Ensures saved configuration can be loaded again.
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "nested" / "config.json"
            manager = ConfigManager(config_path)
            manager.save(
                AppConfig(
                    autostart_enabled=True,
                    theme=THEME_LIGHT,
                    post_capture_action="clipboard",
                    hotkey_capture_window="ctrl+shift+w",
                )
            )

            restored = manager.load()
            self.assertTrue(restored.autostart_enabled)
            self.assertEqual(restored.theme, THEME_LIGHT)
            self.assertEqual(restored.post_capture_action, "clipboard")
            self.assertEqual(restored.hotkey_capture_window, "ctrl+shift+w")

    def test_normalize_hotkey_spec_lowercases_and_trims(self) -> None:
        """
        Ensures hotkey strings are normalized to lowercase segments.
        """

        self.assertEqual(normalize_hotkey_spec(" Ctrl + Shift + A "), "ctrl+shift+a")
        self.assertEqual(normalize_hotkey_spec("CTRL+SHIFT+F1"), "ctrl+shift+f1")

    def test_normalize_post_capture_action_falls_back_to_default(self) -> None:
        """
        Ensures invalid post-capture actions fall back to editor.
        """

        self.assertEqual(normalize_post_capture_action("clipboard"), "clipboard")
        self.assertEqual(normalize_post_capture_action("unknown"), "editor")

