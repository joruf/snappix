"""
Unit tests for platform and session detection helpers.
"""

from __future__ import annotations

import os
import subprocess
import unittest
from unittest.mock import MagicMock, patch

from src.platform import (
    _parse_grim_selection_size,
    apply_linux_window_identity,
    apply_x11_wm_class,
    capture_region_with_grim_slurp,
    get_x11_focused_window_id,
    has_grim_and_slurp,
    has_tesseract,
    is_wayland_session,
)


class TestPlatform(unittest.TestCase):
    """
    Verifies platform detection and Wayland capture helpers.
    """

    def test_is_wayland_session_from_xdg_session_type(self) -> None:
        """
        Ensures XDG_SESSION_TYPE wayland is detected.
        """

        with patch.dict(os.environ, {"XDG_SESSION_TYPE": "wayland", "WAYLAND_DISPLAY": ""}, clear=False):
            self.assertTrue(is_wayland_session())

    def test_is_wayland_session_from_wayland_display(self) -> None:
        """
        Ensures WAYLAND_DISPLAY env var triggers Wayland detection.
        """

        with patch.dict(
            os.environ,
            {"XDG_SESSION_TYPE": "x11", "WAYLAND_DISPLAY": "wayland-0"},
            clear=False,
        ):
            self.assertTrue(is_wayland_session())

    def test_is_wayland_session_false_on_x11(self) -> None:
        """
        Ensures X11 sessions are not reported as Wayland.
        """

        with patch.dict(
            os.environ,
            {"XDG_SESSION_TYPE": "x11", "WAYLAND_DISPLAY": ""},
            clear=True,
        ):
            self.assertFalse(is_wayland_session())

    @patch("src.platform.which")
    def test_has_grim_and_slurp_requires_both(self, mock_which: MagicMock) -> None:
        """
        Ensures grim and slurp must both exist.
        """

        mock_which.side_effect = lambda name: "/usr/bin/grim" if name == "grim" else None
        self.assertFalse(has_grim_and_slurp())

        mock_which.side_effect = lambda name: f"/usr/bin/{name}"
        self.assertTrue(has_grim_and_slurp())

    @patch("src.platform.which")
    def test_has_tesseract(self, mock_which: MagicMock) -> None:
        """
        Ensures tesseract availability is detected via PATH lookup.
        """

        mock_which.return_value = None
        self.assertFalse(has_tesseract())
        mock_which.return_value = "/usr/bin/tesseract"
        self.assertTrue(has_tesseract())

    @patch("src.platform.has_grim_and_slurp", return_value=False)
    def test_capture_region_with_grim_slurp_without_tools(self, _mock_tools: MagicMock) -> None:
        """
        Ensures capture returns None when grim or slurp is missing.
        """

        self.assertIsNone(capture_region_with_grim_slurp())

    @patch("src.platform.subprocess.run")
    @patch("src.platform.has_grim_and_slurp", return_value=True)
    def test_capture_region_with_grim_slurp_success(
        self,
        _mock_tools: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        """
        Ensures grim and slurp output is parsed into PNG bytes and size.
        """

        slurp_result = MagicMock()
        slurp_result.stdout = "640x480+10+20"
        grim_result = MagicMock()
        grim_result.stdout = b"png-bytes"
        mock_run.side_effect = [slurp_result, grim_result]

        result = capture_region_with_grim_slurp()
        self.assertIsNotNone(result)
        assert result is not None
        png_bytes, width, height = result
        self.assertEqual(png_bytes, b"png-bytes")
        self.assertEqual(width, 640)
        self.assertEqual(height, 480)

    @patch("src.platform.subprocess.run")
    @patch("src.platform.has_grim_and_slurp", return_value=True)
    def test_capture_region_with_grim_slurp_parses_two_part_selection(
        self,
        _mock_tools: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        """
        Ensures slurp output with monitor prefix is parsed correctly.
        """

        slurp_result = MagicMock()
        slurp_result.stdout = "0,0 640x480+10+20"
        grim_result = MagicMock()
        grim_result.stdout = b"png-bytes"
        mock_run.side_effect = [slurp_result, grim_result]

        result = capture_region_with_grim_slurp()
        self.assertIsNotNone(result)
        assert result is not None
        _png_bytes, width, height = result
        self.assertEqual(width, 640)
        self.assertEqual(height, 480)

    @patch("src.platform.subprocess.run")
    @patch("src.platform.has_grim_and_slurp", return_value=True)
    def test_capture_region_with_grim_slurp_handles_errors(
        self,
        _mock_tools: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        """
        Ensures subprocess failures return None instead of raising.
        """

        mock_run.side_effect = subprocess.SubprocessError("failed")
        self.assertIsNone(capture_region_with_grim_slurp())


class TestGrimSelectionParsing(unittest.TestCase):
    """
    Verifies geometry parsing for grim-compatible slurp output.
    """

    def test_parse_single_token_geometry(self) -> None:
        """
        Ensures compact grim geometry strings are parsed.
        """

        self.assertEqual(_parse_grim_selection_size("640x480+10+20"), (640, 480))

    def test_parse_monitor_prefixed_geometry(self) -> None:
        """
        Ensures monitor-prefixed slurp output uses the geometry token.
        """

        self.assertEqual(_parse_grim_selection_size("0,0 640x480+10+20"), (640, 480))

    def test_parse_invalid_geometry_returns_zero(self) -> None:
        """
        Ensures invalid geometry strings fall back to zero size.
        """

        self.assertEqual(_parse_grim_selection_size(""), (0, 0))
        self.assertEqual(_parse_grim_selection_size("invalid"), (0, 0))


class TestLinuxWindowIdentity(unittest.TestCase):
    """
    Verifies Linux taskbar identity helpers.
    """

    @patch("src.platform.subprocess.run")
    def test_get_x11_focused_window_id_returns_active_window(
        self,
        mock_run: MagicMock,
    ) -> None:
        """
        Ensures focused window id is parsed from xdotool output.
        """

        mock_run.return_value = MagicMock(stdout="12345678\n")
        self.assertEqual(get_x11_focused_window_id(), "12345678")

    @patch("src.platform.apply_x11_wm_class", return_value=True)
    @patch("PySide6.QtGui.QGuiApplication.setDesktopFileName")
    def test_apply_linux_window_identity_sets_desktop_file_and_wm_class(
        self,
        mock_set_desktop_file_name: MagicMock,
        mock_apply_x11_wm_class: MagicMock,
    ) -> None:
        """
        Ensures desktop file name and WM_CLASS are applied together.
        """

        widget = MagicMock()
        apply_linux_window_identity(
            widget,
            desktop_file_name="snapagent-editor",
            wm_instance="snapagent-editor",
            wm_class="snapagent-editor",
        )
        mock_set_desktop_file_name.assert_called_once_with("snapagent-editor")
        mock_apply_x11_wm_class.assert_called_once_with(
            widget,
            "snapagent-editor",
            "snapagent-editor",
        )

    @patch("src.platform._resolve_x11_display_ptr", return_value=(None, False))
    @patch("PySide6.QtGui.QGuiApplication.platformName", return_value="xcb")
    def test_apply_x11_wm_class_returns_false_without_display(
        self,
        _mock_platform_name: MagicMock,
        _mock_display_ptr: MagicMock,
    ) -> None:
        """
        Ensures missing X11 display access fails gracefully.
        """

        widget = MagicMock()
        widget.windowHandle.return_value = MagicMock()
        widget.windowHandle.return_value.winId.return_value = 42
        self.assertFalse(apply_x11_wm_class(widget, "snapagent", "snapagent"))

    @patch("PySide6.QtGui.QGuiApplication.platformName", return_value="wayland")
    def test_apply_x11_wm_class_skips_non_x11_sessions(
        self,
        _mock_platform_name: MagicMock,
    ) -> None:
        """
        Ensures WM_CLASS updates are skipped outside X11/XCB sessions.
        """

        self.assertFalse(apply_x11_wm_class(MagicMock(), "snapagent", "snapagent"))
