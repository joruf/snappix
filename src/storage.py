"""
Project file storage for Snappix.
"""

from __future__ import annotations

import base64
import json
import zipfile
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QByteArray, QBuffer, QIODevice
from PySide6.QtGui import QImage, QPixmap

from src.constants import APP_FILE_EXTENSION, PROJECT_FORMAT_NAME, PROJECT_FORMAT_VERSION
from src.models import AnnotationModel, ProjectModel


def pixmap_to_base64_png(pixmap: QPixmap) -> str:
    """
    Encodes a pixmap as Base64 PNG data.

    Args:
        pixmap: Source pixmap.

    Returns:
        str: Base64 encoded PNG bytes.
    """

    byte_array = QByteArray()
    buffer = QBuffer(byte_array)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    return bytes(byte_array.toBase64()).decode("utf-8")


def base64_png_to_pixmap(value: str) -> QPixmap:
    """
    Decodes Base64 PNG data to a pixmap.

    Args:
        value: Base64 encoded PNG bytes.

    Returns:
        QPixmap: Decoded pixmap.
    """

    raw = base64.b64decode(value.encode("utf-8"))
    image = QImage()
    image.loadFromData(raw, "PNG")
    return QPixmap.fromImage(image)


def build_project_model(
    screenshot: QPixmap,
    annotation_models: list[AnnotationModel],
) -> ProjectModel:
    """
    Creates a serializable project model from editor state.

    Args:
        screenshot: Screenshot pixmap used as document background.
        annotation_models: Annotation list to persist.

    Returns:
        ProjectModel: Assembled project model.
    """

    return ProjectModel(
        format_name=PROJECT_FORMAT_NAME,
        format_version=PROJECT_FORMAT_VERSION,
        canvas_width=screenshot.width(),
        canvas_height=screenshot.height(),
        screenshot_png_base64=pixmap_to_base64_png(screenshot),
        annotations=annotation_models,
        metadata={},
    )


def save_project(path: str | Path, model: ProjectModel) -> None:
    """
    Saves a project model to disk as ZIP container.

    Args:
        path: Output file path.
        model: Project model to persist.

    Returns:
        None
    """

    output_path = Path(path)
    if output_path.suffix.lower() != APP_FILE_EXTENSION:
        output_path = output_path.with_suffix(APP_FILE_EXTENSION)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    manifest = model.to_dict()
    screenshot_data = base64.b64decode(model.screenshot_png_base64.encode("utf-8"))
    manifest["screenshot_png_base64"] = ""
    manifest["screenshot_path"] = "assets/screenshot.png"

    assets: dict[str, bytes] = {"assets/screenshot.png": screenshot_data}
    for annotation in manifest.get("annotations", []):
        if not isinstance(annotation, dict):
            continue
        payload = annotation.get("payload", {})
        if not isinstance(payload, dict):
            continue
        image_base64 = payload.get("image_png_base64")
        if not image_base64:
            continue
        asset_name = f"assets/image-{uuid4().hex}.png"
        assets[asset_name] = base64.b64decode(str(image_base64).encode("utf-8"))
        payload["image_png_base64"] = ""
        payload["image_asset_path"] = asset_name

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        for asset_path, asset_bytes in assets.items():
            archive.writestr(asset_path, asset_bytes)


def load_project(path: str | Path) -> ProjectModel:
    """
    Loads a project model from JSON or ZIP file.

    Args:
        path: Project file path.

    Returns:
        ProjectModel: Parsed project model.
    """

    source_path = Path(path)
    if source_path.suffix.lower() == ".json" or source_path.suffix.lower() == ".lshot":
        data = json.loads(source_path.read_text(encoding="utf-8"))
        return ProjectModel.from_dict(data)

    with zipfile.ZipFile(source_path, "r") as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        screenshot_path = str(manifest.get("screenshot_path", "assets/screenshot.png"))
        screenshot_data = archive.read(screenshot_path)
        manifest["screenshot_png_base64"] = base64.b64encode(screenshot_data).decode("utf-8")

        for annotation in manifest.get("annotations", []):
            if not isinstance(annotation, dict):
                continue
            payload = annotation.get("payload", {})
            if not isinstance(payload, dict):
                continue
            image_asset_path = payload.get("image_asset_path")
            if not image_asset_path:
                continue
            image_data = archive.read(str(image_asset_path))
            payload["image_png_base64"] = base64.b64encode(image_data).decode("utf-8")
            payload.pop("image_asset_path", None)

    return ProjectModel.from_dict(manifest)

