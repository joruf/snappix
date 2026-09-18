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
tagged.

**One source, three routes to it.** A checkout has the history and reads it
directly. A package does not ship ``.git``, so the packaging scripts write the
number into a ``VERSION`` file next to ``run.py`` -- derived from the same
source, at build time, never typed in.

```
SNAPPIX_VERSION (environment)  ->  for tests and for one-off runs
git history                    ->  started from the checkout
VERSION                        ->  shipped as a package
otherwise                      ->  "unknown", and it says so
```

There is deliberately no invented fallback such as ``0.0.0``: a made-up number
looks real and sends every bug report in the wrong direction.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

#: Shown when nothing can be determined.
UNKNOWN = "unknown"

#: Commits whose subject starts like this begin a new feature round.
FEATURE_SUBJECT = re.compile(r"^(add|implement|introduce|bring)\b", re.IGNORECASE)

ENVIRONMENT_VARIABLE = "SNAPPIX_VERSION"
VERSION_FILE_NAME = "VERSION"

_cached: tuple[str, str] | None = None


def project_root() -> Path:
    """
    Returns the directory holding ``run.py``.

    Returns:
        Path: Project root.
    """

    return Path(__file__).resolve().parent.parent


def _from_environment() -> tuple[str, str] | None:
    """
    Reads an explicitly set version.

    Returns:
        tuple[str, str] | None: Name and build, or None when unset.
    """

    raw = os.environ.get(ENVIRONMENT_VARIABLE, "").strip()
    if not raw:
        return None
    parts = raw.split()
    return (parts[0], parts[1] if len(parts) > 1 else "")


def _from_git(root: Path) -> tuple[str, str] | None:
    """
    Derives the version from the commit history.

    Args:
        root: Directory to read the history of.

    Returns:
        tuple[str, str] | None: Name and build, or None without a history.
    """

    try:
        result = subprocess.run(
            ["git", "log", "--reverse", "--format=%s"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5.0,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    subjects = [line for line in result.stdout.splitlines() if line.strip()]
    if not subjects:
        return None

    minor = 0
    patch = 0
    for subject in subjects:
        if FEATURE_SUBJECT.match(subject):
            minor += 1
            patch = 0
        else:
            patch += 1
    return (f"0.{minor}.{patch}", str(len(subjects)))


def _from_file(root: Path) -> tuple[str, str] | None:
    """
    Reads the file the packaging scripts write.

    Args:
        root: Directory holding the file.

    Returns:
        tuple[str, str] | None: Name and build, or None when absent.
    """

    try:
        parts = (root / VERSION_FILE_NAME).read_text(encoding="utf-8").split()
    except OSError:
        return None
    if not parts:
        return None
    return (parts[0], parts[1] if len(parts) > 1 else "")


def version(*, refresh: bool = False) -> tuple[str, str]:
    """
    Returns the running version as name and build.

    Args:
        refresh: True to look it up again instead of using the cached answer.

    Returns:
        tuple[str, str]: Version name and build number; name is ``unknown``
        when no source could be read.
    """

    global _cached

    if _cached is not None and not refresh:
        return _cached

    root = project_root()
    for source in (_from_environment, lambda: _from_git(root), lambda: _from_file(root)):
        found = source()
        if found is not None and found[0]:
            _cached = found
            return _cached

    _cached = (UNKNOWN, "")
    return _cached


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


def write_version_file(root: Path | None = None) -> Path:
    """
    Writes the derived version next to ``run.py`` for packaging.

    Args:
        root: Target directory; the project root by default.

    Returns:
        Path: The written file.
    """

    target = Path(root) if root is not None else project_root()
    name, build = version(refresh=True)
    path = target / VERSION_FILE_NAME
    path.write_text(f"{name} {build}\n".strip() + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    print(version_string())
