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

from src.constants import APP_FILE_EXTENSION, VIDEO_PROJECT_FILE_EXTENSION

_WORKSPACE_ROOT: Path | None = None


@dataclass(slots=True)
class EditorSessionTab:
    """
    Describes one recoverable editor tab in a saved session.

    Attributes:
        title: Tab title shown in the editor host.
        recovery_path: Auto-save project file for the tab.
        source_path: Optional user project path when the tab was saved before.
        kind: Tab content type, ``image`` or ``video``.
    """

    title: str
    recovery_path: str
    source_path: str = ""
    kind: str = "image"


def reset_workspace_root() -> None:
    """
    Clears the cached workspace root so the next lookup uses defaults again.

    Returns:
        None
    """

    global _WORKSPACE_ROOT
    _WORKSPACE_ROOT = None


def set_workspace_root(path: str | Path) -> Path:
    """
    Sets the workspace directory used for unsaved editor session data.

    Args:
        path: Workspace root directory.

    Returns:
        Path: Resolved workspace root.
    """

    global _WORKSPACE_ROOT
    resolved = Path(path).expanduser()
    try:
        resolved = resolved.resolve()
    except OSError:
        resolved = Path(path).expanduser()
    _WORKSPACE_ROOT = resolved
    _migrate_legacy_workspace_if_needed()
    return resolved


def workspace_root() -> Path:
    """
    Returns the active workspace directory.

    Returns:
        Path: Workspace root, defaulting to ``~/.snappix``.
    """

    if _WORKSPACE_ROOT is not None:
        return _WORKSPACE_ROOT
    from src.config import default_workspace_directory

    return set_workspace_root(default_workspace_directory())


def _session_root_dir() -> Path:
    """
    Returns the directory used for multi-tab recovery snapshots.

    Returns:
        Path: Session recovery directory.
    """

    return workspace_root()


def tabs_dir() -> Path:
    """
    Returns the directory used for per-tab recovery project files.

    Returns:
        Path: Writable tabs directory inside the workspace.
    """

    path = _session_root_dir() / "tabs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def session_video_sources_dir() -> Path:
    """
    Returns the directory used for stable video source copies during recovery.

    Returns:
        Path: Writable directory for session video sources.
    """

    path = _session_root_dir() / "video-sources"
    path.mkdir(parents=True, exist_ok=True)
    return path


def video_assets_dir() -> Path:
    """
    Returns the directory used for extracted video assets during restore.

    Returns:
        Path: Writable directory for extracted session videos.
    """

    path = _session_root_dir() / "video-assets"
    path.mkdir(parents=True, exist_ok=True)
    return path


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

    legacy_in_workspace = _session_root_dir() / f"legacy-autosave{APP_FILE_EXTENSION}"
    if legacy_in_workspace.is_file():
        return legacy_in_workspace
    return Path(tempfile.gettempdir()) / f"snappix-autosave{APP_FILE_EXTENSION}"


def create_tab_recovery_path() -> str:
    """
    Allocates one unique recovery project path for a new editor tab.

    Returns:
        str: Writable recovery project file path.
    """

    return str(tabs_dir() / f"tab-{uuid4().hex}{APP_FILE_EXTENSION}")


def create_video_tab_recovery_path() -> str:
    """
    Allocates one unique recovery project path for a new video editor tab.

    Returns:
        str: Writable recovery video project file path.
    """

    return str(tabs_dir() / f"tab-{uuid4().hex}{VIDEO_PROJECT_FILE_EXTENSION}")


def tab_kind_from_recovery_path(recovery_path: str) -> str:
    """
    Infers the editor tab kind from one recovery file path.

    Args:
        recovery_path: Recovery project file path.

    Returns:
        str: ``video`` for ``.sfpv`` files, otherwise ``image``.
    """

    if recovery_path.strip().lower().endswith(VIDEO_PROJECT_FILE_EXTENSION):
        return "video"
    return "image"


def _recovery_path_is_managed(existing_path: str) -> bool:
    """
    Indicates whether one recovery path lives inside the active workspace.

    Args:
        existing_path: Recovery project file path.

    Returns:
        bool: True when the path belongs to the current workspace layout.
    """

    if not existing_path.strip():
        return False
    target = Path(existing_path).expanduser()
    try:
        target = target.resolve()
    except OSError:
        target = Path(existing_path).expanduser()
    root = _session_root_dir()
    tabs_root = tabs_dir()
    try:
        if target.is_relative_to(tabs_root):
            return True
    except ValueError:
        pass
    try:
        return target.is_relative_to(root)
    except ValueError:
        return False


def ensure_tab_recovery_path(existing_path: str) -> str:
    """
    Ensures one tab recovery path remains writable.

    Reuses the existing path when possible and allocates a new path when the
    workspace directory changed or the file was removed.

    Args:
        existing_path: Current recovery project path for one editor tab.

    Returns:
        str: Writable recovery project path.
    """

    normalized = existing_path.strip()
    if not normalized:
        return create_tab_recovery_path()

    target = Path(normalized)
    suffix = target.suffix.lower()
    recreate = create_video_tab_recovery_path if suffix == VIDEO_PROJECT_FILE_EXTENSION else create_tab_recovery_path
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return recreate()

    if not _recovery_path_is_managed(normalized):
        return recreate()
    return str(target)


def delete_tab_recovery_data(recovery_path: str) -> None:
    """
    Removes one tab's workspace recovery files.

    Args:
        recovery_path: Recovery project file path for the closed tab.

    Returns:
        None
    """

    normalized = recovery_path.strip()
    if not normalized:
        return

    project_path = Path(normalized).expanduser()
    stem = project_path.stem
    try:
        if project_path.is_file() or project_path.is_symlink():
            project_path.unlink()
    except OSError:
        pass

    video_source = session_video_sources_dir() / f"{stem}.mp4"
    try:
        if video_source.is_file() or video_source.is_symlink():
            video_source.unlink()
    except OSError:
        pass

    extract_dir = video_assets_dir() / stem
    try:
        if extract_dir.exists():
            shutil.rmtree(extract_dir, ignore_errors=True)
    except OSError:
        pass


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
                "kind": tab.kind,
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
                kind=str(entry.get("kind", tab_kind_from_recovery_path(recovery_path))).strip()
                or tab_kind_from_recovery_path(recovery_path),
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

    manifest = session_manifest_path()
    try:
        if manifest.is_file():
            manifest.unlink()
    except OSError:
        pass

    for directory in (tabs_dir(), session_video_sources_dir(), video_assets_dir()):
        try:
            if directory.exists():
                shutil.rmtree(directory, ignore_errors=True)
        except OSError:
            pass

    for legacy_candidate in (
        _session_root_dir() / f"legacy-autosave{APP_FILE_EXTENSION}",
        Path(tempfile.gettempdir()) / f"snappix-autosave{APP_FILE_EXTENSION}",
    ):
        try:
            if legacy_candidate.is_file():
                legacy_candidate.unlink()
        except OSError:
            pass


def _migrate_legacy_workspace_if_needed() -> None:
    """
    Moves editor session data from the old temporary directory into the workspace.

    Returns:
        None
    """

    if session_manifest_path().is_file():
        return

    legacy_dir = Path(tempfile.gettempdir()) / "snappix-session"
    if not legacy_dir.is_dir():
        return

    root = _session_root_dir()
    root.mkdir(parents=True, exist_ok=True)
    for item in legacy_dir.iterdir():
        target = root / item.name
        if target.exists():
            continue
        try:
            shutil.move(str(item), str(target))
        except OSError:
            continue
    try:
        legacy_dir.rmdir()
    except OSError:
        pass
