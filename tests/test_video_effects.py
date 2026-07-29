"""
Unit tests for the video annotation entry/exit effects model (fade, slide,
zoom): CRUD helpers, display names, and time-based render-state math.
"""

from __future__ import annotations

import unittest

from src.editor_canvas import Tool
from src.video_effects import (
    EFFECT_EDGE_END,
    EFFECT_EDGE_START,
    EFFECT_KIND_FADE,
    EFFECT_KIND_SLIDE,
    EFFECT_KIND_ZOOM,
    add_annotation_effect,
    compute_effect_render_state,
    effect_display_name,
    get_annotation_effects,
    remove_annotation_effect,
    track_effect_summary,
    update_annotation_effect,
)
from src.video_models import VideoAnnotationModel


def _annotation(start_ms: int = 1000, end_ms: int = 3000, width: float = 100.0) -> VideoAnnotationModel:
    """
    Builds one bare rectangle annotation spanning a known time range.

    Args:
        start_ms: Annotation start time.
        end_ms: Annotation end time.
        width: Annotation width, used by the Slide effect's displacement.

    Returns:
        VideoAnnotationModel: Sample annotation.
    """

    return VideoAnnotationModel(
        annotation_type=Tool.RECT,
        start_ms=start_ms,
        end_ms=end_ms,
        x=0.0,
        y=0.0,
        width=width,
        height=50.0,
        stroke_rgba=[255, 0, 0, 255],
        fill_rgba=[255, 0, 0, 70],
        stroke_width=2.0,
    )


class TestEffectDisplayNames(unittest.TestCase):
    """
    Verifies kind+edge combine into the expected display names.
    """

    def test_fade_start_reads_as_fade_in(self) -> None:
        self.assertEqual(effect_display_name(EFFECT_KIND_FADE, EFFECT_EDGE_START), "Fade In")

    def test_fade_end_reads_as_fade_out(self) -> None:
        self.assertEqual(effect_display_name(EFFECT_KIND_FADE, EFFECT_EDGE_END), "Fade Out")

    def test_zoom_and_slide_follow_the_same_pattern(self) -> None:
        self.assertEqual(effect_display_name(EFFECT_KIND_ZOOM, EFFECT_EDGE_START), "Zoom In")
        self.assertEqual(effect_display_name(EFFECT_KIND_SLIDE, EFFECT_EDGE_END), "Slide Out")


class TestAnnotationEffectCrud(unittest.TestCase):
    """
    Verifies add/update/remove operate on annotation.payload["effects"].
    """

    def test_add_effect_appends_and_returns_entry_with_stable_id(self) -> None:
        annotation = _annotation()
        effect = add_annotation_effect(
            annotation, kind=EFFECT_KIND_FADE, edge=EFFECT_EDGE_START, duration_ms=400
        )
        self.assertIn("id", effect)
        self.assertEqual(get_annotation_effects(annotation), [effect])

    def test_add_effect_clamps_out_of_range_duration(self) -> None:
        annotation = _annotation()
        effect = add_annotation_effect(
            annotation, kind=EFFECT_KIND_FADE, edge=EFFECT_EDGE_START, duration_ms=999_999
        )
        self.assertLessEqual(effect["duration_ms"], 5000)

    def test_update_effect_changes_fields_in_place(self) -> None:
        annotation = _annotation()
        effect = add_annotation_effect(
            annotation, kind=EFFECT_KIND_FADE, edge=EFFECT_EDGE_START, duration_ms=400
        )
        updated = update_annotation_effect(
            annotation,
            effect["id"],
            kind=EFFECT_KIND_ZOOM,
            edge=EFFECT_EDGE_END,
            duration_ms=800,
        )
        self.assertTrue(updated)
        stored = get_annotation_effects(annotation)[0]
        self.assertEqual(stored["kind"], EFFECT_KIND_ZOOM)
        self.assertEqual(stored["edge"], EFFECT_EDGE_END)
        self.assertEqual(stored["duration_ms"], 800)

    def test_update_unknown_effect_id_returns_false(self) -> None:
        annotation = _annotation()
        self.assertFalse(
            update_annotation_effect(
                annotation, "missing", kind=EFFECT_KIND_FADE, edge=EFFECT_EDGE_START, duration_ms=400
            )
        )

    def test_remove_effect_drops_only_the_matching_entry(self) -> None:
        annotation = _annotation()
        keep = add_annotation_effect(
            annotation, kind=EFFECT_KIND_FADE, edge=EFFECT_EDGE_START, duration_ms=300
        )
        drop = add_annotation_effect(
            annotation, kind=EFFECT_KIND_ZOOM, edge=EFFECT_EDGE_END, duration_ms=300
        )
        removed = remove_annotation_effect(annotation, drop["id"])
        self.assertTrue(removed)
        self.assertEqual(get_annotation_effects(annotation), [keep])

    def test_track_effect_summary_joins_display_names(self) -> None:
        annotation = _annotation()
        add_annotation_effect(annotation, kind=EFFECT_KIND_FADE, edge=EFFECT_EDGE_START, duration_ms=300)
        add_annotation_effect(annotation, kind=EFFECT_KIND_ZOOM, edge=EFFECT_EDGE_END, duration_ms=300)
        self.assertEqual(track_effect_summary(annotation), "Fade In, Zoom Out")

    def test_track_effect_summary_is_empty_without_effects(self) -> None:
        self.assertEqual(track_effect_summary(_annotation()), "")


class TestEffectRenderState(unittest.TestCase):
    """
    Verifies the time-based opacity/scale/offset math used for live preview.
    """

    def test_fade_in_ramps_opacity_from_zero_to_one(self) -> None:
        annotation = _annotation(start_ms=1000, end_ms=3000)
        add_annotation_effect(annotation, kind=EFFECT_KIND_FADE, edge=EFFECT_EDGE_START, duration_ms=400)

        opacity_at_start, _scale, _offset = compute_effect_render_state(annotation, 1000)
        opacity_at_half, _s2, _o2 = compute_effect_render_state(annotation, 1200)
        opacity_after, _s3, _o3 = compute_effect_render_state(annotation, 1500)

        self.assertAlmostEqual(opacity_at_start, 0.0)
        self.assertAlmostEqual(opacity_at_half, 0.5)
        self.assertAlmostEqual(opacity_after, 1.0)

    def test_fade_out_ramps_opacity_from_one_to_zero(self) -> None:
        annotation = _annotation(start_ms=1000, end_ms=3000)
        add_annotation_effect(annotation, kind=EFFECT_KIND_FADE, edge=EFFECT_EDGE_END, duration_ms=400)

        opacity_before, _s1, _o1 = compute_effect_render_state(annotation, 2500)
        opacity_at_half, _s2, _o2 = compute_effect_render_state(annotation, 2800)
        opacity_at_end, _s3, _o3 = compute_effect_render_state(annotation, 3000)

        self.assertAlmostEqual(opacity_before, 1.0)
        self.assertAlmostEqual(opacity_at_half, 0.5)
        self.assertAlmostEqual(opacity_at_end, 0.0)

    def test_zoom_in_ramps_scale_from_zero_to_one(self) -> None:
        annotation = _annotation(start_ms=0, end_ms=2000)
        add_annotation_effect(annotation, kind=EFFECT_KIND_ZOOM, edge=EFFECT_EDGE_START, duration_ms=500)

        _o1, scale_start, _off1 = compute_effect_render_state(annotation, 0)
        _o2, scale_half, _off2 = compute_effect_render_state(annotation, 250)
        _o3, scale_done, _off3 = compute_effect_render_state(annotation, 600)

        self.assertAlmostEqual(scale_start, 0.0)
        self.assertAlmostEqual(scale_half, 0.5)
        self.assertAlmostEqual(scale_done, 1.0)

    def test_slide_in_moves_offset_from_negative_width_to_zero(self) -> None:
        annotation = _annotation(start_ms=0, end_ms=2000, width=100.0)
        add_annotation_effect(annotation, kind=EFFECT_KIND_SLIDE, edge=EFFECT_EDGE_START, duration_ms=500)

        _o1, _s1, offset_start = compute_effect_render_state(annotation, 0)
        _o2, _s2, offset_half = compute_effect_render_state(annotation, 250)
        _o3, _s3, offset_done = compute_effect_render_state(annotation, 600)

        self.assertAlmostEqual(offset_start, -100.0)
        self.assertAlmostEqual(offset_half, -50.0)
        self.assertAlmostEqual(offset_done, 0.0)

    def test_slide_out_moves_offset_from_zero_to_positive_width(self) -> None:
        annotation = _annotation(start_ms=0, end_ms=2000, width=100.0)
        add_annotation_effect(annotation, kind=EFFECT_KIND_SLIDE, edge=EFFECT_EDGE_END, duration_ms=500)

        _o1, _s1, offset_before = compute_effect_render_state(annotation, 1400)
        _o2, _s2, offset_half = compute_effect_render_state(annotation, 1750)
        _o3, _s3, offset_end = compute_effect_render_state(annotation, 2000)

        self.assertAlmostEqual(offset_before, 0.0)
        self.assertAlmostEqual(offset_half, 50.0)
        self.assertAlmostEqual(offset_end, 100.0)

    def test_multiple_effects_compose_multiplicatively_and_additively(self) -> None:
        annotation = _annotation(start_ms=0, end_ms=2000, width=100.0)
        add_annotation_effect(annotation, kind=EFFECT_KIND_FADE, edge=EFFECT_EDGE_START, duration_ms=500)
        add_annotation_effect(annotation, kind=EFFECT_KIND_ZOOM, edge=EFFECT_EDGE_START, duration_ms=500)
        add_annotation_effect(annotation, kind=EFFECT_KIND_SLIDE, edge=EFFECT_EDGE_START, duration_ms=500)

        opacity, scale, offset = compute_effect_render_state(annotation, 250)

        self.assertAlmostEqual(opacity, 0.5)
        self.assertAlmostEqual(scale, 0.5)
        self.assertAlmostEqual(offset, -50.0)

    def test_no_effects_yields_identity_render_state(self) -> None:
        opacity, scale, offset = compute_effect_render_state(_annotation(), 1500)
        self.assertEqual((opacity, scale, offset), (1.0, 1.0, 0.0))


class TestEffectsSurviveCanvasResync(unittest.TestCase):
    """
    Regression coverage: VideoCanvas._sync_visible_items_to_models() runs on
    every position change and previously rebuilt each model's payload from
    scratch, silently discarding the "effects" list because
    annotation_from_item() has no notion of effects. A live fade/zoom/slide
    would therefore vanish the moment the playhead moved again.
    """

    @classmethod
    def setUpClass(cls) -> None:
        from tests.qt_test_utils import ensure_qapp

        ensure_qapp()

    def test_effects_survive_a_position_driven_rebuild(self) -> None:
        """
        Ensures an annotation's effects payload survives a full
        rebuild/resync cycle triggered by moving the playhead.
        """

        from src.video_canvas import VideoCanvas

        canvas = VideoCanvas()
        canvas.resize(640, 480)
        canvas.set_video_size(640, 480)
        canvas.show()
        annotation = _annotation(start_ms=0, end_ms=5000)
        add_annotation_effect(annotation, kind=EFFECT_KIND_FADE, edge=EFFECT_EDGE_START, duration_ms=400)
        canvas.set_annotations([annotation])

        # Moving the playhead triggers _on_position_changed -> _rebuild_visible_items()
        # -> _sync_visible_items_to_models(), the exact path that used to wipe effects.
        canvas._on_position_changed(1000)  # pylint: disable=protected-access

        self.assertEqual(len(get_annotation_effects(canvas.annotations()[0])), 1)

    def test_zoom_effect_does_not_corrupt_true_geometry_after_resync(self) -> None:
        """
        Ensures an active Zoom effect's transient scale does not get baked
        into the annotation's real width/height via the geometry resync.
        """

        from src.video_canvas import VideoCanvas

        canvas = VideoCanvas()
        canvas.resize(640, 480)
        canvas.set_video_size(640, 480)
        canvas.show()
        annotation = _annotation(start_ms=0, end_ms=5000, width=100.0)
        add_annotation_effect(annotation, kind=EFFECT_KIND_ZOOM, edge=EFFECT_EDGE_START, duration_ms=1000)
        canvas.set_annotations([annotation])

        # Mid-zoom (scale ~0.5): a resync here must not shrink the true width.
        canvas._on_position_changed(500)  # pylint: disable=protected-access

        self.assertEqual(canvas.annotations()[0].width, 100.0)


if __name__ == "__main__":
    unittest.main()
