"""
Which version of Snappix is running here.

**Derived from the history, not maintained by hand.** Every commit is a new
version, so the number answers "which state is this?" without anyone having to
remember to raise it:

```
build  = number of commits
minor  = number of commits that added something
patch  = commits since the last one that added something
```

That makes ``0.37.8 (124)`` mean: the 124th commit, the 37th feature round,
eight changes since that round began. Major stays at zero until a release is
tagged. Alongside the number stand the short hash and the day of the newest
commit, so a number in a bug report leads back to an exact commit.

**One source, three routes to it.** A checkout has the history and reads it
directly. A package does not ship ``.git``, so the number travels in a
``VERSION`` file next to ``run.py`` -- derived from the same history, never
typed in:

```
SNAPPIX_VERSION (environment)  ->  for tests and for one-off runs
git history                    ->  started from the checkout
VERSION                        ->  shipped as a package
otherwise                      ->  "unknown", and it says so
```

**The file is written by a hook.** ``.githooks/post-commit`` runs
``src/version.py --write`` after every commit, and every read of the history
refreshes it as well. The file carries a marker of the history it was derived
from, so an unchanged checkout answers from the file without starting git. It
is not checked in: it is derived, and a checked-in copy would be stale one
commit later. Activate the hook once per checkout with
``git config core.hooksPath .githooks``; the installer does that itself.

There is deliberately no invented fallback such as ``0.0.0``: a made-up number
looks real and sends every bug report in the wrong direction.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

#: Shown when nothing can be determined.
UNKNOWN = "unknown"

#: Commits whose subject starts like this begin a new feature round.
FEATURE_SUBJECT = re.compile(r"^(add|implement|introduce|bring)\b", re.IGNORECASE)

ENVIRONMENT_VARIABLE = "SNAPPIX_VERSION"
VERSION_FILE_NAME = "VERSION"

#: Separates the parts of a commit's record in the ``git log`` output.
_FIELD = "\x1f"

_cached: tuple[str, str] | None = None
_cached_details: dict[str, str] | None = None


def project_root() -> Path:
    """
    Returns the directory holding ``run.py``.

    Returns:
        Path: Project root.
    """

    return Path(__file__).resolve().parent.parent


def _parse(text: str) -> dict[str, str] | None:
    """
    Reads a stored version: ``name build commit date marker``.

    Older files hold only name and build; the missing fields stay empty.

    Args:
        text: Stored text.

    Returns:
        dict[str, str] | None: The fields, or None for an empty text.
    """

    parts = text.split()
    if not parts:
        return None
    keys = ("name", "build", "commit", "date", "marker")
    return {key: parts[index] if index < len(parts) else "" for index, key in enumerate(keys)}


def _from_environment() -> dict[str, str] | None:
    """
    Reads an explicitly set version.

    Returns:
        dict[str, str] | None: The fields, or None when unset.
    """

    found = _parse(os.environ.get(ENVIRONMENT_VARIABLE, ""))
    if found is not None:
        found["marker"] = ""
    return found


def history_marker(root: Path) -> str:
    """
    Identifies the state of the history without starting a process.

    The reflog grows with every commit, checkout, amend and reset, so its size
    and modification time notice that the history moved on -- even for two
    commits within the same second. The index stands in only where the reflog
    is switched off; it is also rewritten by a plain ``git status``, which would
    cost a needless re-read on every start.

    Args:
        root: Directory holding ``.git``.

    Returns:
        str: The marker, empty when neither file exists.
    """

    for candidate in (root / ".git" / "logs" / "HEAD", root / ".git" / "index"):
        try:
            status = candidate.stat()
        except OSError:
            continue
        return f"{status.st_mtime_ns}.{status.st_size}"
    return ""


def _from_git(root: Path, marker: str = "") -> dict[str, str] | None:
    """
    Derives the version from the commit history.

    Args:
        root: Directory to read the history of.
        marker: History marker to store alongside.

    Returns:
        dict[str, str] | None: The fields, or None without a history.
    """

    environment = dict(os.environ)
    environment["LC_ALL"] = "C"
    try:
        result = subprocess.run(
            ["git", "log", "--reverse", f"--format=%s{_FIELD}%h{_FIELD}%cs"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5.0,
            check=True,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    records = [line.split(_FIELD) for line in result.stdout.splitlines() if line.strip()]
    if not records:
        return None

    minor = 0
    patch = 0
    for record in records:
        if FEATURE_SUBJECT.match(record[0]):
            minor += 1
            patch = 0
        else:
            patch += 1
    newest = records[-1] + ["", "", ""]
    return {
        "name": f"0.{minor}.{patch}",
        "build": str(len(records)),
        "commit": newest[1],
        "date": newest[2],
        "marker": marker,
    }


def _from_file(root: Path) -> dict[str, str] | None:
    """
    Reads the ``VERSION`` file.

    Args:
        root: Directory holding the file.

    Returns:
        dict[str, str] | None: The fields, or None when absent or empty.
    """

    try:
        return _parse((root / VERSION_FILE_NAME).read_text(encoding="utf-8"))
    except OSError:
        return None


def _write(root: Path, found: dict[str, str]) -> Path | None:
    """
    Stores a version in the ``VERSION`` file, never failing the caller.

    A package's folder is often read-only, and that must not stop a start.

    Args:
        root: Target directory.
        found: Fields to store.

    Returns:
        Path | None: The written file, or None when it could not be written.
    """

    line = " ".join(
        found.get(key, "") for key in ("name", "build", "commit", "date", "marker")
    ).strip()
    path = root / VERSION_FILE_NAME
    try:
        path.write_text(line + "\n", encoding="utf-8")
    except OSError:
        return None
    return path


def _resolve(root: Path) -> dict[str, str] | None:
    """
    Tries every source in order.

    Args:
        root: Project root.

    Returns:
        dict[str, str] | None: The first answer any source gave, or None.
    """

    fixed = _from_environment()
    if fixed is not None:
        return fixed

    stored = _from_file(root)
    if not (root / ".git").exists():
        # No history here, so the file is the only answer there can be.
        return stored

    marker = history_marker(root)
    # The file still describes the current history: the normal case on a start.
    if stored is not None and marker and stored["marker"] == marker:
        return stored

    derived = _from_git(root, marker)
    if derived is not None:
        _write(root, derived)
        return derived
    return stored


def details(*, refresh: bool = False) -> dict[str, str]:
    """
    Returns the running version with every field.

    Args:
        refresh: True to look it up again instead of using the cached answer.

    Returns:
        dict[str, str]: ``name``, ``build``, ``commit``, ``date`` and ``marker``;
        name is ``unknown`` when no source could be read.
    """

    global _cached, _cached_details

    if _cached_details is not None and not refresh:
        return dict(_cached_details)

    found = _resolve(project_root())
    if found is None or not found["name"]:
        found = {"name": UNKNOWN, "build": "", "commit": "", "date": "", "marker": ""}
    _cached_details = found
    _cached = (found["name"], found["build"])
    return dict(found)


def version(*, refresh: bool = False) -> tuple[str, str]:
    """
    Returns the running version as name and build.

    Args:
        refresh: True to look it up again instead of using the cached answer.

    Returns:
        tuple[str, str]: Version name and build number; name is ``unknown``
        when no source could be read.
    """

    if _cached is not None and not refresh:
        return _cached
    found = details(refresh=True)
    return (found["name"], found["build"])


def version_string(*, refresh: bool = False) -> str:
    """
    Returns the version the way it is shown to people.

    Args:
        refresh: True to look it up again.

    Returns:
        str: For example ``0.37.8 (124)``, or ``unknown``.
    """

    name, build = version(refresh=refresh)
    return f"{name} ({build})" if build else name


def version_label(*, refresh: bool = False) -> str:
    """
    Returns the full form, for the About dialog and for bug reports.

    Args:
        refresh: True to look it up again.

    Returns:
        str: For example ``0.37.8 (124) · 3b12058 · 29.09.2026``.
    """

    found = details(refresh=refresh)
    parts = [version_string()]
    if found["name"] != UNKNOWN:
        if found["commit"]:
            parts.append(found["commit"])
        if found["date"]:
            parts.append(_day_first(found["date"]))
    return " · ".join(parts)


def _day_first(date: str) -> str:
    """
    Writes ``YYYY-MM-DD`` as ``DD.MM.YYYY``.

    Args:
        date: The date as git reports it.

    Returns:
        str: The reordered date, or the input unchanged when it is no date.
    """

    parts = date.split("-")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return date
    return f"{parts[2]}.{parts[1]}.{parts[0]}"


def write_version_file(root: Path | None = None) -> Path:
    """
    Writes the derived version next to ``run.py``.

    The commit hook calls this through ``--write``; packaging may call it for
    another target directory.

    Args:
        root: Target directory; the project root by default.

    Returns:
        Path: The written file.
    """

    target = Path(root) if root is not None else project_root()
    found = details(refresh=True)
    path = target / VERSION_FILE_NAME
    if _write(target, found) is None:
        raise OSError(f"could not write {path}")
    return path


if __name__ == "__main__":
    # Lets the commit hook, and anybody curious, ask without starting the app.
    if len(sys.argv) > 1 and sys.argv[1] == "--write":
        write_version_file()
    print(version_label())
