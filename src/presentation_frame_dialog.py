"""
Settings dialog for the export presentation frame.

Every control writes straight into a live preview, because the frame is a purely
visual choice: numbers like "6% padding" or "20% shadow" mean nothing until you
see them around the actual screenshot being exported.
"""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from src.presentation_frame import (
    ASPECT_AUTO,
    ASPECT_RATIOS,
    BACKGROUND_GRADIENT,
    BACKGROUND_SOLID,
    BACKGROUND_TRANSPARENT,
    PresentationFrame,
    apply_presentation_frame,
    default_gradient_end,
)

PREVIEW_WIDTH = 320
PREVIEW_HEIGHT = 200


class PresentationFrameDialog(QDialog):
    """
    Class PresentationFrameDialog

    Modal editor for the padding, corner, shadow, and backdrop of export frames.
    """

    def __init__(
        self,
        frame: PresentationFrame,
        source: QPixmap | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """
        Args:
            frame: Frame settings to edit.
            source: Optional screenshot used for the preview.
            parent: Optional parent widget.
        """

        super().__init__(parent)
        self.setWindowTitle("Presentation Frame")
        self._frame = frame
        self._source = source if source is not None and not source.isNull() else None
        self._background_color = QColor(frame.background_color)
        if not self._background_color.isValid():
            self._background_color = QColor(PresentationFrame().background_color)

        layout = QVBoxLayout(self)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(PREVIEW_WIDTH, PREVIEW_HEIGHT)
        layout.addWidget(self.preview_label)

        form = QFormLayout()

        self.enabled_check = QCheckBox("Frame exports")
        self.enabled_check.setChecked(frame.enabled)
        self.enabled_check.toggled.connect(self._refresh)
        form.addRow("", self.enabled_check)

        self.padding_slider = QSlider(Qt.Horizontal)
        self.padding_slider.setRange(0, 25)
        self.padding_slider.setValue(int(round(frame.padding_percent)))
        self.padding_slider.valueChanged.connect(self._refresh)
        self.padding_value = QLabel()
        form.addRow("Padding", self._with_value(self.padding_slider, self.padding_value))

        self.radius_slider = QSlider(Qt.Horizontal)
        self.radius_slider.setRange(0, 48)
        self.radius_slider.setValue(int(round(frame.corner_radius)))
        self.radius_slider.valueChanged.connect(self._refresh)
        self.radius_value = QLabel()
        form.addRow("Corners", self._with_value(self.radius_slider, self.radius_value))

        self.shadow_check = QCheckBox("Drop shadow")
        self.shadow_check.setChecked(frame.shadow_enabled)
        self.shadow_check.toggled.connect(self._refresh)
        form.addRow("", self.shadow_check)

        self.shadow_slider = QSlider(Qt.Horizontal)
        self.shadow_slider.setRange(0, 60)
        self.shadow_slider.setValue(int(round(frame.shadow_opacity * 100)))
        self.shadow_slider.valueChanged.connect(self._refresh)
        self.shadow_value = QLabel()
        form.addRow("Shadow", self._with_value(self.shadow_slider, self.shadow_value))

        self.background_combo = QComboBox()
        self.background_combo.addItem("Solid", BACKGROUND_SOLID)
        self.background_combo.addItem("Gradient", BACKGROUND_GRADIENT)
        self.background_combo.addItem("Transparent", BACKGROUND_TRANSPARENT)
        index = self.background_combo.findData(frame.background_mode)
        self.background_combo.setCurrentIndex(max(0, index))
        self.background_combo.currentIndexChanged.connect(self._refresh)
        self.color_button = QPushButton()
        self.color_button.setFixedWidth(48)
        self.color_button.clicked.connect(self._pick_color)
        background_row = QHBoxLayout()
        background_row.addWidget(self.background_combo, 1)
        background_row.addWidget(self.color_button)
        background_holder = QWidget()
        background_holder.setLayout(background_row)
        form.addRow("Backdrop", background_holder)

        self.aspect_combo = QComboBox()
        self.aspect_combo.addItem("Auto", ASPECT_AUTO)
        for ratio_key in ASPECT_RATIOS:
            self.aspect_combo.addItem(ratio_key, ratio_key)
        aspect_index = self.aspect_combo.findData(frame.aspect_ratio)
        self.aspect_combo.setCurrentIndex(max(0, aspect_index))
        self.aspect_combo.currentIndexChanged.connect(self._refresh)
        form.addRow("Aspect", self.aspect_combo)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._refresh()

    @staticmethod
    def _with_value(slider: QSlider, value_label: QLabel) -> QWidget:
        """
        Pairs one slider with its numeric readout.

        Args:
            slider: Slider to wrap.
            value_label: Label showing the current value.

        Returns:
            QWidget: Row widget holding both.
        """

        value_label.setMinimumWidth(42)
        value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(slider, 1)
        row.addWidget(value_label)
        holder = QWidget()
        holder.setLayout(row)
        return holder

    def _pick_color(self) -> None:
        """
        Opens the color picker for the backdrop color.

        Returns:
            None
        """

        chosen = QColorDialog.getColor(self._background_color, self, "Backdrop Color")
        if chosen.isValid():
            self._background_color = chosen
            self._refresh()

    def selected_frame(self) -> PresentationFrame:
        """
        Reads the dialog controls back into one frame.

        Returns:
            PresentationFrame: Frame described by the current controls.
        """

        mode = str(self.background_combo.currentData())
        gradient_end = ""
        if mode == BACKGROUND_GRADIENT:
            gradient_end = default_gradient_end(self._background_color).name()
        return PresentationFrame(
            enabled=self.enabled_check.isChecked(),
            padding_percent=float(self.padding_slider.value()),
            corner_radius=float(self.radius_slider.value()),
            shadow_enabled=self.shadow_check.isChecked(),
            shadow_opacity=self.shadow_slider.value() / 100.0,
            background_mode=mode,
            background_color=self._background_color.name(),
            gradient_end_color=gradient_end,
            aspect_ratio=str(self.aspect_combo.currentData()),
        )

    def _preview_source(self) -> QPixmap:
        """
        Returns a small stand-in image for the preview.

        Uses the real screenshot when one was handed in, so the preview shows
        the actual export rather than an abstract placeholder.

        Returns:
            QPixmap: Downscaled preview source.
        """

        if self._source is not None:
            return self._source.scaled(
                PREVIEW_WIDTH - 40,
                PREVIEW_HEIGHT - 40,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        placeholder = QPixmap(200, 130)
        placeholder.fill(QColor("#7F8794"))
        return placeholder

    def _refresh(self) -> None:
        """
        Rebuilds the preview and the slider readouts from the controls.

        Returns:
            None
        """

        self.padding_value.setText(f"{self.padding_slider.value()} %")
        self.radius_value.setText(f"{self.radius_slider.value()} px")
        self.shadow_value.setText(f"{self.shadow_slider.value()} %")

        mode = str(self.background_combo.currentData())
        self.color_button.setEnabled(mode != BACKGROUND_TRANSPARENT)
        self.color_button.setStyleSheet(
            f"background-color: {self._background_color.name()}; border: 1px solid palette(mid);"
        )
        self.shadow_slider.setEnabled(self.shadow_check.isChecked())

        frame = self.selected_frame()
        # The preview always renders framed, even while the feature is off, so
        # the settings can be dialed in before switching it on.
        preview_frame = frame if frame.enabled else replace(frame, enabled=True)
        rendered = apply_presentation_frame(self._preview_source(), preview_frame, scale=1.0)
        self.preview_label.setPixmap(
            rendered.scaled(
                PREVIEW_WIDTH,
                PREVIEW_HEIGHT,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )
