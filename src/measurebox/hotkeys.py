"""Global hotkey and mouse listeners bridged to the Qt main thread."""

from __future__ import annotations

import threading
from time import monotonic
from typing import Callable

try:
    from pynput import keyboard, mouse

    PYNPUT_AVAILABLE = True
except ImportError:
    # Not just ModuleNotFoundError: on a display-less session pynput selects a
    # backend at import time and raises a plain ImportError ("failed to acquire
    # X connection"). Importing this module must stay safe there, or every
    # module reaching MeasureBox fails to import -- including under CI.
    keyboard = None
    mouse = None
    PYNPUT_AVAILABLE = False

from PySide6.QtCore import QObject, Signal


class GlobalHotkeyBridge(QObject):
    """Bridge callbacks from pynput thread to Qt main thread."""

    draw_mode_requested = Signal()
    passthrough_mode_requested = Signal()
    clear_requested = Signal()
    ctrl_click_requested = Signal(int, int)
    ctrl_state_changed = Signal(bool)
    color_pick_requested = Signal(int, int)
    ctrl_hover_requested = Signal(int, int)


class GlobalHotkeyListener:
    """Listen for global hotkey events using pynput."""

    def __init__(self, hotkey: str, on_toggle: Callable[[], None]) -> None:
        """Store hotkey binding and callback.

        :param hotkey: Pynput hotkey pattern.
        :param on_toggle: Callback fired for hotkey activation.
        """
        self.hotkey = hotkey
        self.on_toggle = on_toggle
        self.listener: keyboard.GlobalHotKeys | None = None

    def start(self) -> None:
        """Start global hotkey listener in background thread.

        Does nothing when pynput is unavailable (no display / not installed).

        :return: None.
        """
        if not PYNPUT_AVAILABLE:
            return
        self.listener = keyboard.GlobalHotKeys({self.hotkey: self.on_toggle})
        self.listener.start()

    def stop(self) -> None:
        """Stop global hotkey listener.

        :return: None.
        """
        if self.listener is not None:
            self.listener.stop()
            self.listener = None


class GlobalCtrlClickListener:
    """Listen for global Left-Shift+LeftClick to enter edit mode."""

    def __init__(
        self,
        on_ctrl_click: Callable[[int, int], None],
        on_ctrl_state_changed: Callable[[bool], None],
        on_click: Callable[[int, int], None],
        on_ctrl_hover: Callable[[int, int], None],
    ) -> None:
        """Store callback and initialize input listeners.

        :param on_ctrl_click: Callback receiving global click coordinates.
        :param on_ctrl_state_changed: Callback for Left-Shift pressed/released state.
        :param on_click: Callback receiving Left-Shift+left double-click coordinates.
        :param on_ctrl_hover: Callback receiving global pointer coordinates while Left-Shift is held.
        """
        self.on_ctrl_click = on_ctrl_click
        self.on_ctrl_state_changed = on_ctrl_state_changed
        self.on_click = on_click
        self.on_ctrl_hover = on_ctrl_hover
        self._ctrl_down = False
        self._lock = threading.Lock()
        self._double_click_interval_seconds = 0.35
        self._double_click_max_distance_px = 6
        self._last_left_click_time = 0.0
        self._last_left_click_pos: tuple[int, int] | None = None
        self._last_hover_emit_time = 0.0
        self._hover_emit_interval_seconds = 0.05
        self.keyboard_listener: keyboard.Listener | None = None
        self.mouse_listener: mouse.Listener | None = None

    def start(self) -> None:
        """Start global keyboard and mouse listeners.

        Does nothing when pynput is unavailable (no display / not installed).

        :return: None.
        """
        if not PYNPUT_AVAILABLE:
            return
        self.keyboard_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )
        self.mouse_listener = mouse.Listener(on_click=self._on_click, on_move=self._on_move)
        self.keyboard_listener.start()
        self.mouse_listener.start()

    def stop(self) -> None:
        """Stop global keyboard and mouse listeners.

        :return: None.
        """
        if self.keyboard_listener is not None:
            self.keyboard_listener.stop()
            self.keyboard_listener = None
        if self.mouse_listener is not None:
            self.mouse_listener.stop()
            self.mouse_listener = None

    def _on_key_press(self, key) -> None:
        """Track Left-Shift key down state.

        :param key: Pressed key event.
        :return: None.
        """
        if key == keyboard.Key.shift_l:
            emit_change = False
            with self._lock:
                if not self._ctrl_down:
                    self._ctrl_down = True
                    emit_change = True
            if emit_change:
                self.on_ctrl_state_changed(True)

    def _on_key_release(self, key) -> None:
        """Track Left-Shift key release state.

        :param key: Released key event.
        :return: None.
        """
        if key == keyboard.Key.shift_l:
            emit_change = False
            with self._lock:
                if self._ctrl_down:
                    self._ctrl_down = False
                    emit_change = True
            if emit_change:
                self.on_ctrl_state_changed(False)

    def _on_click(self, x: float, y: float, button, pressed: bool) -> None:
        """Emit callbacks for Left-Shift click and Left-Shift+left double click.

        :param x: Global X coordinate.
        :param y: Global Y coordinate.
        :param button: Mouse button.
        :param pressed: True on press, False on release.
        :return: None.
        """
        if not pressed or button != mouse.Button.left:
            return
        current_x = int(x)
        current_y = int(y)
        now = monotonic()
        previous_pos = self._last_left_click_pos
        elapsed = now - self._last_left_click_time
        self._last_left_click_time = now
        self._last_left_click_pos = (current_x, current_y)

        with self._lock:
            ctrl_down = self._ctrl_down

        if ctrl_down and previous_pos is not None:
            distance_x = abs(current_x - previous_pos[0])
            distance_y = abs(current_y - previous_pos[1])
            if (
                elapsed <= self._double_click_interval_seconds
                and distance_x <= self._double_click_max_distance_px
                and distance_y <= self._double_click_max_distance_px
            ):
                self.on_click(current_x, current_y)

        if ctrl_down:
            self.on_ctrl_click(current_x, current_y)

    def _on_move(self, x: float, y: float) -> None:
        """Emit hover callbacks while Left-Shift is held for pre-locking rectangle interaction.

        :param x: Global X coordinate.
        :param y: Global Y coordinate.
        :return: None.
        """
        with self._lock:
            ctrl_down = self._ctrl_down
        if not ctrl_down:
            return

        now = monotonic()
        if now - self._last_hover_emit_time < self._hover_emit_interval_seconds:
            return
        self._last_hover_emit_time = now
        self.on_ctrl_hover(int(x), int(y))
