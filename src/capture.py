"""
Screenshot capture panel and overlays.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from shutil import which
from typing import Callable

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QMouseEvent, QPainter, QPen, QPixmap
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
)

from src.constants import APP_NAME


class CaptureMode:
    """
    Provides capture mode identifiers.
    """

    FULL_SCREEN = "full_screen"
    REGION = "region"
    WINDOW = "window"


_ACTIVE_OVERLAYS: list[QWidget] = []


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
    autostart_toggled = Signal(bool)
    close_requested = Signal()
    editor_requested = Signal()

    def __init__(self) -> None:
        """
        Initializes the compact capture control panel.
        """

        super().__init__()
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
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        root_layout.addWidget(title)
        self.setStyleSheet(
            "QWidget { background: #242833; color: #e7ecf2; }"
            "QPushButton { background: #2f7dd1; color: #ffffff; border: none; padding: 6px 10px; border-radius: 4px; }"
            "QPushButton:hover { background: #4591e4; }"
            "QComboBox, QSpinBox { background: #2f3543; border: 1px solid #3e4657; padding: 3px; border-radius: 4px; }"
            "QFrame { border: 1px solid #3e4657; border-radius: 5px; }"
        )

        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        root_layout.addWidget(frame)
        form = QFormLayout(frame)

        self.delay_slider = QSlider(Qt.Orientation.Horizontal)
        self.delay_slider.setRange(0, 20)
        self.delay_slider.setValue(0)
        self.delay_slider.valueChanged.connect(self._sync_delay_label_from_slider)
        self.delay_slider.setToolTip("Delay capture start in seconds.")

        self.delay_value_label = QLabel("0 s")
        self.delay_value_label.setToolTip("Current delay before capture starts.")
        delay_row = QHBoxLayout()
        delay_row.addWidget(self.delay_slider, 1)
        delay_row.addWidget(self.delay_value_label)
        form.addRow("Delay:", delay_row)

        self._autostart_enabled = False

        self.open_editor_button = QPushButton("Open Editor")
        self.open_editor_button.setFlat(True)
        self.open_editor_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_editor_button.setStyleSheet(
            "QPushButton { color: #78b8ff; text-decoration: underline; background: transparent; border: none; padding: 2px 4px; }"
            "QPushButton:hover { color: #a9d1ff; }"
        )
        self.open_editor_button.setToolTip(
            "Open the editor window with your existing tabs."
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
        self.capture_fullscreen_button.clicked.connect(
            lambda: self._emit_request_for_mode(CaptureMode.FULL_SCREEN)
        )
        self.capture_fullscreen_button.setToolTip("Capture all screens immediately.")
        buttons.addWidget(self.capture_fullscreen_button)

        self.capture_area_button = QPushButton("Capture Area")
        self.capture_area_button.clicked.connect(
            lambda: self._emit_request_for_mode(CaptureMode.REGION)
        )
        self.capture_area_button.setToolTip("Select and capture a custom screen region.")
        buttons.addWidget(self.capture_area_button)

        self.capture_window_button = QPushButton("Capture Window")
        self.capture_window_button.clicked.connect(
            lambda: self._emit_request_for_mode(CaptureMode.WINDOW)
        )
        self.capture_window_button.setToolTip("Select one application window to capture.")
        buttons.addWidget(self.capture_window_button)

        root_layout.addLayout(buttons)

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
        self._dragging = False
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setGeometry(self._virtual_geometry)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def paintEvent(self, _) -> None:
        """
        Paints the screenshot background and selection rectangle.

        Returns:
            None
        """

        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._screenshot)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 60))
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
        self._dragging = True
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """
        Updates drag rectangle while moving.

        Args:
            event: Mouse event.

        Returns:
            None
        """

        if not self._dragging:
            return
        self._current_point = event.position().toPoint()
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
            self.capture_cancelled.emit()
            self.close()


class WindowCaptureOverlay(QWidget):
    """
    Full-screen overlay that highlights the window under cursor.
    """

    capture_done = Signal(QPixmap)
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
        if self._hover_rect.width() > 2 and self._hover_rect.height() > 2:
            self.capture_done.emit(self._screenshot.copy(self._to_local_rect(self._hover_rect)))
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


def detect_window_geometry(global_pos: QPoint) -> QRect:
    """
    Detects geometry of the X11 window below current cursor position.

    Args:
        global_pos: Global cursor position fallback.

    Returns:
        QRect: Detected window rectangle or fallback empty rectangle.
    """

    if which("xdotool") is None or which("xwininfo") is None:
        return QRect()
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
            return QRect()
        window_id = _resolve_top_level_window_id(window_match.group(1))
        if not window_id:
            return QRect()
        info = subprocess.run(
            ["xwininfo", "-id", window_id],
            capture_output=True,
            check=True,
            text=True,
            timeout=0.25,
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
        QTimer.singleShot(request.delay_seconds * 1000, begin_capture)
    else:
        begin_capture()


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

