"""Geometry helpers for overlay rectangles."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF


def normalize_rect(start: QPointF, end: QPointF) -> QRectF:
    """Create a normalized rectangle from two points.

    :param start: First point.
    :param end: Second point.
    :return: Normalized rectangle in scene coordinates.
    """
    return QRectF(start, end).normalized()


def compute_resized_scene_rect(
    left: float,
    top: float,
    right: float,
    bottom: float,
    handle: str,
    scene_x: float,
    scene_y: float,
    min_size: float,
) -> QRectF:
    """Compute a resized scene rectangle while preserving opposite anchor edges.

    :param left: Current left edge in scene coordinates.
    :param top: Current top edge in scene coordinates.
    :param right: Current right edge in scene coordinates.
    :param bottom: Current bottom edge in scene coordinates.
    :param handle: Active resize handle identifier.
    :param scene_x: Current pointer X coordinate in scene space.
    :param scene_y: Current pointer Y coordinate in scene space.
    :param min_size: Minimum allowed width and height.
    :return: Resized rectangle in scene coordinates.
    """
    if handle in {"top_left", "left", "bottom_left"}:
        left = scene_x
    if handle in {"top_right", "right", "bottom_right"}:
        right = scene_x
    if handle in {"top_left", "top", "top_right"}:
        top = scene_y
    if handle in {"bottom_left", "bottom", "bottom_right"}:
        bottom = scene_y

    if handle in {"top_left", "left", "bottom_left"}:
        if right - left < min_size:
            left = right - min_size
    if handle in {"top_right", "right", "bottom_right"}:
        if right - left < min_size:
            right = left + min_size
    if handle in {"top_left", "top", "top_right"}:
        if bottom - top < min_size:
            top = bottom - min_size
    if handle in {"bottom_left", "bottom", "bottom_right"}:
        if bottom - top < min_size:
            bottom = top + min_size

    return QRectF(QPointF(left, top), QPointF(right, bottom)).normalized()
