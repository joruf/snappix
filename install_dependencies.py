#!/usr/bin/env python3
"""
Install Snappix dependencies in a local virtual environment.
"""

from __future__ import annotations

import os
import subprocess
import sys
from ctypes.util import find_library
from pathlib import Path
from shutil import which

from src.install_manifest import (
    record_package_manager,
    record_project_dir,
    record_system_packages_installed,
)

# Tesseract is not listed here on purpose: its winget package installs
# machine-wide and prompts for administrator rights. src/tesseract_setup.py
# installs it for the current user instead, without any prompt.
WINDOWS_WINGET_PACKAGES: dict[str, str] = {
    "ffmpeg": "Gyan.FFmpeg",
}

REQUIRED_SYSTEM_PACKAGE_MAP: dict[str, list[str]] = {
    "apt-get": [
        "libxcb-cursor0",
        "python3-tk",
        "python3-venv",
        "xdotool",
        "x11-utils",
        "tesseract-ocr",
    ],
    "dnf": [
        "xcb-util-cursor",
        "python3-tkinter",
        "xdotool",
        "xwininfo",
        "tesseract",
    ],
    "pacman": [
        "xcb-util-cursor",
        "tk",
        "xdotool",
        "xorg-xwininfo",
        "tesseract",
    ],
    "zypper": [
        "libxcb-cursor0",
        "python3-tk",
        "xdotool",
        "xwininfo",
        "tesseract-ocr",
    ],
}

RECOMMENDED_SYSTEM_PACKAGE_MAP: dict[str, list[str]] = {
    "apt-get": ["grim", "slurp", "ffmpeg"],
    "dnf": ["grim", "slurp", "ffmpeg"],
    "pacman": ["grim", "slurp", "ffmpeg"],
    "zypper": ["grim", "slurp", "ffmpeg"],
}

# Backward-compatible alias used by packaging docs and older callers.
SYSTEM_PACKAGE_MAP: dict[str, list[str]] = {
    manager: [*required, *RECOMMENDED_SYSTEM_PACKAGE_MAP.get(manager, [])]
    for manager, required in REQUIRED_SYSTEM_PACKAGE_MAP.items()
}


def run_command(
    command: list[str],
    cwd: Path,
    *,
    env: dict[str, str] | None = None,
) -> int:
    """
    Runs one command and returns the exit code.

    Args:
        command: Command with arguments.
        cwd: Working directory.
        env: Optional environment overrides.

    Returns:
        int: Process return code.
    """

    result = subprocess.run(command, cwd=cwd, check=False, env=env)
    return result.returncode


def detect_missing_system_dependencies() -> list[str]:
    """
    Detects missing required Qt/X11, OCR, and installer runtime dependencies.

    Returns:
        list[str]: Missing dependency keys.
    """

    from src.paths import is_windows

    missing: list[str] = []
    if is_windows():
        # Qt ships with PySide6 wheels on Windows; no xcb/xdotool. Tesseract is
        # deliberately absent here: the machine-wide installer behind the winget
        # package needs administrator rights, so requiring it locked out every
        # account that does not have them. OCR is offered separately, per user,
        # via --install-ocr.
        return missing
    if find_library("xcb-cursor") is None:
        missing.append("xcb-cursor")
    if which("xdotool") is None:
        missing.append("xdotool")
    if which("xwininfo") is None:
        missing.append("xwininfo")
    if which("tesseract") is None:
        missing.append("tesseract")
    try:
        import tkinter  # noqa: F401
    except ModuleNotFoundError:
        missing.append("tkinter")
    return missing


def detect_missing_recommended_dependencies() -> list[str]:
    """
    Detects missing recommended Wayland capture and video recording tools.

    Returns:
        list[str]: Missing recommended dependency keys.
    """

    from src.paths import is_windows

    missing: list[str] = []
    if not is_windows():
        if which("grim") is None:
            missing.append("grim")
        if which("slurp") is None:
            missing.append("slurp")
    if which("ffmpeg") is None:
        # Match video_recorder discovery (winget install dirs not yet on PATH).
        try:
            from src.video_recorder import has_ffmpeg

            if not has_ffmpeg():
                missing.append("ffmpeg")
        except Exception:
            missing.append("ffmpeg")
    return missing


def detect_package_manager() -> str | None:
    """
    Detects available Linux package manager.

    Returns:
        str | None: Package manager executable or None.
    """

    for manager in ("apt-get", "dnf", "pacman", "zypper"):
        if which(manager) is not None:
            return manager
    return None


def with_privilege(command: list[str]) -> list[str] | None:
    """
    Adds privilege escalation for system package installation.

    Args:
        command: Unprivileged command.

    Returns:
        list[str] | None: Privileged command or None when impossible.
    """

    if getattr(os, "geteuid", lambda: 1)() == 0:
        return command
    if which("sudo") is not None:
        return ["sudo", *command]
    return None


def _build_install_commands(package_manager: str, packages: list[str]) -> list[list[str]]:
    """
    Builds package-manager install commands for the given packages.

    Args:
        package_manager: Detected package manager name.
        packages: Package names to install.

    Returns:
        list[list[str]]: Ordered shell commands.
    """

    if not packages:
        return []
    if package_manager == "apt-get":
        return [
            ["apt-get", "update"],
            ["apt-get", "install", "-y", *packages],
        ]
    if package_manager == "dnf":
        return [["dnf", "install", "-y", *packages]]
    if package_manager == "pacman":
        return [["pacman", "-Sy", "--noconfirm", *packages]]
    return [["zypper", "--non-interactive", "install", *packages]]


def _run_package_commands(project_dir: Path, commands: list[list[str]]) -> int:
    """
    Runs privileged package-manager commands.

    Args:
        project_dir: Project root directory.
        commands: Package manager commands without privilege prefix.

    Returns:
        int: Exit code of the first failing command, otherwise 0.
    """

    for command in commands:
        privileged = with_privilege(command)
        if privileged is None:
            print(
                "Snappix installer error: root/sudo permissions are required for system packages."
            )
            print(f"Please install manually: {' '.join(command)}")
            return 1
        command_code = run_command(privileged, project_dir)
        if command_code != 0:
            print("Snappix installer error: failed to install system packages.")
            print(f"Please run manually: {' '.join(privileged)}")
            return command_code
    return 0


def _gui_mode_needs_pkexec() -> bool:
    """
    Returns whether GUI/non-interactive mode should elevate via pkexec.

    Returns:
        bool: True when not root and stdin is not a TTY.
    """

    geteuid = getattr(os, "geteuid", None)
    if geteuid is None:
        return False
    return geteuid() != 0 and not sys.stdin.isatty()


def _pkexec_env() -> dict[str, str]:
    """
    Builds an environment that keeps GUI elevation dialogs working.

    Returns:
        dict[str, str]: Environment for pkexec child processes.
    """

    env = dict(os.environ)
    for key in ("DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS"):
        value = os.environ.get(key)
        if value:
            env[key] = value
    env["PATH"] = os.environ.get("PATH", "/usr/bin:/bin")
    return env


def _elevate_system_install(project_dir: Path) -> int:
    """
    Elevates and re-runs system package installation for GUI mode.

    Args:
        project_dir: Project root directory.

    Returns:
        int: Exit code from the elevated installer.
    """

    if which("pkexec") is None:
        print(
            "Snappix installer error: pkexec is required for automatic "
            "system package install in GUI mode."
        )
        print("Please install policykit-1 and retry, or run:")
        print(f"  {sys.executable} {Path(__file__).resolve()}")
        return 1

    print("Snappix installer: requesting administrator rights via pkexec...")
    return run_command(
        [
            "pkexec",
            sys.executable,
            str(Path(__file__).resolve()),
            "--install-system-deps-only",
        ],
        project_dir,
        env=_pkexec_env(),
    )


def _install_windows_winget_packages(project_dir: Path, keys: list[str]) -> int:
    """
    Installs missing Windows tools via winget when available.

    Args:
        project_dir: Project root directory.
        keys: Dependency keys such as ``ffmpeg`` or ``tesseract``.

    Returns:
        int: 0 when all requested packages are present afterward, else 1.
    """

    if not keys:
        return 0
    if which("winget") is None:
        print(
            "Snappix installer warning: winget is not available. "
            "Install missing tools manually: "
            + ", ".join(keys)
        )
        print(
            "Snappix installer: recommended — "
            "`winget install Gyan.FFmpeg` and optionally "
            "`winget install UB-Mannheim.TesseractOCR`"
        )
        return 1

    print("Snappix installer: installing Windows packages via winget…")
    failures: list[str] = []
    for key in keys:
        package_id = WINDOWS_WINGET_PACKAGES.get(key)
        if package_id is None:
            failures.append(key)
            continue
        print(f"Snappix installer: winget install {package_id}…")
        code = run_command(
            [
                "winget",
                "install",
                "--id",
                package_id,
                "-e",
                "--accept-package-agreements",
                "--accept-source-agreements",
                "--source",
                "winget",
            ],
            project_dir,
        )
        if code != 0:
            failures.append(key)

    still_missing = [
        key
        for key in keys
        if which(key) is None
    ]
    if still_missing:
        print(
            "Snappix installer warning: still missing after winget: "
            + ", ".join(still_missing)
        )
        return 1
    if failures:
        # winget may report non-zero when already installed; tools present → OK.
        return 0
    record_package_manager("winget")
    record_system_packages_installed(
        [WINDOWS_WINGET_PACKAGES[key] for key in keys if key in WINDOWS_WINGET_PACKAGES]
    )
    return 0


def _report_windows_ocr_state(project_dir: Path) -> None:
    """
    Reports whether OCR is available and how to add it without elevation.

    Args:
        project_dir: Project root directory.

    Returns:
        None
    """

    from src.platform import has_tesseract

    if has_tesseract():
        return
    print(
        "Snappix installer: OCR (text recognition) is optional and not installed. "
        "To add it for your account only, without administrator rights, run: "
        "install.bat --install-ocr"
    )


def install_ocr_for_current_user(project_dir: Path) -> int:
    """
    Installs Tesseract for the current user, without administrator rights.

    Args:
        project_dir: Project root directory.

    Returns:
        int: 0 on success, 1 when OCR remains unavailable.
    """

    from src.paths import is_windows
    from src.platform import has_tesseract

    if has_tesseract():
        print("Snappix installer: OCR is already available.")
        return 0
    if not is_windows():
        print(
            "Snappix installer: install tesseract with your package manager, "
            "for example `sudo apt install tesseract-ocr`."
        )
        return 1

    from src.tesseract_setup import install_for_current_user

    return 0 if install_for_current_user(project_dir) else 1


def install_system_dependencies(project_dir: Path) -> int:
    """
    Installs OS runtime packages required for Qt and capture tools.

    On Linux uses apt/dnf/pacman/zypper. On Windows uses winget when present.
    Recommended tools never fail the bootstrap hard; required elevation failures
    are reported, but callers may continue with Python setup.

    Args:
        project_dir: Project root directory.

    Returns:
        int: Exit code (0 when required deps are satisfied or already present).
    """

    missing = detect_missing_system_dependencies()
    recommended_missing = detect_missing_recommended_dependencies()
    print("Snappix installer: checking system packages...")

    from src.paths import is_windows

    if is_windows():
        needed = [*missing, *recommended_missing]
        if not needed:
            print("Snappix installer: required tools are present")
            _report_windows_ocr_state(project_dir)
            return 0
        print(
            "Snappix installer: detecting missing Windows tools: "
            + ", ".join(needed)
        )
        winget_code = _install_windows_winget_packages(project_dir, needed)
        still_required = detect_missing_system_dependencies()
        if still_required:
            print(
                "Snappix installer warning: required Windows tools still missing: "
                + ", ".join(still_required)
            )
            return 1
        del winget_code
        still_recommended = detect_missing_recommended_dependencies()
        if still_recommended:
            print(
                "Snappix installer warning: recommended tools still missing: "
                + ", ".join(still_recommended)
                + ". Video recording may be limited until ffmpeg is installed."
            )
        _report_windows_ocr_state(project_dir)
        return 0

    if missing:
        print(
            "Snappix installer: detecting missing required packages: "
            + ", ".join(missing)
        )
    if recommended_missing:
        print(
            "Snappix installer: detecting missing recommended tools: "
            + ", ".join(recommended_missing)
        )
    if not missing and not recommended_missing:
        print("Snappix installer: required system packages are present")
        return 0

    package_manager = detect_package_manager()
    if package_manager is None:
        if missing:
            print("Snappix installer warning: no supported package manager found.")
            print(
                "Please install manually: xcb-cursor, xdotool, xwininfo, tesseract, "
                "and python3-tk/tkinter."
            )
            return 1
        print(
            "Snappix installer warning: recommended tools still missing: "
            + ", ".join(recommended_missing)
            + ". Wayland region capture and/or video recording may be limited."
        )
        return 0

    required_packages = list(REQUIRED_SYSTEM_PACKAGE_MAP[package_manager])
    recommended_packages = list(RECOMMENDED_SYSTEM_PACKAGE_MAP.get(package_manager, []))

    # Required deps already present: never block bootstrap on recommended tools.
    if not missing:
        if recommended_missing and not _gui_mode_needs_pkexec():
            print(
                "Snappix installer: required system packages are present; "
                "trying recommended tools without blocking setup..."
            )
            _install_packages_with_tracking(
                project_dir,
                package_manager,
                recommended_packages,
            )
        still_recommended = detect_missing_recommended_dependencies()
        if still_recommended:
            print(
                "Snappix installer warning: recommended tools still missing: "
                + ", ".join(still_recommended)
                + ". Wayland region capture and/or video recording may be limited."
            )
        return 0

    packages = [*required_packages, *recommended_packages]
    if _gui_mode_needs_pkexec():
        elevate_code = _elevate_system_install(project_dir)
        if elevate_code != 0:
            if not detect_missing_system_dependencies():
                print(
                    "Snappix installer warning: administrator prompt failed, "
                    "but required system packages are already available."
                )
                return 0
            print(
                "Snappix installer warning: system package elevation failed "
                f"(exit {elevate_code}). Continuing with Python packages; "
                "some capture/OCR features may be limited until system "
                "packages are installed."
            )
            return elevate_code
        if detect_missing_system_dependencies():
            print(
                "Snappix installer warning: system dependency installation "
                "did not resolve all required libraries."
            )
            return 1
        still_recommended = detect_missing_recommended_dependencies()
        if still_recommended:
            print(
                "Snappix installer warning: recommended tools still missing: "
                + ", ".join(still_recommended)
                + ". Wayland region capture and/or video recording may be limited."
            )
        return 0

    print(f"Snappix installer: installing system dependencies via {package_manager}...")
    install_code = _install_packages_with_tracking(project_dir, package_manager, packages)
    if install_code != 0:
        if not detect_missing_system_dependencies():
            print(
                "Snappix installer warning: package install reported an error, "
                "but required system packages are available."
            )
            return 0
        return install_code

    if detect_missing_system_dependencies():
        print(
            "Snappix installer error: system dependency installation did not resolve all libraries."
        )
        return 1
    still_recommended = detect_missing_recommended_dependencies()
    if still_recommended:
        print(
            "Snappix installer warning: recommended tools still missing: "
            + ", ".join(still_recommended)
            + ". Wayland region capture and/or video recording may be limited."
        )
    return 0


def is_system_package_installed(package_manager: str, package: str) -> bool:
    """
    Checks whether one system package is currently installed.

    Args:
        package_manager: Package manager name.
        package: Package name.

    Returns:
        bool: True when the package is installed.
    """

    if package_manager == "apt-get":
        result = subprocess.run(
            ["dpkg-query", "-W", "-f=${Status}", package],
            capture_output=True,
            text=True,
            check=False,
        )
        return "install ok installed" in result.stdout
    if package_manager in {"dnf", "zypper"}:
        result = subprocess.run(["rpm", "-q", package], capture_output=True, check=False)
        return result.returncode == 0
    if package_manager == "pacman":
        result = subprocess.run(["pacman", "-Qi", package], capture_output=True, check=False)
        return result.returncode == 0
    return False


def packages_not_installed(package_manager: str, packages: list[str]) -> list[str]:
    """
    Returns packages from one list that are not currently installed.

    Args:
        package_manager: Package manager name.
        packages: Candidate package names.

    Returns:
        list[str]: Packages absent before installation.
    """

    return [package for package in packages if not is_system_package_installed(package_manager, package)]


def _record_newly_installed_packages(
    project_dir: Path,
    package_manager: str,
    candidate_packages: list[str],
) -> None:
    """
    Records system packages that Snappix newly installed.

    Args:
        project_dir: Project root directory.
        package_manager: Package manager used for installation.
        candidate_packages: Packages attempted by this install run.

    Returns:
        None
    """

    record_project_dir(project_dir)
    record_package_manager(package_manager)
    installed_now = [
        package
        for package in candidate_packages
        if is_system_package_installed(package_manager, package)
    ]
    record_system_packages_installed(installed_now)


def _install_packages_with_tracking(
    project_dir: Path,
    package_manager: str,
    packages: list[str],
) -> int:
    """
    Installs system packages and records only newly installed ones.

    Args:
        project_dir: Project root directory.
        package_manager: Detected package manager name.
        packages: Package names to ensure are installed.

    Returns:
        int: Exit code from package installation.
    """

    missing_before = packages_not_installed(package_manager, packages)
    if not missing_before:
        return 0
    install_code = _run_package_commands(
        project_dir,
        _build_install_commands(package_manager, packages),
    )
    if install_code == 0:
        _record_newly_installed_packages(project_dir, package_manager, missing_before)
    return install_code


def ensure_venv(project_dir: Path, python_bin: str | None = None) -> int:
    """
    Creates a virtual environment via the managed uv/Python runtime.

    ``python_bin`` is ignored; Snappix always provisions CPython 3.12 through
    the project-local uv toolchain so host Python versions do not matter.

    Args:
        project_dir: Project root directory.
        python_bin: Unused; kept for call-site compatibility.

    Returns:
        int: Exit code.
    """

    del python_bin  # Host interpreter is intentionally ignored.
    from src.runtime_bootstrap import ensure_venv as ensure_managed_venv

    try:
        ensure_managed_venv(project_dir)
    except (RuntimeError, OSError) as exc:
        print(f"Snappix installer error: could not create .venv ({exc}).")
        return 1
    return 0


def install_packages(project_dir: Path) -> int:
    """
    Installs Python packages into the local virtual environment via uv.

    Args:
        project_dir: Project root directory.

    Returns:
        int: Exit code.
    """

    from src.runtime_bootstrap import install_requirements

    try:
        install_requirements(project_dir)
    except (RuntimeError, OSError) as exc:
        print(f"Snappix installer error: {exc}")
        return 1
    return 0


def bootstrap(project_dir: Path, python_bin: str | None = None) -> int:
    """
    Runs system package setup plus managed virtualenv package installation.

    Host ``python_bin`` is unused; the managed uv runtime supplies CPython 3.12.

    Args:
        project_dir: Project root directory.
        python_bin: Unused host interpreter path (API compatibility).

    Returns:
        int: Exit code (0 when Python packages are installed successfully).
    """

    del python_bin
    print("Snappix installer: checking installation requirements...")
    record_project_dir(project_dir)
    system_code = install_system_dependencies(project_dir)

    from src.runtime_bootstrap import bootstrap_managed_runtime

    runtime_code = bootstrap_managed_runtime(project_dir)
    if runtime_code != 0:
        print(
            "Snappix installer error: could not provision managed Python runtime. "
            "Check network access and retry."
        )
        return runtime_code

    from src.paths import is_windows, venv_python_path

    start_cmd = (
        str(venv_python_path(project_dir).relative_to(project_dir))
        if venv_python_path(project_dir).exists()
        else (r".venv\Scripts\python.exe run.py" if is_windows() else ".venv/bin/python3 run.py")
    )
    if not start_cmd.endswith("run.py"):
        start_cmd = f"{start_cmd} run.py"

    if system_code != 0 and detect_missing_system_dependencies():
        print(
            "Snappix installer: Python packages installed, but some required "
            "system packages are still missing: "
            + ", ".join(detect_missing_system_dependencies())
        )
        print("Snappix installer: done with warnings.")
        print(f"Start command: {start_cmd}")
        # Soft success: app can start; missing system tools degrade features.
        return 0

    print("Snappix installer: done.")
    print(f"Start command: {start_cmd}")
    return 0


def main() -> int:
    """
    Runs the complete dependency bootstrap flow.

    Returns:
        int: Exit code.
    """

    project_dir = Path(__file__).resolve().parent

    if "--install-ocr" in sys.argv:
        return install_ocr_for_current_user(project_dir)

    install_system_only = "--install-system-deps-only" in sys.argv
    if install_system_only:
        return install_system_dependencies(project_dir)
    return bootstrap(project_dir, sys.executable)


if __name__ == "__main__":
    raise SystemExit(main())
