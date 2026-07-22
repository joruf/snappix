"""
Data models for Snappix projects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.constants import PROJECT_FORMAT_NAME, PROJECT_FORMAT_VERSION


@dataclass(slots=True)
class AnnotationModel:
    """
    Defines a single drawable annotation object.

    Attributes:
        annotation_type: Logical tool type (text, rect, ellipse, arrow, line, image).
        x: Left position in image coordinates.
        y: Top position in image coordinates.
        width: Width in image coordinates.
        height: Height in image coordinates.
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
    x: float
    y: float
    width: float
    height: float
    stroke_rgba: list[int]
    fill_rgba: list[int]
    stroke_width: float
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
            "annotation_type": self.annotation_type,
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
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AnnotationModel":
        """
        Creates an annotation model from a serialized dictionary.

        Args:
            data: Serialized annotation dictionary.

        Returns:
            AnnotationModel: Restored annotation model.
        """

        return cls(
            annotation_type=str(data.get("annotation_type", "rect")),
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
class ProjectModel:
    """
    Defines the persisted Snappix project document.

    Attributes:
        format_name: Static format identifier for validation.
        format_version: Integer format version for migration handling.
        canvas_width: Screenshot width in pixels.
        canvas_height: Screenshot height in pixels.
        screenshot_png_base64: Screenshot image bytes (PNG) encoded as Base64.
        annotations: List of persisted annotations.
        metadata: Optional extensible metadata object.
    """

    format_name: str
    format_version: int
    canvas_width: int
    canvas_height: int
    screenshot_png_base64: str
    annotations: list[AnnotationModel] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """
        Serializes the project model to a JSON-compatible dictionary.

        Returns:
            dict[str, Any]: Full project payload.
        """

        return {
            "format_name": self.format_name,
            "format_version": self.format_version,
            "canvas_width": self.canvas_width,
            "canvas_height": self.canvas_height,
            "screenshot_png_base64": self.screenshot_png_base64,
            "annotations": [annotation.to_dict() for annotation in self.annotations],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectModel":
        """
        Creates a project model from serialized JSON data.

        Args:
            data: Serialized project dictionary.

        Returns:
            ProjectModel: Restored project model.
        """

        annotations = [
            AnnotationModel.from_dict(item)
            for item in list(data.get("annotations", []))
            if isinstance(item, dict)
        ]
        return cls(
            format_name=str(data.get("format_name", PROJECT_FORMAT_NAME)),
            format_version=int(data.get("format_version", PROJECT_FORMAT_VERSION)),
            canvas_width=int(data.get("canvas_width", 0)),
            canvas_height=int(data.get("canvas_height", 0)),
            screenshot_png_base64=str(data.get("screenshot_png_base64", "")),
            annotations=annotations,
            metadata=dict(data.get("metadata", {})),
        )

