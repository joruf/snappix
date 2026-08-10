"""
Screenshot capture panel and overlays.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from src.py_compat import dataclass
from typing import Callable

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QElapsedTimer, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QIcon,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRegion,
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
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
    QMessageBox,
    QProgressDialog,
)

from src.constants import APP_NAME
from src.auto_scroll_capture import MAX_SCROLL_FRAMES, perform_auto_scroll_capture
from src.crash_log import breadcrumb
from src.config import (
    CAPTURE_BACKEND_AUTO,
    CAPTURE_BACKEND_EXTERNAL,
    CAPTURE_BACKEND_QT,
    normalize_capture_backend,
)
from src.desktop_grab import (
    GRAB_BACKEND_QT,
    describe_grab_backends,
    grab_desktop_region,
    is_suspicious_fraction,
    verify_image_against_x11,
    visible_image_fraction,
    visible_pixmap_fraction,
)
from src.flow_layout import FlowLayoutWidget
from src.ocr import extract_text_from_png_bytes
from src.scroll_capture import pixmap_to_png_bytes
from src.platform import (
    capture_region_with_grim_slurp,
    get_x11_focused_window_id,
    has_grim_and_slurp,
    has_xdotool,
    has_xdotool_and_xwininfo,
    is_wayland_session,
    raise_x11_window,
)


class CaptureMode:
    """
    Provides capture mode identifiers.
    """

    FULL_SCREEN = "full_screen"
    CURRENT_SCREEN = "current_screen"
    REGION = "region"
    LAST_REGION = "last_region"
    WINDOW = "window"
    SCROLL = "scroll"


_ACTIVE_OVERLAYS: list[QWidget] = []

# Owning process per X11 window id, so the hit-test does not shell out to xprop on
# every poll. Bounded because X recycles window ids.
_X11_WINDOW_PID_CACHE: dict[str, int] = {}
_X11_WINDOW_PID_CACHE_LIMIT = 256

# Grab source for screenshots, mirrored from AppConfig.capture_backend.
_capture_backend_preference = CAPTURE_BACKEND_AUTO

# Identifier for "any external screenshot tool" inside the grab order.
_GRAB_SOURCE_EXTERNAL = "external"

# Set once Qt's own grab hands back an empty image, so later captures in this
# session go straight to an external tool instead of grabbing black again.
_qt_grab_unreliable = False

# The all-black explanation is shown once per session, not per capture.
_blank_capture_warning_shown = False

# Last dragged capture region, so the same area can be captured again without
# redrawing it -- the common case when documenting a sequence of steps.
_last_capture_region = QRect()

# Wait for the compositor to drop hidden Snappix windows (Capture panel, countdown)
# before sampling the framebuffer. Too short and the panel still appears in shots.
CAPTURE_UI_SETTLE_MS = 120

# Pen width of the window-capture highlight frame. The frame is offset by the same
# amount so it lands outside the target window instead of on its pixels.
HIGHLIGHT_FRAME_WIDTH = 2

# Live size readout next to the drag rectangle.
SIZE_READOUT_PADDING = 8
SIZE_READOUT_GAP = 6

# Loupe shown while picking a region. Nearest-neighbour at this zoom keeps single
# pixels square and countable, which is the point of the magnifier.
MAGNIFIER_SIZE = 132
MAGNIFIER_ZOOM = 8
MAGNIFIER_GAP = 24

# ---------------------------------------------------------------------------
# Capture panel startup width (client area in pixels).
# Change CAPTURE_PANEL_START_WIDTH to control how buttons wrap on startup.
# Height is always the minimum that fits the content at that width.
# ---------------------------------------------------------------------------
CAPTURE_PANEL_START_WIDTH = 420

# Quiet period after the last width change before the panel corrects its height.
# Long enough to sit out a continuous drag, short enough to feel immediate.
PANEL_HEIGHT_SETTLE_MS = 180


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
        backend: Grab source that produced the pixmap (``qt``, ``ffmpeg``, …).
        blank: True when every grab source returned an empty (black) image.
    """

    pixmap: QPixmap
    virtual_geometry: QRect
    backend: str = ""
    blank: bool = False


class CapturePanel(QWidget):
    """
    Compact panel to start screen captures.
    """

    capture_requested = Signal(CaptureRequest)
    video_capture_requested = Signal()
    color_pick_requested = Signal()
    measure_box_requested = Signal()
    measure_box_settings_requested = Signal(object)
    text_recognition_requested = Signal()
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
        self.setToolTip(
            "Capture panel: choose a capture mode, optional delay, or open the editor."
        )
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self._initial_position_done = False
        # Height is corrected only once the width stops changing. Resizing the
        # window from inside a resize event fights the window manager's own
        # interactive resize: each of our requests becomes the WM's new base
        # geometry, and the window ends up far taller than its content needs.
        self._height_settle_timer = QTimer(self)
        self._height_settle_timer.setSingleShot(True)
        self._height_settle_timer.setInterval(PANEL_HEIGHT_SETTLE_MS)
        self._height_settle_timer.timeout.connect(self.shrink_height_to_content)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(6)

        # No title label here: the window title bar already reads
        # "Snappix Capture", so repeating it only costs vertical space.

        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setToolTip("Capture timing: delay before the capture starts.")
        # Maximum, not the default Preferred: a Preferred frame happily absorbs
        # whatever vertical slack the window has, so the delay row kept the
        # panel tall after the buttons below it had already rewrapped smaller.
        frame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
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
        self._minimize_to_tray_on_close = True

        buttons_frame = QFrame()
        buttons_frame.setFrameShape(QFrame.Shape.StyledPanel)
        buttons_frame.setToolTip(
            "Capture actions: fullscreen, area, window, scroll, video, color picker, "
            "MeasureBox, OCR, and editor."
        )
        root_layout.addWidget(buttons_frame)
        buttons_frame_layout = QVBoxLayout(buttons_frame)
        buttons_frame_layout.setContentsMargins(8, 8, 8, 8)
        buttons_flow = FlowLayoutWidget(buttons_frame)
        buttons_frame_layout.addWidget(buttons_flow)
        button_widgets: list[QWidget] = []

        self.capture_fullscreen_button = QPushButton("Capture Fullscreen")
        self.capture_fullscreen_button.setObjectName("primaryButton")
        self.capture_fullscreen_button.clicked.connect(
            lambda: self._emit_request_for_mode(CaptureMode.FULL_SCREEN)
        )
        self.capture_fullscreen_button.setToolTip("Capture all screens immediately.")
        button_widgets.append(self.capture_fullscreen_button)

        self.capture_area_button = QPushButton("Capture Area")
        self.capture_area_button.setObjectName("primaryButton")
        self.capture_area_button.clicked.connect(
            lambda: self._emit_request_for_mode(CaptureMode.REGION)
        )
        self.capture_area_button.setToolTip("Select and capture a custom screen region.")
        button_widgets.append(self.capture_area_button)

        self.capture_window_button = QPushButton("Capture Window")
        self.capture_window_button.setObjectName("primaryButton")
        self.capture_window_button.clicked.connect(
            lambda: self._emit_request_for_mode(CaptureMode.WINDOW)
        )
        self.capture_window_button.setToolTip("Select one application window to capture.")
        button_widgets.append(self.capture_window_button)

        self.capture_screen_button = QPushButton("Capture Screen")
        self.capture_screen_button.setObjectName("primaryButton")
        self.capture_screen_button.clicked.connect(
            lambda: self._emit_request_for_mode(CaptureMode.CURRENT_SCREEN)
        )
        self.capture_screen_button.setToolTip(
            "Capture only the screen the mouse is on, not every monitor."
        )
        button_widgets.append(self.capture_screen_button)

        self.capture_scroll_button = QPushButton("Scroll")
        self.capture_scroll_button.setObjectName("primaryButton")
        self.capture_scroll_button.clicked.connect(
            lambda: self._emit_request_for_mode(CaptureMode.SCROLL)
        )
        self.capture_scroll_button.setToolTip(
            "Select a window and capture its full scrollable content automatically."
        )
        button_widgets.append(self.capture_scroll_button)

        self.capture_video_button = QPushButton("Capture Video")
        self.capture_video_button.setObjectName("primaryButton")
        self.capture_video_button.setToolTip(
            "Select a screen region and record it to video."
        )
        self.capture_video_button.clicked.connect(self.video_capture_requested.emit)
        # Hidden until ffmpeg availability is confirmed by the app controller.
        self.capture_video_button.hide()
        button_widgets.append(self.capture_video_button)

        self.pick_color_button = QPushButton("")
        self.pick_color_button.setIcon(_build_color_picker_icon())
        self.pick_color_button.setFixedSize(32, 32)
        self.pick_color_button.setToolTip(
            "Pick a color from the screen and copy it to clipboard."
        )
        self.pick_color_button.clicked.connect(self.color_pick_requested.emit)
        button_widgets.append(self.pick_color_button)

        self.measure_box_button = QPushButton("")
        self.measure_box_button.setIcon(_build_measure_box_icon())
        self.measure_box_button.setFixedSize(32, 32)
        self._measure_box_hotkey = ""
        self.set_measure_box_hotkey("")
        self.measure_box_button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.measure_box_button.clicked.connect(self.measure_box_requested.emit)
        self.measure_box_button.customContextMenuRequested.connect(
            self._emit_measure_box_settings_menu
        )
        button_widgets.append(self.measure_box_button)

        self.recognize_text_button = QPushButton("")
        self.recognize_text_button.setIcon(_build_text_recognition_icon())
        self.recognize_text_button.setFixedSize(32, 32)
        self.recognize_text_button.setToolTip(
            "Select a screen region, recognize its text, and copy it to clipboard."
        )
        self.recognize_text_button.clicked.connect(self.text_recognition_requested.emit)
        button_widgets.append(self.recognize_text_button)

        self._buttons_flow = buttons_flow

        button_widgets.append(self.open_editor_button)

        buttons_flow.set_flow_widgets(button_widgets)
        self._apply_platform_feature_availability()

    def _apply_platform_feature_availability(self) -> None:
        """
        Hides capture modes that are not available on the current OS.

        Window and scroll capture are available on Linux (X11) and Windows.
        Video visibility is controlled separately via
        ``set_video_capture_available``.

        Returns:
            None
        """

        from src.paths import supports_scroll_capture, supports_window_capture

        self.capture_window_button.setVisible(supports_window_capture())
        self.capture_scroll_button.setVisible(supports_scroll_capture())
        self._refresh_capture_button_flow()

    def _refresh_capture_button_flow(self) -> None:
        """
        Rebuilds the capture button flow from currently visible controls.

        Returns:
            None
        """

        # Every capture button belongs here. A button missing from this list
        # stays a child of the frame but is no longer managed by the flow
        # layout, so it keeps its last geometry and ends up drawn on top of its
        # neighbours or outside the panel.
        # Order matters: it is the wrap order. The three original capture
        # buttons stay on the first row at the default width, so the two modes
        # added later follow them instead of pushing them out of place.
        candidates = [
            self.capture_fullscreen_button,
            self.capture_area_button,
            self.capture_window_button,
            self.capture_screen_button,
            self.capture_scroll_button,
            self.capture_video_button,
            self.pick_color_button,
            self.measure_box_button,
            self.recognize_text_button,
            self.open_editor_button,
        ]
        visible_buttons = [button for button in candidates if not button.isHidden()]
        self._buttons_flow.set_flow_widgets(visible_buttons)
        self._apply_minimum_panel_width(visible_buttons)
        self.apply_content_height()

    def _apply_minimum_panel_width(self, visible_buttons: list[QWidget]) -> None:
        """
        Stops the panel from being dragged narrower than one row of buttons.

        Without a floor the window can be squeezed to a sliver: the flow layout
        then stacks every button in its own row and the panel shoots up to
        almost screen height. The floor is measured from the buttons themselves
        rather than hardcoded, so a translated interface with longer labels
        raises it accordingly.

        Setting the minimum on the flow container rather than the window lets Qt
        add the surrounding frame and layout margins itself.

        Args:
            visible_buttons: Buttons currently placed in the flow layout.

        Returns:
            None
        """

        if not visible_buttons:
            return

        primary = [
            button
            for button in (
                self.capture_fullscreen_button,
                self.capture_area_button,
                self.capture_window_button,
            )
            if not button.isHidden()
        ]
        if not primary:
            primary = [max(visible_buttons, key=lambda item: item.sizeHint().width())]

        spacing = max(0, self._buttons_flow.flow_layout.horizontalSpacing())
        margins = self._buttons_flow.flow_layout.contentsMargins()
        required = sum(button.sizeHint().width() for button in primary)
        required += spacing * (len(primary) - 1)
        required += margins.left() + margins.right()
        self._buttons_flow.setMinimumWidth(required)

        # The startup width is the width the button rows are designed for.
        # Narrower than that, the flow has to open another row and the panel
        # grows taller the more the user narrows it -- the opposite of what
        # dragging a window edge inward should do. Qt uses whichever floor is
        # larger, so a translation with wider buttons still wins.
        self.setMinimumWidth(max(1, int(CAPTURE_PANEL_START_WIDTH)))

    def set_video_capture_available(self, available: bool) -> None:
        """
        Shows or hides the video capture button based on ffmpeg availability.

        Args:
            available: Whether ffmpeg was found on the system.

        Returns:
            None
        """

        self.capture_video_button.setVisible(available)
        self.capture_video_button.setEnabled(available)
        if available:
            self.capture_video_button.setToolTip(
                "Select a screen region and record it to video."
            )
        else:
            self.capture_video_button.setToolTip(
                "Video capture requires ffmpeg. Please install ffmpeg to enable this feature."
            )
        self._refresh_capture_button_flow()

    def set_text_recognition_available(self, available: bool) -> None:
        """
        Shows or hides the text recognition button based on tesseract availability.

        Args:
            available: Whether the tesseract OCR binary was found on the system.

        Returns:
            None
        """

        self.recognize_text_button.setVisible(available)
        self.recognize_text_button.setEnabled(available)
        if available:
            self.recognize_text_button.setToolTip(
                "Select a screen region, recognize its text, and copy it to clipboard."
            )
        else:
            self.recognize_text_button.setToolTip(
                "Text recognition requires tesseract-ocr. Please install tesseract-ocr to enable this feature."
            )
        self._refresh_capture_button_flow()

    def set_measure_box_hotkey(self, hotkey_spec: str) -> None:
        """
        Updates the MeasureBox button tooltip with the current start hotkey.

        Args:
            hotkey_spec: Normalized hotkey string (e.g. ``ctrl+shift+m``).

        Returns:
            None
        """

        self._measure_box_hotkey = str(hotkey_spec or "").strip()
        self.measure_box_button.setToolTip(measure_box_button_tooltip(self._measure_box_hotkey))

    def _emit_measure_box_settings_menu(self, pos) -> None:
        """
        Emits a request to show the MeasureBox settings context menu.

        Args:
            pos: Local position inside the MeasureBox button.

        Returns:
            None
        """

        global_pos = self.measure_box_button.mapToGlobal(pos)
        self.measure_box_settings_requested.emit(global_pos)

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

        from src.platform import apply_linux_window_identity, apply_windows_window_icon

        super().showEvent(event)
        apply_windows_window_icon(self, self.windowIcon())
        apply_linux_window_identity(
            self,
            desktop_file_name="snappix",
            wm_instance="snappix",
            wm_class="snappix",
        )

    def resizeEvent(self, event) -> None:
        """
        Collapses the panel's height whenever its width changes.

        The action buttons sit in a flow layout, so a wider panel needs fewer
        rows. Without this the window keeps the taller geometry and leaves an
        empty band below the buttons.

        Args:
            event: Qt resize event.

        Returns:
            None
        """

        super().resizeEvent(event)
        if event.oldSize().width() == event.size().width():
            return
        # Applied on every step of the drag, not afterwards: this publishes a
        # size constraint rather than requesting a new geometry, so the window
        # manager clamps the height itself while it still owns the resize.
        self.apply_content_height()
        # The timer is the backstop for the final width, in case the last
        # resize event arrives before the flow layout has rewrapped.
        self._height_settle_timer.start()

    def shrink_height_to_content(self) -> None:
        """
        Resizes the panel to the smallest height its content needs.

        Returns:
            None
        """

        self.apply_content_height()

    def content_height(self) -> int:
        """
        Returns the smallest height the current width allows.

        ``minimumSizeHint()`` tracks the wrapped row count, because the flow
        container publishes its height-for-width as a minimum. ``sizeHint()``
        must never be used here -- it ignores height-for-width and reports one
        constant, tall value for every width.

        Returns:
            int: Required content height in pixels, or 0 when unknown.
        """

        layout = self.layout()
        buttons_flow = getattr(self, "_buttons_flow", None)
        if layout is not None:
            # invalidate() before activate(): activate() alone is a no-op when
            # the layout is not marked dirty, and a plain width change does not
            # mark it. Without this the flow container is still measured at its
            # previous width and the panel keeps the taller height.
            layout.invalidate()
            layout.activate()

        # The container learns its new width from the activate() above, but Qt
        # delivers that resize as a posted event. Rewrapping it here makes the
        # new row count readable in this same call, which is what allows the
        # height to be pinned while the drag is still running rather than after.
        if buttons_flow is not None:
            buttons_flow.update_flow_geometry()
            # updateGeometry() only posts a layout request to the parent, so the
            # frame around the buttons would still report the previous row
            # count. Invalidating every layout between the container and the
            # window makes the new height readable immediately.
            widget = buttons_flow
            while widget is not None:
                widget_layout = widget.layout()
                if widget_layout is not None:
                    widget_layout.invalidate()
                    widget_layout.activate()
                if widget is self:
                    break
                widget = widget.parentWidget()

        target_height = self.minimumSizeHint().height()
        if layout is not None and layout.hasHeightForWidth():
            content_width = max(1, self.contentsRect().width())
            target_height = max(target_height, layout.heightForWidth(content_width))
        return max(0, target_height)

    def apply_content_height(self) -> None:
        """
        Pins the panel to the height its content needs at the current width.

        The height is fixed rather than merely requested: the panel's height is
        fully determined by how the buttons wrap, so there is nothing for the
        user to drag vertically, and a fixed height is a constraint the window
        manager honours during its own interactive resize instead of a competing
        geometry request.

        Returns:
            None
        """

        target_height = self.content_height()
        if target_height <= 0:
            return
        if self.minimumHeight() == target_height and self.maximumHeight() == target_height:
            return
        self.setFixedHeight(target_height)

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
        Applies the Capture startup width with minimum content height and docks
        the panel top-right.

        Width comes from ``CAPTURE_PANEL_START_WIDTH`` at the top of this module.
        Height is the smallest value that fits the layout at that width.

        Returns:
            None
        """

        if self._initial_position_done:
            return
        width = max(1, int(CAPTURE_PANEL_START_WIDTH))
        self.setMaximumHeight(16777215)
        self.resize(width, 1)
        QApplication.processEvents()
        self.apply_content_height()
        self.resize(width, self.height())
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
        from src.platform import fit_top_level_window_to_available

        fit_top_level_window_to_available(self, margin=margin)
        # Keep the capture panel docked top-right after frame metrics settle.
        frame = self.frameGeometry()
        x = available.x() + max(0, available.width() - frame.width() - margin)
        y = max(available.y() + margin, min(frame.y(), available.y() + max(0, available.height() - frame.height())))
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
                self._draw_size_readout(painter, selection)
        if self.rect().contains(self._cursor_point):
            self._draw_magnifier(painter, self._cursor_point)

    def _draw_size_readout(self, painter: QPainter, selection: QRect) -> None:
        """
        Draws the live pixel size of the current selection.

        Placed outside the selection when there is room below it, so it never
        hides the content being captured.

        Args:
            painter: Active painter.
            selection: Selection rectangle in overlay coordinates.

        Returns:
            None
        """

        label = f"{selection.width()} x {selection.height()} px"
        metrics = painter.fontMetrics()
        text_width = metrics.horizontalAdvance(label)
        box = QRect(0, 0, text_width + (SIZE_READOUT_PADDING * 2), metrics.height() + 8)
        box.moveLeft(selection.left())
        below = selection.bottom() + SIZE_READOUT_GAP
        if below + box.height() <= self.height():
            box.moveTop(below)
        elif selection.top() - SIZE_READOUT_GAP - box.height() >= 0:
            box.moveTop(selection.top() - SIZE_READOUT_GAP - box.height())
        else:
            box.moveTop(selection.top() + SIZE_READOUT_GAP)
        box.moveLeft(max(0, min(box.left(), self.width() - box.width())))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(20, 20, 20, 220))
        painter.drawRoundedRect(box, 4, 4)
        painter.setPen(QColor(236, 240, 241, 255))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, label)

    def _draw_magnifier(self, painter: QPainter, cursor: QPoint) -> None:
        """
        Draws a zoomed loupe of the pixels around the cursor.

        Selecting an exact edge is guesswork at 1:1 -- the loupe shows the pixels
        under the crosshair magnified, with the cursor's screen coordinate.

        Args:
            painter: Active painter.
            cursor: Cursor position in overlay coordinates.

        Returns:
            None
        """

        source_span = max(4, MAGNIFIER_SIZE // MAGNIFIER_ZOOM)
        half = source_span // 2
        source = QRect(cursor.x() - half, cursor.y() - half, source_span, source_span)
        source = source.intersected(self.rect())
        if source.width() <= 0 or source.height() <= 0:
            return

        target = QRect(0, 0, MAGNIFIER_SIZE, MAGNIFIER_SIZE)
        target.moveTopLeft(cursor + QPoint(MAGNIFIER_GAP, MAGNIFIER_GAP))
        # Flip to the other side of the cursor when the loupe would leave the screen.
        if target.right() >= self.width():
            target.moveLeft(cursor.x() - MAGNIFIER_GAP - target.width())
        if target.bottom() >= self.height():
            target.moveTop(cursor.y() - MAGNIFIER_GAP - target.height())
        if not self.rect().contains(target):
            return

        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.drawPixmap(target, self._screenshot, source)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(20, 20, 20, 220), 3))
        painter.drawRect(target)
        painter.setPen(QPen(QColor(255, 255, 255, 240), 1))
        painter.drawRect(target)

        center = target.center()
        painter.setPen(QPen(QColor(231, 76, 60, 230), 1))
        painter.drawLine(target.left(), center.y(), target.right(), center.y())
        painter.drawLine(center.x(), target.top(), center.x(), target.bottom())

        global_point = cursor + self._virtual_geometry.topLeft()
        label = f"{global_point.x()}, {global_point.y()}"
        metrics = painter.fontMetrics()
        caption = QRect(
            target.left(),
            target.bottom() + 2,
            target.width(),
            metrics.height() + 4,
        )
        if caption.bottom() >= self.height():
            caption.moveTop(target.top() - caption.height() - 2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(20, 20, 20, 220))
        painter.drawRect(caption)
        painter.setPen(QColor(236, 240, 241, 255))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawText(caption, Qt.AlignmentFlag.AlignCenter, label)

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
            # Remember the region first: capture_done runs the whole post-capture
            # chain synchronously, including showing the panel again, and the
            # panel enables its repeat button from the stored region while
            # becoming visible. Emitting it afterwards left the button disabled
            # until the panel happened to be shown a second time.
            self.region_selected.emit(rect.translated(self._virtual_geometry.topLeft()))
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
RECORDING_TIMER_BAND_HEIGHT = 32
RECORDING_BORDER_ACTIVE_COLOR = QColor(231, 76, 60, 255)
RECORDING_BORDER_PAUSED_COLOR = QColor(243, 156, 18, 255)


def clamp_capture_rect_to_desktop(rect: QRect) -> QRect:
    """
    Keeps one capture rectangle fully inside the combined virtual desktop bounds.

    Args:
        rect: Requested capture region in absolute screen coordinates.

    Returns:
        QRect: Clamped region with the same size as ``rect``.
    """

    screens = QGuiApplication.screens()
    if not screens:
        return rect

    virtual = QRect()
    for screen in screens:
        virtual = virtual.united(screen.geometry())

    max_x = virtual.x() + max(0, virtual.width() - rect.width())
    max_y = virtual.y() + max(0, virtual.height() - rect.height())
    return QRect(
        max(virtual.x(), min(rect.x(), max_x)),
        max(virtual.y(), min(rect.y(), max_y)),
        rect.width(),
        rect.height(),
    )


def recording_overlay_geometry(capture_rect: QRect) -> QRect:
    """
    Returns the outer overlay geometry surrounding one capture rectangle.

    Args:
        capture_rect: Recorded region in absolute virtual-desktop coordinates.

    Returns:
        QRect: Overlay geometry including border margin and timer band.
    """

    return capture_rect.adjusted(
        -RECORDING_BORDER_THICKNESS,
        -RECORDING_BORDER_THICKNESS - RECORDING_TIMER_BAND_HEIGHT,
        RECORDING_BORDER_THICKNESS,
        RECORDING_BORDER_THICKNESS,
    )


class RecordingBorderOverlay(QWidget):
    """
    Blinking border shown just outside the region currently being video-recorded.

    The border is drawn entirely outside the recorded pixels (in a margin
    added around the capture rect) so it never contaminates the ffmpeg
    capture itself -- it is purely a visual indicator for the user.
    """

    region_moved = Signal(QRect)

    def __init__(self, capture_rect: QRect) -> None:
        """
        Initializes the border overlay around one screen-recording region.

        Args:
            capture_rect: Recorded region in absolute virtual-desktop coordinates.
        """

        super().__init__()
        self._capture_rect = QRect(capture_rect)
        self._paused = False
        self._blink_on = True
        self._accumulated_ms = 0
        self._recording_active = True
        self._session_timer = QElapsedTimer()
        self._session_timer.start()
        self._dragging = False
        self._drag_start_global = QPoint()
        self._drag_capture_origin = QPoint()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setMouseTracking(True)
        self._timer_band_height = RECORDING_TIMER_BAND_HEIGHT
        self.set_capture_rect(self._capture_rect)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_blink_tick)
        self._timer.start(RECORDING_BORDER_BLINK_MS)
        self._display_timer = QTimer(self)
        self._display_timer.timeout.connect(self.update)
        self._display_timer.start(250)

    def capture_rect(self) -> QRect:
        """
        Returns the current recorded region in screen coordinates.

        Returns:
            QRect: Active capture rectangle.
        """

        return QRect(self._capture_rect)

    def set_capture_rect(self, capture_rect: QRect) -> None:
        """
        Moves the overlay to surround a new capture rectangle.

        Args:
            capture_rect: New recorded region in absolute screen coordinates.

        Returns:
            None
        """

        self._capture_rect = clamp_capture_rect_to_desktop(QRect(capture_rect))
        self.setGeometry(recording_overlay_geometry(self._capture_rect))
        self._update_input_mask()
        self.update()

    def _inner_capture_rect(self) -> QRect:
        """
        Returns the pass-through hole matching the recorded pixels.

        Returns:
            QRect: Inner rectangle in widget coordinates.
        """

        return QRect(
            RECORDING_BORDER_THICKNESS,
            self._timer_band_height + RECORDING_BORDER_THICKNESS,
            self._capture_rect.width(),
            self._capture_rect.height(),
        )

    def _update_input_mask(self) -> None:
        """
        Limits mouse input to the border frame and timer band.

        Returns:
            None
        """

        outer = QRegion(0, 0, self.width(), self.height())
        inner = QRegion(self._inner_capture_rect())
        self.setMask(outer.subtracted(inner))

    def _current_elapsed_ms(self) -> int:
        """
        Returns elapsed recording time excluding paused intervals.

        Returns:
            int: Elapsed time in milliseconds.
        """

        total = self._accumulated_ms
        if self._recording_active:
            total += self._session_timer.elapsed()
        return total

    def _format_elapsed(self) -> str:
        """
        Formats the elapsed recording time as minutes and seconds.

        Returns:
            str: Time string in M:SS format.
        """

        total_seconds = self._current_elapsed_ms() // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}:{seconds:02d}"

    def set_paused(self, paused: bool) -> None:
        """
        Switches the border between the blinking "recording" and static "paused" look.

        Args:
            paused: True to show a static paused-colored border.

        Returns:
            None
        """

        if paused and not self._paused:
            if self._recording_active:
                self._accumulated_ms += self._session_timer.elapsed()
                self._recording_active = False
        elif not paused and self._paused:
            self._session_timer.restart()
            self._recording_active = True
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

    def _timer_pill_rect(self) -> QRectF:
        """
        Returns the elapsed-time label rectangle above the recording border.

        Returns:
            QRectF: Timer pill bounds in widget coordinates.
        """

        elapsed_text = self._format_elapsed()
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        metrics = QFontMetrics(font)
        text_width = metrics.horizontalAdvance(elapsed_text)
        text_height = metrics.height()
        inner_left = RECORDING_BORDER_THICKNESS
        inner_width = self.width() - 2 * RECORDING_BORDER_THICKNESS
        pill_pad_x = 8
        pill_pad_y = 3
        pill_width = text_width + 2 * pill_pad_x
        pill_height = text_height + 2 * pill_pad_y
        pill_x = inner_left + (inner_width - pill_width) / 2.0
        pill_y = max(2.0, (self._timer_band_height - pill_height) / 2.0)
        return QRectF(pill_x, pill_y, pill_width, pill_height)

    def paintEvent(self, _event) -> None:
        """
        Paints the border ring in the margin surrounding the recorded region.

        Returns:
            None
        """

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        if self._paused or self._blink_on:
            color = RECORDING_BORDER_PAUSED_COLOR if self._paused else RECORDING_BORDER_ACTIVE_COLOR
            painter.setPen(QPen(color, RECORDING_BORDER_THICKNESS))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            half = RECORDING_BORDER_THICKNESS / 2.0
            border_top = float(self._timer_band_height) + half
            painter.drawRect(
                QRectF(
                    half,
                    border_top,
                    self.width() - RECORDING_BORDER_THICKNESS,
                    self.height() - self._timer_band_height - RECORDING_BORDER_THICKNESS,
                )
            )

        elapsed_text = self._format_elapsed()
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        pill_rect = self._timer_pill_rect()
        pill_pad_x = 8
        pill_pad_y = 3
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 170))
        painter.drawRoundedRect(pill_rect, 4, 4)
        text_color = RECORDING_BORDER_PAUSED_COLOR if self._paused else QColor(255, 255, 255)
        painter.setPen(text_color)
        painter.drawText(
            int(pill_rect.x() + pill_pad_x),
            int(pill_rect.y() + pill_pad_y + metrics.ascent()),
            elapsed_text,
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """
        Starts dragging the capture region from the border frame.

        Args:
            event: Mouse press event.

        Returns:
            None
        """

        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._dragging = True
        self._drag_start_global = event.globalPosition().toPoint()
        self._drag_capture_origin = self._capture_rect.topLeft()
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """
        Updates the overlay position while dragging the border frame.

        Args:
            event: Mouse move event.

        Returns:
            None
        """

        if self._dragging:
            delta = event.globalPosition().toPoint() - self._drag_start_global
            moved_rect = QRect(self._drag_capture_origin + delta, self._capture_rect.size())
            self.set_capture_rect(moved_rect)
            event.accept()
            return
        self.setCursor(Qt.CursorShape.SizeAllCursor)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """
        Commits one capture-region move after a border drag.

        Args:
            event: Mouse release event.

        Returns:
            None
        """

        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._dragging:
            self._dragging = False
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            self.region_moved.emit(self.capture_rect())
            event.accept()

    def closeEvent(self, event) -> None:
        """
        Stops the blink timer before the overlay closes.

        Args:
            event: Qt close event.

        Returns:
            None
        """

        self._timer.stop()
        self._display_timer.stop()
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

    from src.paths import is_windows, supports_scroll_capture

    if is_wayland_session():
        QMessageBox.information(
            None,
            "Scroll Capture",
            "Automatic scroll capture requires X11 window control.\n"
            "Use Capture Area on Wayland instead.",
        )
        on_cancel()
        return

    if not supports_scroll_capture():
        QMessageBox.information(
            None,
            "Scroll Capture",
            "Automatic scroll capture is not available on this operating system yet.\n"
            "Use Capture Area instead.",
        )
        on_cancel()
        return

    if not is_windows() and not has_xdotool_and_xwininfo():
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
    if snapshot.blank:
        _warn_blank_capture_once()

    if is_windows():
        _execute_scroll_capture_windows(
            snapshot=snapshot,
            on_capture=on_capture,
            on_cancel=on_cancel,
        )
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

    # Same constraint as window capture: the overlay is input-transparent so
    # xdotool can pick the window underneath, so no window of ours can receive
    # Escape. A passive global listener is what makes cancelling work.
    # Imported lazily: pynput chooses a backend at import time and fails on a
    # display-less session, which must not break importing this module.
    from src.global_hotkeys import EscapeListener

    escape_listener = EscapeListener()

    def finish_selection() -> None:
        escape_listener.stop()
        _untrack_overlay(overlay)
        overlay.close()

    def cancel_selection() -> None:
        if selection_state["cancelled"]:
            return
        selection_state["cancelled"] = True
        if process.poll() is None:
            process.terminate()
        finish_selection()
        on_cancel()

    overlay.capture_cancelled.connect(cancel_selection)
    escape_listener.escape_pressed.connect(cancel_selection)
    escape_listener.start()

    def check_selection_process() -> None:
        if selection_state["cancelled"]:
            return
        return_code = process.poll()
        if return_code is None:
            QTimer.singleShot(70, check_selection_process)
            return

        finish_selection()

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

        _run_scroll_capture_after_pick(
            window_id=window_id,
            global_rect=global_rect,
            on_capture=on_capture,
            on_cancel=on_cancel,
            raise_window=raise_x11_window,
            previous_focus_window_id=get_x11_focused_window_id(),
        )

    QTimer.singleShot(70, check_selection_process)


def _execute_scroll_capture_windows(
    *,
    snapshot,
    on_capture: Callable[[QPixmap], None],
    on_cancel: Callable[[], None],
) -> None:
    """
    Windows scroll pick: overlay click → Win32 HWND → auto-scroll stitch.

    Args:
        snapshot: Pre-captured desktop snapshot for the pick overlay.
        on_capture: Callback invoked with stitched pixmap.
        on_cancel: Callback when capture is cancelled.

    Returns:
        None
    """

    from src.win32_window import get_foreground_hwnd, raise_window

    overlay = WindowCaptureOverlay(
        snapshot.pixmap,
        snapshot.virtual_geometry,
        accept_mouse_input=True,
    )
    _track_overlay(overlay)
    selection_state = {"done": False}

    def finish_cancel() -> None:
        if selection_state["done"]:
            return
        selection_state["done"] = True
        _untrack_overlay(overlay)
        overlay.close()
        on_cancel()

    def on_window_selected(window_id: str, global_rect: QRect, _pixmap: QPixmap) -> None:
        if selection_state["done"]:
            return
        selection_state["done"] = True
        _untrack_overlay(overlay)
        overlay.close()
        if not window_id or global_rect.isNull():
            on_cancel()
            return
        previous_focus = str(get_foreground_hwnd() or "")
        _run_scroll_capture_after_pick(
            window_id=window_id,
            global_rect=global_rect,
            on_capture=on_capture,
            on_cancel=on_cancel,
            raise_window=lambda hwnd_str: raise_window(int(hwnd_str)),
            previous_focus_window_id=previous_focus,
        )

    def on_capture_done_without_id(pixmap: QPixmap) -> None:
        # Fallback if only capture_done fired without window_selected.
        if selection_state["done"]:
            return
        # Prefer window_selected; ignore bare pixmap-only completion here.
        _ = pixmap

    overlay.window_selected.connect(on_window_selected)
    overlay.capture_done.connect(on_capture_done_without_id)
    overlay.capture_cancelled.connect(finish_cancel)
    overlay.show()
    overlay.raise_()
    overlay.activateWindow()
    overlay.grabKeyboard()
    overlay.repaint()


def _run_scroll_capture_after_pick(
    *,
    window_id: str,
    global_rect: QRect,
    on_capture: Callable[[QPixmap], None],
    on_cancel: Callable[[], None],
    raise_window: Callable[[str], bool],
    previous_focus_window_id: str,
) -> None:
    """
    Runs the auto-scroll loop after a window has been selected.

    Args:
        window_id: Target window id / HWND string.
        global_rect: Window geometry in global coordinates.
        on_capture: Success callback.
        on_cancel: Cancel/failure callback.
        raise_window: Callable that raises the target window before each grab.
        previous_focus_window_id: Window to restore after capture.

    Returns:
        None
    """

    progress = ScrollCaptureProgressDialog(
        global_rect.width(),
        global_rect.height(),
    )
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
            raise_window(window_id)
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


class WindowCaptureOverlay(QWidget):
    """
    Full-screen overlay that highlights the window under cursor.

    The highlight frame is drawn outside the target window, so nothing that the
    capture will contain is covered while picking.
    """

    capture_done = Signal(QPixmap)
    window_selected = Signal(str, QRect, QPixmap)
    capture_cancelled = Signal()

    def __init__(
        self,
        screenshot: QPixmap,
        virtual_geometry: QRect,
        *,
        accept_mouse_input: bool = False,
    ) -> None:
        """
        Initializes window detection overlay.

        Args:
            screenshot: Current desktop screenshot.
            virtual_geometry: Combined virtual desktop geometry.
            accept_mouse_input: When True (Windows), the overlay receives clicks
                and completes capture via ``mouseReleaseEvent``. When False
                (Linux X11), the overlay is click-through so ``xdotool`` can pick.
        """

        super().__init__()
        self._screenshot = screenshot
        self._virtual_geometry = virtual_geometry
        self._hover_rect = QRect()
        self._hover_label = ""
        # Claim the window id before the first poll: X11 lists this overlay in the
        # stacking order even though it is click-through, so without excluding it
        # every hit-test returns the overlay and the highlight frame ends up
        # around the whole desktop instead of the target window.
        self._exclude_hwnds: tuple[int, ...] = self._own_window_ids()
        self._accept_mouse_input = accept_mouse_input
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(70)
        self._poll_timer.timeout.connect(self._update_hover_from_cursor)
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        if not accept_mouse_input:
            flags |= Qt.WindowType.WindowTransparentForInput
        self.setWindowFlags(flags)
        self.setGeometry(self._virtual_geometry)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._escape_shortcut = _install_escape_shortcut(self, self._cancel_capture)
        self._poll_timer.start()

    def showEvent(self, event) -> None:
        """
        Records this overlay HWND so Win32 hit-tests can skip it.

        Args:
            event: Qt show event.

        Returns:
            None
        """

        super().showEvent(event)
        self._exclude_hwnds = self._own_window_ids()

    def _own_window_ids(self) -> tuple[int, ...]:
        """
        Returns this overlay's native window id for hit-test exclusion.

        On X11 this is only a first line of defence -- Qt can recreate the native
        window while showing it, so the reliable exclusion happens by process id
        inside ``_x11_window_id_at_point``. On Windows the id is what counts.

        Returns:
            tuple[int, ...]: Window id, empty when it cannot be determined.
        """

        try:
            return (int(self.winId()),)
        except (RuntimeError, TypeError, ValueError):
            return ()

    def _highlight_frame_rect(self, local_rect: QRect) -> QRect:
        """
        Returns the frame rectangle drawn around a target window.

        The frame sits fully *outside* the target so it never covers pixels that
        the capture will contain. A window flush against a desktop edge has no
        room there, so on that side the frame is pulled back onto the screen --
        visible beats correct-but-invisible.

        Args:
            local_rect: Target window rectangle in overlay coordinates.

        Returns:
            QRect: Rectangle to stroke with the highlight pen.
        """

        offset = HIGHLIGHT_FRAME_WIDTH
        outer = local_rect.adjusted(-offset, -offset, offset, offset)
        available = self.rect().adjusted(
            HIGHLIGHT_FRAME_WIDTH // 2,
            HIGHLIGHT_FRAME_WIDTH // 2,
            -HIGHLIGHT_FRAME_WIDTH // 2,
            -HIGHLIGHT_FRAME_WIDTH // 2,
        )
        return QRect(
            max(outer.x(), available.x()),
            max(outer.y(), available.y()),
            min(outer.right(), available.right()) - max(outer.x(), available.x()),
            min(outer.bottom(), available.bottom()) - max(outer.y(), available.y()),
        )

    def _label_y_outside(self, local_rect: QRect, label_height: int) -> int:
        """
        Returns the geometry label's y position, kept off the captured area.

        Args:
            local_rect: Target window rectangle in overlay coordinates.
            label_height: Label height in pixels.

        Returns:
            int: Label top edge in overlay coordinates.
        """

        gap = HIGHLIGHT_FRAME_WIDTH + 4
        above = local_rect.y() - label_height - gap
        if above >= 0:
            return above
        below = local_rect.bottom() + gap
        if below + label_height <= self.height():
            return below
        # Neither side has room (window taller than the desktop): keep it visible.
        return max(0, local_rect.y())

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
            painter.setPen(QPen(QColor(46, 204, 113), HIGHLIGHT_FRAME_WIDTH))
            painter.drawRect(self._highlight_frame_rect(local_rect))
            if self._hover_label:
                label_padding = 8
                label_height = 24
                label_width = max(180, len(self._hover_label) * 8)
                label_x = local_rect.x()
                label_y = self._label_y_outside(local_rect, label_height)
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

        rect = detect_window_geometry(
            event.globalPosition().toPoint(),
            exclude_hwnds=self._exclude_hwnds,
        )
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
        window_id, global_rect = detect_window_at_point(
            event.globalPosition().toPoint(),
            exclude_hwnds=self._exclude_hwnds,
        )
        if global_rect.width() > 2 and global_rect.height() > 2:
            local_rect = self._to_local_rect(global_rect)
            local_rect = local_rect.intersected(self._screenshot.rect())
            if local_rect.width() <= 1 or local_rect.height() <= 1:
                self.capture_cancelled.emit()
                self.close()
                return
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

        rect = detect_window_geometry(QCursor.pos(), exclude_hwnds=self._exclude_hwnds)
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

def _x11_stacking_order() -> list[str]:
    """
    Returns visible top-level window ids from bottom to top.

    Args:
        None

    Returns:
        list[str]: Decimal window ids in stacking order, bottom first.
    """

    try:
        output = subprocess.run(
            ["xprop", "-root", "_NET_CLIENT_LIST_STACKING"],
            capture_output=True,
            check=True,
            text=True,
            timeout=0.5,
        ).stdout
    except Exception:
        return []
    return [str(int(match, 16)) for match in re.findall(r"0x[0-9a-fA-F]+", output)]


def _x11_window_pid(window_id: str) -> int:
    """
    Returns the process id that owns one X11 window.

    Args:
        window_id: Decimal window id.

    Returns:
        int: Owning process id, or 0 when the window publishes none.
    """

    cached = _X11_WINDOW_PID_CACHE.get(window_id)
    if cached is not None:
        return cached
    pid = 0
    try:
        output = subprocess.run(
            ["xprop", "-id", window_id, "_NET_WM_PID"],
            capture_output=True,
            check=False,
            text=True,
            timeout=0.5,
        ).stdout
        match = re.search(r"=\s*(\d+)", output)
        if match:
            pid = int(match.group(1))
    except Exception:
        pid = 0
    if len(_X11_WINDOW_PID_CACHE) > _X11_WINDOW_PID_CACHE_LIMIT:
        # X recycles window ids, so the cache is dropped instead of growing stale.
        _X11_WINDOW_PID_CACHE.clear()
    _X11_WINDOW_PID_CACHE[window_id] = pid
    return pid


def _normalize_window_ids(window_ids) -> frozenset[str]:
    """
    Normalizes window ids to the decimal string form used on X11.

    Args:
        window_ids: Window ids as ints, decimal strings, or hex strings.

    Returns:
        frozenset[str]: Decimal window ids.
    """

    normalized: set[str] = set()
    for value in window_ids or ():
        try:
            if isinstance(value, str):
                text = value.strip()
                normalized.add(str(int(text, 16) if text.lower().startswith("0x") else int(text)))
            else:
                normalized.add(str(int(value)))
        except (TypeError, ValueError):
            continue
    return frozenset(normalized)


def _x11_window_id_at_point(
    global_pos: QPoint,
    exclude_ids: frozenset[str] = frozenset(),
) -> str:
    """
    Finds the topmost window covering one screen coordinate.

    ``xdotool getmouselocation`` can only ever answer for the real pointer, so
    it cannot serve a caller asking about an arbitrary point -- it silently
    returns the window under the mouse instead, which is the wrong window and,
    once resolved upward, often the desktop. Walking the stacking order from the
    top down answers the question that was actually asked.

    Args:
        global_pos: Point in global screen coordinates.
        exclude_ids: Window ids to skip, such as Snappix's own capture overlay.
            The overlay is click-through for the pointer, but X11 still lists it
            in the stacking order, so without this it wins every hit-test.

    Returns:
        str: Window id, or an empty string when nothing matches.
    """

    own_pid = os.getpid()
    current_desktop = _x11_current_desktop()
    for window_id in reversed(_x11_stacking_order()):
        if window_id in exclude_ids:
            continue
        geometry = _window_geometry_from_id(window_id)
        if geometry.isNull() or not geometry.contains(global_pos):
            continue
        if not _x11_window_is_pickable(window_id, current_desktop):
            continue
        # Snappix's own capture overlay covers the whole desktop and is listed in
        # the stacking order even though it is click-through, so it would win every
        # hit-test and the highlight frame would sit on the outermost screen edge.
        # Its Qt window id is not reliable here (Qt recreates the native window
        # while showing it), so ownership is decided by process id.
        if _x11_window_pid(window_id) == own_pid:
            continue
        return window_id
    return ""


def detect_window_at_point(
    global_pos: QPoint,
    *,
    exclude_hwnds: tuple[int, ...] | list[int] = (),
) -> tuple[str, QRect]:
    """
    Detects the top-level window id and geometry below one global cursor position.

    On Linux this uses xdotool/xwininfo. On Windows it uses Win32 EnumWindows.

    Args:
        global_pos: Global cursor position.
        exclude_hwnds: Window ids to ignore -- on both platforms this is how the
            capture overlay keeps itself out of its own hit-test.

    Returns:
        tuple[str, QRect]: Window id and geometry, or empty values when unknown.
    """

    from src.paths import is_windows

    if is_windows():
        from src.win32_window import window_at_point

        hwnd, geometry = window_at_point(
            global_pos.x(),
            global_pos.y(),
            exclude_hwnds=exclude_hwnds,
        )
        if not hwnd or geometry.isNull():
            return "", QRect()
        return str(hwnd), geometry

    if not has_xdotool_and_xwininfo():
        return "", QRect()
    excluded = _normalize_window_ids(exclude_hwnds)
    try:
        window_id = _x11_window_id_at_point(global_pos, excluded)
        if window_id:
            return window_id, _window_geometry_from_id(window_id)

        # Fallback for window managers that publish no stacking hint: the
        # pointer's own window. Only correct when the caller asks about the
        # cursor, which is what every current caller does.
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
        if window_match.group(1) in excluded:
            return "", QRect()
        resolved = _resolve_top_level_window_id(window_match.group(1))
        if not resolved or resolved in excluded:
            return "", QRect()
        return resolved, _window_geometry_from_id(resolved)
    except Exception:
        return "", QRect()


def detect_window_geometry(
    global_pos: QPoint,
    *,
    exclude_hwnds: tuple[int, ...] | list[int] = (),
) -> QRect:
    """
    Detects geometry of the window below the current cursor position.

    Args:
        global_pos: Global cursor position fallback.
        exclude_hwnds: Optional HWNDs to ignore on Windows.

    Returns:
        QRect: Detected window rectangle or fallback empty rectangle.
    """

    _window_id, geometry = detect_window_at_point(
        global_pos,
        exclude_hwnds=exclude_hwnds,
    )
    return geometry


def select_window_geometry() -> QRect:
    """
    Uses xdotool selectwindow to robustly pick a target window by click.

    Returns:
        QRect: Selected window geometry in global coordinates or empty rect.
    """

    if not has_xdotool_and_xwininfo():
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


def geometry_for_selected_window(
    selected_id: str,
    cursor_pos: QPoint,
    *,
    exclude_hwnds: tuple[int, ...] | list[int] = (),
) -> QRect:
    """
    Returns the geometry to capture for a window picked by ``xdotool``.

    The picking overlay is meant to be click-through, but not every window
    manager honours the input shape. Muffin hands ``xdotool selectwindow`` the
    overlay itself, whose geometry is the whole virtual desktop -- so the
    capture quietly became a full-desktop screenshot even though the highlight
    frame, which uses the point lookup, had shown the correct window all along.

    Args:
        selected_id: Window id reported by ``xdotool selectwindow``.
        cursor_pos: Position that was clicked.
        exclude_hwnds: Window ids the point lookup must ignore.

    Returns:
        QRect: Geometry of the window to capture, empty when unknown.
    """

    if _x11_window_pid(selected_id) == os.getpid():
        _fallback_id, geometry = detect_window_at_point(
            cursor_pos,
            exclude_hwnds=exclude_hwnds,
        )
        return geometry
    return _window_geometry_from_id(selected_id)


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


def _x11_current_desktop() -> int | None:
    """
    Returns the active workspace index.

    Returns:
        int | None: Workspace index, or None when it cannot be read.
    """

    try:
        output = subprocess.run(
            ["xprop", "-root", "_NET_CURRENT_DESKTOP"],
            capture_output=True,
            check=True,
            text=True,
            timeout=0.4,
        ).stdout
    except Exception:
        return None
    match = re.search(r"=\s*(\d+)", output)
    return int(match.group(1)) if match else None


def _x11_window_is_pickable(window_id: str, current_desktop: int | None) -> bool:
    """
    Reports whether a window can be the visible target at a screen point.

    Minimized windows and windows on another workspace stay in
    ``_NET_CLIENT_LIST_STACKING`` and keep their geometry, and Muffin even keeps
    them mapped so it can show previews. Without this check the topmost *listed*
    window wins the hit-test even when the user cannot see it -- picking a
    maximized minimized browser instead of the small window actually on screen,
    which then looks like a whole-monitor screenshot.

    Args:
        window_id: Target window id.
        current_desktop: Active workspace index, or None when unknown.

    Returns:
        bool: True when the window is a plausible pick.
    """

    try:
        output = subprocess.run(
            ["xprop", "-id", window_id, "_NET_WM_STATE", "_NET_WM_DESKTOP"],
            capture_output=True,
            check=True,
            text=True,
            timeout=0.4,
        ).stdout
    except Exception:
        # No answer: keep the window rather than silently dropping a valid target.
        return True

    if "_NET_WM_STATE_HIDDEN" in output:
        return False

    if current_desktop is None:
        return True
    desktop_match = re.search(r"_NET_WM_DESKTOP\(CARDINAL\)\s*=\s*(\d+)", output)
    if not desktop_match:
        return True
    desktop = int(desktop_match.group(1))
    # 0xFFFFFFFF marks a window shown on every workspace.
    if desktop == 0xFFFFFFFF:
        return True
    return desktop == current_desktop


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


def screen_rect_under_cursor() -> QRect:
    """
    Returns the geometry of the screen the mouse pointer is on.

    Args:
        None

    Returns:
        QRect: Screen rectangle in virtual-desktop coordinates, empty when no
        screen can be determined.
    """

    screen = QGuiApplication.screenAt(QCursor.pos())
    if screen is None:
        screen = QGuiApplication.primaryScreen()
    if screen is None:
        return QRect()
    return QRect(screen.geometry())


def remember_capture_region(rect: QRect) -> None:
    """
    Stores one captured region so it can be repeated.

    Args:
        rect: Region in virtual-desktop coordinates.

    Returns:
        None
    """

    global _last_capture_region

    if rect.width() > 0 and rect.height() > 0:
        _last_capture_region = QRect(rect)


def last_capture_region() -> QRect:
    """
    Returns the most recently captured region.

    Args:
        None

    Returns:
        QRect: Stored region, empty when nothing was captured yet.
    """

    return QRect(_last_capture_region)


def has_last_capture_region() -> bool:
    """
    Reports whether a region capture can be repeated.

    Args:
        None

    Returns:
        bool: True when a usable region is stored.
    """

    return _last_capture_region.width() > 0 and _last_capture_region.height() > 0


def crop_snapshot_to_rect(snapshot: DesktopSnapshot, rect: QRect) -> QPixmap:
    """
    Cuts one region out of a virtual-desktop snapshot.

    Args:
        snapshot: Captured virtual desktop.
        rect: Region in virtual-desktop coordinates.

    Returns:
        QPixmap: Cropped image, null when the region is unusable or lies
        outside the captured desktop.
    """

    if snapshot.pixmap.isNull() or rect.width() <= 0 or rect.height() <= 0:
        return QPixmap()
    local = rect.translated(-snapshot.virtual_geometry.topLeft())
    local = local.intersected(QRect(0, 0, snapshot.pixmap.width(), snapshot.pixmap.height()))
    if local.width() <= 0 or local.height() <= 0:
        return QPixmap()
    return snapshot.pixmap.copy(local)


def set_capture_backend_preference(backend: str) -> None:
    """
    Sets which grab source screenshots should use.

    Args:
        backend: One of ``auto``, ``qt``, or ``external``.

    Returns:
        None
    """

    global _capture_backend_preference
    _capture_backend_preference = normalize_capture_backend(backend)


def capture_backend_preference() -> str:
    """
    Returns the configured grab source for screenshots.

    Returns:
        str: One of ``auto``, ``qt``, or ``external``.
    """

    return _capture_backend_preference


def qt_grab_unreliable() -> bool:
    """
    Returns whether Qt's own screen grab came back empty in this session.

    Returns:
        bool: True once a Qt grab produced a blank image.
    """

    return _qt_grab_unreliable


def _compose_qt_desktop_grab(
    screens: list,
    virtual_geometry: QRect,
) -> tuple[QPixmap, float]:
    """
    Grabs every screen with Qt and composes them into one virtual desktop image.

    Each screen is measured on its own. A broken grab is not always
    all-or-nothing: on a multi-monitor desktop one screen can come back black
    while the other is fine, and judging only the composed image would call that
    a success and freeze a half-black desktop into the capture overlay.

    Args:
        screens: Screens to grab.
        virtual_geometry: Bounding rectangle across all screens.

    Returns:
        tuple[QPixmap, float]: Composed pixmap (null when no screen delivered
        data) and the visible-content share of the *worst* screen.
    """

    composed = QPixmap(virtual_geometry.size())
    composed.fill(Qt.GlobalColor.transparent)
    painted = False
    worst_fraction = 1.0
    painter = QPainter(composed)
    for screen in screens:
        geometry = screen.geometry()
        screen_pixmap = screen.grabWindow(0)
        if screen_pixmap.isNull():
            worst_fraction = 0.0
            continue
        worst_fraction = min(worst_fraction, visible_pixmap_fraction(screen_pixmap))
        target_pos = geometry.topLeft() - virtual_geometry.topLeft()
        painter.drawPixmap(target_pos, screen_pixmap)
        painted = True
    painter.end()
    if not painted:
        return QPixmap(), 0.0
    return composed, worst_fraction


def _external_desktop_grab(virtual_geometry: QRect) -> tuple[QPixmap, str] | None:
    """
    Grabs the virtual desktop with an external screenshot tool.

    Args:
        virtual_geometry: Bounding rectangle across all screens.

    Returns:
        tuple[QPixmap, str] | None: Pixmap and backend key, or None when no
        external tool produced an image.
    """

    return grab_desktop_region(
        virtual_geometry.x(),
        virtual_geometry.y(),
        virtual_geometry.width(),
        virtual_geometry.height(),
        wayland=is_wayland_session(),
    )


def _desktop_grab_order() -> tuple[str, ...]:
    """
    Returns the grab sources to try, in order.

    Qt's grab is the fast path and comes first on X11. On Wayland it cannot work
    at all, and once it has returned a blank image in this session it is demoted
    so every following capture skips the wasted attempt.

    Returns:
        tuple[str, ...]: Sources, each ``qt`` or ``external``.
    """

    preference = capture_backend_preference()
    if preference == CAPTURE_BACKEND_QT:
        return (GRAB_BACKEND_QT,)
    if preference == CAPTURE_BACKEND_EXTERNAL:
        return (_GRAB_SOURCE_EXTERNAL,)
    if is_wayland_session() or _qt_grab_unreliable:
        return (_GRAB_SOURCE_EXTERNAL, GRAB_BACKEND_QT)
    return (GRAB_BACKEND_QT, _GRAB_SOURCE_EXTERNAL)


def capture_full_screen() -> DesktopSnapshot:
    """
    Captures the current virtual desktop across all monitors.

    Tries the configured grab sources in order and keeps the first image that
    carries visible content. A source can hand back a valid but completely black
    pixmap -- Qt's X11 grab does this on some compositors and virtual GPUs -- so
    every result is checked before it is accepted.

    Returns:
        DesktopSnapshot: Virtual desktop screenshot and geometry. ``blank`` is
        set when every source returned an empty image.
    """

    global _qt_grab_unreliable

    screens = QApplication.screens()
    if not screens:
        return DesktopSnapshot(pixmap=QPixmap(), virtual_geometry=QRect())

    virtual_geometry = QRect(screens[0].geometry())
    for screen in screens[1:]:
        virtual_geometry = virtual_geometry.united(screen.geometry())

    if virtual_geometry.width() <= 0 or virtual_geometry.height() <= 0:
        return DesktopSnapshot(pixmap=QPixmap(), virtual_geometry=QRect())

    best: tuple[QPixmap, str, float, float] | None = None
    verdict: bool | None = None
    for source in _desktop_grab_order():
        if source == GRAB_BACKEND_QT:
            pixmap, worst_screen = _compose_qt_desktop_grab(screens, virtual_geometry)
            backend = GRAB_BACKEND_QT
        else:
            external = _external_desktop_grab(virtual_geometry)
            if external is None:
                continue
            pixmap, backend = external
            worst_screen = 1.0
        if pixmap.isNull():
            continue
        # One conversion per candidate: both the content measurement and the
        # reference check work on this image.
        image = pixmap.toImage()
        if source == GRAB_BACKEND_QT:
            # Second opinion straight from the X server. Content heuristics cannot
            # tell a broken grab from a dark desktop, and they miss a grab that
            # returns a sliver of content and black everywhere else.
            verdict = verify_image_against_x11(
                image,
                virtual_geometry,
                [screen.geometry() for screen in screens],
            )
            if verdict is False:
                worst_screen = 0.0
        # Trust is decided by the emptiest screen, not by the composed average:
        # one black monitor out of two still leaves half a desktop of content.
        # A trustworthy grab always beats a suspicious one, even when the
        # suspicious one covers more pixels -- content that is missing on one
        # screen cannot be outvoted by content on another.
        overall = visible_image_fraction(image)
        trust = min(overall, worst_screen)
        trusted = not is_suspicious_fraction(trust)
        if best is None or (trusted, overall) > (
            not is_suspicious_fraction(best[3]),
            best[2],
        ):
            best = (pixmap, backend, overall, trust)
        if trusted:
            # Clearly a real desktop image: stop before paying for another source.
            break
        if backend == GRAB_BACKEND_QT:
            _qt_grab_unreliable = True

    if best is None:
        return DesktopSnapshot(pixmap=QPixmap(), virtual_geometry=QRect())

    pixmap, backend, fraction, trust = best
    blank = fraction <= 0.0
    if is_suspicious_fraction(trust) or verdict is False:
        # Either the screen really is (nearly) black, the X server contradicted a
        # grab, or every source failed the same way. The capture still goes
        # through -- a black desktop must stay capturable -- but it is recorded so
        # a repeat report is answerable.
        _log_degraded_capture(backend, fraction, blank, verdict)
    breadcrumb(f"capture grab backend={backend} visible={fraction * 100:.1f}%")
    return DesktopSnapshot(
        pixmap=pixmap,
        virtual_geometry=virtual_geometry,
        backend=backend,
        blank=blank,
    )


def _log_degraded_capture(
    backend: str,
    fraction: float,
    blank: bool,
    verdict: bool | None = None,
) -> None:
    """
    Records a capture that came back empty, nearly empty, or contradicted.

    Written to the crash log so an intermittent grab failure leaves evidence
    instead of only a user report.

    Args:
        backend: Grab source that produced the best image.
        fraction: Visible-content share of that image.
        blank: True when the image had no visible content at all.
        verdict: X11 reference check result for the Qt grab, if it ran.

    Returns:
        None
    """

    from src.crash_log import log_note

    state = "empty" if blank else "nearly empty"
    if verdict is False:
        reference = "contradicted by X server reference probe"
    elif verdict is True:
        reference = "matched X server reference probe"
    else:
        reference = "no reference probe available"
    log_note(
        "Degraded screen capture",
        f"Best grab source: {backend}\n"
        f"Visible content: {fraction * 100:.1f}% of samples\n"
        f"Result: {state}\n"
        f"Qt grab vs X server: {reference}\n"
        f"Session: {'wayland' if is_wayland_session() else 'x11'}\n"
        f"Backend preference: {capture_backend_preference()}\n"
        f"Qt grab already known blank: {_qt_grab_unreliable}\n"
        f"External tools available: {describe_grab_backends(wayland=is_wayland_session()) or 'none'}",
    )


def _warn_blank_capture_once() -> None:
    """
    Explains an all-black capture the first time it happens in a session.

    Returns:
        None
    """

    global _blank_capture_warning_shown

    if _blank_capture_warning_shown:
        return
    _blank_capture_warning_shown = True
    available = describe_grab_backends(wayland=is_wayland_session())
    if available:
        detail = (
            f"Fallback tools tried: {available}.\n"
            "If your desktop is not actually black, the display driver or "
            "compositor refused to hand out the screen contents."
        )
    else:
        detail = (
            "No fallback screenshot tool is installed. Install one so Snappix "
            "can bypass the failing Qt grab:\n"
            "    python3 install_dependencies.py\n"
            "(ffmpeg, maim, ImageMagick, or gnome-screenshot all work.)"
        )
    QMessageBox.warning(
        None,
        "Empty Screenshot",
        "The screen capture came back completely black.\n\n"
        f"{detail}\n\n"
        "You can also force a capture source under View > Settings > "
        "Screenshot source.",
    )


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
    if snapshot.blank:
        _warn_blank_capture_once()

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


def execute_text_recognition(
    on_recognized: Callable[[str], None],
    on_no_text: Callable[[], None],
    on_cancel: Callable[[], None],
) -> None:
    """
    Starts interactive region selection and copies its recognized text to clipboard.

    The captured region image itself is discarded once OCR has run over it;
    only the recognized text is handed back to the caller.

    Args:
        on_recognized: Callback with the recognized, non-empty text.
        on_no_text: Callback when the selected region contained no text.
        on_cancel: Callback when selection is cancelled.

    Returns:
        None
    """

    snapshot = capture_full_screen()
    if snapshot.pixmap.isNull() or snapshot.virtual_geometry.isNull():
        on_cancel()
        return
    if snapshot.blank:
        _warn_blank_capture_once()

    overlay = RegionCaptureOverlay(snapshot.pixmap, snapshot.virtual_geometry)
    _track_overlay(overlay)

    def on_region_captured(pixmap: QPixmap) -> None:
        _untrack_overlay(overlay)
        text = extract_text_from_png_bytes(pixmap_to_png_bytes(pixmap))
        if text:
            on_recognized(text)
        else:
            on_no_text()

    def on_region_cancelled() -> None:
        _untrack_overlay(overlay)
        on_cancel()

    overlay.capture_done.connect(on_region_captured)
    overlay.capture_cancelled.connect(on_region_cancelled)
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

        if request.mode == CaptureMode.CURRENT_SCREEN:
            crop = crop_snapshot_to_rect(snapshot, screen_rect_under_cursor())
            if crop.isNull():
                on_capture(screenshot)
            else:
                on_capture(crop)
            return

        if request.mode == CaptureMode.LAST_REGION:
            crop = crop_snapshot_to_rect(snapshot, last_capture_region())
            if not crop.isNull():
                on_capture(crop)
                return
            # Nothing stored yet (first run, or the region no longer fits the
            # desktop): fall through and let the user pick one.

        if request.mode in (CaptureMode.REGION, CaptureMode.LAST_REGION):
            overlay = RegionCaptureOverlay(screenshot, virtual_geometry)
            _track_overlay(overlay)
            overlay.region_selected.connect(remember_capture_region)
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

        from src.paths import is_windows, supports_window_capture

        if not supports_window_capture():
            QMessageBox.information(
                None,
                "Window Capture",
                "Window capture is not available on this operating system yet.\n"
                "Use Capture Area instead.",
            )
            on_cancel()
            return

        if is_windows():
            overlay = WindowCaptureOverlay(
                screenshot,
                virtual_geometry,
                accept_mouse_input=True,
            )
            _track_overlay(overlay)

            def on_windows_capture(pixmap: QPixmap) -> None:
                _untrack_overlay(overlay)
                on_capture(pixmap)

            def on_windows_cancel() -> None:
                _untrack_overlay(overlay)
                on_cancel()

            overlay.capture_done.connect(on_windows_capture)
            overlay.capture_cancelled.connect(on_windows_cancel)
            overlay.show()
            overlay.raise_()
            overlay.activateWindow()
            overlay.grabKeyboard()
            overlay.repaint()
            return

        if not has_xdotool_and_xwininfo():
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

        # The overlay is WindowTransparentForInput so xdotool can pick the
        # window underneath, which also stops any window of ours from receiving
        # key events -- the overlay's own Escape handling never fires here. A
        # passive global listener is what makes Escape work during selection.
        # Imported lazily: pynput chooses a backend at import time and fails on
        # a display-less session, which must not break importing this module.
        from src.global_hotkeys import EscapeListener

        escape_listener = EscapeListener()

        def finish_selection() -> None:
            escape_listener.stop()
            _untrack_overlay(overlay)
            overlay.close()

        def cancel_selection() -> None:
            if selection_state["cancelled"]:
                return
            selection_state["cancelled"] = True
            if process.poll() is None:
                process.terminate()
            finish_selection()
            on_cancel()

        overlay.capture_cancelled.connect(cancel_selection)
        escape_listener.escape_pressed.connect(cancel_selection)
        escape_listener.start()

        def check_selection_process() -> None:
            if selection_state["cancelled"]:
                return
            return_code = process.poll()
            if return_code is None:
                QTimer.singleShot(70, check_selection_process)
                return

            finish_selection()

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

            geometry = geometry_for_selected_window(
                selected_id,
                QCursor.pos(),
                exclude_hwnds=overlay._own_window_ids(),
            )
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
        if snapshot.blank:
            _warn_blank_capture_once()

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


def format_hotkey_for_display(spec: str) -> str:
    """
    Formats a normalized hotkey spec for tooltip display.

    Args:
        spec: Normalized hotkey text such as ``ctrl+shift+m``.

    Returns:
        Human-readable hotkey label such as ``Ctrl+Shift+M``.
    """

    normalized = str(spec or "").strip().lower()
    if not normalized:
        return ""
    labels = {
        "ctrl": "Ctrl",
        "control": "Ctrl",
        "shift": "Shift",
        "alt": "Alt",
        "super": "Super",
        "meta": "Super",
        "win": "Super",
        "cmd": "Super",
    }
    parts: list[str] = []
    for part in normalized.split("+"):
        token = part.strip()
        if not token:
            continue
        if token in labels:
            parts.append(labels[token])
        elif len(token) == 1:
            parts.append(token.upper())
        else:
            parts.append(token.upper() if token.startswith("f") and token[1:].isdigit() else token)
    return "+".join(parts)


def measure_box_button_tooltip(hotkey_spec: str = "") -> str:
    """
    Builds the MeasureBox Capture-button tooltip.

    Args:
        hotkey_spec: Optional start hotkey to include in the tip.

    Returns:
        Short usage tooltip including the current hotkey when set.
    """

    hotkey = format_hotkey_for_display(hotkey_spec)
    start_line = (
        f"Start: {hotkey} or click"
        if hotkey
        else "Start: click the button"
    )
    return (
        "Measure screen size (x/y/w/h).\n"
        f"{start_line} · drag to draw\n"
        "Left Shift: edit · Esc: exit\n"
        "Right-click: appearance settings"
    )


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


def _build_measure_box_icon() -> QIcon:
    """
    Renders a compact ruler/rectangle icon for the MeasureBox action.

    Returns:
        QIcon: Icon image.
    """

    icon = QPixmap(18, 18)
    icon.fill(Qt.GlobalColor.transparent)
    painter = QPainter(icon)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(46, 204, 113), 1.6)
    painter.setPen(pen)
    painter.setBrush(QColor(46, 204, 113, 40))
    painter.drawRect(3, 4, 12, 10)
    painter.drawLine(3, 4, 3, 2)
    painter.drawLine(9, 4, 9, 2)
    painter.drawLine(15, 4, 15, 2)
    painter.drawLine(3, 14, 1, 14)
    painter.drawLine(3, 9, 1, 9)
    painter.end()
    return QIcon(icon)


def _build_text_recognition_icon() -> QIcon:
    """
    Renders a compact "OCR" text icon for capture panel action.

    Returns:
        QIcon: Icon image.
    """

    icon = QPixmap(18, 18)
    icon.fill(Qt.GlobalColor.transparent)
    painter = QPainter(icon)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    font = QFont()
    font.setBold(True)
    font.setPointSize(7)
    painter.setFont(font)
    painter.setPen(QPen(QColor(46, 204, 113), 1))
    painter.drawText(QRect(0, 1, 18, 16), Qt.AlignmentFlag.AlignCenter, "OCR")
    painter.end()
    return QIcon(icon)

