"""
Multi-tab editor session recovery helpers.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from src.constants import APP_FILE_EXTENSION


@dataclass(slots=True)
class EditorSessionTab:
    """
    Describes one recoverable editor tab in a saved session.

    Attributes:
        title: Tab title shown in the editor host.
        recovery_path: Auto-save project file for the tab.
        source_path: Optional user project path when the tab was saved before.
    """

    title: str
    recovery_path: str
    source_path: str = ""


def _session_root_dir() -> Path:
    """
    Returns the directory used for multi-tab recovery snapshots.

    Returns:
        Path: Session recovery directory.
    """

    return Path(tempfile.gettempdir()) / "snappix-session"


def session_manifest_path() -> Path:
    """
    Returns the path of the editor session manifest file.

    Returns:
        Path: Manifest JSON path.
    """

    return _session_root_dir() / "session.json"


def legacy_recovery_snapshot_path() -> Path:
    """
    Returns the legacy single-tab auto-recovery project path.

    Returns:
        Path: Legacy recovery snapshot path.
    """

    return Path(tempfile.gettempdir()) / f"snappix-autosave{APP_FILE_EXTENSION}"


def create_tab_recovery_path() -> str:
    """
    Allocates one unique recovery project path for a new editor tab.

    Returns:
        str: Writable recovery project file path.
    """

    session_dir = _session_root_dir()
    session_dir.mkdir(parents=True, exist_ok=True)
    return str(session_dir / f"tab-{uuid4().hex}{APP_FILE_EXTENSION}")


def ensure_tab_recovery_path(existing_path: str) -> str:
    """
    Ensures one tab recovery path remains writable.

    Reuses the existing path when possible and allocates a new path when the
    session directory was removed from the temporary folder.

    Args:
        existing_path: Current recovery project path for one editor tab.

    Returns:
        str: Writable recovery project path.
    """

    normalized = existing_path.strip()
    if not normalized:
        return create_tab_recovery_path()

    target = Path(normalized)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return create_tab_recovery_path()

    if target.parent != _session_root_dir():
        return create_tab_recovery_path()
    return str(target)


def has_editor_session() -> bool:
    """
    Indicates whether a recoverable multi-tab editor session exists.

    Returns:
        bool: True when a non-empty session manifest is available.
    """

    manifest_path = session_manifest_path()
    try:
        return manifest_path.is_file() and manifest_path.stat().st_size > 0
    except OSError:
        return False


def has_legacy_recovery_snapshot() -> bool:
    """
    Indicates whether the legacy single-tab recovery snapshot exists.

    Returns:
        bool: True when the legacy snapshot file is present.
    """

    path = legacy_recovery_snapshot_path()
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def has_recovery_data() -> bool:
    """
    Indicates whether any editor recovery data exists.

    Returns:
        bool: True when either session or legacy recovery data exists.
    """

    return has_editor_session() or has_legacy_recovery_snapshot()


def save_editor_session(tabs: list[EditorSessionTab]) -> None:
    """
    Persists the current editor tab session to disk.

    Args:
        tabs: Open editor tabs to recover on next launch.

    Returns:
        None
    """

    if not tabs:
        return

    session_dir = _session_root_dir()
    session_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "tabs": [
            {
                "title": tab.title,
                "recovery_path": tab.recovery_path,
                "source_path": tab.source_path,
            }
            for tab in tabs
            if tab.recovery_path.strip()
        ],
    }
    session_manifest_path().write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_editor_session() -> list[EditorSessionTab]:
    """
    Loads a previously saved editor tab session.

    Returns:
        list[EditorSessionTab]: Recoverable tabs, or an empty list.
    """

    manifest_path = session_manifest_path()
    if not manifest_path.is_file():
        return []

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    tabs: list[EditorSessionTab] = []
    raw_tabs = payload.get("tabs", [])
    if not isinstance(raw_tabs, list):
        return []

    for entry in raw_tabs:
        if not isinstance(entry, dict):
            continue
        recovery_path = str(entry.get("recovery_path", "")).strip()
        if not recovery_path or not os.path.isfile(recovery_path):
            continue
        try:
            if os.path.getsize(recovery_path) <= 0:
                continue
        except OSError:
            continue
        tabs.append(
            EditorSessionTab(
                title=str(entry.get("title", "Recovered Session")).strip() or "Recovered Session",
                recovery_path=recovery_path,
                source_path=str(entry.get("source_path", "")).strip(),
            )
        )
    return tabs


def load_legacy_recovery_tab() -> EditorSessionTab | None:
    """
    Loads the legacy single-tab recovery snapshot as one session tab.

    Returns:
        EditorSessionTab | None: Legacy tab entry or None.
    """

    legacy_path = legacy_recovery_snapshot_path()
    if not legacy_path.is_file():
        return None
    try:
        if legacy_path.stat().st_size <= 0:
            return None
    except OSError:
        return None
    return EditorSessionTab(
        title="Recovered Session",
        recovery_path=str(legacy_path),
        source_path="",
    )


def clear_editor_session() -> None:
    """
    Removes the saved editor session manifest and tab recovery files.

    Returns:
        None
    """

    session_dir = _session_root_dir()
    try:
        if session_dir.exists():
            shutil.rmtree(session_dir, ignore_errors=True)
    except OSError:
        pass

    legacy_path = legacy_recovery_snapshot_path()
    try:
        if legacy_path.exists():
            legacy_path.unlink()
    except OSError:
        pass
