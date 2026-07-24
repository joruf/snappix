"""
Unit tests for video project ZIP storage.
"""

from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from src.constants import VIDEO_PROJECT_FILE_EXTENSION
from src.video_models import VideoAnnotationModel
from src.video_storage import build_video_project_model, load_video_project, save_video_project


class TestVideoStorage(unittest.TestCase):
    """
    Verifies save/load round-trip behavior for .sfpv video project archives.
    """

    def test_save_creates_stored_not_deflated_video_asset(self) -> None:
        """
        Ensures the embedded video asset uses ZIP_STORED to avoid wasted
        recompression of already-compressed H.264 bytes.
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            source_video = tmp_root / "source.mp4"
            source_video.write_bytes(b"fake-h264-bytes" * 100)

            model = build_video_project_model(
                video_path=source_video,
                video_width=640,
                video_height=480,
                duration_ms=5000,
                framerate=30.0,
                annotation_models=[],
            )
            output_path = tmp_root / "project.sfpv"
            save_video_project(output_path, model, source_video)

            self.assertTrue(output_path.exists())
            with zipfile.ZipFile(output_path) as archive:
                info = archive.getinfo("assets/source.mp4")
                self.assertEqual(info.compress_type, zipfile.ZIP_STORED)

    def test_save_enforces_file_extension(self) -> None:
        """
        Ensures saving without the .sfpv extension appends it automatically.
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            source_video = tmp_root / "source.mp4"
            source_video.write_bytes(b"fake-bytes")

            model = build_video_project_model(
                video_path=source_video,
                video_width=100,
                video_height=100,
                duration_ms=1000,
                framerate=30.0,
                annotation_models=[],
            )
            requested_path = tmp_root / "project.txt"
            save_video_project(requested_path, model, source_video)

            expected_path = requested_path.with_suffix(VIDEO_PROJECT_FILE_EXTENSION)
            self.assertTrue(expected_path.exists())
            self.assertFalse(requested_path.exists())

    def test_round_trip_preserves_annotations_and_extracts_video(self) -> None:
        """
        Ensures load_video_project restores the manifest and extracts a playable
        video file to disk (Qt Multimedia requires a real file path).
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            source_video = tmp_root / "source.mp4"
            video_bytes = b"fake-h264-bytes" * 50
            source_video.write_bytes(video_bytes)

            annotation = VideoAnnotationModel(
                annotation_type="rect",
                start_ms=0,
                end_ms=1000,
                x=1.0,
                y=2.0,
                width=10.0,
                height=20.0,
                stroke_rgba=[255, 0, 0, 255],
                fill_rgba=[255, 0, 0, 70],
                stroke_width=2.0,
            )
            model = build_video_project_model(
                video_path=source_video,
                video_width=320,
                video_height=240,
                duration_ms=1000,
                framerate=30.0,
                annotation_models=[annotation],
            )
            project_path = tmp_root / "project.sfpv"
            save_video_project(project_path, model, source_video)

            extract_dir = tmp_root / "extracted"
            restored_model, restored_video_path = load_video_project(project_path, extract_dir)

            self.assertEqual(restored_model.video_width, 320)
            self.assertEqual(restored_model.video_height, 240)
            self.assertEqual(len(restored_model.annotations), 1)
            self.assertEqual(restored_model.annotations[0].annotation_type, "rect")
            self.assertTrue(restored_video_path.exists())
            self.assertEqual(restored_video_path.read_bytes(), video_bytes)

    def test_save_reuses_existing_archive_video_when_source_missing(self) -> None:
        """
        Ensures updating one recovery project can keep the embedded video asset
        when the original source file was removed from disk.
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            source_video = tmp_root / "source.mp4"
            source_video.write_bytes(b"embedded-video-bytes")

            model = build_video_project_model(
                video_path=source_video,
                video_width=320,
                video_height=240,
                duration_ms=1000,
                framerate=30.0,
                annotation_models=[],
            )
            project_path = tmp_root / "project.sfpv"
            save_video_project(project_path, model, source_video)
            source_video.unlink()

            updated = build_video_project_model(
                video_path=source_video,
                video_width=320,
                video_height=240,
                duration_ms=2000,
                framerate=30.0,
                annotation_models=[],
            )
            save_video_project(project_path, updated, source_video)

            restored_model, restored_video_path = load_video_project(project_path, tmp_root / "extract")
            self.assertEqual(restored_model.duration_ms, 2000)
            self.assertEqual(restored_video_path.read_bytes(), b"embedded-video-bytes")


if __name__ == "__main__":
    unittest.main()
