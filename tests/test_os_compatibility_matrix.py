"""
Compatibility-matrix tests for Snappix platform profiles.

Simulates Linux X11/Wayland and tool availability without switching OS.
"""

from __future__ import annotations

import unittest

from src.os_compatibility import (
    DARWIN,
    KNOWN_PROFILES,
    LINUX_WAYLAND_GRIM,
    LINUX_WAYLAND_NO_GRIM,
    LINUX_X11_FULL,
    LINUX_X11_MINIMAL,
    LINUX_X11_NO_XDOTOOL,
    WINDOWS,
    FeatureCapability,
    PlatformContext,
    SupportLevel,
    current_os_family,
    evaluate_capabilities,
    region_capture_route,
)


class TestOsCompatibilityMatrix(unittest.TestCase):
    """
    Verifies the documented OS compatibility matrix for Snappix profiles.
    """

    def test_known_profiles_cover_linux_sessions_and_non_linux(self) -> None:
        """
        Ensures the matrix includes X11, Wayland, and unsupported OS families.
        """

        self.assertIn("linux_x11_full", KNOWN_PROFILES)
        self.assertIn("linux_wayland_grim", KNOWN_PROFILES)
        self.assertIn("windows", KNOWN_PROFILES)
        self.assertIn("darwin", KNOWN_PROFILES)

    def test_non_linux_profiles(self) -> None:
        """
        Ensures Windows MVP launch is partial and macOS remains unsupported.
        """

        windows = evaluate_capabilities(WINDOWS)
        self.assertEqual(windows["app_launch"].level, SupportLevel.PARTIAL)
        self.assertEqual(windows["fullscreen_capture"].level, SupportLevel.FULL)
        self.assertEqual(windows["video_capture"].level, SupportLevel.FULL)
        self.assertEqual(windows["window_capture"].level, SupportLevel.FULL)
        self.assertEqual(windows["scroll_capture"].level, SupportLevel.PARTIAL)

        darwin = evaluate_capabilities(DARWIN)
        self.assertEqual(darwin["app_launch"].level, SupportLevel.UNSUPPORTED)

    def test_linux_x11_full_supports_capture_features(self) -> None:
        """
        Ensures a fully equipped X11 profile supports all capture modes.
        """

        capabilities = evaluate_capabilities(LINUX_X11_FULL)
        self.assertEqual(capabilities["app_launch"].level, SupportLevel.FULL)
        self.assertEqual(capabilities["region_capture"].level, SupportLevel.PARTIAL)
        self.assertEqual(capabilities["window_capture"].level, SupportLevel.FULL)
        self.assertEqual(capabilities["scroll_capture"].level, SupportLevel.FULL)
        self.assertEqual(capabilities["video_capture"].level, SupportLevel.FULL)
        self.assertEqual(capabilities["ocr"].level, SupportLevel.FULL)

    def test_linux_x11_without_xdotool_disables_window_and_scroll(self) -> None:
        """
        Ensures missing xdotool/xwininfo blocks X11-only capture modes.
        """

        capabilities = evaluate_capabilities(LINUX_X11_NO_XDOTOOL)
        self.assertEqual(capabilities["window_capture"].level, SupportLevel.UNSUPPORTED)
        self.assertEqual(capabilities["scroll_capture"].level, SupportLevel.UNSUPPORTED)
        self.assertEqual(capabilities["region_capture"].level, SupportLevel.PARTIAL)

    def test_linux_wayland_grim_uses_native_region_capture(self) -> None:
        """
        Ensures grim and slurp enable native Wayland region capture.
        """

        self.assertEqual(region_capture_route(LINUX_WAYLAND_GRIM), "grim_slurp")
        capabilities = evaluate_capabilities(LINUX_WAYLAND_GRIM)
        self.assertEqual(capabilities["region_capture"].level, SupportLevel.FULL)
        self.assertEqual(capabilities["window_capture"].level, SupportLevel.UNSUPPORTED)
        self.assertEqual(capabilities["scroll_capture"].level, SupportLevel.UNSUPPORTED)
        self.assertEqual(capabilities["video_capture"].level, SupportLevel.UNSUPPORTED)

    def test_linux_wayland_without_grim_falls_back_to_qt_overlay(self) -> None:
        """
        Ensures Wayland without grim still allows overlay region capture.
        """

        self.assertEqual(region_capture_route(LINUX_WAYLAND_NO_GRIM), "qt_overlay")
        capabilities = evaluate_capabilities(LINUX_WAYLAND_NO_GRIM)
        self.assertEqual(capabilities["region_capture"].level, SupportLevel.PARTIAL)

    def test_linux_minimal_profile_still_launches(self) -> None:
        """
        Ensures the editor can run even when optional tools are absent.
        """

        capabilities = evaluate_capabilities(LINUX_X11_MINIMAL)
        self.assertEqual(capabilities["app_launch"].level, SupportLevel.FULL)
        self.assertEqual(capabilities["ocr"].level, SupportLevel.UNSUPPORTED)
        self.assertEqual(capabilities["video_capture"].level, SupportLevel.UNSUPPORTED)

    def test_matrix_profile_expectations(self) -> None:
        """
        Ensures every known profile matches its expected capability levels.
        """

        expectations: dict[str, dict[str, SupportLevel]] = {
            "linux_x11_full": {
                "app_launch": SupportLevel.FULL,
                "window_capture": SupportLevel.FULL,
                "scroll_capture": SupportLevel.FULL,
                "video_capture": SupportLevel.FULL,
            },
            "linux_x11_minimal": {
                "app_launch": SupportLevel.FULL,
                "window_capture": SupportLevel.UNSUPPORTED,
                "video_capture": SupportLevel.UNSUPPORTED,
            },
            "linux_x11_no_xdotool": {
                "window_capture": SupportLevel.UNSUPPORTED,
                "scroll_capture": SupportLevel.UNSUPPORTED,
            },
            "linux_wayland_grim": {
                "region_capture": SupportLevel.FULL,
                "window_capture": SupportLevel.UNSUPPORTED,
                "global_hotkeys": SupportLevel.PARTIAL,
            },
            "linux_wayland_no_grim": {
                "region_capture": SupportLevel.PARTIAL,
                "video_capture": SupportLevel.UNSUPPORTED,
            },
            "windows": {
                "app_launch": SupportLevel.PARTIAL,
                "region_capture": SupportLevel.PARTIAL,
                "fullscreen_capture": SupportLevel.FULL,
                "video_capture": SupportLevel.FULL,
                "window_capture": SupportLevel.FULL,
                "scroll_capture": SupportLevel.PARTIAL,
                "autostart": SupportLevel.FULL,
            },
            "windows_minimal": {
                "app_launch": SupportLevel.PARTIAL,
                "video_capture": SupportLevel.UNSUPPORTED,
                "ocr": SupportLevel.UNSUPPORTED,
            },
            "darwin": {
                "app_launch": SupportLevel.UNSUPPORTED,
                "region_capture": SupportLevel.UNSUPPORTED,
            },
        }

        for profile_name, expected_levels in expectations.items():
            profile = KNOWN_PROFILES[profile_name]
            capabilities = evaluate_capabilities(profile)
            for feature_id, expected_level in expected_levels.items():
                with self.subTest(profile=profile_name, feature=feature_id):
                    actual = capabilities[feature_id]
                    self.assertEqual(
                        actual.level,
                        expected_level,
                        msg=f"{profile_name}/{feature_id}: {actual.note}",
                    )

    def test_current_os_family_is_linux_on_ci(self) -> None:
        """
        Ensures the runtime OS family helper reports Linux in this project CI.
        """

        self.assertEqual(current_os_family(), "linux")

    def test_evaluate_capabilities_returns_all_features(self) -> None:
        """
        Ensures every profile reports the full feature set used by diagnostics.
        """

        expected_features = {
            "app_launch",
            "fullscreen_capture",
            "region_capture",
            "window_capture",
            "scroll_capture",
            "video_capture",
            "ocr",
            "global_hotkeys",
            "autostart",
        }
        for profile_name, profile in KNOWN_PROFILES.items():
            with self.subTest(profile=profile_name):
                capabilities = evaluate_capabilities(profile)
                self.assertEqual(set(capabilities), expected_features)
                for capability in capabilities.values():
                    self.assertIsInstance(capability, FeatureCapability)
                    self.assertTrue(capability.note)


class TestRegionCaptureRouteParity(unittest.TestCase):
    """
    Verifies compatibility routing matches capture.py decision points.
    """

    def test_route_unavailable_outside_linux_and_windows(self) -> None:
        """
        Ensures macOS cannot select a capture route.
        """

        self.assertEqual(
            region_capture_route(PlatformContext(os_family="darwin")),
            "unavailable",
        )

    def test_route_uses_overlay_on_windows(self) -> None:
        """
        Ensures Windows region capture uses the Qt overlay route.
        """

        self.assertEqual(region_capture_route(WINDOWS), "qt_overlay")

    def test_route_prefers_grim_on_wayland_when_available(self) -> None:
        """
        Ensures grim+slurp wins over the Qt overlay on Wayland.
        """

        context = PlatformContext(
            os_family="linux",
            is_wayland=True,
            available_tools=frozenset({"grim", "slurp"}),
        )
        self.assertEqual(region_capture_route(context), "grim_slurp")

    def test_route_uses_overlay_on_x11(self) -> None:
        """
        Ensures X11 always uses the Qt overlay route for region capture.
        """

        self.assertEqual(region_capture_route(LINUX_X11_FULL), "qt_overlay")
