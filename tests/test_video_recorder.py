"""
Unit tests for the ffmpeg-based video recording engine.
"""

from __future__ import annotations

import signal
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

try:
    from PySide6.QtCore import QRect

    from src.video_recorder import (
        OverlaySegment,
        RecordingState,
        VideoRecorder,
        build_export_command,
        build_record_command,
        clamp_region_to_even_dimensions,
    )
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


class TestClampRegion(unittest.TestCase):
    """
    Verifies even-dimension clamping for x11grab/libx264 compatibility.
    """

    def test_even_dimensions_are_unchanged(self) -> None:
        """
        Ensures already-even regions pass through unchanged.
        """

        rect = QRect(10, 20, 640, 480)
        clamped = clamp_region_to_even_dimensions(rect)
        self.assertEqual((clamped.width(), clamped.height()), (640, 480))
        self.assertEqual((clamped.x(), clamped.y()), (10, 20))

    def test_odd_dimensions_are_shrunk_to_even(self) -> None:
        """
        Ensures odd width/height are shrunk by one pixel, keeping the origin.
        """

        rect = QRect(5, 5, 641, 481)
        clamped = clamp_region_to_even_dimensions(rect)
        self.assertEqual((clamped.width(), clamped.height()), (640, 480))
        self.assertEqual((clamped.x(), clamped.y()), (5, 5))

    def test_tiny_regions_stay_at_minimum_size(self) -> None:
        """
        Ensures a 1x1 region does not clamp down to a zero-sized rect.
        """

        rect = QRect(0, 0, 1, 1)
        clamped = clamp_region_to_even_dimensions(rect)
        self.assertEqual((clamped.width(), clamped.height()), (2, 2))


class TestBuildRecordCommand(unittest.TestCase):
    """
    Verifies ffmpeg command construction for screen recording.
    """

    def test_command_without_microphone(self) -> None:
        """
        Ensures no pulse audio input is added when microphone recording is off.
        """

        rect = QRect(100, 200, 640, 480)
        command = build_record_command(
            rect, Path("/tmp/out.mp4"), record_microphone=False
        )
        self.assertIn("x11grab", command)
        self.assertIn("640x480", command)
        self.assertIn(":0.0+100,200", command)
        self.assertNotIn("pulse", command)
        self.assertNotIn("-c:a", command)

    def test_command_with_microphone(self) -> None:
        """
        Ensures a pulse audio input and higher-quality AAC encoding are added.
        """

        rect = QRect(0, 0, 640, 480)
        command = build_record_command(
            rect, Path("/tmp/out.mp4"), record_microphone=True
        )
        self.assertIn("pulse", command)
        self.assertIn("default", command)
        self.assertIn("aac", command)
        self.assertIn("192k", command)
        self.assertIn("48000", command)
        self.assertIn("-ac", command)
        # Stereo capture for clearer playback than the previous mono track.
        ac_index = command.index("-ac")
        self.assertEqual(command[ac_index + 1], "2")


class TestBuildExportCommand(unittest.TestCase):
    """
    Verifies ffmpeg command construction for burned-in annotation export.
    """

    def test_command_without_overlays_reencodes_audio(self) -> None:
        """
        Ensures an export with no overlay segments re-encodes video and audio.
        """

        command = build_export_command(Path("/tmp/in.mp4"), [], Path("/tmp/out.mp4"))
        self.assertNotIn("-filter_complex", command)
        self.assertIn(str(Path("/tmp/out.mp4")), command)
        self.assertIn("aac", command)
        self.assertIn("192k", command)
        self.assertNotIn("-an", command)

    def test_command_without_audio_strips_sound(self) -> None:
        """
        Ensures include_audio=False drops the audio track with -an.
        """

        command = build_export_command(
            Path("/tmp/in.mp4"),
            [],
            Path("/tmp/out.mp4"),
            include_audio=False,
        )
        self.assertIn("-an", command)
        self.assertNotIn("aac", command)

    def test_command_with_overlays_builds_filter_graph(self) -> None:
        """
        Ensures each overlay segment becomes a timed overlay filter input.
        """

        segments = [
            OverlaySegment(png_path=Path("/tmp/a.png"), start_s=0.0, end_s=1.5),
            OverlaySegment(png_path=Path("/tmp/b.png"), start_s=1.5, end_s=3.0),
        ]
        command = build_export_command(Path("/tmp/in.mp4"), segments, Path("/tmp/out.mp4"))
        self.assertIn("-filter_complex", command)
        filter_index = command.index("-filter_complex") + 1
        filter_complex = command[filter_index]
        self.assertIn("between(t,0.0,1.5)", filter_complex)
        self.assertIn("between(t,1.5,3.0)", filter_complex)
        self.assertEqual(command.count("/tmp/a.png"), 1)
        self.assertEqual(command.count("/tmp/b.png"), 1)
        self.assertIn("0:a?", command)
        self.assertIn("192k", command)

    def test_command_with_overlays_can_omit_audio(self) -> None:
        """
        Ensures overlay export can strip audio when requested.
        """

        segments = [
            OverlaySegment(png_path=Path("/tmp/a.png"), start_s=0.0, end_s=1.0),
        ]
        command = build_export_command(
            Path("/tmp/in.mp4"),
            segments,
            Path("/tmp/out.mp4"),
            include_audio=False,
        )
        self.assertIn("-an", command)
        self.assertNotIn("0:a?", command)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for recorder lifecycle tests")
class TestVideoRecorderLifecycle(unittest.TestCase):
    """
    Verifies the recorder's process lifecycle and signal sequencing.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for QObject/QTimer usage.
        """

        ensure_qapp()

    def _make_recorder_with_mock_process(self, poll_return_values=None):
        """
        Builds a VideoRecorder with a mocked ffmpeg subprocess already running.

        Args:
            poll_return_values: Sequence of return values for process.poll().

        Returns:
            tuple[VideoRecorder, MagicMock]: Recorder and its mocked process.
        """

        recorder = VideoRecorder()
        mock_process = MagicMock()
        mock_process.pid = 4242
        mock_process.poll.side_effect = poll_return_values or [0]
        with patch("src.video_recorder.has_ffmpeg", return_value=True), patch(
            "subprocess.Popen", return_value=mock_process
        ):
            started = recorder.start(
                QRect(0, 0, 640, 480), Path("/tmp/rec.mp4"), record_microphone=False
            )
        self.assertTrue(started)
        return recorder, mock_process

    def test_pause_sends_sigstop(self) -> None:
        """
        Ensures pause() suspends the ffmpeg process via SIGSTOP.
        """

        recorder, mock_process = self._make_recorder_with_mock_process()
        with patch("os.kill") as mock_kill:
            recorder.pause()
            mock_kill.assert_called_once_with(mock_process.pid, signal.SIGSTOP)
        self.assertEqual(recorder.state, RecordingState.PAUSED)

    def test_resume_sends_sigcont(self) -> None:
        """
        Ensures resume() wakes a paused ffmpeg process via SIGCONT.
        """

        recorder, mock_process = self._make_recorder_with_mock_process()
        with patch("os.kill"):
            recorder.pause()
        with patch("os.kill") as mock_kill:
            recorder.resume()
            mock_kill.assert_called_once_with(mock_process.pid, signal.SIGCONT)
        self.assertEqual(recorder.state, RecordingState.RECORDING)

    def test_stop_while_paused_resumes_before_sigint(self) -> None:
        """
        Ensures stop() sends SIGCONT before SIGINT when the recording is paused,
        since a stopped process holds pending signals until continued.
        """

        recorder, mock_process = self._make_recorder_with_mock_process()
        with patch("os.kill"):
            recorder.pause()

        with patch("os.kill") as mock_kill:
            recorder.stop()
            mock_kill.assert_called_once_with(mock_process.pid, signal.SIGCONT)
        mock_process.send_signal.assert_called_once_with(signal.SIGINT)
        self.assertEqual(recorder.state, RecordingState.IDLE)

    def test_stop_while_recording_sends_only_sigint(self) -> None:
        """
        Ensures stop() does not send SIGCONT when the process was never paused.
        """

        recorder, mock_process = self._make_recorder_with_mock_process()
        with patch("os.kill") as mock_kill:
            recorder.stop()
            mock_kill.assert_not_called()
        mock_process.send_signal.assert_called_once_with(signal.SIGINT)

    def test_stop_emits_finished_with_output_path(self) -> None:
        """
        Ensures stop() emits `finished` with the output path once ffmpeg exits.
        """

        recorder, _mock_process = self._make_recorder_with_mock_process()
        received: list[str] = []
        recorder.finished.connect(received.append)
        with patch("os.kill"):
            recorder.stop()
        self.assertEqual(received, ["/tmp/rec.mp4"])

    def test_start_without_ffmpeg_emits_failed(self) -> None:
        """
        Ensures start() fails gracefully with a clear message when ffmpeg is missing.
        """

        recorder = VideoRecorder()
        messages: list[str] = []
        recorder.failed.connect(messages.append)
        with patch("src.video_recorder.has_ffmpeg", return_value=False):
            started = recorder.start(
                QRect(0, 0, 640, 480), Path("/tmp/rec.mp4"), record_microphone=False
            )
        self.assertFalse(started)
        self.assertEqual(len(messages), 1)
        self.assertIn("ffmpeg", messages[0])


if __name__ == "__main__":
    unittest.main()
