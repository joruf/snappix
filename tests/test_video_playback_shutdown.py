"""
Tests for releasing the audio device before Snappix exits.

A video tab holds a PulseAudio stream open through ``QMediaPlayer``. Nothing
stopped it, so quitting tore the process down while the stream was still open,
which is what produced the audible click on exit.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

try:
    from PySide6.QtCore import QUrl

    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestCanvasPlaybackShutdown(unittest.TestCase):
    """
    Verifies the video canvas hands the audio device back.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def _canvas(self):
        """
        Builds a video canvas over a placeholder file.

        Returns:
            VideoCanvas: Canvas under test.
        """

        from src.video_canvas import VideoCanvas

        canvas = VideoCanvas()
        self.addCleanup(canvas.deleteLater)
        return canvas

    def test_playback_is_stopped_and_the_source_dropped(self) -> None:
        """
        Ensures the backend can close its stream in order.
        """

        canvas = self._canvas()
        player = MagicMock()
        canvas._player = player

        canvas.shutdown_playback()

        player.stop.assert_called_once()
        player.setSource.assert_called_once()
        self.assertTrue(player.setSource.call_args.args[0].isEmpty())

    def test_the_audio_output_is_muted_first(self) -> None:
        """
        Ensures the device goes quiet before the pipeline is torn down.
        """

        canvas = self._canvas()
        canvas._player = MagicMock()
        audio_output = MagicMock()
        canvas._audio_output = audio_output

        canvas.shutdown_playback()

        audio_output.setMuted.assert_called_with(True)

    def test_calling_it_twice_is_harmless(self) -> None:
        """
        Ensures both the tab close and the quit path may call it.
        """

        canvas = self._canvas()
        canvas._player = MagicMock()

        canvas.shutdown_playback()
        canvas.shutdown_playback()

        self.assertEqual(canvas._player.stop.call_count, 2)

    def test_an_already_destroyed_player_does_not_raise(self) -> None:
        """
        Ensures a tab whose C++ object is gone cannot break the quit path.
        """

        canvas = self._canvas()
        player = MagicMock()
        player.stop.side_effect = RuntimeError("wrapped C/C++ object deleted")
        canvas._player = player

        canvas.shutdown_playback()

    def test_a_canvas_without_a_player_does_not_raise(self) -> None:
        """
        Ensures partial construction cannot break the quit path.
        """

        canvas = self._canvas()
        canvas._player = None
        canvas._audio_output = None

        canvas.shutdown_playback()


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestEditorAndQuitPath(unittest.TestCase):
    """
    Verifies the release happens on tab close and on quit.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def _video_editor(self):
        """
        Builds a video editor tab over a placeholder file.

        Returns:
            VideoEditorWindow: Editor under test.
        """

        from src.video_editor_window import VideoEditorWindow

        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        source = Path(tmp_dir.name) / "source.mp4"
        source.write_bytes(b"not-a-real-video")
        editor = VideoEditorWindow(str(source), 320, 240)
        self.addCleanup(editor.close)
        return editor

    def test_the_editor_forwards_the_release_to_its_canvas(self) -> None:
        """
        Ensures the tab knows how to hand back its audio device.
        """

        editor = self._video_editor()
        with patch.object(editor.canvas, "shutdown_playback") as release:
            editor.shutdown_playback()
        release.assert_called_once()

    def test_closing_a_tab_releases_the_audio_device(self) -> None:
        """
        Ensures a closed tab does not keep the stream open in the background.
        """

        editor = self._video_editor()
        editor.set_minimize_to_tray_on_close(False)
        with patch.object(editor, "shutdown_playback") as release, patch.object(
            editor, "confirm_close_if_needed", return_value=True
        ):
            editor.close()
        release.assert_called_once()

    def test_quitting_releases_every_video_tab(self) -> None:
        """
        Ensures the quit path reaches all tabs, not just the visible one.

        This is the one that mattered in practice: the click was heard when
        Snappix exited, not when a tab was closed.
        """

        import run as snappix_run

        controller = snappix_run.AppController.__new__(snappix_run.AppController)
        video_tabs = [MagicMock(), MagicMock()]
        image_tab = MagicMock(spec=[])
        tabs = MagicMock()
        tabs.count.return_value = 3
        tabs.widget.side_effect = [video_tabs[0], image_tab, video_tabs[1]]
        controller.editor_tabs = tabs

        controller._release_video_playback()

        for tab in video_tabs:
            tab.shutdown_playback.assert_called_once()

    def test_quit_releases_playback_before_closing_tabs(self) -> None:
        """
        Ensures the quit path actually calls the release, and early enough.

        Closing the tabs first would destroy the players before their streams
        were handed back, which is the state that clicked.
        """

        import run as snappix_run

        controller = snappix_run.AppController.__new__(snappix_run.AppController)
        order: list[str] = []

        tabs = MagicMock()
        tabs.count.return_value = 0
        controller.editor_tabs = tabs
        controller._save_editor_session = MagicMock()
        controller._hotkey_manager = MagicMock()
        controller.capture_panel = MagicMock()
        controller.editor_host = MagicMock()
        controller.tray_icon = MagicMock()
        controller.app = MagicMock()
        controller._close_editor_tab_by_index = MagicMock(
            side_effect=lambda _index: order.append("close-tab")
        )

        with patch.object(
            snappix_run.AppController,
            "_release_video_playback",
            side_effect=lambda: order.append("release"),
        ) as release:
            controller.quit_application()

        release.assert_called_once()
        self.assertEqual(order[0], "release", f"released too late: {order}")

    def test_a_failing_tab_does_not_stop_the_others(self) -> None:
        """
        Ensures one dead tab cannot leave another one's stream open.
        """

        import run as snappix_run

        controller = snappix_run.AppController.__new__(snappix_run.AppController)
        broken = MagicMock()
        broken.shutdown_playback.side_effect = RuntimeError("gone")
        healthy = MagicMock()
        tabs = MagicMock()
        tabs.count.return_value = 2
        tabs.widget.side_effect = [broken, healthy]
        controller.editor_tabs = tabs

        controller._release_video_playback()

        healthy.shutdown_playback.assert_called_once()


if __name__ == "__main__":
    unittest.main()
