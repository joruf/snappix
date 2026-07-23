"""
Application settings dialog.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.config import (
    EDITOR_LAST_TAB_BEHAVIORS,
    POST_CAPTURE_ACTIONS,
    AppConfig,
    default_capture_save_directory,
    normalize_editor_last_tab_behavior,
    normalize_hotkey_spec,
    normalize_post_capture_action,
    sanitize_editor_shortcut_map,
)
from src.global_hotkeys import GlobalHotkeyManager, hotkey_spec_to_pynput
from src.shortcuts import (
    EDITOR_SHORTCUT_DEFINITIONS,
    find_shortcut_conflicts,
    is_valid_shortcut_spec,
    normalize_editor_shortcuts,
    resolved_shortcut_text,
    shortcut_spec_to_sequences,
)


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
        self.resize(640, 520)
        self._config = config
        self._shortcut_edits: dict[str, QKeySequenceEdit] = {}

        root_layout = QVBoxLayout(self)
        tabs = QTabWidget(self)
        tabs.addTab(self._build_general_tab(config), "General")
        tabs.addTab(self._build_shortcuts_tab(config), "Editor Shortcuts")
        root_layout.addWidget(tabs)

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

    def _build_general_tab(self, config: AppConfig) -> QWidget:
        """
        Builds the general settings tab.

        Args:
            config: Current application configuration.

        Returns:
            QWidget: General settings page.
        """

        page = QWidget(self)
        layout = QVBoxLayout(page)
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

        self.auto_crop_on_shrink_checkbox = QCheckBox(
            "Auto-crop canvas when content shrinks"
        )
        self.auto_crop_on_shrink_checkbox.setToolTip(
            "When enabled, unused canvas margins are cropped automatically after "
            "deleting or moving content. Expanding the canvas for overflow always "
            "stays active."
        )
        self.auto_crop_on_shrink_checkbox.setChecked(bool(config.auto_crop_on_shrink))
        form.addRow("Canvas:", self.auto_crop_on_shrink_checkbox)

        save_directory_row = QHBoxLayout()
        initial_save_directory = (
            config.capture_save_directory.strip() or default_capture_save_directory()
        )
        self.save_directory_edit = QLineEdit(initial_save_directory)
        self.save_directory_edit.setPlaceholderText(default_capture_save_directory())
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._browse_save_directory)
        save_directory_row.addWidget(self.save_directory_edit, 1)
        save_directory_row.addWidget(browse_button)
        form.addRow("Save folder:", save_directory_row)

        layout.addLayout(form)
        layout.addStretch(1)
        return page

    def _build_shortcuts_tab(self, config: AppConfig) -> QWidget:
        """
        Builds the editable editor shortcuts tab.

        Args:
            config: Current application configuration.

        Returns:
            QWidget: Shortcuts settings page.
        """

        page = QWidget(self)
        layout = QVBoxLayout(page)
        hint = QLabel(
            "Click a shortcut field and press the desired keys. "
            "Clear a field to remove the binding. Use Reset to restore defaults."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.shortcuts_table = QTableWidget(0, 3, page)
        self.shortcuts_table.setHorizontalHeaderLabels(["Action", "Shortcut", ""])
        self.shortcuts_table.verticalHeader().setVisible(False)
        self.shortcuts_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.shortcuts_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = self.shortcuts_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.shortcuts_table, 1)

        overrides = normalize_editor_shortcuts(config.editor_shortcuts)
        for definition in EDITOR_SHORTCUT_DEFINITIONS:
            row = self.shortcuts_table.rowCount()
            self.shortcuts_table.insertRow(row)

            label_item = QTableWidgetItem(f"{definition.category}: {definition.label}")
            label_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.shortcuts_table.setItem(row, 0, label_item)

            editor = QKeySequenceEdit(page)
            editor.setClearButtonEnabled(True)
            current_spec = resolved_shortcut_text(definition.action_id, overrides)
            sequences = shortcut_spec_to_sequences(current_spec)
            if sequences:
                editor.setKeySequence(sequences[0])
            else:
                editor.clear()
            self._shortcut_edits[definition.action_id] = editor
            self.shortcuts_table.setCellWidget(row, 1, editor)

            reset_button = QPushButton("Reset")
            reset_button.setToolTip(f"Restore default: {definition.default}")
            reset_button.clicked.connect(
                lambda _checked=False, action_id=definition.action_id: self._reset_shortcut(
                    action_id
                )
            )
            self.shortcuts_table.setCellWidget(row, 2, reset_button)

        reset_all_row = QHBoxLayout()
        reset_all_row.addStretch(1)
        reset_all_button = QPushButton("Reset All Shortcuts")
        reset_all_button.clicked.connect(self._reset_all_shortcuts)
        reset_all_row.addWidget(reset_all_button)
        layout.addLayout(reset_all_row)
        return page

    def _reset_shortcut(self, action_id: str) -> None:
        """
        Restores one shortcut editor to its default binding.

        Args:
            action_id: Shortcut action identifier.

        Returns:
            None
        """

        editor = self._shortcut_edits.get(action_id)
        if editor is None:
            return
        sequences = shortcut_spec_to_sequences(
            resolved_shortcut_text(action_id, {})
        )
        if sequences:
            editor.setKeySequence(sequences[0])
        else:
            editor.clear()

    def _reset_all_shortcuts(self) -> None:
        """
        Restores every editor shortcut field to its default binding.

        Returns:
            None
        """

        for action_id in self._shortcut_edits:
            self._reset_shortcut(action_id)

    def _collect_editor_shortcuts(self) -> dict[str, str]:
        """
        Collects shortcut overrides that differ from defaults.

        Returns:
            dict[str, str]: Persisted override map.
        """

        overrides: dict[str, str] = {}
        for definition in EDITOR_SHORTCUT_DEFINITIONS:
            editor = self._shortcut_edits[definition.action_id]
            sequence = editor.keySequence()
            if sequence.isEmpty():
                current = ""
            else:
                current = sequence.toString(QKeySequence.SequenceFormat.PortableText)
            default_sequences = shortcut_spec_to_sequences(definition.default)
            default_primary = (
                default_sequences[0].toString(QKeySequence.SequenceFormat.PortableText)
                if default_sequences
                else ""
            )
            # Persist only when the primary binding differs from the default primary.
            # Multi-default actions keep remaining defaults unless explicitly overridden.
            if current != default_primary:
                overrides[definition.action_id] = current
        return normalize_editor_shortcuts(overrides)

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
            export_preset=self._config.export_preset,
            export_scale=self._config.export_scale,
            export_keep_transparency=self._config.export_keep_transparency,
            batch_export_profiles=[
                dict(profile) for profile in self._config.batch_export_profiles
            ],
            batch_export_profile_key=self._config.batch_export_profile_key,
            batch_export_last_directory=self._config.batch_export_last_directory,
            auto_crop_on_shrink=self.auto_crop_on_shrink_checkbox.isChecked(),
            editor_shortcuts=sanitize_editor_shortcut_map(self._collect_editor_shortcuts()),
        )

    def _browse_save_directory(self) -> None:
        """
        Opens a folder picker for the capture save directory.

        Returns:
            None
        """

        current_path = self.save_directory_edit.text().strip()
        start_dir = current_path if current_path else default_capture_save_directory()
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

        for action_id, editor in self._shortcut_edits.items():
            sequence = editor.keySequence()
            spec = (
                ""
                if sequence.isEmpty()
                else sequence.toString(QKeySequence.SequenceFormat.PortableText)
            )
            if not is_valid_shortcut_spec(spec):
                QMessageBox.warning(
                    self,
                    "Invalid Shortcut",
                    f"The shortcut for \"{action_id}\" is invalid.",
                )
                return

        # Validate conflicts against the effective resolved map (defaults + overrides).
        conflicts = find_shortcut_conflicts(candidate.editor_shortcuts)
        if conflicts:
            sequence_text, first_id, second_id = conflicts[0]
            QMessageBox.warning(
                self,
                "Shortcut Conflict",
                f"The shortcut \"{sequence_text}\" is assigned more than once. "
                "Choose unique bindings for each action.",
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
