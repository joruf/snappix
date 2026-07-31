"""
Presentation framing for exports: padding, rounded corners, drop shadow, and a
backdrop composited around the finished screenshot.

This runs at the very end of the export pipeline, after annotations are already
flattened into a single pixmap. It never inspects or alters the screenshot's own
pixels -- it only places that pixmap on a larger canvas -- so it composes with
every export format and cannot interfere with annotation rendering.

Sizing is expressed in percent of the source's longer edge rather than in fixed
pixels, so one setting looks the same on a 400px crop and on a 4K full screen.
Only the corner radius is an absolute @1x value, and it is multiplied by the
export scale so a @2x export keeps the same visual roundness.
"""

from __future__ import annotations

from src.py_compat import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QGraphicsPixmapItem,
    QGraphicsScene,
)

BACKGROUND_SOLID = "solid"
BACKGROUND_GRADIENT = "gradient"
BACKGROUND_TRANSPARENT = "transparent"

ASPECT_AUTO = "auto"

# Aspect presets offered in the Export tab. "auto" keeps whatever the padded
# content happens to be; the others letterbox the content into a fixed frame.
ASPECT_RATIOS: dict[str, float] = {
    "16:9": 16.0 / 9.0,
    "4:3": 4.0 / 3.0,
    "1:1": 1.0,
    "3:2": 3.0 / 2.0,
}

# Shadow geometry as a fraction of the source's longer edge. A shadow that
# scales with the image keeps the same apparent softness at every size, and
# these values stay deliberately subtle: the annotations are meant to be the
# only loud elements in the frame.
SHADOW_BLUR_FRACTION = 0.030
SHADOW_OFFSET_FRACTION = 0.015

# Hue/lightness shift used to derive the second gradient stop from the first.
# Kept under 20 degrees so the backdrop reads as one color with depth rather
# than as two competing colors.
GRADIENT_HUE_SHIFT_DEGREES = 18
GRADIENT_LIGHTNESS_SHIFT = 20


@dataclass(frozen=True)
class PresentationFrame:
    """
    Class PresentationFrame

    Immutable description of the frame composited around an exported image.
    """

    enabled: bool = False
    padding_percent: float = 6.0
    corner_radius: float = 10.0
    shadow_enabled: bool = True
    shadow_opacity: float = 0.20
    background_mode: str = BACKGROUND_SOLID
    background_color: str = "#F2F3F5"
    gradient_end_color: str = ""
    aspect_ratio: str = ASPECT_AUTO

    def to_payload(self) -> dict[str, object]:
        """
        Serializes this frame for config and session storage.

        Returns:
            dict[str, object]: JSON-safe representation.
        """

        return {
            "enabled": bool(self.enabled),
            "padding_percent": float(self.padding_percent),
            "corner_radius": float(self.corner_radius),
            "shadow_enabled": bool(self.shadow_enabled),
            "shadow_opacity": float(self.shadow_opacity),
            "background_mode": str(self.background_mode),
            "background_color": str(self.background_color),
            "gradient_end_color": str(self.gradient_end_color),
            "aspect_ratio": str(self.aspect_ratio),
        }

    @staticmethod
    def from_payload(payload: dict[str, object] | None) -> "PresentationFrame":
        """
        Restores one frame from stored settings, falling back to defaults.

        Args:
            payload: Stored mapping, or None when nothing was saved yet.

        Returns:
            PresentationFrame: Restored frame with sanitized values.
        """

        if not isinstance(payload, dict):
            return PresentationFrame()

        default = PresentationFrame()

        def _float(key: str, fallback: float) -> float:
            try:
                return float(payload.get(key, fallback))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return fallback

        def _str(key: str, fallback: str) -> str:
            value = payload.get(key, fallback)
            return value if isinstance(value, str) else fallback

        mode = _str("background_mode", default.background_mode)
        if mode not in (BACKGROUND_SOLID, BACKGROUND_GRADIENT, BACKGROUND_TRANSPARENT):
            mode = default.background_mode

        aspect = _str("aspect_ratio", default.aspect_ratio)
        if aspect != ASPECT_AUTO and aspect not in ASPECT_RATIOS:
            aspect = ASPECT_AUTO

        return PresentationFrame(
            enabled=bool(payload.get("enabled", default.enabled)),
            padding_percent=max(0.0, min(40.0, _float("padding_percent", default.padding_percent))),
            corner_radius=max(0.0, min(120.0, _float("corner_radius", default.corner_radius))),
            shadow_enabled=bool(payload.get("shadow_enabled", default.shadow_enabled)),
            shadow_opacity=max(0.0, min(1.0, _float("shadow_opacity", default.shadow_opacity))),
            background_mode=mode,
            background_color=_str("background_color", default.background_color),
            gradient_end_color=_str("gradient_end_color", default.gradient_end_color),
            aspect_ratio=aspect,
        )


def default_gradient_end(start: QColor) -> QColor:
    """
    Derives the second gradient stop from the first.

    Shifts hue by a small amount and lifts lightness instead of asking the user
    for a second color: two stops far apart read as a poster, while a narrow
    shift reads as a lit surface behind the screenshot.

    Args:
        start: First gradient stop.

    Returns:
        QColor: Second gradient stop.
    """

    hue = start.hue()
    if hue < 0:
        # Achromatic input has no hue to shift, so vary lightness only.
        return QColor.fromHsl(0, 0, max(0, min(255, start.lightness() - GRADIENT_LIGHTNESS_SHIFT)))
    shifted_hue = (hue + GRADIENT_HUE_SHIFT_DEGREES) % 360
    lightness = max(0, min(255, start.lightness() - GRADIENT_LIGHTNESS_SHIFT))
    return QColor.fromHsl(shifted_hue, start.hslSaturation(), lightness)


def framed_size(source_width: int, source_height: int, frame: PresentationFrame) -> tuple[int, int]:
    """
    Computes the output canvas size for one source size and frame.

    Args:
        source_width: Source pixmap width in pixels.
        source_height: Source pixmap height in pixels.
        frame: Frame settings to apply.

    Returns:
        tuple[int, int]: Output width and height in pixels.
    """

    if source_width <= 0 or source_height <= 0:
        return (max(0, source_width), max(0, source_height))

    padding = _padding_pixels(source_width, source_height, frame)
    width = source_width + padding * 2
    height = source_height + padding * 2

    ratio = ASPECT_RATIOS.get(frame.aspect_ratio)
    if ratio is not None:
        # Letterbox rather than crop: the frame only ever grows, so no part of
        # the screenshot can be lost to an aspect preset.
        if width / height < ratio:
            width = int(round(height * ratio))
        else:
            height = int(round(width / ratio))

    return (max(1, int(width)), max(1, int(height)))


def _padding_pixels(source_width: int, source_height: int, frame: PresentationFrame) -> int:
    """
    Converts the padding percentage into pixels for one source size.

    Args:
        source_width: Source pixmap width in pixels.
        source_height: Source pixmap height in pixels.
        frame: Frame settings to apply.

    Returns:
        int: Padding in pixels applied on every side.
    """

    longer_edge = max(source_width, source_height)
    return max(0, int(round(longer_edge * frame.padding_percent / 100.0)))


def _rounded(pixmap: QPixmap, radius: float) -> QPixmap:
    """
    Returns the pixmap with rounded corners cut out of its alpha channel.

    Args:
        pixmap: Source pixmap.
        radius: Corner radius in pixels; values <= 0 return the source unchanged.

    Returns:
        QPixmap: Pixmap with rounded corners.
    """

    if radius <= 0.0:
        return pixmap

    # A radius past half the shorter edge would produce overlapping arcs.
    limit = min(pixmap.width(), pixmap.height()) / 2.0
    radius = min(radius, limit)

    rounded = QPixmap(pixmap.size())
    rounded.fill(Qt.transparent)
    painter = QPainter(rounded)
    painter.setRenderHint(QPainter.Antialiasing, True)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0.0, 0.0, pixmap.width(), pixmap.height()), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()
    return rounded


def _shadowed(pixmap: QPixmap, frame: PresentationFrame, canvas_size: tuple[int, int]) -> QPixmap:
    """
    Renders the pixmap onto a transparent canvas with a drop shadow beneath it.

    Uses Qt's own drop-shadow effect through a throwaway scene so the blur runs
    in Qt rather than pixel-by-pixel in Python, which matters for @3x exports of
    full-screen captures.

    Args:
        pixmap: Already-rounded source pixmap.
        frame: Frame settings to apply.
        canvas_size: Output canvas width and height in pixels.

    Returns:
        QPixmap: Transparent canvas holding the shadowed pixmap.
    """

    canvas_width, canvas_height = canvas_size
    canvas = QPixmap(canvas_width, canvas_height)
    canvas.fill(Qt.transparent)

    longer_edge = max(pixmap.width(), pixmap.height())
    left = (canvas_width - pixmap.width()) / 2.0
    top = (canvas_height - pixmap.height()) / 2.0

    scene = QGraphicsScene()
    item = QGraphicsPixmapItem(pixmap)
    item.setTransformationMode(Qt.SmoothTransformation)
    effect = QGraphicsDropShadowEffect()
    effect.setBlurRadius(longer_edge * SHADOW_BLUR_FRACTION)
    effect.setOffset(QPointF(0.0, longer_edge * SHADOW_OFFSET_FRACTION))
    # Pure black at low alpha: a gray shadow turns muddy the moment the backdrop
    # is not neutral, while black-with-alpha stays correct on any color.
    effect.setColor(QColor(0, 0, 0, int(round(max(0.0, min(1.0, frame.shadow_opacity)) * 255))))
    item.setGraphicsEffect(effect)
    item.setPos(left, top)
    scene.addItem(item)

    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    scene.render(
        painter,
        QRectF(0.0, 0.0, canvas_width, canvas_height),
        QRectF(0.0, 0.0, canvas_width, canvas_height),
    )
    painter.end()
    # Drop the effect before the scene dies so the item does not outlive it.
    item.setGraphicsEffect(None)
    scene.removeItem(item)
    return canvas


def _paint_background(painter: QPainter, frame: PresentationFrame, width: int, height: int) -> None:
    """
    Fills the output canvas with the configured backdrop.

    Args:
        painter: Active painter on the output canvas.
        frame: Frame settings to apply.
        width: Canvas width in pixels.
        height: Canvas height in pixels.

    Returns:
        None
    """

    if frame.background_mode == BACKGROUND_TRANSPARENT:
        return

    start = QColor(frame.background_color)
    if not start.isValid():
        start = QColor(PresentationFrame().background_color)

    if frame.background_mode == BACKGROUND_GRADIENT:
        end = QColor(frame.gradient_end_color)
        if not end.isValid():
            end = default_gradient_end(start)
        gradient = QLinearGradient(0.0, 0.0, 0.0, float(height))
        gradient.setColorAt(0.0, start)
        gradient.setColorAt(1.0, end)
        painter.fillRect(0, 0, width, height, gradient)
        return

    painter.fillRect(0, 0, width, height, start)


def apply_presentation_frame(
    pixmap: QPixmap,
    frame: PresentationFrame,
    scale: float = 1.0,
) -> QPixmap:
    """
    Composites one finished export pixmap onto its presentation frame.

    Args:
        pixmap: Flattened export pixmap.
        frame: Frame settings to apply.
        scale: Export scale factor, used to keep the corner radius proportional.

    Returns:
        QPixmap: Framed pixmap, or the source unchanged when the frame is off.
    """

    if not frame.enabled or pixmap.isNull():
        return pixmap

    # Composite in raw device pixels. A source carrying a ratio (Windows at
    # 125%/150% scaling is the common case) would otherwise be drawn at its
    # logical size into a ratio-1 canvas and come out shrunk; the ratio is put
    # back on the finished pixmap so its logical size stays correct.
    source_ratio = float(pixmap.devicePixelRatio())
    if source_ratio != 1.0:
        pixmap = QPixmap(pixmap)
        pixmap.setDevicePixelRatio(1.0)

    source_width = pixmap.width()
    source_height = pixmap.height()
    canvas_width, canvas_height = framed_size(source_width, source_height, frame)

    body = _rounded(pixmap, frame.corner_radius * max(0.0, scale))

    canvas = QPixmap(canvas_width, canvas_height)
    canvas.fill(Qt.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    _paint_background(painter, frame, canvas_width, canvas_height)

    if frame.shadow_enabled and frame.shadow_opacity > 0.0:
        painter.drawPixmap(0, 0, _shadowed(body, frame, (canvas_width, canvas_height)))
    else:
        painter.drawPixmap(
            int(round((canvas_width - body.width()) / 2.0)),
            int(round((canvas_height - body.height()) / 2.0)),
            body,
        )

    painter.end()
    if source_ratio != 1.0:
        canvas.setDevicePixelRatio(source_ratio)
    return canvas
