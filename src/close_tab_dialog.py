"""
Shared "Close Tab" confirmation dialog, used identically by the Image and
Video editors so the prompt never drifts between the two.
"""

from __future__ import annotations

from PySide6.QtWidgets import QAbstractButton, QDialogButtonBox, QMessageBox, QStyle, QWidget


def _force_button_order(box: QMessageBox, ordered: list[QAbstractButton]) -> None:
    """
    Pins the left-to-right order of a message box's buttons.

    QMessageBox otherwise sorts buttons by role using a platform-specific
    layout, so the same roles land in different positions on Linux and Windows.
    Re-appending the buttons after the button box's leading stretch keeps them
    right-aligned while making their order explicit and identical everywhere.

    Args:
        box: Message box whose buttons should be reordered.
        ordered: Buttons in the desired left-to-right order.

    Returns:
        None
    """

    button_box = box.findChild(QDialogButtonBox)
    if button_box is None:
        return
    layout = button_box.layout()
    if layout is None:
        return

    for button in ordered:
        layout.removeWidget(button)
    for button in ordered:
        layout.addWidget(button)


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
    _force_button_order(box, [cancel_button, close_button])

    box.exec()
    return box.clickedButton() is close_button
