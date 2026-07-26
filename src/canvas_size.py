"""
Canvas size presets and validation helpers.
"""

from __future__ import annotations

from src.py_compat import dataclass

MIN_CANVAS_SIZE = 1
MAX_CANVAS_SIZE = 16384
DEFAULT_CANVAS_WIDTH = 1280
DEFAULT_CANVAS_HEIGHT = 720


@dataclass(frozen=True, slots=True)
class CanvasSizePreset:
    """
    Describes one selectable canvas size preset.

    Attributes:
        key: Stable preset identifier.
        label: Human-readable preset label.
        width: Preset width in pixels, or None for custom sizes.
        height: Preset height in pixels, or None for custom sizes.
    """

    key: str
    label: str
    width: int | None = None
    height: int | None = None


CANVAS_SIZE_PRESETS: tuple[CanvasSizePreset, ...] = (
    CanvasSizePreset("custom", "Custom size"),
    CanvasSizePreset("hd", "HD (1280 × 720)", 1280, 720),
    CanvasSizePreset("full_hd", "Full HD (1920 × 1080)", 1920, 1080),
    CanvasSizePreset("qhd", "QHD (2560 × 1440)", 2560, 1440),
    CanvasSizePreset("4k_uhd", "4K UHD (3840 × 2160)", 3840, 2160),
    CanvasSizePreset("svga", "SVGA (800 × 600)", 800, 600),
    CanvasSizePreset("xga", "XGA (1024 × 768)", 1024, 768),
    CanvasSizePreset("square_1080", "Square (1080 × 1080)", 1080, 1080),
    CanvasSizePreset("a4_portrait", "A4 Portrait (794 × 1123)", 794, 1123),
    CanvasSizePreset("a4_landscape", "A4 Landscape (1123 × 794)", 1123, 794),
    CanvasSizePreset("letter_portrait", "Letter Portrait (816 × 1056)", 816, 1056),
)


def parse_canvas_dimension(raw_value: str) -> int | None:
    """
    Parses one canvas dimension from user input.

    Args:
        raw_value: Raw width or height text.

    Returns:
        int | None: Parsed dimension or None when invalid.
    """

    normalized = raw_value.strip()
    if not normalized:
        return None
    try:
        value = int(normalized)
    except ValueError:
        return None
    if value < MIN_CANVAS_SIZE or value > MAX_CANVAS_SIZE:
        return None
    return value


def validate_canvas_size(width: int, height: int) -> tuple[bool, str]:
    """
    Validates one canvas size pair.

    Args:
        width: Canvas width in pixels.
        height: Canvas height in pixels.

    Returns:
        tuple[bool, str]: Validation result and optional error message.
    """

    if width < MIN_CANVAS_SIZE or width > MAX_CANVAS_SIZE:
        return False, f"Width must be between {MIN_CANVAS_SIZE} and {MAX_CANVAS_SIZE}."
    if height < MIN_CANVAS_SIZE or height > MAX_CANVAS_SIZE:
        return False, f"Height must be between {MIN_CANVAS_SIZE} and {MAX_CANVAS_SIZE}."
    return True, ""


def find_canvas_preset(key: str) -> CanvasSizePreset | None:
    """
    Finds one canvas preset by key.

    Args:
        key: Preset identifier.

    Returns:
        CanvasSizePreset | None: Matching preset or None.
    """

    for preset in CANVAS_SIZE_PRESETS:
        if preset.key == key:
            return preset
    return None
