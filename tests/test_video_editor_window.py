"""
Unit tests for the video editor's export compositing pipeline.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

try:
    from src.video_editor_window import VideoEditorWindow
    from src.video_models import VideoAnnotationModel
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for video editor tests")
class TestVideoEditorExport(unittest.TestCase):
    """
    Verifies the MP4 export pipeline builds correctly timed overlay segments.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for widget/media-player creation.
        """

        ensure_qapp()

    def test_run_export_builds_one_segment_per_visibility_change(self) -> None:
        """
        Ensures each contiguous time range with a distinct visible-annotation set
        produces exactly one overlay segment, and the ffmpeg export command runs.
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            source_video = tmp_root / "source.mp4"
            source_video.write_bytes(b"not-a-real-video")

            editor = VideoEditorWindow(str(source_video), 320, 240)
            # Real video metadata is unavailable for a fake file; force a known
            # duration so segment boundaries are deterministic for the test.
            editor.canvas.duration_ms = MagicMock(return_value=5000)

            first = VideoAnnotationModel(
                annotation_type="rect",
                start_ms=0,
                end_ms=2000,
                x=0.0,
                y=0.0,
                width=10.0,
                height=10.0,
                stroke_rgba=[255, 0, 0, 255],
                fill_rgba=[255, 0, 0, 70],
                stroke_width=2.0,
            )
            second = VideoAnnotationModel(
                annotation_type="text",
                start_ms=2000,
                end_ms=5000,
                x=5.0,
                y=5.0,
                width=0.0,
                height=0.0,
                stroke_rgba=[0, 255, 0, 255],
                fill_rgba=[0, 255, 0, 0],
                stroke_width=1.0,
                text="hello",
            )
            editor._annotations.append(first)
            editor._annotations.append(second)

            fake_result = MagicMock()
            fake_result.returncode = 0
            output_path = tmp_root / "out.mp4"

            with patch(
                "src.video_editor_window.build_export_command",
                return_value=["ffmpeg", "-y"],
            ) as mock_build_command, patch(
                "subprocess.run", return_value=fake_result
            ) as mock_run:
                editor._run_export(output_path, include_audio=True)

            self.assertEqual(mock_run.call_count, 1)
            self.assertTrue(mock_build_command.call_args.kwargs.get("include_audio", True))
            segments = mock_build_command.call_args[0][1]
            self.assertEqual(len(segments), 2)
            self.assertEqual((segments[0].start_s, segments[0].end_s), (0.0, 2.0))
            self.assertEqual((segments[1].start_s, segments[1].end_s), (2.0, 5.0))

    def test_run_export_can_request_silent_output(self) -> None:
        """
        Ensures include_audio=False is forwarded to build_export_command.
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            source_video = tmp_root / "source.mp4"
            source_video.write_bytes(b"not-a-real-video")

            editor = VideoEditorWindow(str(source_video), 320, 240)
            editor.canvas.duration_ms = MagicMock(return_value=1000)

            fake_result = MagicMock()
            fake_result.returncode = 0

            with patch(
                "src.video_editor_window.build_export_command",
                return_value=["ffmpeg", "-y"],
            ) as mock_build_command, patch(
                "subprocess.run", return_value=fake_result
            ):
                editor._run_export(tmp_root / "out.mp4", include_audio=False)

            self.assertFalse(mock_build_command.call_args.kwargs.get("include_audio"))

    def test_playback_sound_defaults_to_muted(self) -> None:
        """
        Ensures the video editor starts with playback sound off.
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            source_video = Path(tmp_dir) / "source.mp4"
            source_video.write_bytes(b"not-a-real-video")
            editor = VideoEditorWindow(str(source_video), 320, 240)
            self.assertTrue(editor.canvas.is_audio_muted())
            self.assertFalse(editor.sound_action.isChecked())
            editor.sound_action.setChecked(True)
            self.assertFalse(editor.canvas.is_audio_muted())
            self.assertEqual(editor.sound_action.text(), "Sound: On")

    def test_run_export_raises_on_ffmpeg_failure(self) -> None:
        """
        Ensures a non-zero ffmpeg exit code raises with stderr detail.
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            source_video = tmp_root / "source.mp4"
            source_video.write_bytes(b"not-a-real-video")

            editor = VideoEditorWindow(str(source_video), 320, 240)
            editor.canvas.duration_ms = MagicMock(return_value=1000)

            fake_result = MagicMock()
            fake_result.returncode = 1
            fake_result.stderr = "ffmpeg exploded"

            with patch(
                "src.video_editor_window.build_export_command",
                return_value=["ffmpeg", "-y"],
            ), patch("subprocess.run", return_value=fake_result):
                with self.assertRaises(RuntimeError):
                    editor._run_export(tmp_root / "out.mp4")


if __name__ == "__main__":
    unittest.main()
