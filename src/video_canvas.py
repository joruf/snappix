"""
Video playback and time-ranged annotation canvas for the Snappix video editor.
"""

from __future__ import annotations

import copy

from PySide6.QtCore import QPoint, QPointF, QRectF, QSizeF, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeyEvent, QMouseEvent, QPainter
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QInputDialog,
)

from src.annotation_items import (
    ITEM_ROLE_ID,
    ITEM_ROLE_LOCKED,
    ITEM_ROLE_TYPE,
    ArrowItem,
    DoubleArrowItem,
    STROKE_STYLE_SOLID,
    StrokeLineItem,
    StyleState,
    annotation_from_item,
    apply_stroke_width_to_pen,
    configure_graphics_item,
    create_pen,
    create_stroke_pen,
    list_to_color,
    normalize_stroke_style,
    stroke_style_to_qt,
)
from src.annotation_shapes import TEXT_STYLE_BUBBLE, StepBadgeItem, StyledTextItem
from src.draw_style_defaults import create_default_style_state
from src.crop_item import CropSelectionItem
from src.editor_canvas import (
    DRAG_LINE_TOOLS,
    DRAG_RECT_TOOLS,
    POLY_DRAW_TOOLS,
    Tool,
)
from src.shape_items import (
    PATH_SHAPE_KINDS,
    SHAPE_LINE_TYPES,
    SHAPE_RECT_TYPES,
    STAMP_MARK_TYPES,
    PathShapeItem,
    PolyPathItem,
    SpotlightItem,
    points_from_payload,
)
from src.video_models import VideoAnnotationModel

DEFAULT_ANNOTATION_DURATION_MS = 3000

DRAG_TOOLS = DRAG_RECT_TOOLS | DRAG_LINE_TOOLS

_DRAW_ACTION_LABELS: dict[str, str] = {
    Tool.RECT: "Draw rectangle",
    Tool.ELLIPSE: "Draw ellipse",
    Tool.TRIANGLE: "Draw triangle",
    Tool.STAR: "Draw star",
    Tool.POLYGON: "Draw polygon",
    Tool.LINE: "Draw line",
    Tool.POLYLINE: "Draw polyline",
    Tool.ARROW: "Draw arrow",
    Tool.DOUBLE_ARROW: "Draw double arrow",
    Tool.BENT_ARROW: "Draw bent arrow",
    Tool.SPOTLIGHT: "Draw spotlight",
    Tool.CROSS: "Draw cross",
    Tool.CHECKMARK: "Draw checkmark",
    Tool.TEXT: "Insert text",
    Tool.CALLOUT: "Insert callout",
    Tool.STEP: "Insert step",
}


def _style_for_annotation(annotation: VideoAnnotationModel) -> StyleState:
    """
    Builds a StyleState from one persisted video annotation.

    Args:
        annotation: Source annotation model.

    Returns:
        StyleState: Style state matching the annotation's stroke/fill/text colors.
    """

    return StyleState(
        stroke_color=list_to_color(annotation.stroke_rgba),
        fill_color=list_to_color(annotation.fill_rgba),
        text_color=list_to_color(annotation.stroke_rgba),
        stroke_width=annotation.stroke_width,
        font_size=annotation.font_size,
        font_family=annotation.font_family,
        font_bold=annotation.font_bold,
        font_italic=annotation.font_italic,
        font_underline=annotation.font_underline,
        stroke_style=str(annotation.payload.get("stroke_style", STROKE_STYLE_SOLID) or STROKE_STYLE_SOLID),
    )


def _configure_video_annotation_item(
    item: QGraphicsItem,
    annotation: VideoAnnotationModel,
) -> None:
    """
    Applies selection flags and stable annotation metadata to one scene item.

    Args:
        item: Graphics item to configure.
        annotation: Source annotation model.

    Returns:
        None
    """

    configure_graphics_item(item, annotation.annotation_type)
    item.setData(ITEM_ROLE_ID, annotation.annotation_id)
    item.setZValue(1.0)


def build_annotation_item(annotation: VideoAnnotationModel) -> QGraphicsItem | None:
    """
    Builds one Qt graphics item that renders a video annotation.

    Args:
        annotation: Annotation model to render.

    Returns:
        QGraphicsItem | None: Graphics item, or None for unknown annotation types.
    """

    style = _style_for_annotation(annotation)
    pen = create_pen(style)
    rect = QRectF(annotation.x, annotation.y, annotation.width, annotation.height)

    if annotation.annotation_type == Tool.RECT:
        corner_radius = float(annotation.payload.get("corner_radius", 0.0) or 0.0)
        item = PathShapeItem("rect", rect, corner_radius=corner_radius)
        item.setPen(pen)
        item.setBrush(style.fill_color)
        _configure_video_annotation_item(item, annotation)
        return item
    if annotation.annotation_type == Tool.ELLIPSE:
        item = QGraphicsEllipseItem(rect)
        item.setPen(pen)
        item.setBrush(style.fill_color)
        _configure_video_annotation_item(item, annotation)
        return item
    if annotation.annotation_type in PATH_SHAPE_KINDS:
        item = PathShapeItem(annotation.annotation_type, rect)
        item.setPen(pen)
        if annotation.annotation_type in STAMP_MARK_TYPES:
            item.setBrush(style.stroke_color)
        else:
            item.setBrush(style.fill_color)
        _configure_video_annotation_item(item, annotation)
        return item
    if annotation.annotation_type == Tool.SPOTLIGHT:
        item = SpotlightItem(
            QRectF(0.0, 0.0, annotation.width, annotation.height),
            focus_mode=str(annotation.payload.get("focus_mode", "ellipse")),
            dim_alpha=int(annotation.payload.get("dim_alpha", 150)),
        )
        item.setPen(pen)
        item.setPos(annotation.x, annotation.y)
        _configure_video_annotation_item(item, annotation)
        return item
    if annotation.annotation_type in POLY_DRAW_TOOLS:
        points = points_from_payload(annotation.payload)
        if len(points) < 2:
            return None
        item = PolyPathItem(annotation.annotation_type, points)
        item.setPen(pen)
        item.setBrush(style.fill_color if annotation.annotation_type == Tool.POLYGON else QColor(0, 0, 0, 0))
        _configure_video_annotation_item(item, annotation)
        return item
    if annotation.annotation_type == Tool.DOUBLE_ARROW:
        line_item = DoubleArrowItem()
        line_item.setLine(
            annotation.x,
            annotation.y,
            annotation.x + annotation.width,
            annotation.y + annotation.height,
        )
        line_item.setPen(pen)
        _configure_video_annotation_item(line_item, annotation)
        return line_item
    if annotation.annotation_type in (Tool.LINE, Tool.ARROW):
        line_item = ArrowItem() if annotation.annotation_type == Tool.ARROW else StrokeLineItem()
        line_item.setLine(
            annotation.x,
            annotation.y,
            annotation.x + annotation.width,
            annotation.y + annotation.height,
        )
        line_item.setPen(pen)
        _configure_video_annotation_item(line_item, annotation)
        return line_item
    if annotation.annotation_type == Tool.STEP:
        from src.annotation_shapes import StepBadgeItem

        step_number = int(annotation.payload.get("step_number", 1) or 1)
        item = StepBadgeItem(step_number)
        item.setPen(pen)
        item.setBrush(style.fill_color)
        item.setPos(annotation.x, annotation.y)
        _configure_video_annotation_item(item, annotation)
        return item
    if annotation.annotation_type in (Tool.TEXT, Tool.CALLOUT):
        text_style = str(annotation.payload.get("text_style", ""))
        if annotation.annotation_type == Tool.CALLOUT and not text_style:
            text_style = TEXT_STYLE_BUBBLE
        text_item = StyledTextItem(
            annotation.text,
            text_style=text_style or "plain",
            text_color=style.text_color,
            stroke_color=style.stroke_color,
            fill_color=style.fill_color,
            stroke_width=style.stroke_width,
        )
        text_item.setPos(annotation.x, annotation.y)
        _configure_video_annotation_item(text_item, annotation)
        return text_item
    if annotation.annotation_type == "image":
        from src.editor_canvas import decode_base64_to_pixmap

        encoded = str(annotation.payload.get("image_png_base64", ""))
        if not encoded:
            return None
        item = QGraphicsPixmapItem(decode_base64_to_pixmap(encoded))
        item.setPos(annotation.x, annotation.y)
        _configure_video_annotation_item(item, annotation)
        return item
    return None


class VideoCanvas(QGraphicsView):
    """
    Interactive video playback canvas with time-ranged annotation overlays.
    """

    position_changed = Signal(int)
    duration_changed = Signal(int)
    annotation_created = Signal(object)
    annotations_removed = Signal()
    tool_changed = Signal(str)
    content_changed = Signal()
    selection_style_changed = Signal(object)
    zoom_changed = Signal(float)

    ZOOM_MIN = 0.1
    ZOOM_MAX = 8.0
    ZOOM_STEP = 1.06

    def __init__(self) -> None:
        """
        Initializes the video canvas, player, and annotation scene.
        """

        super().__init__()
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setBackgroundBrush(QColor(20, 20, 20))

        self._video_item = QGraphicsVideoItem()
        self._video_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._video_item.setZValue(0.0)
        self._scene.addItem(self._video_item)

        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        # Playback starts muted; the video editor exposes an explicit Sound toggle.
        self._audio_output.setMuted(True)
        self._audio_output.setVolume(1.0)
        self._player.setAudioOutput(self._audio_output)
        self._player.setVideoOutput(self._video_item)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.mediaStatusChanged.connect(self._on_media_status_changed)

        self._tool = Tool.SELECT
        self._style = create_default_style_state()

        self._annotations: list[VideoAnnotationModel] = []
        self._visible_items: dict[str, QGraphicsItem] = {}
        self._position_ms = 0
        self._cached_duration_ms = 0
        self._drag_start = None
        self._preview_item: QGraphicsItem | None = None
        self._poly_points: list = []
        self._poly_preview: PolyPathItem | None = None
        self._first_frame_forced = False
        self._zoom_factor = 1.0
        self._initial_view_pending = True
        self._resize_overlay_item: CropSelectionItem | None = None
        self._resize_overlay_target: QGraphicsItem | None = None
        self._updating_resize_overlay = False
        from src.config import DEFAULT_RESIZE_HANDLE_POSITION, DEFAULT_RESIZE_HANDLE_SIZE

        self._resize_handle_size = float(DEFAULT_RESIZE_HANDLE_SIZE)
        self._resize_handle_position = DEFAULT_RESIZE_HANDLE_POSITION
        self._pending_selection_ids: frozenset[str] | None = None
        self._rebuilding_visible_items = False
        self._show_all_annotations = False
        self._rect_corner_radius = 0.0
        self._last_action_label = "Edit"
        self._scene.selectionChanged.connect(self._on_selection_changed)

    def load_video(self, path: str) -> None:
        """
        Loads a video file for playback and sizes the video item to its resolution.

        Args:
            path: Absolute path to the video file.

        Returns:
            None
        """

        self._first_frame_forced = False
        self._player.setSource(QUrl.fromLocalFile(path))

    def set_video_size(self, width: int, height: int) -> None:
        """
        Sets the video item's native pixel size for correct annotation alignment.

        Args:
            width: Video width in pixels.
            height: Video height in pixels.

        Returns:
            None
        """

        self._video_item.setSize(QSizeF(width, height))
        self._scene.setSceneRect(0, 0, width, height)
        self._initial_view_pending = True
        self._fit_scene_in_view()

    def import_image_file(self, file_path: str) -> bool:
        """
        Inserts one image overlay at the current playhead time range.

        Args:
            file_path: Local image file path.

        Returns:
            bool: True when the image was imported successfully.
        """

        from pathlib import Path

        from src.editor_canvas import encode_pixmap_to_base64
        from src.media_import import load_image_pixmap

        pixmap = load_image_pixmap(Path(file_path))
        if pixmap is None:
            return False

        scene_size = self._scene.sceneRect()
        width = float(pixmap.width())
        height = float(pixmap.height())
        x = max(0.0, (scene_size.width() - width) / 2.0)
        y = max(0.0, (scene_size.height() - height) / 2.0)
        self._finalize_annotation(
            "image",
            x,
            y,
            max(1.0, width),
            max(1.0, height),
            payload={"image_png_base64": encode_pixmap_to_base64(pixmap)},
        )
        return True

    def resizeEvent(self, event) -> None:
        """
        Keeps the video scaled to fit the viewport until the user zooms manually.

        Args:
            event: Qt resize event.

        Returns:
            None
        """

        super().resizeEvent(event)
        if self._initial_view_pending:
            self._fit_scene_in_view()

    def showEvent(self, event) -> None:
        """
        Re-fits the view once the widget has its real on-screen size.

        Returns:
            None
        """

        super().showEvent(event)
        if self._initial_view_pending:
            self._fit_scene_in_view()

    def _fit_scene_in_view(self) -> None:
        """
        Scales the view so the full video frame fits, preserving aspect ratio,
        and resets the tracked zoom factor to match.

        Returns:
            None
        """

        if self._scene.sceneRect().isEmpty():
            return
        viewport = self.viewport()
        if viewport is None or viewport.width() <= 1 or viewport.height() <= 1:
            return
        self.resetTransform()
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom_factor = self.transform().m11()
        self._initial_view_pending = False
        self.zoom_changed.emit(self._zoom_factor)

    def wheelEvent(self, event) -> None:
        """
        Zooms with Shift+wheel; otherwise keeps default scroll behavior.

        Args:
            event: Wheel event.

        Returns:
            None
        """

        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            delta = event.angleDelta().y()
            if delta == 0:
                delta = event.angleDelta().x()
            if delta > 0:
                self.zoom_in()
            elif delta < 0:
                self.zoom_out()
            event.accept()
            return
        super().wheelEvent(event)

    def zoom_in(self) -> None:
        """
        Zooms into the video canvas.

        Returns:
            None
        """

        self._apply_zoom(self.ZOOM_STEP)

    def zoom_out(self) -> None:
        """
        Zooms out of the video canvas.

        Returns:
            None
        """

        self._apply_zoom(1.0 / self.ZOOM_STEP)

    def reset_zoom(self) -> None:
        """
        Resets zoom to the default fit level.

        Returns:
            None
        """

        self._initial_view_pending = True
        self._fit_scene_in_view()

    def set_zoom_factor(self, target_zoom: float) -> None:
        """
        Sets zoom to an absolute factor value.

        Args:
            target_zoom: Target zoom factor (1.0 = 100%).

        Returns:
            None
        """

        bounded_zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, target_zoom))
        if abs(bounded_zoom - self._zoom_factor) < 0.0001:
            return
        scale_factor = bounded_zoom / self._zoom_factor
        self.scale(scale_factor, scale_factor)
        self._zoom_factor = bounded_zoom
        self._initial_view_pending = False
        self.zoom_changed.emit(self._zoom_factor)

    def _apply_zoom(self, factor: float) -> None:
        """
        Applies a multiplicative zoom factor.

        Args:
            factor: Scale factor.

        Returns:
            None
        """

        new_zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, self._zoom_factor * factor))
        if abs(new_zoom - self._zoom_factor) < 0.0001:
            return
        scale_factor = new_zoom / self._zoom_factor
        self.scale(scale_factor, scale_factor)
        self._zoom_factor = new_zoom
        self._initial_view_pending = False
        self.zoom_changed.emit(self._zoom_factor)

    def set_tool(self, tool: str) -> None:
        """
        Selects the active drawing tool.

        Args:
            tool: One of the Tool constants.

        Returns:
            None
        """

        if self._tool in POLY_DRAW_TOOLS and tool not in POLY_DRAW_TOOLS:
            self._cancel_poly_draw()
        if self._drag_start is not None:
            self._drag_start = None
            if self._preview_item is not None and self._preview_item.scene() is self._scene:
                self._scene.removeItem(self._preview_item)
            self._preview_item = None
        if tool != Tool.SELECT:
            self._clear_resize_overlay()
        previous_tool = self._tool
        self._tool = tool
        if tool == Tool.SELECT:
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        else:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
        if previous_tool != tool:
            self.tool_changed.emit(tool)
        self._update_style_color_context()

    def set_rect_corner_radius(self, radius: float) -> None:
        """
        Sets the default corner radius for new rectangle annotations.

        Args:
            radius: Corner radius in pixels.

        Returns:
            None
        """

        self._rect_corner_radius = max(0.0, float(radius))

    def consume_last_action_label(self) -> str:
        """
        Returns and resets the last recorded canvas action label.

        Returns:
            str: Action label used for one-shot tool handling.
        """

        label = self._last_action_label.strip() or "Edit"
        self._last_action_label = "Edit"
        return label

    def apply_style_to_selection(self, target: str, color: QColor) -> None:
        """
        Applies one style color to all currently selected annotations.

        Args:
            target: ``stroke``, ``fill``, or ``text``.
            color: Color to apply.

        Returns:
            None
        """

        kwargs = {
            "stroke": {"stroke_color": color},
            "fill": {"fill_color": color},
            "text": {"text_color": color},
        }.get(target, {})
        if kwargs:
            self.update_style(**kwargs, apply_to_selection=True, update_active_style=True)

    def set_style(self, style: StyleState) -> None:
        """
        Sets the style used for newly created annotations.

        Args:
            style: Style state to apply to new annotations.

        Returns:
            None
        """

        self._style = style

    def update_style(
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
        letter_spacing: float | None = None,
        line_spacing_factor: float | None = None,
        box_padding: float | None = None,
        corner_radius: float | None = None,
        stroke_style: str | None = None,
        text_style: str | None = None,
        *,
        apply_to_selection: bool = True,
        update_active_style: bool = True,
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
            letter_spacing: Optional letter spacing in pixels.
            line_spacing_factor: Optional line-spacing multiplier.
            box_padding: Optional text container padding in pixels.
            corner_radius: Optional text container corner radius in pixels.
            stroke_style: Optional line style name.
            text_style: Optional text container style.
            apply_to_selection: When False, only updates the active draw style.
            update_active_style: When False, only updates selected annotations.

        Returns:
            None
        """

        if update_active_style:
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
            if letter_spacing is not None:
                self._style.letter_spacing = float(letter_spacing)
            if line_spacing_factor is not None:
                self._style.line_spacing_factor = max(0.7, float(line_spacing_factor))
            if box_padding is not None:
                self._style.box_padding = max(0.0, float(box_padding))
            if corner_radius is not None:
                self._style.corner_radius = max(0.0, float(corner_radius))
            if stroke_style is not None:
                self._style.stroke_style = normalize_stroke_style(stroke_style)
            if text_style is not None:
                self._style.text_style = text_style

        if not apply_to_selection:
            return

        changed = False
        for item in self._scene.selectedItems():
            if item is self._resize_overlay_item or item is self._video_item:
                continue
            annotation_type = str(item.data(ITEM_ROLE_TYPE) or "")
            if bool(item.data(ITEM_ROLE_LOCKED) or False):
                continue
            if annotation_type in SHAPE_RECT_TYPES:
                shape_item = item
                if annotation_type in STAMP_MARK_TYPES:
                    mark_color = stroke_color if stroke_color is not None else fill_color
                    if mark_color is not None:
                        shape_item.setBrush(mark_color)
                        shape_item.setPen(create_stroke_pen(mark_color, 0.0))
                    changed = True
                    continue
                if stroke_color is not None:
                    pen = shape_item.pen()
                    pen.setColor(stroke_color)
                    shape_item.setPen(pen)
                if fill_color is not None:
                    shape_item.setBrush(fill_color)
                if stroke_width is not None:
                    shape_item.setPen(
                        apply_stroke_width_to_pen(
                            shape_item.pen(),
                            stroke_width,
                            stroke_style=stroke_style,
                        )
                    )
                elif stroke_style is not None and shape_item.pen().style() != Qt.PenStyle.NoPen:
                    pen = shape_item.pen()
                    pen.setStyle(stroke_style_to_qt(stroke_style))
                    shape_item.setPen(pen)
                changed = True
            elif annotation_type == "step" and isinstance(item, StepBadgeItem):
                if stroke_color is not None:
                    pen = item.pen()
                    pen.setColor(stroke_color)
                    item.setPen(pen)
                if fill_color is not None:
                    item.setBrush(fill_color)
                if stroke_width is not None:
                    item.setPen(
                        apply_stroke_width_to_pen(
                            item.pen(),
                            stroke_width,
                            stroke_style=stroke_style,
                        )
                    )
                changed = True
            elif annotation_type in SHAPE_LINE_TYPES:
                line_item = item
                pen = line_item.pen()
                if stroke_color is not None:
                    pen.setColor(stroke_color)
                if stroke_width is not None:
                    pen = apply_stroke_width_to_pen(
                        pen,
                        stroke_width,
                        stroke_style=stroke_style,
                    )
                elif stroke_style is not None and pen.style() != Qt.PenStyle.NoPen:
                    pen.setStyle(stroke_style_to_qt(stroke_style))
                line_item.setPen(pen)
                changed = True
            elif annotation_type in (Tool.TEXT, Tool.CALLOUT) and isinstance(item, StyledTextItem):
                if text_color is not None:
                    item.set_colors(text_color=text_color)
                if stroke_color is not None:
                    item.set_colors(stroke_color=stroke_color)
                if fill_color is not None:
                    item.set_colors(fill_color=fill_color)
                if stroke_width is not None:
                    item.set_stroke_width(float(stroke_width))
                if text_style is not None:
                    item.set_text_style(text_style)
                if (
                    font_size is not None
                    or font_family is not None
                    or font_bold is not None
                    or font_italic is not None
                    or font_underline is not None
                ):
                    font = QFont(item.font())
                    if font_size is not None:
                        font.setPointSize(max(1, int(font_size)))
                    if font_family is not None and font_family.strip():
                        font.setFamily(font_family.strip())
                    if font_bold is not None:
                        font.setBold(bool(font_bold))
                    if font_italic is not None:
                        font.setItalic(bool(font_italic))
                    if font_underline is not None:
                        font.setUnderline(bool(font_underline))
                    item.set_font(font)
                if (
                    letter_spacing is not None
                    or line_spacing_factor is not None
                    or box_padding is not None
                    or corner_radius is not None
                ):
                    item.set_layout_options(
                        letter_spacing=letter_spacing,
                        line_spacing_factor=line_spacing_factor,
                        box_padding=box_padding,
                        corner_radius=corner_radius,
                    )
                changed = True

        if changed and self._sync_visible_items_to_models():
            self.content_changed.emit()
        self._refresh_selection_style()

    def set_annotations(self, annotations: list[VideoAnnotationModel]) -> None:
        """
        Replaces the full annotation list and refreshes visible items.

        Args:
            annotations: Complete annotation list for the loaded video.

        Returns:
            None
        """

        self._annotations = annotations
        self._rebuild_visible_items()

    def annotations(self) -> list[VideoAnnotationModel]:
        """
        Returns the current annotation list.

        Returns:
            list[VideoAnnotationModel]: All annotations for the loaded video.
        """

        return self._annotations

    def refresh_visible_items(self) -> None:
        """
        Rebuilds the visible annotation items for the current playhead position.

        Returns:
            None
        """

        self._rebuild_visible_items()

    def show_all_annotations(self) -> bool:
        """
        Returns whether every annotation is shown regardless of playhead time.

        Returns:
            bool: True when all drawing objects are visible on the canvas.
        """

        return self._show_all_annotations

    def set_show_all_annotations(self, enabled: bool) -> None:
        """
        Shows every annotation on the canvas, ignoring timeline time ranges.

        Args:
            enabled: When True, all drawing objects stay visible for layout work.

        Returns:
            None
        """

        resolved = bool(enabled)
        if resolved == self._show_all_annotations:
            return
        self._show_all_annotations = resolved
        self._rebuild_visible_items()

    def position_ms(self) -> int:
        """
        Returns the current playhead position.

        Returns:
            int: Position in milliseconds.
        """

        return self._position_ms

    def duration_ms(self) -> int:
        """
        Returns the loaded video duration.

        Returns:
            int: Duration in milliseconds.
        """

        player_duration = self._player.duration()
        if player_duration > 0:
            return player_duration
        return self._cached_duration_ms

    def set_position(self, ms: int) -> None:
        """
        Seeks playback to one position.

        Args:
            ms: Target position in milliseconds.

        Returns:
            None
        """

        self._player.setPosition(ms)

    def is_audio_muted(self) -> bool:
        """
        Returns whether playback audio is currently muted.

        Returns:
            bool: True when muted.
        """

        return bool(self._audio_output.isMuted())

    def set_audio_muted(self, muted: bool) -> None:
        """
        Mutes or unmutes playback audio.

        Args:
            muted: True to mute, False to enable sound.

        Returns:
            None
        """

        self._audio_output.setMuted(bool(muted))

    def toggle_audio_muted(self) -> bool:
        """
        Toggles playback mute and returns the new muted state.

        Returns:
            bool: True when audio is muted after the toggle.
        """

        muted = not self.is_audio_muted()
        self.set_audio_muted(muted)
        return muted

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

    def _apply_resize_handle_style(self, overlay) -> None:
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

    def play(self) -> None:
        """
        Starts or resumes playback.

        Returns:
            None
        """

        self._player.play()

    def pause(self) -> None:
        """
        Pauses playback.

        Returns:
            None
        """

        self._player.pause()

    def _on_position_changed(self, ms: int) -> None:
        """
        Handles player position updates.

        Args:
            ms: New position in milliseconds.

        Returns:
            None
        """

        self._position_ms = ms
        self._rebuild_visible_items()
        self.position_changed.emit(ms)

    def _on_duration_changed(self, ms: int) -> None:
        """
        Handles player duration updates.

        Args:
            ms: New duration in milliseconds.

        Returns:
            None
        """

        if ms > 0:
            self._cached_duration_ms = ms
        self.duration_changed.emit(ms)

    def _on_media_status_changed(self, status) -> None:
        """
        Forces the first video frame to render once media finishes loading.

        Qt Multimedia only decodes/pushes a frame to the video item while
        actively playing, so a freshly loaded, never-played video shows a
        blank/black item. Starting playback and pausing again shortly after
        forces one frame to render without visibly starting playback; the
        pause is delayed slightly so the decoder has real wall-clock time to
        actually deliver a frame before playback stops.

        Args:
            status: New QMediaPlayer.MediaStatus value.

        Returns:
            None
        """

        if self._first_frame_forced:
            return
        if status not in (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        ):
            return
        self._first_frame_forced = True
        self._player.play()
        QTimer.singleShot(150, self._player.pause)

    def _annotation_visible_at_playhead(self, annotation: VideoAnnotationModel) -> bool:
        """
        Checks whether one annotation's timeline range includes the playhead.

        Args:
            annotation: Annotation to test.

        Returns:
            bool: True when the current playhead lies inside the annotation range.
        """

        return annotation.start_ms <= self._position_ms <= annotation.end_ms

    def _rebuild_visible_items(self) -> None:
        """
        Rebuilds canvas items for annotations active at the playhead, or all of them.

        Returns:
            None
        """

        if self._pending_selection_ids:
            selected_ids = set(self._pending_selection_ids)
        else:
            selected_ids = {
                str(item.data(ITEM_ROLE_ID))
                for item in self._scene.selectedItems()
                if item.data(ITEM_ROLE_ID)
            }

        self._sync_visible_items_to_models()

        self._rebuilding_visible_items = True
        try:
            self._clear_resize_overlay()

            for item in list(self._visible_items.values()):
                self._scene.removeItem(item)
            self._visible_items.clear()

            for annotation in self._annotations:
                if (
                    not self._show_all_annotations
                    and not self._annotation_visible_at_playhead(annotation)
                ):
                    continue
                item = build_annotation_item(annotation)
                if item is None:
                    continue
                if annotation.annotation_id in selected_ids:
                    item.setSelected(True)
                self._scene.addItem(item)
                self._visible_items[annotation.annotation_id] = item

            if self._pending_selection_ids:
                self._pending_selection_ids = None
        finally:
            self._rebuilding_visible_items = False

        self._on_selection_changed()

    def _next_step_number(self) -> int:
        """
        Returns the next unused step badge number for new annotations.

        Returns:
            int: Next step number.
        """

        used = {
            int(annotation.payload.get("step_number", 0) or 0)
            for annotation in self._annotations
            if annotation.annotation_type == Tool.STEP
        }
        number = 1
        while number in used:
            number += 1
        return number

    def _cancel_poly_draw(self) -> None:
        """
        Discards an in-progress multi-point annotation preview.

        Returns:
            None
        """

        if self._poly_preview is not None and self._poly_preview.scene() is self._scene:
            self._scene.removeItem(self._poly_preview)
        self._poly_preview = None
        self._poly_points = []

    def _refresh_selection_style(self) -> None:
        """
        Emits style details for the current canvas selection.

        Returns:
            None
        """

        selected = [
            item
            for item in self._scene.selectedItems()
            if item is not self._resize_overlay_item and item is not self._video_item
        ]
        if len(selected) != 1:
            self.selection_style_changed.emit({"type": "document"})
            return
        serialized = annotation_from_item(selected[0])
        if serialized is None:
            self.selection_style_changed.emit({"type": "document"})
            return
        self.selection_style_changed.emit(
            {
                "type": serialized.annotation_type,
                "stroke_rgba": serialized.stroke_rgba,
                "fill_rgba": serialized.fill_rgba,
            }
        )

    def _update_style_color_context(self) -> None:
        """
        Refreshes style-panel context after tool changes.

        Returns:
            None
        """

        if self._tool == Tool.SELECT:
            self._refresh_selection_style()
        else:
            self.selection_style_changed.emit({"type": "document"})

    def _annotation_item_at_view_pos(self, view_pos: QPoint) -> QGraphicsItem | None:
        """
        Returns the annotation under a view position, ignoring chrome overlays.

        Args:
            view_pos: View coordinate to inspect.

        Returns:
            QGraphicsItem | None: Drawable annotation item or None.
        """

        hit_item = self.itemAt(view_pos)
        if hit_item is None or hit_item is self._video_item:
            return None
        if hit_item is self._resize_overlay_item:
            return self._resize_overlay_target
        if not str(hit_item.data(ITEM_ROLE_ID) or ""):
            return None
        return hit_item

    def _handle_select_mouse_press(self, event: QMouseEvent) -> None:
        """
        Applies explicit single-click selection before default view drag handling.

        Args:
            event: Mouse press event.

        Returns:
            None
        """

        self.setFocus()
        modifiers = event.modifiers()
        if modifiers & (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
        ):
            super().mousePressEvent(event)
            return

        hit_item = self._annotation_item_at_view_pos(event.position().toPoint())
        if hit_item is None:
            self._scene.clearSelection()
            self._clear_resize_overlay()
            super().mousePressEvent(event)
            return

        self._scene.clearSelection()
        hit_item.setSelected(True)
        self._scene.setFocusItem(hit_item)
        super().mousePressEvent(event)
        if not hit_item.isSelected():
            hit_item.setSelected(True)
        self._on_selection_changed()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """
        Starts drawing a new annotation, or prompts for text at the click point.

        Args:
            event: Mouse press event.

        Returns:
            None
        """

        if event.button() != Qt.MouseButton.LeftButton or self._tool == Tool.SELECT:
            if event.button() == Qt.MouseButton.LeftButton and self._tool == Tool.SELECT:
                self._handle_select_mouse_press(event)
                return
            super().mousePressEvent(event)
            return

        scene_pos = self.mapToScene(event.position().toPoint())

        if self._tool == Tool.TEXT:
            text, accepted = QInputDialog.getText(self, "Insert Text", "Text:")
            if accepted and text:
                self._finalize_annotation(
                    Tool.TEXT,
                    scene_pos.x(),
                    scene_pos.y(),
                    0.0,
                    0.0,
                    text=text,
                )
            return

        if self._tool == Tool.STEP:
            from src.annotation_items import create_stroke_pen

            badge = StepBadgeItem(self._next_step_number())
            badge.setPen(
                create_stroke_pen(
                    QColor(self._style.stroke_color),
                    max(1.0, float(self._style.stroke_width) or 2.0),
                )
            )
            badge.setBrush(self._style.fill_color)
            badge.setPos(
                scene_pos.x() - badge.rect().width() / 2.0,
                scene_pos.y() - badge.rect().height() / 2.0,
            )
            bounds = badge.sceneBoundingRect()
            self._finalize_annotation(
                Tool.STEP,
                bounds.x(),
                bounds.y(),
                bounds.width(),
                bounds.height(),
                payload={"step_number": badge.step_number()},
            )
            return

        if self._tool == Tool.CALLOUT:
            text, accepted = QInputDialog.getText(self, "Insert Callout", "Text:")
            if accepted and text:
                self._finalize_annotation(
                    Tool.CALLOUT,
                    scene_pos.x(),
                    scene_pos.y(),
                    0.0,
                    0.0,
                    text=text,
                    payload={"text_style": TEXT_STYLE_BUBBLE},
                )
            return

        if self._tool in POLY_DRAW_TOOLS:
            self._append_poly_point(scene_pos)
            return

        if self._tool not in DRAG_TOOLS:
            super().mousePressEvent(event)
            return

        self._drag_start = scene_pos
        self._preview_item = self._create_preview_item(scene_pos)
        if self._preview_item is not None:
            self._scene.addItem(self._preview_item)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """
        Resizes the live preview item while dragging.

        Args:
            event: Mouse move event.

        Returns:
            None
        """

        if self._drag_start is None or self._preview_item is None:
            if self._tool in POLY_DRAW_TOOLS and self._poly_points:
                scene_pos = self.mapToScene(event.position().toPoint())
                self._update_poly_preview(scene_pos)
                event.accept()
                return
            if self._tool == Tool.SELECT:
                self._sync_resize_overlay_with_target()
            super().mouseMoveEvent(event)
            return

        scene_pos = self.mapToScene(event.position().toPoint())
        self._update_preview_item(scene_pos)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """
        Finalizes the drawn annotation as a new time-ranged model.

        Args:
            event: Mouse release event.

        Returns:
            None
        """

        if self._drag_start is None:
            super().mouseReleaseEvent(event)
            if self._tool == Tool.SELECT:
                if self._sync_visible_items_to_models():
                    self.content_changed.emit()
                selected = [
                    item
                    for item in self._scene.selectedItems()
                    if item is not self._resize_overlay_item
                ]
                if len(selected) == 1 and self._can_resize_item(selected[0]):
                    self._sync_resize_overlay_with_target(selected[0])
            return

        scene_pos = self.mapToScene(event.position().toPoint())
        start = self._drag_start
        self._drag_start = None
        if self._preview_item is not None:
            self._scene.removeItem(self._preview_item)
            self._preview_item = None

        x = min(start.x(), scene_pos.x())
        y = min(start.y(), scene_pos.y())
        width = abs(scene_pos.x() - start.x())
        height = abs(scene_pos.y() - start.y())
        if self._tool in DRAG_LINE_TOOLS:
            self._finalize_annotation(
                self._tool, start.x(), start.y(), scene_pos.x() - start.x(), scene_pos.y() - start.y()
            )
            return

        if width < 3 or height < 3:
            return
        payload: dict = {}
        if self._tool == Tool.SPOTLIGHT:
            payload = {"focus_mode": "ellipse", "dim_alpha": 150}
        if self._tool == Tool.RECT:
            payload["corner_radius"] = self._rect_corner_radius
        if self._style.stroke_style:
            payload["stroke_style"] = self._style.stroke_style
        self._finalize_annotation(self._tool, x, y, width, height, payload=payload)

    def _create_preview_item(self, scene_pos) -> QGraphicsItem | None:
        """
        Creates a live drag preview item for the active drawing tool.

        Args:
            scene_pos: Drag start position in scene coordinates.

        Returns:
            QGraphicsItem | None: Preview item, or None for tools without one.
        """

        pen = create_pen(self._style)
        if self._tool == Tool.RECT:
            item = PathShapeItem(
                "rect",
                QRectF(scene_pos, scene_pos),
                corner_radius=self._rect_corner_radius,
            )
            item.setPen(pen)
            item.setBrush(self._style.fill_color)
            return item
        if self._tool == Tool.ELLIPSE:
            item = QGraphicsEllipseItem(QRectF(scene_pos, scene_pos))
            item.setPen(pen)
            item.setBrush(self._style.fill_color)
            return item
        if self._tool in PATH_SHAPE_KINDS:
            from src.annotation_items import create_stroke_pen

            fill = self._style.fill_color
            stroke_pen = pen
            if self._tool in STAMP_MARK_TYPES:
                fill = self._style.stroke_color
                stroke_pen = create_stroke_pen(QColor(self._style.stroke_color), 0.0)
            item = PathShapeItem(self._tool, QRectF(scene_pos, scene_pos))
            item.setPen(stroke_pen)
            item.setBrush(fill)
            return item
        if self._tool == Tool.SPOTLIGHT:
            item = SpotlightItem(QRectF(scene_pos, scene_pos), focus_mode="ellipse")
            item.setPen(pen)
            return item
        if self._tool in DRAG_LINE_TOOLS:
            if self._tool == Tool.DOUBLE_ARROW:
                line_item = DoubleArrowItem()
            elif self._tool == Tool.ARROW:
                line_item = ArrowItem()
            else:
                line_item = StrokeLineItem()
            line_item.setLine(scene_pos.x(), scene_pos.y(), scene_pos.x(), scene_pos.y())
            line_item.setPen(pen)
            return line_item
        return None

    def _update_preview_item(self, scene_pos) -> None:
        """
        Updates the live preview item geometry while dragging.

        Args:
            scene_pos: Current drag position in scene coordinates.

        Returns:
            None
        """

        if self._drag_start is None or self._preview_item is None:
            return
        start = self._drag_start
        if isinstance(
            self._preview_item,
            (QGraphicsRectItem, QGraphicsEllipseItem, PathShapeItem, SpotlightItem),
        ):
            rect = QRectF(start, scene_pos).normalized()
            self._preview_item.setRect(rect)
        elif isinstance(self._preview_item, QGraphicsLineItem):
            self._preview_item.setLine(start.x(), start.y(), scene_pos.x(), scene_pos.y())

    def _finalize_annotation(
        self,
        annotation_type: str,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        text: str = "",
        payload: dict | None = None,
    ) -> None:
        """
        Creates and registers one new time-ranged annotation at the current playhead.

        Args:
            annotation_type: Tool identifier for the created annotation.
            x: Left position in video-pixel coordinates.
            y: Top position in video-pixel coordinates.
            width: Width in video-pixel coordinates.
            height: Height in video-pixel coordinates.
            text: Text content for text annotations.

        Returns:
            None
        """

        duration = max(1, self.duration_ms())
        start_ms = self._position_ms
        end_ms = min(duration, start_ms + DEFAULT_ANNOTATION_DURATION_MS)
        fill_color = self._style.fill_color
        if annotation_type in STAMP_MARK_TYPES:
            fill_color = self._style.stroke_color
        payload_data = dict(payload or {})
        if annotation_type == Tool.RECT:
            payload_data.setdefault("corner_radius", self._rect_corner_radius)
        if self._style.stroke_style:
            payload_data.setdefault("stroke_style", self._style.stroke_style)
        annotation = VideoAnnotationModel(
            annotation_type=annotation_type,
            start_ms=start_ms,
            end_ms=end_ms,
            x=x,
            y=y,
            width=width,
            height=height,
            stroke_rgba=[
                self._style.stroke_color.red(),
                self._style.stroke_color.green(),
                self._style.stroke_color.blue(),
                self._style.stroke_color.alpha(),
            ],
            fill_rgba=[
                fill_color.red(),
                fill_color.green(),
                fill_color.blue(),
                fill_color.alpha(),
            ],
            stroke_width=self._style.stroke_width,
            text=text,
            font_size=self._style.font_size,
            font_family=self._style.font_family,
            font_bold=self._style.font_bold,
            font_italic=self._style.font_italic,
            font_underline=self._style.font_underline,
            payload=dict(payload_data),
        )
        self._annotations.append(annotation)
        self._pending_selection_ids = frozenset({annotation.annotation_id})
        self._rebuild_visible_items()
        self._last_action_label = _DRAW_ACTION_LABELS.get(annotation_type, "Edit")
        self.annotation_created.emit(annotation)
        self.content_changed.emit()

    def _append_poly_point(self, scene_pos) -> None:
        """
        Adds one vertex while drawing a polyline, polygon, or bent arrow.

        Args:
            scene_pos: Vertex in scene coordinates.

        Returns:
            None
        """

        from src.shape_items import bounding_rect_from_points, points_to_payload

        if not self._poly_points:
            self._poly_points = [scene_pos]
            self._poly_preview = PolyPathItem(self._tool, self._poly_points)
            self._poly_preview.setPen(create_pen(self._style))
            self._poly_preview.setBrush(
                self._style.fill_color if self._tool == Tool.POLYGON else QColor(0, 0, 0, 0)
            )
            self._scene.addItem(self._poly_preview)
            return
        self._poly_points.append(scene_pos)
        if self._poly_preview is not None:
            self._poly_preview.set_points(self._poly_points)
        # Finish on returning close to the first point for polygons, or keep collecting.
        # Double-click is handled separately.

    def _update_poly_preview(self, cursor_scene_pos: QPointF) -> None:
        """
        Shows a rubber-band segment from the last committed vertex to the cursor.

        Args:
            cursor_scene_pos: Current cursor position in scene coordinates.

        Returns:
            None
        """

        if not self._poly_points or self._poly_preview is None:
            return
        preview_points = list(self._poly_points) + [cursor_scene_pos]
        self._poly_preview.set_points(preview_points)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """
        Finalizes an in-progress multi-point video annotation.

        Args:
            event: Mouse double-click event.

        Returns:
            None
        """

        if event.button() == Qt.MouseButton.LeftButton and self._tool in POLY_DRAW_TOOLS:
            self._finalize_poly_draw()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _finalize_poly_draw(self) -> None:
        """
        Commits the in-progress multi-point video annotation.

        Returns:
            None
        """

        from src.shape_items import bounding_rect_from_points, points_to_payload

        points = list(self._poly_points)
        kind = self._tool
        if self._poly_preview is not None and self._poly_preview.scene() is self._scene:
            self._scene.removeItem(self._poly_preview)
        self._poly_preview = None
        self._poly_points = []
        min_points = 3 if kind == Tool.POLYGON else 2
        if len(points) >= 2 and (points[-1] - points[-2]).manhattanLength() < 0.5:
            points = points[:-1]
        if len(points) < min_points:
            return
        bounds = bounding_rect_from_points(points)
        self._finalize_annotation(
            kind,
            bounds.x(),
            bounds.y(),
            bounds.width(),
            bounds.height(),
            payload={"points": points_to_payload(points)},
        )

    def _sync_visible_items_to_models(self) -> bool:
        """
        Writes current scene geometry from visible items back to annotation models.

        Returns:
            bool: True when at least one model was updated.
        """

        models_by_id = {
            annotation.annotation_id: annotation for annotation in self._annotations
        }
        changed = False
        for item in self._visible_items.values():
            annotation_id = str(item.data(ITEM_ROLE_ID) or "")
            if not annotation_id or annotation_id not in models_by_id:
                continue
            serialized = annotation_from_item(item)
            if serialized is None:
                continue
            model = models_by_id[annotation_id]
            if (
                model.x != serialized.x
                or model.y != serialized.y
                or model.width != serialized.width
                or model.height != serialized.height
                or model.text != serialized.text
                or model.payload != serialized.payload
            ):
                model.x = serialized.x
                model.y = serialized.y
                model.width = serialized.width
                model.height = serialized.height
                model.text = serialized.text
                model.payload = dict(serialized.payload)
                changed = True
        return changed

    def _on_selection_changed(self) -> None:
        """
        Shows resize handles for a single selected annotation in Select mode.

        Returns:
            None
        """

        if self._rebuilding_visible_items:
            return

        if self._tool != Tool.SELECT:
            self._clear_resize_overlay()
            return

        selected = [
            item
            for item in self._scene.selectedItems()
            if item is not self._resize_overlay_item
        ]
        if len(selected) != 1:
            self._clear_resize_overlay()
            return
        item = selected[0]
        if self._can_resize_item(item):
            self._sync_resize_overlay_with_target(item)
        else:
            self._clear_resize_overlay()
        self._refresh_selection_style()

    def _can_resize_item(self, item: QGraphicsItem) -> bool:
        """
        Checks whether one annotation supports interactive resize handles.

        Args:
            item: Scene item to evaluate.

        Returns:
            bool: True when resize handles should be shown.
        """

        annotation_type = str(item.data(ITEM_ROLE_TYPE) or "")
        return annotation_type in (SHAPE_RECT_TYPES | SHAPE_LINE_TYPES | {Tool.TEXT, Tool.CALLOUT})

    def _target_geometry_rect(self, item: QGraphicsItem) -> QRectF:
        """
        Returns geometry bounds for one annotation without pen inflation artifacts.

        Args:
            item: Scene item.

        Returns:
            QRectF: Geometry rectangle in scene coordinates.
        """

        annotation_type = str(item.data(ITEM_ROLE_TYPE) or "")
        if annotation_type in SHAPE_RECT_TYPES:
            return item.mapRectToScene(item.rect()).normalized()
        if annotation_type in SHAPE_LINE_TYPES:
            line = item.line()
            p1 = item.mapToScene(line.p1())
            p2 = item.mapToScene(line.p2())
            return QRectF(p1, p2).normalized()
        return item.sceneBoundingRect().normalized()

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
            selected = [
                item
                for item in self._scene.selectedItems()
                if item is not self._resize_overlay_item
            ]
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
            overlay.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            overlay.set_always_show_handles(True)
            overlay.set_aspect_ratio_lock_enabled(True)
            overlay.set_interior_interactive(False)
            overlay.on_geometry_changed = self._apply_resize_overlay_to_target
            overlay.setZValue(1400)
            self._scene.addItem(overlay)
            self._resize_overlay_item = overlay
        else:
            self._updating_resize_overlay = True
            self._resize_overlay_item.set_interior_interactive(False)
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

    def _apply_resize_overlay_to_target(self) -> None:
        """
        Applies resize-handle geometry changes back to the selected target item.

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
        if self._sync_visible_items_to_models():
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

        if annotation_type in SHAPE_RECT_TYPES:
            target.setPos(new_rect.topLeft())
            target.setRect(QRectF(0.0, 0.0, new_rect.width(), new_rect.height()))
            return True

        if annotation_type in SHAPE_LINE_TYPES:
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

        if annotation_type in {Tool.TEXT, Tool.CALLOUT}:
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

        return False

    def _selected_annotation_items(self) -> list[QGraphicsItem]:
        """
        Returns selected scene items that represent a drawn annotation.

        Returns:
            list[QGraphicsItem]: Selected annotation items, excluding canvas chrome.
        """

        return [
            item
            for item in self._scene.selectedItems()
            if item is not self._resize_overlay_item
            and item is not self._video_item
            and item.data(ITEM_ROLE_ID)
        ]

    def has_selected_annotations(self) -> bool:
        """
        Indicates whether at least one drawn object is currently selected.

        Returns:
            bool: True when a selection exists.
        """

        return bool(self._selected_annotation_items())

    def collect_selected_annotations(self) -> list[VideoAnnotationModel]:
        """
        Serializes currently selected annotations for copy-to-clipboard.

        Returns:
            list[VideoAnnotationModel]: Copies of the selected annotation models.
        """

        self._sync_visible_items_to_models()
        selected_ids = [
            str(item.data(ITEM_ROLE_ID) or "") for item in self._selected_annotation_items()
        ]
        models_by_id = {annotation.annotation_id: annotation for annotation in self._annotations}
        result: list[VideoAnnotationModel] = []
        for annotation_id in selected_ids:
            model = models_by_id.get(annotation_id)
            if model is not None:
                result.append(VideoAnnotationModel.from_dict(model.to_dict()))
        return result

    def merge_annotations_payload(self, source_annotations: list[VideoAnnotationModel]) -> bool:
        """
        Pastes copied annotations into this canvas near the playhead and viewport center.

        Args:
            source_annotations: Annotations copied from this or another video tab.

        Returns:
            bool: True when at least one annotation was pasted.
        """

        if not source_annotations:
            return False

        source_bounds = QRectF()
        for annotation in source_annotations:
            item_rect = QRectF(
                float(annotation.x),
                float(annotation.y),
                max(1.0, float(annotation.width)),
                max(1.0, float(annotation.height)),
            )
            source_bounds = item_rect if source_bounds.isNull() else source_bounds.united(item_rect)

        center_scene = self.mapToScene(self.viewport().rect().center())
        desired_top_left = QPointF(
            center_scene.x() - (source_bounds.width() / 2.0),
            center_scene.y() - (source_bounds.height() / 2.0),
        )
        spatial_offset = desired_top_left - source_bounds.topLeft()

        duration = max(1, self.duration_ms())
        earliest_start_ms = min(annotation.start_ms for annotation in source_annotations)
        time_offset = self._position_ms - earliest_start_ms

        pasted_ids: set[str] = set()
        for annotation in source_annotations:
            span = max(0, annotation.end_ms - annotation.start_ms)
            start_ms = max(0, min(duration, annotation.start_ms + time_offset))
            end_ms = max(start_ms, min(duration, start_ms + span))
            pasted = VideoAnnotationModel(
                annotation_type=annotation.annotation_type,
                start_ms=start_ms,
                end_ms=end_ms,
                x=float(annotation.x + spatial_offset.x()),
                y=float(annotation.y + spatial_offset.y()),
                width=float(annotation.width),
                height=float(annotation.height),
                stroke_rgba=list(annotation.stroke_rgba),
                fill_rgba=list(annotation.fill_rgba),
                stroke_width=float(annotation.stroke_width),
                text=str(annotation.text),
                font_size=int(annotation.font_size),
                font_family=str(annotation.font_family),
                font_bold=bool(annotation.font_bold),
                font_italic=bool(annotation.font_italic),
                font_underline=bool(annotation.font_underline),
                payload=copy.deepcopy(annotation.payload),
            )
            self._annotations.append(pasted)
            pasted_ids.add(pasted.annotation_id)
            self.annotation_created.emit(pasted)

        self._pending_selection_ids = frozenset(pasted_ids)
        self._rebuild_visible_items()
        self._last_action_label = "Paste selection"
        self.content_changed.emit()
        return True

    def delete_selected_annotations(self) -> bool:
        """
        Removes all currently selected annotation models from the timeline.

        Returns:
            bool: True when at least one annotation was deleted.
        """

        selected = self._selected_annotation_items()
        if not selected:
            return False

        ids_to_remove = {
            str(item.data(ITEM_ROLE_ID) or "")
            for item in selected
            if not bool(item.data(ITEM_ROLE_LOCKED) or False)
        }
        if not ids_to_remove:
            return False

        remaining = [
            annotation
            for annotation in self._annotations
            if annotation.annotation_id not in ids_to_remove
        ]
        if len(remaining) == len(self._annotations):
            return False

        self._annotations[:] = remaining
        self._clear_resize_overlay()
        self._rebuild_visible_items()
        return True

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """
        Handles keyboard shortcuts for poly draw, delete, and cancel.

        Args:
            event: Key press event.

        Returns:
            None
        """

        if event.key() == Qt.Key.Key_Escape:
            if self._poly_points:
                self._cancel_poly_draw()
                event.accept()
                return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._tool in POLY_DRAW_TOOLS and self._poly_points:
                self._finalize_poly_draw()
                event.accept()
                return
        if event.key() == Qt.Key.Key_Delete:
            if self.delete_selected_annotations():
                self._last_action_label = "Delete selection"
                self.annotations_removed.emit()
                self.content_changed.emit()
                event.accept()
                return
        super().keyPressEvent(event)
