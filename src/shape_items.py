"""
Vector annotation path shapes: triangle, star, polygon, callout helpers, and more.
"""

from __future__ import annotations

import math
from typing import Sequence

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem, QStyleOptionGraphicsItem, QWidget

# Rect-like annotation types that store AABB geometry (x, y, width, height).
SHAPE_RECT_TYPES = frozenset(
    {
        "rect",
        "ellipse",
        "triangle",
        "round_rect",
        "star",
        "highlight",
        "spotlight",
        "cross",
        "checkmark",
    }
)

# Line-like annotation types that store start + delta (width/height as dx/dy).
SHAPE_LINE_TYPES = frozenset({"line", "arrow", "double_arrow"})

# Multi-point path annotation types (points stored in payload).
SHAPE_POLY_TYPES = frozenset({"polyline", "polygon", "bent_arrow"})

# Types that use PathShapeItem for paint/geometry (includes legacy round_rect/highlight).
PATH_SHAPE_KINDS = frozenset(
    {
        "rect",
        "triangle",
        "round_rect",
        "star",
        "highlight",
        "cross",
        "checkmark",
    }
)

# Stamp marks painted as filled paths; Border/Fill both drive the visible mark color.
STAMP_MARK_TYPES = frozenset({"cross", "checkmark"})


def build_triangle_path(rect: QRectF) -> QPainterPath:
    """
    Builds an isosceles triangle path inscribed in ``rect``.

    Args:
        rect: Bounding rectangle.

    Returns:
        QPainterPath: Closed triangle path.
    """

    path = QPainterPath()
    if rect.width() < 0.5 or rect.height() < 0.5:
        return path
    top = QPointF(rect.center().x(), rect.top())
    bottom_left = QPointF(rect.left(), rect.bottom())
    bottom_right = QPointF(rect.right(), rect.bottom())
    path.moveTo(top)
    path.lineTo(bottom_right)
    path.lineTo(bottom_left)
    path.closeSubpath()
    return path


def build_rect_path(rect: QRectF, *, corner_radius: float = 0.0) -> QPainterPath:
    """
    Builds a rectangle path, optionally with rounded corners.

    Args:
        rect: Bounding rectangle.
        corner_radius: Corner radius in pixels (0 = sharp corners).

    Returns:
        QPainterPath: Rectangle or rounded-rectangle path.
    """

    path = QPainterPath()
    if rect.width() < 0.5 or rect.height() < 0.5:
        return path
    radius = max(0.0, min(float(corner_radius), min(rect.width(), rect.height()) * 0.5))
    if radius <= 0.01:
        path.addRect(rect)
    else:
        path.addRoundedRect(rect, radius, radius)
    return path


def build_round_rect_path(rect: QRectF, *, radius_ratio: float = 0.22) -> QPainterPath:
    """
    Builds a rounded rectangle path inscribed in ``rect``.

    Args:
        rect: Bounding rectangle.
        radius_ratio: Corner radius as a fraction of the shorter side.

    Returns:
        QPainterPath: Rounded rectangle path.
    """

    path = QPainterPath()
    if rect.width() < 0.5 or rect.height() < 0.5:
        return path
    radius = max(2.0, min(rect.width(), rect.height()) * max(0.0, min(0.5, radius_ratio)))
    path.addRoundedRect(rect, radius, radius)
    return path


def build_star_path(rect: QRectF, *, points: int = 5, inner_ratio: float = 0.45) -> QPainterPath:
    """
    Builds a star polygon path inscribed in ``rect``.

    Args:
        rect: Bounding rectangle.
        points: Number of star tips.
        inner_ratio: Inner radius relative to outer radius.

    Returns:
        QPainterPath: Closed star path.
    """

    path = QPainterPath()
    tip_count = max(3, int(points))
    if rect.width() < 0.5 or rect.height() < 0.5:
        return path
    center = rect.center()
    outer_x = rect.width() * 0.5
    outer_y = rect.height() * 0.5
    inner_x = outer_x * max(0.15, min(0.85, inner_ratio))
    inner_y = outer_y * max(0.15, min(0.85, inner_ratio))
    vertices: list[QPointF] = []
    for index in range(tip_count * 2):
        angle = math.radians(-90.0 + (180.0 / tip_count) * index)
        radius_x = outer_x if index % 2 == 0 else inner_x
        radius_y = outer_y if index % 2 == 0 else inner_y
        vertices.append(
            QPointF(
                center.x() + math.cos(angle) * radius_x,
                center.y() + math.sin(angle) * radius_y,
            )
        )
    path.addPolygon(QPolygonF(vertices))
    path.closeSubpath()
    return path


def build_cross_path(rect: QRectF, *, thickness_ratio: float = 0.22) -> QPainterPath:
    """
    Builds an X / cross mark path inside ``rect``.

    Args:
        rect: Bounding rectangle.
        thickness_ratio: Stroke thickness relative to the shorter side.

    Returns:
        QPainterPath: Cross stroke path (for filling via stroke conversion).
    """

    path = QPainterPath()
    if rect.width() < 0.5 or rect.height() < 0.5:
        return path
    inset = min(rect.width(), rect.height()) * 0.12
    left = rect.left() + inset
    right = rect.right() - inset
    top = rect.top() + inset
    bottom = rect.bottom() - inset
    thickness = max(2.0, min(rect.width(), rect.height()) * thickness_ratio)
    base = QPainterPath()
    base.moveTo(left, top)
    base.lineTo(right, bottom)
    base.moveTo(right, top)
    base.lineTo(left, bottom)
    stroker = QPainterPathStroker()
    stroker.setWidth(thickness)
    stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
    stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return stroker.createStroke(base)


def build_checkmark_path(rect: QRectF, *, thickness_ratio: float = 0.18) -> QPainterPath:
    """
    Builds a checkmark path inside ``rect``.

    Args:
        rect: Bounding rectangle.
        thickness_ratio: Stroke thickness relative to the shorter side.

    Returns:
        QPainterPath: Checkmark stroke path.
    """

    path = QPainterPath()
    if rect.width() < 0.5 or rect.height() < 0.5:
        return path
    thickness = max(2.0, min(rect.width(), rect.height()) * thickness_ratio)
    p1 = QPointF(rect.left() + rect.width() * 0.18, rect.top() + rect.height() * 0.55)
    p2 = QPointF(rect.left() + rect.width() * 0.42, rect.top() + rect.height() * 0.78)
    p3 = QPointF(rect.left() + rect.width() * 0.82, rect.top() + rect.height() * 0.22)
    base = QPainterPath()
    base.moveTo(p1)
    base.lineTo(p2)
    base.lineTo(p3)
    stroker = QPainterPathStroker()
    stroker.setWidth(thickness)
    stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
    stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return stroker.createStroke(base)


def build_points_path(
    points: Sequence[QPointF],
    *,
    closed: bool = False,
) -> QPainterPath:
    """
    Builds an open or closed polyline path from scene-local points.

    Args:
        points: Ordered vertices.
        closed: When True, closes the path into a polygon.

    Returns:
        QPainterPath: Polyline or polygon path.
    """

    path = QPainterPath()
    if not points:
        return path
    path.moveTo(points[0])
    for point in points[1:]:
        path.lineTo(point)
    if closed and len(points) >= 3:
        path.closeSubpath()
    return path


def build_arrow_head(
    tip: QPointF,
    direction: QPointF,
    *,
    size: float,
) -> QPainterPath:
    """
    Builds a filled triangular arrow head at ``tip``.

    Args:
        tip: Arrow tip position.
        direction: Unit direction the arrow points toward (tip direction).
        size: Head size in pixels.

    Returns:
        QPainterPath: Closed arrow-head triangle.
    """

    path = QPainterPath()
    length = math.hypot(direction.x(), direction.y())
    if length < 0.001 or size < 1.0:
        return path
    dx = direction.x() / length
    dy = direction.y() / length
    back_x = -dx
    back_y = -dy
    left = QPointF(
        tip.x()
        + size * (back_x * math.cos(math.radians(30.0)) - back_y * math.sin(math.radians(30.0))),
        tip.y()
        + size * (back_x * math.sin(math.radians(30.0)) + back_y * math.cos(math.radians(30.0))),
    )
    right = QPointF(
        tip.x()
        + size
        * (back_x * math.cos(math.radians(-30.0)) - back_y * math.sin(math.radians(-30.0))),
        tip.y()
        + size
        * (back_x * math.sin(math.radians(-30.0)) + back_y * math.cos(math.radians(-30.0))),
    )
    path.moveTo(tip)
    path.lineTo(left)
    path.lineTo(right)
    path.closeSubpath()
    return path


def path_for_shape_kind(
    kind: str,
    rect: QRectF,
    *,
    corner_radius: float = 0.0,
) -> QPainterPath:
    """
    Builds the vector path for one rect-like shape kind.

    Args:
        kind: Annotation type / shape kind.
        rect: Local bounding rectangle.
        corner_radius: Optional corner radius for ``rect`` shapes.

    Returns:
        QPainterPath: Shape outline/fill path.
    """

    resolved = str(kind or "").strip().lower()
    if resolved == "rect":
        return build_rect_path(rect, corner_radius=corner_radius)
    if resolved == "triangle":
        return build_triangle_path(rect)
    if resolved == "round_rect":
        return build_round_rect_path(rect)
    if resolved == "star":
        return build_star_path(rect)
    if resolved == "highlight":
        return build_round_rect_path(rect, radius_ratio=0.08)
    if resolved == "cross":
        return build_cross_path(rect)
    if resolved == "checkmark":
        return build_checkmark_path(rect)
    return build_rect_path(rect, corner_radius=0.0)


class PathShapeItem(QGraphicsPathItem):
    """
    Rect-bounded vector shape (rectangle, triangle, star, stamps, legacy kinds).
    """

    def __init__(
        self,
        shape_kind: str,
        rect: QRectF | None = None,
        parent: QGraphicsItem | None = None,
        *,
        corner_radius: float = 0.0,
    ) -> None:
        """
        Initializes one path-based shape item.

        Args:
            shape_kind: Annotation type identifier.
            rect: Initial local rectangle.
            parent: Optional parent item.
            corner_radius: Corner radius in pixels for rectangle shapes.
        """

        super().__init__(parent)
        self._shape_kind = str(shape_kind or "triangle").strip().lower()
        self._local_rect = QRectF(rect) if rect is not None else QRectF()
        self._corner_radius = max(0.0, float(corner_radius))
        self._rebuild_path()

    def shape_kind(self) -> str:
        """
        Returns the shape kind identifier.

        Returns:
            str: Annotation type string.
        """

        return self._shape_kind

    def corner_radius(self) -> float:
        """
        Returns the rectangle corner radius.

        Returns:
            float: Corner radius in pixels.
        """

        return self._corner_radius

    def set_corner_radius(self, radius: float) -> None:
        """
        Updates the rectangle corner radius and rebuilds the path.

        Args:
            radius: Corner radius in pixels.

        Returns:
            None
        """

        resolved = max(0.0, float(radius))
        if abs(resolved - self._corner_radius) < 0.001:
            return
        self.prepareGeometryChange()
        self._corner_radius = resolved
        self._rebuild_path()
        self.update()

    def rect(self) -> QRectF:
        """
        Returns the local bounding rectangle.

        Returns:
            QRectF: Local geometry rectangle.
        """

        return QRectF(self._local_rect)

    def setRect(self, rect: QRectF) -> None:
        """
        Updates the local bounding rectangle and rebuilds the path.

        Args:
            rect: New local rectangle.

        Returns:
            None
        """

        self.prepareGeometryChange()
        self._local_rect = QRectF(rect)
        self._rebuild_path()
        self.update()

    def _rebuild_path(self) -> None:
        """
        Rebuilds the painter path from the current rectangle.

        Returns:
            None
        """

        self.setPath(
            path_for_shape_kind(
                self._shape_kind,
                self._local_rect,
                corner_radius=self._corner_radius,
            )
        )


class SpotlightItem(QGraphicsItem):
    """
    Dims the surrounding scene while keeping a rectangular or elliptical focus bright.
    """

    def __init__(
        self,
        focus_rect: QRectF | None = None,
        *,
        focus_mode: str = "ellipse",
        dim_alpha: int = 150,
        parent: QGraphicsItem | None = None,
    ) -> None:
        """
        Initializes one spotlight annotation.

        Args:
            focus_rect: Local bright focus rectangle.
            focus_mode: ``ellipse`` or ``rect`` focus hole.
            dim_alpha: Opacity of the darkened surround (0-255).
            parent: Optional parent item.
        """

        super().__init__(parent)
        self._focus_rect = QRectF(focus_rect) if focus_rect is not None else QRectF()
        mode = str(focus_mode or "ellipse").strip().lower()
        self._focus_mode = mode if mode in {"ellipse", "rect"} else "ellipse"
        self._dim_alpha = max(0, min(255, int(dim_alpha)))
        self._stroke_color = QColor(241, 196, 15, 220)
        self._stroke_width = 2.0
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)

    def rect(self) -> QRectF:
        """
        Returns the local focus rectangle.

        Returns:
            QRectF: Focus geometry.
        """

        return QRectF(self._focus_rect)

    def setRect(self, rect: QRectF) -> None:
        """
        Updates the focus rectangle.

        Args:
            rect: New focus rectangle in item coordinates.

        Returns:
            None
        """

        self.prepareGeometryChange()
        self._focus_rect = QRectF(rect)
        self.update()

    def focus_mode(self) -> str:
        """
        Returns the focus hole mode.

        Returns:
            str: ``ellipse`` or ``rect``.
        """

        return self._focus_mode

    def set_focus_mode(self, mode: str) -> None:
        """
        Updates the focus hole mode.

        Args:
            mode: ``ellipse`` or ``rect``.

        Returns:
            None
        """

        resolved = str(mode or "ellipse").strip().lower()
        if resolved not in {"ellipse", "rect"}:
            resolved = "ellipse"
        if resolved == self._focus_mode:
            return
        self._focus_mode = resolved
        self.update()

    def dim_alpha(self) -> int:
        """
        Returns the dim surround opacity.

        Returns:
            int: Alpha 0-255.
        """

        return self._dim_alpha

    def set_dim_alpha(self, alpha: int) -> None:
        """
        Updates the dim surround opacity.

        Args:
            alpha: Alpha 0-255.

        Returns:
            None
        """

        self._dim_alpha = max(0, min(255, int(alpha)))
        self.update()

    def pen(self) -> QPen:
        """
        Returns the focus outline pen.

        Returns:
            QPen: Outline pen.
        """

        if self._stroke_width <= 0.0:
            pen = QPen(Qt.PenStyle.NoPen)
            pen.setColor(self._stroke_color)
            return pen
        return QPen(self._stroke_color, self._stroke_width)

    def setPen(self, pen: QPen) -> None:
        """
        Updates the focus outline pen.

        Args:
            pen: Outline pen.

        Returns:
            None
        """

        self._stroke_color = QColor(pen.color())
        if pen.style() == Qt.PenStyle.NoPen:
            self._stroke_width = 0.0
        else:
            self._stroke_width = float(pen.widthF())
        self.update()

    def brush(self) -> QBrush:
        """
        Returns a brush representing the dim color (for style serialization).

        Returns:
            QBrush: Dim brush.
        """

        return QBrush(QColor(0, 0, 0, self._dim_alpha))

    def setBrush(self, brush: QBrush | QColor) -> None:
        """
        Updates dim alpha from a brush or solid color when provided.

        Args:
            brush: Source brush or color (palette/style APIs may pass either).

        Returns:
            None
        """

        if isinstance(brush, QColor):
            color = QColor(brush)
        else:
            color = QColor(brush.color())
        if color.alpha() > 0:
            self._dim_alpha = color.alpha()
        self.update()

    def _cover_rect(self) -> QRectF:
        """
        Returns the local dim cover rectangle (scene bounds mapped into item space).

        Avoids ``mapRectFromScene`` because that path can re-enter ``boundingRect``.

        Returns:
            QRectF: Cover rectangle.
        """

        scene = self.scene()
        if scene is None:
            return QRectF(self._focus_rect).adjusted(-40.0, -40.0, 40.0, 40.0)
        scene_rect = scene.sceneRect()
        origin = self.pos()
        return QRectF(
            scene_rect.x() - origin.x(),
            scene_rect.y() - origin.y(),
            scene_rect.width(),
            scene_rect.height(),
        )

    def boundingRect(self) -> QRectF:
        """
        Returns bounds covering the dim overlay and focus.

        Returns:
            QRectF: Item bounds.
        """

        return self._cover_rect().united(self._focus_rect).adjusted(-2.0, -2.0, 2.0, 2.0)

    def shape(self) -> QPainterPath:
        """
        Returns the selectable focus region (not the full dim overlay).

        Returns:
            QPainterPath: Focus hit area.
        """

        path = QPainterPath()
        if self._focus_mode == "rect":
            path.addRect(self._focus_rect)
        else:
            path.addEllipse(self._focus_rect)
        return path

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """
        Paints the dim surround with a bright focus hole.

        Args:
            painter: Active painter.
            option: Style options from Qt.
            widget: Optional widget being painted.

        Returns:
            None
        """

        cover = self._cover_rect()
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.OddEvenFill)
        path.addRect(cover)
        if self._focus_mode == "rect":
            path.addRect(self._focus_rect)
        else:
            path.addEllipse(self._focus_rect)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, self._dim_alpha)))
        painter.drawPath(path)
        focus_pen = self.pen()
        if focus_pen.style() != Qt.PenStyle.NoPen:
            painter.setPen(focus_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if self._focus_mode == "rect":
                painter.drawRect(self._focus_rect)
            else:
                painter.drawEllipse(self._focus_rect)


class PolyPathItem(QGraphicsPathItem):
    """
    Multi-point polyline, polygon, or bent arrow annotation.
    """

    HIT_PADDING = 8.0

    def __init__(
        self,
        shape_kind: str,
        points: Sequence[QPointF] | None = None,
        parent: QGraphicsItem | None = None,
    ) -> None:
        """
        Initializes one multi-point path annotation.

        Args:
            shape_kind: ``polyline``, ``polygon``, or ``bent_arrow``.
            points: Initial vertices in item-local coordinates.
            parent: Optional parent item.
        """

        super().__init__(parent)
        kind = str(shape_kind or "polyline").strip().lower()
        self._shape_kind = kind if kind in SHAPE_POLY_TYPES else "polyline"
        self._points: list[QPointF] = [QPointF(point) for point in (points or [])]
        self._rebuild_path()

    def shape_kind(self) -> str:
        """
        Returns the poly path kind.

        Returns:
            str: Annotation type string.
        """

        return self._shape_kind

    def points(self) -> list[QPointF]:
        """
        Returns a copy of the local vertices.

        Returns:
            list[QPointF]: Vertex list.
        """

        return [QPointF(point) for point in self._points]

    def set_points(self, points: Sequence[QPointF]) -> None:
        """
        Replaces all vertices and rebuilds the path.

        Args:
            points: New vertices in item-local coordinates.

        Returns:
            None
        """

        self.prepareGeometryChange()
        self._points = [QPointF(point) for point in points]
        self._rebuild_path()
        self.update()

    def _rebuild_path(self) -> None:
        """
        Rebuilds the displayed path from vertices.

        Returns:
            None
        """

        closed = self._shape_kind == "polygon"
        path = build_points_path(self._points, closed=closed)
        if self._shape_kind == "bent_arrow" and len(self._points) >= 2:
            tip = self._points[-1]
            previous = self._points[-2]
            direction = QPointF(tip.x() - previous.x(), tip.y() - previous.y())
            size = max(8.0, float(self.pen().widthF()) * 3.0)
            path.addPath(build_arrow_head(tip, direction, size=size))
        self.setPath(path)

    def shape(self) -> QPainterPath:
        """
        Returns a thickened clickable stroke around the path.

        Returns:
            QPainterPath: Hit-test geometry.
        """

        base = QPainterPath(self.path())
        if self._shape_kind == "polygon":
            return base
        stroker = QPainterPathStroker()
        stroker.setWidth(max(float(self.pen().widthF()), 1.0) + (self.HIT_PADDING * 2.0))
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return stroker.createStroke(base)

    def setPen(self, pen: QPen) -> None:
        """
        Updates the stroke pen and rebuilds arrow heads when needed.

        Args:
            pen: New pen.

        Returns:
            None
        """

        super().setPen(pen)
        if self._shape_kind == "bent_arrow":
            self._rebuild_path()


def points_to_payload(points: Sequence[QPointF]) -> list[list[float]]:
    """
    Serializes path points for annotation payloads.

    Args:
        points: Vertex list.

    Returns:
        list[list[float]]: ``[[x, y], ...]`` payload fragment.
    """

    return [[float(point.x()), float(point.y())] for point in points]


def points_from_payload(payload: dict | None) -> list[QPointF]:
    """
    Restores path points from an annotation payload.

    Args:
        payload: Annotation payload dictionary.

    Returns:
        list[QPointF]: Restored vertices.
    """

    source = payload if isinstance(payload, dict) else {}
    raw = source.get("points")
    if not isinstance(raw, list):
        return []
    points: list[QPointF] = []
    for entry in raw:
        if not isinstance(entry, (list, tuple)) or len(entry) < 2:
            continue
        points.append(QPointF(float(entry[0]), float(entry[1])))
    return points


def bounding_rect_from_points(points: Sequence[QPointF]) -> QRectF:
    """
    Computes the axis-aligned bounds of a point list.

    Args:
        points: Vertex list.

    Returns:
        QRectF: Bounds, or an empty rect when fewer than one point.
    """

    if not points:
        return QRectF()
    xs = [point.x() for point in points]
    ys = [point.y() for point in points]
    left = min(xs)
    top = min(ys)
    return QRectF(left, top, max(1.0, max(xs) - left), max(1.0, max(ys) - top))
