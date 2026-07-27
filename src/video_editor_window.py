"""
Video editor window/tab chrome for Snappix.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QMimeData, Qt, QSize, Signal
from PySide6.QtGui import QAction, QColor, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QStatusBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src.clipboard_json import get_json_clipboard_data, set_json_clipboard_data
from src.draw_style_defaults import create_default_style_state
from src.history_mixin import EditorHistoryMixin
from src.shortcut_registry_mixin import ShortcutRegistryMixin
from src.constants import APP_NAME
from src.flow_layout import FlowLayoutWidget
from src.timeline_widget import TimelineWidget
from src.tool_icons import build_playback_icon
from src.video_canvas import VideoCanvas
from src.video_models import VideoAnnotationModel, VideoProjectModel
from src.video_recorder import OverlaySegment, build_export_command
from src.video_storage import (
    build_video_project_model,
    load_video_project,
    save_video_project,
)
from src.video_vector_toolbar import VideoVectorToolbar

_VIDEO_ANNOTATIONS_CLIPBOARD_MIME = "application/x-snappix-video-annotations"


class VideoEditorWindow(EditorHistoryMixin, ShortcutRegistryMixin, QMainWindow):
    """
    Hosts the Snappix video editor UI: playback canvas, drawing tools, and timeline.
    """

    close_requested = Signal()
    content_changed = Signal()
    import_image_tab_requested = Signal()
    import_video_tab_requested = Signal()

    def __init__(self, video_path: str, video_width: int, video_height: int) -> None:
        """
        Initializes the video editor for one recorded video file.

        Args:
            video_path: Absolute path to the raw recorded video.
            video_width: Video width in pixels.
            video_height: Video height in pixels.
        """

        super().__init__()
        self.setWindowTitle(f"{APP_NAME} Video Editor")
        self.resize(1200, 860)
        self._video_path = video_path
        self._video_width = video_width
        self._video_height = video_height
        self._minimize_to_tray_on_close = True
        self._current_project_path = ""
        self._recovery_path = ""
        self._cached_duration_ms = 0
        self._session_video_source_path = ""
        self._recovery_dirty = False
        self._autosave_flushing = False
        self._is_playing = False
        self._annotations: list[VideoAnnotationModel] = []
        self._style = create_default_style_state()
        self._record_history = True
        self._history: list[dict[str, Any]] = []
        self._history_labels: list[str] = []
        self._history_index = -1
        self._pending_history_label: str | None = None
        self._syncing_history_list = False
        self._shortcut_actions: dict[str, QAction] = {}
        self._editor_shortcut_overrides: dict[str, str] = {}

        self.canvas = VideoCanvas()
        self.canvas.set_video_size(video_width, video_height)
        self.canvas.set_style(self._style)
        self.canvas.set_annotations(self._annotations)
        self.canvas.load_video(video_path)

        self._build_menu()

        self._vector_toolbar = VideoVectorToolbar(self)
        self._toolbar_widget = self._vector_toolbar.build()

        self.canvas.duration_changed.connect(self._on_duration_changed)
        self.canvas.position_changed.connect(self._on_position_changed)
        self.canvas.annotation_created.connect(self._on_annotation_created)
        self.canvas.annotations_removed.connect(self._on_annotations_removed)
        self.canvas.tool_changed.connect(self._on_canvas_tool_changed)
        self.canvas.content_changed.connect(self._on_canvas_content_changed)
        self.canvas.selection_style_changed.connect(self._vector_toolbar.on_selection_style_changed)
        self.canvas.zoom_changed.connect(self._on_zoom_changed)

        self.timeline = TimelineWidget()
        self.timeline.set_annotations(self._annotations)
        self.timeline.seek_requested.connect(self.canvas.set_position)
        self.timeline.annotation_time_changed.connect(self._on_annotation_time_changed)
        self.timeline.annotation_time_change_committed.connect(
            self._on_annotation_time_committed
        )

        self.timeline_pan_left = QToolButton()
        self.timeline_pan_left.setText("◀")
        self.timeline_pan_left.setToolTip("Jump timeline one page earlier")
        self.timeline_pan_left.clicked.connect(self.timeline.pan_left)

        self.timeline_pan_right = QToolButton()
        self.timeline_pan_right.setText("▶")
        self.timeline_pan_right.setToolTip("Jump timeline one page later")
        self.timeline_pan_right.clicked.connect(self.timeline.pan_right)

        timeline_row = QWidget()
        timeline_row.setObjectName("videoTimelineRow")
        timeline_layout = QHBoxLayout(timeline_row)
        timeline_layout.setContentsMargins(4, 0, 4, 0)
        timeline_layout.setSpacing(4)
        timeline_layout.addWidget(self.timeline_pan_left)
        timeline_layout.addWidget(self.timeline, 1)
        timeline_layout.addWidget(self.timeline_pan_right)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._toolbar_widget, 0)
        layout.addWidget(self.canvas, 3)
        layout.addWidget(timeline_row, 1)
        self.setCentralWidget(central)

        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage("Ready")
        self._toolbar_widget.setToolTip(
            "Video editor toolbar: drawing tools, history, playback, zoom, and style."
        )
        self.canvas.setToolTip(
            "Video preview: play the recording and place time-based annotations."
        )
        self.timeline.setToolTip(
            "Timeline: annotation tracks, duration bars, and playhead scrubbing."
        )
        self._autosave_timer = self.startTimer(30_000)
        self._push_history_state()

    def _build_menu(self) -> None:
        """
        Builds the File and Edit menus with project/import actions.

        Returns:
            None
        """

        file_menu = self.menuBar().addMenu("File")
        edit_menu = self.menuBar().addMenu("Edit")

        import_image_tab_action = QAction("Import Image as New Tab...", self)
        import_image_tab_action.setToolTip(
            "Open an external image in a new editor tab with a movable layer."
        )
        import_image_tab_action.triggered.connect(self.import_image_tab_requested.emit)
        file_menu.addAction(import_image_tab_action)

        import_video_tab_action = QAction("Import Video...", self)
        import_video_tab_action.setToolTip(
            "Open another external video file or Snappix video project in a new tab."
        )
        import_video_tab_action.triggered.connect(self.import_video_tab_requested.emit)
        file_menu.addAction(import_video_tab_action)

        file_menu.addSeparator()

        save_action = QAction("Save Project", self)
        save_action.setToolTip("Save the raw video and annotation timeline as a project file.")
        save_action.triggered.connect(self.save_project)
        file_menu.addAction(save_action)

        export_action = QAction("Export MP4...", self)
        export_action.setToolTip("Render a flattened MP4 with annotations burned in.")
        export_action.triggered.connect(self.export_mp4)
        file_menu.addAction(export_action)

        import_image_action = QAction("Import Image...", self)
        import_image_action.setToolTip(
            "Insert an image overlay on the current video at the playhead."
        )
        import_image_action.triggered.connect(self.import_image)
        edit_menu.addAction(import_image_action)

        edit_menu.addSeparator()

        copy_action = QAction("Copy", self)
        copy_action.setToolTip(
            "Copies the selected drawn objects for pasting into this or another tab."
        )
        copy_action.triggered.connect(self.copy_selected_annotations_to_clipboard)
        edit_menu.addAction(copy_action)
        self._register_shortcut_action("copy", copy_action)

        paste_action = QAction("Paste", self)
        paste_action.setToolTip(
            "Pastes drawn objects copied from this or another tab at the current playhead."
        )
        paste_action.triggered.connect(self.paste_annotations_from_clipboard)
        edit_menu.addAction(paste_action)
        self._register_shortcut_action("paste", paste_action)

        edit_menu.addSeparator()

        self.undo_action = QAction("Undo", self)
        self.undo_action.setToolTip("Undo the last change.")
        self.undo_action.triggered.connect(self.undo)
        edit_menu.addAction(self.undo_action)
        self._register_shortcut_action("undo", self.undo_action)

        self.redo_action = QAction("Redo", self)
        self.redo_action.setToolTip("Redo the last undone change.")
        self.redo_action.triggered.connect(self.redo)
        edit_menu.addAction(self.redo_action)
        self._register_shortcut_action("redo", self.redo_action)

        view_menu = self.menuBar().addMenu("View")

        zoom_in_action = QAction("Zoom In", self)
        zoom_in_action.setToolTip("Zooms into the video canvas.")
        zoom_in_action.triggered.connect(self.canvas.zoom_in)
        view_menu.addAction(zoom_in_action)
        self._register_shortcut_action("zoom_in", zoom_in_action)

        zoom_out_action = QAction("Zoom Out", self)
        zoom_out_action.setToolTip("Zooms out of the video canvas.")
        zoom_out_action.triggered.connect(self.canvas.zoom_out)
        view_menu.addAction(zoom_out_action)
        self._register_shortcut_action("zoom_out", zoom_out_action)

        zoom_reset_action = QAction("Reset Zoom", self)
        zoom_reset_action.setToolTip("Resets zoom to the default fit level.")
        zoom_reset_action.triggered.connect(self.canvas.reset_zoom)
        view_menu.addAction(zoom_reset_action)
        self._register_shortcut_action("zoom_reset", zoom_reset_action)

        self.apply_editor_shortcuts({})

    def import_image(self) -> None:
        """
        Prompts for one image file and inserts it as a time-ranged overlay.

        Returns:
            None
        """

        from src.media_import import IMAGE_FILE_FILTER

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Image",
            "",
            IMAGE_FILE_FILTER,
        )
        if not file_path:
            return
        if not self.canvas.import_image_file(file_path):
            QMessageBox.warning(
                self,
                APP_NAME,
                "Could not import the selected image file.",
            )
            return
        self.statusBar().showMessage("Image imported")
        self._mark_dirty()

    def copy_selected_annotations_to_clipboard(self) -> None:
        """
        Copies the selected drawn objects to the clipboard for cross-tab paste.

        Returns:
            None
        """

        annotations = self.canvas.collect_selected_annotations()
        if not annotations:
            self.statusBar().showMessage("Nothing selected to copy", 2500)
            return

        payload = {
            "kind": "video_annotations",
            "annotations": [annotation.to_dict() for annotation in annotations],
        }
        mime_data = QMimeData()
        set_json_clipboard_data(mime_data, _VIDEO_ANNOTATIONS_CLIPBOARD_MIME, payload)
        QGuiApplication.clipboard().setMimeData(mime_data)

        count = len(annotations)
        label = "object" if count == 1 else "objects"
        self.statusBar().showMessage(f"Copied {count} {label}", 3500)

    def paste_annotations_from_clipboard(self) -> None:
        """
        Pastes drawn objects copied from this or another video tab.

        Returns:
            None
        """

        clipboard = QGuiApplication.clipboard()
        mime_data = clipboard.mimeData()
        payload = get_json_clipboard_data(mime_data, _VIDEO_ANNOTATIONS_CLIPBOARD_MIME)
        if payload is None:
            return
        candidate = payload.get("annotations")
        if not isinstance(candidate, list):
            return
        annotations = [
            VideoAnnotationModel.from_dict(item) for item in candidate if isinstance(item, dict)
        ]
        if not annotations:
            return
        if not self.canvas.merge_annotations_payload(annotations):
            return

        count = len(annotations)
        label = "object" if count == 1 else "objects"
        self.statusBar().showMessage(f"Pasted {count} {label}", 2500)

    def style_state(self) -> StyleState:
        """
        Returns the active draw style for new video annotations.

        Returns:
            StyleState: Current style state.
        """

        return self._style

    def apply_tool_stroke_widths(
        self,
        widths: dict[str, int] | None,
        *,
        emit_signal: bool = False,
    ) -> None:
        """
        Restores persisted per-tool stroke widths for the vector toolbar.

        Args:
            widths: Tool id to width mapping.
            emit_signal: Unused; kept for parity with the image editor API.

        Returns:
            None
        """

        self._vector_toolbar.apply_tool_stroke_widths(widths, emit_signal=emit_signal)

    def apply_tool_stroke_styles(
        self,
        styles: dict[str, str] | None,
        *,
        emit_signal: bool = False,
    ) -> None:
        """
        Restores persisted per-tool stroke styles for the vector toolbar.

        Args:
            styles: Tool id to stroke-style mapping.
            emit_signal: Unused; kept for parity with the image editor API.

        Returns:
            None
        """

        self._vector_toolbar.apply_tool_stroke_styles(styles, emit_signal=emit_signal)

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        """
        Forwards toolbar button events to the vector toolbar controller.

        Returns:
            bool: True when the event was consumed.
        """

        if self._vector_toolbar.handle_event_filter(watched, event):
            return True
        return super().eventFilter(watched, event)

    def build_history_strip_widgets(self, parent: QWidget) -> list[QWidget]:
        """
        Builds the History group for the shared editor tool strip.

        Args:
            parent: Parent flow strip widget.

        Returns:
            list[QWidget]: History category box widgets.
        """

        history_box = QGroupBox("History", parent)
        history_box.setObjectName("toolCategoryBox")
        history_box.setToolTip("Undo and redo edits, and jump to earlier history states.")
        history_box.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Maximum,
        )
        history_layout = QHBoxLayout(history_box)
        history_layout.setContentsMargins(4, 10, 4, 4)
        history_layout.setSpacing(4)

        self.history_undo_button = QPushButton("Undo", history_box)
        self.history_undo_button.setToolTip("Undo the last change.")
        self.history_undo_button.clicked.connect(self.undo)
        history_layout.addWidget(self.history_undo_button)

        self.history_redo_button = QPushButton("Redo", history_box)
        self.history_redo_button.setToolTip("Redo the last undone change.")
        self.history_redo_button.clicked.connect(self.redo)
        history_layout.addWidget(self.history_redo_button)

        self.history_list_combo = QComboBox(history_box)
        self.history_list_combo.setMinimumWidth(160)
        self.history_list_combo.setMaxVisibleItems(16)
        self.history_list_combo.setToolTip("History entries with action names.")
        self.history_list_combo.currentIndexChanged.connect(self._on_history_entry_selected)
        history_layout.addWidget(self.history_list_combo)

        self.history_status_label = QLabel("1/1", history_box)
        self.history_status_label.setToolTip("Current history position.")
        history_layout.addWidget(self.history_status_label)

        self._update_undo_redo_actions()
        return [history_box]

    def build_playback_zoom_strip_widgets(self, parent: QWidget) -> list[QWidget]:
        """
        Builds Playback and Zoom groups for the shared tool strip.

        Args:
            parent: Parent flow strip widget.

        Returns:
            list[QWidget]: Playback and zoom category boxes.
        """

        strip_widgets: list[QWidget] = []

        playback_box = QGroupBox("Playback", parent)
        playback_box.setObjectName("toolCategoryBox")
        playback_box.setToolTip("Playback controls: play, stop, and mute the video preview.")
        playback_box.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Maximum,
        )
        playback_layout = QHBoxLayout(playback_box)
        playback_layout.setContentsMargins(4, 10, 4, 4)
        playback_layout.setSpacing(4)
        self.play_action = QAction(self)
        self.play_action.triggered.connect(self._toggle_playback)
        self.play_button = QToolButton(playback_box)
        self._configure_playback_button(
            self.play_button,
            self.play_action,
            icon_id="play",
            tooltip="Play",
        )
        playback_layout.addWidget(self.play_button)

        self.stop_action = QAction(self)
        self.stop_action.triggered.connect(self._stop_playback)
        self.stop_button = QToolButton(playback_box)
        self._configure_playback_button(
            self.stop_button,
            self.stop_action,
            icon_id="stop",
            tooltip="Stop and rewind to start",
        )
        playback_layout.addWidget(self.stop_button)

        self.sound_action = QAction(self)
        self.sound_action.setCheckable(True)
        self.sound_action.setChecked(False)
        self.sound_action.toggled.connect(self._on_sound_toggled)
        self.sound_button = QToolButton(playback_box)
        self._configure_playback_button(
            self.sound_button,
            self.sound_action,
            icon_id="sound_off",
            tooltip="Turn playback sound on",
        )
        playback_layout.addWidget(self.sound_button)
        self._sync_playback_action_icons()
        strip_widgets.append(playback_box)

        view_box = QGroupBox("View", parent)
        view_box.setObjectName("toolCategoryBox")
        view_box.setToolTip(
            "View options: show all annotation objects even outside the playhead range."
        )
        view_box.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Maximum,
        )
        view_layout = QHBoxLayout(view_box)
        view_layout.setContentsMargins(4, 10, 4, 4)
        view_layout.setSpacing(4)
        self.show_all_objects_checkbox = QCheckBox("Show all objects", view_box)
        self.show_all_objects_checkbox.setToolTip(
            "Display every drawing object on the canvas, even when the playhead "
            "is outside its timeline range."
        )
        self.show_all_objects_checkbox.toggled.connect(self._on_show_all_objects_toggled)
        view_layout.addWidget(self.show_all_objects_checkbox)
        strip_widgets.append(view_box)

        zoom_box = QGroupBox("Zoom", parent)
        zoom_box.setObjectName("toolCategoryBox")
        zoom_box.setToolTip("Zoom the video preview in, out, or fit to the frame.")
        zoom_box.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Maximum,
        )
        zoom_layout = QHBoxLayout(zoom_box)
        zoom_layout.setContentsMargins(4, 10, 4, 4)
        zoom_layout.setSpacing(4)
        self.zoom_out_button = QPushButton("-", zoom_box)
        self.zoom_out_button.setToolTip("Zoom out. Shortcut: Shift+Mouse Wheel.")
        self.zoom_out_button.clicked.connect(self.canvas.zoom_out)
        zoom_layout.addWidget(self.zoom_out_button)

        self.zoom_label = QLabel("100%", zoom_box)
        self.zoom_label.setMinimumWidth(42)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zoom_layout.addWidget(self.zoom_label)

        self.zoom_slider = QSlider(Qt.Orientation.Horizontal, zoom_box)
        self.zoom_slider.setRange(10, 400)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(100)
        self.zoom_slider.setToolTip("Zoom: left smaller, right larger")
        self.zoom_slider.valueChanged.connect(self._zoom_slider_changed)
        zoom_layout.addWidget(self.zoom_slider)

        self.zoom_in_button = QPushButton("+", zoom_box)
        self.zoom_in_button.setToolTip("Zoom in. Shortcut: Shift+Mouse Wheel.")
        self.zoom_in_button.clicked.connect(self.canvas.zoom_in)
        zoom_layout.addWidget(self.zoom_in_button)

        self.zoom_reset_button = QPushButton("Reset", zoom_box)
        self.zoom_reset_button.setToolTip("Reset zoom to fit the video frame.")
        self.zoom_reset_button.clicked.connect(self.canvas.reset_zoom)
        zoom_layout.addWidget(self.zoom_reset_button)
        strip_widgets.append(zoom_box)
        return strip_widgets

    def _configure_playback_button(
        self,
        button: QToolButton,
        action: QAction,
        *,
        icon_id: str,
        tooltip: str,
    ) -> None:
        """
        Applies the shared icon-only styling used by editor toolbar buttons.

        Args:
            button: Playback tool button widget.
            action: Backing action for the button.
            icon_id: Playback icon identifier.
            tooltip: Hover tooltip text.

        Returns:
            None
        """

        action.setIcon(build_playback_icon(icon_id))
        action.setToolTip(tooltip)
        button.setDefaultAction(action)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setIconSize(QSize(28, 28))
        button.setFixedSize(38, 34)

    def _sync_playback_action_icons(self) -> None:
        """
        Refreshes play/pause and sound icons to match the current playback state.

        Returns:
            None
        """

        if self._is_playing:
            self.play_action.setIcon(build_playback_icon("pause"))
            self.play_action.setToolTip("Pause")
        else:
            self.play_action.setIcon(build_playback_icon("play"))
            self.play_action.setToolTip("Play")

        if self.sound_action.isChecked():
            self.sound_action.setIcon(build_playback_icon("sound_on"))
            self.sound_action.setToolTip("Turn playback sound off")
        else:
            self.sound_action.setIcon(build_playback_icon("sound_off"))
            self.sound_action.setToolTip("Turn playback sound on")

    def set_resize_handle_style(self, *, size: float, position: str) -> None:
        """
        Applies resize-overlay handle settings to the video canvas.

        Args:
            size: Handle edge length in pixels.
            position: One of ``center``, ``inside``, or ``outside``.

        Returns:
            None
        """

        self.canvas.set_resize_handle_style(size=size, position=position)

    def _on_canvas_tool_changed(self, tool_id: str) -> None:
        """
        Keeps toolbar visuals aligned with programmatic canvas tool changes.

        Args:
            tool_id: New canvas tool identifier.

        Returns:
            None
        """

        self._vector_toolbar.sync_tool_from_canvas(tool_id)

    def _on_canvas_content_changed(self) -> None:
        """
        Captures history state when canvas content changes.

        Returns:
            None
        """

        action_label = self.canvas.consume_last_action_label()
        self._set_next_history_label(action_label)
        self._push_history_state()
        self._vector_toolbar.on_content_changed(action_label)
        self._mark_dirty()

    def _on_zoom_changed(self, zoom_factor: float) -> None:
        """
        Refreshes the zoom label/slider to match the canvas zoom factor.

        Args:
            zoom_factor: Current zoom factor.

        Returns:
            None
        """

        zoom_percent = int(round(zoom_factor * 100))
        self.zoom_label.setText(f"{zoom_percent}%")
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(max(10, min(400, zoom_percent)))
        self.zoom_slider.blockSignals(False)

    def _zoom_slider_changed(self, value: int) -> None:
        """
        Applies an absolute zoom from the slider percentage value.

        Args:
            value: Slider zoom percentage.

        Returns:
            None
        """

        self.canvas.set_zoom_factor(float(value) / 100.0)

    def _toggle_playback(self) -> None:
        """
        Toggles between video playback and pause.

        Returns:
            None
        """

        if self._is_playing:
            self.canvas.pause()
        else:
            self.canvas.play()
        self._is_playing = not self._is_playing
        self._sync_playback_action_icons()

    def _stop_playback(self) -> None:
        """
        Stops playback and rewinds the playhead to the start of the video.

        Returns:
            None
        """

        self.canvas.pause()
        self.canvas.set_position(0)
        self._is_playing = False
        self._sync_playback_action_icons()

    def _on_sound_toggled(self, enabled: bool) -> None:
        """
        Enables or disables video playback audio from the Sound toolbar switch.

        Args:
            enabled: True when the user wants sound on.

        Returns:
            None
        """

        self.canvas.set_audio_muted(not enabled)
        self._sync_playback_action_icons()

    def _on_show_all_objects_toggled(self, enabled: bool) -> None:
        """
        Shows or hides out-of-range annotations on the video canvas.

        Args:
            enabled: True to display every drawing object regardless of playhead time.

        Returns:
            None
        """

        self.canvas.set_show_all_annotations(enabled)

    def _on_duration_changed(self, duration_ms: int) -> None:
        """
        Propagates the loaded video duration to the timeline.

        Args:
            duration_ms: Video duration in milliseconds.

        Returns:
            None
        """

        self.timeline.set_duration(duration_ms)
        if duration_ms > 0:
            self._cached_duration_ms = duration_ms
            self.flush_recovery_snapshot()
            self._recovery_dirty = False

    def mark_recovery_dirty(self) -> None:
        """
        Marks the tab as having unsaved recovery changes for periodic auto-save.

        Returns:
            None
        """

        self._recovery_dirty = True

    def flush_initial_recovery_snapshot(self) -> None:
        """
        Writes the first recovery snapshot immediately after tab creation.

        Returns:
            None
        """

        self.flush_recovery_snapshot(force=True)
        self._recovery_dirty = False

    def prepare_recovery_assets(self) -> None:
        """
        Copies the source video into session storage for reliable auto-save.

        Returns:
            None
        """

        self._ensure_session_video_source()

    def _effective_duration_ms(self) -> int:
        """
        Returns the best-known video duration for persistence.

        Returns:
            int: Duration in milliseconds.
        """

        return max(
            self._cached_duration_ms,
            self.canvas.duration_ms(),
            self.timeline.duration_ms(),
        )

    def _ensure_session_video_source(self) -> str:
        """
        Ensures the tab references a session-local copy of the source video.

        Returns:
            str: Path to the video file used for project saves.
        """

        if self._session_video_source_path:
            session_source = Path(self._session_video_source_path)
            if session_source.is_file():
                return str(session_source)

        source = Path(self._video_path)
        if not self._recovery_path:
            return self._video_path if source.is_file() else ""

        from src.session_recovery import session_video_sources_dir

        sources_dir = session_video_sources_dir()
        sources_dir.mkdir(parents=True, exist_ok=True)
        target = sources_dir / f"{Path(self._recovery_path).stem}.mp4"
        if source.is_file():
            try:
                if not target.is_file() or target.stat().st_size != source.stat().st_size:
                    shutil.copy2(source, target)
            except OSError:
                if target.is_file():
                    self._session_video_source_path = str(target)
                    self._video_path = str(target)
                    return str(target)
                return self._video_path if source.is_file() else ""
            self._session_video_source_path = str(target)
            self._video_path = str(target)
            return str(target)

        if target.is_file():
            self._session_video_source_path = str(target)
            self._video_path = str(target)
            return str(target)

        return self._video_path if source.is_file() else ""

    def _build_project_model(self) -> VideoProjectModel:
        """
        Builds the serializable project model for the current editor state.

        Returns:
            VideoProjectModel: Current video project snapshot.
        """

        return build_video_project_model(
            video_path=self._video_path,
            video_width=self._video_width,
            video_height=self._video_height,
            duration_ms=max(1, self._effective_duration_ms()),
            framerate=30.0,
            annotation_models=self._annotations,
        )

    def load_video_project_model(
        self,
        project_model: VideoProjectModel,
        source_path: str = "",
    ) -> None:
        """
        Loads one parsed video project into the current editor tab.

        Args:
            project_model: Parsed project model.
            source_path: Optional user-facing project path for manual saves.

        Returns:
            None
        """

        self._video_width = project_model.video_width
        self._video_height = project_model.video_height
        self._annotations = list(project_model.annotations)
        self.canvas.set_video_size(self._video_width, self._video_height)
        self.canvas.set_annotations(self._annotations)
        self.canvas.load_video(self._video_path)
        self.timeline.set_annotations(self._annotations)
        if project_model.duration_ms > 0:
            self._cached_duration_ms = project_model.duration_ms
            self.timeline.set_duration(project_model.duration_ms)
        self._current_project_path = source_path.strip()
        self.canvas.refresh_visible_items()
        self.timeline.refresh()
        self._reset_history()

    def _serialize_state(self) -> dict[str, Any]:
        """
        Serializes the current annotation state for undo history.

        Returns:
            dict[str, Any]: Snapshot payload.
        """

        return {
            "annotations": [
                annotation.to_dict()
                for annotation in self._annotations
            ],
        }

    def _restore_state(self, snapshot: dict[str, Any]) -> None:
        """
        Restores annotation state from one history snapshot.

        Args:
            snapshot: Stored snapshot payload.

        Returns:
            None
        """

        annotations = [
            VideoAnnotationModel.from_dict(item)
            for item in list(snapshot.get("annotations", []))
            if isinstance(item, dict)
        ]

        self._record_history = False
        self._annotations.clear()
        self._annotations.extend(annotations)
        self.canvas.set_annotations(self._annotations)
        self.timeline.set_annotations(self._annotations)
        self.timeline.refresh()
        self._record_history = True

    def _on_history_navigated(self) -> None:
        """
        Marks the project dirty after undo/redo/history-list navigation.

        Returns:
            None
        """

        self._mark_dirty()

    def _update_undo_redo_actions(self) -> None:
        """
        Enables or disables undo and redo controls.

        Returns:
            None
        """

        can_undo = self._history_index > 0
        can_redo = self._history_index < len(self._history) - 1
        if hasattr(self, "undo_action"):
            self.undo_action.setEnabled(can_undo)
            self.redo_action.setEnabled(can_redo)
        if hasattr(self, "history_undo_button"):
            self.history_undo_button.setEnabled(can_undo)
            self.history_redo_button.setEnabled(can_redo)
            self.history_list_combo.setEnabled(bool(self._history))
            total_states = max(1, len(self._history))
            current_state = max(1, self._history_index + 1)
            self.history_status_label.setText(f"{current_state}/{total_states}")
            self._refresh_history_list()

    def _refresh_history_list(self) -> None:
        """
        Synchronizes visible history list entries and current position.

        Returns:
            None
        """

        self._syncing_history_list = True
        if not hasattr(self, "history_list_combo"):
            self._syncing_history_list = False
            return
        self.history_list_combo.clear()
        for index, label in enumerate(self._history_labels, start=1):
            self.history_list_combo.addItem(f"{index}: {label}")
        if self._history_index >= 0:
            self.history_list_combo.setCurrentIndex(self._history_index)
        self._syncing_history_list = False

    def set_recovery_path(self, path: str) -> None:
        """
        Sets the auto-save target path for this video editor tab.

        Args:
            path: Recovery project file path.

        Returns:
            None
        """

        self._recovery_path = path.strip()

    def recovery_path(self) -> str:
        """
        Returns the auto-save target path for this video editor tab.

        Returns:
            str: Recovery project file path.
        """

        return self._recovery_path

    def flush_recovery_snapshot(self, *, force: bool = False) -> None:
        """
        Persists the current tab state to its recovery project file.

        Args:
            force: When True, persist even if the media player no longer reports duration.

        Returns:
            None
        """

        if not self._recovery_path:
            return
        if self._autosave_flushing:
            return

        duration_ms = self._effective_duration_ms()
        if duration_ms <= 0 and not force:
            return

        from shiboken6 import isValid

        if not force:
            if not isValid(self):
                return
            canvas = getattr(self, "canvas", None)
            if canvas is None or not isValid(canvas):
                return

        from src.session_recovery import ensure_tab_recovery_path

        video_source = self._ensure_session_video_source()
        recovery_path = Path(self._recovery_path)
        if not video_source and not recovery_path.is_file():
            return

        self._autosave_flushing = True
        try:
            self._recovery_path = ensure_tab_recovery_path(self._recovery_path)
            model = self._build_project_model()
            save_source = video_source or str(recovery_path)
            try:
                save_video_project(self._recovery_path, model, save_source)
            except OSError:
                return

            if self._current_project_path and self._current_project_path != self._recovery_path:
                try:
                    save_video_project(self._current_project_path, model, save_source)
                except OSError:
                    return
        except RuntimeError:
            return
        finally:
            self._autosave_flushing = False

    def timerEvent(self, event) -> None:  # noqa: N802 - Qt API name
        """
        Runs periodic auto-save every 30 seconds.

        Args:
            event: Timer event from Qt.

        Returns:
            None
        """

        if event.timerId() != self._autosave_timer:
            super().timerEvent(event)
            return

        if not self._recovery_dirty:
            return
        self.flush_recovery_snapshot()
        self._recovery_dirty = False

    def _on_position_changed(self, position_ms: int) -> None:
        """
        Propagates the current playhead position to the timeline.

        Args:
            position_ms: Current playhead position in milliseconds.

        Returns:
            None
        """

        self.timeline.set_position(position_ms)

    def _on_annotation_created(self, _annotation: VideoAnnotationModel) -> None:
        """
        Refreshes the timeline after a new annotation was drawn on the canvas.

        Args:
            _annotation: Newly created annotation (already appended in-place).

        Returns:
            None
        """

        self.timeline.refresh()
        self._mark_dirty()

    def _on_annotations_removed(self) -> None:
        """
        Refreshes the timeline after one or more annotations were deleted.

        Returns:
            None
        """

        self.timeline.refresh()
        self._mark_dirty()

    def _on_annotation_time_changed(self, _annotation_id: str, _start_ms: int, _end_ms: int) -> None:
        """
        Refreshes the canvas after an annotation's time range changed on the timeline.

        Returns:
            None
        """

        self.canvas.refresh_visible_items()
        self.mark_recovery_dirty()

    def _on_annotation_time_committed(
        self,
        _annotation_id: str,
        _start_ms: int,
        _end_ms: int,
    ) -> None:
        """
        Records one undo step after a timeline drag finishes.

        Returns:
            None
        """

        self._set_next_history_label("Change annotation timing")
        self._push_history_state()
        self._mark_dirty()

    def _mark_dirty(self) -> None:
        """
        Marks the project as having unsaved changes.

        Returns:
            None
        """

        self.content_changed.emit()
        self.mark_recovery_dirty()

    def has_annotations(self) -> bool:
        """
        Indicates whether this tab currently contains annotations.

        Returns:
            bool: True when at least one annotation exists.
        """

        return len(self._annotations) > 0

    def confirm_close_if_needed(self) -> bool:
        """
        Requests close confirmation when this tab has drawn annotations.

        Returns:
            bool: True when the tab may be closed.
        """

        if not self.has_annotations():
            return True
        answer = QMessageBox.question(
            self,
            "Close Tab",
            "This video has unsaved annotations. Close it anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def set_minimize_to_tray_on_close(self, enabled: bool) -> None:
        """
        Enables or disables close-to-tray behavior.

        Args:
            enabled: True to hide on close, False to close normally.

        Returns:
            None
        """

        self._minimize_to_tray_on_close = enabled

    def closeEvent(self, event) -> None:
        """
        Handles close button behavior for tray minimization.

        Args:
            event: Qt close event.

        Returns:
            None
        """

        if self._minimize_to_tray_on_close:
            self.close_requested.emit()
            event.ignore()
            return
        if not self.confirm_close_if_needed():
            event.ignore()
            return
        self.flush_recovery_snapshot(force=True)
        autosave_timer = getattr(self, "_autosave_timer", 0)
        if autosave_timer:
            self.killTimer(autosave_timer)
            self._autosave_timer = 0
        super().closeEvent(event)

    def save_project(self) -> None:
        """
        Saves the current video project (raw video + annotation timeline) as .sfpv.

        Returns:
            None
        """

        start_path = self._current_project_path or str(Path.home() / "video-project.sfpv")
        path, _filter = QFileDialog.getSaveFileName(
            self,
            "Save Video Project",
            start_path,
            "Snappix Video Project (*.sfpv)",
        )
        if not path:
            return

        model = self._build_project_model()
        try:
            save_video_project(path, model, self._video_path)
        except OSError as exc:
            QMessageBox.warning(self, "Save Project", f"Could not save project:\n{exc}")
            return

        self._current_project_path = path
        self.statusBar().showMessage(f"Project saved to {path}", 5000)

    def export_mp4(self) -> None:
        """
        Renders a flattened MP4 with annotations burned in via ffmpeg compositing.

        Returns:
            None
        """

        options = self._prompt_export_options()
        if options is None:
            return
        include_audio = bool(options.get("include_audio", True))

        default_path = str(Path(self._video_path).with_suffix(".export.mp4"))
        path, _filter = QFileDialog.getSaveFileName(
            self,
            "Export Video",
            default_path,
            "MP4 Video (*.mp4)",
        )
        if not path:
            return

        self.statusBar().showMessage("Exporting video…")
        try:
            self._run_export(Path(path), include_audio=include_audio)
        except (OSError, RuntimeError) as exc:
            QMessageBox.warning(self, "Export Video", f"Could not export video:\n{exc}")
            self.statusBar().showMessage("Export failed", 5000)
            return

        self.statusBar().showMessage(f"Exported to {path}", 5000)

    def _prompt_export_options(self) -> dict[str, bool] | None:
        """
        Asks whether the exported MP4 should include audio.

        Returns:
            dict[str, bool] | None: Chosen options, or None when cancelled.
        """

        dialog = QDialog(self)
        dialog.setWindowTitle("Export Video Options")
        layout = QVBoxLayout(dialog)
        hint = QLabel(
            "Choose whether the exported MP4 should keep the recording audio track."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        include_audio = QCheckBox("Include audio in exported video", dialog)
        include_audio.setChecked(True)
        include_audio.setToolTip(
            "When unchecked, the exported MP4 is silent even if the recording has sound."
        )
        layout.addWidget(include_audio)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return {"include_audio": include_audio.isChecked()}

    def _run_export(self, output_path: Path, *, include_audio: bool = True) -> None:
        """
        Composites annotation-layer PNGs and invokes ffmpeg to burn them into the video.

        Args:
            output_path: Destination MP4 file path.
            include_audio: When True, keep audio in the export; when False, strip it.

        Returns:
            None
        """

        import subprocess
        import tempfile

        from PySide6.QtGui import QImage, QPainter
        from PySide6.QtWidgets import QStyleOptionGraphicsItem

        from src.video_canvas import build_annotation_item

        boundaries = sorted(
            {0, self.canvas.duration_ms()}
            | {annotation.start_ms for annotation in self._annotations}
            | {annotation.end_ms for annotation in self._annotations}
        )

        with tempfile.TemporaryDirectory(prefix="snappix-export-") as tmp_dir:
            tmp_root = Path(tmp_dir)
            segments: list[OverlaySegment] = []
            for index in range(len(boundaries) - 1):
                segment_start = boundaries[index]
                segment_end = boundaries[index + 1]
                if segment_end <= segment_start:
                    continue
                midpoint = (segment_start + segment_end) // 2
                visible = [
                    annotation
                    for annotation in self._annotations
                    if annotation.start_ms <= midpoint <= annotation.end_ms
                ]
                if not visible:
                    continue

                image = QImage(
                    self._video_width,
                    self._video_height,
                    QImage.Format.Format_ARGB32_Premultiplied,
                )
                image.fill(0)
                painter = QPainter(image)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                style_option = QStyleOptionGraphicsItem()
                for annotation in visible:
                    item = build_annotation_item(annotation)
                    if item is None:
                        continue
                    painter.save()
                    painter.translate(item.pos())
                    item.paint(painter, style_option, None)
                    painter.restore()
                painter.end()

                png_path = tmp_root / f"overlay_{index}.png"
                image.save(str(png_path), "PNG")
                segments.append(
                    OverlaySegment(
                        png_path=png_path,
                        start_s=segment_start / 1000.0,
                        end_s=segment_end / 1000.0,
                    )
                )

            command = build_export_command(
                Path(self._video_path),
                segments,
                output_path,
                include_audio=include_audio,
            )
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(result.stderr[-2000:] if result.stderr else "ffmpeg failed")
