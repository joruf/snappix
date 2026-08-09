"""
Dialog for resizing the whole document.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.document_scale import MAX_DOCUMENT_SIZE, MIN_DOCUMENT_SIZE, scaled_size

# Percentages offered next to the pixel fields, since "half size" is asked for far
# more often than a specific number.
PERCENT_PRESETS = (25, 50, 75, 100, 150, 200)


class ImageSizeDialog(QDialog):
    """
    Asks for a new document size in pixels or percent.
    """

    def __init__(self, width: int, height: int, parent: QWidget | None = None) -> None:
        """
        Initializes the dialog with the current document size.

        Args:
            width: Current document width in pixels.
            height: Current document height in pixels.
            parent: Optional parent widget.
        """

        super().__init__(parent)
        self.setWindowTitle("Image Size")
        self.setModal(True)
        self._source_width = max(1, int(width))
        self._source_height = max(1, int(height))
        self._syncing = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(8)

        self.width_spin = QSpinBox()
        self.width_spin.setRange(MIN_DOCUMENT_SIZE, MAX_DOCUMENT_SIZE)
        self.width_spin.setSuffix(" px")
        self.width_spin.setValue(self._source_width)
        form.addRow("Width:", self.width_spin)

        self.height_spin = QSpinBox()
        self.height_spin.setRange(MIN_DOCUMENT_SIZE, MAX_DOCUMENT_SIZE)
        self.height_spin.setSuffix(" px")
        self.height_spin.setValue(self._source_height)
        form.addRow("Height:", self.height_spin)

        self.percent_combo = QComboBox()
        self.percent_combo.addItem("Custom", 0)
        for percent in PERCENT_PRESETS:
            self.percent_combo.addItem(f"{percent} %", percent)
        self.percent_combo.setToolTip("Scale relative to the current size.")
        form.addRow("Preset:", self.percent_combo)

        layout.addLayout(form)

        self.keep_aspect_check = QCheckBox("Keep aspect ratio")
        self.keep_aspect_check.setChecked(True)
        layout.addWidget(self.keep_aspect_check)

        self.summary_label = QLabel()
        self.summary_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.summary_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.width_spin.valueChanged.connect(self._on_width_changed)
        self.height_spin.valueChanged.connect(self._on_height_changed)
        self.percent_combo.currentIndexChanged.connect(self._on_percent_changed)
        self._refresh_summary()

    def _on_width_changed(self, value: int) -> None:
        """
        Mirrors a width change onto the height when the ratio is locked.

        Args:
            value: New width in pixels.

        Returns:
            None
        """

        if self._syncing:
            return
        if self.keep_aspect_check.isChecked():
            _, height = scaled_size(
                self._source_width,
                self._source_height,
                target_width=value,
                keep_aspect=True,
            )
            self._set_without_feedback(self.height_spin, height)
        self._refresh_summary()

    def _on_height_changed(self, value: int) -> None:
        """
        Mirrors a height change onto the width when the ratio is locked.

        Args:
            value: New height in pixels.

        Returns:
            None
        """

        if self._syncing:
            return
        if self.keep_aspect_check.isChecked():
            width, _ = scaled_size(
                self._source_width,
                self._source_height,
                target_height=value,
                keep_aspect=True,
            )
            self._set_without_feedback(self.width_spin, width)
        self._refresh_summary()

    def _on_percent_changed(self, _index: int) -> None:
        """
        Applies a percentage preset to both fields.

        Args:
            _index: Unused combo index.

        Returns:
            None
        """

        percent = int(self.percent_combo.currentData() or 0)
        if percent <= 0:
            return
        factor = percent / 100.0
        self._set_without_feedback(self.width_spin, max(1, round(self._source_width * factor)))
        self._set_without_feedback(self.height_spin, max(1, round(self._source_height * factor)))
        self._refresh_summary()

    def _set_without_feedback(self, spin: QSpinBox, value: int) -> None:
        """
        Sets a spin box value without triggering the mirroring handlers.

        Args:
            spin: Target spin box.
            value: New value.

        Returns:
            None
        """

        self._syncing = True
        try:
            spin.setValue(int(value))
        finally:
            self._syncing = False

    def _refresh_summary(self) -> None:
        """
        Updates the before/after summary line.

        Returns:
            None
        """

        width, height = self.selected_size()
        percent = (width / self._source_width) * 100.0
        self.summary_label.setText(
            f"{self._source_width} x {self._source_height} px  ->  "
            f"{width} x {height} px  ({percent:.0f} %)"
        )

    def selected_size(self) -> tuple[int, int]:
        """
        Returns the chosen document size.

        Returns:
            tuple[int, int]: Width and height in pixels.
        """

        return int(self.width_spin.value()), int(self.height_spin.value())
