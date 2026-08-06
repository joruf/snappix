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

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QImage, QPixmap

from src.py_compat import dataclass

GRAB_BACKEND_QT = "qt"

SESSION_X11 = "x11"
SESSION_WAYLAND = "wayland"

# Anything at or below this summed RGB counts as black for the blank check.
BLANK_LUMA_THRESHOLD = 24

# Sampling grid for the blank check; 64px keeps a 5120x1440 desktop at ~2ms.
BLANK_SAMPLE_STEP = 64

# A grab with less visible content than this is not trusted on its own. The
# failure is not always all-or-nothing: one screen of a multi-monitor desktop can
# come back black while the other is fine, and a grab can return a single window
# on an otherwise black screen. Both look "not blank" to a plain emptiness test,
# so anything this sparse is cross-checked against an external grab and the
# richer image wins. A genuinely dark screen loses nothing -- both sources then
# report the same darkness and the result is identical, only slower.
SUSPICIOUS_VISIBLE_FRACTION = 0.02

# Reference probe: tiles read straight from the X server and compared against the
# grabbed image. A 16px tile costs well under a millisecond, so a grid of them can
# run on every capture -- this is what separates "the grab is broken" from "the
# desktop is dark", which no content heuristic can decide on its own.
REFERENCE_TILE_SIZE = 16
REFERENCE_TILE_GRID = (5, 3)

# Brightness (0-255) above which a reference tile counts as real content, and at
# or below which a grabbed tile counts as black.
REFERENCE_CONTENT_BRIGHTNESS = 8.0
REFERENCE_BLACK_BRIGHTNESS = 2.0

# Judge only when enough tiles carry content, and require a solid share of them
# to disagree: a window repainting between grab and probe must not count as a
# broken grab.
REFERENCE_MIN_CONTENT_TILES = 3
REFERENCE_MISMATCH_RATIO = 0.5

_X11_PROBE_DISPLAY = None
_X11_PROBE_AVAILABLE = True

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


def visible_image_fraction(image: QImage, step: int = BLANK_SAMPLE_STEP) -> float:
    """
    Returns how much of an image carries visible content.

    Samples a sparse grid instead of every pixel: a broken grab is uniformly
    transparent or black, so a grid catches it while staying cheap on a
    multi-monitor desktop.

    Args:
        image: Image to inspect.
        step: Sampling distance in pixels.

    Returns:
        float: Share of samples that are opaque and above the black threshold,
        between 0.0 and 1.0. A null image reports 0.0.
    """

    if image.isNull() or image.width() <= 0 or image.height() <= 0:
        return 0.0
    sample_step = max(1, int(step))
    samples = 0
    visible = 0
    for y in range(0, image.height(), sample_step):
        for x in range(0, image.width(), sample_step):
            color = image.pixelColor(x, y)
            samples += 1
            if color.alpha() == 0:
                continue
            if color.red() + color.green() + color.blue() > BLANK_LUMA_THRESHOLD:
                visible += 1
    if samples == 0:
        return 0.0
    return visible / samples


def visible_pixmap_fraction(pixmap: QPixmap, step: int = BLANK_SAMPLE_STEP) -> float:
    """
    Returns how much of a pixmap carries visible content.

    Args:
        pixmap: Pixmap to inspect.
        step: Sampling distance in pixels.

    Returns:
        float: Share of visible samples between 0.0 and 1.0.
    """

    if pixmap.isNull():
        return 0.0
    return visible_image_fraction(pixmap.toImage(), step)


def is_blank_image(image: QImage, step: int = BLANK_SAMPLE_STEP) -> bool:
    """
    Detects an image that carries no visible content at all.

    Args:
        image: Image to inspect.
        step: Sampling distance in pixels.

    Returns:
        bool: True when every sample is transparent or (near-)black.
    """

    return visible_image_fraction(image, step) <= 0.0


def is_blank_pixmap(pixmap: QPixmap, step: int = BLANK_SAMPLE_STEP) -> bool:
    """
    Detects a pixmap that carries no visible content at all.

    Args:
        pixmap: Pixmap to inspect.
        step: Sampling distance in pixels.

    Returns:
        bool: True when every sample is transparent or (near-)black.
    """

    return visible_pixmap_fraction(pixmap, step) <= 0.0


def is_suspicious_fraction(fraction: float) -> bool:
    """
    Returns whether a visible-content share is too sparse to trust on its own.

    Args:
        fraction: Visible sample share from ``visible_pixmap_fraction``.

    Returns:
        bool: True when the grab needs a cross-check against another source.
    """

    return fraction < SUSPICIOUS_VISIBLE_FRACTION


def _reset_x11_probe_connection() -> None:
    """
    Drops the cached X11 probe connection.

    Returns:
        None
    """

    global _X11_PROBE_DISPLAY

    if _X11_PROBE_DISPLAY is not None:
        try:
            _X11_PROBE_DISPLAY.close()
        except Exception:
            pass
    _X11_PROBE_DISPLAY = None


def _x11_probe_root():
    """
    Returns the X11 root window used for reference samples.

    Uses python-xlib, which ships with pynput on Linux. It is treated as
    optional: without it the caller falls back to content heuristics.

    Returns:
        object | None: Root window, or None when unavailable.
    """

    global _X11_PROBE_DISPLAY, _X11_PROBE_AVAILABLE

    if not _X11_PROBE_AVAILABLE:
        return None
    if _X11_PROBE_DISPLAY is None:
        try:
            from Xlib import display as xlib_display

            _X11_PROBE_DISPLAY = xlib_display.Display()
        except Exception:
            _X11_PROBE_AVAILABLE = False
            _X11_PROBE_DISPLAY = None
            return None
    try:
        return _X11_PROBE_DISPLAY.screen().root
    except Exception:
        _reset_x11_probe_connection()
        return None


def sample_x11_tile_brightness(x: int, y: int, size: int) -> float | None:
    """
    Reads the mean brightness of one screen tile straight from the X server.

    This is the independent second opinion on what is actually on screen. A
    ``XGetImage`` on a small tile costs well under a millisecond, so it can run
    on every capture -- unlike a full-desktop read through python-xlib, which
    takes seconds.

    Args:
        x: Tile left edge in root coordinates.
        y: Tile top edge in root coordinates.
        size: Tile edge length in pixels.

    Returns:
        float | None: Mean brightness 0-255, or None when the read failed.
    """

    root = _x11_probe_root()
    if root is None:
        return None
    try:
        from Xlib import X

        image = root.get_image(x, y, size, size, X.ZPixmap, 0xFFFFFFFF)
        data = image.data
    except Exception:
        _reset_x11_probe_connection()
        return None
    if isinstance(data, str):
        data = data.encode("latin-1")
    pixels = len(data) // 4
    if pixels <= 0:
        return None
    total = 0
    for index in range(0, pixels * 4, 4):
        total += data[index] + data[index + 1] + data[index + 2]
    return total / (pixels * 3)


def _pixmap_tile_brightness(image: QImage, x: int, y: int, size: int) -> float:
    """
    Returns the mean brightness of one tile inside a grabbed image.

    Args:
        image: Grabbed desktop image.
        x: Tile left edge in image coordinates.
        y: Tile top edge in image coordinates.
        size: Tile edge length in pixels.

    Returns:
        float: Mean brightness 0-255. Fully transparent samples count as black.
    """

    total = 0
    samples = 0
    for offset_y in range(0, size, 4):
        for offset_x in range(0, size, 4):
            point_x = x + offset_x
            point_y = y + offset_y
            if point_x >= image.width() or point_y >= image.height():
                continue
            color = image.pixelColor(point_x, point_y)
            samples += 1
            if color.alpha() == 0:
                continue
            total += (color.red() + color.green() + color.blue()) / 3.0
    if samples == 0:
        return 0.0
    return total / samples


def _probe_points(rect: QRect) -> list[tuple[int, int]]:
    """
    Returns evenly spread probe positions inside one screen rectangle.

    Args:
        rect: Screen rectangle in root coordinates.

    Returns:
        list[tuple[int, int]]: Probe tile origins.
    """

    columns, rows = REFERENCE_TILE_GRID
    points: list[tuple[int, int]] = []
    for row in range(rows):
        for column in range(columns):
            x = rect.x() + int(rect.width() * (column + 0.5) / columns)
            y = rect.y() + int(rect.height() * (row + 0.5) / rows)
            x = min(x, rect.x() + max(0, rect.width() - REFERENCE_TILE_SIZE))
            y = min(y, rect.y() + max(0, rect.height() - REFERENCE_TILE_SIZE))
            points.append((x, y))
    return points


def verify_grab_against_x11(
    pixmap: QPixmap,
    virtual_geometry: QRect,
    screen_rects: list[QRect],
) -> bool | None:
    """
    Checks a grabbed desktop pixmap against the X server.

    Args:
        pixmap: Grabbed virtual desktop image.
        virtual_geometry: Bounding rectangle across all screens.
        screen_rects: Individual screen rectangles.

    Returns:
        bool | None: See ``verify_image_against_x11``.
    """

    if pixmap.isNull():
        return None
    return verify_image_against_x11(pixmap.toImage(), virtual_geometry, screen_rects)


def verify_image_against_x11(
    image: QImage,
    virtual_geometry: QRect,
    screen_rects: list[QRect],
) -> bool | None:
    """
    Checks a grabbed desktop against what the X server reports on screen.

    Content heuristics alone cannot separate a broken grab from a dark desktop,
    and they miss a grab that returns a little content and black everywhere else.
    Comparing tiles against ``XGetImage`` does separate them: only a grab that
    reports black where the X server reports content is broken.

    Args:
        image: Grabbed virtual desktop image.
        virtual_geometry: Bounding rectangle across all screens.
        screen_rects: Individual screen rectangles.

    Returns:
        bool | None: True when the grab matches the screen, False when it
        contradicts it, None when no reference was available.
    """

    if image.isNull() or virtual_geometry.width() <= 0 or virtual_geometry.height() <= 0:
        return None
    if _x11_probe_root() is None:
        return None

    scale = image.width() / virtual_geometry.width() if virtual_geometry.width() else 1.0
    content_tiles = 0
    mismatched_tiles = 0
    for rect in screen_rects or [virtual_geometry]:
        for x, y in _probe_points(rect):
            reference = sample_x11_tile_brightness(x, y, REFERENCE_TILE_SIZE)
            if reference is None:
                return None
            if reference <= REFERENCE_CONTENT_BRIGHTNESS:
                continue
            content_tiles += 1
            grabbed = _pixmap_tile_brightness(
                image,
                int((x - virtual_geometry.x()) * scale),
                int((y - virtual_geometry.y()) * scale),
                max(1, int(REFERENCE_TILE_SIZE * scale)),
            )
            if grabbed <= REFERENCE_BLACK_BRIGHTNESS:
                mismatched_tiles += 1

    if content_tiles < REFERENCE_MIN_CONTENT_TILES:
        # Screen is too dark to judge; the content heuristics decide instead.
        return None
    return (mismatched_tiles / content_tiles) < REFERENCE_MISMATCH_RATIO


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
