"""
Application settings dialog.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
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
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.config import (
    DEFAULT_HOTKEY_MEASURE_BOX,
    EDITOR_LAST_TAB_BEHAVIORS,
    POST_CAPTURE_ACTIONS,
    AppConfig,
    default_capture_save_directory,
    default_workspace_directory,
    normalize_editor_last_tab_behavior,
    normalize_hotkey_spec,
    normalize_post_capture_action,
    normalize_resize_handle_position,
    normalize_resize_handle_size,
    normalize_tool_brush_hardness,
    normalize_tool_stroke_styles,
    normalize_tool_stroke_widths,
    RESIZE_HANDLE_POSITIONS,
    sanitize_editor_shortcut_map,
)
from src.global_hotkeys import GlobalHotkeyManager, hotkey_spec_to_pynput
from src.measurebox.settings import MeasureBoxSettings
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

    def __init__(
        self,
        config: AppConfig,
        parent: QWidget | None = None,
        measure_box_settings: MeasureBoxSettings | None = None,
    ) -> None:
        """
        Initializes the settings dialog with current values.

        Args:
            config: Current application configuration.
            parent: Optional parent widget.
            measure_box_settings: Optional MeasureBox appearance settings.
        """

        super().__init__(parent)
        self.setWindowTitle("Snappix Settings")
        self.setModal(True)
        self.resize(640, 520)
        self._config = config
        self._measure_box_settings = measure_box_settings or MeasureBoxSettings()
        self._shortcut_edits: dict[str, QKeySequenceEdit] = {}
        self._measure_line_rgba = self._measure_box_settings.line_rgba
        self._measure_fill_rgba = self._measure_box_settings.fill_rgba

        root_layout = QVBoxLayout(self)
        tabs = QTabWidget(self)
        tabs.addTab(self._build_general_tab(config), "General")
        tabs.addTab(self._build_measure_box_tab(config, self._measure_box_settings), "MeasureBox")
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

        from src.paths import supports_window_capture
        from src.video_recorder import has_ffmpeg

        self.hotkey_window_edit = QLineEdit(config.hotkey_capture_window)
        self.hotkey_window_edit.setPlaceholderText("ctrl+shift+w")
        if supports_window_capture():
            form.addRow("Capture window:", self.hotkey_window_edit)
        else:
            self.hotkey_window_edit.hide()

        self.hotkey_fullscreen_edit = QLineEdit(config.hotkey_capture_fullscreen)
        self.hotkey_fullscreen_edit.setPlaceholderText("ctrl+shift+f")
        form.addRow("Capture fullscreen:", self.hotkey_fullscreen_edit)

        self.hotkey_video_edit = QLineEdit(config.hotkey_capture_video)
        self.hotkey_video_edit.setPlaceholderText("ctrl+shift+v")
        self.hotkey_recording_pause_resume_edit = QLineEdit(
            config.hotkey_recording_pause_resume
        )
        self.hotkey_recording_pause_resume_edit.setPlaceholderText("ctrl+shift+p")
        self.hotkey_recording_stop_edit = QLineEdit(config.hotkey_recording_stop)
        self.hotkey_recording_stop_edit.setPlaceholderText("ctrl+shift+r")
        if has_ffmpeg():
            form.addRow("Capture video:", self.hotkey_video_edit)
            form.addRow(
                "Pause/resume recording:", self.hotkey_recording_pause_resume_edit
            )
            form.addRow("Stop recording:", self.hotkey_recording_stop_edit)
        else:
            self.hotkey_video_edit.hide()
            self.hotkey_recording_pause_resume_edit.hide()
            self.hotkey_recording_stop_edit.hide()

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

        self.resize_handle_size_spin = QSpinBox()
        self.resize_handle_size_spin.setRange(6, 24)
        self.resize_handle_size_spin.setSuffix(" px")
        self.resize_handle_size_spin.setToolTip(
            "Edge length of the eight resize handles shown around selected objects."
        )
        self.resize_handle_size_spin.setValue(normalize_resize_handle_size(config.resize_handle_size))
        form.addRow("Selection handle size:", self.resize_handle_size_spin)

        self.resize_handle_position_combo = QComboBox()
        for position_key, position_label in RESIZE_HANDLE_POSITIONS.items():
            self.resize_handle_position_combo.addItem(position_label, position_key)
        position_index = self.resize_handle_position_combo.findData(
            normalize_resize_handle_position(config.resize_handle_position)
        )
        if position_index >= 0:
            self.resize_handle_position_combo.setCurrentIndex(position_index)
        self.resize_handle_position_combo.setToolTip(
            "Placement of resize handles relative to the selection border."
        )
        form.addRow("Selection handle position:", self.resize_handle_position_combo)

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

        workspace_directory_row = QHBoxLayout()
        initial_workspace_directory = (
            config.workspace_directory.strip() or default_workspace_directory()
        )
        self.workspace_directory_edit = QLineEdit(initial_workspace_directory)
        self.workspace_directory_edit.setPlaceholderText(default_workspace_directory())
        self.workspace_directory_edit.setToolTip(
            "Unsaved image and video tabs, annotations, and session recovery data "
            "are stored here while Snappix is closed."
        )
        workspace_browse_button = QPushButton("Browse...")
        workspace_browse_button.clicked.connect(self._browse_workspace_directory)
        workspace_directory_row.addWidget(self.workspace_directory_edit, 1)
        workspace_directory_row.addWidget(workspace_browse_button)
        form.addRow("Workspace folder:", workspace_directory_row)

        layout.addLayout(form)
        layout.addStretch(1)
        return page

    def _build_measure_box_tab(
        self,
        config: AppConfig,
        measure_box_settings: MeasureBoxSettings,
    ) -> QWidget:
        """
        Builds the MeasureBox settings tab (hotkey + appearance).

        Args:
            config: Current application configuration.
            measure_box_settings: Current MeasureBox appearance settings.

        Returns:
            QWidget: MeasureBox settings page.
        """

        page = QWidget(self)
        layout = QVBoxLayout(page)
        hint = QLabel(
            "Start MeasureBox from Capture with the global hotkey below, or click "
            "the MeasureBox button. Drag to draw a measurement, hold Left Shift to "
            "edit, and press Esc to exit."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()
        hotkey_row = QHBoxLayout()
        self.hotkey_measure_box_edit = QLineEdit(config.hotkey_measure_box)
        self.hotkey_measure_box_edit.setPlaceholderText(DEFAULT_HOTKEY_MEASURE_BOX)
        self.hotkey_measure_box_edit.setToolTip(
            "Global shortcut to start MeasureBox. Example: ctrl+shift+m"
        )
        hotkey_row.addWidget(self.hotkey_measure_box_edit, 1)
        reset_hotkey_button = QPushButton("Reset")
        reset_hotkey_button.setToolTip(f"Restore default: {DEFAULT_HOTKEY_MEASURE_BOX}")
        reset_hotkey_button.clicked.connect(
            lambda: self.hotkey_measure_box_edit.setText(DEFAULT_HOTKEY_MEASURE_BOX)
        )
        hotkey_row.addWidget(reset_hotkey_button)
        form.addRow("Start MeasureBox:", hotkey_row)

        line_row = QHBoxLayout()
        self.measure_line_color_button = QPushButton("Choose...")
        self.measure_line_color_button.clicked.connect(self._choose_measure_line_color)
        line_row.addWidget(self.measure_line_color_button)
        line_row.addStretch(1)
        form.addRow("Line color:", line_row)

        fill_row = QHBoxLayout()
        self.measure_fill_color_button = QPushButton("Choose...")
        self.measure_fill_color_button.clicked.connect(self._choose_measure_fill_color)
        fill_row.addWidget(self.measure_fill_color_button)
        fill_row.addStretch(1)
        form.addRow("Fill color:", fill_row)

        self.measure_ruler_checkbox = QCheckBox("Show pixel ruler (px)")
        self.measure_ruler_checkbox.setChecked(measure_box_settings.ruler_enabled)
        self.measure_ruler_checkbox.toggled.connect(self._sync_measure_ruler_outside_enabled)
        form.addRow("", self.measure_ruler_checkbox)

        self.measure_ruler_outside_checkbox = QCheckBox("Ruler outside rectangle")
        self.measure_ruler_outside_checkbox.setChecked(measure_box_settings.ruler_outside)
        self.measure_ruler_outside_checkbox.setEnabled(measure_box_settings.ruler_enabled)
        form.addRow("", self.measure_ruler_outside_checkbox)

        self.measure_crosshair_checkbox = QCheckBox("Show Left Shift crosshair")
        self.measure_crosshair_checkbox.setChecked(measure_box_settings.crosshair_enabled)
        form.addRow("", self.measure_crosshair_checkbox)

        layout.addLayout(form)
        layout.addStretch(1)
        self._refresh_measure_color_buttons()
        return page

    def _sync_measure_ruler_outside_enabled(self, checked: bool) -> None:
        self.measure_ruler_outside_checkbox.setEnabled(checked)

    def _choose_measure_line_color(self) -> None:
        selected = QColorDialog.getColor(
            QColor(*self._measure_line_rgba),
            self,
            "Select MeasureBox line color (with alpha)",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if not selected.isValid():
            return
        self._measure_line_rgba = (
            selected.red(),
            selected.green(),
            selected.blue(),
            selected.alpha(),
        )
        self._refresh_measure_color_buttons()

    def _choose_measure_fill_color(self) -> None:
        selected = QColorDialog.getColor(
            QColor(*self._measure_fill_rgba),
            self,
            "Select MeasureBox fill color (with alpha)",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if not selected.isValid():
            return
        self._measure_fill_rgba = (
            selected.red(),
            selected.green(),
            selected.blue(),
            selected.alpha(),
        )
        self._refresh_measure_color_buttons()

    def _refresh_measure_color_buttons(self) -> None:
        line = QColor(*self._measure_line_rgba)
        fill = QColor(*self._measure_fill_rgba)
        self.measure_line_color_button.setText(line.name(QColor.NameFormat.HexArgb).upper())
        self.measure_line_color_button.setStyleSheet(
            f"background-color: {line.name(QColor.NameFormat.HexArgb)};"
        )
        self.measure_fill_color_button.setText(fill.name(QColor.NameFormat.HexArgb).upper())
        self.measure_fill_color_button.setStyleSheet(
            f"background-color: {fill.name(QColor.NameFormat.HexArgb)};"
        )

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
            hotkey_capture_video=normalize_hotkey_spec(self.hotkey_video_edit.text()),
            hotkey_recording_pause_resume=normalize_hotkey_spec(
                self.hotkey_recording_pause_resume_edit.text()
            ),
            hotkey_recording_stop=normalize_hotkey_spec(
                self.hotkey_recording_stop_edit.text()
            ),
            hotkey_measure_box=normalize_hotkey_spec(self.hotkey_measure_box_edit.text()),
            post_capture_action=normalize_post_capture_action(
                str(self.post_capture_combo.currentData())
            ),
            capture_save_directory=self.save_directory_edit.text().strip(),
            workspace_directory=self.workspace_directory_edit.text().strip(),
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
            resize_handle_size=normalize_resize_handle_size(
                self.resize_handle_size_spin.value()
            ),
            resize_handle_position=normalize_resize_handle_position(
                str(self.resize_handle_position_combo.currentData())
            ),
            editor_shortcuts=sanitize_editor_shortcut_map(self._collect_editor_shortcuts()),
            tool_stroke_widths=normalize_tool_stroke_widths(self._config.tool_stroke_widths),
            tool_brush_hardness=normalize_tool_brush_hardness(self._config.tool_brush_hardness),
            tool_stroke_styles=normalize_tool_stroke_styles(self._config.tool_stroke_styles),
        )

    def build_measure_box_settings(self) -> MeasureBoxSettings:
        """
        Builds updated MeasureBox appearance settings from dialog fields.

        Returns:
            MeasureBoxSettings: Updated MeasureBox settings.
        """

        return MeasureBoxSettings(
            line_rgba=self._measure_line_rgba,
            fill_rgba=self._measure_fill_rgba,
            ruler_enabled=self.measure_ruler_checkbox.isChecked(),
            ruler_outside=self.measure_ruler_outside_checkbox.isChecked(),
            crosshair_enabled=self.measure_crosshair_checkbox.isChecked(),
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

    def _browse_workspace_directory(self) -> None:
        """
        Opens a folder picker for the editor workspace directory.

        Returns:
            None
        """

        current_path = self.workspace_directory_edit.text().strip()
        start_dir = current_path if current_path else default_workspace_directory()
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select Workspace Folder",
            start_dir,
        )
        if selected:
            self.workspace_directory_edit.setText(selected)

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
            ("Capture area", config.hotkey_capture_region, True),
            (
                "Capture window",
                config.hotkey_capture_window,
                not self.hotkey_window_edit.isHidden(),
            ),
            ("Capture fullscreen", config.hotkey_capture_fullscreen, True),
            (
                "Capture video",
                config.hotkey_capture_video,
                not self.hotkey_video_edit.isHidden(),
            ),
            (
                "Pause/resume recording",
                config.hotkey_recording_pause_resume,
                not self.hotkey_recording_pause_resume_edit.isHidden(),
            ),
            (
                "Stop recording",
                config.hotkey_recording_stop,
                not self.hotkey_recording_stop_edit.isHidden(),
            ),
            ("Start MeasureBox", config.hotkey_measure_box, True),
        ]
        for label, spec, enabled in checks:
            if not enabled:
                continue
            if hotkey_spec_to_pynput(spec) is None:
                return label
        return None
