"""
Persistence logic for saving a captured screenshot to disk.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

# Placeholders a user can put in the file-name template. Kept small and literal:
# a strftime string would be more powerful but also lets one wrong character
# produce a directory separator or an empty name.
FILENAME_PLACEHOLDERS: dict[str, str] = {
    "{date}": "Date as YYYY-MM-DD",
    "{time}": "Time as HH-MM-SS",
    "{year}": "Year as YYYY",
    "{month}": "Month as MM",
    "{day}": "Day as DD",
    "{counter}": "Number that counts up when the name already exists",
}

DEFAULT_FILENAME_TEMPLATE = "snappix_{date}_{time}"

# Characters no filesystem in scope accepts. Windows is the strictest, so its set
# is applied everywhere -- a capture folder synced between machines otherwise
# produces files that cannot be opened on the other side.
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Names Windows refuses regardless of extension.
_RESERVED_WINDOWS_NAMES = frozenset(
    {
        "CON", "PRN", "AUX", "NUL",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }
)


def sanitize_filename_stem(stem: str) -> str:
    """
    Makes one file-name stem safe on Linux and Windows.

    Args:
        stem: Raw file name without extension.

    Returns:
        str: Sanitized stem, never empty.
    """

    cleaned = _INVALID_FILENAME_CHARS.sub("_", str(stem)).strip()
    # Windows silently drops trailing dots and spaces, which would turn
    # "shot." into "shot" and break an existence check.
    cleaned = cleaned.rstrip(". ")
    if not cleaned:
        return "snappix"
    if cleaned.upper() in _RESERVED_WINDOWS_NAMES:
        return f"{cleaned}_"
    return cleaned[:120]


def format_capture_filename(
    template: str = DEFAULT_FILENAME_TEMPLATE,
    now: datetime | None = None,
    counter: int = 1,
) -> str:
    """
    Builds one PNG file name from a template.

    Args:
        template: Template using the supported placeholders.
        now: Timestamp to encode; defaults to the current time.
        counter: Value for ``{counter}``.

    Returns:
        str: File name including the ``.png`` extension.
    """

    stamp = now or datetime.now()
    text = str(template).strip() or DEFAULT_FILENAME_TEMPLATE
    replacements = {
        "{date}": stamp.strftime("%Y-%m-%d"),
        "{time}": stamp.strftime("%H-%M-%S"),
        "{year}": stamp.strftime("%Y"),
        "{month}": stamp.strftime("%m"),
        "{day}": stamp.strftime("%d"),
        "{counter}": str(counter),
    }
    for placeholder, value in replacements.items():
        text = text.replace(placeholder, value)
    if text.lower().endswith(".png"):
        text = text[:-4]
    return f"{sanitize_filename_stem(text)}.png"


def build_capture_filename(
    now: datetime | None = None,
    template: str = DEFAULT_FILENAME_TEMPLATE,
) -> str:
    """
    Builds a PNG filename for one captured screenshot.

    Args:
        now: Timestamp to encode; defaults to the current time.
        template: Optional file-name template.

    Returns:
        str: File name including the ``.png`` extension.
    """

    return format_capture_filename(template, now)


def resolve_unique_path(
    directory: Path,
    template: str = DEFAULT_FILENAME_TEMPLATE,
    now: datetime | None = None,
) -> Path:
    """
    Returns a path in ``directory`` that does not exist yet.

    Two captures inside the same second, or a template without a time part,
    would otherwise overwrite the previous file.

    Args:
        directory: Target directory.
        template: File-name template.
        now: Timestamp to encode; defaults to the current time.

    Returns:
        Path: Free target path.
    """

    stamp = now or datetime.now()
    candidate = directory / format_capture_filename(template, stamp, counter=1)
    if not candidate.exists():
        return candidate
    for counter in range(2, 10000):
        if "{counter}" in template:
            candidate = directory / format_capture_filename(template, stamp, counter=counter)
        else:
            base = format_capture_filename(template, stamp)[:-4]
            candidate = directory / f"{base}-{counter}.png"
        if not candidate.exists():
            return candidate
    return candidate


def save_capture_pixmap_to_directory(
    pixmap,
    directory: Path,
    template: str = DEFAULT_FILENAME_TEMPLATE,
) -> Path | None:
    """
    Saves one capture pixmap as a PNG inside an existing directory.

    Args:
        pixmap: Captured screenshot pixmap.
        directory: Target directory; must already exist.
        template: File-name template.

    Returns:
        Path | None: Saved file path, or None when the write fails.
    """

    target_path = resolve_unique_path(directory, template)
    if not pixmap.save(str(target_path), "PNG"):
        return None
    return target_path
