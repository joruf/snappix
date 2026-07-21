"""
Global keyboard shortcut registration for SnapAgent.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, Signal

from src.config import AppConfig, normalize_hotkey_spec

try:
    from pynput import keyboard

    PYNPUT_AVAILABLE = True
except ModuleNotFoundError:
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
        bindings = [
            (config.hotkey_capture_region, "capture_region"),
            (config.hotkey_capture_window, "capture_window"),
            (config.hotkey_capture_fullscreen, "capture_fullscreen"),
        ]
        for spec, action in bindings:
            pynput_spec = hotkey_spec_to_pynput(spec)
            if pynput_spec is None:
                continue
            mapping[pynput_spec] = self._make_callback(action)

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
