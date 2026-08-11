"""
Vector icons for the Snappix settings dialog (tabs and option rows).
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF


_STROKE = QColor("#d7e3f1")
_ACCENT = QColor("#4aa3ff")
_ACCENT_FILL = QColor(74, 163, 255, 70)
_GREEN = QColor("#2ecc71")
_GREEN_FILL = QColor(46, 204, 113, 50)


def build_settings_icon(icon_id: str, *, size: int = 18) -> QIcon:
    """
    Builds one settings icon by identifier.

    Args:
        icon_id: Stable icon key (tab or option).
        size: Pixel edge length of the rendered pixmap.

    Returns:
        QIcon: Rendered icon, or a null icon for unknown ids.
    """

    painters = {
        "tab_general": _paint_tab_general,
        "tab_measure_box": _paint_tab_measure_box,
        "tab_shortcuts": _paint_tab_shortcuts,
        "hotkeys": _paint_hotkeys,
        "capture_area": _paint_capture_area,
        "capture_window": _paint_capture_window,
        "capture_fullscreen": _paint_capture_fullscreen,
        "capture_screen": _paint_capture_screen,
        "capture_same_area": _paint_capture_same_area,
        "capture_video": _paint_capture_video,
        "pause_resume": _paint_pause_resume,
        "stop_recording": _paint_stop_recording,
        "after_capture": _paint_after_capture,
        "language": _paint_language,
        "screenshot_source": _paint_screenshot_source,
        "last_tab": _paint_last_tab,
        "canvas": _paint_canvas,
        "handle_size": _paint_handle_size,
        "handle_position": _paint_handle_position,
        "save_folder": _paint_save_folder,
        "file_name": _paint_file_name,
        "workspace_folder": _paint_workspace_folder,
        "measure_hotkey": _paint_measure_hotkey,
        "line_color": _paint_line_color,
        "fill_color": _paint_fill_color,
        "ruler": _paint_ruler,
        "ruler_outside": _paint_ruler_outside,
        "crosshair": _paint_crosshair,
    }
    painter_fn = painters.get(icon_id)
    if painter_fn is None:
        return QIcon()

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    scale = size / 18.0
    painter.scale(scale, scale)
    painter_fn(painter)
    painter.end()
    return QIcon(pixmap)


def _stroke(width: float = 1.5) -> QPen:
    return QPen(_STROKE, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)


def _accent(width: float = 1.5) -> QPen:
    return QPen(_ACCENT, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)


def _paint_tab_general(painter: QPainter) -> None:
    painter.setPen(_stroke(1.4))
    painter.setBrush(QBrush(_ACCENT_FILL))
    painter.drawEllipse(QRectF(3.5, 3.5, 11.0, 11.0))
    painter.setBrush(QBrush(_STROKE))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QRectF(7.2, 7.2, 3.6, 3.6))
    painter.setPen(_stroke(1.3))
    for angle in range(0, 360, 45):
        painter.save()
        painter.translate(9.0, 9.0)
        painter.rotate(angle)
        painter.drawLine(QPointF(0.0, -7.2), QPointF(0.0, -5.2))
        painter.restore()


def _paint_tab_measure_box(painter: QPainter) -> None:
    painter.setPen(QPen(_GREEN, 1.5))
    painter.setBrush(QBrush(_GREEN_FILL))
    painter.drawRect(QRectF(3.0, 4.0, 12.0, 10.0))
    painter.drawLine(QPointF(3.0, 4.0), QPointF(3.0, 2.0))
    painter.drawLine(QPointF(9.0, 4.0), QPointF(9.0, 2.0))
    painter.drawLine(QPointF(15.0, 4.0), QPointF(15.0, 2.0))
    painter.drawLine(QPointF(3.0, 14.0), QPointF(1.0, 14.0))
    painter.drawLine(QPointF(3.0, 9.0), QPointF(1.0, 9.0))


def _paint_tab_shortcuts(painter: QPainter) -> None:
    painter.setPen(_stroke(1.4))
    painter.setBrush(QBrush(_ACCENT_FILL))
    painter.drawRoundedRect(QRectF(2.0, 5.0, 14.0, 9.0), 2.0, 2.0)
    painter.setBrush(QBrush(_STROKE))
    painter.setPen(Qt.PenStyle.NoPen)
    for x in (4.0, 7.0, 10.0, 13.0):
        painter.drawRoundedRect(QRectF(x - 0.7, 7.0, 1.8, 1.8), 0.4, 0.4)
    painter.drawRoundedRect(QRectF(5.5, 10.2, 7.0, 1.8), 0.4, 0.4)


def _paint_hotkeys(painter: QPainter) -> None:
    _paint_tab_shortcuts(painter)


def _paint_capture_area(painter: QPainter) -> None:
    painter.setPen(_accent(1.4))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRect(QRectF(3.5, 4.0, 11.0, 10.0))
    painter.setPen(_stroke(1.3))
    painter.drawLine(QPointF(3.5, 4.0), QPointF(6.5, 4.0))
    painter.drawLine(QPointF(3.5, 4.0), QPointF(3.5, 7.0))
    painter.drawLine(QPointF(14.5, 14.0), QPointF(11.5, 14.0))
    painter.drawLine(QPointF(14.5, 14.0), QPointF(14.5, 11.0))


def _paint_capture_window(painter: QPainter) -> None:
    painter.setPen(_stroke(1.4))
    painter.setBrush(QBrush(_ACCENT_FILL))
    painter.drawRoundedRect(QRectF(2.5, 3.5, 13.0, 11.0), 1.5, 1.5)
    painter.drawLine(QPointF(2.5, 6.5), QPointF(15.5, 6.5))
    painter.setBrush(QBrush(_STROKE))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QRectF(4.0, 4.3, 1.4, 1.4))
    painter.drawEllipse(QRectF(6.2, 4.3, 1.4, 1.4))


def _paint_capture_fullscreen(painter: QPainter) -> None:
    painter.setPen(_stroke(1.4))
    painter.setBrush(QBrush(_ACCENT_FILL))
    painter.drawRoundedRect(QRectF(2.0, 3.5, 14.0, 10.0), 1.2, 1.2)
    painter.drawLine(QPointF(7.0, 15.0), QPointF(11.0, 15.0))
    painter.drawLine(QPointF(9.0, 13.5), QPointF(9.0, 15.0))


def _paint_capture_screen(painter: QPainter) -> None:
    painter.setPen(_stroke(1.3))
    painter.setBrush(QBrush(QColor(74, 163, 255, 35)))
    painter.drawRoundedRect(QRectF(1.5, 4.5, 6.5, 5.0), 0.8, 0.8)
    painter.setPen(_accent(1.4))
    painter.setBrush(QBrush(_ACCENT_FILL))
    painter.drawRoundedRect(QRectF(9.0, 3.5, 7.5, 8.5), 1.0, 1.0)
    painter.setPen(_stroke(1.2))
    painter.drawLine(QPointF(11.5, 13.5), QPointF(14.0, 13.5))


def _paint_capture_same_area(painter: QPainter) -> None:
    painter.setPen(_stroke(1.3))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRect(QRectF(2.5, 3.5, 8.0, 7.0))
    painter.setPen(_accent(1.4))
    painter.drawRect(QRectF(7.0, 7.0, 8.0, 7.0))
    path = QPainterPath()
    path.moveTo(13.5, 3.5)
    path.quadTo(15.5, 3.5, 15.5, 5.5)
    painter.drawPath(path)
    painter.setBrush(QBrush(_ACCENT))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawPolygon(
        QPolygonF([QPointF(15.5, 6.8), QPointF(14.2, 4.8), QPointF(16.5, 4.8)])
    )


def _paint_capture_video(painter: QPainter) -> None:
    painter.setPen(_stroke(1.4))
    painter.setBrush(QBrush(_ACCENT_FILL))
    painter.drawRoundedRect(QRectF(2.0, 5.0, 9.5, 8.0), 1.2, 1.2)
    painter.setBrush(QBrush(_STROKE))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawPolygon(
        QPolygonF([QPointF(12.0, 6.5), QPointF(16.5, 4.5), QPointF(16.5, 13.5), QPointF(12.0, 11.5)])
    )


def _paint_pause_resume(painter: QPainter) -> None:
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(_STROKE))
    painter.drawRoundedRect(QRectF(3.5, 4.0, 2.2, 10.0), 0.6, 0.6)
    painter.drawRoundedRect(QRectF(7.2, 4.0, 2.2, 10.0), 0.6, 0.6)
    painter.setBrush(QBrush(_ACCENT))
    painter.drawPolygon(
        QPolygonF([QPointF(11.5, 5.0), QPointF(16.0, 9.0), QPointF(11.5, 13.0)])
    )


def _paint_stop_recording(painter: QPainter) -> None:
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(QColor("#e74c3c")))
    painter.drawRoundedRect(QRectF(4.5, 4.5, 9.0, 9.0), 1.5, 1.5)


def _paint_after_capture(painter: QPainter) -> None:
    painter.setPen(_stroke(1.4))
    painter.setBrush(QBrush(_ACCENT_FILL))
    painter.drawRoundedRect(QRectF(2.0, 4.0, 7.0, 10.0), 1.0, 1.0)
    painter.setPen(_accent(1.5))
    painter.drawLine(QPointF(10.0, 9.0), QPointF(14.5, 9.0))
    painter.setBrush(QBrush(_ACCENT))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawPolygon(
        QPolygonF([QPointF(14.0, 6.5), QPointF(16.5, 9.0), QPointF(14.0, 11.5)])
    )


def _paint_language(painter: QPainter) -> None:
    painter.setPen(_stroke(1.4))
    painter.setBrush(QBrush(_ACCENT_FILL))
    painter.drawEllipse(QRectF(3.0, 3.0, 12.0, 12.0))
    painter.drawEllipse(QRectF(6.5, 3.0, 5.0, 12.0))
    painter.drawLine(QPointF(3.0, 9.0), QPointF(15.0, 9.0))
    painter.drawLine(QPointF(4.0, 6.0), QPointF(14.0, 6.0))
    painter.drawLine(QPointF(4.0, 12.0), QPointF(14.0, 12.0))


def _paint_screenshot_source(painter: QPainter) -> None:
    painter.setPen(_stroke(1.4))
    painter.setBrush(QBrush(_ACCENT_FILL))
    painter.drawRoundedRect(QRectF(2.0, 5.5, 14.0, 9.0), 1.5, 1.5)
    painter.drawRoundedRect(QRectF(6.5, 3.5, 5.0, 2.5), 0.8, 0.8)
    painter.setBrush(QBrush(_STROKE))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QRectF(6.5, 7.5, 5.0, 5.0))
    painter.setBrush(QBrush(_ACCENT))
    painter.drawEllipse(QRectF(7.8, 8.8, 2.4, 2.4))


def _paint_last_tab(painter: QPainter) -> None:
    painter.setPen(_stroke(1.3))
    painter.setBrush(QBrush(_ACCENT_FILL))
    painter.drawRoundedRect(QRectF(2.0, 4.0, 8.0, 4.0), 0.8, 0.8)
    painter.drawRoundedRect(QRectF(2.0, 8.5, 14.0, 6.0), 1.0, 1.0)
    painter.setPen(_accent(1.4))
    painter.drawLine(QPointF(12.0, 4.5), QPointF(15.5, 8.0))
    painter.drawLine(QPointF(15.5, 4.5), QPointF(12.0, 8.0))


def _paint_canvas(painter: QPainter) -> None:
    painter.setPen(_stroke(1.3))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRect(QRectF(2.5, 3.0, 13.0, 12.0))
    painter.setPen(_accent(1.4))
    painter.setBrush(QBrush(_ACCENT_FILL))
    painter.drawRect(QRectF(5.0, 5.5, 8.0, 7.0))
    painter.drawLine(QPointF(2.5, 3.0), QPointF(5.0, 5.5))
    painter.drawLine(QPointF(15.5, 15.0), QPointF(13.0, 12.5))


def _paint_handle_size(painter: QPainter) -> None:
    painter.setPen(_stroke(1.3))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRect(QRectF(4.0, 5.0, 10.0, 8.0))
    painter.setBrush(QBrush(_ACCENT))
    painter.setPen(Qt.PenStyle.NoPen)
    for x, y in ((4.0, 5.0), (14.0, 5.0), (4.0, 13.0), (14.0, 13.0), (9.0, 5.0), (9.0, 13.0)):
        painter.drawRect(QRectF(x - 1.3, y - 1.3, 2.6, 2.6))


def _paint_handle_position(painter: QPainter) -> None:
    painter.setPen(_stroke(1.3))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRect(QRectF(4.0, 5.0, 10.0, 8.0))
    painter.setBrush(QBrush(_ACCENT))
    painter.setPen(Qt.PenStyle.NoPen)
    for x, y in ((4.0, 5.0), (14.0, 5.0), (4.0, 13.0), (14.0, 13.0)):
        painter.drawRect(QRectF(x - 1.1, y - 1.1, 2.2, 2.2))


def _paint_save_folder(painter: QPainter) -> None:
    painter.setPen(_stroke(1.4))
    painter.setBrush(QBrush(_ACCENT_FILL))
    path = QPainterPath()
    path.moveTo(2.5, 6.0)
    path.lineTo(2.5, 5.0)
    path.lineTo(7.0, 5.0)
    path.lineTo(8.5, 6.5)
    path.lineTo(15.5, 6.5)
    path.lineTo(15.5, 14.0)
    path.lineTo(2.5, 14.0)
    path.closeSubpath()
    painter.drawPath(path)


def _paint_file_name(painter: QPainter) -> None:
    painter.setPen(_stroke(1.4))
    painter.setBrush(QBrush(_ACCENT_FILL))
    path = QPainterPath()
    path.moveTo(5.0, 2.5)
    path.lineTo(11.0, 2.5)
    path.lineTo(14.0, 5.5)
    path.lineTo(14.0, 15.5)
    path.lineTo(5.0, 15.5)
    path.closeSubpath()
    painter.drawPath(path)
    painter.drawLine(QPointF(11.0, 2.5), QPointF(11.0, 5.5))
    painter.drawLine(QPointF(11.0, 5.5), QPointF(14.0, 5.5))
    painter.drawLine(QPointF(7.0, 9.0), QPointF(12.0, 9.0))
    painter.drawLine(QPointF(7.0, 11.5), QPointF(12.0, 11.5))


def _paint_workspace_folder(painter: QPainter) -> None:
    _paint_save_folder(painter)
    painter.setPen(_accent(1.3))
    painter.setBrush(QBrush(_ACCENT))
    painter.drawEllipse(QRectF(10.5, 8.5, 5.0, 5.0))
    painter.setPen(QPen(QColor("#0b1220"), 1.1))
    painter.drawLine(QPointF(13.0, 9.5), QPointF(13.0, 11.0))
    painter.drawLine(QPointF(13.0, 12.2), QPointF(13.0, 12.5))


def _paint_measure_hotkey(painter: QPainter) -> None:
    _paint_tab_measure_box(painter)


def _paint_line_color(painter: QPainter) -> None:
    painter.setPen(QPen(_GREEN, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawLine(QPointF(3.0, 14.0), QPointF(14.5, 3.5))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(_GREEN))
    painter.drawEllipse(QRectF(12.5, 2.0, 3.5, 3.5))


def _paint_fill_color(painter: QPainter) -> None:
    painter.setPen(_stroke(1.3))
    painter.setBrush(QBrush(_GREEN_FILL))
    painter.drawRect(QRectF(3.5, 4.0, 11.0, 10.0))
    painter.setBrush(QBrush(_GREEN))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QRectF(11.5, 2.5, 4.0, 4.0))


def _paint_ruler(painter: QPainter) -> None:
    painter.setPen(_stroke(1.4))
    painter.setBrush(QBrush(_ACCENT_FILL))
    painter.drawRoundedRect(QRectF(2.0, 6.5, 14.0, 5.0), 1.0, 1.0)
    for x in (4.0, 6.0, 8.0, 10.0, 12.0, 14.0):
        height = 2.5 if int(x) % 4 == 0 else 1.5
        painter.drawLine(QPointF(x, 6.5), QPointF(x, 6.5 + height))


def _paint_ruler_outside(painter: QPainter) -> None:
    painter.setPen(_stroke(1.3))
    painter.setBrush(QBrush(_ACCENT_FILL))
    painter.drawRect(QRectF(5.0, 5.0, 9.0, 9.0))
    painter.setPen(_accent(1.3))
    painter.drawLine(QPointF(5.0, 3.0), QPointF(14.0, 3.0))
    painter.drawLine(QPointF(5.0, 2.5), QPointF(5.0, 3.5))
    painter.drawLine(QPointF(14.0, 2.5), QPointF(14.0, 3.5))
    painter.drawLine(QPointF(3.0, 5.0), QPointF(3.0, 14.0))
    painter.drawLine(QPointF(2.5, 5.0), QPointF(3.5, 5.0))
    painter.drawLine(QPointF(2.5, 14.0), QPointF(3.5, 14.0))


def _paint_crosshair(painter: QPainter) -> None:
    painter.setPen(_accent(1.4))
    painter.drawLine(QPointF(9.0, 2.5), QPointF(9.0, 15.5))
    painter.drawLine(QPointF(2.5, 9.0), QPointF(15.5, 9.0))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QRectF(6.5, 6.5, 5.0, 5.0))
