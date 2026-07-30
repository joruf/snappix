"""
Renders drawn annotation items into a standalone transparent image.

Used when copying objects so the system clipboard carries a real picture
alongside Snappix's own JSON payload, which lets the copied object be pasted
into any other application.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem

# Breathing room around the drawn bounds so wide strokes and arrow heads are
# never clipped by rounding.
RENDER_MARGIN_PX = 2
# Guard against a pathological selection producing a gigantic allocation.
MAX_RENDER_EDGE_PX = 8000


def render_items_to_image(
    items: list[QGraphicsItem],
    *,
    margin_px: int = RENDER_MARGIN_PX,
) -> QImage | None:
    """
    Draws graphics items onto a transparent image cropped to their bounds.

    Items are painted through their scene transform, so rotation, scaling, and
    flips are preserved. Selection handles are not drawn: each item receives a
    fresh, unstyled option.

    Args:
        items: Graphics items to render. Empty renders nothing.
        margin_px: Transparent padding added on every side.

    Returns:
        QImage | None: Rendered image, or None when there is nothing to draw
        or the bounds are degenerate.
    """

    if not items:
        return None

    bounds = QRectF()
    for item in items:
        bounds = bounds.united(item.sceneBoundingRect())
    if bounds.isEmpty():
        return None

    margin = max(0, int(margin_px))
    bounds = bounds.adjusted(-margin, -margin, margin, margin)
    width = max(1, int(math.ceil(bounds.width())))
    height = max(1, int(math.ceil(bounds.height())))
    if width > MAX_RENDER_EDGE_PX or height > MAX_RENDER_EDGE_PX:
        return None

    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.translate(-bounds.x(), -bounds.y())
    option = QStyleOptionGraphicsItem()
    for item in items:
        painter.save()
        painter.setTransform(item.sceneTransform(), True)
        item.paint(painter, option, None)
        painter.restore()
    painter.end()

    return image
