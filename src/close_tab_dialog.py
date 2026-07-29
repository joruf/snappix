"""
Shared "Close Tab" confirmation dialog, used identically by the Image and
Video editors so the prompt never drifts between the two.
"""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QStyle, QWidget


def confirm_close_tab(parent: QWidget, message: str) -> bool:
    """
    Asks whether one editor tab with unsaved annotations may be closed.

    Args:
        parent: Owner widget for the dialog.
        message: Tab-specific warning text (image vs. video wording).

    Returns:
        bool: True when the user chose to close the tab.
    """

    box = QMessageBox(parent)
    box.setWindowTitle("Close Tab")
    box.setIcon(QMessageBox.Icon.Question)
    box.setText(message)

    style = box.style()
    cancel_button = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    cancel_button.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogCancelButton))
    close_button = box.addButton("Close Tab", QMessageBox.ButtonRole.DestructiveRole)
    close_button.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogCloseButton))
    box.setDefaultButton(cancel_button)

    box.exec()
    return box.clickedButton() is close_button
