"""
Timeline entry/exit effects (fade, zoom, slide) for video annotations.

Effects are stored per-annotation in ``annotation.payload["effects"]`` as a
list of small dicts, so no changes to :class:`VideoAnnotationModel` or its
serialization are needed. Each effect combines a generic *kind* (the visual
transform) with an *edge* (whether it plays at the annotation's start or
end), so "Fade" + "start" reads as Fade In, "Fade" + "end" as Fade Out, etc.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from src.video_models import VideoAnnotationModel

EFFECT_KIND_FADE = "fade"
EFFECT_KIND_SLIDE = "slide"
EFFECT_KIND_ZOOM = "zoom"
EFFECT_KINDS = (EFFECT_KIND_FADE, EFFECT_KIND_SLIDE, EFFECT_KIND_ZOOM)

EFFECT_EDGE_START = "start"
EFFECT_EDGE_END = "end"
EFFECT_EDGES = (EFFECT_EDGE_START, EFFECT_EDGE_END)

_EFFECT_KIND_LABELS = {
    EFFECT_KIND_FADE: "Fade",
    EFFECT_KIND_SLIDE: "Slide",
    EFFECT_KIND_ZOOM: "Zoom",
}

DEFAULT_EFFECT_DURATION_MS = 500
MIN_EFFECT_DURATION_MS = 50
MAX_EFFECT_DURATION_MS = 5000


def effect_kind_label(kind: str) -> str:
    """
    Returns the human-readable label for one effect kind.

    Args:
        kind: Effect kind identifier.

    Returns:
        str: Display label, falling back to the raw kind for unknown values.
    """

    return _EFFECT_KIND_LABELS.get(kind, kind.title())


def effect_display_name(kind: str, edge: str) -> str:
    """
    Builds the combined display name for one effect (e.g. "Fade In").

    Args:
        kind: Effect kind identifier.
        edge: Annotation edge the effect plays at.

    Returns:
        str: Combined display name.
    """

    suffix = "In" if edge == EFFECT_EDGE_START else "Out"
    return f"{effect_kind_label(kind)} {suffix}"


def normalize_effect_duration_ms(duration_ms: Any) -> int:
    """
    Clamps an effect duration to the supported range.

    Args:
        duration_ms: Candidate duration in milliseconds.

    Returns:
        int: Clamped duration in milliseconds.
    """

    try:
        value = int(duration_ms)
    except (TypeError, ValueError):
        value = DEFAULT_EFFECT_DURATION_MS
    return max(MIN_EFFECT_DURATION_MS, min(MAX_EFFECT_DURATION_MS, value))


def get_annotation_effects(annotation: VideoAnnotationModel) -> list[dict[str, Any]]:
    """
    Returns the list of effects currently stored on one annotation.

    Args:
        annotation: Annotation to read effects from.

    Returns:
        list[dict[str, Any]]: Effect entries (kind, edge, duration_ms, id).
    """

    effects = annotation.payload.get("effects")
    return list(effects) if isinstance(effects, list) else []


def set_annotation_effects(
    annotation: VideoAnnotationModel,
    effects: list[dict[str, Any]],
) -> None:
    """
    Replaces the effect list stored on one annotation.

    Args:
        annotation: Annotation to update.
        effects: New complete effect list.

    Returns:
        None
    """

    annotation.payload["effects"] = list(effects)


def add_annotation_effect(
    annotation: VideoAnnotationModel,
    *,
    kind: str,
    edge: str,
    duration_ms: int,
) -> dict[str, Any]:
    """
    Appends one new effect to an annotation.

    Args:
        annotation: Annotation to add the effect to.
        kind: Effect kind identifier.
        edge: Annotation edge the effect plays at.
        duration_ms: Effect duration in milliseconds.

    Returns:
        dict[str, Any]: The newly created effect entry.
    """

    effect = {
        "id": uuid4().hex,
        "kind": kind if kind in EFFECT_KINDS else EFFECT_KIND_FADE,
        "edge": edge if edge in EFFECT_EDGES else EFFECT_EDGE_START,
        "duration_ms": normalize_effect_duration_ms(duration_ms),
    }
    effects = get_annotation_effects(annotation)
    effects.append(effect)
    set_annotation_effects(annotation, effects)
    return effect


def update_annotation_effect(
    annotation: VideoAnnotationModel,
    effect_id: str,
    *,
    kind: str,
    edge: str,
    duration_ms: int,
) -> bool:
    """
    Updates one existing effect in place, identified by its id.

    Args:
        annotation: Annotation whose effect should be updated.
        effect_id: Id of the effect entry to update.
        kind: New effect kind identifier.
        edge: New annotation edge.
        duration_ms: New effect duration in milliseconds.

    Returns:
        bool: True when an effect with that id was found and updated.
    """

    effects = get_annotation_effects(annotation)
    for effect in effects:
        if effect.get("id") == effect_id:
            effect["kind"] = kind if kind in EFFECT_KINDS else EFFECT_KIND_FADE
            effect["edge"] = edge if edge in EFFECT_EDGES else EFFECT_EDGE_START
            effect["duration_ms"] = normalize_effect_duration_ms(duration_ms)
            set_annotation_effects(annotation, effects)
            return True
    return False


def remove_annotation_effect(annotation: VideoAnnotationModel, effect_id: str) -> bool:
    """
    Removes one effect from an annotation, identified by its id.

    Args:
        annotation: Annotation to remove the effect from.
        effect_id: Id of the effect entry to remove.

    Returns:
        bool: True when an effect with that id was found and removed.
    """

    effects = get_annotation_effects(annotation)
    remaining = [effect for effect in effects if effect.get("id") != effect_id]
    if len(remaining) == len(effects):
        return False
    set_annotation_effects(annotation, remaining)
    return True


def track_effect_summary(annotation: VideoAnnotationModel) -> str:
    """
    Builds the short, comma-joined effect summary shown on a timeline bar.

    Args:
        annotation: Annotation to summarize.

    Returns:
        str: Comma-joined display names (e.g. "Fade In, Zoom Out"), or an
            empty string when the annotation has no effects.
    """

    return ", ".join(
        effect_display_name(str(effect.get("kind", "")), str(effect.get("edge", "")))
        for effect in get_annotation_effects(annotation)
    )


def _effect_progress(annotation: VideoAnnotationModel, effect: dict[str, Any], position_ms: int) -> float:
    """
    Computes how far (0..1) the playhead is into one effect's active window.

    Args:
        annotation: Owning annotation, for its start/end timing.
        effect: Effect entry (edge, duration_ms).
        position_ms: Current playhead position in milliseconds.

    Returns:
        float: Progress from 0.0 (window not yet reached/just begun) to 1.0
            (window fully elapsed).
    """

    duration_ms = max(1, int(effect.get("duration_ms", DEFAULT_EFFECT_DURATION_MS) or 1))
    if effect.get("edge") == EFFECT_EDGE_END:
        window_start = annotation.end_ms - duration_ms
        elapsed = position_ms - window_start
    else:
        elapsed = position_ms - annotation.start_ms
    return max(0.0, min(1.0, elapsed / duration_ms))


def compute_effect_render_state(
    annotation: VideoAnnotationModel,
    position_ms: int,
) -> tuple[float, float, float]:
    """
    Combines all of one annotation's effects into one render state.

    Args:
        annotation: Annotation to evaluate.
        position_ms: Current playhead position in milliseconds.

    Returns:
        tuple[float, float, float]: ``(opacity, scale, offset_x)`` to apply
            to the annotation's graphics item. Multiple effects compose:
            opacity and scale multiply, horizontal offsets add.
    """

    opacity = 1.0
    scale = 1.0
    offset_x = 0.0
    width = max(1.0, float(annotation.width))
    for effect in get_annotation_effects(annotation):
        progress = _effect_progress(annotation, effect, position_ms)
        is_start = effect.get("edge") != EFFECT_EDGE_END
        kind = effect.get("kind")
        if kind == EFFECT_KIND_FADE:
            opacity *= progress if is_start else (1.0 - progress)
        elif kind == EFFECT_KIND_ZOOM:
            scale *= progress if is_start else (1.0 - progress)
        elif kind == EFFECT_KIND_SLIDE:
            offset_x += -(1.0 - progress) * width if is_start else progress * width
    return opacity, scale, offset_x


def apply_effect_render_state(item, annotation: VideoAnnotationModel, position_ms: int) -> None:
    """
    Applies one annotation's combined effect render state to its graphics item.

    Args:
        item: Graphics item rendering the annotation.
        annotation: Source annotation model.
        position_ms: Current playhead position in milliseconds.

    Returns:
        None
    """

    opacity, scale, offset_x = compute_effect_render_state(annotation, position_ms)
    item.setOpacity(max(0.0, min(1.0, opacity)))
    if scale != 1.0:
        item.setTransformOriginPoint(item.boundingRect().center())
        item.setScale(max(0.0, scale))
    if offset_x:
        pos = item.pos()
        item.setPos(pos.x() + offset_x, pos.y())
