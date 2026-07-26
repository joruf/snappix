"""
Python-version compatibility helpers.

Keeps optional language/stdlib features working across supported interpreters
and documents the minimum runtime Snappix supports.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass as _stdlib_dataclass
from dataclasses import field
from pathlib import Path
from typing import Optional, Tuple, Union

__all__ = [
    "MIN_PYTHON",
    "dataclass",
    "field",
    "is_relative_to",
    "is_supported_python",
    "unsupported_python_message",
]

# Matches README / CI: PySide6 6.11.x and pinned deps need 3.11+.
MIN_PYTHON: Tuple[int, int] = (3, 11)

_SUPPORTS_DATACLASS_SLOTS = sys.version_info >= (3, 10)
_SUPPORTS_PATH_IS_RELATIVE_TO = sys.version_info >= (3, 9)


def is_supported_python(
    version_info: Optional[Tuple[int, ...]] = None,
) -> bool:
    """
    Returns whether an interpreter meets Snappix's minimum Python version.

    Args:
        version_info: Version tuple such as ``sys.version_info``. Defaults to
            the current interpreter.

    Returns:
        bool: True when major/minor are at least ``MIN_PYTHON``.
    """

    info = version_info if version_info is not None else sys.version_info
    return info[:2] >= MIN_PYTHON


def unsupported_python_message(
    version_info: Optional[Tuple[int, ...]] = None,
) -> str:
    """
    Builds a user-facing error when the Python version is too old.

    Args:
        version_info: Version tuple such as ``sys.version_info``. Defaults to
            the current interpreter.

    Returns:
        str: Multi-line explanation with install hints.
    """

    info = version_info if version_info is not None else sys.version_info
    current = (
        f"{info[0]}.{info[1]}.{info[2]}"
        if len(info) > 2
        else f"{info[0]}.{info[1]}"
    )
    required = f"{MIN_PYTHON[0]}.{MIN_PYTHON[1]}"
    return (
        f"Snappix requires Python {required}+ to run (found {current}).\n"
        f"Pinned packages such as PySide6==6.11.1 need a modern interpreter.\n\n"
        f"Start Snappix with Snappix.bat (Windows) or ./snappix.sh (Linux) so it "
        f"can download a managed Python {required}+ runtime automatically.\n"
        f"Or install Python {required}+ from https://www.python.org/downloads/ "
        f"and run again."
    )


def dataclass(*args, **kwargs):
    """
    Wraps ``dataclasses.dataclass`` and drops ``slots`` on Python < 3.10.

    On Python 3.10+ behavior matches the standard library, including ``slots``.

    Args:
        *args: Positional arguments forwarded to ``dataclasses.dataclass``.
        **kwargs: Keyword arguments forwarded to ``dataclasses.dataclass``.

    Returns:
        The decorated class, or a decorator awaiting a class.
    """

    if not _SUPPORTS_DATACLASS_SLOTS:
        kwargs.pop("slots", None)
    return _stdlib_dataclass(*args, **kwargs)


def is_relative_to(path: Union[str, Path], other: Union[str, Path]) -> bool:
    """
    Returns whether ``path`` is relative to ``other``.

    Uses ``Path.is_relative_to`` on Python 3.9+ and a ``relative_to`` fallback
    on older interpreters.

    Args:
        path: Candidate path.
        other: Potential parent path.

    Returns:
        bool: True when ``path`` is under ``other``.
    """

    candidate = Path(path)
    base = Path(other)
    if _SUPPORTS_PATH_IS_RELATIVE_TO:
        return candidate.is_relative_to(base)
    try:
        candidate.relative_to(base)
        return True
    except ValueError:
        return False
