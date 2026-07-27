"""
Unit tests for the installer splash pen animation.
"""

from __future__ import annotations

import math
import unittest

from src.install_progress_gui import (
    SplashPenAnimation,
    blend_hex_toward_background,
    hsv_to_hex,
    ink_color_at,
    ink_fade_alpha,
    ink_hue_at,
    pen_path_at,
    pen_tip_angle,
    pen_trail_points,
    pen_trail_samples,
)


class TestSplashPenGeometry(unittest.TestCase):
    """
    Verifies continuous pen path helpers used by the splash animation.
    """

    def test_pen_trail_grows_then_caps_to_fade_window(self) -> None:
        """
        Ensures trail samples grow early, then stay bounded by the fade length.
        """

        short = pen_trail_points(30.0)
        medium = pen_trail_points(180.0)
        long = pen_trail_points(5000.0, fade_length=520.0)
        self.assertEqual(pen_trail_points(0.0), [])
        self.assertGreaterEqual(len(short), 2)
        self.assertGreater(len(medium), len(short))
        # Far beyond the fade window the visible point count stays bounded.
        self.assertLess(len(long), 250)

    def test_pen_path_stays_within_canvas_margins(self) -> None:
        """
        Ensures sampled doodle points remain inside the canvas with margins.
        """

        width = 420.0
        height = 130.0
        for distance in (0.0, 50.0, 400.0, 1200.0, 5000.0):
            x, y = pen_path_at(distance, width=width, height=height)
            self.assertGreaterEqual(x, 0.0)
            self.assertLessEqual(x, width)
            self.assertGreaterEqual(y, 0.0)
            self.assertLessEqual(y, height)

    def test_pen_tip_angle_is_finite(self) -> None:
        """
        Ensures tangent angle is a finite float for early and later travel.
        """

        early = pen_tip_angle(5.0)
        later = pen_tip_angle(250.0)
        self.assertTrue(math.isfinite(early))
        self.assertTrue(math.isfinite(later))

    def test_ink_hue_cycles_through_full_spectrum(self) -> None:
        """
        Ensures hue advances slowly and wraps through the full rainbow.
        """

        self.assertAlmostEqual(ink_hue_at(0.0, cycle_px=1000.0), 0.0)
        self.assertAlmostEqual(ink_hue_at(250.0, cycle_px=1000.0), 0.25)
        self.assertAlmostEqual(ink_hue_at(1000.0, cycle_px=1000.0), 0.0)
        red = hsv_to_hex(0.0)
        green = hsv_to_hex(1.0 / 3.0)
        blue = hsv_to_hex(2.0 / 3.0)
        self.assertNotEqual(red, green)
        self.assertNotEqual(green, blue)

    def test_old_ink_fades_then_disappears(self) -> None:
        """
        Ensures ink opacity falls with age and vanishes past the fade length.
        """

        self.assertAlmostEqual(ink_fade_alpha(100.0, 100.0, fade_length=400.0), 1.0)
        mid = ink_fade_alpha(100.0, 300.0, fade_length=400.0)
        self.assertGreater(mid, 0.0)
        self.assertLess(mid, 1.0)
        self.assertEqual(ink_fade_alpha(100.0, 600.0, fade_length=400.0), 0.0)
        self.assertIsNone(ink_color_at(100.0, 600.0, fade_length=400.0))
        vivid = ink_color_at(500.0, 500.0, fade_length=400.0)
        self.assertIsNotNone(vivid)
        faded = blend_hex_toward_background("#ff0000", 0.0)
        self.assertEqual(faded.lower(), "#1a1f2a")

    def test_trail_samples_omit_fully_faded_history(self) -> None:
        """
        Ensures samples start near tip - fade_length, not from distance zero.
        """

        samples = pen_trail_samples(2000.0, fade_length=520.0, step=10.0)
        self.assertGreaterEqual(len(samples), 2)
        self.assertGreaterEqual(samples[0][2], 2000.0 - 520.0 - 10.0)
        self.assertAlmostEqual(samples[-1][2], 2000.0)


class TestSplashPenAnimationLifecycle(unittest.TestCase):
    """
    Verifies start/stop lifecycle and growing ink distance on a Tk canvas.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Creates a shared Tk root when a display is available.
        """

        cls._tk = None
        cls._skip_reason = ""
        try:
            import tkinter as tk

            root = tk.Tk()
            root.withdraw()
            cls._tk = root
        except Exception as exc:  # pragma: no cover - display-dependent
            cls._skip_reason = str(exc)

    @classmethod
    def tearDownClass(cls) -> None:
        """
        Destroys the shared Tk root.
        """

        if cls._tk is not None:
            cls._tk.destroy()
            cls._tk = None

    def test_start_advances_distance_and_stop_is_idempotent(self) -> None:
        """
        Ensures the pen travels farther while running and stop is safe twice.
        """

        if self._tk is None:
            self.skipTest(f"Tk unavailable: {self._skip_reason}")

        import tkinter as tk

        canvas = tk.Canvas(self._tk, width=420, height=130)
        animation = SplashPenAnimation(canvas, interval_ms=20, speed_px=10.0)
        animation.start()
        self.assertTrue(animation.is_running)
        self._tk.update_idletasks()
        self._tk.update()
        after_one = animation.distance
        self.assertGreater(after_one, 0.0)
        self._tk.update()
        self.assertGreaterEqual(animation.distance, after_one)
        animation.stop()
        self.assertFalse(animation.is_running)
        stopped_at = animation.distance
        animation.stop()
        self.assertFalse(animation.is_running)
        self.assertEqual(animation.distance, stopped_at)


if __name__ == "__main__":
    unittest.main()
