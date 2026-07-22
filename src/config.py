"""
Application configuration model and persistence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.theme import DEFAULT_THEME, normalize_theme_name

POST_CAPTURE_EDITOR = "editor"
POST_CAPTURE_CLIPBOARD = "clipboard"
POST_CAPTURE_SAVE = "save"
DEFAULT_POST_CAPTURE_ACTION = POST_CAPTURE_EDITOR
VALID_POST_CAPTURE_ACTIONS = frozenset(
    {
        POST_CAPTURE_EDITOR,
        POST_CAPTURE_CLIPBOARD,
        POST_CAPTURE_SAVE,
    }
)
POST_CAPTURE_ACTIONS = {
    POST_CAPTURE_EDITOR: "Open in editor",
    POST_CAPTURE_CLIPBOARD: "Copy to clipboard",
    POST_CAPTURE_SAVE: "Save to folder",
}

EDITOR_LAST_TAB_KEEP_OPEN = "keep_open"
EDITOR_LAST_TAB_CLOSE_WINDOW = "close_window"
DEFAULT_EDITOR_LAST_TAB_BEHAVIOR = EDITOR_LAST_TAB_KEEP_OPEN
VALID_EDITOR_LAST_TAB_BEHAVIORS = frozenset(
    {
        EDITOR_LAST_TAB_KEEP_OPEN,
        EDITOR_LAST_TAB_CLOSE_WINDOW,
    }
)
EDITOR_LAST_TAB_BEHAVIORS = {
    EDITOR_LAST_TAB_KEEP_OPEN: "Keep editor window open",
    EDITOR_LAST_TAB_CLOSE_WINDOW: "Close editor window",
}

DEFAULT_HOTKEY_CAPTURE_REGION = "ctrl+shift+a"
DEFAULT_HOTKEY_CAPTURE_WINDOW = "ctrl+shift+w"
DEFAULT_HOTKEY_CAPTURE_FULLSCREEN = "ctrl+shift+f"


def normalize_hotkey_spec(spec: str) -> str:
    """
    Normalizes one hotkey specification string.

    Args:
        spec: Hotkey text such as ``Ctrl+Shift+A``.

    Returns:
        str: Lowercase normalized hotkey text.
    """

    parts = [part.strip().lower() for part in spec.split("+") if part.strip()]
    return "+".join(parts)


def normalize_post_capture_action(action: str) -> str:
    """
    Returns a supported post-capture action identifier.

    Args:
        action: Requested action identifier.

    Returns:
        str: Valid post-capture action.
    """

    if action in VALID_POST_CAPTURE_ACTIONS:
        return action
    return DEFAULT_POST_CAPTURE_ACTION


def normalize_editor_last_tab_behavior(behavior: str) -> str:
    """
    Returns a supported editor behavior for closing the last tab.

    Args:
        behavior: Requested last-tab behavior identifier.

    Returns:
        str: Valid last-tab behavior.
    """

    if behavior in VALID_EDITOR_LAST_TAB_BEHAVIORS:
        return behavior
    return DEFAULT_EDITOR_LAST_TAB_BEHAVIOR


@dataclass(slots=True)
class AppConfig:
    """
    Defines persisted Snappix user settings.

    Attributes:
        autostart_enabled: Whether app launches at desktop login.
        theme: Active UI theme identifier (light or dark).
        hotkeys_enabled: Whether global capture hotkeys are active.
        hotkey_capture_region: Hotkey for region capture.
        hotkey_capture_window: Hotkey for window capture.
        hotkey_capture_fullscreen: Hotkey for fullscreen capture.
        post_capture_action: Action after a successful capture.
        capture_save_directory: Optional folder for automatic capture saves.
        editor_last_tab_behavior: Behavior when the last editor tab is closed.
    """

    autostart_enabled: bool = False
    theme: str = DEFAULT_THEME
    hotkeys_enabled: bool = True
    hotkey_capture_region: str = DEFAULT_HOTKEY_CAPTURE_REGION
    hotkey_capture_window: str = DEFAULT_HOTKEY_CAPTURE_WINDOW
    hotkey_capture_fullscreen: str = DEFAULT_HOTKEY_CAPTURE_FULLSCREEN
    post_capture_action: str = DEFAULT_POST_CAPTURE_ACTION
    capture_save_directory: str = ""
    editor_last_tab_behavior: str = DEFAULT_EDITOR_LAST_TAB_BEHAVIOR


class ConfigManager:
    """
    Reads and writes Snappix configuration.
    """

    def __init__(self, config_path: Path) -> None:
        """
        Initializes the manager with target path.

        Args:
            config_path: JSON configuration file path.
        """

        self.config_path = config_path

    def load(self) -> AppConfig:
        """
        Loads configuration from disk or returns defaults.

        Returns:
            AppConfig: Loaded or fallback configuration.
        """

        if not self.config_path.exists():
            return AppConfig()
        try:
            payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return AppConfig()
        return AppConfig(
            autostart_enabled=bool(payload.get("autostart_enabled", False)),
            theme=normalize_theme_name(str(payload.get("theme", DEFAULT_THEME))),
            hotkeys_enabled=bool(payload.get("hotkeys_enabled", True)),
            hotkey_capture_region=normalize_hotkey_spec(
                str(payload.get("hotkey_capture_region", DEFAULT_HOTKEY_CAPTURE_REGION))
            ),
            hotkey_capture_window=normalize_hotkey_spec(
                str(payload.get("hotkey_capture_window", DEFAULT_HOTKEY_CAPTURE_WINDOW))
            ),
            hotkey_capture_fullscreen=normalize_hotkey_spec(
                str(
                    payload.get(
                        "hotkey_capture_fullscreen",
                        DEFAULT_HOTKEY_CAPTURE_FULLSCREEN,
                    )
                )
            ),
            post_capture_action=normalize_post_capture_action(
                str(payload.get("post_capture_action", DEFAULT_POST_CAPTURE_ACTION))
            ),
            capture_save_directory=str(payload.get("capture_save_directory", "")).strip(),
            editor_last_tab_behavior=normalize_editor_last_tab_behavior(
                str(
                    payload.get(
                        "editor_last_tab_behavior",
                        DEFAULT_EDITOR_LAST_TAB_BEHAVIOR,
                    )
                )
            ),
        )

    def save(self, config: AppConfig) -> None:
        """
        Persists configuration as JSON.

        Args:
            config: Configuration model to store.

        Returns:
            None
        """

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "autostart_enabled": config.autostart_enabled,
            "theme": normalize_theme_name(config.theme),
            "hotkeys_enabled": config.hotkeys_enabled,
            "hotkey_capture_region": normalize_hotkey_spec(config.hotkey_capture_region),
            "hotkey_capture_window": normalize_hotkey_spec(config.hotkey_capture_window),
            "hotkey_capture_fullscreen": normalize_hotkey_spec(
                config.hotkey_capture_fullscreen
            ),
            "post_capture_action": normalize_post_capture_action(config.post_capture_action),
            "capture_save_directory": config.capture_save_directory.strip(),
            "editor_last_tab_behavior": normalize_editor_last_tab_behavior(
                config.editor_last_tab_behavior
            ),
        }
        self.config_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
