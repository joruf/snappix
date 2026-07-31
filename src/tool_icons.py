"""
Vector tool icons for Snappix editor toolbars.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, QSize
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF

from src.editor_canvas import Tool
from src.theme import get_editor_accent_colors


def build_tool_icon(tool: str, *, locked: bool = False) -> QIcon:
    """
    Builds a vector icon for one toolbar drawing tool.

    Args:
        tool: Tool identifier.
        locked: True to overlay a lock badge on the icon.

    Returns:
        QIcon: Rendered icon.
    """

    size = 28
    scale = size / 18.0
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.scale(scale, scale)

    stroke_pen = QPen(QColor("#d7e3f1"), 1.6)
    accent_pen = QPen(QColor(get_editor_accent_colors()[0]), 1.6)

    if tool == Tool.SELECT:
        painter.setPen(stroke_pen)
        pointer_shape = QPolygonF(
            [
                QPointF(3.0, 2.5),
                QPointF(3.0, 14.5),
                QPointF(7.0, 10.8),
                QPointF(10.8, 15.5),
                QPointF(12.4, 14.1),
                QPointF(8.6, 9.6),
                QPointF(14.5, 9.2),
            ]
        )
        painter.drawPolygon(pointer_shape)
    elif tool == Tool.RECT:
        painter.setPen(stroke_pen)
        painter.setBrush(QBrush(QColor(74, 163, 255, 70)))
        painter.drawRect(QRectF(3.0, 4.0, 12.0, 10.0))
    elif tool == Tool.ELLIPSE:
        painter.setPen(stroke_pen)
        painter.setBrush(QBrush(QColor(74, 163, 255, 70)))
        painter.drawEllipse(QRectF(3.0, 4.0, 12.0, 10.0))
    elif tool == Tool.TRIANGLE:
        painter.setPen(stroke_pen)
        painter.setBrush(QBrush(QColor(74, 163, 255, 70)))
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(9.0, 3.0),
                    QPointF(15.0, 14.0),
                    QPointF(3.0, 14.0),
                ]
            )
        )
    elif tool == Tool.STAR:
        painter.setPen(stroke_pen)
        painter.setBrush(QBrush(QColor(241, 196, 15, 160)))
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(9.0, 2.5),
                    QPointF(10.5, 7.0),
                    QPointF(15.0, 7.2),
                    QPointF(11.4, 10.0),
                    QPointF(12.7, 14.5),
                    QPointF(9.0, 12.0),
                    QPointF(5.3, 14.5),
                    QPointF(6.6, 10.0),
                    QPointF(3.0, 7.2),
                    QPointF(7.5, 7.0),
                ]
            )
        )
    elif tool == Tool.POLYGON:
        # Irregular freeform outline with vertex dots (not a regular pentagon).
        painter.setPen(stroke_pen)
        painter.setBrush(QBrush(QColor(74, 163, 255, 70)))
        polygon_points = [
            QPointF(3.0, 5.5),
            QPointF(7.5, 2.5),
            QPointF(14.5, 4.0),
            QPointF(12.5, 10.5),
            QPointF(15.0, 14.5),
            QPointF(8.0, 13.0),
            QPointF(3.5, 14.0),
        ]
        painter.drawPolygon(QPolygonF(polygon_points))
        painter.setBrush(QBrush(QColor("#d7e3f1")))
        painter.setPen(QPen(QColor("#8fa3b8"), 0.8))
        for point in polygon_points:
            painter.drawEllipse(point, 1.15, 1.15)
    elif tool == Tool.LINE:
        painter.setPen(stroke_pen)
        painter.drawLine(3, 14, 15, 4)
    elif tool == Tool.POLYLINE:
        painter.setPen(stroke_pen)
        painter.drawPolyline(
            QPolygonF(
                [
                    QPointF(3.0, 13.0),
                    QPointF(7.0, 6.0),
                    QPointF(11.0, 11.0),
                    QPointF(15.0, 4.0),
                ]
            )
        )
    elif tool == Tool.ARROW:
        painter.setPen(accent_pen)
        painter.drawLine(3, 14, 13, 5)
        painter.drawLine(13, 5, 11, 5)
        painter.drawLine(13, 5, 13, 7)
    elif tool == Tool.DOUBLE_ARROW:
        painter.setPen(accent_pen)
        painter.drawLine(4, 14, 14, 4)
        painter.drawLine(4, 14, 4, 11)
        painter.drawLine(4, 14, 7, 14)
        painter.drawLine(14, 4, 14, 7)
        painter.drawLine(14, 4, 11, 4)
    elif tool == Tool.BENT_ARROW:
        painter.setPen(accent_pen)
        painter.drawPolyline(
            QPolygonF(
                [
                    QPointF(3.0, 13.0),
                    QPointF(3.0, 6.0),
                    QPointF(12.0, 6.0),
                ]
            )
        )
        painter.drawLine(12, 6, 10, 4)
        painter.drawLine(12, 6, 10, 8)
    elif tool == Tool.SPOTLIGHT:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 140)))
        painter.drawRect(QRectF(2.0, 2.0, 14.0, 14.0))
        painter.setBrush(QBrush(QColor(0, 0, 0, 0)))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.drawEllipse(QRectF(5.0, 5.0, 8.0, 8.0))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setPen(QPen(QColor("#f1c40f"), 1.3))
        painter.drawEllipse(QRectF(5.0, 5.0, 8.0, 8.0))
    elif tool == Tool.CROSS:
        painter.setPen(QPen(QColor("#e74c3c"), 2.0))
        painter.drawLine(4, 4, 14, 14)
        painter.drawLine(14, 4, 4, 14)
    elif tool == Tool.CHECKMARK:
        painter.setPen(QPen(QColor("#27ae60"), 2.0))
        painter.drawPolyline(
            QPolygonF(
                [
                    QPointF(3.5, 9.5),
                    QPointF(7.5, 13.5),
                    QPointF(14.5, 4.5),
                ]
            )
        )
    elif tool == Tool.TEXT:
        painter.setPen(stroke_pen)
        text_font = painter.font()
        text_font.setBold(True)
        text_font.setPointSize(10)
        painter.setFont(text_font)
        painter.drawText(QRectF(2.0, 1.0, 14.0, 16.0), "T")
    elif tool == Tool.CALLOUT:
        painter.setPen(stroke_pen)
        painter.setBrush(QBrush(QColor(255, 255, 255, 220)))
        painter.drawRoundedRect(QRectF(2.5, 2.5, 13.0, 9.0), 2.0, 2.0)
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(5.0, 11.0),
                    QPointF(8.0, 11.0),
                    QPointF(6.0, 15.0),
                ]
            )
        )
    elif tool == Tool.FILL_BG:
        painter.setPen(stroke_pen)
        painter.setBrush(QBrush(QColor(74, 163, 255, 100)))
        painter.drawRect(QRectF(2.5, 9.0, 13.0, 6.0))
        painter.drawLine(5, 8, 9, 4)
        painter.drawLine(9, 4, 12, 7)
    elif tool == Tool.SELECT_RECT:
        painter.setPen(QPen(QColor("#f5f5f5"), 1.4, Qt.PenStyle.DashLine))
        painter.setBrush(QBrush(QColor(52, 152, 219, 60)))
        painter.drawRect(QRectF(3.0, 4.0, 12.0, 10.0))
    elif tool == Tool.SELECT_ELLIPSE:
        painter.setPen(QPen(QColor("#f5f5f5"), 1.4, Qt.PenStyle.DashLine))
        painter.setBrush(QBrush(QColor(52, 152, 219, 60)))
        painter.drawEllipse(QRectF(3.0, 4.0, 12.0, 10.0))
    elif tool == Tool.SELECT_PATH:
        painter.setPen(QPen(QColor("#f5f5f5"), 1.4, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolyline(
            QPolygonF(
                [
                    QPointF(3.0, 12.0),
                    QPointF(6.0, 5.0),
                    QPointF(11.0, 8.0),
                    QPointF(15.0, 4.0),
                ]
            )
        )
    elif tool == Tool.MAGIC_WAND:
        wand_pen = QPen(QColor("#f5d76e"), 1.8)
        wand_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(wand_pen)
        painter.drawLine(QPointF(4.5, 15.0), QPointF(11.5, 7.0))
        star_center = QPointF(12.5, 5.0)
        star_points = QPolygonF(
            [
                QPointF(star_center.x(), star_center.y() - 3.6),
                QPointF(star_center.x() + 1.0, star_center.y() - 1.0),
                QPointF(star_center.x() + 3.6, star_center.y()),
                QPointF(star_center.x() + 1.0, star_center.y() + 1.0),
                QPointF(star_center.x(), star_center.y() + 3.6),
                QPointF(star_center.x() - 1.0, star_center.y() + 1.0),
                QPointF(star_center.x() - 3.6, star_center.y()),
                QPointF(star_center.x() - 1.0, star_center.y() - 1.0),
            ]
        )
        painter.setPen(QPen(QColor("#f7e27a"), 1.0))
        painter.setBrush(QBrush(QColor("#f1c40f")))
        painter.drawPolygon(star_points)
        spark_pen = QPen(QColor("#fff6c2"), 1.2)
        spark_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(spark_pen)
        painter.drawLine(QPointF(15.2, 2.2), QPointF(16.4, 1.0))
        painter.drawLine(QPointF(15.8, 4.8), QPointF(17.0, 4.8))
        painter.drawLine(QPointF(13.8, 1.4), QPointF(13.8, 0.2))
    elif tool == Tool.BRUSH:
        painter.setPen(stroke_pen)
        painter.setBrush(QBrush(QColor(74, 163, 255, 180)))
        painter.drawEllipse(QRectF(4.0, 3.0, 5.0, 5.0))
        painter.drawLine(6, 8, 13, 15)
    elif tool == Tool.ERASER:
        painter.setPen(stroke_pen)
        painter.setBrush(QBrush(QColor(236, 240, 241, 220)))
        painter.drawRoundedRect(QRectF(4.0, 5.0, 10.0, 8.0), 1.5, 1.5)
        painter.drawLine(5, 7, 13, 7)
    elif tool == Tool.BUCKET:
        painter.setPen(stroke_pen)
        painter.setBrush(QBrush(QColor(74, 163, 255, 120)))
        painter.drawRect(QRectF(4.0, 7.0, 9.0, 7.0))
        painter.drawLine(7, 7, 10, 3)
    elif tool == Tool.EYEDROPPER:
        painter.setPen(QPen(QColor("#f5f5f5"), 1.6))
        painter.drawLine(QPointF(5.0, 14.0), QPointF(11.0, 8.0))
        painter.setBrush(QBrush(QColor("#e74c3c")))
        painter.drawEllipse(QRectF(10.0, 3.0, 5.0, 5.0))
    elif tool == Tool.BLUR:
        painter.setPen(QPen(QColor("#c39bd3"), 1.6))
        painter.setBrush(QBrush(QColor(155, 89, 182, 120)))
        painter.drawRect(QRectF(3.0, 3.0, 5.0, 5.0))
        painter.drawRect(QRectF(9.0, 3.0, 5.0, 5.0))
        painter.drawRect(QRectF(3.0, 9.0, 5.0, 5.0))
        painter.drawRect(QRectF(9.0, 9.0, 5.0, 5.0))
    elif tool == Tool.STEP:
        painter.setPen(stroke_pen)
        painter.setBrush(QBrush(QColor(231, 76, 60, 230)))
        painter.drawEllipse(QRectF(3.0, 3.0, 12.0, 12.0))
        painter.setPen(QColor(255, 255, 255, 255))
        painter.drawText(
            QRectF(3.0, 2.0, 12.0, 14.0),
            int(Qt.AlignmentFlag.AlignCenter),
            "1",
        )
    elif tool == Tool.OCR:
        painter.setPen(QPen(QColor("#2ecc71"), 1.6))
        text_font = painter.font()
        text_font.setBold(True)
        text_font.setPointSize(8)
        painter.setFont(text_font)
        painter.drawText(QRectF(1.0, 2.0, 16.0, 14.0), "OCR")
    elif tool == Tool.CROP:
        painter.setPen(accent_pen)
        painter.drawLine(3, 3, 9, 3)
        painter.drawLine(3, 3, 3, 9)
        painter.drawLine(15, 15, 9, 15)
        painter.drawLine(15, 15, 15, 9)
        painter.setPen(stroke_pen)
        painter.drawRect(QRectF(5.0, 5.0, 8.0, 8.0))
    else:
        painter.setPen(stroke_pen)
        painter.drawRect(QRectF(4.0, 4.0, 10.0, 10.0))

    if locked:
        painter.resetTransform()
        badge_bg = QColor(20, 24, 32, 230)
        badge_pen = QPen(QColor("#f1c40f"), 1.2)
        painter.setPen(badge_pen)
        painter.setBrush(QBrush(badge_bg))
        body = QRectF(size - 10.0, size - 8.5, 8.5, 6.5)
        painter.drawRoundedRect(body, 1.2, 1.2)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        shackle = QRectF(size - 8.4, size - 12.2, 5.2, 5.0)
        painter.drawArc(shackle, 0 * 16, 180 * 16)

    painter.end()
    return QIcon(pixmap)


ZOOM_STEP_FONT_POINT_SIZE = 13


def apply_zoom_step_button_style(button) -> None:
    """
    Makes a zoom +/- button's glyph large enough to read at a glance.

    At the default toolbar font a bare "+" renders as a few faint pixels and is
    easy to miss beside the much wider zoom slider.

    Args:
        button: Zoom step button to restyle.

    Returns:
        None
    """

    font = button.font()
    font.setPointSize(ZOOM_STEP_FONT_POINT_SIZE)
    font.setBold(True)
    button.setFont(font)
    button.setFixedWidth(30)


def build_zoom_reset_icon(color: QColor) -> QIcon:
    """
    Draws a circular reset arrow used in place of a "Reset" text button.

    Args:
        color: Stroke color for the glyph.

    Returns:
        QIcon: Reset icon.
    """

    pixmap = QPixmap(QSize(18, 18))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(color, 2.0)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    # Open circle, leaving a gap where the arrow head goes.
    painter.drawArc(QRectF(3.0, 3.0, 12.0, 12.0), 55 * 16, 275 * 16)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(color))
    painter.drawPolygon(
        QPolygonF(
            [
                QPointF(11.4, 1.2),
                QPointF(16.4, 4.6),
                QPointF(10.8, 6.2),
            ]
        )
    )
    painter.end()
    return QIcon(pixmap)


def build_playback_icon(icon_id: str) -> QIcon:
    """
    Builds one vector icon for video playback controls.

    Args:
        icon_id: One of ``play``, ``pause``, ``stop``, ``sound_on``, ``sound_off``.

    Returns:
        QIcon: Rendered icon.
    """

    size = 28
    scale = size / 18.0
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.scale(scale, scale)

    stroke_pen = QPen(QColor("#d7e3f1"), 1.6)
    accent_pen = QPen(QColor(get_editor_accent_colors()[0]), 1.6)
    painter.setPen(stroke_pen)
    painter.setBrush(QBrush(QColor(74, 163, 255, 90)))

    if icon_id == "play":
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(5.5, 3.5),
                    QPointF(5.5, 14.5),
                    QPointF(14.5, 9.0),
                ]
            )
        )
    elif icon_id == "pause":
        painter.setBrush(QBrush(QColor("#d7e3f1")))
        painter.drawRect(QRectF(4.5, 3.5, 3.2, 11.0))
        painter.drawRect(QRectF(10.3, 3.5, 3.2, 11.0))
    elif icon_id == "stop":
        painter.setBrush(QBrush(QColor("#d7e3f1")))
        painter.drawRect(QRectF(4.5, 4.5, 9.0, 9.0))
    elif icon_id in {"sound_on", "sound_off"}:
        painter.setBrush(QBrush(QColor("#d7e3f1")))
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(3.0, 7.0),
                    QPointF(6.0, 7.0),
                    QPointF(10.0, 4.0),
                    QPointF(10.0, 14.0),
                    QPointF(6.0, 11.0),
                    QPointF(3.0, 11.0),
                ]
            )
        )
        if icon_id == "sound_on":
            painter.setPen(accent_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(QRectF(10.5, 6.0, 4.0, 6.0), 300 * 16, 120 * 16)
            painter.drawArc(QRectF(12.0, 4.5, 5.0, 9.0), 300 * 16, 120 * 16)
        else:
            painter.setPen(QPen(QColor("#e74c3c"), 1.8))
            painter.drawLine(11.0, 5.0, 15.5, 13.0)
            painter.drawLine(15.5, 5.0, 11.0, 13.0)
    else:
        painter.drawRect(QRectF(4.0, 4.0, 10.0, 10.0))

    painter.end()
    return QIcon(pixmap)

