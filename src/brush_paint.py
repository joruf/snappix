"""
Soft brush and eraser painting helpers for the editor canvas.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QRadialGradient


def clamp_hardness(hardness: float) -> float:
    """
    Clamps brush hardness to the inclusive 0–100 range.

    Args:
        hardness: Raw hardness percentage.

    Returns:
        float: Hardness in [0, 100].
    """

    return max(0.0, min(100.0, float(hardness)))


def paint_soft_brush_segment(
    image: QImage,
    start: QPointF,
    end: QPointF,
    *,
    radius: float,
    color: QColor,
    hardness: float,
    erase: bool = False,
    clip_region=None,
) -> bool:
    """
    Paints one soft brush or eraser segment onto an ARGB image.

    A solid core (sized by hardness) keeps strokes visible; the outer ring uses
    a soft radial falloff.

    Args:
        image: Target image (modified in place).
        start: Segment start in image pixel coordinates.
        end: Segment end in image pixel coordinates.
        radius: Brush radius in image pixels.
        color: Brush color including alpha (opacity). Ignored for erase alpha
            except that color.alpha() drives erase strength.
        hardness: Softness control from 0 (very soft) to 100 (hard edge).
        erase: True to erase with DestinationOut; False to paint SourceOver.
        clip_region: Optional QRegion clip for selection-limited painting.

    Returns:
        bool: True when any stamp was drawn.
    """

    if image.isNull() or radius < 0.25:
        return False

    resolved_hardness = clamp_hardness(hardness) / 100.0
    stamp = _build_soft_stamp(radius, color, resolved_hardness, erase=erase)
    if stamp.isNull():
        return False

    spacing = max(0.4, radius * 0.32)
    points = _sample_segment_points(start, end, spacing)
    painter = QPainter(image)
    if not painter.isActive():
        return False
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    if clip_region is not None:
        painter.setClipRegion(clip_region)
    if erase:
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
    else:
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    half = stamp.width() / 2.0
    drawn = False
    for point in points:
        painter.drawImage(QPointF(point.x() - half, point.y() - half), stamp)
        drawn = True

    # Guaranteed solid core so thin/soft strokes remain visible.
    core_radius = max(0.6, radius * max(0.35, resolved_hardness))
    if erase:
        core_color = QColor(255, 255, 255, max(0, min(255, color.alpha())))
    else:
        core_color = QColor(color)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(core_color)
    painter.drawEllipse(start, core_radius, core_radius)
    painter.drawEllipse(end, core_radius, core_radius)
    if start != end:
        pen = QPen(core_color, core_radius * 2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(start, end)
    painter.end()
    return drawn


def _sample_segment_points(start: QPointF, end: QPointF, spacing: float) -> list[QPointF]:
    """
    Samples stamp centers along a segment including both endpoints.

    Args:
        start: Segment start.
        end: Segment end.
        spacing: Maximum distance between consecutive stamps.

    Returns:
        list[QPointF]: Stamp center positions.
    """

    dx = end.x() - start.x()
    dy = end.y() - start.y()
    distance = math.hypot(dx, dy)
    if distance < 0.001:
        return [QPointF(start)]

    count = max(1, int(math.ceil(distance / max(0.1, spacing))))
    points: list[QPointF] = []
    for index in range(count + 1):
        t = index / count
        points.append(QPointF(start.x() + dx * t, start.y() + dy * t))
    return points


def _build_soft_stamp(
    radius: float,
    color: QColor,
    hardness: float,
    *,
    erase: bool,
) -> QImage:
    """
    Builds a circular soft stamp image with a radial alpha falloff.

    Args:
        radius: Brush radius in pixels.
        color: Source color (RGB used for paint; alpha for strength).
        hardness: Normalized hardness in [0, 1].
        erase: True when stamp alpha drives DestinationOut erasure.

    Returns:
        QImage: ARGB stamp image.
    """

    size = max(3, int(math.ceil(radius * 2.0)) + 3)
    stamp = QImage(size, size, QImage.Format.Format_ARGB32)
    stamp.fill(Qt.GlobalColor.transparent)

    center = size / 2.0
    gradient = QRadialGradient(center, center, max(0.5, radius))
    strength = max(0, min(255, color.alpha()))
    inner_stop = max(0.0, min(0.92, hardness * 0.88))
    if erase:
        core = QColor(255, 255, 255, strength)
        edge = QColor(255, 255, 255, 0)
    else:
        core = QColor(color.red(), color.green(), color.blue(), strength)
        edge = QColor(color.red(), color.green(), color.blue(), 0)
    gradient.setColorAt(0.0, core)
    gradient.setColorAt(inner_stop, core)
    gradient.setColorAt(1.0, edge)

    painter = QPainter(stamp)
    if not painter.isActive():
        return stamp
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    painter.drawEllipse(QPointF(center, center), radius, radius)
    painter.end()
    return stamp
