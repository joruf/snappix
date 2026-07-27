"""
Shared JSON clipboard payload encode/decode helpers for Snappix MIME formats.
"""

from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import QMimeData


def set_json_clipboard_data(mime_data: QMimeData, mime_type: str, payload: dict[str, Any]) -> None:
    """
    Encodes one JSON payload and attaches it to a QMimeData object.

    Args:
        mime_data: Target clipboard MIME container to mutate.
        mime_type: MIME type identifier for the payload.
        payload: JSON-serializable payload.

    Returns:
        None
    """

    encoded = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    mime_data.setData(mime_type, encoded)


def get_json_clipboard_data(mime_data: QMimeData | None, mime_type: str) -> dict[str, Any] | None:
    """
    Decodes one JSON payload from a QMimeData object.

    Args:
        mime_data: Clipboard MIME container, or None.
        mime_type: MIME type identifier to read.

    Returns:
        dict[str, Any] | None: Decoded payload, or None when absent/invalid.
    """

    if mime_data is None or not mime_data.hasFormat(mime_type):
        return None
    raw_data = bytes(mime_data.data(mime_type))
    try:
        payload = json.loads(raw_data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None
