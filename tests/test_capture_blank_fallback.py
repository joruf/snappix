"""
Unit tests for empty (black) screen grabs and the external grab fallback.

``QScreen.grabWindow(0)`` can hand back a valid, fully opaque, completely black
pixmap on some X11 stacks -- no error and not null, so the old null check let it
through. The capture overlay then froze a black desktop and the exported
screenshot was black. These tests cover the blank detection, the fallback order,
and the configurable grab source.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

try:
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QColor, QImage, QPixmap

    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


def _solid_pixmap(width: int, height: int, color: QColor) -> QPixmap:
    """
    Builds a filled pixmap.

    Args:
        width: Pixmap width.
        height: Pixmap height.
        color: Fill color.

    Returns:
        QPixmap: Filled pixmap.
    """

    pixmap = QPixmap(width, height)
    pixmap.fill(color)
    return pixmap


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for capture fallback tests")
class TestBlankDetection(unittest.TestCase):
    """
    Verifies blank detection accepts real content and rejects empty grabs.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for image tests.
        """

        cls._app = ensure_qapp()

    def test_opaque_black_image_counts_as_blank(self) -> None:
        """
        Ensures the failure mode this fixes is detected: opaque, not null, black.
        """

        from src.desktop_grab import is_blank_pixmap

        pixmap = _solid_pixmap(400, 300, QColor(0, 0, 0, 255))
        self.assertFalse(pixmap.isNull())
        self.assertTrue(is_blank_pixmap(pixmap))

    def test_transparent_image_counts_as_blank(self) -> None:
        """
        Ensures a composed pixmap nothing was painted into is blank as well.
        """

        from src.desktop_grab import is_blank_pixmap

        self.assertTrue(is_blank_pixmap(_solid_pixmap(400, 300, QColor(0, 0, 0, 0))))

    def test_near_black_image_counts_as_blank(self) -> None:
        """
        Ensures dark noise a few levels above zero is still treated as empty.
        """

        from src.desktop_grab import is_blank_pixmap

        self.assertTrue(is_blank_pixmap(_solid_pixmap(400, 300, QColor(4, 4, 4, 255))))

    def test_desktop_content_is_not_blank(self) -> None:
        """
        Ensures a normal desktop grab is never mistaken for a failed one.
        """

        from src.desktop_grab import is_blank_pixmap

        self.assertFalse(is_blank_pixmap(_solid_pixmap(400, 300, QColor(30, 34, 44))))

    def test_single_bright_region_defeats_blank_detection(self) -> None:
        """
        Ensures a mostly black screen with visible content is kept.
        """

        from src.desktop_grab import is_blank_image

        image = QImage(400, 300, QImage.Format.Format_ARGB32)
        image.fill(QColor(0, 0, 0, 255))
        for y in range(0, 80):
            for x in range(0, 80):
                image.setPixelColor(x, y, QColor(200, 200, 200))
        self.assertFalse(is_blank_image(image))

    def test_null_pixmap_counts_as_blank(self) -> None:
        """
        Ensures a failed grab with no image at all is blank.
        """

        from src.desktop_grab import is_blank_pixmap

        self.assertTrue(is_blank_pixmap(QPixmap()))


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for capture fallback tests")
class TestGrabBackends(unittest.TestCase):
    """
    Verifies external backend selection and command construction.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for pixmap tests.
        """

        cls._app = ensure_qapp()

    def test_x11_and_wayland_backends_are_kept_apart(self) -> None:
        """
        Ensures grim is only offered on Wayland and x11grab only on X11.
        """

        from src.desktop_grab import backends_for_session

        x11_keys = [backend.key for backend in backends_for_session(wayland=False)]
        wayland_keys = [backend.key for backend in backends_for_session(wayland=True)]
        self.assertIn("ffmpeg", x11_keys)
        self.assertNotIn("grim", x11_keys)
        self.assertEqual(wayland_keys, ["grim"])

    def test_available_backends_skip_missing_tools(self) -> None:
        """
        Ensures only installed tools are offered.
        """

        from src.desktop_grab import available_grab_backends

        with patch(
            "src.desktop_grab.which",
            side_effect=lambda tool: "/usr/bin/maim" if tool == "maim" else None,
        ):
            keys = [backend.key for backend in available_grab_backends(wayland=False)]
        self.assertEqual(keys, ["maim"])

    def test_ffmpeg_command_carries_region_display_and_no_pointer(self) -> None:
        """
        Ensures x11grab reads the requested region and omits the mouse pointer,
        which Qt's grab does not include either.
        """

        from src.desktop_grab import backends_for_session, build_grab_command

        backend = next(
            item for item in backends_for_session(wayland=False) if item.key == "ffmpeg"
        )
        with patch.dict("os.environ", {"DISPLAY": ":1"}):
            command = build_grab_command(backend, 100, 40, 800, 600)
        self.assertIn("-video_size", command)
        self.assertIn("800x600", command)
        self.assertIn(":1+100,40", command)
        self.assertEqual(command[command.index("-draw_mouse") + 1], "0")

    def test_grim_command_uses_wayland_geometry_syntax(self) -> None:
        """
        Ensures the Wayland backend gets grim's ``x,y WxH`` geometry.
        """

        from src.desktop_grab import backends_for_session, build_grab_command

        backend = backends_for_session(wayland=True)[0]
        command = build_grab_command(backend, 10, 20, 300, 200)
        self.assertEqual(command, ["grim", "-g", "10,20 300x200", "-"])

    def test_file_based_backend_receives_output_path(self) -> None:
        """
        Ensures backends without stdout support write to the given path.
        """

        from src.desktop_grab import backends_for_session, build_grab_command

        backend = next(
            item
            for item in backends_for_session(wayland=False)
            if not item.writes_to_stdout
        )
        command = build_grab_command(backend, 0, 0, 100, 100, "/tmp/shot.png")
        self.assertIn("/tmp/shot.png", command)

    def test_full_desktop_result_is_cropped_to_the_region(self) -> None:
        """
        Ensures a tool that can only grab everything still yields the region.
        """

        from src.desktop_grab import fit_pixmap_to_region

        source = QPixmap(200, 100)
        source.fill(QColor(10, 20, 30))
        result = fit_pixmap_to_region(source, 50, 20, 80, 40, crops_region=False)
        self.assertEqual((result.width(), result.height()), (80, 40))

    def test_matching_size_is_returned_untouched(self) -> None:
        """
        Ensures the common case does not copy or scale the pixmap.
        """

        from src.desktop_grab import fit_pixmap_to_region

        source = QPixmap(80, 40)
        source.fill(QColor(10, 20, 30))
        result = fit_pixmap_to_region(source, 0, 0, 80, 40, crops_region=True)
        self.assertIs(result, source)

    def test_unexpected_resolution_is_scaled_to_the_region(self) -> None:
        """
        Ensures a tool reporting another resolution stays usable.
        """

        from src.desktop_grab import fit_pixmap_to_region

        source = QPixmap(60, 30)
        source.fill(QColor(10, 20, 30))
        result = fit_pixmap_to_region(source, 0, 0, 120, 60, crops_region=True)
        self.assertEqual((result.width(), result.height()), (120, 60))


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for capture fallback tests")
class TestCaptureFullScreenFallback(unittest.TestCase):
    """
    Verifies capture_full_screen keeps the first grab that has visible content.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for screen enumeration.
        """

        cls._app = ensure_qapp()

    def setUp(self) -> None:
        """
        Resets the module state the fallback logic keeps per session.
        """

        import src.capture as capture

        from src.config import CAPTURE_BACKEND_AUTO

        capture._qt_grab_unreliable = False
        capture._blank_capture_warning_shown = False
        capture.set_capture_backend_preference(CAPTURE_BACKEND_AUTO)
        # The reference probe talks to the real X server; these tests exercise the
        # content heuristics, so it stays neutral unless a test says otherwise.
        probe = patch.object(capture, "verify_image_against_x11", return_value=None)
        probe.start()
        self.addCleanup(probe.stop)

    def test_black_qt_grab_is_replaced_by_the_external_backend(self) -> None:
        """
        Ensures the reported bug is gone: a black Qt grab no longer reaches the
        capture overlay when an external tool can deliver the desktop.
        """

        import src.capture as capture

        content = _solid_pixmap(64, 48, QColor(30, 34, 44))
        with patch.object(
            capture,
            "_compose_qt_desktop_grab",
            return_value=(_solid_pixmap(64, 48, QColor(0, 0, 0)), 0.0),
        ), patch.object(
            capture, "_external_desktop_grab", return_value=(content, "ffmpeg")
        ):
            snapshot = capture.capture_full_screen()

        self.assertEqual(snapshot.backend, "ffmpeg")
        self.assertFalse(snapshot.blank)
        self.assertFalse(snapshot.pixmap.isNull())

    def test_blank_qt_grab_demotes_qt_for_later_captures(self) -> None:
        """
        Ensures the second capture skips the grab that is known to be broken,
        instead of paying for a black grab every time.
        """

        import src.capture as capture

        from src.desktop_grab import GRAB_BACKEND_QT

        content = _solid_pixmap(64, 48, QColor(30, 34, 44))
        self.assertEqual(capture._desktop_grab_order()[0], GRAB_BACKEND_QT)
        with patch.object(
            capture,
            "_compose_qt_desktop_grab",
            return_value=(_solid_pixmap(64, 48, QColor(0, 0, 0)), 0.0),
        ), patch.object(
            capture, "_external_desktop_grab", return_value=(content, "ffmpeg")
        ):
            capture.capture_full_screen()

        self.assertTrue(capture.qt_grab_unreliable())
        self.assertNotEqual(capture._desktop_grab_order()[0], GRAB_BACKEND_QT)

    def test_working_qt_grab_skips_the_external_tool(self) -> None:
        """
        Ensures the fast path stays fast: no external process on a good grab.
        """

        import src.capture as capture

        from src.desktop_grab import GRAB_BACKEND_QT

        with patch.object(
            capture,
            "_compose_qt_desktop_grab",
            return_value=(_solid_pixmap(64, 48, QColor(30, 34, 44)), 1.0),
        ), patch.object(capture, "_external_desktop_grab") as external:
            snapshot = capture.capture_full_screen()

        external.assert_not_called()
        self.assertEqual(snapshot.backend, GRAB_BACKEND_QT)
        self.assertFalse(snapshot.blank)

    def test_all_sources_blank_still_returns_the_image_but_flags_it(self) -> None:
        """
        Ensures a genuinely black desktop is still captured, and marked so the
        caller can explain it once.
        """

        import src.capture as capture

        with patch.object(
            capture,
            "_compose_qt_desktop_grab",
            return_value=(_solid_pixmap(64, 48, QColor(0, 0, 0)), 0.0),
        ), patch.object(capture, "_external_desktop_grab", return_value=None):
            snapshot = capture.capture_full_screen()

        self.assertTrue(snapshot.blank)
        self.assertFalse(snapshot.pixmap.isNull())

    def test_qt_preference_never_calls_an_external_tool(self) -> None:
        """
        Ensures the manual 'Qt only' setting is honored even on a black grab.
        """

        import src.capture as capture

        from src.config import CAPTURE_BACKEND_QT

        capture.set_capture_backend_preference(CAPTURE_BACKEND_QT)
        with patch.object(
            capture,
            "_compose_qt_desktop_grab",
            return_value=(_solid_pixmap(64, 48, QColor(0, 0, 0)), 0.0),
        ), patch.object(capture, "_external_desktop_grab") as external:
            snapshot = capture.capture_full_screen()

        external.assert_not_called()
        self.assertTrue(snapshot.blank)

    def test_external_preference_never_calls_the_qt_grab(self) -> None:
        """
        Ensures the manual 'External tool only' setting bypasses Qt completely.
        """

        import src.capture as capture

        from src.config import CAPTURE_BACKEND_EXTERNAL

        capture.set_capture_backend_preference(CAPTURE_BACKEND_EXTERNAL)
        content = _solid_pixmap(64, 48, QColor(30, 34, 44))
        with patch.object(capture, "_compose_qt_desktop_grab") as qt_grab, patch.object(
            capture, "_external_desktop_grab", return_value=(content, "maim")
        ):
            snapshot = capture.capture_full_screen()

        qt_grab.assert_not_called()
        self.assertEqual(snapshot.backend, "maim")

    def test_wayland_prefers_the_external_backend(self) -> None:
        """
        Ensures Wayland skips a Qt grab that cannot work there in the first place.
        """

        import src.capture as capture

        from src.desktop_grab import GRAB_BACKEND_QT

        with patch.object(capture, "is_wayland_session", return_value=True):
            self.assertNotEqual(capture._desktop_grab_order()[0], GRAB_BACKEND_QT)

    def test_single_screen_null_grab_is_not_painted(self) -> None:
        """
        Ensures a screen whose grab failed leaves the composed image empty
        instead of contributing a transparent hole that looks like content.
        """

        import src.capture as capture

        class FakeScreen:
            def __init__(self, rect: QRect, pixmap: QPixmap) -> None:
                self._rect = rect
                self._pixmap = pixmap

            def geometry(self) -> QRect:
                return self._rect

            def grabWindow(self, _window_id: int) -> QPixmap:
                return self._pixmap

        rect = QRect(0, 0, 64, 48)
        composed, fraction = capture._compose_qt_desktop_grab(
            [FakeScreen(rect, QPixmap())], rect
        )
        self.assertTrue(composed.isNull())
        self.assertEqual(fraction, 0.0)

    def test_blank_warning_is_shown_only_once(self) -> None:
        """
        Ensures a broken session explains itself once instead of nagging on
        every capture.
        """

        import src.capture as capture

        with patch.object(capture.QMessageBox, "warning") as warning:
            capture._warn_blank_capture_once()
            capture._warn_blank_capture_once()
        warning.assert_called_once()


class TestCaptureBackendConfig(unittest.TestCase):
    """
    Verifies the grab source survives a config round-trip.
    """

    def test_invalid_backend_falls_back_to_automatic(self) -> None:
        """
        Ensures a hand-edited config cannot disable the fallback by accident.
        """

        from src.config import CAPTURE_BACKEND_AUTO, normalize_capture_backend

        self.assertEqual(normalize_capture_backend("nonsense"), CAPTURE_BACKEND_AUTO)
        self.assertEqual(normalize_capture_backend(""), CAPTURE_BACKEND_AUTO)

    def test_backend_choice_is_saved_and_loaded(self) -> None:
        """
        Ensures the manual override persists across restarts.
        """

        import tempfile
        from pathlib import Path

        from src.config import CAPTURE_BACKEND_EXTERNAL, AppConfig, ConfigManager

        with tempfile.TemporaryDirectory() as directory:
            manager = ConfigManager(Path(directory) / "config.json")
            manager.save(AppConfig(capture_backend=CAPTURE_BACKEND_EXTERNAL))
            self.assertEqual(manager.load().capture_backend, CAPTURE_BACKEND_EXTERNAL)

    def test_default_is_automatic(self) -> None:
        """
        Ensures a fresh install repairs black captures without configuration.
        """

        from src.config import CAPTURE_BACKEND_AUTO, AppConfig

        self.assertEqual(AppConfig().capture_backend, CAPTURE_BACKEND_AUTO)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for capture fallback tests")
class TestPartiallyEmptyGrab(unittest.TestCase):
    """
    Verifies grabs that fail on only part of the desktop are caught too.

    The first fix only rejected grabs that were empty everywhere. On a
    multi-monitor desktop the failure is per screen: one black monitor next to a
    working one still leaves plenty of content in the composed image, which
    passed as a success and froze a half-black desktop into the overlay.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for pixmap tests.
        """

        cls._app = ensure_qapp()

    def setUp(self) -> None:
        """
        Resets the per-session grab state.
        """

        import src.capture as capture

        from src.config import CAPTURE_BACKEND_AUTO

        capture._qt_grab_unreliable = False
        capture._blank_capture_warning_shown = False
        capture.set_capture_backend_preference(CAPTURE_BACKEND_AUTO)
        # The reference probe talks to the real X server; these tests exercise the
        # content heuristics, so it stays neutral unless a test says otherwise.
        probe = patch.object(capture, "verify_image_against_x11", return_value=None)
        probe.start()
        self.addCleanup(probe.stop)

    class _FakeScreen:
        """
        Minimal QScreen stand-in returning a prepared grab.
        """

        def __init__(self, rect, pixmap) -> None:
            self._rect = rect
            self._pixmap = pixmap

        def geometry(self):
            return self._rect

        def grabWindow(self, _window_id: int):
            return self._pixmap

    def test_one_black_screen_of_two_is_reported_as_untrustworthy(self) -> None:
        """
        Ensures the emptiest screen decides, not the composed average.
        """

        import src.capture as capture

        left = self._FakeScreen(
            QRect(0, 0, 64, 48), _solid_pixmap(64, 48, QColor(30, 34, 44))
        )
        right = self._FakeScreen(
            QRect(64, 0, 64, 48), _solid_pixmap(64, 48, QColor(0, 0, 0))
        )
        composed, worst = capture._compose_qt_desktop_grab(
            [left, right], QRect(0, 0, 128, 48)
        )

        self.assertFalse(composed.isNull())
        self.assertEqual(worst, 0.0)
        # The composed image itself looks fine -- that is why it slipped through.
        from src.desktop_grab import is_blank_pixmap

        self.assertFalse(is_blank_pixmap(composed))

    def test_half_black_desktop_falls_back_to_the_external_tool(self) -> None:
        """
        Ensures the reported symptom is gone: with one monitor black, the whole
        capture is repeated externally instead of freezing a half-black desktop.
        """

        import src.capture as capture

        half_black = _solid_pixmap(128, 48, QColor(30, 34, 44))
        full = _solid_pixmap(128, 48, QColor(30, 34, 44))
        with patch.object(
            capture, "_compose_qt_desktop_grab", return_value=(half_black, 0.0)
        ), patch.object(
            capture, "_external_desktop_grab", return_value=(full, "ffmpeg")
        ):
            snapshot = capture.capture_full_screen()

        self.assertEqual(snapshot.backend, "ffmpeg")
        self.assertFalse(snapshot.blank)
        self.assertTrue(capture.qt_grab_unreliable())

    def test_sparse_grab_loses_against_a_richer_external_grab(self) -> None:
        """
        Ensures a grab that returns only a sliver of content is cross-checked and
        replaced when another source has more of the desktop.
        """

        import src.capture as capture

        # One visible window on an otherwise black desktop: the sampling grid is
        # 64px, so the image has to be desktop-sized for the share to be realistic.
        source = QImage(640, 480, QImage.Format.Format_ARGB32)
        source.fill(QColor(0, 0, 0))
        for y in range(0, 40):
            for x in range(0, 40):
                source.setPixelColor(x, y, QColor(220, 220, 220))
        sparse = QPixmap.fromImage(source)
        rich = _solid_pixmap(640, 480, QColor(30, 34, 44))

        with patch.object(
            capture, "_compose_qt_desktop_grab", return_value=(sparse, 1.0)
        ), patch.object(capture, "_external_desktop_grab", return_value=(rich, "maim")):
            snapshot = capture.capture_full_screen()

        self.assertEqual(snapshot.backend, "maim")

    def test_healthy_grab_still_skips_the_cross_check(self) -> None:
        """
        Ensures the safety net costs nothing on a normal desktop: no external
        process is started when every screen delivered content.
        """

        import src.capture as capture

        from src.desktop_grab import GRAB_BACKEND_QT

        good = _solid_pixmap(128, 48, QColor(30, 34, 44))
        with patch.object(
            capture, "_compose_qt_desktop_grab", return_value=(good, 1.0)
        ), patch.object(capture, "_external_desktop_grab") as external:
            snapshot = capture.capture_full_screen()

        external.assert_not_called()
        self.assertEqual(snapshot.backend, GRAB_BACKEND_QT)

    def test_dark_desktop_is_kept_when_no_source_has_more_content(self) -> None:
        """
        Ensures a genuinely black screen stays capturable instead of being
        rejected as a failure.
        """

        import src.capture as capture

        black = _solid_pixmap(128, 48, QColor(0, 0, 0))
        with patch.object(
            capture, "_compose_qt_desktop_grab", return_value=(black, 0.0)
        ), patch.object(
            capture, "_external_desktop_grab", return_value=(black, "ffmpeg")
        ), patch("src.crash_log.log_note"):
            snapshot = capture.capture_full_screen()

        self.assertFalse(snapshot.pixmap.isNull())
        self.assertTrue(snapshot.blank)

    def test_contradicted_grab_falls_back_even_when_it_looks_full(self) -> None:
        """
        Ensures the reference probe overrules the content heuristics.

        A grab can come back rich in content and still be wrong -- this is the
        case pure statistics cannot see, and the one that kept reaching users.
        """

        import src.capture as capture

        looks_fine = _solid_pixmap(128, 48, QColor(30, 34, 44))
        real = _solid_pixmap(128, 48, QColor(90, 120, 200))
        with patch.object(
            capture, "_compose_qt_desktop_grab", return_value=(looks_fine, 1.0)
        ), patch.object(
            capture, "verify_image_against_x11", return_value=False
        ), patch.object(
            capture, "_external_desktop_grab", return_value=(real, "ffmpeg")
        ), patch("src.crash_log.log_note"):
            snapshot = capture.capture_full_screen()

        self.assertEqual(snapshot.backend, "ffmpeg")
        self.assertTrue(capture.qt_grab_unreliable())

    def test_confirmed_grab_is_kept_without_external_call(self) -> None:
        """
        Ensures a grab the X server confirms is used directly.
        """

        import src.capture as capture

        from src.desktop_grab import GRAB_BACKEND_QT

        good = _solid_pixmap(128, 48, QColor(30, 34, 44))
        with patch.object(
            capture, "_compose_qt_desktop_grab", return_value=(good, 1.0)
        ), patch.object(
            capture, "verify_image_against_x11", return_value=True
        ), patch.object(capture, "_external_desktop_grab") as external:
            snapshot = capture.capture_full_screen()

        external.assert_not_called()
        self.assertEqual(snapshot.backend, GRAB_BACKEND_QT)

    def test_degraded_capture_is_written_to_the_crash_log(self) -> None:
        """
        Ensures an intermittent failure leaves evidence behind, so a repeat
        report can be answered from data instead of guesswork.
        """

        import src.capture as capture

        black = _solid_pixmap(128, 48, QColor(0, 0, 0))
        with patch.object(
            capture, "_compose_qt_desktop_grab", return_value=(black, 0.0)
        ), patch.object(
            capture, "_external_desktop_grab", return_value=None
        ), patch("src.crash_log.log_note") as note:
            capture.capture_full_screen()

        note.assert_called_once()
        body = note.call_args.args[1]
        self.assertIn("Visible content", body)
        self.assertIn("qt", body)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for capture fallback tests")
class TestX11ReferenceProbe(unittest.TestCase):
    """
    Verifies the X server reference check that judges a grab.

    Content statistics cannot separate "the grab is broken" from "the desktop is
    dark". Comparing small tiles against what the X server reports can, so this
    check decides whether a grab is trusted -- and it must be both correct and
    tolerant of the desktop changing between grab and probe.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for image tests.
        """

        cls._app = ensure_qapp()

    def _image(self, color: QColor) -> QImage:
        """
        Builds a filled desktop-sized image.

        Args:
            color: Fill color.

        Returns:
            QImage: Filled image.
        """

        image = QImage(640, 480, QImage.Format.Format_ARGB32)
        image.fill(color)
        return image

    def _verify(self, image: QImage, reference_brightness):
        """
        Runs the reference check with a stubbed X server probe.

        Args:
            image: Grabbed image to judge.
            reference_brightness: Callable or value the probe returns per tile.

        Returns:
            bool | None: Check result.
        """

        from src.desktop_grab import verify_image_against_x11

        sampler = (
            reference_brightness
            if callable(reference_brightness)
            else (lambda *_args: reference_brightness)
        )
        with patch("src.desktop_grab._x11_probe_root", return_value=object()), patch(
            "src.desktop_grab.sample_x11_tile_brightness", side_effect=sampler
        ):
            return verify_image_against_x11(
                image, QRect(0, 0, 640, 480), [QRect(0, 0, 640, 480)]
            )

    def test_black_grab_on_a_lit_screen_is_contradicted(self) -> None:
        """
        Ensures the observed failure is detected: the grab says black, the X
        server says there is content.
        """

        self.assertIs(self._verify(self._image(QColor(0, 0, 0)), 200.0), False)

    def test_matching_grab_is_confirmed(self) -> None:
        """
        Ensures a grab that agrees with the screen is accepted.
        """

        self.assertIs(self._verify(self._image(QColor(200, 200, 200)), 200.0), True)

    def test_dark_screen_cannot_be_judged(self) -> None:
        """
        Ensures a genuinely dark desktop is not called a failure -- there is
        nothing to compare, so the content heuristics decide instead.
        """

        self.assertIsNone(self._verify(self._image(QColor(0, 0, 0)), 1.0))

    def test_missing_probe_cannot_be_judged(self) -> None:
        """
        Ensures a system without python-xlib degrades to the heuristics.
        """

        from src.desktop_grab import verify_image_against_x11

        with patch("src.desktop_grab._x11_probe_root", return_value=None):
            result = verify_image_against_x11(
                self._image(QColor(0, 0, 0)),
                QRect(0, 0, 640, 480),
                [QRect(0, 0, 640, 480)],
            )
        self.assertIsNone(result)

    def test_a_single_repainted_tile_does_not_condemn_the_grab(self) -> None:
        """
        Ensures a window repainting between grab and probe is tolerated: only a
        solid share of disagreeing tiles counts as a broken grab.
        """

        image = self._image(QColor(200, 200, 200))
        for y in range(0, 40):
            for x in range(0, 40):
                image.setPixelColor(x, y, QColor(0, 0, 0))
        self.assertIs(self._verify(image, 200.0), True)

    def test_null_image_cannot_be_judged(self) -> None:
        """
        Ensures a failed grab with no image is left to the null checks.
        """

        from src.desktop_grab import verify_image_against_x11

        self.assertIsNone(
            verify_image_against_x11(QImage(), QRect(0, 0, 640, 480), [])
        )

    def test_probe_points_stay_inside_the_screen(self) -> None:
        """
        Ensures probe tiles never read past a screen edge, which would make the
        X server return an error instead of pixels.
        """

        from src.desktop_grab import REFERENCE_TILE_SIZE, _probe_points

        rect = QRect(2560, 0, 2560, 1440)
        points = _probe_points(rect)
        self.assertTrue(points)
        for x, y in points:
            self.assertGreaterEqual(x, rect.x())
            self.assertGreaterEqual(y, rect.y())
            self.assertLessEqual(x + REFERENCE_TILE_SIZE, rect.x() + rect.width())
            self.assertLessEqual(y + REFERENCE_TILE_SIZE, rect.y() + rect.height())


if __name__ == "__main__":
    unittest.main()
