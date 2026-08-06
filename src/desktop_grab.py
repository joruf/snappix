"""
Desktop grab fallbacks for sessions where Qt's own screen grab returns nothing.

``QScreen.grabWindow(0)`` is the fast path, but on some X11 stacks -- virtual
GPUs, and compositors that do not keep the root window painted -- it hands back
a valid, fully opaque, completely **black** image: no error, no null pixmap. The
capture overlay then froze a black desktop and the exported screenshot was
black. External tools read the screen through a different path (XGetImage or the
compositor itself) and still deliver real content in that state, so they serve
as the fallback once a grab is detected as blank.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from shutil import which

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap

from src.py_compat import dataclass

GRAB_BACKEND_QT = "qt"

SESSION_X11 = "x11"
SESSION_WAYLAND = "wayland"

# Anything at or below this summed RGB counts as black for the blank check.
BLANK_LUMA_THRESHOLD = 24

# Sampling grid for the blank check; 64px keeps a 5120x1440 desktop at ~2ms.
BLANK_SAMPLE_STEP = 64

_GRAB_TIMEOUT_SECONDS = 20


@dataclass(frozen=True)
class DesktopGrabBackend:
    """
    Describes one external desktop grab tool.

    Attributes:
        key: Stable identifier stored in snapshots and log messages.
        tool: Executable that must exist on PATH.
        label: Human-readable name for dialogs.
        session: Session type the tool works in (``x11`` or ``wayland``).
        crops_region: True when the tool applies the requested geometry itself.
        writes_to_stdout: True when the PNG arrives on stdout instead of a file.
    """

    key: str
    tool: str
    label: str
    session: str
    crops_region: bool
    writes_to_stdout: bool


def _x11_display() -> str:
    """
    Returns the X11 display name to grab from.

    Returns:
        str: Display specification such as ``:0``.
    """

    return os.environ.get("DISPLAY", "").strip() or ":0"


def _grim_command(x: int, y: int, width: int, height: int, _path: str) -> list[str]:
    """
    Builds the grim command for one region.

    Args:
        x: Region left edge.
        y: Region top edge.
        width: Region width.
        height: Region height.
        _path: Unused output path (grim writes to stdout).

    Returns:
        list[str]: Command arguments.
    """

    return ["grim", "-g", f"{x},{y} {width}x{height}", "-"]


def _ffmpeg_command(x: int, y: int, width: int, height: int, _path: str) -> list[str]:
    """
    Builds the ffmpeg x11grab command for one region.

    ``-draw_mouse 0`` matches Qt's grab, which never includes the pointer.

    Args:
        x: Region left edge.
        y: Region top edge.
        width: Region width.
        height: Region height.
        _path: Unused output path (ffmpeg writes to stdout).

    Returns:
        list[str]: Command arguments.
    """

    return [
        "ffmpeg",
        "-loglevel",
        "error",
        "-f",
        "x11grab",
        "-draw_mouse",
        "0",
        "-video_size",
        f"{width}x{height}",
        "-i",
        f"{_x11_display()}+{x},{y}",
        "-frames:v",
        "1",
        "-f",
        "image2pipe",
        "-vcodec",
        "png",
        "-",
    ]


def _maim_command(x: int, y: int, width: int, height: int, _path: str) -> list[str]:
    """
    Builds the maim command for one region.

    Args:
        x: Region left edge.
        y: Region top edge.
        width: Region width.
        height: Region height.
        _path: Unused output path (maim writes to stdout).

    Returns:
        list[str]: Command arguments.
    """

    return ["maim", "--hidecursor", "-g", f"{width}x{height}+{x}+{y}"]


def _import_command(x: int, y: int, width: int, height: int, _path: str) -> list[str]:
    """
    Builds the ImageMagick import command for one region.

    Args:
        x: Region left edge.
        y: Region top edge.
        width: Region width.
        height: Region height.
        _path: Unused output path (import writes to stdout).

    Returns:
        list[str]: Command arguments.
    """

    return [
        "import",
        "-window",
        "root",
        "-crop",
        f"{width}x{height}+{x}+{y}",
        "+repage",
        "png:-",
    ]


def _gnome_screenshot_command(
    _x: int,
    _y: int,
    _width: int,
    _height: int,
    path: str,
) -> list[str]:
    """
    Builds the gnome-screenshot command for the whole desktop.

    gnome-screenshot has no non-interactive region mode, so it grabs everything
    and the caller crops the result.

    Args:
        _x: Unused region left edge.
        _y: Unused region top edge.
        _width: Unused region width.
        _height: Unused region height.
        path: Output PNG path.

    Returns:
        list[str]: Command arguments.
    """

    return ["gnome-screenshot", "-f", path]


_BACKENDS: tuple[DesktopGrabBackend, ...] = (
    DesktopGrabBackend(
        key="grim",
        tool="grim",
        label="grim",
        session=SESSION_WAYLAND,
        crops_region=True,
        writes_to_stdout=True,
    ),
    DesktopGrabBackend(
        key="ffmpeg",
        tool="ffmpeg",
        label="ffmpeg (x11grab)",
        session=SESSION_X11,
        crops_region=True,
        writes_to_stdout=True,
    ),
    DesktopGrabBackend(
        key="maim",
        tool="maim",
        label="maim",
        session=SESSION_X11,
        crops_region=True,
        writes_to_stdout=True,
    ),
    DesktopGrabBackend(
        key="import",
        tool="import",
        label="ImageMagick (import)",
        session=SESSION_X11,
        crops_region=True,
        writes_to_stdout=True,
    ),
    DesktopGrabBackend(
        key="gnome-screenshot",
        tool="gnome-screenshot",
        label="gnome-screenshot",
        session=SESSION_X11,
        crops_region=False,
        writes_to_stdout=False,
    ),
)

_COMMAND_BUILDERS = {
    "grim": _grim_command,
    "ffmpeg": _ffmpeg_command,
    "maim": _maim_command,
    "import": _import_command,
    "gnome-screenshot": _gnome_screenshot_command,
}


def build_grab_command(
    backend: DesktopGrabBackend,
    x: int,
    y: int,
    width: int,
    height: int,
    path: str = "",
) -> list[str]:
    """
    Builds the command line for one backend and region.

    Args:
        backend: Backend to run.
        x: Region left edge in screen coordinates.
        y: Region top edge in screen coordinates.
        width: Region width in pixels.
        height: Region height in pixels.
        path: Output path for backends that cannot write to stdout.

    Returns:
        list[str]: Command arguments.
    """

    builder = _COMMAND_BUILDERS[backend.key]
    return builder(x, y, width, height, path)


def backends_for_session(*, wayland: bool) -> tuple[DesktopGrabBackend, ...]:
    """
    Returns all backends that can work in the given session type.

    Args:
        wayland: True for a Wayland session.

    Returns:
        tuple[DesktopGrabBackend, ...]: Backends in preference order.
    """

    session = SESSION_WAYLAND if wayland else SESSION_X11
    return tuple(backend for backend in _BACKENDS if backend.session == session)


def available_grab_backends(*, wayland: bool) -> tuple[DesktopGrabBackend, ...]:
    """
    Returns installed backends for the given session type, in preference order.

    Args:
        wayland: True for a Wayland session.

    Returns:
        tuple[DesktopGrabBackend, ...]: Installed backends.
    """

    return tuple(
        backend
        for backend in backends_for_session(wayland=wayland)
        if which(backend.tool) is not None
    )


def describe_grab_backends(*, wayland: bool) -> str:
    """
    Returns a comma-separated list of backend tools for user-facing messages.

    Args:
        wayland: True for a Wayland session.

    Returns:
        str: Tool names, empty when none of them is installed.
    """

    return ", ".join(
        backend.label for backend in available_grab_backends(wayland=wayland)
    )


def is_blank_image(image: QImage, step: int = BLANK_SAMPLE_STEP) -> bool:
    """
    Detects an image that carries no visible content.

    Samples a sparse grid instead of every pixel: a broken grab is uniformly
    transparent or black, so a grid catches it while staying cheap on a
    multi-monitor desktop.

    Args:
        image: Image to inspect.
        step: Sampling distance in pixels.

    Returns:
        bool: True when every sample is transparent or (near-)black.
    """

    if image.isNull() or image.width() <= 0 or image.height() <= 0:
        return True
    sample_step = max(1, int(step))
    for y in range(0, image.height(), sample_step):
        for x in range(0, image.width(), sample_step):
            color = image.pixelColor(x, y)
            if color.alpha() == 0:
                continue
            if color.red() + color.green() + color.blue() > BLANK_LUMA_THRESHOLD:
                return False
    return True


def is_blank_pixmap(pixmap: QPixmap, step: int = BLANK_SAMPLE_STEP) -> bool:
    """
    Detects a pixmap that carries no visible content.

    Args:
        pixmap: Pixmap to inspect.
        step: Sampling distance in pixels.

    Returns:
        bool: True when every sample is transparent or (near-)black.
    """

    if pixmap.isNull():
        return True
    return is_blank_image(pixmap.toImage(), step)


def _run_backend(
    backend: DesktopGrabBackend,
    x: int,
    y: int,
    width: int,
    height: int,
) -> bytes | None:
    """
    Runs one backend and returns its PNG bytes.

    Args:
        backend: Backend to run.
        x: Region left edge.
        y: Region top edge.
        width: Region width.
        height: Region height.

    Returns:
        bytes | None: PNG data, or None when the tool failed.
    """

    if backend.writes_to_stdout:
        command = build_grab_command(backend, x, y, width, height)
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                check=True,
                timeout=_GRAB_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return bytes(result.stdout) or None

    with tempfile.TemporaryDirectory(prefix="snappix-grab-") as directory:
        target = str(Path(directory) / "desktop.png")
        command = build_grab_command(backend, x, y, width, height, target)
        try:
            subprocess.run(
                command,
                capture_output=True,
                check=True,
                timeout=_GRAB_TIMEOUT_SECONDS,
            )
            return Path(target).read_bytes() or None
        except (OSError, subprocess.SubprocessError):
            return None


def fit_pixmap_to_region(
    pixmap: QPixmap,
    x: int,
    y: int,
    width: int,
    height: int,
    *,
    crops_region: bool,
) -> QPixmap:
    """
    Trims or scales a backend result to the requested region.

    Args:
        pixmap: Loaded backend result.
        x: Region left edge in screen coordinates.
        y: Region top edge in screen coordinates.
        width: Region width in pixels.
        height: Region height in pixels.
        crops_region: True when the backend already applied the geometry.

    Returns:
        QPixmap: Region-sized pixmap, null when the result cannot be used.
    """

    if pixmap.isNull() or width <= 0 or height <= 0:
        return QPixmap()
    if pixmap.width() == width and pixmap.height() == height:
        return pixmap
    if not crops_region and pixmap.width() >= x + width and pixmap.height() >= y + height:
        return pixmap.copy(x, y, width, height)
    # Last resort: a tool reported a different resolution (scaled desktop, HiDPI
    # mismatch). Stretching keeps the capture usable instead of dropping it.
    return pixmap.scaled(
        width,
        height,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def grab_desktop_region(
    x: int,
    y: int,
    width: int,
    height: int,
    *,
    wayland: bool,
) -> tuple[QPixmap, str] | None:
    """
    Grabs one desktop region with the first external backend that delivers data.

    Args:
        x: Region left edge in screen coordinates.
        y: Region top edge in screen coordinates.
        width: Region width in pixels.
        height: Region height in pixels.
        wayland: True for a Wayland session.

    Returns:
        tuple[QPixmap, str] | None: Region pixmap and backend key, or None when
        no backend produced a usable image.
    """

    if width <= 0 or height <= 0:
        return None
    for backend in available_grab_backends(wayland=wayland):
        data = _run_backend(backend, x, y, width, height)
        if not data:
            continue
        pixmap = QPixmap()
        if not pixmap.loadFromData(data, "PNG") or pixmap.isNull():
            continue
        fitted = fit_pixmap_to_region(
            pixmap,
            x,
            y,
            width,
            height,
            crops_region=backend.crops_region,
        )
        if fitted.isNull():
            continue
        return fitted, backend.key
    return None
