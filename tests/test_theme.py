"""
Unit tests for theme helpers and stylesheet generation.
"""

from __future__ import annotations

import unittest

from src.theme import (
    DEFAULT_THEME,
    THEME_DARK,
    THEME_LIGHT,
    THEME_SEPIA,
    THEME_SLATE,
    build_application_stylesheet,
    build_editor_accent_stylesheet,
    get_editor_accent_colors,
    get_theme_colors,
    normalize_theme_name,
    set_current_theme,
    current_theme_name,
)

try:
    from PySide6.QtGui import QColor

    HAS_PYSIDE6 = True
except ModuleNotFoundError:
    HAS_PYSIDE6 = False


class TestThemeHelpers(unittest.TestCase):
    """
    Verifies theme normalization and stylesheet generation.
    """

    def test_normalize_theme_name_falls_back_to_default(self) -> None:
        """
        Ensures unknown theme names use the default theme.
        """

        self.assertEqual(normalize_theme_name("unknown"), DEFAULT_THEME)
        self.assertEqual(normalize_theme_name(THEME_LIGHT), THEME_LIGHT)

    def test_set_current_theme_updates_active_name(self) -> None:
        """
        Ensures current theme tracking is updated.
        """

        set_current_theme(THEME_LIGHT)
        self.assertEqual(current_theme_name(), THEME_LIGHT)
        set_current_theme(THEME_DARK)

    def test_build_application_stylesheet_contains_theme_tokens(self) -> None:
        """
        Ensures generated stylesheets include theme-specific colors.
        """

        dark_stylesheet = build_application_stylesheet(THEME_DARK)
        light_stylesheet = build_application_stylesheet(THEME_LIGHT)
        self.assertIn(get_theme_colors(THEME_DARK).accent, dark_stylesheet)
        self.assertIn(get_theme_colors(THEME_LIGHT).accent, light_stylesheet)
        self.assertIn("QComboBox", dark_stylesheet)
        self.assertIn("QTextEdit", light_stylesheet)
        self.assertIn('QToolButton[toolLocked="true"]:checked', dark_stylesheet)

    def test_build_editor_accent_stylesheet_uses_blue_editor_colors(self) -> None:
        """
        Ensures editor accent overrides use the blue logo palette.
        """

        editor_stylesheet = build_editor_accent_stylesheet(THEME_DARK)
        accent, _hover = get_editor_accent_colors(THEME_DARK)
        self.assertEqual(accent, "#2f7dd1")
        self.assertIn("#editorHost", editor_stylesheet)
        self.assertIn(accent, editor_stylesheet)
        self.assertIn('#editorHost QToolButton[toolLocked="true"]:checked', editor_stylesheet)

    def test_slate_and_sepia_themes_are_supported(self) -> None:
        """
        Ensures Slate and Sepia resolve to dedicated color palettes.
        """

        self.assertEqual(normalize_theme_name(THEME_SLATE), THEME_SLATE)
        self.assertEqual(normalize_theme_name(THEME_SEPIA), THEME_SEPIA)
        slate = get_theme_colors(THEME_SLATE)
        sepia = get_theme_colors(THEME_SEPIA)
        self.assertNotEqual(slate.window_bg, get_theme_colors(THEME_DARK).window_bg)
        self.assertNotEqual(sepia.window_bg, get_theme_colors(THEME_LIGHT).window_bg)
        self.assertIn(slate.accent, build_application_stylesheet(THEME_SLATE))
        self.assertIn(sepia.accent, build_application_stylesheet(THEME_SEPIA))
        self.assertEqual(get_editor_accent_colors(THEME_SEPIA)[0], "#2563eb")
        self.assertEqual(get_editor_accent_colors(THEME_SLATE)[0], "#2f7dd1")
        set_current_theme(THEME_SLATE)
        self.assertEqual(current_theme_name(), THEME_SLATE)
        set_current_theme(THEME_DARK)

    def test_build_capture_accent_stylesheet_uses_red_capture_colors(self) -> None:
        """
        Ensures capture accent overrides use the red logo palette.
        """

        from src.theme import (
            build_capture_accent_stylesheet,
            get_capture_accent_colors,
            get_capture_accent_text_color,
        )

        capture_stylesheet = build_capture_accent_stylesheet(THEME_DARK)
        accent, _hover = get_capture_accent_colors(THEME_DARK)
        self.assertEqual(accent, "#b92f2f")
        self.assertIn("#capturePanel", capture_stylesheet)
        self.assertIn(accent, capture_stylesheet)
        self.assertIn("font-weight: 700", capture_stylesheet)
        self.assertEqual(get_capture_accent_text_color(THEME_DARK), "#ffffff")
        self.assertIn("#ffffff", capture_stylesheet)
        light_accent, _light_hover = get_capture_accent_colors(THEME_LIGHT)
        self.assertEqual(light_accent, "#b42318")
        self.assertEqual(get_capture_accent_text_color(THEME_LIGHT), "#ffffff")
        light_stylesheet = build_capture_accent_stylesheet(THEME_LIGHT)
        self.assertIn(light_accent, light_stylesheet)
        self.assertIn("#ffffff", light_stylesheet)

    def test_dynamic_button_styles_use_theme_border(self) -> None:
        """
        Ensures palette and preview button styles include theme borders.
        """

        if not HAS_PYSIDE6:
            self.skipTest("PySide6 is required for dynamic button style tests")

        from src.theme import color_preview_button_stylesheet, palette_button_stylesheet

        color = QColor("#ff0000")
        dark_palette = palette_button_stylesheet(color, THEME_DARK)
        light_palette = palette_button_stylesheet(color, THEME_LIGHT)
        self.assertIn(get_theme_colors(THEME_DARK).palette_border, dark_palette)
        self.assertIn(get_theme_colors(THEME_LIGHT).palette_border, light_palette)
        preview = color_preview_button_stylesheet(color, THEME_LIGHT)
        self.assertIn(get_theme_colors(THEME_LIGHT).border_strong, preview)
