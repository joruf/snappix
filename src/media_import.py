"""
Helpers for importing external image and video files into Snappix editors.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPixmap

from src.constants import VIDEO_PROJECT_FILE_EXTENSION
from src.video_recorder import has_ffmpeg

SUPPORTED_IMAGE_SUFFIXES = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}
)
IMAGE_FILE_FILTER = (
    "Images (*.png *.jpg *.jpeg *.gif *.bmp *.webp *.tif *.tiff);;All Files (*)"
)
VIDEO_FILE_FILTER = (
    "Video Files (*.mp4 *.mkv *.webm *.mov *.avi *.m4v);;"
    f"Snappix Video Project (*{VIDEO_PROJECT_FILE_EXTENSION});;All Files (*)"
)
MAX_IMPORTED_VIDEO_DURATION_MS = 5 * 60 * 1000


@dataclass(frozen=True, slots=True)
class VideoFileProbe:
    """
    Describes one importable video file discovered via ffprobe.

    Attributes:
        width: Video width in pixels.
        height: Video height in pixels.
        duration_ms: Video duration in milliseconds.
    """

    width: int
    height: int
    duration_ms: int


def pixmap_has_alpha_channel(pixmap: QPixmap) -> bool:
    """
    Returns whether a pixmap contains any non-opaque pixels.

    Args:
        pixmap: Source pixmap.

    Returns:
        bool: True when alpha transparency is present.
    """

    if pixmap.isNull():
        return False
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    if not image.hasAlphaChannel():
        return False
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha() < 255:
                return True
    return False


def build_import_canvas_background(image: QPixmap) -> QPixmap:
    """
    Builds a document background for one imported image tab.

    PNGs with transparency use a transparent background; opaque images use white.

    Args:
        image: Imported image pixmap.

    Returns:
        QPixmap: Background pixmap sized to the imported image.
    """

    background = QPixmap(image.size())
    if pixmap_has_alpha_channel(image):
        background.fill(Qt.GlobalColor.transparent)
    else:
        background.fill(QColor(255, 255, 255, 255))
    return background


def load_image_pixmap(path: str | Path) -> QPixmap | None:
    """
    Loads one supported image file into a pixmap.

    Args:
        path: Local image file path.

    Returns:
        QPixmap | None: Loaded pixmap or None.
    """

    resolved = Path(path)
    if resolved.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES or not resolved.is_file():
        return None
    pixmap = QPixmap(str(resolved))
    if pixmap.isNull():
        return None
    return pixmap


def validate_import_video_duration(duration_ms: int) -> bool:
    """
    Returns whether one imported video duration is within the allowed limit.

    Args:
        duration_ms: Video duration in milliseconds.

    Returns:
        bool: True when duration is positive and at most five minutes.
    """

    return 0 < duration_ms <= MAX_IMPORTED_VIDEO_DURATION_MS


def probe_video_file(path: str | Path) -> VideoFileProbe | None:
    """
    Reads width, height, and duration for one local video file via ffprobe.

    Args:
        path: Local video file path.

    Returns:
        VideoFileProbe | None: Probe result, or None when probing fails.
    """

    if not has_ffmpeg():
        return None

    resolved = Path(path)
    if not resolved.is_file():
        return None

    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(resolved),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return None

    streams = payload.get("streams") or []
    if not streams:
        return None
    stream = streams[0]
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    if width <= 0 or height <= 0:
        return None

    duration_raw = (payload.get("format") or {}).get("duration")
    try:
        duration_ms = int(float(duration_raw) * 1000)
    except (TypeError, ValueError):
        duration_ms = 0

    return VideoFileProbe(width=width, height=height, duration_ms=max(0, duration_ms))
