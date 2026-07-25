"""
Unit tests for playback control icons.
"""

from __future__ import annotations

import unittest

try:
    from src.tool_icons import build_playback_icon
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for playback icon tests")
class TestPlaybackIcons(unittest.TestCase):
    """
    Verifies playback toolbar icons render for all control states.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for icon creation.
        """

        ensure_qapp()

    def test_build_playback_icon_returns_icons_for_all_controls(self) -> None:
        """
        Ensures each playback control has a non-empty icon.
        """

        for icon_id in ("play", "pause", "stop", "sound_on", "sound_off"):
            with self.subTest(icon_id=icon_id):
                icon = build_playback_icon(icon_id)
                self.assertFalse(icon.isNull())
                self.assertFalse(icon.pixmap(28, 28).isNull())


if __name__ == "__main__":
    unittest.main()
