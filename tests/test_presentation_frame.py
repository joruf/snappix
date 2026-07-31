"""
Tests for the export presentation frame composition.
"""

from __future__ import annotations

import unittest

from PySide6.QtGui import QColor, QPixmap

from src.presentation_frame import (
    ASPECT_AUTO,
    BACKGROUND_GRADIENT,
    BACKGROUND_SOLID,
    BACKGROUND_TRANSPARENT,
    PresentationFrame,
    apply_presentation_frame,
    default_gradient_end,
    framed_size,
)
from tests.qt_test_utils import ensure_qapp


class PresentationFrameTests(unittest.TestCase):
    """
    Class PresentationFrameTests

    Covers sizing, letterboxing, backdrops, and the disabled pass-through.
    """

    def setUp(self) -> None:
        """
        Returns:
            None
        """

        ensure_qapp()
        self.source = QPixmap(400, 300)
        self.source.fill(QColor("#3B82F6"))

    def test_disabled_frame_returns_source_unchanged(self) -> None:
        """
        Returns:
            None
        """

        result = apply_presentation_frame(self.source, PresentationFrame(enabled=False))
        self.assertEqual(result.size(), self.source.size())

    def test_padding_is_percent_of_longer_edge(self) -> None:
        """
        Returns:
            None
        """

        frame = PresentationFrame(enabled=True, padding_percent=10.0)
        # 10% of the 400px longer edge is 40px on every side.
        self.assertEqual(framed_size(400, 300, frame), (480, 380))

    def test_padding_scales_with_source_so_setting_is_resolution_independent(self) -> None:
        """
        Returns:
            None
        """

        frame = PresentationFrame(enabled=True, padding_percent=5.0)
        small_w, small_h = framed_size(400, 300, frame)
        large_w, large_h = framed_size(4000, 3000, frame)
        self.assertAlmostEqual(small_w / small_h, large_w / large_h, places=3)

    def test_aspect_preset_letterboxes_and_never_crops(self) -> None:
        """
        Returns:
            None
        """

        frame = PresentationFrame(enabled=True, padding_percent=0.0, aspect_ratio="16:9")
        width, height = framed_size(400, 300, frame)
        self.assertGreaterEqual(width, 400)
        self.assertGreaterEqual(height, 300)
        self.assertAlmostEqual(width / height, 16 / 9, places=2)

    def test_square_aspect_from_landscape_source(self) -> None:
        """
        Returns:
            None
        """

        frame = PresentationFrame(enabled=True, padding_percent=0.0, aspect_ratio="1:1")
        self.assertEqual(framed_size(400, 300, frame), (400, 400))

    def test_auto_aspect_keeps_padded_shape(self) -> None:
        """
        Returns:
            None
        """

        frame = PresentationFrame(enabled=True, padding_percent=0.0, aspect_ratio=ASPECT_AUTO)
        self.assertEqual(framed_size(400, 300, frame), (400, 300))

    def test_transparent_backdrop_leaves_corner_alpha_zero(self) -> None:
        """
        Returns:
            None
        """

        frame = PresentationFrame(
            enabled=True,
            padding_percent=10.0,
            shadow_enabled=False,
            background_mode=BACKGROUND_TRANSPARENT,
        )
        image = apply_presentation_frame(self.source, frame).toImage()
        self.assertEqual(image.pixelColor(0, 0).alpha(), 0)

    def test_solid_backdrop_fills_padding_area(self) -> None:
        """
        Returns:
            None
        """

        frame = PresentationFrame(
            enabled=True,
            padding_percent=10.0,
            shadow_enabled=False,
            background_mode=BACKGROUND_SOLID,
            background_color="#101010",
        )
        image = apply_presentation_frame(self.source, frame).toImage()
        self.assertEqual(image.pixelColor(2, 2).name(), "#101010")

    def test_source_pixels_survive_framing(self) -> None:
        """
        Returns:
            None
        """

        frame = PresentationFrame(enabled=True, padding_percent=10.0, corner_radius=0.0)
        result = apply_presentation_frame(self.source, frame)
        center = result.toImage().pixelColor(result.width() // 2, result.height() // 2)
        self.assertEqual(center.name(), "#3b82f6")

    def test_corner_radius_cuts_the_body_corner(self) -> None:
        """
        Returns:
            None
        """

        frame = PresentationFrame(
            enabled=True,
            padding_percent=0.0,
            corner_radius=40.0,
            shadow_enabled=False,
            background_mode=BACKGROUND_TRANSPARENT,
        )
        image = apply_presentation_frame(self.source, frame).toImage()
        self.assertEqual(image.pixelColor(1, 1).alpha(), 0)

    def test_radius_is_clamped_to_half_the_shorter_edge(self) -> None:
        """
        Returns:
            None
        """

        frame = PresentationFrame(enabled=True, padding_percent=0.0, corner_radius=9999.0)
        result = apply_presentation_frame(self.source, frame)
        self.assertEqual(result.size(), self.source.size())

    def test_gradient_second_stop_stays_close_in_hue(self) -> None:
        """
        Returns:
            None
        """

        start = QColor("#3B82F6")
        end = default_gradient_end(start)
        delta = abs(start.hue() - end.hue()) % 360
        self.assertLessEqual(min(delta, 360 - delta), 20)

    def test_gradient_backdrop_differs_top_to_bottom(self) -> None:
        """
        Returns:
            None
        """

        frame = PresentationFrame(
            enabled=True,
            padding_percent=12.0,
            shadow_enabled=False,
            background_mode=BACKGROUND_GRADIENT,
            background_color="#3B82F6",
        )
        image = apply_presentation_frame(self.source, frame).toImage()
        self.assertNotEqual(
            image.pixelColor(2, 2).name(),
            image.pixelColor(2, image.height() - 3).name(),
        )

    def test_achromatic_gradient_end_has_no_hue_artifact(self) -> None:
        """
        Returns:
            None
        """

        end = default_gradient_end(QColor("#808080"))
        self.assertEqual(end.saturation(), 0)

    def test_shadow_darkens_area_below_the_body(self) -> None:
        """
        Returns:
            None
        """

        lit = PresentationFrame(
            enabled=True,
            padding_percent=12.0,
            shadow_enabled=False,
            background_mode=BACKGROUND_SOLID,
            background_color="#FFFFFF",
        )
        shadowed = PresentationFrame(
            enabled=True,
            padding_percent=12.0,
            shadow_enabled=True,
            shadow_opacity=0.5,
            background_mode=BACKGROUND_SOLID,
            background_color="#FFFFFF",
        )
        flat_image = apply_presentation_frame(self.source, lit).toImage()
        shadow_image = apply_presentation_frame(self.source, shadowed).toImage()
        # Probe just below the body's bottom edge: the shadow reaches only a few
        # percent past it by design, so a probe at the canvas edge sees nothing.
        probe_x = shadow_image.width() // 2
        probe_y = (shadow_image.height() + self.source.height()) // 2 + 6
        self.assertLess(
            shadow_image.pixelColor(probe_x, probe_y).lightness(),
            flat_image.pixelColor(probe_x, probe_y).lightness(),
        )

    def test_payload_roundtrip_preserves_values(self) -> None:
        """
        Returns:
            None
        """

        frame = PresentationFrame(
            enabled=True,
            padding_percent=8.0,
            corner_radius=14.0,
            shadow_opacity=0.35,
            background_mode=BACKGROUND_GRADIENT,
            background_color="#123456",
            aspect_ratio="4:3",
        )
        restored = PresentationFrame.from_payload(frame.to_payload())
        self.assertEqual(restored, frame)

    def test_payload_rejects_unknown_modes_and_bad_numbers(self) -> None:
        """
        Returns:
            None
        """

        restored = PresentationFrame.from_payload(
            {
                "background_mode": "hologram",
                "aspect_ratio": "21:9",
                "padding_percent": "not-a-number",
                "shadow_opacity": 5.0,
            }
        )
        self.assertEqual(restored.background_mode, BACKGROUND_SOLID)
        self.assertEqual(restored.aspect_ratio, ASPECT_AUTO)
        self.assertEqual(restored.padding_percent, PresentationFrame().padding_percent)
        self.assertEqual(restored.shadow_opacity, 1.0)

    def test_payload_from_none_yields_defaults(self) -> None:
        """
        Returns:
            None
        """

        self.assertEqual(PresentationFrame.from_payload(None), PresentationFrame())

    def test_device_pixel_ratio_survives_framing(self) -> None:
        """
        Windows commonly runs at 125%/150% scaling, so a source can carry a
        device pixel ratio. Compositing must happen in raw pixels and the ratio
        must come back on the result, otherwise the body is drawn at its logical
        size into a ratio-1 canvas and comes out shrunk.

        Returns:
            None
        """

        frame = PresentationFrame(enabled=True, padding_percent=10.0, shadow_enabled=False)
        baseline = apply_presentation_frame(self.source, frame)

        for ratio in (1.25, 1.5, 2.0):
            scaled_source = QPixmap(self.source)
            scaled_source.setDevicePixelRatio(ratio)
            result = apply_presentation_frame(scaled_source, frame)
            self.assertEqual(result.size(), baseline.size())
            self.assertEqual(result.devicePixelRatio(), ratio)
            image = result.toImage()
            self.assertEqual(
                image.pixelColor(result.width() // 2, result.height() // 2).name(),
                "#3b82f6",
            )

    def test_framing_does_not_mutate_the_source_ratio(self) -> None:
        """
        Returns:
            None
        """

        scaled_source = QPixmap(self.source)
        scaled_source.setDevicePixelRatio(2.0)
        apply_presentation_frame(
            scaled_source, PresentationFrame(enabled=True, padding_percent=5.0)
        )
        self.assertEqual(scaled_source.devicePixelRatio(), 2.0)

    def test_null_pixmap_is_returned_untouched(self) -> None:
        """
        Returns:
            None
        """

        empty = QPixmap()
        result = apply_presentation_frame(empty, PresentationFrame(enabled=True))
        self.assertTrue(result.isNull())


class PresentationFrameExportTests(unittest.TestCase):
    """
    Class PresentationFrameExportTests

    Covers the frame reaching every export format through the shared pixmap.
    """

    def setUp(self) -> None:
        """
        Returns:
            None
        """

        ensure_qapp()
        from src.editor_window import EditorWindow

        pixmap = QPixmap(400, 300)
        pixmap.fill(QColor("#3B82F6"))
        self.window = EditorWindow(pixmap)

    def tearDown(self) -> None:
        """
        Returns:
            None
        """

        self.window.close()

    def test_export_is_unframed_by_default(self) -> None:
        """
        Returns:
            None
        """

        self.assertEqual(
            self.window._export_output_pixmap(for_jpeg=False).size().toTuple(),
            (400, 300),
        )

    def test_enabled_frame_reaches_the_export_pixmap(self) -> None:
        """
        Returns:
            None
        """

        self.window.set_presentation_frame(
            PresentationFrame(enabled=True, padding_percent=10.0)
        )
        self.assertEqual(
            self.window._export_output_pixmap(for_jpeg=False).size().toTuple(),
            (480, 380),
        )

    def test_frame_stays_proportional_at_higher_export_scale(self) -> None:
        """
        Returns:
            None
        """

        self.window.set_presentation_frame(
            PresentationFrame(enabled=True, padding_percent=10.0)
        )
        self.window.set_export_scale(2.0)
        self.assertEqual(
            self.window._export_output_pixmap(for_jpeg=False).size().toTuple(),
            (960, 760),
        )

    def test_transparent_backdrop_is_matted_for_jpeg(self) -> None:
        """
        JPEG cannot store alpha, so a transparent backdrop must not reach the
        encoder -- it would be flattened to black.

        Returns:
            None
        """

        self.window.set_presentation_frame(
            PresentationFrame(
                enabled=True,
                padding_percent=10.0,
                shadow_enabled=False,
                background_mode=BACKGROUND_TRANSPARENT,
            )
        )
        image = self.window._export_output_pixmap(for_jpeg=True).toImage()
        self.assertEqual(image.pixelColor(2, 2).alpha(), 255)
        self.assertEqual(image.pixelColor(2, 2).name(), "#ffffff")

    def test_transparent_backdrop_survives_for_png(self) -> None:
        """
        Returns:
            None
        """

        self.window.set_presentation_frame(
            PresentationFrame(
                enabled=True,
                padding_percent=10.0,
                shadow_enabled=False,
                background_mode=BACKGROUND_TRANSPARENT,
            )
        )
        image = self.window._export_output_pixmap(for_jpeg=False).toImage()
        self.assertEqual(image.pixelColor(2, 2).alpha(), 0)

    def test_toolbar_checkbox_drives_the_frame(self) -> None:
        """
        Returns:
            None
        """

        self.window.presentation_frame_check.setChecked(True)
        self.assertTrue(self.window.presentation_frame().enabled)
        self.window.presentation_frame_check.setChecked(False)
        self.assertFalse(self.window.presentation_frame().enabled)


if __name__ == "__main__":
    unittest.main()
