"""
Screenshot capture panel and overlays.
"""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from shutil import which
from typing import Callable

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QGuiApplication,
    QIcon,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QShortcut,
    QKeySequence,
)
from PySide6.QtWidgets import (
    QApplication,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
    QMessageBox,
    QProgressDialog,
)

from src.constants import APP_NAME
from src.auto_scroll_capture import MAX_SCROLL_FRAMES, perform_auto_scroll_capture
from src.platform import (
    capture_desktop_png_bytes,
    capture_region_with_grim_slurp,
    get_x11_focused_window_id,
    has_grim,
    has_grim_and_slurp,
    is_wayland_session,
    raise_x11_window,
)


class CaptureMode:
    """
    Provides capture mode identifiers.
    """

    FULL_SCREEN = "full_screen"
    REGION = "region"
    WINDOW = "window"
    SCROLL = "scroll"


_ACTIVE_OVERLAYS: list[QWidget] = []

# Wait for the compositor to drop hidden Snappix windows (Capture panel, countdown)
# before sampling the framebuffer. Too short and the panel still appears in shots.
CAPTURE_UI_SETTLE_MS = 120


def schedule_capture_after_ui_settle(callback: Callable[[], None]) -> None:
    """
    Runs ``callback`` after processing events and a short compositor settle delay.

    Callers should hide the Capture panel (and other Snappix chrome) before
    invoking this helper so screenshots do not include those windows.

    Args:
        callback: Capture work to run after the UI has settled.

    Returns:
        None
    """

    QApplication.processEvents()
    QTimer.singleShot(CAPTURE_UI_SETTLE_MS, callback)


def _install_escape_shortcut(widget: QWidget, callback: Callable[[], None]) -> QShortcut:
    """
    Register an application-wide Escape shortcut for a temporary capture widget.

    Args:
        widget: Owner widget for shortcut lifecycle.
        callback: Function invoked when Escape is pressed.

    Returns:
        QShortcut: Created shortcut instance.
    """

    shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), widget)
    shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
    shortcut.activated.connect(callback)
    return shortcut


def draw_cursor_edge_guides(painter: QPainter, bounds: QRect, point: QPoint) -> None:
    """
    Draws fading guide lines from the cursor to the four edges of ``bounds``.

    Args:
        painter: Active painter.
        bounds: Overlay rectangle in local coordinates.
        point: Cursor position in local coordinates.

    Returns:
        None
    """

    if not bounds.contains(point):
        return

    fade_color = QColor(255, 255, 255, 170)
    transparent = QColor(255, 255, 255, 0)

    left_gradient = QLinearGradient(point.x(), point.y(), bounds.left(), point.y())
    left_gradient.setColorAt(0.0, fade_color)
    left_gradient.setColorAt(1.0, transparent)
    left_pen = QPen()
    left_pen.setWidthF(1.2)
    left_pen.setBrush(left_gradient)
    painter.setPen(left_pen)
    painter.drawLine(point.x(), point.y(), bounds.left(), point.y())

    right_gradient = QLinearGradient(point.x(), point.y(), bounds.right(), point.y())
    right_gradient.setColorAt(0.0, fade_color)
    right_gradient.setColorAt(1.0, transparent)
    right_pen = QPen()
    right_pen.setWidthF(1.2)
    right_pen.setBrush(right_gradient)
    painter.setPen(right_pen)
    painter.drawLine(point.x(), point.y(), bounds.right(), point.y())

    top_gradient = QLinearGradient(point.x(), point.y(), point.x(), bounds.top())
    top_gradient.setColorAt(0.0, fade_color)
    top_gradient.setColorAt(1.0, transparent)
    top_pen = QPen()
    top_pen.setWidthF(1.2)
    top_pen.setBrush(top_gradient)
    painter.setPen(top_pen)
    painter.drawLine(point.x(), point.y(), point.x(), bounds.top())

    bottom_gradient = QLinearGradient(point.x(), point.y(), point.x(), bounds.bottom())
    bottom_gradient.setColorAt(0.0, fade_color)
    bottom_gradient.setColorAt(1.0, transparent)
    bottom_pen = QPen()
    bottom_pen.setWidthF(1.2)
    bottom_pen.setBrush(bottom_gradient)
    painter.setPen(bottom_pen)
    painter.drawLine(point.x(), point.y(), point.x(), bounds.bottom())


@dataclass(slots=True)
class CaptureRequest:
    """
    Defines a capture request from the panel.

    Attributes:
        mode: Requested capture mode.
        delay_seconds: Delay before capture starts.
    """

    mode: str
    delay_seconds: int


@dataclass(slots=True)
class DesktopSnapshot:
    """
    Contains a captured virtual desktop image and geometry.

    Attributes:
        pixmap: Captured virtual desktop pixmap.
        virtual_geometry: Bounding rectangle across all screens.
    """

    pixmap: QPixmap
    virtual_geometry: QRect


class CapturePanel(QWidget):
    """
    SnagIt-like compact panel to start screen captures.
    """

    capture_requested = Signal(CaptureRequest)
    video_capture_requested = Signal()
    color_pick_requested = Signal()
    autostart_toggled = Signal(bool)
    close_requested = Signal()
    editor_requested = Signal()

    def __init__(self) -> None:
        """
        Initializes the compact capture control panel.
        """

        super().__init__()
        self.setObjectName("capturePanel")
        self.setWindowTitle(f"{APP_NAME} Capture")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self._initial_position_done = False

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(6)

        title = QLabel(APP_NAME)
        title.setObjectName("titleLabel")
        root_layout.addWidget(title)

        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        root_layout.addWidget(frame)
        form = QFormLayout(frame)

        self.delay_slider = QSlider(Qt.Orientation.Horizontal)
        self.delay_slider.setRange(0, 20)
        self.delay_slider.setValue(0)
        self.delay_slider.valueChanged.connect(self._sync_delay_label_from_slider)
        self.delay_slider.setToolTip(
            "Delay capture start in seconds. Press Esc during the countdown to cancel."
        )

        self.delay_value_label = QLabel("0 s")
        self.delay_value_label.setToolTip(
            "Current delay before capture starts. Esc cancels during countdown."
        )
        delay_row = QHBoxLayout()
        delay_row.addWidget(self.delay_slider, 1)
        delay_row.addWidget(self.delay_value_label)
        form.addRow("Delay:", delay_row)

        self._autostart_enabled = False

        self.open_editor_button = QPushButton("Open Editor")
        self.open_editor_button.setObjectName("linkButton")
        self.open_editor_button.setFlat(True)
        self.open_editor_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_editor_button.setToolTip(
            "Open the editor or create a blank canvas without taking a screenshot."
        )
        self.open_editor_button.clicked.connect(self.editor_requested.emit)
        open_editor_row = QHBoxLayout()
        open_editor_row.setContentsMargins(0, 0, 0, 0)
        open_editor_row.addStretch(1)
        open_editor_row.addWidget(self.open_editor_button)
        form.addRow("", open_editor_row)
        self._minimize_to_tray_on_close = True

        buttons = QHBoxLayout()
        self.capture_fullscreen_button = QPushButton("Capture Fullscreen")
        self.capture_fullscreen_button.setObjectName("primaryButton")
        self.capture_fullscreen_button.clicked.connect(
            lambda: self._emit_request_for_mode(CaptureMode.FULL_SCREEN)
        )
        self.capture_fullscreen_button.setToolTip("Capture all screens immediately.")
        buttons.addWidget(self.capture_fullscreen_button)

        self.capture_area_button = QPushButton("Capture Area")
        self.capture_area_button.setObjectName("primaryButton")
        self.capture_area_button.clicked.connect(
            lambda: self._emit_request_for_mode(CaptureMode.REGION)
        )
        self.capture_area_button.setToolTip("Select and capture a custom screen region.")
        buttons.addWidget(self.capture_area_button)

        self.capture_window_button = QPushButton("Capture Window")
        self.capture_window_button.setObjectName("primaryButton")
        self.capture_window_button.clicked.connect(
            lambda: self._emit_request_for_mode(CaptureMode.WINDOW)
        )
        self.capture_window_button.setToolTip("Select one application window to capture.")
        buttons.addWidget(self.capture_window_button)

        self.capture_scroll_button = QPushButton("Scroll")
        self.capture_scroll_button.setObjectName("primaryButton")
        self.capture_scroll_button.clicked.connect(
            lambda: self._emit_request_for_mode(CaptureMode.SCROLL)
        )
        self.capture_scroll_button.setToolTip(
            "Select a window and capture its full scrollable content automatically."
        )
        buttons.addWidget(self.capture_scroll_button)

        self.capture_video_button = QPushButton("Capture Video")
        self.capture_video_button.setObjectName("primaryButton")
        self.capture_video_button.setToolTip(
            "Select a screen region and record it to video."
        )
        self.capture_video_button.clicked.connect(self.video_capture_requested.emit)
        buttons.addWidget(self.capture_video_button)

        self.pick_color_button = QPushButton("")
        self.pick_color_button.setIcon(_build_color_picker_icon())
        self.pick_color_button.setFixedSize(32, 32)
        self.pick_color_button.setToolTip(
            "Pick a color from the screen and copy it to clipboard."
        )
        self.pick_color_button.clicked.connect(self.color_pick_requested.emit)
        buttons.addWidget(self.pick_color_button)

        root_layout.addLayout(buttons)

    def set_video_capture_available(self, available: bool) -> None:
        """
        Enables or disables the video capture button based on ffmpeg availability.

        Args:
            available: Whether ffmpeg was found on the system.

        Returns:
            None
        """

        self.capture_video_button.setEnabled(available)
        if available:
            self.capture_video_button.setToolTip(
                "Select a screen region and record it to video."
            )
        else:
            self.capture_video_button.setToolTip(
                "Video capture requires ffmpeg. Please install ffmpeg to enable this feature."
            )

    def _emit_request_for_mode(self, mode: str) -> None:
        """
        Emits a structured capture request for one capture mode.

        Args:
            mode: Selected capture mode.

        Returns:
            None
        """

        self.capture_requested.emit(
            CaptureRequest(
                mode=mode,
                delay_seconds=int(self.delay_slider.value()),
            )
        )

    def _sync_delay_label_from_slider(self, value: int) -> None:
        """
        Synchronizes delay label from slider value.

        Args:
            value: Delay in seconds.

        Returns:
            None
        """

        self.delay_value_label.setText(f"{value} s")

    def showEvent(self, event) -> None:
        """
        Applies capture taskbar identity when the panel becomes visible.

        Args:
            event: Qt show event.

        Returns:
            None
        """

        from src.platform import apply_linux_window_identity

        apply_linux_window_identity(
            self,
            desktop_file_name="snappix",
            wm_instance="snappix",
            wm_class="snappix",
        )
        super().showEvent(event)

    def set_autostart_checked(self, enabled: bool) -> None:
        """
        Stores autostart state from tray/config synchronization.

        Args:
            enabled: Desired checked state.

        Returns:
            None
        """

        self._autostart_enabled = enabled

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
        super().closeEvent(event)

    def showEvent(self, event) -> None:
        """
        Positions capture panel at top-right on first show.

        Args:
            event: Qt show event.

        Returns:
            None
        """

        super().showEvent(event)
        if self._initial_position_done:
            return
        QTimer.singleShot(0, self._apply_initial_window_geometry)

    def _apply_initial_window_geometry(self) -> None:
        """
        Applies compact initial size and top-right position once per run.

        Returns:
            None
        """

        if self._initial_position_done:
            return
        self.adjustSize()
        target_size = self.minimumSizeHint()
        self.resize(target_size)
        screen = QGuiApplication.screenAt(QCursor.pos())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        margin = 12
        x = available.x() + available.width() - self.width() - margin
        y = available.y() + margin
        self.move(x, y)
        self._initial_position_done = True


class RegionCaptureOverlay(QWidget):
    """
    Full-screen overlay used for drag-based region captures.
    """

    capture_done = Signal(QPixmap)
    capture_cancelled = Signal()
    region_selected = Signal(QRect)

    def __init__(self, screenshot: QPixmap, virtual_geometry: QRect) -> None:
        """
        Initializes region selection overlay.

        Args:
            screenshot: Current desktop screenshot for visual background.
        """

        super().__init__()
        self._screenshot = screenshot
        self._virtual_geometry = virtual_geometry
        self._start_point = QPoint()
        self._current_point = QPoint()
        self._cursor_point = QPoint(-1, -1)
        self._dragging = False
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setGeometry(self._virtual_geometry)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._escape_shortcut = _install_escape_shortcut(self, self._cancel_capture)

    def showEvent(self, event) -> None:
        """
        Seeds the cursor guide position when the overlay becomes visible.

        Args:
            event: Qt show event.

        Returns:
            None
        """

        self._cursor_point = self.mapFromGlobal(QCursor.pos())
        super().showEvent(event)

    def paintEvent(self, _) -> None:
        """
        Paints the screenshot background, cursor guides, and selection rectangle.

        Returns:
            None
        """

        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._screenshot)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 60))
        if self.rect().contains(self._cursor_point):
            draw_cursor_edge_guides(painter, self.rect(), self._cursor_point)
        if self._dragging:
            selection = QRect(self._start_point, self._current_point).normalized()
            if selection.width() > 0 and selection.height() > 0:
                painter.drawPixmap(selection, self._screenshot, selection)

                # Draw a high-contrast double border so selection is always visible.
                outer_pen = QPen(QColor(255, 255, 255, 240), 2)
                inner_pen = QPen(QColor(52, 152, 219, 255), 1, Qt.PenStyle.DashLine)
                outer_rect = selection.adjusted(0, 0, -1, -1)
                inner_rect = selection.adjusted(1, 1, -2, -2)

                painter.setPen(outer_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(outer_rect)

                painter.setPen(inner_pen)
                painter.drawRect(inner_rect)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """
        Starts rectangle dragging on left click.

        Args:
            event: Mouse event.

        Returns:
            None
        """

        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._start_point = event.position().toPoint()
        self._current_point = self._start_point
        self._cursor_point = self._current_point
        self._dragging = True
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """
        Updates cursor guides and drag rectangle while moving.

        Args:
            event: Mouse event.

        Returns:
            None
        """

        self._cursor_point = event.position().toPoint()
        if self._dragging:
            self._current_point = self._cursor_point
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """
        Finalizes capture after drag release.

        Args:
            event: Mouse event.

        Returns:
            None
        """

        if event.button() != Qt.MouseButton.LeftButton or not self._dragging:
            return
        self._dragging = False
        rect = QRect(self._start_point, self._current_point).normalized()
        if rect.width() > 3 and rect.height() > 3:
            self.capture_done.emit(self._screenshot.copy(rect))
            self.region_selected.emit(rect.translated(self._virtual_geometry.topLeft()))
        else:
            self.capture_cancelled.emit()
        self.close()

    def keyPressEvent(self, event) -> None:
        """
        Cancels capture when Escape is pressed.

        Args:
            event: Key event.

        Returns:
            None
        """

        if event.key() == Qt.Key.Key_Escape:
            self._cancel_capture()

    def _cancel_capture(self) -> None:
        """
        Cancels region capture and closes the overlay.

        Returns:
            None
        """

        self.capture_cancelled.emit()
        self.close()

    def closeEvent(self, event) -> None:
        """
        Releases keyboard grab when region overlay closes.

        Args:
            event: Qt close event.

        Returns:
            None
        """

        self.releaseKeyboard()
        super().closeEvent(event)


RECORDING_BORDER_THICKNESS = 4
RECORDING_BORDER_BLINK_MS = 600
RECORDING_BORDER_ACTIVE_COLOR = QColor(231, 76, 60, 255)
RECORDING_BORDER_PAUSED_COLOR = QColor(243, 156, 18, 255)


class RecordingBorderOverlay(QWidget):
    """
    Blinking border shown just outside the region currently being video-recorded.

    The border is drawn entirely outside the recorded pixels (in a margin
    added around the capture rect) so it never contaminates the ffmpeg
    capture itself -- it is purely a visual indicator for the user.
    """

    def __init__(self, capture_rect: QRect) -> None:
        """
        Initializes the border overlay around one screen-recording region.

        Args:
            capture_rect: Recorded region in absolute virtual-desktop coordinates.
        """

        super().__init__()
        self._paused = False
        self._blink_on = True
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        outer_rect = capture_rect.adjusted(
            -RECORDING_BORDER_THICKNESS,
            -RECORDING_BORDER_THICKNESS,
            RECORDING_BORDER_THICKNESS,
            RECORDING_BORDER_THICKNESS,
        )
        self.setGeometry(outer_rect)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_blink_tick)
        self._timer.start(RECORDING_BORDER_BLINK_MS)

    def set_paused(self, paused: bool) -> None:
        """
        Switches the border between the blinking "recording" and static "paused" look.

        Args:
            paused: True to show a static paused-colored border.

        Returns:
            None
        """

        self._paused = paused
        self._blink_on = True
        self.update()

    def _on_blink_tick(self) -> None:
        """
        Toggles the visible blink phase while actively recording.

        Returns:
            None
        """

        if self._paused:
            return
        self._blink_on = not self._blink_on
        self.update()

    def paintEvent(self, _event) -> None:
        """
        Paints the border ring in the margin surrounding the recorded region.

        Returns:
            None
        """

        if not self._paused and not self._blink_on:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        color = RECORDING_BORDER_PAUSED_COLOR if self._paused else RECORDING_BORDER_ACTIVE_COLOR
        painter.setPen(QPen(color, RECORDING_BORDER_THICKNESS))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        half = RECORDING_BORDER_THICKNESS / 2.0
        painter.drawRect(
            QRectF(
                half,
                half,
                self.width() - RECORDING_BORDER_THICKNESS,
                self.height() - RECORDING_BORDER_THICKNESS,
            )
        )

    def closeEvent(self, event) -> None:
        """
        Stops the blink timer before the overlay closes.

        Args:
            event: Qt close event.

        Returns:
            None
        """

        self._timer.stop()
        super().closeEvent(event)


def _capture_region_via_grim_slurp() -> QPixmap | None:
    """
    Captures one region through grim and slurp on Wayland.

    Returns:
        QPixmap | None: Captured pixmap or None when cancelled.
    """

    result = capture_region_with_grim_slurp()
    if result is None:
        return None
    png_bytes, _, _ = result
    pixmap = QPixmap()
    if not pixmap.loadFromData(png_bytes, "PNG"):
        return None
    return pixmap


class ScrollCaptureProgressDialog(QProgressDialog):
    """
    Shows detailed progress for automatic scroll capture.
    """

    def __init__(self, window_width: int, window_height: int) -> None:
        """
        Initializes the scroll capture progress dialog.

        Args:
            window_width: Selected window width in pixels.
            window_height: Selected window height in pixels.
        """

        super().__init__(None)
        self._window_size_text = f"{window_width}×{window_height} px"
        self.setWindowTitle(f"{APP_NAME} Scroll Capture")
        self.setLabelText("Preparing scroll capture...")
        self.setCancelButtonText("Cancel")
        self.setMinimumWidth(460)
        self.setMinimumHeight(118)
        self.setRange(0, MAX_SCROLL_FRAMES)
        self.setValue(0)
        self.setMinimumDuration(0)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setAutoReset(False)
        self.setAutoClose(False)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._escape_shortcut = _install_escape_shortcut(self, self.cancel)

    def show_centered(self) -> None:
        """
        Shows the dialog centered on the primary screen without taking focus.

        Returns:
            None
        """

        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            dialog_size = self.sizeHint()
            x_pos = available.x() + max(0, (available.width() - dialog_size.width()) // 2)
            y_pos = available.y() + max(0, (available.height() - dialog_size.height()) // 3)
            self.move(x_pos, y_pos)
        self.show()
        self.raise_()
        QApplication.processEvents()

    def update_progress(self, message: str, step: int, max_steps: int) -> None:
        """
        Updates progress text and bar value.

        Args:
            message: Status message for the current step.
            step: Current progress step.
            max_steps: Maximum step count.

        Returns:
            None
        """

        bounded_max = max(1, max_steps)
        bounded_step = max(0, min(step, bounded_max))
        self.setMaximum(bounded_max)
        self.setValue(bounded_step)
        self.setLabelText(f"{message}\nWindow: {self._window_size_text}")
        QApplication.processEvents()


def execute_scroll_capture(
    on_capture: Callable[[QPixmap], None],
    on_cancel: Callable[[], None],
) -> None:
    """
    Starts automatic scroll capture for one selected window.

    Args:
        on_capture: Callback invoked with stitched pixmap.
        on_cancel: Callback when capture is cancelled.

    Returns:
        None
    """

    if is_wayland_session():
        QMessageBox.information(
            None,
            "Scroll Capture",
            "Automatic scroll capture requires X11 window control.\n"
            "Use Capture Area on Wayland instead.",
        )
        on_cancel()
        return

    if which("xdotool") is None or which("xwininfo") is None:
        QMessageBox.warning(
            None,
            "Scroll Capture Unavailable",
            "Scroll capture requires xdotool and xwininfo.\n"
            "Please run: python3 install_dependencies.py",
        )
        on_cancel()
        return

    snapshot = capture_full_screen()
    if snapshot.pixmap.isNull() or snapshot.virtual_geometry.isNull():
        on_cancel()
        return

    overlay = WindowCaptureOverlay(snapshot.pixmap, snapshot.virtual_geometry)
    _track_overlay(overlay)
    overlay.show()
    overlay.raise_()
    overlay.activateWindow()
    overlay.grabKeyboard()
    # Force an immediate synchronous paint: some compositors race the very
    # first async update() on a freshly mapped always-on-top fullscreen
    # window, occasionally dropping the initial frame (dimming/crosshair/
    # selection border never appear until the next repaint trigger).
    overlay.repaint()

    process = subprocess.Popen(
        ["xdotool", "selectwindow"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    selection_state = {"cancelled": False}

    def cancel_selection() -> None:
        if selection_state["cancelled"]:
            return
        selection_state["cancelled"] = True
        if process.poll() is None:
            process.terminate()
        _untrack_overlay(overlay)
        overlay.close()
        on_cancel()

    overlay.capture_cancelled.connect(cancel_selection)

    def check_selection_process() -> None:
        if selection_state["cancelled"]:
            return
        return_code = process.poll()
        if return_code is None:
            QTimer.singleShot(70, check_selection_process)
            return

        _untrack_overlay(overlay)
        overlay.close()

        if return_code != 0:
            on_cancel()
            return

        selected_id_raw = process.stdout.read().strip() if process.stdout is not None else ""
        if not selected_id_raw:
            on_cancel()
            return

        window_id = _resolve_top_level_window_id(selected_id_raw)
        if not window_id:
            on_cancel()
            return

        global_rect = _window_geometry_from_id(window_id)
        if global_rect.isNull():
            on_cancel()
            return

        progress = ScrollCaptureProgressDialog(
            global_rect.width(),
            global_rect.height(),
        )
        previous_focus_window_id = get_x11_focused_window_id()
        progress.show_centered()

        cancelled = {"value": False}
        progress.canceled.connect(lambda: cancelled.__setitem__("value", True))
        capture_settle_seconds = 0.08

        def capture_without_progress_dialog():
            was_visible = progress.isVisible()
            progress.hide()
            QApplication.processEvents()
            time.sleep(0.03)
            QApplication.processEvents()
            try:
                raise_x11_window(window_id)
                time.sleep(capture_settle_seconds)
                QApplication.processEvents()
                return capture_full_screen()
            finally:
                if was_visible and not cancelled["value"]:
                    progress.show_centered()

        result = perform_auto_scroll_capture(
            window_id=window_id,
            window_rect=global_rect,
            capture_snapshot=capture_without_progress_dialog,
            is_cancelled=lambda: cancelled["value"] or progress.wasCanceled(),
            progress_callback=progress.update_progress,
            restore_focus_window_id=previous_focus_window_id,
        )
        progress.hide()
        QApplication.processEvents()
        progress.close()

        if result.cancelled:
            on_cancel()
            return

        if not result.succeeded:
            QMessageBox.warning(
                None,
                "Scroll Capture",
                result.message or "Scroll capture did not produce an image.",
            )
            on_cancel()
            return

        if result.frame_count <= 1 and result.pixmap.height() <= global_rect.height() + 4:
            answer = QMessageBox.question(
                None,
                "Scroll Capture",
                (
                    f"{result.message}\n\n"
                    "Only one frame was captured. The window may not have scrollable "
                    "content.\nOpen this result anyway?"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer != QMessageBox.StandardButton.Yes:
                on_cancel()
                return

        on_capture(result.pixmap)

    QTimer.singleShot(70, check_selection_process)


class WindowCaptureOverlay(QWidget):
    """
    Full-screen overlay that highlights the window under cursor.
    """

    capture_done = Signal(QPixmap)
    window_selected = Signal(str, QRect, QPixmap)
    capture_cancelled = Signal()

    def __init__(self, screenshot: QPixmap, virtual_geometry: QRect) -> None:
        """
        Initializes window detection overlay.

        Args:
            screenshot: Current desktop screenshot.
        """

        super().__init__()
        self._screenshot = screenshot
        self._virtual_geometry = virtual_geometry
        self._hover_rect = QRect()
        self._hover_label = ""
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(70)
        self._poll_timer.timeout.connect(self._update_hover_from_cursor)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setGeometry(self._virtual_geometry)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._escape_shortcut = _install_escape_shortcut(self, self._cancel_capture)
        self._poll_timer.start()

    def paintEvent(self, _) -> None:
        """
        Paints background and current window highlight.

        Returns:
            None
        """

        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._screenshot)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 35))
        painter.setPen(QColor(255, 255, 255, 240))
        painter.drawText(
            20,
            30,
            "Click the target window. Press Esc to cancel.",
        )
        if not self._hover_rect.isNull():
            local_rect = self._to_local_rect(self._hover_rect)
            painter.drawPixmap(local_rect, self._screenshot, local_rect)
            painter.setPen(QPen(QColor(46, 204, 113), 2))
            painter.drawRect(local_rect)
            if self._hover_label:
                label_padding = 8
                label_height = 24
                label_width = max(180, len(self._hover_label) * 8)
                label_x = local_rect.x()
                label_y = max(0, local_rect.y() - label_height - 4)
                painter.fillRect(
                    QRect(label_x, label_y, label_width, label_height),
                    QColor(20, 20, 20, 220),
                )
                painter.setPen(QPen(QColor(236, 240, 241), 1))
                painter.drawText(
                    QRect(
                        label_x + label_padding,
                        label_y,
                        label_width - (label_padding * 2),
                        label_height,
                    ),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    self._hover_label,
                )

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """
        Updates highlighted window under cursor.

        Args:
            event: Mouse move event.

        Returns:
            None
        """

        rect = detect_window_geometry(event.globalPosition().toPoint())
        if rect != self._hover_rect:
            self._hover_rect = rect
            if rect.isNull():
                self._hover_label = ""
            else:
                self._hover_label = (
                    f"X:{rect.x()} Y:{rect.y()} W:{rect.width()} H:{rect.height()}"
                )
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """
        Captures highlighted window on left click.

        Args:
            event: Mouse event.

        Returns:
            None
        """

        if event.button() != Qt.MouseButton.LeftButton:
            return
        window_id, global_rect = detect_window_at_point(event.globalPosition().toPoint())
        if global_rect.width() > 2 and global_rect.height() > 2:
            local_rect = self._to_local_rect(global_rect)
            pixmap = self._screenshot.copy(local_rect)
            self.capture_done.emit(pixmap)
            if window_id:
                self.window_selected.emit(window_id, global_rect, pixmap)
        else:
            self.capture_cancelled.emit()
        self.close()

    def keyPressEvent(self, event) -> None:
        """
        Cancels window capture on Escape.

        Args:
            event: Key event.

        Returns:
            None
        """

        if event.key() == Qt.Key.Key_Escape:
            self._cancel_capture()

    def _cancel_capture(self) -> None:
        """
        Cancels window capture and closes the overlay.

        Returns:
            None
        """

        self.capture_cancelled.emit()
        self.close()

    def _to_local_rect(self, global_rect: QRect) -> QRect:
        """
        Converts a global desktop rect into local overlay coordinates.

        Args:
            global_rect: Geometry in global desktop coordinates.

        Returns:
            QRect: Geometry mapped into local scene coordinates.
        """

        return global_rect.translated(
            -self._virtual_geometry.x(),
            -self._virtual_geometry.y(),
        )

    def _update_hover_from_cursor(self) -> None:
        """
        Polls cursor position and updates highlighted target window.

        Returns:
            None
        """

        rect = detect_window_geometry(QCursor.pos())
        if rect == self._hover_rect:
            return
        self._hover_rect = rect
        if rect.isNull():
            self._hover_label = ""
        else:
            self._hover_label = f"X:{rect.x()} Y:{rect.y()} W:{rect.width()} H:{rect.height()}"
        self.update()

    def closeEvent(self, event) -> None:
        """
        Stops polling timer when overlay closes.

        Args:
            event: Qt close event.

        Returns:
            None
        """

        self._poll_timer.stop()
        self.releaseKeyboard()
        super().closeEvent(event)


class ColorPickerOverlay(QWidget):
    """
    Full-screen overlay for picking one color from the screenshot.
    """

    color_picked = Signal(str)
    pick_cancelled = Signal()

    def __init__(self, screenshot: QPixmap, virtual_geometry: QRect) -> None:
        """
        Initializes color picker overlay with screenshot background.

        Args:
            screenshot: Current desktop screenshot.
            virtual_geometry: Combined virtual desktop geometry.
        """

        super().__init__()
        self._screenshot = screenshot
        self._virtual_geometry = virtual_geometry
        self._hover_point = QPoint(-1, -1)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setGeometry(self._virtual_geometry)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._escape_shortcut = _install_escape_shortcut(self, self._cancel_pick)

    def paintEvent(self, _) -> None:
        """
        Paints the screenshot and current color preview marker.

        Returns:
            None
        """

        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._screenshot)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 20))
        if not self.rect().contains(self._hover_point):
            return
        draw_cursor_edge_guides(painter, self.rect(), self._hover_point)
        color = self._color_at(self._hover_point)
        if color is None:
            return

        marker_size = 20
        marker_rect = QRect(
            self._hover_point.x() + 14,
            self._hover_point.y() + 14,
            marker_size,
            marker_size,
        )
        if marker_rect.right() > self.width():
            marker_rect.moveRight(self.width() - 2)
        if marker_rect.bottom() > self.height():
            marker_rect.moveBottom(self.height() - 2)
        painter.setPen(QPen(QColor(240, 240, 240), 1))
        painter.setBrush(color)
        painter.drawRect(marker_rect)
        painter.setPen(QPen(QColor(255, 255, 255), 1))
        painter.drawText(
            QRect(marker_rect.x(), marker_rect.bottom() + 2, 120, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            color.name().upper(),
        )

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """
        Updates hover marker while moving the cursor.

        Args:
            event: Mouse move event.

        Returns:
            None
        """

        self._hover_point = event.position().toPoint()
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """
        Picks color from screen on left click.

        Args:
            event: Mouse press event.

        Returns:
            None
        """

        if event.button() != Qt.MouseButton.LeftButton:
            return
        color = self._color_at(event.position().toPoint())
        if color is None:
            self.pick_cancelled.emit()
        else:
            self.color_picked.emit(color.name().upper())
        self.close()

    def keyPressEvent(self, event) -> None:
        """
        Cancels color picking when Escape is pressed.

        Args:
            event: Key event.

        Returns:
            None
        """

        if event.key() == Qt.Key.Key_Escape:
            self._cancel_pick()

    def _cancel_pick(self) -> None:
        """
        Cancels color picking and closes the overlay.

        Returns:
            None
        """

        self.pick_cancelled.emit()
        self.close()

    def closeEvent(self, event) -> None:
        """
        Releases keyboard grab when color picker overlay closes.

        Args:
            event: Qt close event.

        Returns:
            None
        """

        self.releaseKeyboard()
        super().closeEvent(event)

    def _color_at(self, local_pos: QPoint) -> QColor | None:
        """
        Resolves screenshot color at a local overlay position.

        Args:
            local_pos: Overlay-local point.

        Returns:
            QColor | None: Pixel color or None if out of range.
        """

        if local_pos.x() < 0 or local_pos.y() < 0:
            return None
        if local_pos.x() >= self._screenshot.width() or local_pos.y() >= self._screenshot.height():
            return None
        image = self._screenshot.toImage()
        return image.pixelColor(local_pos)

def detect_window_at_point(global_pos: QPoint) -> tuple[str, QRect]:
    """
    Detects the X11 window id and geometry below one global cursor position.

    Args:
        global_pos: Global cursor position.

    Returns:
        tuple[str, QRect]: Window id and geometry, or empty values when unknown.
    """

    if which("xdotool") is None or which("xwininfo") is None:
        return "", QRect()
    try:
        mouse_data = subprocess.run(
            ["xdotool", "getmouselocation", "--shell"],
            capture_output=True,
            check=True,
            text=True,
            timeout=0.25,
        ).stdout
        window_match = re.search(r"WINDOW=(\d+)", mouse_data)
        if not window_match:
            return "", QRect()
        window_id = _resolve_top_level_window_id(window_match.group(1))
        if not window_id:
            return "", QRect()
        return window_id, _window_geometry_from_id(window_id)
    except Exception:
        return "", QRect()


def detect_window_geometry(global_pos: QPoint) -> QRect:
    """
    Detects geometry of the X11 window below current cursor position.

    Args:
        global_pos: Global cursor position fallback.

    Returns:
        QRect: Detected window rectangle or fallback empty rectangle.
    """

    _window_id, geometry = detect_window_at_point(global_pos)
    return geometry


def select_window_geometry() -> QRect:
    """
    Uses xdotool selectwindow to robustly pick a target window by click.

    Returns:
        QRect: Selected window geometry in global coordinates or empty rect.
    """

    if which("xdotool") is None or which("xwininfo") is None:
        return QRect()
    try:
        result = subprocess.run(
            ["xdotool", "selectwindow"],
            capture_output=True,
            check=False,
            text=True,
        )
        if result.returncode != 0:
            return QRect()
        window_id_raw = result.stdout.strip()
        if not window_id_raw:
            return QRect()
        window_id = _resolve_top_level_window_id(window_id_raw)
        if not window_id:
            return QRect()

        return _window_geometry_from_id(window_id)
    except Exception:
        return QRect()


def capture_window_by_selection(snapshot: DesktopSnapshot) -> QPixmap:
    """
    Captures one selected window from the current desktop snapshot.

    Args:
        snapshot: Pre-captured virtual desktop screenshot and geometry.

    Returns:
        QPixmap: Cropped window pixmap or null pixmap.
    """

    selected_rect = select_window_geometry()
    if selected_rect.isNull():
        return QPixmap()
    local_rect = selected_rect.translated(
        -snapshot.virtual_geometry.x(),
        -snapshot.virtual_geometry.y(),
    )
    local_rect = local_rect.intersected(snapshot.pixmap.rect())
    if local_rect.width() <= 1 or local_rect.height() <= 1:
        return QPixmap()
    return snapshot.pixmap.copy(local_rect)


def _resolve_top_level_window_id(window_id: str) -> str:
    """
    Resolves the top-level parent window id for a hovered child window.

    Args:
        window_id: Initial window id from xdotool.

    Returns:
        str: Top-level window id suitable for final capture.
    """

    current_id = window_id
    previous_id = window_id
    root_id = _get_root_window_id()
    root_candidates = {"0", "0x0"}
    if root_id:
        root_candidates.add(root_id.lower())

    for _ in range(16):
        info = subprocess.run(
            ["xwininfo", "-id", current_id],
            capture_output=True,
            check=True,
            text=True,
            timeout=0.25,
        ).stdout
        if "(the root window)" in info.lower():
            return previous_id

        parent_match = re.search(r"Parent window id:\s+(\S+)", info)
        if not parent_match:
            return current_id
        parent_id = parent_match.group(1)
        if parent_id.lower() in root_candidates:
            return current_id
        previous_id = current_id
        current_id = parent_id
    return current_id


def _get_root_window_id() -> str:
    """
    Reads X11 root window id for parent-chain stop detection.

    Returns:
        str: Root window id (hex string) or empty string.
    """

    try:
        root_info = subprocess.run(
            ["xwininfo", "-root"],
            capture_output=True,
            check=True,
            text=True,
            timeout=0.25,
        ).stdout
        match = re.search(r"Window id:\s+(\S+)", root_info)
        if not match:
            return ""
        return match.group(1)
    except Exception:
        return ""


def _window_geometry_from_id(window_id: str) -> QRect:
    """
    Resolves absolute geometry for one X11 window id.

    Args:
        window_id: Target window id.

    Returns:
        QRect: Window geometry or empty rect.
    """

    try:
        info = subprocess.run(
            ["xwininfo", "-id", window_id],
            capture_output=True,
            check=True,
            text=True,
            timeout=0.4,
        ).stdout
        x_match = re.search(r"Absolute upper-left X:\s+(-?\d+)", info)
        y_match = re.search(r"Absolute upper-left Y:\s+(-?\d+)", info)
        w_match = re.search(r"Width:\s+(\d+)", info)
        h_match = re.search(r"Height:\s+(\d+)", info)
        if not all([x_match, y_match, w_match, h_match]):
            return QRect()
        x = int(x_match.group(1))
        y = int(y_match.group(1))
        w = int(w_match.group(1))
        h = int(h_match.group(1))
        if w <= 0 or h <= 0:
            return QRect()
        return QRect(x, y, w, h)
    except Exception:
        return QRect()


def capture_full_screen() -> DesktopSnapshot:
    """
    Captures the current virtual desktop across all monitors.

    Returns:
        DesktopSnapshot: Virtual desktop screenshot and geometry.
    """

    screens = QApplication.screens()
    if not screens:
        return DesktopSnapshot(pixmap=QPixmap(), virtual_geometry=QRect())

    virtual_geometry = QRect(screens[0].geometry())
    for screen in screens[1:]:
        virtual_geometry = virtual_geometry.united(screen.geometry())

    if virtual_geometry.width() <= 0 or virtual_geometry.height() <= 0:
        return DesktopSnapshot(pixmap=QPixmap(), virtual_geometry=QRect())

    if is_wayland_session() and has_grim():
        png_bytes = capture_desktop_png_bytes()
        if png_bytes:
            grim_pixmap = QPixmap()
            if grim_pixmap.loadFromData(png_bytes, "PNG") and not grim_pixmap.isNull():
                if grim_pixmap.size() == virtual_geometry.size():
                    return DesktopSnapshot(pixmap=grim_pixmap, virtual_geometry=virtual_geometry)
                scaled = grim_pixmap.scaled(
                    virtual_geometry.size(),
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                return DesktopSnapshot(pixmap=scaled, virtual_geometry=virtual_geometry)

    composed = QPixmap(virtual_geometry.size())
    composed.fill(Qt.GlobalColor.transparent)
    painter = QPainter(composed)
    for screen in screens:
        geometry = screen.geometry()
        screen_pixmap = screen.grabWindow(0)
        target_pos = geometry.topLeft() - virtual_geometry.topLeft()
        painter.drawPixmap(target_pos, screen_pixmap)
    painter.end()
    return DesktopSnapshot(pixmap=composed, virtual_geometry=virtual_geometry)


class CaptureDelayOverlay(QWidget):
    """
    Shows a capture countdown that can be cancelled with Escape.
    """

    finished = Signal()
    cancelled = Signal()

    def __init__(self, delay_seconds: int) -> None:
        """
        Initializes the countdown overlay.

        Args:
            delay_seconds: Remaining seconds before capture starts.
        """

        super().__init__()
        self._remaining = max(1, int(delay_seconds))
        self._closed = False
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(6)

        self._countdown_label = QLabel(str(self._remaining), self)
        self._countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._countdown_label.setStyleSheet(
            "color: #ffffff; font-size: 42px; font-weight: 700;"
        )
        root.addWidget(self._countdown_label)

        self._hint_label = QLabel("Capturing soon — press Esc to cancel", self)
        self._hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint_label.setStyleSheet("color: #e8eef7; font-size: 12px;")
        root.addWidget(self._hint_label)

        self.setStyleSheet(
            "CaptureDelayOverlay {"
            " background: rgba(20, 24, 32, 210);"
            " border: 1px solid rgba(255, 255, 255, 55);"
            " border-radius: 10px;"
            "}"
        )
        self.adjustSize()
        self._place_near_cursor()

        self._escape_shortcut = _install_escape_shortcut(self, self._cancel)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)

    def showEvent(self, event) -> None:
        """
        Starts the countdown when the overlay becomes visible.

        Args:
            event: Qt show event.

        Returns:
            None
        """

        super().showEvent(event)
        self._countdown_label.setText(str(self._remaining))
        if not self._timer.isActive():
            self._timer.start()
        self.raise_()
        self.activateWindow()
        self.grabKeyboard()

    def keyPressEvent(self, event) -> None:
        """
        Cancels the delayed capture when Escape is pressed.

        Args:
            event: Key event.

        Returns:
            None
        """

        if event.key() == Qt.Key.Key_Escape:
            self._cancel()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        """
        Releases keyboard grab when the overlay closes.

        Args:
            event: Close event.

        Returns:
            None
        """

        self.releaseKeyboard()
        self._timer.stop()
        super().closeEvent(event)

    def _place_near_cursor(self) -> None:
        """
        Positions the overlay near the current pointer screen.

        Returns:
            None
        """

        screen = QGuiApplication.screenAt(QCursor.pos())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        x = available.center().x() - (self.width() // 2)
        y = available.y() + 48
        self.move(x, y)

    def _on_tick(self) -> None:
        """
        Decrements the countdown and finishes when reaching zero.

        Returns:
            None
        """

        if self._closed:
            return
        self._remaining -= 1
        if self._remaining <= 0:
            # Hide timer chrome before capture so it is not in the screenshot.
            self._hide_countdown_chrome()
            self._finish()
            return
        self._countdown_label.setText(str(self._remaining))

    def _hide_countdown_chrome(self) -> None:
        """
        Hides countdown text and the overlay window immediately.

        Returns:
            None
        """

        self._countdown_label.clear()
        self._countdown_label.hide()
        self._hint_label.hide()
        self.hide()
        QApplication.processEvents()

    def _finish(self) -> None:
        """
        Completes the delay and notifies listeners to start capture.

        Returns:
            None
        """

        if self._closed:
            return
        self._closed = True
        self._timer.stop()
        self.releaseKeyboard()
        self._hide_countdown_chrome()
        # Brief deferral lets the compositor drop the overlay before capture.
        QTimer.singleShot(CAPTURE_UI_SETTLE_MS, self._emit_finished)

    def _emit_finished(self) -> None:
        """
        Emits the finished signal after the overlay is fully hidden.

        Returns:
            None
        """

        self.finished.emit()
        self.close()

    def _cancel(self) -> None:
        """
        Cancels the delayed capture.

        Returns:
            None
        """

        if self._closed:
            return
        self._closed = True
        self._timer.stop()
        self.releaseKeyboard()
        self._hide_countdown_chrome()
        self.cancelled.emit()
        self.close()


def execute_color_pick(
    on_picked: Callable[[str], None],
    on_cancel: Callable[[], None],
) -> None:
    """
    Starts interactive color picking from the current desktop screenshot.

    Args:
        on_picked: Callback with picked HEX color.
        on_cancel: Callback when picking is cancelled.

    Returns:
        None
    """

    snapshot = capture_full_screen()
    if snapshot.pixmap.isNull() or snapshot.virtual_geometry.isNull():
        on_cancel()
        return

    overlay = ColorPickerOverlay(snapshot.pixmap, snapshot.virtual_geometry)
    _track_overlay(overlay)
    overlay.color_picked.connect(on_picked)
    overlay.color_picked.connect(lambda _hex: _untrack_overlay(overlay))
    overlay.pick_cancelled.connect(on_cancel)
    overlay.pick_cancelled.connect(lambda: _untrack_overlay(overlay))
    overlay.show()
    overlay.raise_()
    overlay.activateWindow()
    overlay.grabKeyboard()
    # Force an immediate synchronous paint: some compositors race the very
    # first async update() on a freshly mapped always-on-top fullscreen
    # window, occasionally dropping the initial frame (dimming/crosshair/
    # selection border never appear until the next repaint trigger).
    overlay.repaint()


def execute_capture_request(
    request: CaptureRequest,
    on_capture: Callable[[QPixmap], None],
    on_cancel: Callable[[], None],
) -> None:
    """
    Executes a capture request with optional delay.

    Args:
        request: Capture request from panel.
        on_capture: Callback invoked with resulting QPixmap.
        on_cancel: Callback when capture is cancelled.

    Returns:
        None
    """

    def begin_capture() -> None:
        if request.mode == CaptureMode.SCROLL:
            execute_scroll_capture(on_capture=on_capture, on_cancel=on_cancel)
            return

        if request.mode == CaptureMode.REGION and is_wayland_session() and has_grim_and_slurp():
            pixmap = _capture_region_via_grim_slurp()
            if pixmap is None or pixmap.isNull():
                on_cancel()
            else:
                on_capture(pixmap)
            return

        snapshot = capture_full_screen()
        screenshot = snapshot.pixmap
        virtual_geometry = snapshot.virtual_geometry
        if screenshot.isNull() or virtual_geometry.isNull():
            on_cancel()
            return
        if request.mode == CaptureMode.FULL_SCREEN:
            on_capture(screenshot)
            return

        if request.mode == CaptureMode.REGION:
            overlay = RegionCaptureOverlay(screenshot, virtual_geometry)
            _track_overlay(overlay)
            overlay.capture_done.connect(on_capture)
            overlay.capture_done.connect(lambda _pixmap: _untrack_overlay(overlay))
            overlay.capture_cancelled.connect(on_cancel)
            overlay.capture_cancelled.connect(lambda: _untrack_overlay(overlay))
            overlay.show()
            overlay.raise_()
            overlay.activateWindow()
            overlay.grabKeyboard()
            overlay.repaint()
            return

        if is_wayland_session():
            QMessageBox.information(
                None,
                "Wayland Window Capture",
                "Window capture is limited on Wayland.\n"
                "Use Capture Area or Scroll capture instead.",
            )
            on_cancel()
            return

        if which("xdotool") is None or which("xwininfo") is None:
            QMessageBox.warning(
                None,
                "Window Capture Unavailable",
                "Window capture requires xdotool and xwininfo.\n"
                "Please run: python3 install_dependencies.py",
            )
            on_cancel()
            return
        overlay = WindowCaptureOverlay(screenshot, virtual_geometry)
        _track_overlay(overlay)
        overlay.show()
        overlay.raise_()
        overlay.activateWindow()
        overlay.grabKeyboard()
        overlay.repaint()

        process = subprocess.Popen(
            ["xdotool", "selectwindow"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        selection_state = {"cancelled": False}

        def cancel_selection() -> None:
            if selection_state["cancelled"]:
                return
            selection_state["cancelled"] = True
            if process.poll() is None:
                process.terminate()
            _untrack_overlay(overlay)
            overlay.close()
            on_cancel()

        overlay.capture_cancelled.connect(cancel_selection)

        def check_selection_process() -> None:
            if selection_state["cancelled"]:
                return
            return_code = process.poll()
            if return_code is None:
                QTimer.singleShot(70, check_selection_process)
                return

            _untrack_overlay(overlay)
            overlay.close()

            if return_code != 0:
                on_cancel()
                return

            selected_id_raw = (
                process.stdout.read().strip() if process.stdout is not None else ""
            )
            if not selected_id_raw:
                on_cancel()
                return
            selected_id = _resolve_top_level_window_id(selected_id_raw)
            if not selected_id:
                on_cancel()
                return
            geometry = _window_geometry_from_id(selected_id)
            if geometry.isNull():
                on_cancel()
                return
            local_rect = geometry.translated(
                -snapshot.virtual_geometry.x(),
                -snapshot.virtual_geometry.y(),
            ).intersected(snapshot.pixmap.rect())
            if local_rect.width() <= 1 or local_rect.height() <= 1:
                on_cancel()
                return
            on_capture(snapshot.pixmap.copy(local_rect))

        QTimer.singleShot(70, check_selection_process)

    if request.delay_seconds > 0:
        delay_state = {"cancelled": False}
        delay_overlay = CaptureDelayOverlay(request.delay_seconds)
        _track_overlay(delay_overlay)

        def on_delay_finished() -> None:
            _untrack_overlay(delay_overlay)
            if delay_state["cancelled"]:
                return
            begin_capture()

        def on_delay_cancelled() -> None:
            if delay_state["cancelled"]:
                return
            delay_state["cancelled"] = True
            _untrack_overlay(delay_overlay)
            on_cancel()

        delay_overlay.finished.connect(on_delay_finished)
        delay_overlay.cancelled.connect(on_delay_cancelled)
        delay_overlay.show()
        delay_overlay.raise_()
        delay_overlay.activateWindow()
    else:
        # Immediate captures still need a settle gap after the Capture panel hides.
        schedule_capture_after_ui_settle(begin_capture)


def _track_overlay(overlay: QWidget) -> None:
    """
    Stores overlay references to prevent premature garbage collection.

    Args:
        overlay: Overlay widget.

    Returns:
        None
    """

    _ACTIVE_OVERLAYS.append(overlay)


def _untrack_overlay(overlay: QWidget) -> None:
    """
    Removes closed overlays from active tracking list.

    Args:
        overlay: Overlay widget.

    Returns:
        None
    """

    if overlay in _ACTIVE_OVERLAYS:
        _ACTIVE_OVERLAYS.remove(overlay)


def select_video_region(
    on_selected: Callable[[QRect], None],
    on_cancel: Callable[[], None],
) -> None:
    """
    Shows the drag-select overlay for a video recording region.

    Args:
        on_selected: Callback invoked with the selected region in absolute
            virtual-desktop coordinates.
        on_cancel: Callback invoked when the selection is cancelled.

    Returns:
        None
    """

    def begin_selection() -> None:
        snapshot = capture_full_screen()
        screenshot = snapshot.pixmap
        virtual_geometry = snapshot.virtual_geometry
        if screenshot.isNull() or virtual_geometry.isNull():
            on_cancel()
            return

        overlay = RegionCaptureOverlay(screenshot, virtual_geometry)
        _track_overlay(overlay)
        overlay.region_selected.connect(on_selected)
        overlay.region_selected.connect(lambda _rect: _untrack_overlay(overlay))
        overlay.capture_cancelled.connect(on_cancel)
        overlay.capture_cancelled.connect(lambda: _untrack_overlay(overlay))
        overlay.show()
        overlay.raise_()
        overlay.activateWindow()
        overlay.grabKeyboard()
        overlay.repaint()

    schedule_capture_after_ui_settle(begin_selection)


def _build_color_picker_icon() -> QIcon:
    """
    Renders a compact eyedropper icon for capture panel action.

    Returns:
        QIcon: Icon image.
    """

    icon = QPixmap(18, 18)
    icon.fill(Qt.GlobalColor.transparent)
    painter = QPainter(icon)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(237, 242, 248), 1.6)
    painter.setPen(pen)
    painter.drawLine(4, 13, 13, 4)
    path = QPainterPath()
    path.addEllipse(11.5, 2.5, 4, 4)
    painter.drawPath(path)
    painter.drawLine(3, 14, 2, 16)
    painter.end()
    return QIcon(icon)

