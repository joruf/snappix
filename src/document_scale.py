"""
Scaling a whole document: background image and every annotation together.

Cropping already exists, and exports can be written at @1x/@2x/@3x, but neither
changes the document itself -- and a screenshot headed for a ticket or a manual
usually has to be a specific pixel width. Scaling the background alone would slide
every annotation out of place, so geometry, stroke widths, font sizes, and the
multi-point payloads are scaled with it.
"""

from __future__ import annotations

from src.models import AnnotationModel

# Guard rails for the dialog and for programmatic callers. The upper bound keeps a
# stray value from allocating gigabytes of pixmap.
MIN_DOCUMENT_SIZE = 1
MAX_DOCUMENT_SIZE = 20000


def clamp_document_size(value: int) -> int:
    """
    Clamps one document dimension to the supported range.

    Args:
        value: Requested pixel size.

    Returns:
        int: Size within the supported range.
    """

    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = MIN_DOCUMENT_SIZE
    return max(MIN_DOCUMENT_SIZE, min(MAX_DOCUMENT_SIZE, parsed))


def scaled_size(
    width: int,
    height: int,
    *,
    target_width: int | None = None,
    target_height: int | None = None,
    keep_aspect: bool = True,
) -> tuple[int, int]:
    """
    Computes the target size from a partially specified request.

    Args:
        width: Current document width.
        height: Current document height.
        target_width: Requested width, or None to derive it.
        target_height: Requested height, or None to derive it.
        keep_aspect: Whether the missing side follows the aspect ratio.

    Returns:
        tuple[int, int]: Clamped target width and height.
    """

    source_width = max(1, int(width))
    source_height = max(1, int(height))
    if target_width is None and target_height is None:
        return source_width, source_height

    if keep_aspect:
        if target_width is not None:
            factor = clamp_document_size(target_width) / source_width
            return (
                clamp_document_size(target_width),
                clamp_document_size(round(source_height * factor)),
            )
        factor = clamp_document_size(target_height) / source_height
        return (
            clamp_document_size(round(source_width * factor)),
            clamp_document_size(target_height),
        )

    return (
        clamp_document_size(target_width if target_width is not None else source_width),
        clamp_document_size(target_height if target_height is not None else source_height),
    )


def scale_annotation(
    annotation: AnnotationModel,
    scale_x: float,
    scale_y: float,
) -> AnnotationModel:
    """
    Returns a copy of one annotation scaled by the given factors.

    Stroke width and font size follow the smaller factor so a non-uniform scale
    cannot make a border wider than the shape it outlines.

    Args:
        annotation: Annotation to scale.
        scale_x: Horizontal factor.
        scale_y: Vertical factor.

    Returns:
        AnnotationModel: Scaled copy.
    """

    uniform = min(abs(scale_x), abs(scale_y))
    payload = dict(annotation.payload)

    points = payload.get("points")
    if isinstance(points, list):
        scaled_points = []
        for point in points:
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                scaled_points.append([float(point[0]) * scale_x, float(point[1]) * scale_y])
            else:
                scaled_points.append(point)
        payload["points"] = scaled_points

    for key in ("corner_radius", "box_padding", "stroke_width"):
        value = payload.get(key)
        if isinstance(value, (int, float)):
            payload[key] = float(value) * uniform

    return AnnotationModel(
        annotation_type=annotation.annotation_type,
        x=annotation.x * scale_x,
        y=annotation.y * scale_y,
        width=annotation.width * scale_x,
        height=annotation.height * scale_y,
        stroke_rgba=list(annotation.stroke_rgba),
        fill_rgba=list(annotation.fill_rgba),
        stroke_width=max(0.0, annotation.stroke_width * uniform),
        text=annotation.text,
        font_size=max(1, int(round(annotation.font_size * uniform))),
        font_family=annotation.font_family,
        font_bold=annotation.font_bold,
        font_italic=annotation.font_italic,
        font_underline=annotation.font_underline,
        payload=payload,
    )


def scale_annotations(
    annotations: list[AnnotationModel],
    scale_x: float,
    scale_y: float,
) -> list[AnnotationModel]:
    """
    Scales a list of annotations.

    Args:
        annotations: Annotations to scale.
        scale_x: Horizontal factor.
        scale_y: Vertical factor.

    Returns:
        list[AnnotationModel]: Scaled copies in the original order.
    """

    return [scale_annotation(item, scale_x, scale_y) for item in annotations]
