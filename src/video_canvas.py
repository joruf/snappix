"""
Video playback and time-ranged annotation canvas for the Snappix video editor.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSizeF, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QInputDialog,
)

from src.annotation_items import ArrowItem, StrokeLineItem, StyleState, create_pen, list_to_color
from src.annotation_shapes import StyledTextItem
from src.video_models import VideoAnnotationModel

DEFAULT_ANNOTATION_DURATION_MS = 3000


class Tool:
    """
    Defines the drawing tools available in the video editor.
    """

    SELECT = "select"
    RECT = "rect"
    ELLIPSE = "ellipse"
    LINE = "line"
    ARROW = "arrow"
    TEXT = "text"


DRAG_TOOLS = frozenset({Tool.RECT, Tool.ELLIPSE, Tool.LINE, Tool.ARROW})


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
    )


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
        item = QGraphicsRectItem(rect)
        item.setPen(pen)
        item.setBrush(style.fill_color)
        return item
    if annotation.annotation_type == Tool.ELLIPSE:
        item = QGraphicsEllipseItem(rect)
        item.setPen(pen)
        item.setBrush(style.fill_color)
        return item
    if annotation.annotation_type in (Tool.LINE, Tool.ARROW):
        line_item = ArrowItem() if annotation.annotation_type == Tool.ARROW else StrokeLineItem()
        line_item.setLine(
            annotation.x,
            annotation.y,
            annotation.x + annotation.width,
            annotation.y + annotation.height,
        )
        line_item.setPen(pen)
        return line_item
    if annotation.annotation_type == Tool.TEXT:
        text_item = StyledTextItem(
            annotation.text,
            text_color=style.text_color,
            stroke_color=style.stroke_color,
            fill_color=style.fill_color,
            stroke_width=style.stroke_width,
        )
        text_item.setPos(annotation.x, annotation.y)
        return text_item
    return None


class VideoCanvas(QGraphicsView):
    """
    Interactive video playback canvas with time-ranged annotation overlays.
    """

    position_changed = Signal(int)
    duration_changed = Signal(int)
    annotation_created = Signal(object)
    content_changed = Signal()
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
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setBackgroundBrush(QColor(20, 20, 20))

        self._video_item = QGraphicsVideoItem()
        self._scene.addItem(self._video_item)

        self._player = QMediaPlayer(self)
        self._player.setVideoOutput(self._video_item)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.mediaStatusChanged.connect(self._on_media_status_changed)

        self._tool = Tool.SELECT
        self._style = StyleState(
            stroke_color=QColor(231, 76, 60, 255),
            fill_color=QColor(231, 76, 60, 70),
            text_color=QColor(44, 62, 80, 255),
            stroke_width=3,
            font_size=16,
            font_family="",
            font_bold=False,
            font_italic=False,
            font_underline=False,
        )

        self._annotations: list[VideoAnnotationModel] = []
        self._visible_items: dict[str, QGraphicsItem] = {}
        self._position_ms = 0
        self._drag_start = None
        self._preview_item: QGraphicsItem | None = None
        self._first_frame_forced = False
        self._zoom_factor = 1.0
        self._initial_view_pending = True

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

        self._tool = tool

    def set_style(self, style: StyleState) -> None:
        """
        Sets the style used for newly created annotations.

        Args:
            style: Style state to apply to new annotations.

        Returns:
            None
        """

        self._style = style

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

        return self._player.duration()

    def set_position(self, ms: int) -> None:
        """
        Seeks playback to one position.

        Args:
            ms: Target position in milliseconds.

        Returns:
            None
        """

        self._player.setPosition(ms)

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

    def _rebuild_visible_items(self) -> None:
        """
        Shows only the annotations whose time range covers the current position.

        Returns:
            None
        """

        for item in list(self._visible_items.values()):
            self._scene.removeItem(item)
        self._visible_items.clear()

        for annotation in self._annotations:
            if not (annotation.start_ms <= self._position_ms <= annotation.end_ms):
                continue
            item = build_annotation_item(annotation)
            if item is None:
                continue
            self._scene.addItem(item)
            self._visible_items[annotation.annotation_id] = item

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """
        Starts drawing a new annotation, or prompts for text at the click point.

        Args:
            event: Mouse press event.

        Returns:
            None
        """

        if event.button() != Qt.MouseButton.LeftButton or self._tool == Tool.SELECT:
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
        if self._tool in (Tool.LINE, Tool.ARROW):
            self._finalize_annotation(
                self._tool, start.x(), start.y(), scene_pos.x() - start.x(), scene_pos.y() - start.y()
            )
            return

        if width < 3 or height < 3:
            return
        self._finalize_annotation(self._tool, x, y, width, height)

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
            item = QGraphicsRectItem(QRectF(scene_pos, scene_pos))
            item.setPen(pen)
            item.setBrush(self._style.fill_color)
            return item
        if self._tool == Tool.ELLIPSE:
            item = QGraphicsEllipseItem(QRectF(scene_pos, scene_pos))
            item.setPen(pen)
            item.setBrush(self._style.fill_color)
            return item
        if self._tool in (Tool.LINE, Tool.ARROW):
            line_item = ArrowItem() if self._tool == Tool.ARROW else StrokeLineItem()
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
        if isinstance(self._preview_item, (QGraphicsRectItem, QGraphicsEllipseItem)):
            rect = QRectF(start, scene_pos).normalized()
            self._preview_item.setRect(rect)
        elif isinstance(self._preview_item, StrokeLineItem):
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
                self._style.fill_color.red(),
                self._style.fill_color.green(),
                self._style.fill_color.blue(),
                self._style.fill_color.alpha(),
            ],
            stroke_width=self._style.stroke_width,
            text=text,
            font_size=self._style.font_size,
            font_family=self._style.font_family,
            font_bold=self._style.font_bold,
            font_italic=self._style.font_italic,
            font_underline=self._style.font_underline,
        )
        self._annotations.append(annotation)
        self._rebuild_visible_items()
        self.annotation_created.emit(annotation)
        self.content_changed.emit()
