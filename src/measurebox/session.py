"""One-shot MeasureBox session for Snappix Capture."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QCursor, QGuiApplication
from PySide6.QtWidgets import QApplication, QColorDialog, QMenu, QWidget

from src.global_hotkeys import EscapeListener
from src.measurebox.hotkeys import GlobalCtrlClickListener, GlobalHotkeyBridge
from src.measurebox.overlay_view import OverlayView
from src.measurebox.settings import MeasureBoxSettings, MeasureBoxSettingsManager
from src.paths import user_config_dir


class MeasureBoxSession(QObject):
    """
    Runs MeasureBox until Escape ends the session.

    Clicking the Capture button starts one session: draw mode is active so the
    user can draw a measurement rectangle that stays on screen (same persistent
    overlay behaviour as standalone MeasureBox). After the rectangle is created,
    the overlay switches to pass-through; hold Left Shift to edit again. A single
    Escape press ends the session and closes the overlay.
    """

    finished = Signal()

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        settings_path: Path | None = None,
        on_finished: Callable[[], None] | None = None,
    ) -> None:
        """
        Create a session that owns overlay, listeners, and settings.

        Args:
            parent: Optional Qt parent.
            settings_path: Optional JSON path for MeasureBox settings.
            on_finished: Optional callback when the session ends.
        """

        super().__init__(parent)
        self._on_finished = on_finished
        path = settings_path or (user_config_dir() / "measurebox.json")
        self._settings_manager = MeasureBoxSettingsManager(path)
        self._settings = self._settings_manager.load()
        self._line_color = QColor(*self._settings.line_rgba)
        self._fill_color = QColor(*self._settings.fill_rgba)
        self._ruler_enabled = self._settings.ruler_enabled
        self._ruler_outside = self._settings.ruler_outside
        self._crosshair_enabled = self._settings.crosshair_enabled

        self._overlay: OverlayView | None = None
        self._escape_listener: EscapeListener | None = None
        self._hotkey_bridge: GlobalHotkeyBridge | None = None
        self._ctrl_click_listener: GlobalCtrlClickListener | None = None
        self._passthrough_refresh_timer: QTimer | None = None
        self._interaction_locked = True
        self._ctrl_physically_held = False
        self._shutdown_complete = False

    @property
    def settings(self) -> MeasureBoxSettings:
        """Current MeasureBox settings snapshot."""

        return MeasureBoxSettings(
            line_rgba=(
                self._line_color.red(),
                self._line_color.green(),
                self._line_color.blue(),
                self._line_color.alpha(),
            ),
            fill_rgba=(
                self._fill_color.red(),
                self._fill_color.green(),
                self._fill_color.blue(),
                self._fill_color.alpha(),
            ),
            ruler_enabled=self._ruler_enabled,
            ruler_outside=self._ruler_outside,
            crosshair_enabled=self._crosshair_enabled,
        )

    def is_active(self) -> bool:
        """Return whether the overlay session is currently running."""

        return self._overlay is not None and not self._shutdown_complete

    def start(self) -> None:
        """
        Show the overlay in draw mode so the user can measure once.

        Returns:
            None
        """

        if self.is_active():
            return

        self._shutdown_complete = False
        self._overlay = OverlayView(self._line_color, self._fill_color)
        self._overlay.set_ruler_options(self._ruler_enabled, self._ruler_outside)
        self._overlay.set_crosshair_enabled(self._crosshair_enabled)
        self._overlay.rectangle_created.connect(self._on_rectangle_created)
        self._overlay.interaction_lock_changed.connect(self._on_interaction_lock_changed)

        self._hotkey_bridge = GlobalHotkeyBridge()
        self._hotkey_bridge.ctrl_click_requested.connect(self._handle_ctrl_click)
        self._hotkey_bridge.ctrl_state_changed.connect(self._handle_ctrl_state_changed)
        self._hotkey_bridge.color_pick_requested.connect(self._handle_color_pick_at)
        self._hotkey_bridge.ctrl_hover_requested.connect(self._handle_ctrl_hover)

        self._ctrl_click_listener = GlobalCtrlClickListener(
            self._hotkey_bridge.ctrl_click_requested.emit,
            self._hotkey_bridge.ctrl_state_changed.emit,
            self._hotkey_bridge.color_pick_requested.emit,
            self._hotkey_bridge.ctrl_hover_requested.emit,
        )
        self._ctrl_click_listener.start()

        self._escape_listener = EscapeListener()
        self._escape_listener.escape_pressed.connect(self.stop)
        self._escape_listener.start()

        self._passthrough_refresh_timer = QTimer(self)
        self._passthrough_refresh_timer.setInterval(1000)
        self._passthrough_refresh_timer.timeout.connect(self._refresh_passthrough_mode)
        self._passthrough_refresh_timer.start()

        self._activate_draw_mode()
        QTimer.singleShot(0, self._stabilize_draw_mode)
        QTimer.singleShot(250, self._stabilize_draw_mode)

    def stop(self) -> None:
        """
        End the session, persist settings, and tear down the overlay.

        Returns:
            None
        """

        if self._shutdown_complete:
            return
        self._shutdown_complete = True

        if self._passthrough_refresh_timer is not None:
            self._passthrough_refresh_timer.stop()
            self._passthrough_refresh_timer = None

        if self._escape_listener is not None:
            self._escape_listener.stop()
            self._escape_listener = None

        if self._ctrl_click_listener is not None:
            self._ctrl_click_listener.stop()
            self._ctrl_click_listener = None

        self._hotkey_bridge = None
        self._save_settings()

        if self._overlay is not None:
            self._overlay.clear_all()
            self._overlay.clear_crosshair()
            self._overlay.hide()
            self._overlay.deleteLater()
            self._overlay = None

        self.finished.emit()
        if self._on_finished is not None:
            self._on_finished()

    def apply_settings(self, settings: MeasureBoxSettings) -> None:
        """
        Apply settings to a live or idle session and persist them.

        Args:
            settings: New MeasureBox settings.

        Returns:
            None
        """

        self._line_color = QColor(*settings.line_rgba)
        self._fill_color = QColor(*settings.fill_rgba)
        self._ruler_enabled = settings.ruler_enabled
        self._ruler_outside = settings.ruler_outside
        self._crosshair_enabled = settings.crosshair_enabled
        if self._overlay is not None:
            self._overlay.set_line_color(self._line_color)
            self._overlay.set_fill_color(self._fill_color)
            self._overlay.set_ruler_options(self._ruler_enabled, self._ruler_outside)
            self._overlay.set_crosshair_enabled(self._crosshair_enabled)
        self._save_settings()

    def build_settings_menu(self, parent: QWidget | None = None) -> QMenu:
        """
        Build a context menu with MeasureBox appearance options.

        Args:
            parent: Optional parent widget for the menu.

        Returns:
            Configured QMenu ready to exec.
        """

        menu = QMenu(parent)
        line_action = QAction("Line Color...", menu)
        line_action.triggered.connect(self.choose_line_color)
        menu.addAction(line_action)

        fill_action = QAction("Fill Color...", menu)
        fill_action.triggered.connect(self.choose_fill_color)
        menu.addAction(fill_action)
        menu.addSeparator()

        ruler_action = QAction("Show Pixel Ruler (px)", menu)
        ruler_action.setCheckable(True)
        ruler_action.setChecked(self._ruler_enabled)
        ruler_action.toggled.connect(self._toggle_ruler_enabled)
        menu.addAction(ruler_action)

        ruler_outside_action = QAction("Ruler Outside Rectangle", menu)
        ruler_outside_action.setCheckable(True)
        ruler_outside_action.setChecked(self._ruler_outside)
        ruler_outside_action.setEnabled(self._ruler_enabled)
        ruler_outside_action.toggled.connect(self._toggle_ruler_outside)
        menu.addAction(ruler_outside_action)
        self._ruler_outside_action = ruler_outside_action

        crosshair_action = QAction("Show Left Shift Crosshair", menu)
        crosshair_action.setCheckable(True)
        crosshair_action.setChecked(self._crosshair_enabled)
        crosshair_action.toggled.connect(self._toggle_crosshair_enabled)
        menu.addAction(crosshair_action)
        return menu

    def choose_line_color(self, parent: QWidget | None = None) -> None:
        """Open a color dialog for the measurement border color."""

        selected = QColorDialog.getColor(
            self._line_color,
            parent,
            "Select line color (with alpha)",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if not selected.isValid():
            return
        self._line_color = selected
        if self._overlay is not None:
            self._overlay.set_line_color(self._line_color)
        self._save_settings()

    def choose_fill_color(self, parent: QWidget | None = None) -> None:
        """Open a color dialog for the measurement fill color."""

        selected = QColorDialog.getColor(
            self._fill_color,
            parent,
            "Select fill color (with alpha)",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if not selected.isValid():
            return
        self._fill_color = selected
        if self._overlay is not None:
            self._overlay.set_fill_color(self._fill_color)
        self._save_settings()

    def _toggle_ruler_enabled(self, checked: bool) -> None:
        self._ruler_enabled = checked
        if hasattr(self, "_ruler_outside_action"):
            self._ruler_outside_action.setEnabled(checked)
        if self._overlay is not None:
            self._overlay.set_ruler_options(self._ruler_enabled, self._ruler_outside)
        self._save_settings()

    def _toggle_ruler_outside(self, checked: bool) -> None:
        self._ruler_outside = checked
        if self._overlay is not None:
            self._overlay.set_ruler_options(self._ruler_enabled, self._ruler_outside)
        self._save_settings()

    def _toggle_crosshair_enabled(self, checked: bool) -> None:
        self._crosshair_enabled = checked
        if self._overlay is not None:
            self._overlay.set_crosshair_enabled(checked)
            if checked and self._ctrl_physically_held:
                self._update_crosshair_at_cursor()
        self._save_settings()

    def _activate_draw_mode(self) -> None:
        if self._overlay is None:
            return
        self._interaction_locked = True
        self._overlay.set_interaction_lock(True)
        self._overlay.set_edit_mode(True)
        self._overlay.reapply_interaction_state()
        self._overlay.ensure_visible_foreground()
        self._overlay.set_interaction_lock(True)

    def _activate_passthrough_mode(self) -> None:
        if self._overlay is None:
            return
        self._interaction_locked = False
        self._overlay.set_interaction_lock(False)
        self._overlay.set_edit_mode(True)
        self._overlay.ensure_visible_foreground()

    def _stabilize_draw_mode(self) -> None:
        if self._overlay is None or not self._interaction_locked:
            return
        self._overlay.reapply_interaction_state()
        self._overlay.raise_()

    def _on_rectangle_created(self) -> None:
        self._activate_passthrough_mode()

    def _on_interaction_lock_changed(self, locked: bool) -> None:
        self._interaction_locked = locked

    def _handle_ctrl_click(self, x: int, y: int) -> None:
        self._update_crosshair_at(x, y)
        self._activate_ctrl_interaction_at(x, y)

    def _handle_ctrl_state_changed(self, pressed: bool) -> None:
        self._ctrl_physically_held = pressed
        if self._overlay is None:
            return
        if pressed:
            self._update_crosshair_at_cursor()
            self._activate_draw_mode()
            self._overlay.select_active_rectangle_for_edit()
            return
        self._overlay.clear_crosshair()
        self._activate_passthrough_mode()

    def _handle_ctrl_hover(self, x: int, y: int) -> None:
        if not self._ctrl_physically_held or self._overlay is None:
            return
        if self._crosshair_enabled:
            self._overlay.set_crosshair_at_global(x, y)
        if not self._overlay.is_global_point_on_active_item(x, y):
            return
        self._activate_ctrl_interaction_at(x, y)

    def _activate_ctrl_interaction_at(self, x: int, y: int) -> None:
        if self._overlay is None:
            return
        if self._overlay.try_activate_interaction_at_global(x, y):
            self._interaction_locked = True
            return
        if not self._overlay.has_active_rectangle():
            self._activate_draw_mode()
            return
        self._activate_passthrough_mode()

    def _update_crosshair_at_cursor(self) -> None:
        cursor_pos = QCursor.pos()
        self._update_crosshair_at(cursor_pos.x(), cursor_pos.y())

    def _update_crosshair_at(self, x: int, y: int) -> None:
        if not self._crosshair_enabled or self._overlay is None:
            return
        self._overlay.set_crosshair_at_global(x, y)

    def _handle_color_pick_at(self, x: int, y: int) -> None:
        if self._overlay is None:
            return
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        sample = screen.grabWindow(0, x, y, 1, 1)
        image = sample.toImage()
        if image.isNull() or image.width() < 1 or image.height() < 1:
            return
        color = image.pixelColor(0, 0)
        color_hex = color.name(QColor.NameFormat.HexRgb).upper()
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(color_hex)
        self._overlay.set_active_pick_result(color_hex, x, y)

    def _refresh_passthrough_mode(self) -> None:
        if self._overlay is None or self._interaction_locked:
            return
        self._overlay.ensure_visible_foreground()
        self._activate_passthrough_mode()

    def _save_settings(self) -> None:
        self._settings_manager.save(self.settings)
