"""
Small stateless QRectF helpers shared across the image and video canvases.
"""

from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import QRectF


def union_rect(rects: Iterable[QRectF]) -> QRectF:
    """
    Returns the union bounding rectangle of zero or more rectangles.

    Args:
        rects: Rectangles to combine.

    Returns:
        QRectF: Union bounds, or a null rectangle when given no rectangles.
    """

    bounds = QRectF()
    for rect in rects:
        bounds = rect if bounds.isNull() else bounds.united(rect)
    return bounds
