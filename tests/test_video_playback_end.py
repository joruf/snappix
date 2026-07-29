"""
Unit tests for video playback end-of-media handling.

Reaching the end of the video must rewind the playhead to the start and
re-enable immediate replay via the Play button, instead of leaving playback
stuck in a "just finished" state.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

try:
    from PySide6.QtMultimedia import QMediaPlayer

    from src.video_canvas import VideoCanvas
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for video playback tests")
class TestVideoCanvasPlaybackEnd(unittest.TestCase):
    """
    Verifies VideoCanvas rewinds and signals when playback reaches the end.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for media-player widget creation.
        """

        ensure_qapp()

    def test_end_of_media_rewinds_and_emits_playback_finished(self) -> None:
        """
        Ensures reaching EndOfMedia pauses, seeks back to position 0, and
        emits playback_finished so listeners can reset their Play button.
        """

        canvas = VideoCanvas()
        finished_spy = MagicMock()
        canvas.playback_finished.connect(finished_spy)

        canvas._on_media_status_changed(QMediaPlayer.MediaStatus.EndOfMedia)

        self.assertEqual(canvas._player.position(), 0)
        finished_spy.assert_called_once()

    def test_loaded_media_status_does_not_emit_playback_finished(self) -> None:
        """
        Ensures the unrelated first-frame-forcing statuses never emit
        playback_finished.
        """

        canvas = VideoCanvas()
        finished_spy = MagicMock()
        canvas.playback_finished.connect(finished_spy)

        canvas._on_media_status_changed(QMediaPlayer.MediaStatus.LoadedMedia)

        finished_spy.assert_not_called()


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for video playback tests")
class TestVideoEditorWindowPlaybackEnd(unittest.TestCase):
    """
    Verifies VideoEditorWindow resyncs its Play button when playback ends.
    """

    @classmethod
    def setUpClass(cls) -> None:
        ensure_qapp()

    def test_on_playback_finished_clears_is_playing_and_resyncs_icons(self) -> None:
        """
        Ensures _on_playback_finished flips _is_playing back to False and
        refreshes the Play/Pause icon, so a fresh Play click can start
        playback again immediately.
        """

        from src.video_editor_window import VideoEditorWindow

        window = VideoEditorWindow.__new__(VideoEditorWindow)
        window._is_playing = True
        window._sync_playback_action_icons = MagicMock()

        window._on_playback_finished()

        self.assertFalse(window._is_playing)
        window._sync_playback_action_icons.assert_called_once()


if __name__ == "__main__":
    unittest.main()
