"""
Win32 helpers for top-level window pick and geometry (Windows Capture Window).
"""

from __future__ import annotations

import ctypes
import sys
from collections.abc import Iterable
from ctypes import wintypes

from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QGuiApplication

# WINFUNCTYPE exists only on Windows; CFUNCTYPE works for mocked unit tests on Linux.
WINFUNCTYPE = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)

GA_ROOT = 2
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class POINT(ctypes.Structure):
    _fields_ = [
        ("x", wintypes.LONG),
        ("y", wintypes.LONG),
    ]


def _user32():
    return ctypes.windll.user32


def is_win32_available() -> bool:
    """
    Returns whether Win32 window APIs can be used on this process.

    Returns:
        bool: True on native Windows.
    """

    return sys.platform == "win32"


def _device_pixel_ratio_at(x: int, y: int) -> float:
    screen = QGuiApplication.screenAt(QPoint(x, y))
    if screen is None:
        screen = QGuiApplication.primaryScreen()
    if screen is None:
        return 1.0
    ratio = float(screen.devicePixelRatio())
    return ratio if ratio > 0 else 1.0


def qt_point_to_physical(x: int, y: int) -> tuple[int, int]:
    """
    Converts a Qt logical desktop point to physical pixels for Win32 APIs.

    Args:
        x: Logical X coordinate.
        y: Logical Y coordinate.

    Returns:
        tuple[int, int]: Physical pixel coordinates.
    """

    ratio = _device_pixel_ratio_at(x, y)
    return int(round(x * ratio)), int(round(y * ratio))


def physical_rect_to_qt(left: int, top: int, right: int, bottom: int) -> QRect:
    """
    Converts a physical Win32 rect into a Qt logical ``QRect``.

    Args:
        left: Physical left edge.
        top: Physical top edge.
        right: Physical right edge.
        bottom: Physical bottom edge.

    Returns:
        QRect: Logical geometry in Qt desktop coordinates.
    """

    primary = QGuiApplication.primaryScreen()
    seed_ratio = float(primary.devicePixelRatio()) if primary is not None else 1.0
    if seed_ratio <= 0:
        seed_ratio = 1.0
    mid_logical = QPoint(
        int(round(((left + right) / 2) / seed_ratio)),
        int(round(((top + bottom) / 2) / seed_ratio)),
    )
    ratio = _device_pixel_ratio_at(mid_logical.x(), mid_logical.y())
    return QRect(
        int(round(left / ratio)),
        int(round(top / ratio)),
        max(0, int(round((right - left) / ratio))),
        max(0, int(round((bottom - top) / ratio))),
    )


def _hwnd_to_int(hwnd) -> int:
    if hwnd is None:
        return 0
    value = getattr(hwnd, "value", hwnd)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def get_top_level_hwnd(hwnd: int) -> int:
    """
    Resolves the top-level ancestor for one HWND.

    Args:
        hwnd: Window handle (may be a child).

    Returns:
        int: Top-level HWND, or 0 when invalid.
    """

    hwnd_i = _hwnd_to_int(hwnd)
    if not hwnd_i:
        return 0
    user32 = _user32()
    root = _hwnd_to_int(user32.GetAncestor(wintypes.HWND(hwnd_i), GA_ROOT))
    return root or hwnd_i


def get_window_rect(hwnd: int) -> QRect:
    """
    Returns the outer window rectangle for one HWND in Qt logical coordinates.

    Args:
        hwnd: Top-level window handle.

    Returns:
        QRect: Window geometry, or an empty rect when unavailable.
    """

    if not hwnd:
        return QRect()
    rect = RECT()
    if not _user32().GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
        return QRect()
    return physical_rect_to_qt(rect.left, rect.top, rect.right, rect.bottom)


def _is_capturable_top_level(hwnd: int, exclude: set[int]) -> bool:
    hwnd_i = _hwnd_to_int(hwnd)
    if not hwnd_i or hwnd_i in exclude:
        return False
    user32 = _user32()
    handle = wintypes.HWND(hwnd_i)
    if not user32.IsWindow(handle):
        return False
    if not user32.IsWindowVisible(handle):
        return False
    if _hwnd_to_int(user32.GetAncestor(handle, GA_ROOT)) != hwnd_i:
        return False
    # Skip tool/no-activate chrome that should not be capture targets.
    try:
        ex_style = int(user32.GetWindowLongW(handle, GWL_EXSTYLE))
    except OSError:
        ex_style = 0
    if ex_style & WS_EX_TOOLWINDOW:
        return False
    return True


def window_at_point(
    x: int,
    y: int,
    *,
    exclude_hwnds: Iterable[int] = (),
) -> tuple[int, QRect]:
    """
    Finds the top-most capturable top-level window under a Qt logical point.

    Uses ``EnumWindows`` (Z-order) so the Snappix overlay HWND can be excluded
    even when it is receiving mouse input.

    Args:
        x: Logical cursor X.
        y: Logical cursor Y.
        exclude_hwnds: HWNDs to ignore (overlay, capture panel, etc.).

    Returns:
        tuple[int, QRect]: HWND and geometry, or ``(0, QRect())`` when none.
    """

    if not is_win32_available():
        return 0, QRect()

    exclude = {int(value) for value in exclude_hwnds if value}
    physical_x, physical_y = qt_point_to_physical(x, y)
    user32 = _user32()
    found: list[int] = []

    @WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum_proc(hwnd, _lparam):  # type: ignore[no-untyped-def]
        handle = _hwnd_to_int(hwnd)
        if not _is_capturable_top_level(handle, exclude):
            return True
        rect = RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        if not (rect.left <= physical_x < rect.right and rect.top <= physical_y < rect.bottom):
            return True
        found.append(handle)
        return False  # Stop at first (top-most) match.

    user32.EnumWindows(_enum_proc, 0)
    if not found:
        return 0, QRect()
    hwnd = _hwnd_to_int(found[0])
    return hwnd, get_window_rect(hwnd)


def window_from_point(x: int, y: int, *, exclude_hwnds: Iterable[int] = ()) -> tuple[int, QRect]:
    """
    Alias for ``window_at_point`` kept for call-site clarity.

    Args:
        x: Logical cursor X.
        y: Logical cursor Y.
        exclude_hwnds: HWNDs to ignore.

    Returns:
        tuple[int, QRect]: HWND and geometry.
    """

    return window_at_point(x, y, exclude_hwnds=exclude_hwnds)


# --- Focus / keyboard helpers for Windows scroll capture ---

SW_RESTORE = 9
INPUT_KEYBOARD = 1
INPUT_MOUSE = 0
KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_WHEEL = 0x0800
WHEEL_DELTA = 120
VK_CONTROL = 0x11
VK_HOME = 0x24
VK_PRIOR = 0x21  # Page Up
VK_NEXT = 0x22  # Page Down
VK_UP = 0x26
VK_DOWN = 0x28


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", _INPUTUNION),
    ]


def get_foreground_hwnd() -> int:
    """
    Returns the HWND of the foreground window.

    Returns:
        int: Foreground HWND, or 0 when unavailable.
    """

    if not is_win32_available():
        return 0
    return _hwnd_to_int(_user32().GetForegroundWindow())


def raise_window(hwnd: int) -> bool:
    """
    Raises and activates one top-level window for capture.

    Args:
        hwnd: Target window handle.

    Returns:
        bool: True when activation was attempted.
    """

    hwnd_i = _hwnd_to_int(hwnd)
    if not hwnd_i or not is_win32_available():
        return False
    user32 = _user32()
    handle = wintypes.HWND(hwnd_i)
    try:
        if user32.IsIconic(handle):
            user32.ShowWindow(handle, SW_RESTORE)
        user32.BringWindowToTop(handle)
        # AttachThreadInput helps SetForegroundWindow succeed more often.
        foreground = _hwnd_to_int(user32.GetForegroundWindow())
        current_tid = ctypes.windll.kernel32.GetCurrentThreadId()
        target_tid = user32.GetWindowThreadProcessId(handle, None)
        foreground_tid = (
            user32.GetWindowThreadProcessId(wintypes.HWND(foreground), None)
            if foreground
            else 0
        )
        attached = False
        if foreground_tid and foreground_tid != current_tid:
            attached = bool(user32.AttachThreadInput(current_tid, foreground_tid, True))
        if target_tid and target_tid != current_tid:
            user32.AttachThreadInput(current_tid, target_tid, True)
        user32.SetForegroundWindow(handle)
        user32.SetActiveWindow(handle)
        user32.SetFocus(handle)
        if attached and foreground_tid:
            user32.AttachThreadInput(current_tid, foreground_tid, False)
        if target_tid and target_tid != current_tid:
            user32.AttachThreadInput(current_tid, target_tid, False)
        return True
    except OSError:
        return False


def restore_window_focus(hwnd: int | str) -> bool:
    """
    Restores focus to one previously focused window.

    Args:
        hwnd: HWND as int or decimal string.

    Returns:
        bool: True when restore was attempted.
    """

    try:
        handle = int(str(hwnd).strip())
    except (TypeError, ValueError):
        return False
    return raise_window(handle)


def _send_inputs(inputs: list[INPUT]) -> bool:
    if not inputs or not is_win32_available():
        return False
    array_type = INPUT * len(inputs)
    payload = array_type(*inputs)
    sent = _user32().SendInput(len(inputs), ctypes.byref(payload), ctypes.sizeof(INPUT))
    return sent == len(inputs)


def _key_input(vk: int, *, key_up: bool = False) -> INPUT:
    flags = KEYEVENTF_KEYUP if key_up else 0
    return INPUT(
        type=INPUT_KEYBOARD,
        union=_INPUTUNION(
            ki=KEYBDINPUT(
                wVk=vk,
                wScan=0,
                dwFlags=flags,
                time=0,
                dwExtraInfo=None,
            )
        ),
    )


def send_key(vk: int) -> bool:
    """
    Sends one virtual-key press/release via ``SendInput``.

    Args:
        vk: Virtual-key code.

    Returns:
        bool: True when both down and up events were sent.
    """

    return _send_inputs([_key_input(vk, key_up=False), _key_input(vk, key_up=True)])


def send_chord(modifiers: list[int], vk: int) -> bool:
    """
    Sends a modifier chord such as Ctrl+Home.

    Args:
        modifiers: Modifier virtual-key codes held during ``vk``.
        vk: Main virtual-key code.

    Returns:
        bool: True when the chord was sent.
    """

    events: list[INPUT] = [_key_input(mod, key_up=False) for mod in modifiers]
    events.append(_key_input(vk, key_up=False))
    events.append(_key_input(vk, key_up=True))
    events.extend(_key_input(mod, key_up=True) for mod in reversed(modifiers))
    return _send_inputs(events)


def click_screen_point(logical_x: int, logical_y: int) -> bool:
    """
    Moves the cursor and left-clicks one Qt logical screen point.

    Args:
        logical_x: Logical desktop X.
        logical_y: Logical desktop Y.

    Returns:
        bool: True when the click was sent.
    """

    if not is_win32_available():
        return False
    physical_x, physical_y = qt_point_to_physical(logical_x, logical_y)
    user32 = _user32()
    if not user32.SetCursorPos(physical_x, physical_y):
        return False
    down = INPUT(
        type=INPUT_MOUSE,
        union=_INPUTUNION(
            mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, None),
        ),
    )
    up = INPUT(
        type=INPUT_MOUSE,
        union=_INPUTUNION(
            mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, None),
        ),
    )
    return _send_inputs([down, up])


def focus_window_content(hwnd: int, window_rect: QRect) -> bool:
    """
    Activates a window and clicks its content area so keys reach the scroller.

    Args:
        hwnd: Target window handle.
        window_rect: Window bounds in Qt logical desktop coordinates.

    Returns:
        bool: True when focus/click were attempted.
    """

    if window_rect.isNull() or window_rect.width() <= 0 or window_rect.height() <= 0:
        return False
    if not raise_window(hwnd):
        return False
    click_x = window_rect.x() + max(1, window_rect.width() // 2)
    click_y = window_rect.y() + max(96, int(window_rect.height() * 0.55))
    return click_screen_point(click_x, click_y)


def scroll_window_to_top(hwnd: int, window_rect: QRect) -> None:
    """
    Moves the focused window scroll position toward the top via keys.

    Args:
        hwnd: Target window handle.
        window_rect: Window bounds in Qt logical coordinates.

    Returns:
        None
    """

    import time

    focus_window_content(hwnd, window_rect)
    time.sleep(0.12)
    for _ in range(3):
        send_chord([VK_CONTROL], VK_HOME)
        send_key(VK_HOME)
    for _ in range(10):
        send_key(VK_PRIOR)
    time.sleep(0.45)


def send_mouse_wheel(notches: int) -> bool:
    """
    Sends a vertical mouse-wheel scroll at the current cursor position.

    Args:
        notches: Wheel notches (negative = scroll down / content up).

    Returns:
        bool: True when the wheel event was sent.
    """

    if notches == 0 or not is_win32_available():
        return False
    wheel = INPUT(
        type=INPUT_MOUSE,
        union=_INPUTUNION(
            mi=MOUSEINPUT(0, 0, notches * WHEEL_DELTA & 0xFFFFFFFF, MOUSEEVENTF_WHEEL, 0, None),
        ),
    )
    return _send_inputs([wheel])


def scroll_window_down(hwnd: int, window_rect: QRect | None = None) -> None:
    """
    Scrolls the focused window down by roughly one viewport step.

    Prefers mouse-wheel input (more reliable for Firefox/Chrome), with PageDown
    as a secondary nudge for native controls.

    Args:
        hwnd: Target window handle.
        window_rect: Optional window bounds used to re-click content before scroll.

    Returns:
        None
    """

    import time

    if window_rect is not None and not window_rect.isNull():
        focus_window_content(hwnd, window_rect)
        time.sleep(0.05)
    else:
        raise_window(hwnd)
    # Three wheel notches ≈ a comfortable page step in most browsers.
    send_mouse_wheel(-3)
    send_key(VK_NEXT)
    time.sleep(0.28)


def pulse_scrollbar_visible(hwnd: int, window_rect: QRect | None = None) -> None:
    """
    Nudges scroll so overlay scrollbars become visible in captures.

    Args:
        hwnd: Target window handle.
        window_rect: Optional window bounds for content focus.

    Returns:
        None
    """

    import time

    if window_rect is not None and not window_rect.isNull():
        focus_window_content(hwnd, window_rect)
    else:
        raise_window(hwnd)
    send_mouse_wheel(-1)
    time.sleep(0.06)
    send_mouse_wheel(1)
    time.sleep(0.1)
