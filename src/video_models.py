"""
Data models for Snappix video projects.
"""

from __future__ import annotations

from src.py_compat import dataclass, field
from typing import Any
from uuid import uuid4

from src.constants import VIDEO_PROJECT_FORMAT_NAME, VIDEO_PROJECT_FORMAT_VERSION


@dataclass(slots=True)
class VideoAnnotationModel:
    """
    Defines a single drawable, time-ranged video annotation object.

    Attributes:
        annotation_id: Stable identifier used to track this annotation across
            the video canvas and timeline widget.
        annotation_type: Logical tool type (rect, ellipse, line, arrow, text).
        start_ms: Timeline position (milliseconds) where the annotation appears.
        end_ms: Timeline position (milliseconds) where the annotation disappears.
        x: Left position in video-pixel coordinates.
        y: Top position in video-pixel coordinates.
        width: Width in video-pixel coordinates.
        height: Height in video-pixel coordinates.
        stroke_rgba: Stroke color as [r, g, b, a].
        fill_rgba: Fill color as [r, g, b, a].
        stroke_width: Stroke thickness in pixels.
        text: Text content for text annotations.
        font_size: Font size in points for text annotations.
        font_family: Font family name for text annotations.
        font_bold: Bold state for text annotations.
        font_italic: Italic state for text annotations.
        font_underline: Underline state for text annotations.
        payload: Extra type-specific data for forward compatibility.
    """

    annotation_type: str
    start_ms: int
    end_ms: int
    x: float
    y: float
    width: float
    height: float
    stroke_rgba: list[int]
    fill_rgba: list[int]
    stroke_width: float
    annotation_id: str = field(default_factory=lambda: uuid4().hex)
    text: str = ""
    font_size: int = 16
    font_family: str = ""
    font_bold: bool = False
    font_italic: bool = False
    font_underline: bool = False
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """
        Serializes the annotation to a dictionary.

        Returns:
            dict[str, Any]: Annotation payload for JSON storage.
        """

        return {
            "annotation_id": self.annotation_id,
            "annotation_type": self.annotation_type,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "stroke_rgba": self.stroke_rgba,
            "fill_rgba": self.fill_rgba,
            "stroke_width": self.stroke_width,
            "text": self.text,
            "font_size": self.font_size,
            "font_family": self.font_family,
            "font_bold": self.font_bold,
            "font_italic": self.font_italic,
            "font_underline": self.font_underline,
            "payload": dict(self.payload),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VideoAnnotationModel":
        """
        Creates a video annotation model from a serialized dictionary.

        Args:
            data: Serialized annotation dictionary.

        Returns:
            VideoAnnotationModel: Restored annotation model.
        """

        return cls(
            annotation_id=str(data.get("annotation_id", "")) or uuid4().hex,
            annotation_type=str(data.get("annotation_type", "rect")),
            start_ms=int(data.get("start_ms", 0)),
            end_ms=int(data.get("end_ms", 0)),
            x=float(data.get("x", 0)),
            y=float(data.get("y", 0)),
            width=float(data.get("width", 0)),
            height=float(data.get("height", 0)),
            stroke_rgba=list(data.get("stroke_rgba", [255, 0, 0, 255])),
            fill_rgba=list(data.get("fill_rgba", [255, 0, 0, 70])),
            stroke_width=float(data.get("stroke_width", 2)),
            text=str(data.get("text", "")),
            font_size=int(data.get("font_size", 16)),
            font_family=str(data.get("font_family", "")),
            font_bold=bool(data.get("font_bold", False)),
            font_italic=bool(data.get("font_italic", False)),
            font_underline=bool(data.get("font_underline", False)),
            payload=dict(data.get("payload", {})),
        )


@dataclass(slots=True)
class VideoProjectModel:
    """
    Defines the persisted Snappix video project document.

    Attributes:
        format_name: Static format identifier for validation.
        format_version: Integer format version for migration handling.
        video_width: Recorded video width in pixels.
        video_height: Recorded video height in pixels.
        duration_ms: Video duration in milliseconds.
        framerate: Video framerate in frames per second.
        video_path_in_archive: Archive-relative path to the source video asset.
        annotations: List of persisted time-ranged annotations.
        metadata: Optional extensible metadata object.
    """

    format_name: str
    format_version: int
    video_width: int
    video_height: int
    duration_ms: int
    framerate: float
    video_path_in_archive: str
    annotations: list[VideoAnnotationModel] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """
        Serializes the video project model to a JSON-compatible dictionary.

        Returns:
            dict[str, Any]: Full project payload.
        """

        return {
            "format_name": self.format_name,
            "format_version": self.format_version,
            "video_width": self.video_width,
            "video_height": self.video_height,
            "duration_ms": self.duration_ms,
            "framerate": self.framerate,
            "video_path_in_archive": self.video_path_in_archive,
            "annotations": [annotation.to_dict() for annotation in self.annotations],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VideoProjectModel":
        """
        Creates a video project model from serialized JSON data.

        Args:
            data: Serialized project dictionary.

        Returns:
            VideoProjectModel: Restored project model.
        """

        annotations = [
            VideoAnnotationModel.from_dict(item)
            for item in list(data.get("annotations", []))
            if isinstance(item, dict)
        ]
        return cls(
            format_name=str(data.get("format_name", VIDEO_PROJECT_FORMAT_NAME)),
            format_version=int(data.get("format_version", VIDEO_PROJECT_FORMAT_VERSION)),
            video_width=int(data.get("video_width", 0)),
            video_height=int(data.get("video_height", 0)),
            duration_ms=int(data.get("duration_ms", 0)),
            framerate=float(data.get("framerate", 30.0)),
            video_path_in_archive=str(
                data.get("video_path_in_archive", "assets/source.mp4")
            ),
            annotations=annotations,
            metadata=dict(data.get("metadata", {})),
        )
