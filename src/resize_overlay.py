"""
Shared interactive resize-handle overlay management for the image and video canvases.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtWidgets import QGraphicsItem, QGraphicsLineItem

from src.annotation_items import ITEM_ROLE_TYPE
from src.crop_item import (
    FRAME_MODE_ELLIPSE,
    FRAME_MODE_LINE,
    FRAME_MODE_RECT,
    CropSelectionItem,
)
from src.shape_items import SHAPE_LINE_TYPES, SHAPE_RECT_TYPES


def rect_or_line_geometry_rect(item: QGraphicsItem) -> QRectF | None:
    """
    Returns the scene-space geometry rectangle for a rect/line-shaped item.

    Args:
        item: Scene item to evaluate.

    Returns:
        QRectF | None: Geometry rectangle, or None when the item is neither a
        rect-family nor a line-family annotation.
    """

    annotation_type = str(item.data(ITEM_ROLE_TYPE) or "")
    if annotation_type in SHAPE_RECT_TYPES:
        return item.mapRectToScene(item.rect()).normalized()
    if annotation_type in SHAPE_LINE_TYPES:
        line = item.line()
        p1 = item.mapToScene(line.p1())
        p2 = item.mapToScene(line.p2())
        return QRectF(p1, p2).normalized()
    return None


def overlay_frame_mode_for_item(item: QGraphicsItem) -> str:
    """
    Resolves the selection-overlay frame mode for one annotation.

    Args:
        item: Selected annotation item.

    Returns:
        str: ``ellipse``, ``line``, or ``rect``.
    """

    annotation_type = str(item.data(ITEM_ROLE_TYPE) or "")
    if annotation_type == "ellipse":
        return FRAME_MODE_ELLIPSE
    if annotation_type in SHAPE_LINE_TYPES:
        return FRAME_MODE_LINE
    return FRAME_MODE_RECT


def line_scene_endpoints(item: QGraphicsItem) -> tuple[QPointF, QPointF] | None:
    """
    Returns scene-space endpoints for a line-family annotation.

    Args:
        item: Annotation item.

    Returns:
        tuple[QPointF, QPointF] | None: Endpoints, or None when not a line item.
    """

    annotation_type = str(item.data(ITEM_ROLE_TYPE) or "")
    if annotation_type not in SHAPE_LINE_TYPES:
        return None
    if not isinstance(item, QGraphicsLineItem):
        return None
    line = item.line()
    return item.mapToScene(line.p1()), item.mapToScene(line.p2())


class ResizeOverlayMixin:
    """
    Manages the shared CropSelectionItem used as interactive resize handles.

    Host classes must provide ``self._scene``, ``self._resize_overlay_item``,
    ``self._resize_overlay_target``, ``self._updating_resize_overlay``,
    ``self._resize_handle_size``, ``self._resize_handle_position``, plus
    ``_can_resize_item()`` and ``_target_geometry_rect()``. The overlay's
    move/interior-click behavior and any extra teardown are host-specific, so
    hosts override ``_resize_overlay_is_movable()``,
    ``_resize_overlay_interior_interactive()``, and ``_on_resize_overlay_cleared()``.
    """

    def _can_resize_item(self, item: QGraphicsItem) -> bool:
        """
        Checks whether one annotation supports interactive resize handles.

        Args:
            item: Scene item to evaluate.

        Returns:
            bool: True when resize handles should be shown.
        """

        raise NotImplementedError

    def _target_geometry_rect(self, item: QGraphicsItem) -> QRectF:
        """
        Returns geometry bounds for one annotation without pen inflation artifacts.

        Args:
            item: Scene item.

        Returns:
            QRectF: Geometry rectangle in scene coordinates.
        """

        raise NotImplementedError

    def _resize_overlay_is_movable(self, target: QGraphicsItem) -> bool:
        """
        Indicates whether the resize-overlay box itself can be dragged to move
        the target annotation.

        Args:
            target: Annotation the overlay is attached to.

        Returns:
            bool: True when the overlay should be movable.
        """

        raise NotImplementedError

    def _resize_overlay_interior_interactive(self, target: QGraphicsItem) -> bool:
        """
        Indicates whether clicks inside the overlay should pass through to the
        target item instead of being handled by the overlay itself.

        Args:
            target: Annotation the overlay is attached to.

        Returns:
            bool: True when the overlay interior should stay interactive.
        """

        raise NotImplementedError

    def _on_resize_overlay_cleared(self) -> None:
        """
        Runs extra teardown after the resize overlay is removed; no-op unless overridden.

        Returns:
            None
        """

        return

    def _item_scene_rect(self, item: QGraphicsItem) -> QRectF:
        """
        Returns a normalized scene-space geometry rectangle for one item.

        Args:
            item: Scene item.

        Returns:
            QRectF: Normalized scene rectangle.
        """

        rect = self._target_geometry_rect(item).normalized()
        if rect.width() < 2:
            rect.setWidth(2)
        if rect.height() < 2:
            rect.setHeight(2)
        return rect

    def _apply_resize_handle_style(self, overlay: CropSelectionItem) -> None:
        """
        Applies the current resize-handle settings to one overlay item.

        Args:
            overlay: Selection overlay item.

        Returns:
            None
        """

        overlay.set_handle_style(
            size=self._resize_handle_size,
            position=self._resize_handle_position,
        )

    def set_resize_handle_style(self, *, size: float, position: str) -> None:
        """
        Configures resize-overlay handle size and placement.

        Args:
            size: Handle edge length in pixels.
            position: One of ``center``, ``inside``, or ``outside``.

        Returns:
            None
        """

        from src.config import normalize_resize_handle_position, normalize_resize_handle_size

        self._resize_handle_size = float(normalize_resize_handle_size(size))
        self._resize_handle_position = normalize_resize_handle_position(position)
        if self._resize_overlay_item is not None:
            self._resize_overlay_item.set_handle_style(
                size=self._resize_handle_size,
                position=self._resize_handle_position,
            )

    def _sync_resize_overlay_with_target(self, target: QGraphicsItem | None = None) -> None:
        """
        Aligns interactive resize handles to the current selected target item.

        Args:
            target: Optional explicit selected item.

        Returns:
            None
        """

        if self._updating_resize_overlay:
            return
        if target is None:
            selected = self._scene.selectedItems()
            if len(selected) != 1:
                self._clear_resize_overlay()
                return
            target = selected[0]
        if not self._can_resize_item(target):
            self._clear_resize_overlay()
            return

        target_rect = self._item_scene_rect(target)
        frame_mode = overlay_frame_mode_for_item(target)
        interior_interactive = self._resize_overlay_interior_interactive(target)
        if frame_mode == FRAME_MODE_LINE:
            interior_interactive = False
        if self._resize_overlay_item is None:
            overlay = CropSelectionItem(target_rect)
            overlay.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            overlay.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, False)
            overlay.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable,
                self._resize_overlay_is_movable(target) and frame_mode != FRAME_MODE_LINE,
            )
            overlay.set_always_show_handles(True)
            overlay.set_aspect_ratio_lock_enabled(True)
            overlay.set_frame_mode(frame_mode)
            overlay.set_interior_interactive(interior_interactive)
            if frame_mode == FRAME_MODE_LINE:
                endpoints = line_scene_endpoints(target)
                if endpoints is not None:
                    overlay.set_line_endpoints(endpoints[0], endpoints[1])
            overlay.on_geometry_changed = self._apply_resize_overlay_to_target
            overlay.setZValue(1400)
            self._scene.addItem(overlay)
            self._resize_overlay_item = overlay
        else:
            self._updating_resize_overlay = True
            self._resize_overlay_item.set_frame_mode(frame_mode)
            self._resize_overlay_item.set_interior_interactive(interior_interactive)
            self._resize_overlay_item.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable,
                self._resize_overlay_is_movable(target) and frame_mode != FRAME_MODE_LINE,
            )
            if frame_mode == FRAME_MODE_LINE:
                endpoints = line_scene_endpoints(target)
                if endpoints is not None:
                    self._resize_overlay_item.set_line_endpoints(endpoints[0], endpoints[1])
            else:
                self._resize_overlay_item.setPos(target_rect.topLeft())
                self._resize_overlay_item.setRect(
                    QRectF(0.0, 0.0, target_rect.width(), target_rect.height())
                )
            self._updating_resize_overlay = False
        self._apply_resize_handle_style(self._resize_overlay_item)
        self._resize_overlay_target = target

    def _clear_resize_overlay(self) -> None:
        """
        Removes interactive resize handles from the scene.

        Returns:
            None
        """

        if self._resize_overlay_item is not None and self._resize_overlay_item.scene() is self._scene:
            self._scene.removeItem(self._resize_overlay_item)
        self._resize_overlay_item = None
        self._resize_overlay_target = None
        self._on_resize_overlay_cleared()
