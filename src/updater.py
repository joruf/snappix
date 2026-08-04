"""
Checking GitHub for a newer version, fetching it, and restarting.

The repository publishes neither releases nor tags, so "newer" means the head
commit of the default branch: the API reports it, and it is compared against the
commit this checkout sits on.

Two ways to apply an update:

* **git** -- ``git pull --ff-only`` when Snappix runs from a checkout. It refuses
  to run over local commits or a dirty tree, which is the point: never silently
  discard someone's work.
* **archive** -- otherwise the branch ZIP is downloaded and unpacked over the
  installation. Only files the archive carries are replaced; the workspace
  folder, the configuration, and saved projects live elsewhere and are never
  touched.

Nothing here runs on its own: ``check`` only looks, ``apply`` only acts when the
caller says so.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from src.constants import ABOUT_GITHUB, APP_NAME
from src.py_compat import dataclass

# Branch the update is taken from.
BRANCH = "main"
# Seconds to wait for GitHub before giving up.
TIMEOUT = 20.0

_USER_AGENT = f"{APP_NAME} (+{ABOUT_GITHUB})"

# Files and folders an archive update never overwrites: user state must survive
# an update, and .git would corrupt a checkout.
_KEEP = frozenset({".git", ".venv", "config.json", "snappix.log"})


@dataclass
class UpdateInfo:
    """
    Class UpdateInfo

    Outcome of one look at the repository.
    """

    available: bool = False
    local: str = ""
    remote: str = ""
    summary: str = ""
    error: str = ""


def project_root() -> Path:
    """
    Returns the installation directory Snappix runs from.

    Returns:
        Path: Directory holding ``run.py``.
    """

    return Path(__file__).resolve().parent.parent


def repository_slug(url: str = ABOUT_GITHUB) -> str:
    """
    Extracts ``owner/name`` from a GitHub repository URL.

    Args:
        url: Repository URL.

    Returns:
        str: The slug, or an empty string when the URL is not GitHub.
    """

    marker = "github.com/"
    if marker not in url:
        return ""
    slug = url.split(marker, 1)[1]
    if slug.endswith(".git"):
        slug = slug[:-4]
    return slug.strip("/")


def is_git_checkout(root: Path | None = None) -> bool:
    """
    Reports whether the installation is a usable git working tree.

    Args:
        root: Installation directory; defaults to the project root.

    Returns:
        bool: True when git can be used to update.
    """

    target = root or project_root()
    return (target / ".git").exists() and shutil.which("git") is not None


def local_commit(root: Path | None = None) -> str:
    """
    Returns the commit the installation sits on.

    Args:
        root: Installation directory; defaults to the project root.

    Returns:
        str: Full SHA, or an empty string when it cannot be determined.
    """

    target = root or project_root()
    if not is_git_checkout(target):
        return ""
    code, output = _run(["git", "rev-parse", "HEAD"], target)
    return output.strip() if code == 0 else ""


def _fetch_head() -> tuple[str, str]:
    """
    Asks the GitHub API for the branch head.

    Split out from ``check`` so the comparison logic can be tested without a
    network connection.

    Returns:
        tuple[str, str]: Commit SHA and the first line of its message.
    """

    url = f"https://api.github.com/repos/{repository_slug()}/commits/{BRANCH}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": _USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        payload = json.load(response)

    sha = str(payload.get("sha") or "")
    summary = ""
    commit = payload.get("commit")
    if isinstance(commit, dict) and commit.get("message"):
        summary = str(commit["message"]).splitlines()[0]
    return sha, summary


def check(root: Path | None = None) -> UpdateInfo:
    """
    Asks GitHub whether the branch is ahead of this installation.

    Never raises: a failed check is reported through ``UpdateInfo.error`` so a
    missing network connection cannot take the app down.

    Args:
        root: Installation directory; defaults to the project root.

    Returns:
        UpdateInfo: What was found.
    """

    if not repository_slug():
        return UpdateInfo(error=f"{ABOUT_GITHUB} is not a GitHub repository")

    try:
        remote, summary = _fetch_head()
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return UpdateInfo(error=str(exc))

    if not remote:
        return UpdateInfo(error="the API returned no commit")

    local = local_commit(root)
    return UpdateInfo(
        available=bool(local) and local != remote,
        local=local[:10],
        remote=remote[:10],
        summary=summary,
    )


def apply(root: Path | None = None) -> tuple[bool, str]:
    """
    Fetches the new version into the installation.

    Args:
        root: Installation directory; defaults to the project root.

    Returns:
        tuple[bool, str]: Success flag and a message meant for the user.
    """

    target = root or project_root()
    if is_git_checkout(target):
        return _apply_git(target)
    return _apply_archive(target)


def _apply_git(root: Path) -> tuple[bool, str]:
    """
    Updates a git checkout, refusing to touch local work.

    Args:
        root: The working tree.

    Returns:
        tuple[bool, str]: Success flag and message.
    """

    code, output = _run(["git", "status", "--porcelain"], root)
    if code != 0:
        return False, f"git status failed: {output.strip()}"
    if output.strip():
        return False, "There are local changes; commit or discard them first."

    code, output = _run(["git", "pull", "--ff-only"], root, timeout=180.0)
    if code != 0:
        return False, output.strip() or "git pull failed"
    return True, output.strip()


def _apply_archive(root: Path) -> tuple[bool, str]:
    """
    Downloads the branch archive and unpacks it over the installation.

    Args:
        root: Installation directory.

    Returns:
        tuple[bool, str]: Success flag and message.
    """

    slug = repository_slug()
    if not slug:
        return False, "no GitHub repository configured"
    url = f"https://github.com/{slug}/archive/refs/heads/{BRANCH}.zip"

    with tempfile.TemporaryDirectory(prefix="snappix-update-") as work:
        archive = Path(work) / "update.zip"
        request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                archive.write_bytes(response.read())
            with zipfile.ZipFile(archive) as bundle:
                bundle.extractall(work)
        except (urllib.error.URLError, OSError, zipfile.BadZipFile) as exc:
            return False, f"Download failed: {exc}"

        unpacked = [item for item in Path(work).iterdir() if item.is_dir()]
        if len(unpacked) != 1:
            return False, "the archive has an unexpected layout"
        copied = _copy_tree(unpacked[0], root)

    return True, f"{copied} files updated"


def _copy_tree(source: Path, target: Path) -> int:
    """
    Copies the archive contents over the installation.

    Args:
        source: Unpacked archive root.
        target: Installation directory.

    Returns:
        int: How many files were written.
    """

    written = 0
    for item in source.rglob("*"):
        relative = item.relative_to(source)
        if relative.parts and relative.parts[0] in _KEEP:
            continue
        destination = target / relative
        if item.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, destination)
        written += 1
    return written


def restart_command() -> list[str]:
    """
    Returns the command that starts Snappix again.

    Returns:
        list[str]: Interpreter and entry point.
    """

    root = project_root()
    candidates = [
        root / ".venv" / ("Scripts" if sys.platform == "win32" else "bin") / (
            "pythonw.exe" if sys.platform == "win32" else "python3"
        ),
        Path(sys.executable),
    ]
    interpreter = next((path for path in candidates if path.exists()), Path(sys.executable))
    return [str(interpreter), str(root / "run.py")]


def restart() -> None:
    """
    Replaces the running program with a fresh one.

    On POSIX the process is replaced outright; Windows cannot do that, so a new
    one is spawned and this one is expected to exit right after.

    Returns:
        None
    """

    command = restart_command()
    environment = dict(os.environ)
    if sys.platform == "win32":
        subprocess.Popen(command, env=environment, close_fds=True)
        return
    os.execve(command[0], command, environment)


def _run(command: list[str], cwd: Path, timeout: float = 60.0) -> tuple[int, str]:
    """
    Runs a command in one directory and captures its combined output.

    Args:
        command: Command and arguments.
        cwd: Working directory.
        timeout: Seconds before the command is abandoned.

    Returns:
        tuple[int, str]: Exit code and combined output.
    """

    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)
    return completed.returncode, completed.stdout or ""
