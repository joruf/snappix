"""
Video project file storage for Snappix.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from src.constants import VIDEO_PROJECT_FILE_EXTENSION
from src.video_models import VideoProjectModel

_VIDEO_ASSET_ARCNAME = "assets/source.mp4"


def build_video_project_model(
    *,
    video_path: str | Path,
    video_width: int,
    video_height: int,
    duration_ms: int,
    framerate: float,
    annotation_models: list,
) -> VideoProjectModel:
    """
    Creates a serializable video project model from editor state.

    Args:
        video_path: Path to the source video file (referenced, not embedded, until save).
        video_width: Video width in pixels.
        video_height: Video height in pixels.
        duration_ms: Video duration in milliseconds.
        framerate: Video framerate in frames per second.
        annotation_models: Annotation list to persist.

    Returns:
        VideoProjectModel: Assembled project model.
    """

    from src.constants import VIDEO_PROJECT_FORMAT_NAME, VIDEO_PROJECT_FORMAT_VERSION

    return VideoProjectModel(
        format_name=VIDEO_PROJECT_FORMAT_NAME,
        format_version=VIDEO_PROJECT_FORMAT_VERSION,
        video_width=video_width,
        video_height=video_height,
        duration_ms=duration_ms,
        framerate=framerate,
        video_path_in_archive=_VIDEO_ASSET_ARCNAME,
        annotations=annotation_models,
        metadata={"source_video_path": str(video_path)},
    )


def save_video_project(path: str | Path, model: VideoProjectModel, source_video_path: str | Path) -> None:
    """
    Saves a video project model to disk as a ZIP container.

    Args:
        path: Output file path.
        model: Project model to persist.
        source_video_path: Path to the raw video file to embed as an asset.

    Returns:
        None
    """

    output_path = Path(path)
    if output_path.suffix.lower() != VIDEO_PROJECT_FILE_EXTENSION:
        output_path = output_path.with_suffix(VIDEO_PROJECT_FILE_EXTENSION)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    manifest = model.to_dict()
    manifest["video_path_in_archive"] = _VIDEO_ASSET_ARCNAME

    source_path = Path(source_video_path)
    if source_path.is_file():
        video_bytes = source_path.read_bytes()
    elif output_path.is_file():
        with zipfile.ZipFile(output_path, "r") as existing:
            video_bytes = existing.read(_VIDEO_ASSET_ARCNAME)
    else:
        raise OSError(f"Source video not found: {source_video_path}")

    with zipfile.ZipFile(output_path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        # H.264/AAC payload is already compressed; storing (not deflating) avoids
        # wasted CPU re-compressing incompressible bytes.
        archive.writestr(
            zipfile.ZipInfo(_VIDEO_ASSET_ARCNAME),
            video_bytes,
            compress_type=zipfile.ZIP_STORED,
        )


def load_video_project(path: str | Path, extract_dir: str | Path) -> tuple[VideoProjectModel, Path]:
    """
    Loads a video project model from a ZIP file, extracting the video asset to disk.

    Args:
        path: Project file path.
        extract_dir: Directory to extract the embedded video asset into. Qt Multimedia
            requires a real file on disk (or a QUrl), not in-memory bytes.

    Returns:
        tuple[VideoProjectModel, Path]: Parsed project model and extracted video file path.
    """

    source_path = Path(path)
    extract_root = Path(extract_dir)
    extract_root.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(source_path, "r") as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        asset_name = str(manifest.get("video_path_in_archive", _VIDEO_ASSET_ARCNAME))
        video_bytes = archive.read(asset_name)

    video_path = extract_root / f"{source_path.stem}.mp4"
    video_path.write_bytes(video_bytes)

    return VideoProjectModel.from_dict(manifest), video_path
