#!/usr/bin/env python3
"""
Fetches the current Windows ffmpeg build as one ZIP for offline installs.

Snappix needs ffmpeg for video recording and MP4/GIF export, and on Windows the
winget package installs machine-wide -- which prompts for administrator rights
and simply fails on accounts that do not have them. A plain ZIP avoids that
entirely: it is unpacked with Python, so no installer runs and nobody is asked
for anything.

The archive is far too large to keep in the repository, so this script produces
it on demand instead. The download is picked from the current release, and what
was fetched is written next to it so the build in use stays identifiable.

The GPL variant is required, not a preference: Snappix encodes H.264 through
``libx264``, which the LGPL builds do not carry.

Usage::

    python scripts/fetch_ffmpeg_windows.py            # fetch when missing
    python scripts/fetch_ffmpeg_windows.py --force    # fetch again
    python scripts/fetch_ffmpeg_windows.py --list     # only show what is offered
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

RELEASE_API = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest"

# Static GPL build for 64-bit Windows: one directory with self-contained
# executables, no shared DLLs to place and no registry entries.
ASSET_PATTERN = re.compile(r"^ffmpeg-(?:n(?P<version>[\d.]+)-)?.*win64-gpl.*\.zip$")

VENDOR_DIR_NAME = "vendor"
ARCHIVE_NAME = "ffmpeg-windows.zip"
METADATA_NAME = "ffmpeg-windows.json"

REQUIRED_MEMBER_SUFFIX = "bin/ffmpeg.exe"


def project_root() -> Path:
    """
    Returns the repository root.

    Returns:
        Path: Directory containing this script's parent.
    """

    return Path(__file__).resolve().parent.parent


def archive_path(root: Path) -> Path:
    """
    Returns where the fetched archive is stored.

    Args:
        root: Repository root.

    Returns:
        Path: Archive path; the directory is git-ignored.
    """

    return root / VENDOR_DIR_NAME / ARCHIVE_NAME


def metadata_path(root: Path) -> Path:
    """
    Returns where the provenance record is stored.

    Args:
        root: Repository root.

    Returns:
        Path: Metadata path.
    """

    return root / VENDOR_DIR_NAME / METADATA_NAME


def _version_key(name: str) -> tuple[int, tuple[int, ...]]:
    """
    Builds a sort key that prefers numbered releases over master builds.

    Args:
        name: Asset file name.

    Returns:
        tuple: Sort key; higher sorts later.
    """

    match = ASSET_PATTERN.match(name)
    version = match.group("version") if match else None
    if not version:
        # A master build is usable but less predictable than a release.
        return (0, ())
    return (1, tuple(int(part) for part in version.split(".") if part.isdigit()))


def list_assets(*, timeout: float = 60.0) -> list[dict]:
    """
    Returns the candidate Windows archives from the current release.

    Args:
        timeout: Network timeout in seconds.

    Returns:
        list[dict]: Matching assets, best last.

    Raises:
        OSError: When the release cannot be read.
    """

    request = urllib.request.Request(
        RELEASE_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "snappix"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        release = json.load(response)

    assets = [
        asset
        for asset in release.get("assets", [])
        if ASSET_PATTERN.match(asset.get("name", ""))
        and "shared" not in asset.get("name", "")
    ]
    assets.sort(key=lambda asset: _version_key(asset["name"]))
    for asset in assets:
        asset["release_tag"] = release.get("tag_name", "")
        asset["published_at"] = release.get("published_at", "")
    return assets


def download(url: str, destination: Path, *, timeout: float = 900.0) -> Path:
    """
    Downloads one file, reporting progress on a single line.

    Args:
        url: Source URL.
        destination: Target file.
        timeout: Network timeout in seconds.

    Returns:
        Path: The written file.

    Raises:
        OSError: When the download fails.
    """

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "snappix"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        total = int(response.headers.get("Content-Length") or 0)
        written = 0
        with partial.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 512)
                if not chunk:
                    break
                handle.write(chunk)
                written += len(chunk)
                if total:
                    print(
                        f"\r  {written // (1024 * 1024)} / "
                        f"{total // (1024 * 1024)} MB",
                        end="",
                        flush=True,
                    )
    print()
    if total and written != total:
        partial.unlink(missing_ok=True)
        raise OSError(f"download incomplete: {written} of {total} bytes")
    partial.replace(destination)
    return destination


def verify_archive(archive: Path) -> str:
    """
    Checks that the archive really contains an ffmpeg executable.

    Args:
        archive: Downloaded ZIP.

    Returns:
        str: Archive-internal path of the executable.

    Raises:
        OSError: When the archive is unusable.
    """

    try:
        with zipfile.ZipFile(archive) as bundle:
            broken = bundle.testzip()
            if broken is not None:
                raise OSError(f"archive is damaged at {broken}")
            for name in bundle.namelist():
                if name.replace("\\", "/").endswith(REQUIRED_MEMBER_SUFFIX):
                    return name
    except zipfile.BadZipFile as error:
        raise OSError(f"not a usable ZIP: {error}") from error
    raise OSError(f"no {REQUIRED_MEMBER_SUFFIX} inside the archive")


def sha256(path: Path) -> str:
    """
    Returns the SHA-256 checksum of one file.

    Args:
        path: File to read.

    Returns:
        str: Hex digest.
    """

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    """
    Fetches and verifies the archive.

    Returns:
        int: Exit code.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="fetch even if present")
    parser.add_argument("--list", action="store_true", help="only list the candidates")
    arguments = parser.parse_args()

    root = project_root()
    archive = archive_path(root)

    try:
        assets = list_assets()
    except (OSError, ValueError) as error:
        print(f"Could not read the release list: {error}", file=sys.stderr)
        return 1
    if not assets:
        print("No matching Windows GPL build in the current release.", file=sys.stderr)
        return 1

    if arguments.list:
        for asset in assets:
            print(f"  {asset['name']}: {asset['size'] // (1024 * 1024)} MB")
        print(f"\nWould take: {assets[-1]['name']}")
        return 0

    if archive.is_file() and not arguments.force:
        print(f"Already present: {archive} ({archive.stat().st_size // (1024 * 1024)} MB)")
        print("Use --force to fetch it again.")
        return 0

    chosen = assets[-1]
    print(f"ffmpeg for Windows: {chosen['name']} ({chosen['size'] // (1024 * 1024)} MB)")
    try:
        download(chosen["browser_download_url"], archive)
        member = verify_archive(archive)
    except OSError as error:
        print(f"Failed: {error}", file=sys.stderr)
        archive.unlink(missing_ok=True)
        return 1

    checksum = sha256(archive)
    metadata_path(root).write_text(
        json.dumps(
            {
                "asset": chosen["name"],
                "url": chosen["browser_download_url"],
                "release_tag": chosen.get("release_tag", ""),
                "published_at": chosen.get("published_at", ""),
                "size_bytes": archive.stat().st_size,
                "sha256": checksum,
                "executable": member,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Stored:     {archive}")
    print(f"Executable: {member}")
    print(f"SHA-256:    {checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
