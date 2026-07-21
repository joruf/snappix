"""
Editable screenshot canvas for SnapAgent.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import requests
from PySide6.QtCore import (
    QByteArray,
    QBuffer,
    QIODevice,
    QPoint,
    QPointF,
    QRectF,
    Qt,
    QTimer,
    Signal,
    QLineF,
    QUrl,
)
from PySide6.QtGui import (
    QAction,
    QBrush,
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
    QTransform,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QLabel,
    QMenu,
    QTextEdit,
    QVBoxLayout,
)

from src.annotation_items import (
    ArrowItem,
    ITEM_ROLE_TYPE,
    STROKE_STYLE_DASH,
    STROKE_STYLE_DASH_DOT,
    STROKE_STYLE_DOT,
    STROKE_STYLE_SOLID,
    StyleState,
    add_annotation_to_scene,
    annotation_from_item,
    color_to_list,
    configure_graphics_item,
    create_pen,
    normalize_stroke_style,
    stroke_style_to_qt,
)
from src.annotation_items import _stroke_style_from_pen as stroke_style_from_pen
from src.annotation_shapes import (
    StepBadgeItem,
    StyledTextItem,
    TEXT_STYLE_BOX,
    TEXT_STYLE_BUBBLE,
    TEXT_STYLE_PLAIN,
)
from src.crop_item import CropSelectionItem
from src.image_effects import pixelate_qimage_region
from src.models import AnnotationModel
from src.ocr import extract_text_from_png_bytes
from src.scroll_capture import pixmap_to_png_bytes
from src.theme import THEME_LIGHT, current_theme_name, get_theme_colors, normalize_theme_name

_WORKSPACE_MARGIN_MIN = 96.0
_WORKSPACE_MARGIN_RATIO = 0.15
_DOCUMENT_SHADOW_OFFSET = 4.0
_DOCUMENT_MATTE_COLOR = "#ffffff"
_CLIPBOARD_IMAGE_SUFFIXES = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}
)


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
    BLUR = "blur"
    STEP = "step"
    OCR = "ocr"


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
        self.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        )
        self.setFrameShape(QGraphicsView.Shape.NoFrame)

        self._document_rect = QRectF()
        self._workspace_item = QGraphicsRectItem()
        self._workspace_item.setZValue(-2000)
        self._workspace_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._workspace_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self._document_shadow_item = QGraphicsRectItem()
        self._document_shadow_item.setZValue(-1002)
        self._document_shadow_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._document_shadow_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self._document_matte_item = QGraphicsRectItem()
        self._document_matte_item.setZValue(-1001)
        self._document_matte_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._document_matte_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self._scene.addItem(self._workspace_item)
        self._scene.addItem(self._document_shadow_item)
        self._scene.addItem(self._document_matte_item)
        self.refresh_workspace_theme()

        self._tool = Tool.SELECT
        self._style = StyleState(
            stroke_color=QColor(231, 76, 60, 255),
            fill_color=QColor(231, 76, 60, 80),
            text_color=QColor(44, 62, 80, 255),
            stroke_width=3.0,
            font_size=16,
            font_family="Sans Serif",
            font_bold=False,
            font_italic=False,
            font_underline=False,
            stroke_style=STROKE_STYLE_SOLID,
            text_style=TEXT_STYLE_PLAIN,
        )
        self._zoom_factor = 1.0
        self._initial_view_pending = False
        self._last_action_label = "Edit"
        self._start_scene_pos = QPointF()
        self._preview_item: QGraphicsItem | None = None
        self._crop_item: CropSelectionItem | None = None
        self._crop_shade_item: QGraphicsPathItem | None = None
        self._resize_overlay_item: CropSelectionItem | None = None
        self._resize_overlay_target: QGraphicsItem | None = None
        self._updating_resize_overlay = False
        self._grid_visible = False
        self._snap_enabled = False
        self._grid_size = 16
        self._blur_block_size = 16
        self._next_step_number = 1
        self._alignment_threshold = 8.0
        self._alignment_guides: list[QLineF] = []
        self._blank_document = False

        self._background_item = QGraphicsPixmapItem()
        self._background_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._background_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self._background_item.setZValue(-1000)
        self._scene.addItem(self._background_item)

        self._scene.selectionChanged.connect(self._on_selection_changed)

    def set_blank_document(self, enabled: bool) -> None:
        """
        Marks the document as an empty canvas awaiting its first pasted image.

        Args:
            enabled: True when the canvas is blank and should resize on first paste.

        Returns:
            None
        """

        self._blank_document = bool(enabled)

    def is_blank_document(self) -> bool:
        """
        Returns whether the canvas should adopt pasted image dimensions.

        Returns:
            bool: True for an unused blank canvas tab.
        """

        return self._blank_document

    def document_rect(self) -> QRectF:
        """
        Returns the drawable document bounds in scene coordinates.

        Returns:
            QRectF: Document rectangle (0, 0, width, height).
        """

        return QRectF(self._document_rect)

    def refresh_workspace_theme(self, theme_name: str | None = None) -> None:
        """
        Updates pasteboard and document frame colors for the active theme.

        Args:
            theme_name: Optional theme identifier; uses current theme when omitted.

        Returns:
            None
        """

        colors = get_theme_colors(theme_name)
        resolved_theme = normalize_theme_name(theme_name or current_theme_name())
        workspace_color = QColor(colors.editor_workspace)
        border_color = QColor(colors.editor_document_border)
        shadow_alpha = 65 if resolved_theme == THEME_LIGHT else 85
        shadow_color = QColor(0, 0, 0, shadow_alpha)

        self.setBackgroundBrush(QBrush(workspace_color))
        self._workspace_item.setBrush(workspace_color)
        self._workspace_item.setPen(QPen(Qt.PenStyle.NoPen))
        self._document_matte_item.setBrush(QColor(_DOCUMENT_MATTE_COLOR))
        self._document_matte_item.setPen(QPen(border_color, 1.0))
        self._document_shadow_item.setBrush(shadow_color)
        self._document_shadow_item.setPen(QPen(Qt.PenStyle.NoPen))
        self.viewport().update()

    def _workspace_chrome_items(self) -> frozenset[QGraphicsItem]:
        """
        Returns scene items that form the editor pasteboard chrome.

        Returns:
            frozenset[QGraphicsItem]: Non-annotation workspace items.
        """

        return frozenset(
            {
                self._workspace_item,
                self._document_shadow_item,
                self._document_matte_item,
                self._background_item,
            }
        )

    def _non_annotation_scene_items(self) -> frozenset[QGraphicsItem]:
        """
        Returns scene items that must not be treated as user annotations.

        Returns:
            frozenset[QGraphicsItem]: Chrome and transient editor items.
        """

        blocked = set(self._workspace_chrome_items())
        if self._crop_item is not None:
            blocked.add(self._crop_item)
        if self._crop_shade_item is not None:
            blocked.add(self._crop_shade_item)
        if self._resize_overlay_item is not None:
            blocked.add(self._resize_overlay_item)
        return frozenset(blocked)

    def _compute_workspace_margin(self, width: float, height: float) -> float:
        """
        Computes pasteboard padding around the document.

        Args:
            width: Document width in pixels.
            height: Document height in pixels.

        Returns:
            float: Workspace margin in scene units.
        """

        if width < 1.0 or height < 1.0:
            return _WORKSPACE_MARGIN_MIN
        return max(_WORKSPACE_MARGIN_MIN, min(width, height) * _WORKSPACE_MARGIN_RATIO)

    def _update_workspace_layout(self) -> None:
        """
        Expands the scene pasteboard and positions document chrome items.

        Returns:
            None
        """

        document_rect = self.document_rect()
        if document_rect.width() < 1.0 or document_rect.height() < 1.0:
            self._workspace_item.setVisible(False)
            self._document_shadow_item.setVisible(False)
            self._document_matte_item.setVisible(False)
            self._scene.setSceneRect(QRectF())
            return

        margin = self._compute_workspace_margin(document_rect.width(), document_rect.height())
        workspace_rect = document_rect.adjusted(-margin, -margin, margin, margin)
        self._scene.setSceneRect(workspace_rect)
        self._workspace_item.setRect(workspace_rect)
        self._workspace_item.setVisible(True)
        shadow_rect = document_rect.translated(
            _DOCUMENT_SHADOW_OFFSET,
            _DOCUMENT_SHADOW_OFFSET,
        )
        self._document_shadow_item.setRect(shadow_rect)
        self._document_shadow_item.setVisible(True)
        self._document_matte_item.setRect(document_rect)
        self._document_matte_item.setVisible(True)

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
        self._document_rect = QRectF(pixmap.rect())
        self._update_workspace_layout()
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
        Fits large screenshots into the viewport while keeping smaller ones at 100%.

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
        viewport_height = self.viewport().height()
        if viewport_width <= 1 or viewport_height <= 1:
            return

        self.resetTransform()
        screenshot_rect = QRectF(screenshot.rect())
        needs_fit = (
            screenshot_rect.width() > viewport_width
            or screenshot_rect.height() > viewport_height
        )
        if needs_fit:
            self.fitInView(screenshot_rect, Qt.AspectRatioMode.KeepAspectRatio)
            self._zoom_factor = self.transform().m11()
            self.ensureVisible(
                screenshot_rect.left(),
                screenshot_rect.top(),
                1,
                1,
            )
        else:
            self._zoom_factor = 1.0
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
        QApplication.restoreOverrideCursor()
        self._apply_tool_cursor(tool)
        self._alignment_guides.clear()
        self.viewport().update()
        if tool == Tool.SELECT:
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        else:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
        if tool == Tool.CROP and not self.has_pending_crop():
            self._create_default_crop_selection()

    def consume_last_action_label(self) -> str:
        """
        Returns and resets the last recorded canvas action label.

        Returns:
            str: Action label used for history entries.
        """

        label = self._last_action_label.strip() or "Edit"
        self._last_action_label = "Edit"
        return label

    def _emit_content_changed(self, action_label: str) -> None:
        """
        Emits content change signal with a descriptive action label.

        Args:
            action_label: Human readable action description.

        Returns:
            None
        """

        self._last_action_label = action_label.strip() or "Edit"
        self.content_changed.emit()
        if self._selected_annotation_items():
            self._refresh_selection_info()

    def _selected_annotation_items(self) -> list[QGraphicsItem]:
        """
        Returns currently selected drawable annotation items.

        Returns:
            list[QGraphicsItem]: Selected annotation items.
        """

        return [
            item
            for item in self._scene.selectedItems()
            if item not in self._non_annotation_scene_items()
            and str(item.data(ITEM_ROLE_TYPE) or "")
        ]

    def _build_selection_payload(self, item: QGraphicsItem) -> dict[str, Any]:
        """
        Builds a detail payload for one selected annotation item.

        Args:
            item: Selected annotation graphics item.

        Returns:
            dict[str, Any]: Selection details for toolbar and status display.
        """

        annotation_type = str(item.data(ITEM_ROLE_TYPE) or "")
        rect = self._item_scene_rect(item)
        payload: dict[str, Any] = {
            "type": annotation_type,
            "x": round(rect.x(), 1),
            "y": round(rect.y(), 1),
            "width": round(rect.width(), 1),
            "height": round(rect.height(), 1),
            "z_index": round(item.zValue(), 1),
        }

        if annotation_type in {"rect", "ellipse"}:
            payload["stroke_rgba"] = color_to_list(item.pen().color())
            payload["fill_rgba"] = color_to_list(item.brush().color())
            payload["stroke_width"] = item.pen().widthF()
        elif annotation_type in {"line", "arrow"}:
            payload["stroke_rgba"] = color_to_list(item.pen().color())
            payload["stroke_width"] = item.pen().widthF()
            payload["stroke_style"] = stroke_style_from_pen(item.pen())
        elif annotation_type == "text":
            if isinstance(item, StyledTextItem):
                payload["text_rgba"] = color_to_list(item._text_color)
                payload["fill_rgba"] = color_to_list(item._fill_color)
                payload["stroke_rgba"] = color_to_list(item._stroke_color)
                payload["stroke_width"] = item._stroke_width
                payload["text_style"] = item.text_style()
                payload["text_preview"] = item.text().replace("\n", " ").strip()
                payload["font_size"] = item._font.pointSize()
                payload["font_family"] = item._font.family()
                payload["font_bold"] = item._font.bold()
                payload["font_italic"] = item._font.italic()
                payload["font_underline"] = item._font.underline()
            else:
                payload["stroke_rgba"] = color_to_list(item.defaultTextColor())
                payload["text_rgba"] = color_to_list(item.defaultTextColor())
                payload["text_preview"] = item.toPlainText().replace("\n", " ").strip()
                payload["font_size"] = item.font().pointSize()
                payload["font_family"] = item.font().family()
                payload["font_bold"] = item.font().bold()
                payload["font_italic"] = item.font().italic()
                payload["font_underline"] = item.font().underline()
        elif annotation_type == "image":
            payload["stroke_width"] = 0.0
        elif annotation_type == "step" and isinstance(item, StepBadgeItem):
            payload["step_number"] = item.step_number()
            payload["stroke_rgba"] = color_to_list(item.pen().color())
            payload["fill_rgba"] = color_to_list(item.brush().color())
            payload["stroke_width"] = item.pen().widthF()

        return payload

    def _refresh_selection_info(self) -> None:
        """
        Re-emits selection details for the active annotation selection.

        Returns:
            None
        """

        selected = self._selected_annotation_items()
        if not selected:
            self.selection_style_changed.emit({"type": ""})
            return
        payload = self._build_selection_payload(selected[0])
        if len(selected) > 1:
            payload["count"] = len(selected)
        self.selection_style_changed.emit(payload)

    def _apply_tool_cursor(self, tool: str) -> None:
        """
        Applies the expected mouse cursor for the active tool.

        Args:
            tool: Active tool identifier.

        Returns:
            None
        """

        if tool == Tool.SELECT:
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            return
        if tool == Tool.TEXT:
            self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
            return
        self.viewport().setCursor(Qt.CursorShape.CrossCursor)

    def set_style(
        self,
        stroke_color: QColor | None = None,
        fill_color: QColor | None = None,
        text_color: QColor | None = None,
        stroke_width: float | None = None,
        font_size: int | None = None,
        font_family: str | None = None,
        font_bold: bool | None = None,
        font_italic: bool | None = None,
        font_underline: bool | None = None,
        stroke_style: str | None = None,
        text_style: str | None = None,
    ) -> None:
        """
        Updates active style options and selected item style.

        Args:
            stroke_color: Optional new stroke color.
            fill_color: Optional new fill color.
            text_color: Optional new text color.
            stroke_width: Optional new stroke width.
            font_size: Optional new font size.
            font_family: Optional new font family.
            font_bold: Optional bold state for text.
            font_italic: Optional italic state for text.
            font_underline: Optional underline state for text.

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
        if font_bold is not None:
            self._style.font_bold = bool(font_bold)
        if font_italic is not None:
            self._style.font_italic = bool(font_italic)
        if font_underline is not None:
            self._style.font_underline = bool(font_underline)
        if stroke_style is not None:
            self._style.stroke_style = normalize_stroke_style(stroke_style)
        if text_style is not None:
            self._style.text_style = text_style

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
                if stroke_style is not None:
                    pen.setStyle(stroke_style_to_qt(stroke_style))
                line_item.setPen(pen)
                changed = True
            elif annotation_type == "text" and isinstance(item, StyledTextItem):
                if text_color is not None or stroke_color is not None:
                    item.set_colors(
                        text_color=text_color or stroke_color,
                        stroke_color=stroke_color or text_color,
                    )
                if fill_color is not None:
                    item.set_colors(fill_color=fill_color)
                if font_size is not None or font_family is not None or font_bold is not None or font_italic is not None or font_underline is not None:
                    font = item._font
                    if font_size is not None:
                        font.setPointSize(font_size)
                    if font_family is not None and font_family.strip():
                        font.setFamily(font_family.strip())
                    if font_bold is not None:
                        font.setBold(bool(font_bold))
                    if font_italic is not None:
                        font.setItalic(bool(font_italic))
                    if font_underline is not None:
                        font.setUnderline(bool(font_underline))
                    item.set_font(font)
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
                if font_bold is not None:
                    font = text_item.font()
                    font.setBold(bool(font_bold))
                    text_item.setFont(font)
                if font_italic is not None:
                    font = text_item.font()
                    font.setItalic(bool(font_italic))
                    text_item.setFont(font)
                if font_underline is not None:
                    font = text_item.font()
                    font.setUnderline(bool(font_underline))
                    text_item.setFont(font)
                changed = True
        if changed:
            self._emit_content_changed("Update selected style")

    def set_grid_visible(self, visible: bool) -> None:
        """
        Enables or disables the optional canvas grid overlay.

        Args:
            visible: True to display the grid.

        Returns:
            None
        """

        self._grid_visible = bool(visible)
        self.viewport().update()

    def set_snap_enabled(self, enabled: bool) -> None:
        """
        Enables or disables snapping for placement and movement.

        Args:
            enabled: True to enable snapping.

        Returns:
            None
        """

        self._snap_enabled = bool(enabled)
        self._alignment_guides.clear()
        self.viewport().update()

    def set_grid_size(self, size: int) -> None:
        """
        Updates the grid spacing in scene pixels.

        Args:
            size: Grid step size.

        Returns:
            None
        """

        self._grid_size = max(4, min(128, int(size)))
        self.viewport().update()

    def grid_visible(self) -> bool:
        """
        Returns current grid visibility state.

        Returns:
            bool: True when grid is visible.
        """

        return self._grid_visible

    def snap_enabled(self) -> bool:
        """
        Returns current snapping state.

        Returns:
            bool: True when snapping is enabled.
        """

        return self._snap_enabled

    def grid_size(self) -> int:
        """
        Returns the current snapping grid size.

        Returns:
            int: Grid step in pixels.
        """

        return self._grid_size

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
        scene_pos = self._snap_point_to_grid(scene_pos)
        self._start_scene_pos = scene_pos

        if self._tool == Tool.TEXT:
            text = self._prompt_text_input()
            if text:
                scene_pos = self._snap_point_to_grid(scene_pos)
                if self._style.text_style in {TEXT_STYLE_BOX, TEXT_STYLE_BUBBLE}:
                    font = QFont()
                    font.setPointSize(self._style.font_size)
                    font.setFamily(self._style.font_family)
                    font.setBold(self._style.font_bold)
                    font.setItalic(self._style.font_italic)
                    font.setUnderline(self._style.font_underline)
                    item = StyledTextItem(
                        text=text,
                        text_style=self._style.text_style,
                        font=font,
                        text_color=QColor(self._style.text_color),
                        fill_color=QColor(self._style.fill_color),
                        stroke_color=QColor(self._style.stroke_color),
                        stroke_width=self._style.stroke_width,
                    )
                    item.setPos(scene_pos)
                    self._scene.addItem(item)
                else:
                    item = self._scene.addText(text)
                    item.setDefaultTextColor(self._style.text_color)
                    font = item.font()
                    font.setPointSize(self._style.font_size)
                    font.setFamily(self._style.font_family)
                    font.setBold(self._style.font_bold)
                    font.setItalic(self._style.font_italic)
                    font.setUnderline(self._style.font_underline)
                    item.setFont(font)
                    item.setPos(scene_pos)
                    item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
                    configure_graphics_item(item, "text")
                self._emit_content_changed("Insert text")
            return

        if self._tool == Tool.STEP:
            badge = StepBadgeItem(self._next_step_number)
            badge.setPos(scene_pos.x() - badge.rect().width() / 2.0, scene_pos.y() - badge.rect().height() / 2.0)
            self._scene.addItem(badge)
            self._next_step_number += 1
            self._emit_content_changed("Insert step")
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
        if self._tool == Tool.BLUR:
            self._clear_resize_overlay()
            self._preview_item = self._create_preview_item(scene_pos)
            if self._preview_item is not None:
                self._scene.addItem(self._preview_item)
            return
        if self._tool == Tool.OCR:
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
        if hit_item in self._non_annotation_scene_items():
            return False
        if not (hit_item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable):
            return False

        self._scene.clearSelection()
        hit_item.setSelected(True)
        self._scene.setFocusItem(hit_item)
        event.accept()
        return True

    def _prompt_text_input(self) -> str:
        """
        Opens a multi-line text input dialog for text annotations.

        Returns:
            str: Entered text, empty when cancelled.
        """

        dialog = QDialog(self)
        dialog.setWindowTitle("Insert Text")
        dialog.setModal(True)
        dialog.resize(420, 240)

        root_layout = QVBoxLayout(dialog)
        label = QLabel("Text:")
        root_layout.addWidget(label)
        text_edit = QTextEdit(dialog)
        text_edit.setPlaceholderText("Enter one or multiple lines.")
        root_layout.addWidget(text_edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        root_layout.addWidget(buttons)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return ""
        return text_edit.toPlainText().strip()

    def _snap_point_to_grid(self, point: QPointF) -> QPointF:
        """
        Snaps one point to grid intersections when snapping is enabled.

        Args:
            point: Scene-space point.

        Returns:
            QPointF: Snapped or unchanged point.
        """

        if not self._snap_enabled:
            return point
        grid_size = float(max(1, self._grid_size))
        snapped_x = round(point.x() / grid_size) * grid_size
        snapped_y = round(point.y() / grid_size) * grid_size
        return QPointF(snapped_x, snapped_y)

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
                    self._crop_item.set_aspect_ratio_lock_enabled(True)
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
            if self._tool == Tool.BLUR:
                blur_rect = self._preview_item.boundingRect().translated(self._preview_item.pos())
                self._scene.removeItem(self._preview_item)
                self._preview_item = None
                self._apply_region_blur(blur_rect)
                return
            if self._tool == Tool.OCR:
                ocr_rect = self._preview_item.boundingRect().translated(self._preview_item.pos())
                self._scene.removeItem(self._preview_item)
                self._preview_item = None
                self._run_ocr_on_region(ocr_rect)
                return

            configure_graphics_item(self._preview_item, self._tool)
            self._preview_item = None
            draw_names = {
                Tool.RECT: "Draw rectangle",
                Tool.ELLIPSE: "Draw ellipse",
                Tool.LINE: "Draw line",
                Tool.ARROW: "Draw arrow",
            }
            self._emit_content_changed(draw_names.get(self._tool, "Draw annotation"))
            return
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self._snap_selected_items_with_alignment()
        self._sync_resize_overlay_with_target()
        self._refresh_selection_info()

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

    def _annotation_item_at_view_pos(self, view_pos: QPoint) -> QGraphicsItem | None:
        """
        Returns the annotation under a view position for context menu actions.

        Args:
            view_pos: View coordinate to inspect.

        Returns:
            QGraphicsItem | None: Drawable annotation item or None.
        """

        hit_item = self.itemAt(view_pos)
        if hit_item is None:
            return None
        if hit_item is self._resize_overlay_item and self._resize_overlay_target is not None:
            return self._resize_overlay_target
        if hit_item in self._non_annotation_scene_items():
            return None
        if not str(hit_item.data(ITEM_ROLE_TYPE) or ""):
            return None
        return hit_item

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """
        Shows context menu with paste and annotation actions.

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

        annotation_item = self._annotation_item_at_view_pos(event.pos())
        if annotation_item is not None:
            if not annotation_item.isSelected():
                self._scene.clearSelection()
                annotation_item.setSelected(True)
            menu.addSeparator()
            bring_to_front_action = QAction("Bring to Front", self)
            bring_to_front_action.triggered.connect(self.bring_selected_to_front)
            menu.addAction(bring_to_front_action)
            send_to_back_action = QAction("Send to Back", self)
            send_to_back_action.triggered.connect(self.send_selected_to_back)
            menu.addAction(send_to_back_action)
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
        self.fitInView(self.document_rect(), Qt.AspectRatioMode.KeepAspectRatio)
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

        pen = create_pen(self._style)
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
        if self._tool == Tool.BLUR:
            blur_pen = QPen(QColor(155, 89, 182, 220), 1.5, Qt.PenStyle.DashLine)
            item = QGraphicsRectItem(QRectF(start, start))
            item.setPen(blur_pen)
            item.setBrush(QColor(155, 89, 182, 70))
            return item
        if self._tool == Tool.OCR:
            ocr_pen = QPen(QColor(46, 204, 113, 220), 1.5, Qt.PenStyle.DashLine)
            item = QGraphicsRectItem(QRectF(start, start))
            item.setPen(ocr_pen)
            item.setBrush(QColor(46, 204, 113, 70))
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
        snapped_current = self._snap_point_to_grid(current)
        rect = QRectF(start, snapped_current).normalized()
        if isinstance(self._preview_item, (QGraphicsRectItem, QGraphicsEllipseItem)):
            self._preview_item.setRect(rect)
            return
        if isinstance(self._preview_item, QGraphicsLineItem):
            self._preview_item.setLine(
                start.x(),
                start.y(),
                snapped_current.x(),
                snapped_current.y(),
            )

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

        source_screenshot = self.screenshot()
        if source_screenshot.isNull():
            return
        annotation_models = self.collect_annotations()
        transformed_annotations = self._transform_annotations_for_crop(
            annotation_models,
            crop_rect,
        )

        crop_rect_int = crop_rect.toAlignedRect()
        background_color = self._background_base_color()
        expanded = QImage(crop_rect_int.size(), QImage.Format.Format_ARGB32)
        expanded.fill(background_color)
        painter = QPainter(expanded)
        source_offset_x = -crop_rect_int.x()
        source_offset_y = -crop_rect_int.y()
        painter.drawPixmap(source_offset_x, source_offset_y, source_screenshot)
        painter.end()
        cropped = QPixmap.fromImage(expanded)
        self.cancel_crop()
        self.clear_annotations()
        self.set_screenshot(cropped)
        self.load_annotations(transformed_annotations)
        self._emit_content_changed("Apply crop")

    def _transform_annotations_for_crop(
        self,
        annotations: list[AnnotationModel],
        crop_rect: QRectF,
    ) -> list[AnnotationModel]:
        """
        Translates annotations into the cropped coordinate system.

        Args:
            annotations: Existing annotation models.
            crop_rect: Crop rectangle in old scene coordinates.

        Returns:
            list[AnnotationModel]: Cropped/translated annotations.
        """

        transformed: list[AnnotationModel] = []
        for annotation in annotations:
            annotation_rect = self._annotation_bounds(annotation)
            if not annotation_rect.intersects(crop_rect):
                continue
            transformed.append(
                AnnotationModel(
                    annotation_type=annotation.annotation_type,
                    x=annotation.x - crop_rect.x(),
                    y=annotation.y - crop_rect.y(),
                    width=annotation.width,
                    height=annotation.height,
                    stroke_rgba=list(annotation.stroke_rgba),
                    fill_rgba=list(annotation.fill_rgba),
                    stroke_width=annotation.stroke_width,
                    text=annotation.text,
                    font_size=annotation.font_size,
                    font_family=annotation.font_family,
                    payload=dict(annotation.payload),
                )
            )
        return transformed

    def _annotation_bounds(self, annotation: AnnotationModel) -> QRectF:
        """
        Computes scene-space bounds for one serialized annotation.

        Args:
            annotation: Annotation model.

        Returns:
            QRectF: Annotation geometry bounds.
        """

        if annotation.annotation_type in {"line", "arrow"}:
            return QRectF(
                QPointF(annotation.x, annotation.y),
                QPointF(annotation.x + annotation.width, annotation.y + annotation.height),
            ).normalized()
        return QRectF(
            annotation.x,
            annotation.y,
            annotation.width,
            annotation.height,
        ).normalized()

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
            if item in self._workspace_chrome_items():
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
            if item in self._workspace_chrome_items():
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

        rect = self.document_rect().toRect()
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
        Pastes text, image, image file, or image URL from clipboard.

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

        pixmap = self._pixmap_from_clipboard(mime)
        if pixmap is not None and not pixmap.isNull():
            self._paste_image_pixmap(pixmap, scene_pos)
            return

        if mime.hasText():
            text = mime.text().strip()
            if text.lower().startswith(("http://", "https://")) and self._try_paste_image_url(text, scene_pos):
                return
            path_pixmap = self._pixmap_from_local_path_text(text)
            if path_pixmap is not None and not path_pixmap.isNull():
                self._paste_image_pixmap(path_pixmap, scene_pos)
                return
            if text:
                text_item = self._scene.addText(text)
                text_item.setDefaultTextColor(self._style.text_color)
                font = text_item.font()
                font.setPointSize(self._style.font_size)
                font.setFamily(self._style.font_family)
                font.setBold(self._style.font_bold)
                font.setItalic(self._style.font_italic)
                font.setUnderline(self._style.font_underline)
                text_item.setFont(font)
                text_item.setPos(scene_pos)
                text_item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
                configure_graphics_item(text_item, "text")
                self._emit_content_changed("Paste text")

    def keyPressEvent(self, event) -> None:
        """
        Handles Ctrl+V clipboard paste shortcut.

        Args:
            event: Key event.

        Returns:
            None
        """

        if (
            event.modifiers() & Qt.KeyboardModifier.ControlModifier
            and event.key() == Qt.Key.Key_D
        ):
            if self.duplicate_selected_items():
                return
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
                if item in self._workspace_chrome_items():
                    continue
                if item is self._crop_item:
                    self.cancel_crop()
                    removed = True
                    continue
                self._scene.removeItem(item)
                removed = True
            if removed:
                self._emit_content_changed("Delete selection")
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
            if item in self._non_annotation_scene_items():
                continue
            if self._resize_item_geometry(item, scale_factor):
                changed = True
        if changed:
            self._sync_resize_overlay_with_target()
            self._emit_content_changed("Resize selection")
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

        clipped = rect.intersected(self.document_rect()).normalized()
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
        self._emit_content_changed("Fill background")

    def set_blur_block_size(self, block_size: int) -> None:
        """
        Sets the pixel block size used by the blur tool.

        Args:
            block_size: Pixelation block size in pixels.

        Returns:
            None
        """

        self._blur_block_size = max(4, min(int(block_size), 64))

    def blur_block_size(self) -> int:
        """
        Returns the active blur block size.

        Returns:
            int: Blur block size in pixels.
        """

        return self._blur_block_size

    def _apply_region_blur(self, rect: QRectF) -> None:
        """
        Pixelates a rectangular screenshot area for redaction.

        Args:
            rect: Target area in scene coordinates.

        Returns:
            None
        """

        clipped = rect.intersected(self.document_rect()).normalized()
        if clipped.width() < 1 or clipped.height() < 1:
            return
        screenshot = self.screenshot()
        if screenshot.isNull():
            return
        image = screenshot.toImage()
        blurred = pixelate_qimage_region(
            image,
            clipped.toAlignedRect(),
            self._blur_block_size,
        )
        self._background_item.setPixmap(QPixmap.fromImage(blurred))
        self._emit_content_changed("Blur region")

    def duplicate_selected_items(self) -> bool:
        """
        Duplicates the current selection with a small offset.

        Returns:
            bool: True when at least one item was duplicated.
        """

        selected_items = [
            item
            for item in self._scene.selectedItems()
            if item not in self._non_annotation_scene_items()
        ]
        if not selected_items:
            return False

        created_items: list[QGraphicsItem] = []
        for item in selected_items:
            model = annotation_from_item(item)
            if model is None:
                continue
            model.x += 16.0
            model.y += 16.0
            max_z = max(
                (existing.zValue() for existing in self._annotation_items()),
                default=0.0,
            )
            created = add_annotation_to_scene(self._scene, model)
            if created is None:
                continue
            created.setZValue(max_z + 1.0)
            created_items.append(created)
        if not created_items:
            return False
        self._scene.clearSelection()
        for created in created_items:
            created.setSelected(True)
        self._emit_content_changed("Duplicate selection")
        return True

    def bring_selected_forward(self) -> None:
        """
        Moves selected items one step toward the front.

        Returns:
            None
        """

        self._change_selected_z_order(1.0)

    def send_selected_backward(self) -> None:
        """
        Moves selected items one step toward the back.

        Returns:
            None
        """

        self._change_selected_z_order(-1.0)

    def bring_selected_to_front(self) -> None:
        """
        Moves selected items to the topmost z-order.

        Returns:
            None
        """

        selected = self._scene.selectedItems()
        if not selected:
            return
        max_z = max((item.zValue() for item in self._annotation_items()), default=0.0)
        for index, item in enumerate(selected):
            item.setZValue(max_z + 1.0 + index)
        self._emit_content_changed("Bring to front")

    def send_selected_to_back(self) -> None:
        """
        Moves selected items to the lowest z-order.

        Returns:
            None
        """

        selected = self._scene.selectedItems()
        if not selected:
            return
        min_z = min((item.zValue() for item in self._annotation_items()), default=0.0)
        for index, item in enumerate(selected):
            item.setZValue(min_z - 1.0 - index)
        self._emit_content_changed("Send to back")

    def reset_step_counter(self, value: int = 1) -> None:
        """
        Sets the next step badge number.

        Args:
            value: Next step number.

        Returns:
            None
        """

        self._next_step_number = max(1, int(value))

    def _change_selected_z_order(self, delta: float) -> None:
        """
        Applies a z-order delta to selected annotation items.

        Args:
            delta: Z-order delta.

        Returns:
            None
        """

        selected = self._scene.selectedItems()
        if not selected:
            return
        for item in selected:
            item.setZValue(item.zValue() + delta)
        self._emit_content_changed("Change layer order")

    def _run_ocr_on_region(self, rect: QRectF) -> None:
        """
        Runs OCR on one screenshot region and copies text to clipboard.

        Args:
            rect: Target region in scene coordinates.

        Returns:
            None
        """

        clipped = rect.intersected(self.document_rect()).normalized()
        if clipped.width() < 2 or clipped.height() < 2:
            return
        composited = self.export_composited_pixmap()
        if composited.isNull():
            return
        cropped = composited.copy(clipped.toAlignedRect())
        if cropped.isNull():
            return
        text = extract_text_from_png_bytes(pixmap_to_png_bytes(cropped))
        if not text:
            self._emit_content_changed("OCR found no text")
            return
        QGuiApplication.clipboard().setText(text)
        self._emit_content_changed("Copy OCR text")

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

    def import_image_file(self, file_path: str, view_pos: QPoint | None = None) -> bool:
        """
        Imports one local image file into the document as a movable annotation.

        Args:
            file_path: Absolute or relative path to an image file.
            view_pos: Optional view coordinate for insertion.

        Returns:
            bool: True when the image was imported successfully.
        """

        pixmap = self._load_image_pixmap(Path(file_path))
        if pixmap is None or pixmap.isNull():
            return False
        scene_pos = (
            self.mapToScene(view_pos) if view_pos is not None else self.mapToScene(self.viewport().rect().center())
        )
        self._paste_image_pixmap(pixmap, scene_pos)
        return True

    def _paste_image_pixmap(self, pixmap: QPixmap, scene_pos: QPointF) -> None:
        """
        Inserts one image and applies blank-canvas sizing rules when needed.

        Args:
            pixmap: Image to insert.
            scene_pos: Target position in scene coordinates.

        Returns:
            None
        """

        snap_position = True
        if self._blank_document and not self.collect_annotations():
            blank = QPixmap(pixmap.size())
            blank.fill(QColor(255, 255, 255, 255))
            self.set_screenshot(blank)
            self._blank_document = False
            scene_pos = QPointF(0.0, 0.0)
            snap_position = False
        self._insert_image_pixmap(pixmap, scene_pos, snap=snap_position)

    def _pixmap_from_local_path_text(self, text: str) -> QPixmap | None:
        """
        Loads an image when clipboard text contains one local file path.

        Args:
            text: Clipboard text payload.

        Returns:
            QPixmap | None: Loaded image or None.
        """

        for path in self._image_paths_from_text(text):
            pixmap = self._load_image_pixmap(path)
            if pixmap is not None:
                return pixmap
        return None

    def _load_image_pixmap(self, path: Path) -> QPixmap | None:
        """
        Loads one supported image file into a pixmap.

        Args:
            path: Local image file path.

        Returns:
            QPixmap | None: Loaded pixmap or None.
        """

        if path.suffix.lower() not in _CLIPBOARD_IMAGE_SUFFIXES or not path.is_file():
            return None
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return None
        return pixmap

    def _normalize_local_image_path(self, value: str) -> Path | None:
        """
        Normalizes clipboard path or URI text to one local image path.

        Args:
            value: Raw clipboard path or URI line.

        Returns:
            Path | None: Existing local image path or None.
        """

        candidate = value.strip().strip('"').strip("'")
        if not candidate or candidate.lower() in {"copy", "cut"}:
            return None
        if candidate.startswith("file://"):
            candidate = QUrl(candidate).toLocalFile().strip()
        if not candidate:
            return None
        path = Path(candidate)
        if path.suffix.lower() not in _CLIPBOARD_IMAGE_SUFFIXES or not path.is_file():
            return None
        return path

    def _image_paths_from_text(self, text: str) -> list[Path]:
        """
        Extracts local image file paths from plain clipboard text.

        Args:
            text: Clipboard text payload.

        Returns:
            list[Path]: Supported local image paths.
        """

        paths: list[Path] = []
        seen: set[str] = set()
        for line in text.splitlines():
            normalized = self._normalize_local_image_path(line)
            if normalized is None:
                continue
            key = str(normalized.resolve())
            if key in seen:
                continue
            seen.add(key)
            paths.append(normalized)
        if not paths:
            normalized = self._normalize_local_image_path(text)
            if normalized is not None:
                paths.append(normalized)
        return paths

    def _image_paths_from_mime(self, mime) -> list[Path]:
        """
        Extracts local image file paths from clipboard MIME payloads.

        Args:
            mime: Clipboard MIME payload.

        Returns:
            list[Path]: Supported local image paths.
        """

        paths: list[Path] = []
        seen: set[str] = set()

        def append_path(raw_value: str) -> None:
            normalized = self._normalize_local_image_path(raw_value)
            if normalized is None:
                return
            key = str(normalized.resolve())
            if key in seen:
                return
            seen.add(key)
            paths.append(normalized)

        if mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    append_path(url.toLocalFile())

        for format_name in (
            "text/uri-list",
            "x-special/gnome-copied-files",
            "x-special/mate-copied-files",
        ):
            if not mime.hasFormat(format_name):
                continue
            raw = bytes(mime.data(format_name)).decode("utf-8", errors="ignore")
            for line in raw.splitlines():
                append_path(line)

        if mime.hasText():
            for path in self._image_paths_from_text(mime.text()):
                key = str(path.resolve())
                if key in seen:
                    continue
                seen.add(key)
                paths.append(path)

        return paths

    def _pixmap_from_clipboard(self, mime) -> QPixmap | None:
        """
        Resolves one image pixmap from clipboard MIME data.

        Args:
            mime: Clipboard MIME payload.

        Returns:
            QPixmap | None: Image pixmap when clipboard contains image data.
        """

        if mime.hasImage():
            pixmap = QPixmap.fromImage(mime.image())
            if not pixmap.isNull():
                return pixmap

        for path in self._image_paths_from_mime(mime):
            pixmap = self._load_image_pixmap(path)
            if pixmap is not None:
                return pixmap

        return None

    def _insert_image_pixmap(self, pixmap: QPixmap, scene_pos: QPointF, *, snap: bool = True) -> None:
        """
        Inserts a pasted image as movable annotation.

        Args:
            pixmap: Pasted pixmap.
            scene_pos: Item position.
            snap: True to align the insertion point to the active grid.

        Returns:
            None
        """

        position = self._snap_point_to_grid(scene_pos) if snap else scene_pos
        item = QGraphicsPixmapItem(pixmap)
        item.setPos(position)
        configure_graphics_item(item, "image")
        item.setData(2001, encode_pixmap_to_base64(pixmap))
        self._scene.addItem(item)
        self._scene.clearSelection()
        item.setSelected(True)
        self._sync_resize_overlay_with_target(item)
        self._emit_content_changed("Paste image")

    def _on_selection_changed(self) -> None:
        """
        Emits style details of the first selected item.

        Returns:
            None
        """

        selected = self._scene.selectedItems()
        if not selected:
            self._clear_resize_overlay()
            self.selection_style_changed.emit({"type": ""})
            return
        item = selected[0]
        if item in {self._crop_item, self._crop_shade_item, self._resize_overlay_item}:
            self._clear_resize_overlay()
            self.selection_style_changed.emit({"type": ""})
            return
        if len(selected) == 1 and self._can_resize_item(item):
            self._sync_resize_overlay_with_target(item)
        else:
            self._clear_resize_overlay()
        self._refresh_selection_info()

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
            overlay.set_aspect_ratio_lock_enabled(True)
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
        self._emit_content_changed("Resize selection")

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
            if pixmap.width() <= 0 or pixmap.height() <= 0:
                return False
            target.setTransform(QTransform())
            target.setPos(new_rect.topLeft())
            scale_x = new_rect.width() / float(pixmap.width())
            scale_y = new_rect.height() / float(pixmap.height())
            target.setTransform(QTransform.fromScale(scale_x, scale_y))
            return True

        return False

    def _annotation_items(self) -> list[QGraphicsItem]:
        """
        Returns all scene items that represent persisted annotations.

        Returns:
            list[QGraphicsItem]: Annotation graphics items.
        """

        items: list[QGraphicsItem] = []
        for item in self._scene.items():
            if item in self._non_annotation_scene_items():
                continue
            if not str(item.data(ITEM_ROLE_TYPE) or ""):
                continue
            items.append(item)
        return items

    def _snap_selected_items_with_alignment(self) -> None:
        """
        Snaps selected annotations to grid and nearby item alignment.

        Returns:
            None
        """

        if not self._snap_enabled:
            self._alignment_guides.clear()
            self.viewport().update()
            return

        selected = [
            item
            for item in self._scene.selectedItems()
            if item not in self._non_annotation_scene_items()
        ]
        if not selected:
            self._alignment_guides.clear()
            self.viewport().update()
            return

        anchor = selected[0]
        anchor_rect = self._item_scene_rect(anchor)

        grid_anchor = self._snap_point_to_grid(anchor_rect.topLeft())
        grid_dx = grid_anchor.x() - anchor_rect.x()
        grid_dy = grid_anchor.y() - anchor_rect.y()

        align_dx, align_dy, guides = self._compute_alignment_shift(anchor, anchor_rect)
        shift_x = align_dx if align_dx is not None else grid_dx
        shift_y = align_dy if align_dy is not None else grid_dy
        if abs(shift_x) < 0.001 and abs(shift_y) < 0.001:
            self._alignment_guides = guides
            self.viewport().update()
            return

        for item in selected:
            item.setPos(item.pos() + QPointF(shift_x, shift_y))
        self._sync_resize_overlay_with_target()
        self._alignment_guides = guides
        self.viewport().update()
        self._emit_content_changed("Snap selection")

    def _compute_alignment_shift(
        self,
        anchor: QGraphicsItem,
        anchor_rect: QRectF,
    ) -> tuple[float | None, float | None, list[QLineF]]:
        """
        Calculates magnetic alignment offsets against nearby annotations.

        Args:
            anchor: Currently moved anchor item.
            anchor_rect: Anchor geometry in scene coordinates.

        Returns:
            tuple[float | None, float | None, list[QLineF]]: Best X/Y offset and guide lines.
        """

        candidates = [item for item in self._annotation_items() if item is not anchor]
        if not candidates:
            return None, None, []

        x_points = [
            anchor_rect.left(),
            anchor_rect.center().x(),
            anchor_rect.right(),
        ]
        y_points = [
            anchor_rect.top(),
            anchor_rect.center().y(),
            anchor_rect.bottom(),
        ]

        best_dx: float | None = None
        best_dy: float | None = None
        guides: list[QLineF] = []

        for candidate in candidates:
            rect = self._item_scene_rect(candidate)
            compare_x = [rect.left(), rect.center().x(), rect.right()]
            compare_y = [rect.top(), rect.center().y(), rect.bottom()]

            for source_x in x_points:
                for target_x in compare_x:
                    delta = target_x - source_x
                    if abs(delta) > self._alignment_threshold:
                        continue
                    if best_dx is None or abs(delta) < abs(best_dx):
                        best_dx = delta
                        guides = [line for line in guides if line.p1().x() != line.p2().x()]
                        guides.append(QLineF(target_x, rect.top(), target_x, rect.bottom()))

            for source_y in y_points:
                for target_y in compare_y:
                    delta = target_y - source_y
                    if abs(delta) > self._alignment_threshold:
                        continue
                    if best_dy is None or abs(delta) < abs(best_dy):
                        best_dy = delta
                        guides = [line for line in guides if line.p1().y() != line.p2().y()]
                        guides.append(QLineF(rect.left(), target_y, rect.right(), target_y))

        return best_dx, best_dy, guides

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        """
        Draws optional grid and alignment guides on top of scene items.

        Args:
            painter: Qt painter.
            rect: Visible scene rectangle.

        Returns:
            None
        """

        super().drawForeground(painter, rect)
        document_rect = self.document_rect()
        if document_rect.width() < 1.0 or document_rect.height() < 1.0:
            return
        if self._grid_visible:
            grid_pen = QPen(QColor(255, 255, 255, 30), 0)
            painter.setPen(grid_pen)
            size = max(4, self._grid_size)
            grid_rect = document_rect.intersected(rect)
            start_x = int(grid_rect.left() // size) * size
            end_x = int(grid_rect.right()) + size
            start_y = int(grid_rect.top() // size) * size
            end_y = int(grid_rect.bottom()) + size
            x = start_x
            while x <= end_x:
                painter.drawLine(
                    QPointF(float(x), grid_rect.top()),
                    QPointF(float(x), grid_rect.bottom()),
                )
                x += size
            y = start_y
            while y <= end_y:
                painter.drawLine(
                    QPointF(grid_rect.left(), float(y)),
                    QPointF(grid_rect.right(), float(y)),
                )
                y += size

        if self._alignment_guides:
            guide_pen = QPen(QColor(78, 205, 196, 200), 1.2, Qt.PenStyle.DashLine)
            painter.setPen(guide_pen)
            for line in self._alignment_guides:
                painter.drawLine(line)

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
        outer = QRectF(self.document_rect())
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

        rect = QRectF(self.document_rect())
        self._crop_item = CropSelectionItem(rect)
        self._crop_item.set_aspect_ratio_lock_enabled(True)
        self._crop_item.on_geometry_changed = self._update_crop_shade
        self._scene.addItem(self._crop_item)
        self._crop_item.setSelected(True)
        self._ensure_crop_shade_item()
        self._update_crop_shade()
        self.crop_selection_changed.emit(True)

