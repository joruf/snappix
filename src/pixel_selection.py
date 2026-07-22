"""
Pixel selection helpers for wand, marquee, and mask painting.
"""

from __future__ import annotations

from collections import deque

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import (
    QBitmap,
    QColor,
    QImage,
    QPainter,
    QPainterPath,
    QPixmap,
    QRegion,
)


def color_distance(left: QColor, right: QColor) -> int:
    """
    Returns the maximum channel distance between two colors.

    Args:
        left: First color.
        right: Second color.

    Returns:
        int: Max absolute RGBA channel delta.
    """

    return max(
        abs(left.red() - right.red()),
        abs(left.green() - right.green()),
        abs(left.blue() - right.blue()),
        abs(left.alpha() - right.alpha()),
    )


def colors_match(left: QColor, right: QColor, tolerance: int) -> bool:
    """
    Checks whether two colors are within the given tolerance.

    Args:
        left: First color.
        right: Second color.
        tolerance: Allowed max channel delta.

    Returns:
        bool: True when colors match within tolerance.
    """

    return color_distance(left, right) <= max(0, int(tolerance))


def rect_selection_path(rect: QRectF) -> QPainterPath:
    """
    Builds a rectangular selection path.

    Args:
        rect: Selection rectangle in document coordinates.

    Returns:
        QPainterPath: Closed rectangular path.
    """

    path = QPainterPath()
    normalized = rect.normalized()
    if normalized.width() < 1.0 or normalized.height() < 1.0:
        return path
    path.addRect(normalized)
    return path


def ellipse_selection_path(rect: QRectF) -> QPainterPath:
    """
    Builds an elliptical selection path.

    Args:
        rect: Bounding rectangle in document coordinates.

    Returns:
        QPainterPath: Closed elliptical path.
    """

    path = QPainterPath()
    normalized = rect.normalized()
    if normalized.width() < 1.0 or normalized.height() < 1.0:
        return path
    path.addEllipse(normalized)
    return path


def polygon_selection_path(points: list[QPointF]) -> QPainterPath:
    """
    Builds a closed polygon selection path from ordered points.

    Args:
        points: Polygon vertices in document coordinates.

    Returns:
        QPainterPath: Closed polygon path.
    """

    path = QPainterPath()
    if len(points) < 3:
        return path
    path.moveTo(points[0])
    for point in points[1:]:
        path.lineTo(point)
    path.closeSubpath()
    return path


def _rgba_view(image: QImage) -> tuple[QImage, memoryview, int, int, int]:
    """
    Returns a writable RGBA8888 buffer view for fast pixel access.

    Args:
        image: Source image.

    Returns:
        tuple: Converted image, byte view, width, height, bytes-per-line.
    """

    source = image
    if source.format() != QImage.Format.Format_RGBA8888:
        source = image.convertToFormat(QImage.Format.Format_RGBA8888)
    source = source.copy()
    width = source.width()
    height = source.height()
    bytes_per_line = source.bytesPerLine()
    view = memoryview(source.bits()).cast("B")
    return source, view, width, height, bytes_per_line


def _rgba_at(
    view: memoryview,
    bytes_per_line: int,
    x_pos: int,
    y_pos: int,
) -> tuple[int, int, int, int]:
    """
    Reads one RGBA pixel from a raw buffer.

    Args:
        view: RGBA byte buffer.
        bytes_per_line: Row stride in bytes.
        x_pos: Pixel X.
        y_pos: Pixel Y.

    Returns:
        tuple[int, int, int, int]: R, G, B, A.
    """

    index = y_pos * bytes_per_line + x_pos * 4
    return view[index], view[index + 1], view[index + 2], view[index + 3]


def _rgba_matches(
    view: memoryview,
    bytes_per_line: int,
    x_pos: int,
    y_pos: int,
    target: tuple[int, int, int, int],
    tolerance: int,
) -> bool:
    """
    Compares one buffer pixel to a target RGBA tuple.

    Args:
        view: RGBA byte buffer.
        bytes_per_line: Row stride in bytes.
        x_pos: Pixel X.
        y_pos: Pixel Y.
        target: Target RGBA.
        tolerance: Allowed max channel delta.

    Returns:
        bool: True when the pixel matches.
    """

    red, green, blue, alpha = _rgba_at(view, bytes_per_line, x_pos, y_pos)
    return (
        abs(red - target[0]) <= tolerance
        and abs(green - target[1]) <= tolerance
        and abs(blue - target[2]) <= tolerance
        and abs(alpha - target[3]) <= tolerance
    )


def _empty_alpha_mask(width: int, height: int) -> QImage:
    """
    Creates an empty opaque-selection mask image.

    Args:
        width: Mask width.
        height: Mask height.

    Returns:
        QImage: ARGB32 mask filled with transparent pixels.
    """

    mask = QImage(max(1, width), max(1, height), QImage.Format.Format_ARGB32)
    mask.fill(Qt.GlobalColor.transparent)
    return mask


def _alpha_mask_to_argb(alpha_mask: QImage) -> QImage:
    """
    Converts an Alpha8 selection mask to an ARGB32 punch mask.

    Args:
        alpha_mask: Alpha8 mask (0 = outside, 255 = selected).

    Returns:
        QImage: ARGB32 mask with opaque white selected pixels.
    """

    if alpha_mask.format() != QImage.Format.Format_Alpha8:
        alpha_mask = alpha_mask.convertToFormat(QImage.Format.Format_Alpha8)
    return alpha_mask.convertToFormat(QImage.Format.Format_ARGB32)


def mask_opaque_bounds(mask: QImage) -> QRect:
    """
    Computes the bounding rectangle of opaque mask pixels.

    Args:
        mask: Selection mask image.

    Returns:
        QRect: Bounding rect, empty when nothing is selected.
    """

    if mask.isNull() or mask.width() < 1 or mask.height() < 1:
        return QRect()
    cached = mask.text("selection_bounds")
    if cached:
        parts = cached.split(",")
        if len(parts) == 4:
            try:
                return QRect(int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]))
            except ValueError:
                pass
    source = mask
    if source.format() != QImage.Format.Format_ARGB32:
        source = mask.convertToFormat(QImage.Format.Format_ARGB32)
    width = source.width()
    height = source.height()
    view = memoryview(source.constBits()).cast("B")
    bpl = source.bytesPerLine()
    min_x = width
    min_y = height
    max_x = -1
    max_y = -1
    for y_pos in range(height):
        row = y_pos * bpl
        row_hit = False
        for x_pos in range(width):
            if view[row + x_pos * 4 + 3] != 0:
                row_hit = True
                if x_pos < min_x:
                    min_x = x_pos
                if x_pos > max_x:
                    max_x = x_pos
        if row_hit:
            if y_pos < min_y:
                min_y = y_pos
            if y_pos > max_y:
                max_y = y_pos
    if max_x < min_x or max_y < min_y:
        return QRect()
    return QRect(min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)


def mask_has_selection(mask: QImage) -> bool:
    """
    Returns whether a mask contains any selected pixels.

    Args:
        mask: Selection mask image.

    Returns:
        bool: True when at least one opaque pixel exists.
    """

    if mask.isNull() or mask.width() < 1 or mask.height() < 1:
        return False
    source = mask
    if source.format() == QImage.Format.Format_Alpha8:
        view = memoryview(source.constBits()).cast("B")
        bpl = source.bytesPerLine()
        width = source.width()
        height = source.height()
        for y_pos in range(height):
            row = y_pos * bpl
            for x_pos in range(width):
                if view[row + x_pos] != 0:
                    return True
        return False
    if source.format() != QImage.Format.Format_ARGB32:
        source = mask.convertToFormat(QImage.Format.Format_ARGB32)
    view = memoryview(source.constBits()).cast("B")
    bpl = source.bytesPerLine()
    width = source.width()
    height = source.height()
    for y_pos in range(height):
        row = y_pos * bpl
        for x_pos in range(width):
            if view[row + x_pos * 4 + 3] != 0:
                return True
    return False


def path_from_mask_bounds(mask: QImage) -> QPainterPath:
    """
    Builds a lightweight rectangular path around opaque mask pixels.

    Args:
        mask: Selection mask image.

    Returns:
        QPainterPath: Bounds path used for outlines and emptiness checks.
    """

    path = QPainterPath()
    bounds = mask_opaque_bounds(mask)
    if bounds.isEmpty():
        return path
    path.addRect(QRectF(bounds))
    return path


def region_from_mask(mask: QImage) -> QRegion:
    """
    Converts a selection mask into a Qt region for clipping.

    Args:
        mask: ARGB selection mask.

    Returns:
        QRegion: Region covering opaque mask pixels.
    """

    if mask.isNull() or mask.width() < 1 or mask.height() < 1:
        return QRegion()
    alpha_mask = mask.createAlphaMask()
    return QRegion(QBitmap.fromImage(alpha_mask))


def rasterize_path_to_mask(path: QPainterPath, width: int, height: int) -> QImage:
    """
    Rasterizes a selection path into an ARGB mask image.

    Args:
        path: Selection path in image coordinates.
        width: Mask width.
        height: Mask height.

    Returns:
        QImage: ARGB32 mask.
    """

    mask = _empty_alpha_mask(width, height)
    if path.isEmpty() or width < 1 or height < 1:
        return mask
    painter = QPainter(mask)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(255, 255, 255, 255))
    painter.drawPath(path)
    painter.end()
    return mask


def unite_masks(base: QImage, extra: QImage) -> QImage:
    """
    Unions two selection masks.

    Args:
        base: Existing mask.
        extra: Mask to add.

    Returns:
        QImage: Combined mask.
    """

    if base.isNull() or not mask_has_selection(base):
        return extra.copy() if not extra.isNull() else _empty_alpha_mask(1, 1)
    if extra.isNull() or not mask_has_selection(extra):
        return base.copy()
    width = max(base.width(), extra.width())
    height = max(base.height(), extra.height())
    result = _empty_alpha_mask(width, height)
    painter = QPainter(result)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    painter.drawImage(0, 0, base)
    painter.drawImage(0, 0, extra)
    painter.end()
    return result


def build_wand_mask_image(
    image: QImage,
    x_pos: int,
    y_pos: int,
    tolerance: int,
    *,
    contiguous: bool = True,
) -> QImage:
    """
    Builds a magic-wand selection mask from a seed pixel.

    Args:
        image: Source image in document pixel space.
        x_pos: Seed X coordinate.
        y_pos: Seed Y coordinate.
        tolerance: Max channel delta for matching colors.
        contiguous: True for flood-fill; False for global color match.

    Returns:
        QImage: ARGB32 mask with opaque white selected pixels.
    """

    if image.isNull() or image.width() < 1 or image.height() < 1:
        return _empty_alpha_mask(1, 1)
    width = image.width()
    height = image.height()
    if not (0 <= x_pos < width and 0 <= y_pos < height):
        return _empty_alpha_mask(width, height)

    _source, view, width, height, bytes_per_line = _rgba_view(image)
    target_r, target_g, target_b, target_a = _rgba_at(view, bytes_per_line, x_pos, y_pos)
    tolerance = max(0, int(tolerance))

    alpha_mask = QImage(width, height, QImage.Format.Format_Alpha8)
    alpha_mask.fill(0)
    mask_view = memoryview(alpha_mask.bits()).cast("B")
    mask_bpl = alpha_mask.bytesPerLine()
    selected_count = 0
    min_x = width
    min_y = height
    max_x = -1
    max_y = -1

    def matches(px: int, py: int) -> bool:
        index = py * bytes_per_line + px * 4
        return (
            abs(view[index] - target_r) <= tolerance
            and abs(view[index + 1] - target_g) <= tolerance
            and abs(view[index + 2] - target_b) <= tolerance
            and abs(view[index + 3] - target_a) <= tolerance
        )

    def is_marked(px: int, py: int) -> bool:
        return mask_view[py * mask_bpl + px] != 0

    def mark_span(py: int, left: int, right: int) -> None:
        nonlocal selected_count, min_x, min_y, max_x, max_y
        row = py * mask_bpl
        for px in range(left, right + 1):
            if mask_view[row + px] == 0:
                mask_view[row + px] = 255
                selected_count += 1
        if left < min_x:
            min_x = left
        if right > max_x:
            max_x = right
        if py < min_y:
            min_y = py
        if py > max_y:
            max_y = py

    if contiguous:
        stack: deque[tuple[int, int]] = deque([(x_pos, y_pos)])
        while stack:
            seed_x, seed_y = stack.pop()
            if not (0 <= seed_x < width and 0 <= seed_y < height):
                continue
            if is_marked(seed_x, seed_y) or not matches(seed_x, seed_y):
                continue

            left = seed_x
            while left > 0 and not is_marked(left - 1, seed_y) and matches(left - 1, seed_y):
                left -= 1
            right = seed_x
            while right + 1 < width and not is_marked(right + 1, seed_y) and matches(right + 1, seed_y):
                right += 1

            mark_span(seed_y, left, right)

            for next_y in (seed_y - 1, seed_y + 1):
                if not (0 <= next_y < height):
                    continue
                span_x = left
                while span_x <= right:
                    while span_x <= right and (is_marked(span_x, next_y) or not matches(span_x, next_y)):
                        span_x += 1
                    if span_x > right:
                        break
                    stack.append((span_x, next_y))
                    while span_x <= right and not is_marked(span_x, next_y) and matches(span_x, next_y):
                        span_x += 1
    else:
        for scan_y in range(height):
            row = scan_y * bytes_per_line
            mask_row = scan_y * mask_bpl
            row_min = width
            row_max = -1
            for scan_x in range(width):
                index = row + scan_x * 4
                if (
                    abs(view[index] - target_r) <= tolerance
                    and abs(view[index + 1] - target_g) <= tolerance
                    and abs(view[index + 2] - target_b) <= tolerance
                    and abs(view[index + 3] - target_a) <= tolerance
                ):
                    mask_view[mask_row + scan_x] = 255
                    selected_count += 1
                    if scan_x < row_min:
                        row_min = scan_x
                    if scan_x > row_max:
                        row_max = scan_x
            if row_max >= row_min:
                if row_min < min_x:
                    min_x = row_min
                if row_max > max_x:
                    max_x = row_max
                if scan_y < min_y:
                    min_y = scan_y
                if scan_y > max_y:
                    max_y = scan_y

    if selected_count == 0:
        return _empty_alpha_mask(width, height)
    result = _alpha_mask_to_argb(alpha_mask)
    # Store bounds in image text key for fast outline without a full rescan.
    result.setText(
        "selection_bounds",
        f"{min_x},{min_y},{max_x - min_x + 1},{max_y - min_y + 1}",
    )
    result.setText("selection_count", str(selected_count))
    return result


def build_wand_mask(
    image: QImage,
    x_pos: int,
    y_pos: int,
    tolerance: int,
    *,
    contiguous: bool = True,
) -> QPainterPath:
    """
    Builds a magic-wand selection path from a seed pixel.

    Args:
        image: Source image in document pixel space.
        x_pos: Seed X coordinate.
        y_pos: Seed Y coordinate.
        tolerance: Max channel delta for matching colors.
        contiguous: True for flood-fill; False for global color match.

    Returns:
        QPainterPath: Lightweight bounds path for the selection.
    """

    mask = build_wand_mask_image(
        image,
        x_pos,
        y_pos,
        tolerance,
        contiguous=contiguous,
    )
    return path_from_mask_bounds(mask)


def build_selection_overlay_pixmap(mask: QImage, dim_alpha: int = 110) -> QPixmap:
    """
    Builds a dimmed overlay pixmap with the selection punched out.

    Args:
        mask: Selection mask in document pixel space.
        dim_alpha: Outside dim opacity.

    Returns:
        QPixmap: Overlay pixmap matching the mask size.
    """

    if mask.isNull() or mask.width() < 1 or mask.height() < 1:
        return QPixmap()
    overlay = QImage(mask.size(), QImage.Format.Format_ARGB32_Premultiplied)
    overlay.fill(QColor(20, 20, 20, max(0, min(255, int(dim_alpha)))))
    painter = QPainter(overlay)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
    painter.drawImage(0, 0, mask)
    painter.end()
    return QPixmap.fromImage(overlay)


def paint_mask_on_image(
    image: QImage,
    mask: QImage,
    color: QColor,
    *,
    erase_transparent: bool = False,
) -> QImage:
    """
    Paints or erases image pixels covered by a selection mask.

    Args:
        image: Source image.
        mask: Selection mask.
        color: Fill color when not erasing.
        erase_transparent: True to clear masked pixels.

    Returns:
        QImage: Modified image copy.
    """

    if image.isNull() or mask.isNull() or not mask_has_selection(mask):
        return image
    result = image.convertToFormat(QImage.Format.Format_ARGB32)
    painter = QPainter(result)
    painter.setClipRegion(region_from_mask(mask))
    if erase_transparent:
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(result.rect(), Qt.GlobalColor.transparent)
    else:
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.fillRect(result.rect(), color)
    painter.end()
    return result


def paint_path_on_image(
    image: QImage,
    path: QPainterPath,
    color: QColor,
    *,
    pen_width: float = 0.0,
    erase_transparent: bool = False,
) -> QImage:
    """
    Paints a clipped fill or stroke onto an image copy.

    Args:
        image: Source image.
        path: Clip / stroke path in image coordinates.
        color: Paint color.
        pen_width: When > 0, draws a stroke instead of a fill.
        erase_transparent: When True, clears clipped pixels to transparent.

    Returns:
        QImage: Modified image copy.
    """

    if image.isNull() or path.isEmpty():
        return image
    result = image.convertToFormat(QImage.Format.Format_ARGB32)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setClipPath(path)
    if erase_transparent:
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(result.rect(), Qt.GlobalColor.transparent)
    elif pen_width > 0.0:
        from PySide6.QtGui import QPen

        pen = QPen(color, max(1.0, float(pen_width)), Qt.PenStyle.SolidLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
    else:
        painter.fillRect(result.rect(), color)
    painter.end()
    return result


def document_point_to_image(point: QPointF, document_origin: QPointF = QPointF(0.0, 0.0)) -> QPoint:
    """
    Converts a document scene point to integer image coordinates.

    Args:
        point: Scene/document point.
        document_origin: Document top-left in scene space.

    Returns:
        QPoint: Integer image pixel coordinate.
    """

    return QPoint(
        int(point.x() - document_origin.x()),
        int(point.y() - document_origin.y()),
    )
