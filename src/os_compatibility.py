"""
Operating-system compatibility matrix for Snappix.

Evaluates which features are expected to work under a given platform profile.
Used by automated tests and documents supported Linux session/tool combinations.
"""

from __future__ import annotations

import sys
from src.py_compat import dataclass
from enum import Enum


class SupportLevel(str, Enum):
    """
    Describes how fully one feature is supported on a platform profile.
    """

    FULL = "full"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class PlatformContext:
    """
    Describes one runtime environment for compatibility evaluation.

    Attributes:
        os_family: ``linux``, ``windows``, or ``darwin``.
        is_wayland: True when the desktop session uses Wayland.
        available_tools: External binaries expected on PATH for this profile.
    """

    os_family: str
    is_wayland: bool = False
    available_tools: frozenset[str] = frozenset()

    def has_tool(self, name: str) -> bool:
        """
        Checks whether one external tool is available in this profile.

        Args:
            name: Binary name such as ``grim`` or ``xdotool``.

        Returns:
            bool: True when the tool is listed for this profile.
        """

        return name in self.available_tools


@dataclass(frozen=True, slots=True)
class FeatureCapability:
    """
    Describes support for one Snappix feature on one platform profile.

    Attributes:
        feature_id: Stable feature identifier.
        level: Support level for the feature.
        note: Short explanation shown in tests and diagnostics.
    """

    feature_id: str
    level: SupportLevel
    note: str = ""


_ALL_LINUX_TOOLS = frozenset(
    {
        "xdotool",
        "xwininfo",
        "grim",
        "slurp",
        "tesseract",
        "ffmpeg",
    }
)

LINUX_X11_FULL = PlatformContext(
    os_family="linux",
    is_wayland=False,
    available_tools=_ALL_LINUX_TOOLS,
)

LINUX_X11_MINIMAL = PlatformContext(
    os_family="linux",
    is_wayland=False,
    available_tools=frozenset(),
)

LINUX_X11_NO_XDOTOOL = PlatformContext(
    os_family="linux",
    is_wayland=False,
    available_tools=_ALL_LINUX_TOOLS - {"xdotool", "xwininfo"},
)

LINUX_WAYLAND_GRIM = PlatformContext(
    os_family="linux",
    is_wayland=True,
    available_tools=frozenset({"grim", "slurp", "tesseract", "ffmpeg"}),
)

LINUX_WAYLAND_NO_GRIM = PlatformContext(
    os_family="linux",
    is_wayland=True,
    available_tools=frozenset({"tesseract", "ffmpeg"}),
)

WINDOWS = PlatformContext(
    os_family="windows",
    available_tools=frozenset({"ffmpeg", "tesseract"}),
)
WINDOWS_MINIMAL = PlatformContext(os_family="windows")
DARWIN = PlatformContext(os_family="darwin")

KNOWN_PROFILES: dict[str, PlatformContext] = {
    "linux_x11_full": LINUX_X11_FULL,
    "linux_x11_minimal": LINUX_X11_MINIMAL,
    "linux_x11_no_xdotool": LINUX_X11_NO_XDOTOOL,
    "linux_wayland_grim": LINUX_WAYLAND_GRIM,
    "linux_wayland_no_grim": LINUX_WAYLAND_NO_GRIM,
    "windows": WINDOWS,
    "windows_minimal": WINDOWS_MINIMAL,
    "darwin": DARWIN,
}


def current_os_family() -> str:
    """
    Returns the current interpreter OS family.

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


def region_capture_route(context: PlatformContext) -> str:
    """
    Mirrors capture routing for region mode.

    Args:
        context: Platform profile to evaluate.

    Returns:
        str: ``grim_slurp``, ``qt_overlay``, or ``unavailable``.
    """

    if context.os_family not in {"linux", "windows"}:
        return "unavailable"
    if (
        context.os_family == "linux"
        and context.is_wayland
        and context.has_tool("grim")
        and context.has_tool("slurp")
    ):
        return "grim_slurp"
    return "qt_overlay"


def evaluate_capabilities(context: PlatformContext) -> dict[str, FeatureCapability]:
    """
    Evaluates Snappix feature support for one platform profile.

    Args:
        context: Platform profile to evaluate.

    Returns:
        dict[str, FeatureCapability]: Feature id to capability mapping.
    """

    capabilities = {
        "app_launch": _app_launch_capability(context),
        "fullscreen_capture": _fullscreen_capture_capability(context),
        "region_capture": _region_capture_capability(context),
        "window_capture": _window_capture_capability(context),
        "scroll_capture": _scroll_capture_capability(context),
        "video_capture": _video_capture_capability(context),
        "ocr": _ocr_capability(context),
        "global_hotkeys": _global_hotkeys_capability(context),
        "autostart": _autostart_capability(context),
    }
    return capabilities


def _app_launch_capability(context: PlatformContext) -> FeatureCapability:
    if context.os_family == "linux":
        return FeatureCapability(
            "app_launch",
            SupportLevel.FULL,
            "PySide6 GUI is supported on Linux.",
        )
    if context.os_family == "windows":
        return FeatureCapability(
            "app_launch",
            SupportLevel.PARTIAL,
            "Windows MVP: editor + Qt capture + window/scroll pick + ffmpeg gdigrab.",
        )
    return FeatureCapability(
        "app_launch",
        SupportLevel.UNSUPPORTED,
        "macOS is not supported yet.",
    )


def _fullscreen_capture_capability(context: PlatformContext) -> FeatureCapability:
    if context.os_family == "windows":
        return FeatureCapability(
            "fullscreen_capture",
            SupportLevel.FULL,
            "Qt desktop sampling works on Windows.",
        )
    if context.os_family != "linux":
        return FeatureCapability(
            "fullscreen_capture",
            SupportLevel.UNSUPPORTED,
            "Fullscreen capture is not supported on this OS.",
        )
    if context.is_wayland and context.has_tool("grim"):
        return FeatureCapability(
            "fullscreen_capture",
            SupportLevel.FULL,
            "Wayland fullscreen capture can use grim.",
        )
    return FeatureCapability(
        "fullscreen_capture",
        SupportLevel.FULL,
        "Qt desktop sampling works on X11 and as a Wayland fallback.",
    )


def _region_capture_capability(context: PlatformContext) -> FeatureCapability:
    route = region_capture_route(context)
    if route == "unavailable":
        return FeatureCapability(
            "region_capture",
            SupportLevel.UNSUPPORTED,
            "Region capture is not supported on this OS.",
        )
    if route == "grim_slurp":
        return FeatureCapability(
            "region_capture",
            SupportLevel.FULL,
            "Native Wayland region picker via grim and slurp.",
        )
    if context.os_family == "windows":
        return FeatureCapability(
            "region_capture",
            SupportLevel.PARTIAL,
            "Region selection uses a Qt fullscreen overlay crop on Windows.",
        )
    return FeatureCapability(
        "region_capture",
        SupportLevel.PARTIAL,
        "Region selection uses a Qt fullscreen overlay crop.",
    )


def _window_capture_capability(context: PlatformContext) -> FeatureCapability:
    if context.os_family == "windows":
        return FeatureCapability(
            "window_capture",
            SupportLevel.FULL,
            "Win32 window pick with Qt desktop snapshot crop.",
        )
    if context.os_family != "linux":
        return FeatureCapability(
            "window_capture",
            SupportLevel.UNSUPPORTED,
            "Window capture is not supported on this OS.",
        )
    if context.is_wayland:
        return FeatureCapability(
            "window_capture",
            SupportLevel.UNSUPPORTED,
            "Wayland does not expose per-window X11 selection.",
        )
    if not context.has_tool("xdotool") or not context.has_tool("xwininfo"):
        return FeatureCapability(
            "window_capture",
            SupportLevel.UNSUPPORTED,
            "Window capture requires xdotool and xwininfo.",
        )
    return FeatureCapability(
        "window_capture",
        SupportLevel.FULL,
        "X11 window selection via xdotool and xwininfo.",
    )


def _scroll_capture_capability(context: PlatformContext) -> FeatureCapability:
    if context.os_family == "windows":
        return FeatureCapability(
            "scroll_capture",
            SupportLevel.PARTIAL,
            "Win32 PageDown scroll + stitch; best-effort for normal desktop apps.",
        )
    if context.os_family != "linux":
        return FeatureCapability(
            "scroll_capture",
            SupportLevel.UNSUPPORTED,
            "Scroll capture is not supported on this OS.",
        )
    if context.is_wayland:
        return FeatureCapability(
            "scroll_capture",
            SupportLevel.UNSUPPORTED,
            "Automatic scroll capture needs X11 window control.",
        )
    if not context.has_tool("xdotool") or not context.has_tool("xwininfo"):
        return FeatureCapability(
            "scroll_capture",
            SupportLevel.UNSUPPORTED,
            "Scroll capture requires xdotool and xwininfo.",
        )
    return FeatureCapability(
        "scroll_capture",
        SupportLevel.FULL,
        "X11 auto-scroll via xdotool with vertical frame stitching.",
    )


def _video_capture_capability(context: PlatformContext) -> FeatureCapability:
    if context.os_family == "windows":
        if not context.has_tool("ffmpeg"):
            return FeatureCapability(
                "video_capture",
                SupportLevel.UNSUPPORTED,
                "Video capture requires ffmpeg (gdigrab).",
            )
        return FeatureCapability(
            "video_capture",
            SupportLevel.FULL,
            "Region screen recording via ffmpeg gdigrab.",
        )
    if context.os_family != "linux":
        return FeatureCapability(
            "video_capture",
            SupportLevel.UNSUPPORTED,
            "Video capture is not supported on this OS.",
        )
    if context.is_wayland:
        return FeatureCapability(
            "video_capture",
            SupportLevel.UNSUPPORTED,
            "ffmpeg x11grab recording requires an X11 session.",
        )
    if not context.has_tool("ffmpeg"):
        return FeatureCapability(
            "video_capture",
            SupportLevel.UNSUPPORTED,
            "Video capture requires ffmpeg.",
        )
    return FeatureCapability(
        "video_capture",
        SupportLevel.FULL,
        "Region screen recording via ffmpeg x11grab.",
    )


def _ocr_capability(context: PlatformContext) -> FeatureCapability:
    if context.os_family not in {"linux", "windows"}:
        return FeatureCapability(
            "ocr",
            SupportLevel.UNSUPPORTED,
            "OCR is not supported on this OS.",
        )
    if not context.has_tool("tesseract"):
        return FeatureCapability(
            "ocr",
            SupportLevel.UNSUPPORTED,
            "OCR requires the tesseract binary.",
        )
    return FeatureCapability(
        "ocr",
        SupportLevel.FULL,
        "Text recognition via tesseract.",
    )


def _global_hotkeys_capability(context: PlatformContext) -> FeatureCapability:
    if context.os_family == "windows":
        return FeatureCapability(
            "global_hotkeys",
            SupportLevel.PARTIAL,
            "Global hotkeys via pynput on Windows (may need elevated privileges).",
        )
    if context.os_family != "linux":
        return FeatureCapability(
            "global_hotkeys",
            SupportLevel.UNSUPPORTED,
            "Global hotkeys are not configured for this OS.",
        )
    if context.is_wayland:
        return FeatureCapability(
            "global_hotkeys",
            SupportLevel.PARTIAL,
            "pynput hotkeys may be limited by the Wayland compositor.",
        )
    return FeatureCapability(
        "global_hotkeys",
        SupportLevel.FULL,
        "Global hotkeys via pynput on X11.",
    )


def _autostart_capability(context: PlatformContext) -> FeatureCapability:
    if context.os_family == "windows":
        return FeatureCapability(
            "autostart",
            SupportLevel.FULL,
            "Windows Startup folder batch file is supported.",
        )
    if context.os_family != "linux":
        return FeatureCapability(
            "autostart",
            SupportLevel.UNSUPPORTED,
            "Autostart is not supported on this OS.",
        )
    return FeatureCapability(
        "autostart",
        SupportLevel.FULL,
        "XDG autostart desktop entry is supported on Linux.",
    )
