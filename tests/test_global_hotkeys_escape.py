"""
Unit tests for the always-registered Escape-stops-recording global hotkey and
for the temporary Escape listener used while a capture overlay cannot hold focus.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.config import AppConfig
from src.global_hotkeys import EscapeListener, GlobalHotkeyManager, HotkeyBridge


class TestEscapeStopsRecording(unittest.TestCase):
    """
    Verifies apply_config always includes an Escape binding for recording_stop.
    """

    def test_escape_binding_is_registered_by_default(self) -> None:
        """
        Ensures <esc> is present in the pynput mapping and triggers recording_stop.
        """

        bridge = HotkeyBridge()
        manager = GlobalHotkeyManager(bridge)
        received: list[str] = []
        bridge.triggered.connect(received.append)

        captured_mapping = {}

        def fake_global_hotkeys(mapping):
            captured_mapping.update(mapping)
            fake_listener = MagicMock()
            return fake_listener

        with patch("src.global_hotkeys.PYNPUT_AVAILABLE", True), patch(
            "src.global_hotkeys.keyboard"
        ) as mock_keyboard:
            mock_keyboard.GlobalHotKeys.side_effect = fake_global_hotkeys
            result = manager.apply_config(AppConfig())

        self.assertTrue(result)
        self.assertIn("<esc>", captured_mapping)

        captured_mapping["<esc>"]()
        self.assertEqual(received, ["recording_stop"])

    def test_escape_does_not_override_an_explicit_user_binding(self) -> None:
        """
        Ensures a (currently impossible, but future-proofed) explicit binding
        to the exact "<esc>" pynput spec is not silently overwritten.
        """

        bridge = HotkeyBridge()
        manager = GlobalHotkeyManager(bridge)
        received: list[str] = []
        bridge.triggered.connect(received.append)

        captured_mapping = {}

        def fake_global_hotkeys(mapping):
            captured_mapping.update(mapping)
            return MagicMock()

        config = AppConfig()
        with patch("src.global_hotkeys.PYNPUT_AVAILABLE", True), patch(
            "src.global_hotkeys.hotkey_spec_to_pynput",
            side_effect=lambda spec: "<esc>" if spec == config.hotkey_capture_region else None,
        ), patch("src.global_hotkeys.keyboard") as mock_keyboard:
            mock_keyboard.GlobalHotKeys.side_effect = fake_global_hotkeys
            manager.apply_config(config)

        captured_mapping["<esc>"]()
        self.assertEqual(received, ["capture_region"])


class TestEscapeListener(unittest.TestCase):
    """
    Verifies the temporary global Escape listener used during window capture.

    The Linux window-capture overlay is input-transparent so xdotool can pick
    the window beneath it, which leaves no window of the app able to receive
    key events -- this listener is what makes Escape cancel the selection.
    """

    def test_escape_key_emits_the_signal(self) -> None:
        """
        Ensures pressing Escape reaches the Qt side.
        """

        listener = EscapeListener()
        fired: list[bool] = []
        listener.escape_pressed.connect(lambda: fired.append(True))

        captured = {}

        def fake_listener(on_press):
            captured["on_press"] = on_press
            return MagicMock()

        with patch("src.global_hotkeys.PYNPUT_AVAILABLE", True), patch(
            "src.global_hotkeys.keyboard"
        ) as mock_keyboard:
            mock_keyboard.Listener.side_effect = fake_listener
            self.assertTrue(listener.start())
            captured["on_press"](mock_keyboard.Key.esc)

        self.assertEqual(fired, [True])

    def test_other_keys_are_ignored(self) -> None:
        """
        Ensures unrelated keys never cancel a capture.
        """

        listener = EscapeListener()
        fired: list[bool] = []
        listener.escape_pressed.connect(lambda: fired.append(True))

        captured = {}

        def fake_listener(on_press):
            captured["on_press"] = on_press
            return MagicMock()

        with patch("src.global_hotkeys.PYNPUT_AVAILABLE", True), patch(
            "src.global_hotkeys.keyboard"
        ) as mock_keyboard:
            mock_keyboard.Listener.side_effect = fake_listener
            listener.start()
            captured["on_press"]("a")

        self.assertEqual(fired, [])

    def test_listener_is_passive_and_does_not_suppress(self) -> None:
        """
        Ensures Escape is not swallowed from the rest of the desktop.

        pynput suppresses keys only when ``suppress=True`` is passed, so the
        listener must be constructed without it.
        """

        listener = EscapeListener()
        with patch("src.global_hotkeys.PYNPUT_AVAILABLE", True), patch(
            "src.global_hotkeys.keyboard"
        ) as mock_keyboard:
            listener.start()
            _args, kwargs = mock_keyboard.Listener.call_args

        self.assertNotIn("suppress", kwargs)

    def test_start_is_idempotent_and_stop_releases(self) -> None:
        """
        Ensures repeated starts reuse one listener and stop tears it down.
        """

        listener = EscapeListener()
        fake = MagicMock()
        with patch("src.global_hotkeys.PYNPUT_AVAILABLE", True), patch(
            "src.global_hotkeys.keyboard"
        ) as mock_keyboard:
            mock_keyboard.Listener.return_value = fake
            self.assertTrue(listener.start())
            self.assertTrue(listener.start())
            self.assertEqual(mock_keyboard.Listener.call_count, 1)

            listener.stop()
            fake.stop.assert_called_once()
            listener.stop()
            fake.stop.assert_called_once()

    def test_unsupported_platform_reports_failure(self) -> None:
        """
        Ensures a missing pynput degrades quietly instead of raising.
        """

        listener = EscapeListener()
        with patch("src.global_hotkeys.PYNPUT_AVAILABLE", False):
            self.assertFalse(listener.start())
        listener.stop()

    def test_start_failure_does_not_raise(self) -> None:
        """
        Ensures a platform refusing the input hook is handled.
        """

        listener = EscapeListener()
        with patch("src.global_hotkeys.PYNPUT_AVAILABLE", True), patch(
            "src.global_hotkeys.keyboard"
        ) as mock_keyboard:
            mock_keyboard.Listener.side_effect = OSError("no input hook")
            self.assertFalse(listener.start())


if __name__ == "__main__":
    unittest.main()
