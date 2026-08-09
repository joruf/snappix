"""
Global keyboard shortcut registration for Snappix.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, Signal

from src.config import AppConfig, normalize_hotkey_spec

try:
    from pynput import keyboard

    PYNPUT_AVAILABLE = True
except ImportError:
    # Not just ModuleNotFoundError: on a headless Linux session pynput picks a
    # backend at import time and raises a plain ImportError ("failed to acquire
    # X connection"). Catching only the narrower error made importing this
    # module -- and everything importing it -- explode on CI and on any
    # display-less run.
    keyboard = None
    PYNPUT_AVAILABLE = False

_MODIFIER_ALIASES = {
    "ctrl": "<ctrl>",
    "control": "<ctrl>",
    "shift": "<shift>",
    "alt": "<alt>",
    "super": "<super>",
    "meta": "<super>",
    "win": "<super>",
    "cmd": "<super>",
}


class HotkeyBridge(QObject):
    """
    Forwards global hotkey callbacks to the Qt main thread.

    Signals:
        triggered: Emits one hotkey action identifier.
    """

    triggered = Signal(str)


def hotkey_spec_to_pynput(spec: str) -> str | None:
    """
    Converts a user hotkey string into pynput GlobalHotKeys syntax.

    Args:
        spec: Normalized hotkey text.

    Returns:
        str | None: pynput hotkey string or None when invalid.
    """

    normalized = normalize_hotkey_spec(spec)
    if not normalized:
        return None

    converted: list[str] = []
    for part in normalized.split("+"):
        if part in _MODIFIER_ALIASES:
            converted.append(_MODIFIER_ALIASES[part])
            continue
        if len(part) == 1 and part.isalnum():
            converted.append(part)
            continue
        if part.startswith("f") and part[1:].isdigit():
            converted.append(f"<{part}>")
            continue
        return None
    if not converted:
        return None
    return "+".join(converted)


class GlobalHotkeyManager:
    """
    Registers and manages global keyboard shortcuts.
    """

    def __init__(self, bridge: HotkeyBridge) -> None:
        """
        Initializes the hotkey manager.

        Args:
            bridge: Qt signal bridge for main-thread delivery.
        """

        self._bridge = bridge
        self._listener = None
        self._last_error = ""

    @property
    def last_error(self) -> str:
        """
        Returns the last startup error message.

        Returns:
            str: Last error text, empty when none occurred.
        """

        return self._last_error

    @staticmethod
    def is_supported() -> bool:
        """
        Indicates whether global hotkey dependencies are available.

        Returns:
            bool: True when pynput can be used.
        """

        return PYNPUT_AVAILABLE

    def apply_config(self, config: AppConfig) -> bool:
        """
        Starts or restarts global hotkeys from application settings.

        Args:
            config: Current application configuration.

        Returns:
            bool: True when hotkeys were registered successfully.
        """

        self.stop()
        self._last_error = ""
        if not config.hotkeys_enabled:
            return True
        if not PYNPUT_AVAILABLE:
            self._last_error = "Global hotkeys require the pynput package."
            return False

        mapping: dict[str, Callable[[], None]] = {}
        from src.paths import supports_window_capture
        from src.video_recorder import has_ffmpeg

        bindings: list[tuple[str, str]] = [
            (config.hotkey_capture_region, "capture_region"),
            (config.hotkey_capture_fullscreen, "capture_fullscreen"),
            (config.hotkey_capture_screen, "capture_screen"),
            (config.hotkey_capture_last_region, "capture_last_region"),
            (config.hotkey_measure_box, "measure_box"),
        ]
        if supports_window_capture():
            bindings.append((config.hotkey_capture_window, "capture_window"))
        if has_ffmpeg():
            bindings.extend(
                [
                    (config.hotkey_capture_video, "capture_video"),
                    (config.hotkey_recording_pause_resume, "recording_pause_resume"),
                    (config.hotkey_recording_stop, "recording_stop"),
                ]
            )
        for spec, action in bindings:
            pynput_spec = hotkey_spec_to_pynput(spec)
            if pynput_spec is None:
                continue
            mapping[pynput_spec] = self._make_callback(action)

        # Escape always stops an active recording too, in addition to whatever
        # the user configured for "stop recording" above. This listener is
        # passive (does not suppress the key), so Escape still reaches
        # whatever application has focus as normal; the callback itself is a
        # no-op unless a recording is actually in progress.
        mapping.setdefault("<esc>", self._make_callback("recording_stop"))

        if not mapping:
            self._last_error = "No valid global hotkeys were configured."
            return False

        try:
            self._listener = keyboard.GlobalHotKeys(mapping)
            self._listener.start()
        except Exception as exc:
            self._listener = None
            self._last_error = f"Could not register global hotkeys: {exc}"
            return False
        return True

    def stop(self) -> None:
        """
        Stops the active global hotkey listener.

        Returns:
            None
        """

        if self._listener is None:
            return
        try:
            self._listener.stop()
        except Exception:
            pass
        self._listener = None

    def _make_callback(self, action: str) -> Callable[[], None]:
        """
        Creates one listener callback for a hotkey action.

        Args:
            action: Hotkey action identifier.

        Returns:
            Callable[[], None]: Listener callback.
        """

        def callback() -> None:
            self._bridge.triggered.emit(action)

        return callback


class EscapeListener(QObject):
    """
    Listens for Escape globally while a capture overlay cannot hold focus.

    The Linux window-capture overlay is ``WindowTransparentForInput`` so
    ``xdotool`` can pick the window underneath. That also means no window of
    the app can receive key events, which kills widget-level Escape handling,
    keyboard grabs, and application shortcuts alike. A passive global listener
    is the only thing that still sees the key in that state.

    Signals:
        escape_pressed: Emitted on the Qt main thread when Escape is pressed.
    """

    escape_pressed = Signal()

    def __init__(self) -> None:
        """
        Initializes the listener without starting it.
        """

        super().__init__()
        self._listener = None

    @staticmethod
    def is_supported() -> bool:
        """
        Indicates whether a global Escape listener can run.

        Returns:
            bool: True when pynput is importable.
        """

        return PYNPUT_AVAILABLE

    def start(self) -> bool:
        """
        Starts listening for Escape.

        Returns:
            bool: True when the listener started, False when unsupported or the
            platform refused the input hook.
        """

        if self._listener is not None:
            return True
        if not PYNPUT_AVAILABLE or keyboard is None:
            return False

        def on_press(key) -> None:
            # Runs on pynput's thread; the signal hops to the Qt main thread.
            if key == keyboard.Key.esc:
                self.escape_pressed.emit()

        try:
            # Passive: Escape is never suppressed, other apps still receive it.
            listener = keyboard.Listener(on_press=on_press)
            listener.start()
        except Exception:
            self._listener = None
            return False
        self._listener = listener
        return True

    def stop(self) -> None:
        """
        Stops the listener if it is running.

        Returns:
            None
        """

        if self._listener is None:
            return
        try:
            self._listener.stop()
        except Exception:
            pass
        self._listener = None
