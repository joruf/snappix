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

The single-file executable (``build-exe.py``) has neither sources to pull nor a
commit to compare, so it asks for the latest GitHub *release* instead: the
workflow ``release-exe.yml`` publishes one per build number, tagged
``v<version>-build<build>``, with one executable per platform. A higher build
number is an update; the matching asset is saved next to the running file under
its own, versioned name and takes its place.

Nothing here runs on its own: ``check`` only looks, ``apply`` only acts when the
caller says so.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from src import paths
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

# Release tags of the executables, as ``release-exe.yml`` writes them.
RELEASE_TAG = re.compile(r"^v(?P<version>[0-9][0-9.]*)-build(?P<build>[0-9]+)$")
# State key naming the executable an update replaced, until it is removed.
_REPLACED_KEY = "replaced_executable"
# The executable ``apply`` just downloaded; the restart starts it.
_updated_executable: Path | None = None


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
    if paths.IS_FROZEN:
        return _check_release()

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

    if paths.IS_FROZEN:
        return _apply_release()
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


def _state_file() -> Path:
    """
    Returns the file that remembers an executable update between two starts.

    Returns:
        Path: JSON file in the per-user data directory.
    """

    return paths.user_data_dir() / "update-state.json"


def _load_state() -> dict:
    """
    Reads the update state, never failing the caller.

    Returns:
        dict: The stored state; empty when there is none.
    """

    try:
        state = json.loads(_state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return state if isinstance(state, dict) else {}


def _save_state(state: dict) -> None:
    """
    Writes the update state, never failing the caller.

    Args:
        state: The state to store.

    Returns:
        None
    """

    try:
        _state_file().parent.mkdir(parents=True, exist_ok=True)
        _state_file().write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError:
        pass


def _running_build() -> int:
    """
    Returns the build number of this program.

    Returns:
        int: The build, ``0`` when it is unknown.
    """

    from src.version import version

    build = version()[1]
    return int(build) if build.isdigit() else 0


def _fetch_release() -> dict:
    """
    Asks the GitHub API for the newest executable release.

    Returns:
        dict: The release as the API returns it.

    Raises:
        ValueError: When the answer is no release.
    """

    url = f"https://api.github.com/repos/{repository_slug()}/releases/latest"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": _USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("the API returned no release")
    return payload


def release_build(tag: str) -> int | None:
    """
    Returns the build number of a release tag.

    Args:
        tag: For example ``v0.39.0-build129``.

    Returns:
        int | None: For example ``129``; None for a tag that is no executable build.
    """

    match = RELEASE_TAG.match(tag.strip())
    return int(match.group("build")) if match else None


def release_asset_name(release: dict) -> str:
    """
    Returns the file name this platform's executable has in a release.

    Args:
        release: The release as the GitHub API returns it.

    Returns:
        str: For example ``snappix-linux-x86_64-0.39.0-build129``; empty for a
        release that is not an executable build.
    """

    match = RELEASE_TAG.match(str(release.get("tag_name") or "").strip())
    if not match:
        return ""
    return paths.executable_name(match.group("version"), int(match.group("build")))


def release_asset_url(release: dict) -> str:
    """
    Returns the download URL of this platform's executable in a release.

    Args:
        release: The release as the GitHub API returns it.

    Returns:
        str: The URL, or an empty string when the release has none for us.
    """

    wanted = release_asset_name(release)
    if not wanted:
        return ""
    for asset in release.get("assets") or []:
        if isinstance(asset, dict) and asset.get("name") == wanted:
            return str(asset.get("browser_download_url") or "")
    return ""


def _check_release() -> UpdateInfo:
    """
    Compares the newest release with the build of this executable.

    Returns:
        UpdateInfo: What was found; never raises.
    """

    from src.version import version_string

    try:
        release = _fetch_release()
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return UpdateInfo(error=str(exc))
    tag = str(release.get("tag_name") or "")
    build = release_build(tag)
    if build is None:
        return UpdateInfo(error=f"the latest release {tag!r} is not an executable build")
    if not release_asset_url(release):
        return UpdateInfo(error=f"the release {tag} has no {release_asset_name(release)}")
    match = RELEASE_TAG.match(tag)
    remote = f"{match.group('version')} ({build})" if match else tag
    return UpdateInfo(
        available=build > _running_build(),
        local=version_string(),
        remote=remote,
        summary=str(release.get("name") or remote),
    )


def _apply_release() -> tuple[bool, str]:
    """
    Downloads the newest executable next to the running one.

    The file name carries the version, so the new one gets its own name instead
    of overwriting this one -- which Windows would refuse for a running ``.exe``
    anyway. The old file is removed, and the desktop shortcut and autostart are
    pointed at the new one, by ``finish_executable_update`` in the new program.

    Returns:
        tuple[bool, str]: Success flag and a message meant for the user.
    """

    global _updated_executable
    try:
        release = _fetch_release()
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return False, str(exc)
    url = release_asset_url(release)
    if not url:
        return False, f"the latest release has no {release_asset_name(release) or 'executable'}"

    current = paths.executable()
    target = current.with_name(release_asset_name(release))
    if target == current:
        return False, f"{current.name} is already this version"
    partial = target.with_name(target.name + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response, partial.open("wb") as handle:
            shutil.copyfileobj(response, handle)
        if partial.stat().st_size < 1024 * 1024:
            raise OSError("the downloaded file is too small to be the program")
        if not paths.is_windows():
            partial.chmod(0o755)
        os.replace(str(partial), str(target))
    except (urllib.error.URLError, OSError) as exc:
        try:
            if partial.exists():
                partial.unlink()
        except OSError:
            pass
        return False, f"{target}: {exc}"
    state = _load_state()
    state[_REPLACED_KEY] = str(current)
    _save_state(state)
    _updated_executable = target
    return True, f"updated to {target.name}"


def finish_executable_update(point_launchers: Callable[[], None] | None = None) -> None:
    """
    Completes an update in the program it installed.

    Points an existing desktop shortcut and autostart entry at this file, then
    removes the previous one. While the previous one is still running -- the
    Windows restart overlaps for a moment -- its removal waits for the next start.

    Args:
        point_launchers: Rewrites the existing launchers for this executable;
            run.py owns them.

    Returns:
        None
    """

    state = _load_state()
    previous = state.get(_REPLACED_KEY)
    if not isinstance(previous, str) or not previous:
        return
    old = Path(previous)
    if old == paths.executable():
        # The old file was started again; it must not delete itself.
        return
    if point_launchers is not None:
        try:
            point_launchers()
        except OSError:
            pass
    try:
        if old.exists():
            old.unlink()
    except OSError:
        # Still running, or locked by Windows: tried again on the next start.
        return
    state.pop(_REPLACED_KEY, None)
    _save_state(state)


def restart_command() -> list[str]:
    """
    Returns the command that starts Snappix again.

    Returns:
        list[str]: Interpreter and entry point; only the executable for the
        single-file build.
    """

    if paths.IS_FROZEN:
        return [str(_updated_executable or paths.executable())]
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
    # Without the unpacked files' library paths: execve bypasses the cleaning
    # every subprocess gets (see paths.use_system_environment_for_children).
    environment = paths.child_environment()
    if paths.IS_FROZEN:
        # Without it the new executable would reuse this one's unpacked files,
        # which are deleted the moment this process ends -- and run the old code.
        environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
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
