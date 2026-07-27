"""
Persistence logic for saving a captured screenshot to disk.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def build_capture_filename(now: datetime | None = None) -> str:
    """
    Builds a timestamped PNG filename for one captured screenshot.

    Args:
        now: Timestamp to encode; defaults to the current time.

    Returns:
        str: Filename in the ``snappix_YYYY-MM-DD_HH-MM-SS.png`` shape.
    """

    return (now or datetime.now()).strftime("snappix_%Y-%m-%d_%H-%M-%S.png")


def save_capture_pixmap_to_directory(pixmap, directory: Path) -> Path | None:
    """
    Saves one capture pixmap as a timestamped PNG inside an existing directory.

    Args:
        pixmap: Captured screenshot pixmap.
        directory: Target directory; must already exist.

    Returns:
        Path | None: Saved file path, or None when the write fails.
    """

    target_path = directory / build_capture_filename()
    if not pixmap.save(str(target_path), "PNG"):
        return None
    return target_path
