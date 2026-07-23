"""
Application configuration model and persistence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.theme import DEFAULT_THEME, normalize_theme_name
from src.shortcuts import normalize_editor_shortcuts

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

EXPORT_PRESET_WEB = "web"
EXPORT_PRESET_DOCS = "docs"
EXPORT_PRESET_PRINT = "print"
EXPORT_PRESET_LIGHTWEIGHT = "lightweight"
DEFAULT_EXPORT_PRESET = EXPORT_PRESET_DOCS
VALID_EXPORT_PRESETS = frozenset(
    {
        EXPORT_PRESET_WEB,
        EXPORT_PRESET_DOCS,
        EXPORT_PRESET_PRINT,
        EXPORT_PRESET_LIGHTWEIGHT,
    }
)

DEFAULT_BATCH_EXPORT_PROFILES: list[dict[str, Any]] = [
    {
        "key": "web_fast",
        "label": "Web Fast",
        "formats": ["png", "jpg"],
        "jpg_quality": 82,
        "pdf_dpi": 150,
    },
    {
        "key": "docs_hq",
        "label": "Docs HQ",
        "formats": ["png", "jpg", "pdf"],
        "jpg_quality": 90,
        "pdf_dpi": 300,
    },
    {
        "key": "print_master",
        "label": "Print Master",
        "formats": ["png", "jpg", "pdf"],
        "jpg_quality": 96,
        "pdf_dpi": 600,
    },
]
DEFAULT_BATCH_EXPORT_PROFILE_KEY = "docs_hq"
DEFAULT_EXPORT_SCALE = 1.0
VALID_EXPORT_SCALES = frozenset({1.0, 2.0, 3.0})
DEFAULT_EXPORT_KEEP_TRANSPARENCY = True

DEFAULT_HOTKEY_CAPTURE_REGION = "ctrl+shift+a"
DEFAULT_HOTKEY_CAPTURE_WINDOW = "ctrl+shift+w"
DEFAULT_HOTKEY_CAPTURE_FULLSCREEN = "ctrl+shift+f"


def default_capture_save_directory() -> str:
    """
    Returns the default capture save folder path.

    Returns:
        str: Absolute path under the user Downloads directory.
    """

    return str(Path.home() / "Downloads" / "snappix")


def sanitize_editor_shortcut_map(
    overrides: dict[str, str] | list[Any] | None,
) -> dict[str, str]:
    """
    Sanitizes a raw editor shortcut override map from configuration.

    Args:
        overrides: Raw mapping of action id to shortcut text.

    Returns:
        dict[str, str]: Trimmed string map. Unknown ids are kept here and
        filtered when shortcuts are applied.
    """

    if not isinstance(overrides, dict):
        return {}
    sanitized: dict[str, str] = {}
    for raw_key, raw_value in overrides.items():
        action_id = str(raw_key).strip()
        if not action_id:
            continue
        sanitized[action_id] = str(raw_value).strip()
    return sanitized


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


def normalize_export_preset(preset: str) -> str:
    """
    Returns a supported export preset identifier.

    Args:
        preset: Requested export preset identifier.

    Returns:
        str: Valid export preset.
    """

    normalized = preset.strip().lower()
    if normalized in VALID_EXPORT_PRESETS:
        return normalized
    return DEFAULT_EXPORT_PRESET


def normalize_export_scale(scale: float | int | str) -> float:
    """
    Returns a supported export scale factor.

    Args:
        scale: Requested scale (@1x/@2x/@3x).

    Returns:
        float: Valid scale factor.
    """

    try:
        resolved = float(scale)
    except (TypeError, ValueError):
        return DEFAULT_EXPORT_SCALE
    if abs(resolved - 3.0) < 0.001:
        return 3.0
    if abs(resolved - 2.0) < 0.001:
        return 2.0
    return 1.0


def normalize_batch_export_profiles(
    profiles: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> list[dict[str, Any]]:
    """
    Normalizes batch export profile definitions.

    Args:
        profiles: Raw profile objects from configuration.

    Returns:
        list[dict[str, Any]]: Sanitized profile list.
    """

    normalized: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for index, profile in enumerate(list(profiles or [])):
        if not isinstance(profile, dict):
            continue
        raw_key = str(profile.get("key", "")).strip().lower()
        key = "".join(
            character if character.isalnum() or character == "_" else "_"
            for character in raw_key
        ).strip("_")
        if not key:
            key = f"profile_{index + 1}"
        if key in seen_keys:
            continue
        label = str(profile.get("label", "")).strip() or key.replace("_", " ").title()
        formats = [
            str(value).strip().lower()
            for value in list(profile.get("formats", []))
            if str(value).strip().lower() in {"png", "jpg", "pdf"}
        ]
        if not formats:
            formats = ["png"]
        jpg_quality = max(1, min(100, int(profile.get("jpg_quality", 90))))
        pdf_dpi = max(72, min(1200, int(profile.get("pdf_dpi", 300))))
        normalized.append(
            {
                "key": key,
                "label": label,
                "formats": formats,
                "jpg_quality": jpg_quality,
                "pdf_dpi": pdf_dpi,
            }
        )
        seen_keys.add(key)

    if normalized:
        return normalized
    return [dict(profile) for profile in DEFAULT_BATCH_EXPORT_PROFILES]


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
        export_preset: Preferred export quality preset.
        export_scale: Preferred export scale factor (1.0, 2.0, or 3.0).
        export_keep_transparency: Whether PNG exports preserve alpha by default.
        batch_export_profiles: Saved named batch export profiles.
        batch_export_profile_key: Active batch export profile key.
        batch_export_last_directory: Last used batch export output directory.
        auto_crop_on_shrink: Whether unused canvas margins are cropped automatically.
        editor_shortcuts: Optional overrides for editor keyboard shortcuts.
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
    export_preset: str = DEFAULT_EXPORT_PRESET
    export_scale: float = DEFAULT_EXPORT_SCALE
    export_keep_transparency: bool = DEFAULT_EXPORT_KEEP_TRANSPARENCY
    batch_export_profiles: list[dict[str, Any]] = None
    batch_export_profile_key: str = DEFAULT_BATCH_EXPORT_PROFILE_KEY
    batch_export_last_directory: str = ""
    auto_crop_on_shrink: bool = True
    editor_shortcuts: dict[str, str] = None

    def __post_init__(self) -> None:
        """
        Initializes mutable defaults after dataclass construction.

        Returns:
            None
        """

        if self.batch_export_profiles is None:
            self.batch_export_profiles = [
                dict(profile) for profile in DEFAULT_BATCH_EXPORT_PROFILES
            ]
        if self.editor_shortcuts is None:
            self.editor_shortcuts = {}
        else:
            self.editor_shortcuts = normalize_editor_shortcuts(
                sanitize_editor_shortcut_map(self.editor_shortcuts)
            )
        profile_keys = {
            str(profile.get("key", "")).strip().lower()
            for profile in self.batch_export_profiles
            if isinstance(profile, dict)
        }
        normalized_key = str(self.batch_export_profile_key).strip().lower()
        if normalized_key not in profile_keys:
            self.batch_export_profile_key = next(iter(profile_keys), DEFAULT_BATCH_EXPORT_PROFILE_KEY)


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
            export_preset=normalize_export_preset(
                str(payload.get("export_preset", DEFAULT_EXPORT_PRESET))
            ),
            export_scale=normalize_export_scale(
                payload.get("export_scale", DEFAULT_EXPORT_SCALE)
            ),
            export_keep_transparency=bool(
                payload.get("export_keep_transparency", DEFAULT_EXPORT_KEEP_TRANSPARENCY)
            ),
            batch_export_profiles=normalize_batch_export_profiles(
                payload.get("batch_export_profiles")
                if isinstance(payload.get("batch_export_profiles"), list)
                else None
            ),
            batch_export_profile_key=str(
                payload.get("batch_export_profile_key", DEFAULT_BATCH_EXPORT_PROFILE_KEY)
            ).strip().lower(),
            batch_export_last_directory=str(
                payload.get("batch_export_last_directory", "")
            ).strip(),
            auto_crop_on_shrink=bool(payload.get("auto_crop_on_shrink", True)),
            editor_shortcuts=normalize_editor_shortcuts(
                sanitize_editor_shortcut_map(
                    payload.get("editor_shortcuts")
                    if isinstance(payload.get("editor_shortcuts"), dict)
                    else None
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
            "export_preset": normalize_export_preset(config.export_preset),
            "export_scale": normalize_export_scale(config.export_scale),
            "export_keep_transparency": bool(config.export_keep_transparency),
            "batch_export_profiles": normalize_batch_export_profiles(
                config.batch_export_profiles
            ),
            "batch_export_profile_key": str(config.batch_export_profile_key).strip().lower(),
            "batch_export_last_directory": config.batch_export_last_directory.strip(),
            "auto_crop_on_shrink": bool(config.auto_crop_on_shrink),
            "editor_shortcuts": normalize_editor_shortcuts(
                sanitize_editor_shortcut_map(config.editor_shortcuts)
            ),
        }
        self.config_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
