"""
Editable screenshot canvas for SnapAgent.
"""

from __future__ import annotations

import base64
from typing import Any

import requests
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QContextMenuEvent,
    QGuiApplication,
    QImage,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QInputDialog,
    QMenu,
)

from src.annotation_items import (
    ArrowItem,
    ITEM_ROLE_TYPE,
    StyleState,
    add_annotation_to_scene,
    annotation_from_item,
    color_to_list,
    configure_graphics_item,
)
from src.crop_item import CropSelectionItem
from src.models import AnnotationModel


def decode_base64_to_pixmap(value: str) -> QPixmap:
    """
    Decodes Base64 PNG data to a pixmap.

    Args:
        value: Base64 encoded PNG bytes.

    Returns:
        QPixmap: Decoded pixmap.
    """

    data = base64.b64decode(value.encode("utf-8"))
    image = QImage()
    image.loadFromData(data, "PNG")
    return QPixmap.fromImage(image)


def encode_pixmap_to_base64(pixmap: QPixmap) -> str:
    """
    Encodes a pixmap to Base64 PNG data.

    Args:
        pixmap: Source pixmap.

    Returns:
        str: Base64 encoded PNG data.
    """

    byte_array = QByteArray()
    buffer = QBuffer(byte_array)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    return bytes(byte_array.toBase64()).decode("utf-8")


class Tool:
    """
    Defines all available editor tools.
    """

    SELECT = "select"
    RECT = "rect"
    ELLIPSE = "ellipse"
    LINE = "line"
    ARROW = "arrow"
    TEXT = "text"
    CROP = "crop"
    FILL_BG = "fill_bg"


class EditorCanvas(QGraphicsView):
    """
    Interactive graphics canvas for screenshot annotations.
    """

    content_changed = Signal()
    zoom_changed = Signal(float)
    selection_style_changed = Signal(dict)
    crop_selection_changed = Signal(bool)
    crop_applied = Signal()

    def __init__(self) -> None:
        """
        Initializes the canvas view and graphics scene.
        """

        super().__init__()
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
            | QPainter.RenderHint.TextAntialiasing
        )
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

        self._tool = Tool.SELECT
        self._style = StyleState(
            stroke_color=QColor(231, 76, 60, 255),
            fill_color=QColor(231, 76, 60, 80),
            text_color=QColor(44, 62, 80, 255),
            stroke_width=3.0,
            font_size=16,
            font_family="Sans Serif",
        )
        self._zoom_factor = 1.0
        self._initial_view_pending = False
        self._start_scene_pos = QPointF()
        self._preview_item: QGraphicsItem | None = None
        self._crop_item: CropSelectionItem | None = None
        self._crop_shade_item: QGraphicsPathItem | None = None
        self._resize_overlay_item: CropSelectionItem | None = None
        self._resize_overlay_target: QGraphicsItem | None = None
        self._updating_resize_overlay = False

        self._background_item = QGraphicsPixmapItem()
        self._background_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._background_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self._background_item.setZValue(-1000)
        self._scene.addItem(self._background_item)

        self._scene.selectionChanged.connect(self._on_selection_changed)

    def screenshot(self) -> QPixmap:
        """
        Returns the current screenshot pixmap.

        Returns:
            QPixmap: Screenshot pixmap.
        """

        return self._background_item.pixmap()

    def set_screenshot(self, pixmap: QPixmap) -> None:
        """
        Sets the screenshot pixmap used as canvas background.

        Args:
            pixmap: New screenshot image.

        Returns:
            None
        """

        self._background_item.setPixmap(pixmap)
        self._background_item.setPos(0, 0)
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        self._initial_view_pending = True
        QTimer.singleShot(0, self._apply_initial_screenshot_view)

    def resizeEvent(self, event) -> None:
        """
        Applies pending initial screenshot scaling after viewport resize.

        Args:
            event: Qt resize event.

        Returns:
            None
        """

        super().resizeEvent(event)
        if self._initial_view_pending:
            self._apply_initial_screenshot_view()

    def _apply_initial_screenshot_view(self) -> None:
        """
        Shows screenshot at original size unless it is wider than viewport.

        Returns:
            None
        """

        screenshot = self.screenshot()
        if screenshot.isNull():
            self._initial_view_pending = False
            self._zoom_factor = 1.0
            self.zoom_changed.emit(self._zoom_factor)
            return

        viewport_width = self.viewport().width()
        if viewport_width <= 1:
            return

        self.resetTransform()
        if screenshot.width() > viewport_width:
            zoom_factor = viewport_width / float(screenshot.width())
            self.scale(zoom_factor, zoom_factor)
            self._zoom_factor = zoom_factor
        else:
            self._zoom_factor = 1.0
        self.centerOn(self._background_item)
        self._initial_view_pending = False
        self.zoom_changed.emit(self._zoom_factor)

    def set_tool(self, tool: str) -> None:
        """
        Activates a drawing tool.

        Args:
            tool: Tool identifier.

        Returns:
            None
        """

        if self._tool == Tool.CROP and tool != Tool.CROP:
            self.cancel_crop()
        self._tool = tool
        if tool == Tool.SELECT:
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        else:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
        if tool == Tool.CROP and not self.has_pending_crop():
            self._create_default_crop_selection()

    def set_style(
        self,
        stroke_color: QColor | None = None,
        fill_color: QColor | None = None,
        text_color: QColor | None = None,
        stroke_width: float | None = None,
        font_size: int | None = None,
        font_family: str | None = None,
    ) -> None:
        """
        Updates active style options and selected item style.

        Args:
            stroke_color: Optional new stroke color.
            fill_color: Optional new fill color.
            stroke_width: Optional new stroke width.
            font_size: Optional new font size.

        Returns:
            None
        """

        if stroke_color is not None:
            self._style.stroke_color = stroke_color
        if fill_color is not None:
            self._style.fill_color = fill_color
        if stroke_width is not None:
            self._style.stroke_width = stroke_width
        if font_size is not None:
            self._style.font_size = font_size
        if text_color is not None:
            self._style.text_color = text_color
        if font_family is not None and font_family.strip():
            self._style.font_family = font_family.strip()

        changed = False
        for item in self._scene.selectedItems():
            annotation_type = str(item.data(ITEM_ROLE_TYPE) or "")
            if annotation_type in {"rect", "ellipse"}:
                shape_item = item
                if stroke_color is not None:
                    pen = shape_item.pen()
                    pen.setColor(stroke_color)
                    shape_item.setPen(pen)
                if fill_color is not None:
                    shape_item.setBrush(fill_color)
                if stroke_width is not None:
                    pen = shape_item.pen()
                    pen.setWidthF(stroke_width)
                    shape_item.setPen(pen)
                changed = True
            elif annotation_type in {"line", "arrow"}:
                line_item = item
                pen = line_item.pen()
                if stroke_color is not None:
                    pen.setColor(stroke_color)
                if stroke_width is not None:
                    pen.setWidthF(stroke_width)
                line_item.setPen(pen)
                changed = True
            elif annotation_type == "text":
                text_item = item
                if text_color is not None:
                    text_item.setDefaultTextColor(text_color)
                elif stroke_color is not None:
                    text_item.setDefaultTextColor(stroke_color)
                if font_size is not None:
                    font = text_item.font()
                    font.setPointSize(font_size)
                    text_item.setFont(font)
                if font_family is not None and font_family.strip():
                    font = text_item.font()
                    font.setFamily(font_family.strip())
                    text_item.setFont(font)
                changed = True
        if changed:
            self.content_changed.emit()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """
        Handles drawing start and text insertion actions.

        Args:
            event: Mouse press event.

        Returns:
            None
        """

        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        if self._try_select_item_with_ctrl(event):
            return

        scene_pos = self.mapToScene(event.position().toPoint())
        self._start_scene_pos = scene_pos

        if self._tool == Tool.TEXT:
            text, accepted = QInputDialog.getText(self, "Insert Text", "Text:")
            if accepted and text:
                item = self._scene.addText(text)
                item.setDefaultTextColor(self._style.text_color)
                font = item.font()
                font.setPointSize(self._style.font_size)
                font.setFamily(self._style.font_family)
                item.setFont(font)
                item.setPos(scene_pos)
                item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
                configure_graphics_item(item, "text")
                self.content_changed.emit()
            return

        if self._tool in {Tool.RECT, Tool.ELLIPSE, Tool.LINE, Tool.ARROW}:
            self._clear_resize_overlay()
            self._preview_item = self._create_preview_item(scene_pos)
            if self._preview_item is not None:
                self._scene.addItem(self._preview_item)
            return
        if self._tool == Tool.FILL_BG:
            self._clear_resize_overlay()
            self._preview_item = self._create_preview_item(scene_pos)
            if self._preview_item is not None:
                self._scene.addItem(self._preview_item)
            return
        if self._tool == Tool.CROP:
            self._clear_resize_overlay()
            if self.has_pending_crop():
                super().mousePressEvent(event)
                return
            self._preview_item = self._create_preview_item(scene_pos)
            if self._preview_item is not None:
                self._scene.addItem(self._preview_item)
            return

        super().mousePressEvent(event)

    def _try_select_item_with_ctrl(self, event: QMouseEvent) -> bool:
        """
        Selects an item on Ctrl+click while preserving the current tool.

        Args:
            event: Mouse press event.

        Returns:
            bool: True when selection was handled.
        """

        if event.button() != Qt.MouseButton.LeftButton:
            return False
        if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            return False

        hit_item = self.itemAt(event.position().toPoint())
        if hit_item is None:
            return False
        if hit_item in {
            self._background_item,
            self._crop_shade_item,
            self._resize_overlay_item,
        }:
            return False
        if not (hit_item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable):
            return False

        self._scene.clearSelection()
        hit_item.setSelected(True)
        self._scene.setFocusItem(hit_item)
        event.accept()
        return True

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """
        Updates the preview item while drawing.

        Args:
            event: Mouse move event.

        Returns:
            None
        """

        if self._preview_item is not None:
            current = self.mapToScene(event.position().toPoint())
            self._update_preview_item(self._start_scene_pos, current)
            return
        self._sync_resize_overlay_with_target()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """
        Finalizes the current draw action and stores history state.

        Args:
            event: Mouse release event.

        Returns:
            None
        """

        if event.button() == Qt.MouseButton.LeftButton and self._preview_item is not None:
            if self._tool == Tool.CROP:
                crop_rect = self._preview_item.boundingRect().translated(self._preview_item.pos())
                self._scene.removeItem(self._preview_item)
                self._preview_item = None
                if crop_rect.width() > 2 and crop_rect.height() > 2:
                    self._crop_item = CropSelectionItem(crop_rect)
                    self._crop_item.on_geometry_changed = self._update_crop_shade
                    self._scene.addItem(self._crop_item)
                    self._crop_item.setSelected(True)
                    self._ensure_crop_shade_item()
                    self._update_crop_shade()
                    self.crop_selection_changed.emit(True)
                return
            if self._tool == Tool.FILL_BG:
                fill_rect = self._preview_item.boundingRect().translated(self._preview_item.pos())
                self._scene.removeItem(self._preview_item)
                self._preview_item = None
                self._apply_background_fill(fill_rect)
                return

            configure_graphics_item(self._preview_item, self._tool)
            self._preview_item = None
            self.content_changed.emit()
            return
        super().mouseReleaseEvent(event)
        self._sync_resize_overlay_with_target()

    def wheelEvent(self, event) -> None:
        """
        Applies Ctrl+mousewheel zoom behavior.

        Args:
            event: Wheel event.

        Returns:
            None
        """

        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
            return
        super().wheelEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """
        Shows context menu with paste action.

        Args:
            event: Context menu event.

        Returns:
            None
        """

        menu = QMenu(self)
        paste_action = QAction("Paste", self)
        paste_action.setShortcut(QKeySequence.StandardKey.Paste)
        paste_action.triggered.connect(lambda: self.paste_from_clipboard(event.pos()))
        menu.addAction(paste_action)
        if self._scene.selectedItems():
            menu.addSeparator()
            grow_action = QAction("Increase Element Size", self)
            grow_action.triggered.connect(lambda: self.resize_selected_items(1.1))
            menu.addAction(grow_action)
            shrink_action = QAction("Decrease Element Size", self)
            shrink_action.triggered.connect(lambda: self.resize_selected_items(0.9))
            menu.addAction(shrink_action)
        if self.has_pending_crop():
            apply_crop_action = QAction("Apply Crop", self)
            apply_crop_action.triggered.connect(self.apply_pending_crop)
            menu.addAction(apply_crop_action)
            cancel_crop_action = QAction("Cancel Crop", self)
            cancel_crop_action.triggered.connect(self.cancel_crop)
            menu.addAction(cancel_crop_action)
        menu.exec(event.globalPos())

    def zoom_in(self) -> None:
        """
        Zooms into the canvas.

        Returns:
            None
        """

        self._apply_zoom(1.1)

    def zoom_out(self) -> None:
        """
        Zooms out of the canvas.

        Returns:
            None
        """

        self._apply_zoom(1.0 / 1.1)

    def reset_zoom(self) -> None:
        """
        Resets zoom to default fit level.

        Returns:
            None
        """

        self.resetTransform()
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom_factor = 1.0
        self.zoom_changed.emit(self._zoom_factor)

    def set_zoom_factor(self, target_zoom: float) -> None:
        """
        Sets zoom to an absolute factor value.

        Args:
            target_zoom: Target zoom factor (1.0 = 100%).

        Returns:
            None
        """

        bounded_zoom = max(0.1, min(8.0, target_zoom))
        if abs(bounded_zoom - self._zoom_factor) < 0.0001:
            return
        scale_factor = bounded_zoom / self._zoom_factor
        self.scale(scale_factor, scale_factor)
        self._zoom_factor = bounded_zoom
        self.zoom_changed.emit(self._zoom_factor)

    def _apply_zoom(self, factor: float) -> None:
        """
        Applies a multiplicative zoom factor.

        Args:
            factor: Scale factor.

        Returns:
            None
        """

        new_zoom = self._zoom_factor * factor
        if new_zoom < 0.1 or new_zoom > 8.0:
            return
        self.scale(factor, factor)
        self._zoom_factor = new_zoom
        self.zoom_changed.emit(self._zoom_factor)

    def _create_preview_item(self, start: QPointF) -> QGraphicsItem:
        """
        Creates a temporary preview item for the active draw tool.

        Args:
            start: Start point in scene coordinates.

        Returns:
            QGraphicsItem: Preview item instance.
        """

        pen = QPen(self._style.stroke_color, self._style.stroke_width)
        if self._tool == Tool.RECT:
            item = QGraphicsRectItem(QRectF(start, start))
            item.setPen(pen)
            item.setBrush(self._style.fill_color)
            return item
        if self._tool == Tool.ELLIPSE:
            item = QGraphicsEllipseItem(QRectF(start, start))
            item.setPen(pen)
            item.setBrush(self._style.fill_color)
            return item
        if self._tool == Tool.LINE:
            item = QGraphicsLineItem(start.x(), start.y(), start.x(), start.y())
            item.setPen(pen)
            return item
        if self._tool == Tool.ARROW:
            item = ArrowItem(start.x(), start.y(), start.x(), start.y())
            item.setPen(pen)
            return item
        if self._tool == Tool.CROP:
            crop_pen = QPen(QColor(52, 152, 219, 220), 2.0, Qt.PenStyle.DashLine)
            item = QGraphicsRectItem(QRectF(start, start))
            item.setPen(crop_pen)
            item.setBrush(QColor(52, 152, 219, 50))
            return item
        if self._tool == Tool.FILL_BG:
            fill_pen = QPen(QColor(255, 255, 255, 180), 1.5, Qt.PenStyle.DashLine)
            item = QGraphicsRectItem(QRectF(start, start))
            item.setPen(fill_pen)
            item.setBrush(QColor(self._style.fill_color.red(), self._style.fill_color.green(), self._style.fill_color.blue(), 90))
            return item
        return QGraphicsRectItem(QRectF(start, start))

    def _update_preview_item(self, start: QPointF, current: QPointF) -> None:
        """
        Updates preview geometry between start and current points.

        Args:
            start: Start point.
            current: Current mouse position.

        Returns:
            None
        """

        if self._preview_item is None:
            return
        rect = QRectF(start, current).normalized()
        if isinstance(self._preview_item, (QGraphicsRectItem, QGraphicsEllipseItem)):
            self._preview_item.setRect(rect)
            return
        if isinstance(self._preview_item, QGraphicsLineItem):
            self._preview_item.setLine(start.x(), start.y(), current.x(), current.y())

    def _apply_crop(self, crop_rect: QRectF) -> None:
        """
        Crops the current screenshot and annotations to the chosen rectangle.

        Args:
            crop_rect: Selected crop rectangle in scene coordinates.

        Returns:
            None
        """

        crop_rect = crop_rect.normalized()
        if crop_rect.width() < 2 or crop_rect.height() < 2:
            return

        crop_item_was_visible = False
        crop_shade_was_visible = False
        if self._crop_item is not None:
            crop_item_was_visible = self._crop_item.isVisible()
            self._crop_item.setVisible(False)
        if self._crop_shade_item is not None:
            crop_shade_was_visible = self._crop_shade_item.isVisible()
            self._crop_shade_item.setVisible(False)

        flattened = self.export_composited_pixmap()

        if self._crop_item is not None:
            self._crop_item.setVisible(crop_item_was_visible)
        if self._crop_shade_item is not None:
            self._crop_shade_item.setVisible(crop_shade_was_visible)

        crop_rect_int = crop_rect.toAlignedRect()
        background_color = self._background_base_color()
        expanded = QImage(crop_rect_int.size(), QImage.Format.Format_ARGB32)
        expanded.fill(background_color)
        painter = QPainter(expanded)
        source_offset_x = -crop_rect_int.x()
        source_offset_y = -crop_rect_int.y()
        painter.drawPixmap(source_offset_x, source_offset_y, flattened)
        painter.end()
        cropped = QPixmap.fromImage(expanded)
        self.cancel_crop()
        self.clear_annotations()
        self.set_screenshot(cropped)
        self.content_changed.emit()

    def has_pending_crop(self) -> bool:
        """
        Indicates whether an editable crop selection is active.

        Returns:
            bool: True when a crop selection exists.
        """

        return self._crop_item is not None and self._crop_item.scene() is self._scene

    def apply_pending_crop(self) -> None:
        """
        Applies current crop selection and removes the crop frame.

        Returns:
            None
        """

        if not self.has_pending_crop():
            return
        crop_rect = self._crop_item.scene_rect()
        self._apply_crop(crop_rect)
        self.crop_applied.emit()

    def cancel_crop(self) -> None:
        """
        Removes active crop selection without changing the image.

        Returns:
            None
        """

        if self._crop_item is not None and self._crop_item.scene() is self._scene:
            self._scene.removeItem(self._crop_item)
        self._crop_item = None
        self._remove_crop_shade_item()
        self._clear_resize_overlay()
        self.crop_selection_changed.emit(False)

    def clear_annotations(self) -> None:
        """
        Removes all annotation items from the scene.

        Returns:
            None
        """

        for item in self._scene.items():
            if item is self._background_item:
                continue
            self._scene.removeItem(item)
        self._crop_item = None
        self._remove_crop_shade_item()
        self._clear_resize_overlay()
        self.crop_selection_changed.emit(False)

    def collect_annotations(self) -> list[AnnotationModel]:
        """
        Serializes all current annotation items.

        Returns:
            list[AnnotationModel]: Serialized annotations.
        """

        models: list[AnnotationModel] = []
        for item in self._scene.items():
            if item is self._background_item:
                continue
            if item is self._crop_item:
                continue
            if item is self._crop_shade_item:
                continue
            if item is self._resize_overlay_item:
                continue
            annotation = annotation_from_item(item)
            if annotation is not None:
                models.append(annotation)
        models.reverse()
        return models

    def load_annotations(self, models: list[AnnotationModel]) -> None:
        """
        Clears and rebuilds annotation items from models.

        Args:
            models: Annotation list.

        Returns:
            None
        """

        self.clear_annotations()
        for model in models:
            add_annotation_to_scene(self._scene, model)

    def export_composited_pixmap(self) -> QPixmap:
        """
        Renders screenshot and all annotations into a single pixmap.

        Returns:
            QPixmap: Composited output.
        """

        rect = self._scene.sceneRect().toRect()
        resize_overlay_was_visible = False
        if self._resize_overlay_item is not None:
            resize_overlay_was_visible = self._resize_overlay_item.isVisible()
            self._resize_overlay_item.setVisible(False)
        image = QImage(rect.size(), QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        self._scene.render(painter, QRectF(image.rect()), QRectF(rect))
        painter.end()
        if self._resize_overlay_item is not None:
            self._resize_overlay_item.setVisible(resize_overlay_was_visible)
        return QPixmap.fromImage(image)

    def paste_from_clipboard(self, view_pos: QPoint | None = None) -> None:
        """
        Pastes text, image, or image URL from clipboard.

        Args:
            view_pos: Optional view coordinate for insertion.

        Returns:
            None
        """

        clipboard = QGuiApplication.clipboard()
        mime = clipboard.mimeData()
        scene_pos = (
            self.mapToScene(view_pos) if view_pos is not None else self.mapToScene(self.viewport().rect().center())
        )

        if mime.hasImage():
            image = clipboard.image()
            pixmap = QPixmap.fromImage(image)
            self._insert_image_pixmap(pixmap, scene_pos)
            return

        if mime.hasText():
            text = mime.text().strip()
            if text.lower().startswith(("http://", "https://")) and self._try_paste_image_url(text, scene_pos):
                return
            if text:
                text_item = self._scene.addText(text)
                text_item.setDefaultTextColor(self._style.text_color)
                font = text_item.font()
                font.setPointSize(self._style.font_size)
                font.setFamily(self._style.font_family)
                text_item.setFont(font)
                text_item.setPos(scene_pos)
                text_item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
                configure_graphics_item(text_item, "text")
                self.content_changed.emit()

    def keyPressEvent(self, event) -> None:
        """
        Handles Ctrl+V clipboard paste shortcut.

        Args:
            event: Key event.

        Returns:
            None
        """

        if event.matches(QKeySequence.StandardKey.Paste):
            self.paste_from_clipboard()
            return
        if (
            event.modifiers() & Qt.KeyboardModifier.ControlModifier
            and event.key() in {Qt.Key.Key_Plus, Qt.Key.Key_Equal}
        ):
            if self.resize_selected_items(1.1):
                return
        if (
            event.modifiers() & Qt.KeyboardModifier.ControlModifier
            and event.key() in {Qt.Key.Key_Minus, Qt.Key.Key_Underscore}
        ):
            if self.resize_selected_items(0.9):
                return
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter} and self.has_pending_crop():
            self.apply_pending_crop()
            return
        if event.key() == Qt.Key.Key_Escape and self.has_pending_crop():
            self.cancel_crop()
            return
        if event.key() == Qt.Key.Key_Delete:
            if self.has_pending_crop() and self._crop_item is not None and self._crop_item.isSelected():
                self.cancel_crop()
                return
            removed = False
            for item in list(self._scene.selectedItems()):
                if item is self._background_item:
                    continue
                if item is self._crop_item:
                    self.cancel_crop()
                    removed = True
                    continue
                self._scene.removeItem(item)
                removed = True
            if removed:
                self.content_changed.emit()
            return
        super().keyPressEvent(event)

    def resize_selected_items(self, scale_factor: float) -> bool:
        """
        Resizes currently selected annotations by a scale factor.

        Args:
            scale_factor: Multiplicative resize factor.

        Returns:
            bool: True when at least one item was resized.
        """

        if scale_factor <= 0:
            return False
        changed = False
        for item in self._scene.selectedItems():
            if item in {
                self._background_item,
                self._crop_item,
                self._crop_shade_item,
                self._resize_overlay_item,
            }:
                continue
            if self._resize_item_geometry(item, scale_factor):
                changed = True
        if changed:
            self._sync_resize_overlay_with_target()
            self.content_changed.emit()
        return changed

    def _resize_item_geometry(self, item: QGraphicsItem, scale_factor: float) -> bool:
        """
        Applies geometry-based resize to one annotation item.

        Args:
            item: Selected annotation item.
            scale_factor: Multiplicative resize factor.

        Returns:
            bool: True when the item geometry changed.
        """

        annotation_type = str(item.data(ITEM_ROLE_TYPE) or "")
        min_size = 2.0

        if annotation_type in {"rect", "ellipse"}:
            shape_item = item
            rect = shape_item.rect()
            center = rect.center()
            new_width = max(min_size, rect.width() * scale_factor)
            new_height = max(min_size, rect.height() * scale_factor)
            shape_item.setRect(
                QRectF(
                    center.x() - (new_width / 2.0),
                    center.y() - (new_height / 2.0),
                    new_width,
                    new_height,
                )
            )
            return True

        if annotation_type in {"line", "arrow"}:
            line_item = item
            line = line_item.line()
            center = QPointF(
                (line.p1().x() + line.p2().x()) / 2.0,
                (line.p1().y() + line.p2().y()) / 2.0,
            )
            p1 = QPointF(
                center.x() + (line.p1().x() - center.x()) * scale_factor,
                center.y() + (line.p1().y() - center.y()) * scale_factor,
            )
            p2 = QPointF(
                center.x() + (line.p2().x() - center.x()) * scale_factor,
                center.y() + (line.p2().y() - center.y()) * scale_factor,
            )
            line_item.setLine(p1.x(), p1.y(), p2.x(), p2.y())
            return True

        if annotation_type == "text":
            text_item = item
            font = text_item.font()
            point_size = font.pointSize()
            if point_size <= 0:
                point_size = 16
            font.setPointSize(max(1, int(round(point_size * scale_factor))))
            text_item.setFont(font)
            return True

        if annotation_type == "image":
            image_item = item
            pixmap = image_item.pixmap()
            if pixmap.width() <= 0:
                return False
            image_item.setScale(max(0.05, image_item.scale() * scale_factor))
            return True

        return False

    def _background_base_color(self) -> QColor:
        """
        Derives a base background color from the screenshot.

        Returns:
            QColor: Sampled background color.
        """

        screenshot = self.screenshot()
        if screenshot.isNull():
            return QColor(255, 255, 255, 255)
        image = screenshot.toImage()
        if image.isNull():
            return QColor(255, 255, 255, 255)
        return image.pixelColor(0, 0)

    def _apply_background_fill(self, rect: QRectF) -> None:
        """
        Applies selected fill color to a rectangular screenshot area.

        Args:
            rect: Target area in scene coordinates.

        Returns:
            None
        """

        clipped = rect.intersected(self._scene.sceneRect()).normalized()
        if clipped.width() < 1 or clipped.height() < 1:
            return
        screenshot = self.screenshot()
        if screenshot.isNull():
            return
        image = screenshot.toImage()
        painter = QPainter(image)
        painter.fillRect(clipped.toAlignedRect(), self._style.fill_color)
        painter.end()
        self._background_item.setPixmap(QPixmap.fromImage(image))
        self.content_changed.emit()

    def _try_paste_image_url(self, url: str, scene_pos: QPointF) -> bool:
        """
        Downloads an image from URL and inserts it on success.

        Args:
            url: Clipboard URL.
            scene_pos: Insert position.

        Returns:
            bool: True when pasted as image.
        """

        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
        except Exception:
            return False

        image = QImage()
        if not image.loadFromData(response.content):
            return False
        self._insert_image_pixmap(QPixmap.fromImage(image), scene_pos)
        return True

    def _insert_image_pixmap(self, pixmap: QPixmap, scene_pos: QPointF) -> None:
        """
        Inserts a pasted image as movable annotation.

        Args:
            pixmap: Pasted pixmap.
            scene_pos: Item position.

        Returns:
            None
        """

        item = QGraphicsPixmapItem(pixmap)
        item.setPos(scene_pos)
        configure_graphics_item(item, "image")
        item.setData(2001, encode_pixmap_to_base64(pixmap))
        self._scene.addItem(item)
        self.content_changed.emit()

    def _on_selection_changed(self) -> None:
        """
        Emits style details of the first selected item.

        Returns:
            None
        """

        selected = self._scene.selectedItems()
        if not selected:
            self._clear_resize_overlay()
            return
        item = selected[0]
        if item in {self._crop_item, self._crop_shade_item, self._resize_overlay_item}:
            self._clear_resize_overlay()
            return
        if len(selected) == 1 and self._can_resize_item(item):
            self._sync_resize_overlay_with_target(item)
        else:
            self._clear_resize_overlay()
        annotation_type = str(item.data(ITEM_ROLE_TYPE) or "")
        payload: dict[str, Any] = {"type": annotation_type}
        if annotation_type in {"rect", "ellipse"}:
            payload["stroke_rgba"] = color_to_list(item.pen().color())
            payload["fill_rgba"] = color_to_list(item.brush().color())
            payload["stroke_width"] = item.pen().widthF()
        elif annotation_type in {"line", "arrow"}:
            payload["stroke_rgba"] = color_to_list(item.pen().color())
            payload["stroke_width"] = item.pen().widthF()
        elif annotation_type == "text":
            payload["stroke_rgba"] = color_to_list(item.defaultTextColor())
            payload["text_rgba"] = color_to_list(item.defaultTextColor())
            payload["font_size"] = item.font().pointSize()
            payload["font_family"] = item.font().family()
        elif annotation_type == "image":
            payload["stroke_width"] = 0.0
        self.selection_style_changed.emit(payload)

    def _can_resize_item(self, item: QGraphicsItem) -> bool:
        """
        Checks whether an annotation type supports interactive resize.

        Args:
            item: Scene item to evaluate.

        Returns:
            bool: True if resize handles should be shown.
        """

        annotation_type = str(item.data(ITEM_ROLE_TYPE) or "")
        return annotation_type in {"rect", "ellipse", "line", "arrow", "text", "image"}

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

    def _target_geometry_rect(self, item: QGraphicsItem) -> QRectF:
        """
        Returns geometry bounds for one annotation without pen inflation artifacts.

        Args:
            item: Scene item.

        Returns:
            QRectF: Geometry rectangle in scene coordinates.
        """

        annotation_type = str(item.data(ITEM_ROLE_TYPE) or "")
        if annotation_type in {"rect", "ellipse"}:
            return item.mapRectToScene(item.rect()).normalized()
        if annotation_type in {"line", "arrow"}:
            line = item.line()
            p1 = item.mapToScene(line.p1())
            p2 = item.mapToScene(line.p2())
            return QRectF(p1, p2).normalized()
        return item.sceneBoundingRect().normalized()

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
        if self._resize_overlay_item is None:
            overlay = CropSelectionItem(target_rect)
            overlay.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            overlay.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, False)
            overlay.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            overlay.set_always_show_handles(True)
            overlay.on_geometry_changed = self._apply_resize_overlay_to_target
            overlay.setZValue(1400)
            self._scene.addItem(overlay)
            self._resize_overlay_item = overlay
        else:
            self._updating_resize_overlay = True
            self._resize_overlay_item.setPos(target_rect.topLeft())
            self._resize_overlay_item.setRect(
                QRectF(0.0, 0.0, target_rect.width(), target_rect.height())
            )
            self._updating_resize_overlay = False
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

    def _apply_resize_overlay_to_target(self) -> None:
        """
        Applies resize-handle geometry changes back to selected target item.

        Returns:
            None
        """

        if self._updating_resize_overlay:
            return
        if self._resize_overlay_item is None or self._resize_overlay_target is None:
            return
        target = self._resize_overlay_target
        if target.scene() is not self._scene:
            self._clear_resize_overlay()
            return

        old_rect = self._target_geometry_rect(target)
        new_rect = self._resize_overlay_item.scene_rect().normalized()
        if new_rect.width() < 2 or new_rect.height() < 2:
            return

        if not self._resize_target_to_rect(target, old_rect, new_rect):
            return
        self.content_changed.emit()

    def _resize_target_to_rect(
        self,
        target: QGraphicsItem,
        old_rect: QRectF,
        new_rect: QRectF,
    ) -> bool:
        """
        Resizes one target annotation to a new scene-space rectangle.

        Args:
            target: Target annotation item.
            old_rect: Previous scene-space item rectangle.
            new_rect: New scene-space item rectangle from overlay.

        Returns:
            bool: True when resize was applied.
        """

        annotation_type = str(target.data(ITEM_ROLE_TYPE) or "")

        if annotation_type in {"rect", "ellipse"}:
            target.setPos(new_rect.topLeft())
            target.setRect(QRectF(0.0, 0.0, new_rect.width(), new_rect.height()))
            return True

        if annotation_type in {"line", "arrow"}:
            line = target.line()
            p1_scene = target.mapToScene(line.p1())
            p2_scene = target.mapToScene(line.p2())
            old_width = max(0.0001, old_rect.width())
            old_height = max(0.0001, old_rect.height())
            old_width_is_degenerate = old_rect.width() < 0.0002
            old_height_is_degenerate = old_rect.height() < 0.0002

            def map_point(point: QPointF) -> QPointF:
                if old_width_is_degenerate:
                    ratio_x = 0.5
                else:
                    ratio_x = (point.x() - old_rect.x()) / old_width
                if old_height_is_degenerate:
                    ratio_y = 0.5
                else:
                    ratio_y = (point.y() - old_rect.y()) / old_height
                return QPointF(
                    new_rect.x() + (new_rect.width() * ratio_x),
                    new_rect.y() + (new_rect.height() * ratio_y),
                )

            mapped_p1 = map_point(p1_scene)
            mapped_p2 = map_point(p2_scene)
            target.setPos(0.0, 0.0)
            target.setLine(
                mapped_p1.x(),
                mapped_p1.y(),
                mapped_p2.x(),
                mapped_p2.y(),
            )
            return True

        if annotation_type == "text":
            font = target.font()
            point_size = font.pointSize()
            if point_size <= 0:
                point_size = 16
            scale_x = new_rect.width() / max(0.0001, old_rect.width())
            scale_y = new_rect.height() / max(0.0001, old_rect.height())
            scale = max(0.1, (scale_x + scale_y) / 2.0)
            font.setPointSize(max(1, int(round(point_size * scale))))
            target.setFont(font)
            target.setPos(new_rect.topLeft())
            return True

        if annotation_type == "image":
            pixmap = target.pixmap()
            if pixmap.width() <= 0:
                return False
            target.setPos(new_rect.topLeft())
            target.setScale(new_rect.width() / float(pixmap.width()))
            return True

        return False

    def _ensure_crop_shade_item(self) -> None:
        """
        Creates a semi-transparent crop outside mask if missing.

        Returns:
            None
        """

        if self._crop_shade_item is not None:
            return
        self._crop_shade_item = QGraphicsPathItem()
        self._crop_shade_item.setZValue(900)
        self._crop_shade_item.setPen(QPen(Qt.PenStyle.NoPen))
        self._crop_shade_item.setBrush(QColor(20, 20, 20, 110))
        self._crop_shade_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._crop_shade_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self._scene.addItem(self._crop_shade_item)
        if self._crop_item is not None:
            self._crop_item.setZValue(901)

    def _remove_crop_shade_item(self) -> None:
        """
        Removes the crop outside mask item.

        Returns:
            None
        """

        if self._crop_shade_item is None:
            return
        self._scene.removeItem(self._crop_shade_item)
        self._crop_shade_item = None

    def _update_crop_shade(self) -> None:
        """
        Updates the crop outside mask path to current crop rect.

        Returns:
            None
        """

        if self._crop_item is None or self._crop_shade_item is None:
            return
        outer = QRectF(self._scene.sceneRect())
        inner = self._crop_item.scene_rect().normalized()
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.OddEvenFill)
        path.addRect(outer)
        path.addRect(inner)
        self._crop_shade_item.setPath(path)

    def _create_default_crop_selection(self) -> None:
        """
        Creates default crop selection immediately after crop tool activation.

        Returns:
            None
        """

        rect = QRectF(self._scene.sceneRect())
        self._crop_item = CropSelectionItem(rect)
        self._crop_item.on_geometry_changed = self._update_crop_shade
        self._scene.addItem(self._crop_item)
        self._crop_item.setSelected(True)
        self._ensure_crop_shade_item()
        self._update_crop_shade()
        self.crop_selection_changed.emit(True)

