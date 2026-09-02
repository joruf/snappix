"""
Per-user ffmpeg setup for Windows, without administrator rights.

Video recording, MP4 export, and GIF export all need ffmpeg. The winget package
``Gyan.FFmpeg`` installs machine-wide, so it prompts for elevation and cannot be
used at all on a locked-down Windows account.

The replacement is a plain ZIP. Nothing is executed to install it -- Python
unpacks two executables into Snappix's own runtime folder -- so no prompt
appears for anyone, administrator or not, and the system stays untouched.

``scripts/fetch_ffmpeg_windows.py`` can place that archive under ``vendor/``
beforehand, which makes the install work offline; otherwise it is downloaded.
"""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from shutil import which

RUNTIME_DIR_NAME = ".snappix-runtime"
FFMPEG_DIR_NAME = "ffmpeg"

VENDOR_ARCHIVE = Path("vendor") / "ffmpeg-windows.zip"

# ffplay is deliberately left out: Snappix plays video through Qt, and skipping
# it saves well over a hundred megabytes.
REQUIRED_EXECUTABLES = ("ffmpeg.exe", "ffprobe.exe")


def bundled_ffmpeg_dir(project_dir: Path) -> Path:
    """
    Returns the directory Snappix unpacks its own ffmpeg into.

    Args:
        project_dir: Project root directory.

    Returns:
        Path: Target directory inside the project runtime folder.
    """

    return Path(project_dir) / RUNTIME_DIR_NAME / FFMPEG_DIR_NAME


def bundled_ffmpeg_exe(project_dir: Path) -> Path:
    """
    Returns the path of the private ffmpeg executable.

    Args:
        project_dir: Project root directory.

    Returns:
        Path: Executable path, whether or not it exists yet.
    """

    return bundled_ffmpeg_dir(project_dir) / "ffmpeg.exe"


def has_bundled_ffmpeg(project_dir: Path) -> bool:
    """
    Reports whether the private copy is complete.

    Args:
        project_dir: Project root directory.

    Returns:
        bool: True when every required executable is present.
    """

    directory = bundled_ffmpeg_dir(project_dir)
    return all((directory / name).is_file() for name in REQUIRED_EXECUTABLES)


def vendored_archive(project_dir: Path) -> Path | None:
    """
    Returns the pre-fetched archive when one is available.

    Args:
        project_dir: Project root directory.

    Returns:
        Path | None: Archive path, or None when it was not fetched.
    """

    archive = Path(project_dir) / VENDOR_ARCHIVE
    return archive if archive.is_file() else None


def extract_executables(archive: Path, target_dir: Path) -> list[Path]:
    """
    Unpacks the needed executables out of the archive.

    The archive nests everything under one version-named directory; the
    executables are flattened into ``target_dir`` so their location does not
    change with every ffmpeg release.

    Args:
        archive: ZIP to read.
        target_dir: Directory to write the executables into.

    Returns:
        list[Path]: Written files.

    Raises:
        OSError: When the archive does not carry the executables.
    """

    target_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with zipfile.ZipFile(archive) as bundle:
        members = {
            Path(name.replace("\\", "/")).name: name
            for name in bundle.namelist()
            if not name.endswith("/")
        }
        for executable in REQUIRED_EXECUTABLES:
            source = members.get(executable)
            if source is None:
                raise OSError(f"{executable} is missing from {archive.name}")
            destination = target_dir / executable
            with bundle.open(source) as reader, destination.open("wb") as writer:
                shutil.copyfileobj(reader, writer)
            destination.chmod(0o755)
            written.append(destination)
    return written


def _download_current_archive(destination: Path) -> Path:
    """
    Downloads the archive the fetch script would have placed under ``vendor``.

    Args:
        destination: File to write.

    Returns:
        Path: The written archive.

    Raises:
        OSError: When the download fails.
    """

    from scripts.fetch_ffmpeg_windows import download, list_assets, verify_archive

    assets = list_assets()
    if not assets:
        raise OSError("no Windows build offered by the current release")
    download(assets[-1]["browser_download_url"], destination)
    verify_archive(destination)
    return destination


def install_for_current_user(project_dir: Path) -> bool:
    """
    Unpacks ffmpeg into the project runtime folder without elevation.

    Args:
        project_dir: Project root directory.

    Returns:
        bool: True when a usable ffmpeg exists afterwards.
    """

    from src.paths import is_windows

    if not is_windows():
        return False
    if has_bundled_ffmpeg(project_dir):
        return True

    project_dir = Path(project_dir)
    target_dir = bundled_ffmpeg_dir(project_dir)
    archive = vendored_archive(project_dir)
    temporary_archive: Path | None = None

    if archive is None:
        temporary_archive = target_dir.parent / "ffmpeg-windows.zip"
        print("Snappix installer: downloading ffmpeg (no administrator rights needed)…")
        try:
            archive = _download_current_archive(temporary_archive)
        except (OSError, ValueError) as error:
            print(f"Snappix installer warning: ffmpeg download failed: {error}")
            return False
    else:
        print(f"Snappix installer: using {archive.name} from vendor/…")

    try:
        extract_executables(archive, target_dir)
    except (OSError, zipfile.BadZipFile) as error:
        print(f"Snappix installer warning: ffmpeg could not be unpacked: {error}")
        return False
    finally:
        if temporary_archive is not None:
            temporary_archive.unlink(missing_ok=True)

    if not has_bundled_ffmpeg(project_dir):
        print(
            "Snappix installer warning: ffmpeg is still incomplete. "
            "Video recording and MP4/GIF export stay unavailable."
        )
        return False
    print(f"Snappix installer: ffmpeg ready in {target_dir}.")
    return True


def resolve_ffprobe_path() -> str | None:
    """
    Resolves the ffprobe executable for the current machine.

    Mirrors the ffmpeg lookup: ``PATH`` first, then Snappix's own copy, which on
    an account without administrator rights is the only one that can exist.

    Returns:
        str | None: Path to ffprobe, or None when nothing was found.
    """

    found = which("ffprobe")
    if found:
        return found

    from src.paths import is_windows

    if not is_windows():
        return None

    candidate = bundled_ffmpeg_dir(Path(__file__).resolve().parent.parent) / "ffprobe.exe"
    try:
        return str(candidate) if candidate.is_file() else None
    except OSError:
        return None


def bundled_version_note(project_dir: Path) -> str:
    """
    Returns a short description of the archive used, when recorded.

    Args:
        project_dir: Project root directory.

    Returns:
        str: Asset name, or an empty string when unknown.
    """

    metadata = Path(project_dir) / "vendor" / "ffmpeg-windows.json"
    try:
        return str(json.loads(metadata.read_text(encoding="utf-8")).get("asset", ""))
    except (OSError, ValueError):
        return ""
