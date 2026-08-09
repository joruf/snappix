"""
Handing the finished image to other applications as a file.

Pasting a screenshot works everywhere that accepts image data, but a lot of
targets want a *file*: a file manager, an e-mail attachment, an upload field.
Those read ``text/uri-list``, which the clipboard payload did not carry. The same
payload also powers a drag source, so the image can be dragged straight into
another window.

The PNG is written into a per-session temporary directory. Dropping and pasting
are asynchronous -- the receiving application may read the file well after the
drop -- so the file has to outlive the operation and is cleaned up when Snappix
exits instead.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from PySide6.QtCore import QMimeData, QPoint, QUrl, Qt
from PySide6.QtGui import QDrag, QPixmap
from PySide6.QtWidgets import QToolButton, QWidget

_SESSION_DIR: Path | None = None

# Thumbnail edge length for the image shown under the cursor while dragging.
DRAG_PREVIEW_SIZE = 96


def session_export_dir() -> Path:
    """
    Returns the per-session directory holding dragged/copied image files.

    Returns:
        Path: Existing temporary directory.
    """

    global _SESSION_DIR

    if _SESSION_DIR is None or not _SESSION_DIR.exists():
        _SESSION_DIR = Path(tempfile.mkdtemp(prefix="snappix-share-"))
    return _SESSION_DIR


def cleanup_session_export_dir() -> None:
    """
    Removes the session directory and every file handed out from it.

    Returns:
        None
    """

    global _SESSION_DIR

    if _SESSION_DIR is not None:
        shutil.rmtree(_SESSION_DIR, ignore_errors=True)
    _SESSION_DIR = None


def write_shareable_png(pixmap: QPixmap, file_name: str) -> Path | None:
    """
    Writes one image into the session directory for sharing.

    Args:
        pixmap: Image to write.
        file_name: Preferred file name; sanitized and forced to ``.png``.

    Returns:
        Path | None: Written file path, or None when saving failed.
    """

    if pixmap.isNull():
        return None
    stem = "".join(
        character if character.isalnum() or character in "-_ " else "_"
        for character in Path(file_name).stem
    ).strip() or "snappix"
    target = session_export_dir() / f"{stem}.png"
    counter = 2
    while target.exists():
        target = session_export_dir() / f"{stem}-{counter}.png"
        counter += 1
    if not pixmap.save(str(target), "PNG"):
        return None
    return target


def attach_image_file(mime_data: QMimeData, pixmap: QPixmap, file_name: str) -> Path | None:
    """
    Adds a file reference for one image to an existing clipboard payload.

    Args:
        mime_data: Payload to extend; existing formats are kept.
        pixmap: Image to offer as a file.
        file_name: Preferred file name.

    Returns:
        Path | None: Written file path, or None when it could not be created.
    """

    path = write_shareable_png(pixmap, file_name)
    if path is None:
        return None
    mime_data.setUrls([QUrl.fromLocalFile(str(path))])
    return path


class ImageDragButton(QToolButton):
    """
    Button that starts a drag carrying the current image as a file.

    A dedicated drag source keeps the canvas free: dragging there already draws,
    moves, and resizes annotations, so there is no spare gesture to overload.
    """

    def __init__(self, provider, parent: QWidget | None = None) -> None:
        """
        Initializes the drag source.

        Args:
            provider: Callable returning ``(QPixmap, file_name)`` when a drag
                starts. Returning a null pixmap cancels the drag.
            parent: Optional parent widget.
        """

        super().__init__(parent)
        self._provider = provider
        self._press_pos = QPoint()
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mousePressEvent(self, event) -> None:
        """
        Records the press position so a drag can be told from a click.

        Args:
            event: Mouse press event.

        Returns:
            None
        """

        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        """
        Starts the drag once the pointer has moved far enough.

        Args:
            event: Mouse move event.

        Returns:
            None
        """

        if not (event.buttons() & Qt.MouseButton.LeftButton):
            super().mouseMoveEvent(event)
            return
        moved = (event.position().toPoint() - self._press_pos).manhattanLength()
        if moved < self.style().pixelMetric(self.style().PixelMetric.PM_DefaultFrameWidth) + 8:
            super().mouseMoveEvent(event)
            return
        self.start_drag()

    def start_drag(self) -> bool:
        """
        Builds the payload and runs the drag.

        Returns:
            bool: True when a drag was started.
        """

        pixmap, file_name = self._provider()
        if pixmap is None or pixmap.isNull():
            return False
        mime_data = QMimeData()
        mime_data.setImageData(pixmap.toImage())
        if attach_image_file(mime_data, pixmap, file_name) is None:
            return False
        drag = QDrag(self)
        drag.setMimeData(mime_data)
        drag.setPixmap(
            pixmap.scaled(
                DRAG_PREVIEW_SIZE,
                DRAG_PREVIEW_SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        drag.exec(Qt.DropAction.CopyAction)
        return True
