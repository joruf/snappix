"""
Cross-platform user data path helpers for Snappix.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def os_family() -> str:
    """
    Returns the current OS family identifier.

    Returns:
        str: ``linux``, ``windows``, ``darwin``, or the raw ``sys.platform`` value.
    """

    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "darwin"
    return sys.platform


def is_windows() -> bool:
    """
    Returns whether the current process runs on Windows.

    Returns:
        bool: True on Windows.
    """

    return os_family() == "windows"


def is_linux() -> bool:
    """
    Returns whether the current process runs on Linux.

    Returns:
        bool: True on Linux.
    """

    return os_family() == "linux"


def user_config_dir() -> Path:
    """
    Returns the Snappix configuration directory.

    Returns:
        Path: ``%APPDATA%\\snappix`` on Windows, ``~/.config/snappix`` elsewhere.
    """

    if is_windows():
        base = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        return Path(base) / "snappix"
    return Path.home() / ".config" / "snappix"


def user_data_dir() -> Path:
    """
    Returns the Snappix local data directory (workspace default parent).

    Returns:
        Path: ``%LOCALAPPDATA%\\snappix`` on Windows, ``~/.snappix`` elsewhere.
    """

    if is_windows():
        base = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        return Path(base) / "snappix"
    return Path.home() / ".snappix"


def user_cache_dir() -> Path:
    """
    Returns the Snappix cache directory (single-instance lock, etc.).

    Returns:
        Path: Cache directory path.
    """

    if is_windows():
        return user_data_dir() / "cache"
    return Path.home() / ".cache" / "snappix"


def default_autostart_path() -> Path:
    """
    Returns the default autostart entry path for the current platform.

    Returns:
        Path: Startup ``.bat`` on Windows, XDG ``.desktop`` on Linux.
    """

    if is_windows():
        startup = (
            Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
            / "Startup"
        )
        return startup / "Snappix.bat"
    return Path.home() / ".config" / "autostart" / "snappix.desktop"


def venv_python_path(project_root: Path) -> Path:
    """
    Resolves the project virtualenv Python executable for the current OS.

    Args:
        project_root: Snappix project root.

    Returns:
        Path: Preferred interpreter path (may not exist yet).
    """

    if is_windows():
        scripts = project_root / ".venv" / "Scripts"
        for name in ("python.exe", "pythonw.exe"):
            candidate = scripts / name
            if candidate.exists():
                return candidate
        return scripts / "python.exe"
    python3_path = project_root / ".venv" / "bin" / "python3"
    if python3_path.exists():
        return python3_path
    return project_root / ".venv" / "bin" / "python"


def supports_window_capture() -> bool:
    """
    Returns whether native window pick capture is available on this OS.

    Returns:
        bool: True on Linux (X11 tools) and Windows (Win32); False on macOS.
    """

    return is_linux() or is_windows()


def supports_scroll_capture() -> bool:
    """
    Returns whether automatic scroll capture is available on this OS.

    Returns:
        bool: True on Linux (X11 tools) and Windows (Win32); False on macOS.
    """

    return is_linux() or is_windows()


def supports_native_video_capture() -> bool:
    """
    Returns whether region screen recording is supported on this OS.

    Returns:
        bool: True on Linux (x11grab) and Windows (gdigrab).
    """

    return os_family() in {"linux", "windows"}
