"""
Per-user Tesseract setup for Windows, without administrator rights.

The winget package ``UB-Mannheim.TesseractOCR`` installs machine-wide, so it
needs elevation: users on a locked-down Windows account cannot install it at
all, and everyone else gets a UAC prompt during setup.

The installer behind that package is an NSIS one, and its manifest requests
``highestAvailable`` rather than ``requireAdministrator``. That difference is
what makes this module possible: started by an account without administrator
rights, Windows runs it at that account's own level and shows no prompt at all.
Pointed at a directory the user can write to, it then produces a complete,
self-contained Tesseract -- the build ships its own MinGW runtime, so nothing
has to be registered system-wide.

Snappix already keeps a private runtime directory for uv and Python; Tesseract
goes next to them.
"""

from __future__ import annotations

import os
import subprocess
import urllib.request
from pathlib import Path

# Same file the winget manifest points at, from the maintainer's own server.
TESSERACT_VERSION = "5.3.0.20221214"
TESSERACT_INSTALLER_URL = (
    "https://digi.bib.uni-mannheim.de/tesseract/"
    f"tesseract-ocr-w64-setup-v{TESSERACT_VERSION}.exe"
)

RUNTIME_DIR_NAME = ".snappix-runtime"
TESSERACT_DIR_NAME = "tesseract"

# Roughly what the silent install writes; used only for the progress message.
APPROXIMATE_INSTALL_MB = 300


def bundled_tesseract_dir(project_dir: Path) -> Path:
    """
    Returns the directory Snappix installs its own Tesseract into.

    Args:
        project_dir: Project root directory.

    Returns:
        Path: Target directory inside the project runtime folder.
    """

    return Path(project_dir) / RUNTIME_DIR_NAME / TESSERACT_DIR_NAME


def bundled_tesseract_exe(project_dir: Path) -> Path:
    """
    Returns the path of the private Tesseract executable.

    Args:
        project_dir: Project root directory.

    Returns:
        Path: Executable path, whether or not it exists yet.
    """

    return bundled_tesseract_dir(project_dir) / "tesseract.exe"


def has_bundled_tesseract(project_dir: Path) -> bool:
    """
    Reports whether Snappix already installed its own Tesseract.

    Args:
        project_dir: Project root directory.

    Returns:
        bool: True when the private executable is present.
    """

    return bundled_tesseract_exe(project_dir).is_file()


def build_silent_install_command(installer: Path, target_dir: Path) -> str:
    """
    Builds the NSIS silent-install command line.

    Returned as one string on purpose. NSIS requires ``/D=`` to be the last
    argument and to stay *unquoted* even when the path contains spaces; passing
    the arguments as a list would let Windows quote it and the installer would
    fall back to its default machine-wide directory.

    Args:
        installer: Downloaded installer path.
        target_dir: Directory to install into.

    Returns:
        str: Complete command line.
    """

    # No trailing separator: NSIS treats one as an escape and drops the path.
    target = str(target_dir).rstrip("\\/")
    return f'"{installer}" /S /D={target}'


def download_installer(destination: Path, *, timeout: float = 300.0) -> Path:
    """
    Downloads the official Tesseract installer.

    Args:
        destination: File to write.
        timeout: Network timeout in seconds.

    Returns:
        Path: The written file.

    Raises:
        OSError: When the download fails.
    """

    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(TESSERACT_INSTALLER_URL, timeout=timeout) as response:
        payload = response.read()
    if len(payload) < 1_000_000:
        raise OSError("Tesseract download looks truncated")
    destination.write_bytes(payload)
    return destination


def install_for_current_user(project_dir: Path, *, timeout: float = 900.0) -> bool:
    """
    Installs Tesseract into the project runtime folder without elevation.

    Args:
        project_dir: Project root directory.
        timeout: Seconds to allow for the silent install.

    Returns:
        bool: True when a usable executable exists afterwards.
    """

    from src.paths import is_windows

    if not is_windows():
        return False
    if has_bundled_tesseract(project_dir):
        return True

    target_dir = bundled_tesseract_dir(project_dir)
    installer = target_dir.parent / f"tesseract-setup-{TESSERACT_VERSION}.exe"

    print(
        "Snappix installer: downloading Tesseract OCR "
        f"({APPROXIMATE_INSTALL_MB} MB installed, no administrator rights needed)…"
    )
    try:
        download_installer(installer)
    except (OSError, ValueError) as error:
        print(f"Snappix installer warning: Tesseract download failed: {error}")
        return False

    target_dir.mkdir(parents=True, exist_ok=True)
    print(f"Snappix installer: installing Tesseract into {target_dir}…")
    try:
        subprocess.run(
            build_silent_install_command(installer, target_dir),
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as error:
        print(f"Snappix installer warning: Tesseract install failed: {error}")
        return False
    finally:
        try:
            installer.unlink(missing_ok=True)
        except OSError:
            pass

    if not has_bundled_tesseract(project_dir):
        print(
            "Snappix installer warning: Tesseract was not installed. "
            "OCR stays unavailable; every other feature works."
        )
        return False
    print("Snappix installer: Tesseract ready.")
    return True


def tessdata_dir(project_dir: Path) -> Path:
    """
    Returns the language-data directory of the private install.

    Args:
        project_dir: Project root directory.

    Returns:
        Path: ``tessdata`` directory next to the executable.
    """

    return bundled_tesseract_dir(project_dir) / "tessdata"


def tesseract_environment(project_dir: Path) -> dict[str, str]:
    """
    Returns the environment needed to run the private Tesseract.

    A Tesseract outside its install location cannot find its language files on
    its own; ``TESSDATA_PREFIX`` is what points it back at them.

    Args:
        project_dir: Project root directory.

    Returns:
        dict[str, str]: Environment for ``subprocess``.
    """

    environment = dict(os.environ)
    data_dir = tessdata_dir(project_dir)
    if data_dir.is_dir():
        environment["TESSDATA_PREFIX"] = str(data_dir)
    return environment
