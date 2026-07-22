"""
Application theme definitions and Qt Style Sheet generation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtGui import QColor

THEME_DARK = "dark"
THEME_LIGHT = "light"
VALID_THEMES = frozenset({THEME_DARK, THEME_LIGHT})
DEFAULT_THEME = THEME_DARK

_current_theme = DEFAULT_THEME


@dataclass(frozen=True, slots=True)
class ThemeColors:
    """
    Defines color tokens used by Snappix UI chrome.

    Attributes:
        window_bg: Main window background.
        surface: Panel and control background.
        surface_alt: Secondary surface (toolbar groups, tabs).
        text: Primary text color.
        text_muted: Secondary label text color.
        border: Default border color.
        border_strong: Emphasized border color.
        accent: Primary action and selection color.
        accent_hover: Hover state for accent controls.
        button_bg: Default button background.
        button_hover: Default button hover background.
        button_checked_text: Text on checked tool buttons.
        input_bg: Text fields and spin box background.
        dropdown_bg: Combo box popup background.
        link: Link-style button text color.
        link_hover: Link-style button hover text color.
        palette_border: Border around color palette swatches.
        scrollbar_bg: Scrollbar track background.
        scrollbar_handle: Scrollbar handle color.
        editor_workspace: Gray pasteboard behind the drawable document.
        editor_document_border: Border around the document canvas.
    """

    window_bg: str
    surface: str
    surface_alt: str
    text: str
    text_muted: str
    border: str
    border_strong: str
    accent: str
    accent_hover: str
    button_bg: str
    button_hover: str
    button_checked_text: str
    input_bg: str
    dropdown_bg: str
    link: str
    link_hover: str
    palette_border: str
    scrollbar_bg: str
    scrollbar_handle: str
    editor_workspace: str
    editor_document_border: str


_DARK_COLORS = ThemeColors(
    window_bg="#1f2430",
    surface="#242833",
    surface_alt="#222938",
    text="#e7ecf2",
    text_muted="#9fb2c9",
    border="#3e4657",
    border_strong="#434d63",
    accent="#2f7dd1",
    accent_hover="#4591e4",
    button_bg="#2f3543",
    button_hover="#3a4357",
    button_checked_text="#ffffff",
    input_bg="#2f3543",
    dropdown_bg="#2a3040",
    link="#78b8ff",
    link_hover="#a9d1ff",
    palette_border="#59657c",
    scrollbar_bg="#2a3040",
    scrollbar_handle="#434d63",
    editor_workspace="#4d525c",
    editor_document_border="#2f3541",
)

_LIGHT_COLORS = ThemeColors(
    window_bg="#f5f6f8",
    surface="#ffffff",
    surface_alt="#eef1f5",
    text="#1e293b",
    text_muted="#64748b",
    border="#cbd5e1",
    border_strong="#94a3b8",
    accent="#2563eb",
    accent_hover="#1d4ed8",
    button_bg="#e2e8f0",
    button_hover="#cbd5e1",
    button_checked_text="#ffffff",
    input_bg="#ffffff",
    dropdown_bg="#ffffff",
    link="#2563eb",
    link_hover="#1d4ed8",
    palette_border="#94a3b8",
    scrollbar_bg="#eef1f5",
    scrollbar_handle="#cbd5e1",
    editor_workspace="#b8bcc4",
    editor_document_border="#8b939e",
)

_THEME_COLORS: dict[str, ThemeColors] = {
    THEME_DARK: _DARK_COLORS,
    THEME_LIGHT: _LIGHT_COLORS,
}

_EDITOR_DARK_ACCENT = "#c73838"
_EDITOR_DARK_ACCENT_HOVER = "#d64545"
_EDITOR_LIGHT_ACCENT = "#c73838"
_EDITOR_LIGHT_ACCENT_HOVER = "#a61f1f"


def normalize_theme_name(theme_name: str) -> str:
    """
    Returns a supported theme name, falling back to the default.

    Args:
        theme_name: Requested theme identifier.

    Returns:
        str: Valid theme name.
    """

    if theme_name in VALID_THEMES:
        return theme_name
    return DEFAULT_THEME


def set_current_theme(theme_name: str) -> str:
    """
    Stores the active theme for helper style builders.

    Args:
        theme_name: Theme identifier to activate.

    Returns:
        str: Normalized active theme name.
    """

    global _current_theme
    _current_theme = normalize_theme_name(theme_name)
    return _current_theme


def current_theme_name() -> str:
    """
    Returns the currently active theme identifier.

    Returns:
        str: Active theme name.
    """

    return _current_theme


def get_theme_colors(theme_name: str | None = None) -> ThemeColors:
    """
    Resolves color tokens for one theme.

    Args:
        theme_name: Optional theme identifier; uses current theme when omitted.

    Returns:
        ThemeColors: Theme color tokens.
    """

    resolved = normalize_theme_name(theme_name or _current_theme)
    return _THEME_COLORS[resolved]


def get_editor_accent_colors(theme_name: str | None = None) -> tuple[str, str]:
    """
    Returns accent colors for editor chrome aligned with the red editor logo.

    Args:
        theme_name: Optional theme identifier; uses current theme when omitted.

    Returns:
        tuple[str, str]: Accent and hover accent hex colors.
    """

    resolved = normalize_theme_name(theme_name or _current_theme)
    if resolved == THEME_LIGHT:
        return _EDITOR_LIGHT_ACCENT, _EDITOR_LIGHT_ACCENT_HOVER
    return _EDITOR_DARK_ACCENT, _EDITOR_DARK_ACCENT_HOVER


def build_editor_accent_stylesheet(theme_name: str | None = None) -> str:
    """
    Builds editor-only accent overrides scoped to the editor host window.

    Args:
        theme_name: Optional theme identifier; uses current theme when omitted.

    Returns:
        str: Editor accent stylesheet.
    """

    colors = get_theme_colors(theme_name)
    accent, accent_hover = get_editor_accent_colors(theme_name)
    checked_text = colors.button_checked_text
    return (
        f"#editorHost QToolButton:checked {{"
        f" background: {accent}; border: 1px solid {accent}; color: {checked_text};"
        f" }}"
        f"#editorHost QPushButton#primaryButton {{"
        f" background: {accent}; color: {checked_text}; border: none;"
        f" }}"
        f"#editorHost QPushButton#primaryButton:hover {{ background: {accent_hover}; }}"
        f"#editorHost QTabBar::tab:selected {{ background: {accent}; color: {checked_text}; }}"
        f"#editorHost QSlider::handle:horizontal {{ background: {accent}; }}"
        f"#editorHost QComboBox QAbstractItemView {{"
        f" selection-background-color: {accent}; selection-color: {checked_text};"
        f" }}"
        f"#editorHost QMenu::item:selected {{ background: {accent}; color: {checked_text}; }}"
    )


def build_application_stylesheet(theme_name: str | None = None) -> str:
    """
    Builds the global Qt Style Sheet for Snappix.

    Args:
        theme_name: Optional theme identifier; uses current theme when omitted.

    Returns:
        str: Complete application stylesheet.
    """

    colors = get_theme_colors(theme_name)
    return (
        f"QWidget {{ background: {colors.surface}; color: {colors.text}; }}"
        f"QMainWindow {{ background: {colors.window_bg}; color: {colors.text}; }}"
        f"QMenuBar, QMenu, QStatusBar {{ background: {colors.surface_alt}; color: {colors.text}; }}"
        f"QMenu::item:selected {{ background: {colors.accent}; color: {colors.button_checked_text}; }}"
        f"QToolButton, QPushButton {{"
        f" background: {colors.button_bg}; color: {colors.text};"
        f" border: 1px solid {colors.border_strong}; border-radius: 4px; padding: 4px 8px;"
        f" }}"
        f"QToolButton:checked {{"
        f" background: {colors.accent}; border: 1px solid {colors.accent};"
        f" color: {colors.button_checked_text};"
        f" }}"
        f"QPushButton:hover, QToolButton:hover {{ background: {colors.button_hover}; }}"
        f"QPushButton#primaryButton {{"
        f" background: {colors.accent}; color: {colors.button_checked_text};"
        f" border: none; padding: 6px 10px; border-radius: 4px;"
        f" }}"
        f"QPushButton#primaryButton:hover {{ background: {colors.accent_hover}; }}"
        f"QPushButton#linkButton {{"
        f" color: {colors.link}; text-decoration: underline;"
        f" background: transparent; border: none; padding: 2px 4px;"
        f" }}"
        f"QPushButton#linkButton:hover {{ color: {colors.link_hover}; }}"
        f"QSpinBox, QComboBox, QLineEdit, QTextEdit, QPlainTextEdit {{"
        f" background: {colors.input_bg}; color: {colors.text};"
        f" border: 1px solid {colors.border_strong}; border-radius: 4px; padding: 3px;"
        f" }}"
        f"QComboBox::drop-down {{ border: none; }}"
        f"QComboBox QAbstractItemView {{"
        f" background: {colors.dropdown_bg}; color: {colors.text};"
        f" selection-background-color: {colors.accent};"
        f" selection-color: {colors.button_checked_text};"
        f" border: 1px solid {colors.border_strong};"
        f" }}"
        f"QSlider::groove:horizontal {{"
        f" background: {colors.border}; height: 6px; border-radius: 3px;"
        f" }}"
        f"QSlider::handle:horizontal {{"
        f" background: {colors.accent}; width: 14px; margin: -4px 0; border-radius: 7px;"
        f" }}"
        f"QFrame {{ border: 1px solid {colors.border}; border-radius: 5px; }}"
        f"QFrame[toolbarGroup=\"true\"] {{"
        f" border: 1px solid {colors.border_strong}; border-radius: 6px;"
        f" background: {colors.surface_alt};"
        f" }}"
        f"QFrame[toolbarGroup=\"true\"] QLabel {{ color: {colors.text}; }}"
        f"QWidget#editorToolbar QToolButton, QWidget#editorToolbar QPushButton {{"
        f" padding: 1px 5px; min-height: 18px; max-height: 24px;"
        f" }}"
        f"QWidget#editorToolbar QComboBox, QWidget#editorToolbar QSpinBox {{"
        f" padding: 1px 3px; min-height: 18px; max-height: 24px;"
        f" }}"
        f"QWidget#editorToolbar QLabel#mutedLabel {{"
        f" font-size: 10px; color: {colors.text_muted}; margin: 0; padding: 0;"
        f" }}"
        f"QWidget#editorToolbar QSlider::groove:horizontal {{ height: 4px; }}"
        f"QWidget#editorToolbar QSlider::handle:horizontal {{"
        f" width: 12px; height: 12px; margin: -4px 0; border-radius: 6px;"
        f" }}"
        f"QLabel#mutedLabel {{ font-size: 11px; color: {colors.text_muted}; }}"
        f"QLabel#titleLabel {{ font-size: 16px; font-weight: 700; color: {colors.text}; }}"
        f"QTabWidget::pane {{ border: 1px solid {colors.border_strong}; background: {colors.window_bg}; }}"
        f"QTabBar::tab {{"
        f" background: {colors.button_bg}; color: {colors.text};"
        f" border: 1px solid {colors.border_strong}; padding: 6px 12px; margin-right: 2px;"
        f" }}"
        f"QTabBar::tab:selected {{ background: {colors.accent}; color: {colors.button_checked_text}; }}"
        f"QTabBar::tab:hover:!selected {{ background: {colors.button_hover}; }}"
        f"QDialog {{ background: {colors.surface}; color: {colors.text}; }}"
        f"QDialogButtonBox QPushButton {{ min-width: 72px; }}"
        f"QScrollBar:vertical {{ background: {colors.scrollbar_bg}; width: 12px; margin: 0; }}"
        f"QScrollBar::handle:vertical {{ background: {colors.scrollbar_handle}; min-height: 24px; border-radius: 6px; }}"
        f"QScrollBar:horizontal {{ background: {colors.scrollbar_bg}; height: 12px; margin: 0; }}"
        f"QScrollBar::handle:horizontal {{ background: {colors.scrollbar_handle}; min-width: 24px; border-radius: 6px; }}"
    )


def palette_button_stylesheet(color: QColor, theme_name: str | None = None) -> str:
    """
    Builds stylesheet text for one palette color swatch button.

    Args:
        color: Swatch color.
        theme_name: Optional theme identifier.

    Returns:
        str: Button stylesheet.
    """

    from PySide6.QtGui import QColor as QtColor

    colors = get_theme_colors(theme_name)
    return (
        "QPushButton {"
        f"background: {color.name(QtColor.NameFormat.HexArgb)};"
        f"border: 1px solid {colors.palette_border};"
        "border-radius: 3px;"
        "padding: 0px;"
        "}"
    )


def color_preview_button_stylesheet(color: QColor, theme_name: str | None = None) -> str:
    """
    Builds stylesheet text for one color preview button.

    Args:
        color: Preview color.
        theme_name: Optional theme identifier.

    Returns:
        str: Button stylesheet.
    """

    from PySide6.QtGui import QColor as QtColor

    colors = get_theme_colors(theme_name)
    return (
        "QPushButton {"
        f"background: {color.name(QtColor.NameFormat.HexArgb)};"
        f"color: {colors.text};"
        f"border: 1px solid {colors.border_strong};"
        "border-radius: 4px;"
        "padding: 4px 8px;"
        "}"
    )
