"""
Cross-platform user data path helpers for Snappix.
"""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

#: ``True`` inside the single-file executable that ``build-exe.py`` produces.
IS_FROZEN = bool(getattr(sys, "frozen", False))


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


def runtime_parent(project_dir: Path) -> Path:
    """
    Returns the directory that holds Snappix's private ``.snappix-runtime`` tools.

    A checkout keeps them next to ``run.py``. The single-file executable unpacks
    itself into a temporary directory that is deleted on exit, so its ffmpeg and
    Tesseract live in the per-user data directory instead.

    Args:
        project_dir: Snappix project root.

    Returns:
        Path: ``project_dir``, or :func:`user_data_dir` in the executable.
    """

    if IS_FROZEN:
        return user_data_dir()
    return Path(project_dir)


def executable() -> Path:
    """
    Returns the single-file executable this process was started from.

    Only meaningful when :data:`IS_FROZEN` is set; otherwise it is the Python
    interpreter.

    Returns:
        Path: The running program file.
    """

    return Path(sys.executable).resolve()


def executable_name(version: str = "", build: int = 0) -> str:
    """
    Returns the file name of the executable for this platform and version.

    ``build-exe.py`` writes the executable under this name and the updater looks
    for a release asset with it, so both always agree. The version is part of it
    so a downloaded file says which one it is.

    Args:
        version: ``major.minor.patch``; defaults to this program's.
        build: The build number; defaults to this program's.

    Returns:
        str: For example ``snappix-linux-x86_64-0.39.0-build129`` or
        ``snappix-windows-x86_64-0.39.0-build129.exe``.
    """

    if not version:
        from src.version import version as running_version

        version, build_text = running_version()
        build = int(build_text) if build_text.isdigit() else 0
    machine = platform.machine().lower()
    machine = {"amd64": "x86_64", "x64": "x86_64", "arm64": "aarch64"}.get(machine, machine)
    family = os_family()
    system = {"darwin": "macos"}.get(family, family)
    suffix = ".exe" if family == "windows" else ""
    return f"snappix-{system}-{machine}-{version}-build{build}{suffix}"


def child_environment(env: "dict | None" = None) -> dict:
    """
    Returns the environment a child process should get.

    The executable runs with ``LD_LIBRARY_PATH`` - and, through PyInstaller's Qt
    hooks, ``QT_PLUGIN_PATH`` and friends - pointing into its unpacked files.
    Inherited, they make ffmpeg, xdotool, Tesseract or the file manager load the
    program's libraries instead of their own, which ends anywhere between odd
    warnings and crashes. Every entry that points into the unpacked files is
    removed; ``LD_LIBRARY_PATH`` gets the value it had before the program
    started.

    Args:
        env: The environment to clean; defaults to this process's.

    Returns:
        dict: A new dict; a plain copy outside the executable.
    """

    source = os.environ if env is None else env
    bundle = getattr(sys, "_MEIPASS", "")
    if not IS_FROZEN or not bundle:
        return dict(source)
    clean = {}
    for key, value in source.items():
        if key.startswith("_PYI_") or key == "LD_LIBRARY_PATH_ORIG":
            continue
        if bundle in value:
            kept = [part for part in value.split(os.pathsep) if part and bundle not in part]
            if not kept:
                continue
            value = os.pathsep.join(kept)
        clean[key] = value
    original = source.get("LD_LIBRARY_PATH_ORIG")
    if original:
        clean["LD_LIBRARY_PATH"] = original
    return clean


def use_system_environment_for_children() -> None:
    """
    Starts every child process with :func:`child_environment`.

    One place instead of every ``subprocess`` call: the program starts many
    tools, and a single forgotten ``env=`` would bring the problem back. Does
    nothing outside the executable.

    Returns:
        None
    """

    import subprocess

    if not IS_FROZEN or getattr(subprocess.Popen, "_snappix_clean_env", False):
        return

    class _SystemPopen(subprocess.Popen):  # type: ignore[misc, valid-type]
        """``Popen`` that never hands the bundled libraries to a child."""

        _snappix_clean_env = True

        def __init__(self, *args, **kwargs) -> None:
            kwargs["env"] = child_environment(kwargs.get("env"))
            super().__init__(*args, **kwargs)

    subprocess.Popen = _SystemPopen  # type: ignore[misc]


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
