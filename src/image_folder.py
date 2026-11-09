"""
The other images in the folder of the one being looked at.

Browsing a folder with the arrow keys needs two answers: which files count as
images, and which of them comes before or after the current one. Names are
ordered the way a file manager shows them -- case ignored, numbers by value --
so ``img2.png`` comes before ``img10.png`` rather than after it.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.file_association import IMAGE_SUFFIXES

_DIGITS = re.compile(r"(\d+)")


def natural_key(name: str) -> tuple:
    """
    Builds a sort key that orders numbers inside a name by their value.

    Args:
        name: File name.

    Returns:
        tuple: Key for ``sorted``; text and numbers never compare with each other.
    """

    parts = _DIGITS.split(name.casefold())
    return tuple((0, int(part), "") if part.isdigit() else (1, 0, part) for part in parts)


def images_in_folder(path: str | Path) -> list[Path]:
    """
    Lists the images next to a file, in the order a file manager would.

    Args:
        path: Any file in the folder; the folder is its parent.

    Returns:
        list[Path]: Image files of that folder, including the file itself when
        it is one. Empty when the folder cannot be read.
    """

    folder = Path(path).resolve().parent
    try:
        entries = [
            entry
            for entry in folder.iterdir()
            if entry.suffix.lower() in IMAGE_SUFFIXES and entry.is_file()
        ]
    except OSError:
        return []
    return sorted(entries, key=lambda entry: (natural_key(entry.name), entry.name))


def neighbours(path: str | Path, step: int) -> list[Path]:
    """
    Lists the images after (or before) a file, nearest first, wrapping around.

    The result runs through every other image once, so a caller that cannot
    open the nearest one can simply try the next.

    Args:
        path: The current image.
        step: ``1`` for the images that follow, ``-1`` for the ones before.

    Returns:
        list[Path]: Other images in the folder, nearest first. Empty when the
        current image is the only one.
    """

    current = Path(path).resolve()
    images = images_in_folder(current)
    if current not in images:
        # The file is gone or is no image: there is no place in the order.
        return []
    index = images.index(current)
    count = len(images)
    direction = 1 if step >= 0 else -1
    return [images[(index + direction * offset) % count] for offset in range(1, count)]
