"""
Shared Help menu dialogs (About, Manual) used by every Snappix window.

The image editor, the video editor, and the editor host window all expose the
same Help entries. Keeping the dialog bodies here means the empty editor host
shows exactly the dialogs a tab would show.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.constants import APP_NAME, build_about_dialog_html
from src.shortcuts import build_shortcuts_reference_text
from src.theme import get_theme_colors

EDITOR_MANUAL_INTRO = (
    "How it works:\n"
    "1) Use the capture panel to create a screenshot.\n"
    "2) Annotate with tools in the top bar.\n"
    "3) Save project, export image, or print from File menu.\n\n"
    "Open the ? toolbar button for icon explanations.\n\n"
)

VIDEO_MANUAL_INTRO = (
    "How it works:\n"
    "1) Record or import a video.\n"
    "2) Annotate with time-based tools in the top bar and timeline.\n"
    "3) Save the project or export a flattened MP4 from the File menu.\n\n"
)

HOST_MANUAL_INTRO = (
    "How it works:\n"
    "1) Use the capture panel to create a screenshot, or start from\n"
    "   File > New Canvas, File > Open Project, or File > Import Image.\n"
    "2) Annotate with tools in the top bar of the tab.\n"
    "3) Save project, export image, or print from the File menu.\n\n"
)


def show_about_dialog(parent: QWidget | None) -> None:
    """
    Displays About dialog information with clickable website links.

    Args:
        parent: Widget the dialog is parented to, or None.

    Returns:
        None
    """

    box = QMessageBox(parent)
    box.setWindowTitle(f"About {APP_NAME}")
    box.setIcon(QMessageBox.Icon.Information)
    box.setTextFormat(Qt.TextFormat.RichText)
    box.setText(build_about_dialog_html())
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    # QMessageBox labels do not open links unless explicitly enabled.
    colors = get_theme_colors()
    for label in box.findChildren(QLabel):
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        label.setOpenExternalLinks(True)
        label.setStyleSheet(
            f"QLabel {{ color: {colors.text}; }}"
            f"QLabel a {{ color: {colors.link}; text-decoration: underline; }}"
        )
    box.exec()


def show_manual_dialog(
    parent: QWidget | None,
    intro: str = EDITOR_MANUAL_INTRO,
    overrides: dict[str, str] | None = None,
) -> None:
    """
    Displays a short manual and the currently configured shortcuts.

    Args:
        parent: Widget the dialog is parented to, or None.
        intro: Leading explanation text shown above the shortcut reference.
        overrides: Optional user shortcut overrides from configuration.

    Returns:
        None
    """

    dialog = QDialog(parent)
    dialog.setWindowTitle("Manual")
    dialog.setModal(True)
    dialog.resize(720, 560)
    dialog.setMinimumSize(640, 420)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(10)

    text = QPlainTextEdit(dialog)
    text.setReadOnly(True)
    text.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
    text.setPlainText(intro + build_shortcuts_reference_text(overrides))
    text.setUndoRedoEnabled(False)
    text.moveCursor(QTextCursor.MoveOperation.Start)
    layout.addWidget(text, 1)

    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dialog)
    close_button = buttons.button(QDialogButtonBox.StandardButton.Close)
    if close_button is not None:
        close_button.clicked.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    dialog.exec()
