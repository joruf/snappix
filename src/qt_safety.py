"""
Keeps Python exceptions from unwinding through Qt's C++ stack.

Qt calls a graphics item's ``boundingRect``, ``shape``, ``paint``, and
``itemChange`` from inside its own render and event loops. When a Python
override raises, PySide has no valid value to hand back to C++ and the process
dies -- the crash log for that failure mode reads:

    AttributeError: Error calling Python override of QGraphicsRectItem::boundingRect()
    ...
    Fatal Python error: Segmentation fault

The bug that triggers it is usually small and local (a wrong setter on the wrong
item class, a stale reference), but the consequence is the whole editor and the
user's unsaved work. Wrapping those overrides converts that class of failure into
a logged, survivable glitch: the item may draw wrong for one frame instead of
taking the application down, and the traceback lands in the crash log where it
can be fixed.

This is a safety net, not a licence to ignore errors -- every catch is recorded.
"""

from __future__ import annotations

import functools
from typing import Any, Callable

# Every distinct override reports once per session. Qt calls boundingRect() for
# every repaint, so an unguarded log would write thousands of identical blocks
# and bury the first, most useful one.
_REPORTED: set[str] = set()


def reset_reported_overrides() -> None:
    """
    Clears the "already reported" set.

    Returns:
        None
    """

    _REPORTED.clear()


def reported_override_failures() -> frozenset[str]:
    """
    Returns the overrides that failed in this session.

    Returns:
        frozenset[str]: Keys of the form ``ClassName.method``.
    """

    return frozenset(_REPORTED)


def _report(key: str) -> None:
    """
    Records one override failure in the crash log, once per session.

    Args:
        key: Identifier of the failing override.

    Returns:
        None
    """

    if key in _REPORTED:
        return
    _REPORTED.add(key)
    try:
        from src.crash_log import log_exception

        log_exception(f"Qt override failed: {key}")
    except Exception:
        # Reporting must never be the reason the override fails.
        pass


def safe_qt_override(fallback: Callable[..., Any]) -> Callable:
    """
    Wraps a Qt virtual override so an exception cannot reach C++.

    Args:
        fallback: Called with the same arguments as the override to produce a
            usable return value when it raises. ``itemChange`` passes the
            incoming value straight through, geometry getters return an empty
            shape, and painters return None.

    Returns:
        Callable: Decorator for the override.
    """

    def decorate(function: Callable) -> Callable:
        @functools.wraps(function)
        def wrapper(self, *args, **kwargs):
            try:
                return function(self, *args, **kwargs)
            except Exception:
                _report(f"{type(self).__name__}.{function.__name__}")
                return fallback(self, *args, **kwargs)

        return wrapper

    return decorate


def _empty_rect(_self, *_args, **_kwargs):
    """
    Returns an empty rectangle for a failed geometry override.

    Returns:
        QRectF: Empty rectangle.
    """

    from PySide6.QtCore import QRectF

    return QRectF()


def _empty_path(_self, *_args, **_kwargs):
    """
    Returns an empty painter path for a failed shape override.

    Returns:
        QPainterPath: Empty path.
    """

    from PySide6.QtGui import QPainterPath

    return QPainterPath()


def _nothing(*_args, **_kwargs) -> None:
    """
    Returns None for a failed paint override.

    Returns:
        None
    """

    return None


def _passthrough_value(_self, _change, value, *_args, **_kwargs):
    """
    Returns ``itemChange``'s incoming value unchanged.

    Args:
        _self: Item the override belongs to.
        _change: Qt change enum.
        value: Value Qt passed in.

    Returns:
        object: The unchanged value, which is what Qt expects on no-op.
    """

    return value


safe_bounding_rect = safe_qt_override(_empty_rect)
safe_shape = safe_qt_override(_empty_path)
safe_paint = safe_qt_override(_nothing)
safe_item_change = safe_qt_override(_passthrough_value)
