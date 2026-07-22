"""
Application settings dialog.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.config import (
    EDITOR_LAST_TAB_BEHAVIORS,
    POST_CAPTURE_ACTIONS,
    AppConfig,
    normalize_editor_last_tab_behavior,
    normalize_hotkey_spec,
    normalize_post_capture_action,
)
from src.global_hotkeys import GlobalHotkeyManager, hotkey_spec_to_pynput


class SettingsDialog(QDialog):
    """
    Edits persisted Snappix application settings.
    """

    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        """
        Initializes the settings dialog with current values.

        Args:
            config: Current application configuration.
            parent: Optional parent widget.
        """

        super().__init__(parent)
        self.setWindowTitle("Snappix Settings")
        self.setModal(True)
        self.resize(520, 360)
        self._config = config

        root_layout = QVBoxLayout(self)
        form = QFormLayout()

        self.hotkeys_enabled_checkbox = QCheckBox("Enable global hotkeys")
        self.hotkeys_enabled_checkbox.setToolTip(
            "Register system-wide shortcuts for capture actions."
        )
        self.hotkeys_enabled_checkbox.setChecked(config.hotkeys_enabled)
        form.addRow("", self.hotkeys_enabled_checkbox)

        self.hotkey_region_edit = QLineEdit(config.hotkey_capture_region)
        self.hotkey_region_edit.setPlaceholderText("ctrl+shift+a")
        form.addRow("Capture area:", self.hotkey_region_edit)

        self.hotkey_window_edit = QLineEdit(config.hotkey_capture_window)
        self.hotkey_window_edit.setPlaceholderText("ctrl+shift+w")
        form.addRow("Capture window:", self.hotkey_window_edit)

        self.hotkey_fullscreen_edit = QLineEdit(config.hotkey_capture_fullscreen)
        self.hotkey_fullscreen_edit.setPlaceholderText("ctrl+shift+f")
        form.addRow("Capture fullscreen:", self.hotkey_fullscreen_edit)

        self.post_capture_combo = QComboBox()
        for action_key, action_label in POST_CAPTURE_ACTIONS.items():
            self.post_capture_combo.addItem(action_label, action_key)
        current_index = self.post_capture_combo.findData(
            normalize_post_capture_action(config.post_capture_action)
        )
        if current_index >= 0:
            self.post_capture_combo.setCurrentIndex(current_index)
        form.addRow("After capture:", self.post_capture_combo)

        self.editor_last_tab_combo = QComboBox()
        for behavior_key, behavior_label in EDITOR_LAST_TAB_BEHAVIORS.items():
            self.editor_last_tab_combo.addItem(behavior_label, behavior_key)
        behavior_index = self.editor_last_tab_combo.findData(
            normalize_editor_last_tab_behavior(config.editor_last_tab_behavior)
        )
        if behavior_index >= 0:
            self.editor_last_tab_combo.setCurrentIndex(behavior_index)
        form.addRow("When last tab closes:", self.editor_last_tab_combo)

        save_directory_row = QHBoxLayout()
        self.save_directory_edit = QLineEdit(config.capture_save_directory)
        self.save_directory_edit.setPlaceholderText("~/Pictures/Snappix")
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._browse_save_directory)
        save_directory_row.addWidget(self.save_directory_edit, 1)
        save_directory_row.addWidget(browse_button)
        form.addRow("Save folder:", save_directory_row)

        root_layout.addLayout(form)

        if not GlobalHotkeyManager.is_supported():
            warning = QMessageBox(self)
            warning.setIcon(QMessageBox.Icon.Warning)
            warning.setWindowTitle("Global Hotkeys")
            warning.setText(
                "The pynput package is not installed. Global hotkeys stay disabled "
                "until dependencies are updated."
            )
            warning.setStandardButtons(QMessageBox.StandardButton.Ok)
            warning.show()
            self.hotkeys_enabled_checkbox.setChecked(False)
            self.hotkeys_enabled_checkbox.setEnabled(False)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_settings)
        buttons.rejected.connect(self.reject)
        root_layout.addWidget(buttons)

    def build_config(self) -> AppConfig:
        """
        Builds an updated configuration model from dialog fields.

        Returns:
            AppConfig: Updated configuration.
        """

        return AppConfig(
            autostart_enabled=self._config.autostart_enabled,
            theme=self._config.theme,
            hotkeys_enabled=self.hotkeys_enabled_checkbox.isChecked(),
            hotkey_capture_region=normalize_hotkey_spec(self.hotkey_region_edit.text()),
            hotkey_capture_window=normalize_hotkey_spec(self.hotkey_window_edit.text()),
            hotkey_capture_fullscreen=normalize_hotkey_spec(
                self.hotkey_fullscreen_edit.text()
            ),
            post_capture_action=normalize_post_capture_action(
                str(self.post_capture_combo.currentData())
            ),
            capture_save_directory=self.save_directory_edit.text().strip(),
            editor_last_tab_behavior=normalize_editor_last_tab_behavior(
                str(self.editor_last_tab_combo.currentData())
            ),
        )

    def _browse_save_directory(self) -> None:
        """
        Opens a folder picker for the capture save directory.

        Returns:
            None
        """

        current_path = self.save_directory_edit.text().strip()
        start_dir = str(Path(current_path).expanduser()) if current_path else str(
            Path.home() / "Pictures"
        )
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select Capture Save Folder",
            start_dir,
        )
        if selected:
            self.save_directory_edit.setText(selected)

    def _accept_settings(self) -> None:
        """
        Validates settings and closes the dialog on success.

        Returns:
            None
        """

        candidate = self.build_config()
        if candidate.hotkeys_enabled:
            invalid_field = self._find_invalid_hotkey_field(candidate)
            if invalid_field is not None:
                QMessageBox.warning(
                    self,
                    "Invalid Hotkey",
                    f"The hotkey for \"{invalid_field}\" is invalid. "
                    "Use formats like ctrl+shift+a or ctrl+shift+f1.",
                )
                return
        self._config = candidate
        self.accept()

    def _find_invalid_hotkey_field(self, config: AppConfig) -> str | None:
        """
        Returns the first invalid hotkey field label.

        Args:
            config: Candidate configuration.

        Returns:
            str | None: Invalid field label or None when all are valid.
        """

        checks = [
            ("Capture area", config.hotkey_capture_region),
            ("Capture window", config.hotkey_capture_window),
            ("Capture fullscreen", config.hotkey_capture_fullscreen),
        ]
        for label, spec in checks:
            if hotkey_spec_to_pynput(spec) is None:
                return label
        return None
