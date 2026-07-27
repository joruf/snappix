"""
Builds a standalone Windows executable of Snappix with PyInstaller.

Produces a one-folder PyInstaller build (`.build/windows/dist/Snappix/`) and
zips it into `dist/Snappix-{version}-windows-x64.zip`, mirroring how
`build_deb.sh` / `build_appimage.sh` drop their output in `dist/`.

Usage:
    python packaging/build_windows.py [version]

Requires PyInstaller (`pip install pyinstaller`); it is a build-time tool,
not a pinned runtime dependency, so it is not listed in requirements.txt.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = PROJECT_ROOT / ".build" / "windows"
DIST_DIR = PROJECT_ROOT / "dist"
APP_NAME = "Snappix"


def main() -> int:
    """
    Builds and zips the Windows PyInstaller bundle.

    Returns:
        int: Process exit code.
    """

    version = sys.argv[1] if len(sys.argv) > 1 else "0.1.0"

    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    work_dir = BUILD_DIR / "work"
    spec_dir = BUILD_DIR / "spec"
    onedir_dist = BUILD_DIR / "dist"
    work_dir.mkdir(parents=True)
    spec_dir.mkdir(parents=True)

    print("[snappix] Running PyInstaller...")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--name",
            APP_NAME,
            "--windowed",
            "--noconfirm",
            "--distpath",
            str(onedir_dist),
            "--workpath",
            str(work_dir),
            "--specpath",
            str(spec_dir),
            "--add-data",
            f"{PROJECT_ROOT / 'assets'}{';' if sys.platform == 'win32' else ':'}assets",
            "--hidden-import",
            "PySide6.QtSvg",
            "--hidden-import",
            "PySide6.QtMultimedia",
            "--hidden-import",
            "PySide6.QtMultimediaWidgets",
            "--hidden-import",
            "pynput.mouse._win32",
            "--hidden-import",
            "pynput.keyboard._win32",
            str(PROJECT_ROOT / "run.py"),
        ],
        cwd=PROJECT_ROOT,
        check=True,
    )

    app_dir = onedir_dist / APP_NAME
    if not app_dir.exists():
        print(f"[snappix] Expected PyInstaller output missing: {app_dir}", file=sys.stderr)
        return 1

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = DIST_DIR / f"{APP_NAME}-{version}-windows-x64.zip"
    if zip_path.exists():
        zip_path.unlink()

    print(f"[snappix] Zipping build: {zip_path}")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for file_path in app_dir.rglob("*"):
            if file_path.is_file():
                archive.write(file_path, Path(APP_NAME) / file_path.relative_to(app_dir))

    print("[snappix] Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
