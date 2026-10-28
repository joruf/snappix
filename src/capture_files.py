"""
Capture files that back an editor tab.

Every screenshot and recording that opens as a tab is written to the capture
folder at once, so a crash or a lost tab never costs the picture. Snappix keeps
a small index of the files it created itself, in a hidden file inside that
folder. The index is what separates them from everything else lying there:

* only indexed files are brought back as tabs when a tab got lost,
* only indexed files are ever deleted, so a path that ended up in the wrong
  place can never take somebody's own file with it.

The module has no Qt dependency; every failure is swallowed, because the index
is a safety net and must never be the reason a capture is lost.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

#: Name of the index inside the capture folder.
INDEX_FILE_NAME = ".snappix-captures.json"

KIND_IMAGE = "image"
KIND_VIDEO = "video"

_INDEX_VERSION = 1


@dataclass(slots=True)
class CaptureEntry:
    """
    One indexed capture file.

    Attributes:
        path: Absolute path of the capture file.
        kind: ``image`` or ``video``.
        recovery_path: Recovery project of the tab that showed it, which holds
            the annotations; empty when unknown.
    """

    path: Path
    kind: str = KIND_IMAGE
    recovery_path: str = ""


def index_path(directory: Path) -> Path:
    """
    Returns where the index of one capture folder lives.

    Args:
        directory: Capture folder.

    Returns:
        Path: The hidden index file.
    """

    return Path(directory) / INDEX_FILE_NAME


def _read_rows(directory: Path) -> list[dict[str, str]]:
    """
    Reads the raw index rows of one folder.

    Args:
        directory: Capture folder.

    Returns:
        list[dict[str, str]]: Rows with ``name``, ``kind`` and ``recovery``;
        empty when the index is missing or damaged.
    """

    try:
        payload = json.loads(index_path(directory).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    raw_rows = payload.get("files", []) if isinstance(payload, dict) else []
    if not isinstance(raw_rows, list):
        return []

    rows: list[dict[str, str]] = []
    for raw in raw_rows:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name", "")).strip()
        # A name is a plain file name: nothing here may point outside the folder.
        if not name or name != Path(name).name:
            continue
        rows.append(
            {
                "name": name,
                "kind": str(raw.get("kind", KIND_IMAGE)).strip() or KIND_IMAGE,
                "recovery": str(raw.get("recovery", "")).strip(),
            }
        )
    return rows


def _write_rows(directory: Path, rows: list[dict[str, str]]) -> bool:
    """
    Writes the index of one folder, replacing it in one step.

    Args:
        directory: Capture folder.
        rows: Rows to store.

    Returns:
        bool: True when the index was written.
    """

    target = index_path(directory)
    if not rows:
        # Nothing left to remember: do not leave an empty file behind.
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            return False
        return True
    temporary = target.with_name(f"{target.name}.tmp")
    payload = {"version": _INDEX_VERSION, "files": rows}
    try:
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(temporary, target)
    except OSError:
        try:
            temporary.unlink()
        except OSError:
            pass
        return False
    return True


def register_capture(path: str | Path, kind: str = KIND_IMAGE, recovery_path: str = "") -> bool:
    """
    Records a capture file as one Snappix created.

    Registering a file again updates its entry instead of adding a second one.

    Args:
        path: Capture file.
        kind: ``image`` or ``video``.
        recovery_path: Recovery project of the tab showing it.

    Returns:
        bool: True when the index was written.
    """

    file_path = Path(path)
    directory = file_path.parent
    if not directory.is_dir():
        return False
    row = {"name": file_path.name, "kind": kind, "recovery": str(recovery_path or "")}
    rows = [existing for existing in _read_rows(directory) if existing["name"] != file_path.name]
    rows.append(row)
    return _write_rows(directory, rows)


def unregister_capture(path: str | Path) -> bool:
    """
    Forgets a capture file without touching the file itself.

    The file stays where it is but is no longer brought back as a tab.

    Args:
        path: Capture file.

    Returns:
        bool: True when the file had an entry.
    """

    file_path = Path(path)
    directory = file_path.parent
    rows = _read_rows(directory)
    kept = [row for row in rows if row["name"] != file_path.name]
    if len(kept) == len(rows):
        return False
    _write_rows(directory, kept)
    return True


def is_registered(path: str | Path) -> bool:
    """
    Reports whether a file is one Snappix created as a capture.

    Args:
        path: File to check.

    Returns:
        bool: True when the folder's index lists it.
    """

    file_path = Path(path)
    return any(row["name"] == file_path.name for row in _read_rows(file_path.parent))


def delete_capture(path: str | Path) -> bool:
    """
    Deletes a capture file and its entry.

    Only an indexed file is deleted. Anything else is left alone, because a
    path that is not in the index was not made by a capture.

    Args:
        path: Capture file.

    Returns:
        bool: True when the file is gone afterwards.
    """

    file_path = Path(path)
    if not is_registered(file_path):
        return False
    try:
        file_path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        return False
    unregister_capture(file_path)
    return True


def registered_captures(directory: str | Path) -> list[CaptureEntry]:
    """
    Lists the indexed captures of one folder that still exist.

    Args:
        directory: Capture folder.

    Returns:
        list[CaptureEntry]: Entries in the order they were registered.
    """

    folder = Path(directory)
    entries: list[CaptureEntry] = []
    for row in _read_rows(folder):
        candidate = folder / row["name"]
        if candidate.is_file():
            entries.append(CaptureEntry(candidate, row["kind"], row["recovery"]))
    return entries
