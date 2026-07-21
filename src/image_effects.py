"""
Image effect helpers for screenshot editing.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QImage


def pixelate_qimage_region(image: QImage, rect: QRect, block_size: int = 16) -> QImage:
    """
    Pixelates one rectangular region inside a QImage copy.

    Args:
        image: Source image.
        rect: Target rectangle in image coordinates.
        block_size: Pixel block size used for the pixelation effect.

    Returns:
        QImage: New image with the selected region pixelated.
    """

    from PIL import Image
    from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QRect
    from PySide6.QtGui import QImage

    if image.isNull():
        return image

    bounds = QRect(0, 0, image.width(), image.height())
    clipped = rect.normalized().intersected(bounds)
    if clipped.width() < 2 or clipped.height() < 2:
        return image.copy()

    block_size = max(4, min(block_size, min(clipped.width(), clipped.height())))

    byte_array = QByteArray()
    buffer = QBuffer(byte_array)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    pil_image = Image.open(io.BytesIO(bytes(byte_array))).convert("RGBA")

    left = clipped.left()
    top = clipped.top()
    region_width = clipped.width()
    region_height = clipped.height()
    region = pil_image.crop((left, top, left + region_width, top + region_height))
    small_width = max(1, region_width // block_size)
    small_height = max(1, region_height // block_size)
    pixelated = region.resize((small_width, small_height), Image.Resampling.BILINEAR)
    pixelated = pixelated.resize((region_width, region_height), Image.Resampling.NEAREST)
    pil_image.paste(pixelated, (left, top))

    output_buffer = io.BytesIO()
    pil_image.save(output_buffer, format="PNG")
    output = QImage()
    output.loadFromData(output_buffer.getvalue(), "PNG")
    return output
