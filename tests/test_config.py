"""
Unit tests for configuration persistence.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.config import (
    DEFAULT_EXPORT_PRESET,
    DEFAULT_EXPORT_SCALE,
    DEFAULT_HOTKEY_CAPTURE_REGION,
    DEFAULT_EDITOR_LAST_TAB_BEHAVIOR,
    AppConfig,
    ConfigManager,
    normalize_editor_last_tab_behavior,
    normalize_export_preset,
    normalize_export_scale,
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
            self.assertEqual(
                config.editor_last_tab_behavior,
                DEFAULT_EDITOR_LAST_TAB_BEHAVIOR,
            )
            self.assertEqual(config.export_preset, DEFAULT_EXPORT_PRESET)
            self.assertTrue(config.batch_export_profiles)
            self.assertEqual(config.batch_export_profile_key, "docs_hq")
            self.assertEqual(config.batch_export_last_directory, "")
            self.assertTrue(config.auto_crop_on_shrink)

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
            self.assertEqual(
                config.editor_last_tab_behavior,
                DEFAULT_EDITOR_LAST_TAB_BEHAVIOR,
            )
            self.assertEqual(config.export_preset, DEFAULT_EXPORT_PRESET)
            self.assertTrue(config.batch_export_profiles)
            self.assertEqual(config.batch_export_profile_key, "docs_hq")
            self.assertEqual(config.batch_export_last_directory, "")
            self.assertTrue(config.auto_crop_on_shrink)

    def test_save_and_load_editor_shortcuts_roundtrip(self) -> None:
        """
        Ensures custom editor shortcuts persist and unknown ids are dropped.
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.json"
            manager = ConfigManager(config_path)
            manager.save(
                AppConfig(
                    editor_shortcuts={
                        "copy": "F9",
                        "paste": "",
                        "not_a_real_action": "F1",
                    }
                )
            )
            loaded = manager.load()
            self.assertEqual(loaded.editor_shortcuts.get("copy"), "F9")
            self.assertEqual(loaded.editor_shortcuts.get("paste"), "")
            self.assertNotIn("not_a_real_action", loaded.editor_shortcuts)

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
                    editor_last_tab_behavior="close_window",
                    export_preset="print",
                    export_scale=2.0,
                    export_keep_transparency=False,
                    batch_export_profiles=[
                        {
                            "key": "custom_profile",
                            "label": "Custom Profile",
                            "formats": ["png", "pdf"],
                            "jpg_quality": 88,
                            "pdf_dpi": 240,
                        }
                    ],
                    batch_export_profile_key="custom_profile",
                    batch_export_last_directory="/tmp/snappix-export",
                    auto_crop_on_shrink=False,
                )
            )

            restored = manager.load()
            self.assertTrue(restored.autostart_enabled)
            self.assertEqual(restored.theme, THEME_LIGHT)
            self.assertEqual(restored.post_capture_action, "clipboard")
            self.assertEqual(restored.hotkey_capture_window, "ctrl+shift+w")
            self.assertEqual(restored.editor_last_tab_behavior, "close_window")
            self.assertEqual(restored.export_preset, "print")
            self.assertEqual(restored.export_scale, 2.0)
            self.assertFalse(restored.export_keep_transparency)
            self.assertEqual(restored.batch_export_profile_key, "custom_profile")
            self.assertEqual(restored.batch_export_last_directory, "/tmp/snappix-export")
            self.assertEqual(len(restored.batch_export_profiles), 1)
            self.assertEqual(restored.batch_export_profiles[0]["key"], "custom_profile")
            self.assertFalse(restored.auto_crop_on_shrink)

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

    def test_normalize_editor_last_tab_behavior_falls_back_to_default(self) -> None:
        """
        Ensures invalid last-tab behaviors fall back to keep_open.
        """

        self.assertEqual(normalize_editor_last_tab_behavior("close_window"), "close_window")
        self.assertEqual(normalize_editor_last_tab_behavior("invalid"), "keep_open")

    def test_normalize_export_preset_falls_back_to_default(self) -> None:
        """
        Ensures invalid export presets fall back to docs.
        """

        self.assertEqual(normalize_export_preset("print"), "print")
        self.assertEqual(normalize_export_preset("unknown"), DEFAULT_EXPORT_PRESET)

    def test_normalize_export_scale(self) -> None:
        """
        Ensures export scale values normalize to 1/2/3.
        """

        self.assertEqual(normalize_export_scale(2), 2.0)
        self.assertEqual(normalize_export_scale("3"), 3.0)
        self.assertEqual(normalize_export_scale("bad"), DEFAULT_EXPORT_SCALE)

    def test_invalid_batch_export_profile_key_falls_back(self) -> None:
        """
        Ensures invalid active batch profile keys fall back to available profiles.
        """

        config = AppConfig(
            batch_export_profiles=[
                {
                    "key": "alpha",
                    "label": "Alpha",
                    "formats": ["png"],
                    "jpg_quality": 80,
                    "pdf_dpi": 150,
                }
            ],
            batch_export_profile_key="missing",
        )
        self.assertEqual(config.batch_export_profile_key, "alpha")

