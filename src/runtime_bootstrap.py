"""
Managed Python runtime bootstrap via project-local uv.

Downloads uv when missing, installs CPython 3.12 into ``.snappix-runtime``,
creates ``.venv``, and installs pinned requirements — independent of the host
Python version.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

TARGET_PYTHON = "3.12"
UV_VERSION = "0.11.32"
RUNTIME_DIRNAME = ".snappix-runtime"
UV_RELEASE_BASE = (
    f"https://github.com/astral-sh/uv/releases/download/{UV_VERSION}"
)


def runtime_dir(project_dir: Path) -> Path:
    """
    Returns the project-local managed runtime directory.

    Args:
        project_dir: Snappix project root.

    Returns:
        Path: ``.snappix-runtime`` under the project.
    """

    return project_dir / RUNTIME_DIRNAME


def uv_binary_path(project_dir: Path) -> Path:
    """
    Returns the expected path of the project-local uv executable.

    Args:
        project_dir: Snappix project root.

    Returns:
        Path: ``uv.exe`` on Windows, ``uv`` elsewhere.
    """

    name = "uv.exe" if sys.platform == "win32" else "uv"
    return runtime_dir(project_dir) / "uv" / name


def uv_env(project_dir: Path) -> dict[str, str]:
    """
    Builds an environment that keeps uv caches inside the project runtime dir.

    Args:
        project_dir: Snappix project root.

    Returns:
        dict[str, str]: Environment for uv subprocesses.
    """

    root = runtime_dir(project_dir)
    env = dict(os.environ)
    env["UV_CACHE_DIR"] = str(root / "cache")
    env["UV_PYTHON_INSTALL_DIR"] = str(root / "python")
    return env


def _machine_tag() -> str:
    """
    Normalizes ``platform.machine()`` to uv release architecture names.

    Returns:
        str: ``x86_64``, ``aarch64``, or the raw machine string.
    """

    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        return "x86_64"
    if machine in {"aarch64", "arm64"}:
        return "aarch64"
    return machine


def uv_download_spec() -> tuple[str, str]:
    """
    Resolves the uv release asset filename and download URL for this host.

    Returns:
        tuple[str, str]: ``(filename, url)``.

    Raises:
        RuntimeError: When the OS/arch combination is unsupported.
    """

    arch = _machine_tag()
    if sys.platform == "win32":
        if arch != "x86_64":
            raise RuntimeError(
                f"Snappix managed runtime does not support Windows/{arch}."
            )
        filename = "uv-x86_64-pc-windows-msvc.zip"
    elif sys.platform.startswith("linux"):
        if arch not in {"x86_64", "aarch64"}:
            raise RuntimeError(
                f"Snappix managed runtime does not support Linux/{arch}."
            )
        filename = f"uv-{arch}-unknown-linux-gnu.tar.gz"
    else:
        raise RuntimeError(
            f"Snappix managed runtime does not support platform {sys.platform}."
        )
    return filename, f"{UV_RELEASE_BASE}/{filename}"


def _download_file(url: str, destination: Path) -> None:
    """
    Downloads one URL to a local file with a progress log line.

    Args:
        url: Remote URL.
        destination: Local file path.

    Returns:
        None

    Raises:
        RuntimeError: When the download fails.
    """

    print(f"Snappix installer: downloading {url}...")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=120) as response:
            destination.write_bytes(response.read())
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(
            f"Failed to download managed runtime tooling from {url}: {exc}"
        ) from exc


def _extract_archive(archive: Path, target_dir: Path) -> None:
    """
    Extracts a zip or tar.gz archive into ``target_dir``.

    Args:
        archive: Downloaded archive path.
        target_dir: Extraction directory.

    Returns:
        None
    """

    target_dir.mkdir(parents=True, exist_ok=True)
    if archive.suffix == ".zip" or archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as handle:
            handle.extractall(target_dir)
        return
    with tarfile.open(archive, "r:gz") as handle:
        handle.extractall(target_dir)


def _find_extracted_uv(extract_root: Path) -> Path:
    """
    Locates the uv binary inside an extracted release archive.

    Args:
        extract_root: Directory where the archive was unpacked.

    Returns:
        Path: Found uv executable.

    Raises:
        RuntimeError: When uv cannot be found.
    """

    names = ("uv.exe", "uv")
    for name in names:
        direct = extract_root / name
        if direct.is_file():
            return direct
    for path in extract_root.rglob("*"):
        if path.is_file() and path.name in names:
            return path
    raise RuntimeError("Downloaded uv archive did not contain an uv binary.")


def ensure_uv(project_dir: Path) -> Path:
    """
    Ensures a project-local uv binary exists, downloading it when needed.

    Args:
        project_dir: Snappix project root.

    Returns:
        Path: Path to the uv executable.

    Raises:
        RuntimeError: When download or extraction fails.
    """

    uv_path = uv_binary_path(project_dir)
    if uv_path.is_file():
        return uv_path

    print("Snappix installer: installing uv toolchain…")
    filename, url = uv_download_spec()
    uv_home = uv_path.parent
    uv_home.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="snappix-uv-") as tmp:
        archive = Path(tmp) / filename
        extract_root = Path(tmp) / "extract"
        _download_file(url, archive)
        _extract_archive(archive, extract_root)
        extracted = _find_extracted_uv(extract_root)
        if uv_path.exists():
            uv_path.unlink()
        shutil.copy2(extracted, uv_path)

    if sys.platform != "win32":
        uv_path.chmod(uv_path.stat().st_mode | 0o111)

    if not uv_path.is_file():
        raise RuntimeError(f"uv binary missing after install: {uv_path}")

    from src.install_manifest import record_project_dir, record_runtime_created

    record_project_dir(project_dir)
    record_runtime_created(project_dir)
    print(f"Snappix installer: uv ready at {uv_path}")
    return uv_path


def _run_uv(
    project_dir: Path,
    uv_path: Path,
    args: list[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """
    Runs one uv command with project-local cache/python dirs.

    Args:
        project_dir: Snappix project root.
        uv_path: Path to uv.
        args: Arguments after the uv binary.
        check: Raise when the exit code is non-zero.

    Returns:
        subprocess.CompletedProcess[str]: Completed process result.

    Raises:
        RuntimeError: When ``check`` is True and the command fails.
    """

    command = [str(uv_path), *args]
    result = subprocess.run(
        command,
        cwd=str(project_dir),
        check=False,
        capture_output=True,
        text=True,
        env=uv_env(project_dir),
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(
            f"uv command failed ({' '.join(args)}): {detail or result.returncode}"
        )
    if result.stdout.strip():
        print(result.stdout.rstrip())
    if result.stderr.strip() and result.returncode == 0:
        # uv often writes progress to stderr.
        print(result.stderr.rstrip())
    return result


def ensure_managed_python(project_dir: Path, uv_path: Path | None = None) -> None:
    """
    Installs the target CPython version via uv when missing.

    Args:
        project_dir: Snappix project root.
        uv_path: Optional existing uv path.

    Returns:
        None
    """

    binary = uv_path or ensure_uv(project_dir)
    print(f"Snappix installer: ensuring Python {TARGET_PYTHON} runtime…")
    _run_uv(project_dir, binary, ["python", "install", TARGET_PYTHON])


def _venv_python(project_dir: Path) -> Path:
    """
    Resolves the project ``.venv`` interpreter path for this OS.

    Args:
        project_dir: Snappix project root.

    Returns:
        Path: Interpreter path (may not exist yet).
    """

    from src.paths import venv_python_path

    return venv_python_path(project_dir)


def _python_version(python_bin: Path) -> tuple[int, int] | None:
    """
    Probes major/minor version of one interpreter.

    Args:
        python_bin: Interpreter path.

    Returns:
        tuple[int, int] | None: Version pair or None.
    """

    result = subprocess.run(
        [
            str(python_bin),
            "-c",
            "import sys; print(f'{sys.version_info[0]} {sys.version_info[1]}')",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    parts = result.stdout.strip().split()
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def ensure_venv(project_dir: Path, uv_path: Path | None = None) -> Path:
    """
    Creates or refreshes ``.venv`` using the managed Python 3.12 toolchain.

    Args:
        project_dir: Snappix project root.
        uv_path: Optional existing uv path.

    Returns:
        Path: Path to the venv Python interpreter.
    """

    from src.py_compat import is_supported_python

    binary = uv_path or ensure_uv(project_dir)
    ensure_managed_python(project_dir, binary)

    venv_dir = project_dir / ".venv"
    venv_py = _venv_python(project_dir)
    if venv_dir.exists() and venv_py.exists():
        version = _python_version(venv_py)
        if version is not None and is_supported_python(version):
            return venv_py
        print(
            "Snappix installer: existing .venv uses unsupported Python "
            f"{'.'.join(str(part) for part in (version or ('?', '?')))}; "
            "recreating…"
        )
        shutil.rmtree(venv_dir)

    print("Snappix installer: creating virtual environment...")
    _run_uv(
        project_dir,
        binary,
        ["venv", "--python", TARGET_PYTHON, str(venv_dir)],
    )
    if not venv_py.exists():
        raise RuntimeError(f"Virtual environment Python missing at {venv_py}")

    from src.install_manifest import record_project_dir, record_runtime_created, record_venv_created

    record_project_dir(project_dir)
    record_venv_created(project_dir)
    record_runtime_created(project_dir)
    return venv_py


def install_requirements(project_dir: Path, uv_path: Path | None = None) -> None:
    """
    Installs pinned requirements into the project ``.venv`` via uv pip.

    Args:
        project_dir: Snappix project root.
        uv_path: Optional existing uv path.

    Returns:
        None
    """

    binary = uv_path or ensure_uv(project_dir)
    venv_py = ensure_venv(project_dir, binary)
    requirements = project_dir / "requirements.txt"
    if not requirements.is_file():
        raise RuntimeError(f"requirements.txt missing at {requirements}")
    print("Snappix installer: installing dependencies...")
    _run_uv(
        project_dir,
        binary,
        [
            "pip",
            "install",
            "-r",
            str(requirements),
            "--python",
            str(venv_py),
        ],
    )
    _verify_qt_multimedia(venv_py)


def _verify_qt_multimedia(venv_py: Path) -> None:
    """
    Fails install early when QtMultimedia is missing from the venv.

    Args:
        venv_py: Virtualenv Python interpreter.

    Returns:
        None

    Raises:
        RuntimeError: When ``PySide6.QtMultimedia`` cannot be imported.
    """

    result = subprocess.run(
        [
            str(venv_py),
            "-c",
            "from PySide6.QtMultimedia import QMediaPlayer",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(
            "PySide6.QtMultimedia is missing after package install. "
            "Ensure PySide6_Addons is installed. "
            f"Details: {detail or result.returncode}"
        )


def bootstrap_managed_runtime(project_dir: Path) -> int:
    """
    Ensures uv, managed Python, ``.venv``, and requirements are ready.

    Args:
        project_dir: Snappix project root.

    Returns:
        int: 0 on success, 1 on failure.
    """

    try:
        uv_path = ensure_uv(project_dir)
        install_requirements(project_dir, uv_path)
    except RuntimeError as exc:
        print(f"Snappix installer error: {exc}")
        return 1
    except OSError as exc:
        print(f"Snappix installer error: {exc}")
        return 1
    return 0
