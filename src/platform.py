"""
Platform and session detection helpers.
"""

from __future__ import annotations

import os
import subprocess
from shutil import which


def is_wayland_session() -> bool:
    """
    Detects whether the current desktop session uses Wayland.

    Returns:
        bool: True when running on Wayland.
    """

    session_type = os.environ.get("XDG_SESSION_TYPE", "").strip().lower()
    if session_type == "wayland":
        return True
    return os.environ.get("WAYLAND_DISPLAY", "").strip() != ""


def has_grim() -> bool:
    """
    Checks whether the grim screenshot tool is available.

    Returns:
        bool: True when grim exists.
    """

    return which("grim") is not None


def has_grim_and_slurp() -> bool:
    """
    Checks whether grim and slurp are available for Wayland region capture.

    Returns:
        bool: True when both tools exist.
    """

    return which("grim") is not None and which("slurp") is not None


def capture_desktop_png_bytes(geometry: str | None = None) -> bytes | None:
    """
    Captures the desktop or one region using grim.

    Args:
        geometry: Optional grim geometry such as ``640x480+10+20``.

    Returns:
        bytes | None: PNG bytes or None when capture fails.
    """

    if not has_grim():
        return None
    command = ["grim", "-"]
    if geometry:
        command = ["grim", "-g", geometry, "-"]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            check=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if not result.stdout:
        return None
    return bytes(result.stdout)


def capture_region_with_grim_slurp() -> tuple[bytes, int, int] | None:
    """
    Captures one screen region using grim and slurp on Wayland.

    Returns:
        tuple[bytes, int, int] | None: PNG bytes with width and height, or None.
    """

    if not has_grim_and_slurp():
        return None
    try:
        selection = subprocess.run(
            ["slurp"],
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        ).stdout.strip()
        if not selection:
            return None
        image_bytes = subprocess.run(
            ["grim", "-g", selection, "-"],
            capture_output=True,
            check=True,
            timeout=30,
        ).stdout
        if not image_bytes:
            return None
        width, height = _parse_grim_selection_size(selection)
        return (image_bytes, width, height)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _parse_grim_selection_size(selection: str) -> tuple[int, int]:
    """
    Parses width and height from grim/slurp selection output.

    Args:
        selection: Slurp stdout such as ``640x480+10+20`` or ``0,0 640x480+10+20``.

    Returns:
        tuple[int, int]: Parsed width and height, or ``(0, 0)`` when unknown.
    """

    parts = [part for part in selection.split() if part]
    if not parts:
        return (0, 0)
    geometry = parts[-1] if len(parts) >= 2 else parts[0]
    size_token = geometry.split("+", maxsplit=1)[0]
    if "x" not in size_token:
        return (0, 0)
    width_text, height_text = size_token.split("x", maxsplit=1)
    try:
        return (int(width_text), int(height_text))
    except ValueError:
        return (0, 0)


def has_tesseract() -> bool:
    """
    Checks whether the tesseract OCR binary is available.

    Returns:
        bool: True when tesseract exists.
    """

    return which("tesseract") is not None


def _resolve_x11_display_ptr(window_handle) -> tuple[object, bool]:
    """
    Resolves an X11 Display pointer for one native window handle.

    Args:
        window_handle: Qt window handle.

    Returns:
        tuple[object, bool]: Display pointer and whether it must be closed.
    """

    import ctypes
    import ctypes.util

    from PySide6.QtGui import QGuiApplication

    platform_native_getter = getattr(QGuiApplication, "platformNativeInterface", None)
    if callable(platform_native_getter):
        native = platform_native_getter()
        if native is not None:
            display_ptr = native.nativeResourceForWindow("display", window_handle)
            if display_ptr:
                return display_ptr, False

    library_name = ctypes.util.find_library("X11")
    if not library_name:
        return None, False

    x11 = ctypes.CDLL(library_name)
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = ctypes.c_void_p
    display_ptr = x11.XOpenDisplay(None)
    if not display_ptr:
        return None, False
    return display_ptr, True


def restore_x11_window_focus(window_id: str) -> bool:
    """
    Restores keyboard focus to one X11 window.

    Args:
        window_id: Target window id from xdotool.

    Returns:
        bool: True when focus restoration was attempted successfully.
    """

    if which("xdotool") is None:
        return False
    normalized = window_id.strip()
    if not normalized or normalized == "0":
        return False
    try:
        subprocess.run(
            ["xdotool", "windowactivate", normalized],
            check=True,
            timeout=1.0,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def get_x11_focused_window_id() -> str:
    """
    Returns the currently focused X11 window id.

    Returns:
        str: Focused window id or empty string when unavailable.
    """

    if which("xdotool") is None:
        return ""
    try:
        result = subprocess.run(
            ["xdotool", "getwindowfocus"],
            capture_output=True,
            text=True,
            check=True,
            timeout=1.0,
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def apply_x11_wm_class(widget, instance_name: str, class_name: str) -> bool:
    """
    Sets the X11 WM_CLASS property for one top-level window.

    Args:
        widget: Top-level widget with a native window handle.
        instance_name: WM_CLASS instance/resource name.
        class_name: WM_CLASS class/resource class.

    Returns:
        bool: True when WM_CLASS was applied.
    """

    import ctypes
    import ctypes.util

    from PySide6.QtGui import QGuiApplication

    if QGuiApplication.platformName() not in {"xcb", "x11"}:
        return False

    try:
        window_handle = widget.windowHandle()
        if window_handle is None:
            return False

        win_id = int(window_handle.winId())
        if win_id <= 0:
            return False

        display_ptr, close_display = _resolve_x11_display_ptr(window_handle)
        if not display_ptr:
            return False

        library_name = ctypes.util.find_library("X11")
        if not library_name:
            return False

        class XClassHint(ctypes.Structure):
            _fields_ = [
                ("res_name", ctypes.c_char_p),
                ("res_class", ctypes.c_char_p),
            ]

        x11 = ctypes.CDLL(library_name)
        x11.XSetClassHint.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(XClassHint),
        ]
        x11.XSetClassHint.restype = ctypes.c_int
        x11.XFlush.argtypes = [ctypes.c_void_p]
        x11.XFlush.restype = ctypes.c_int
        x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        x11.XCloseDisplay.restype = ctypes.c_int

        hint = XClassHint(
            instance_name.encode("utf-8"),
            class_name.encode("utf-8"),
        )
        applied = x11.XSetClassHint(display_ptr, win_id, ctypes.byref(hint)) != 0
        x11.XFlush(display_ptr)
        if close_display:
            x11.XCloseDisplay(display_ptr)
        return applied
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def apply_linux_window_identity(
    widget,
    *,
    desktop_file_name: str,
    wm_instance: str,
    wm_class: str,
) -> None:
    """
    Applies Linux taskbar identity hints for one top-level window.

    Args:
        widget: Top-level widget shown in the desktop taskbar.
        desktop_file_name: Desktop entry base name without ``.desktop``.
        wm_instance: X11 WM_CLASS instance/resource name.
        wm_class: X11 WM_CLASS class/resource class.

    Returns:
        None
    """

    from PySide6.QtGui import QGuiApplication

    try:
        QGuiApplication.setDesktopFileName(desktop_file_name)
        apply_x11_wm_class(widget, wm_instance, wm_class)
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
        return
