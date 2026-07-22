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

SYSTEM_PACKAGE_MAP: dict[str, list[str]] = {
    "apt-get": ["libxcb-cursor0", "xdotool", "x11-utils", "tesseract-ocr"],
    "dnf": ["xcb-util-cursor", "xdotool", "xwininfo", "tesseract"],
    "pacman": ["xcb-util-cursor", "xdotool", "xorg-xwininfo", "tesseract"],
    "zypper": ["libxcb-cursor0", "xdotool", "xwininfo", "tesseract-ocr"],
}


def run_command(command: list[str], cwd: Path) -> int:
    """
    Runs one command and returns the exit code.

    Args:
        command: Command with arguments.
        cwd: Working directory.

    Returns:
        int: Process return code.
    """

    result = subprocess.run(command, cwd=cwd, check=False)
    return result.returncode


def detect_missing_system_dependencies() -> list[str]:
    """
    Detects missing Qt/X11 and OCR runtime dependencies.

    Returns:
        list[str]: Missing dependency keys.
    """

    missing: list[str] = []
    if find_library("xcb-cursor") is None:
        missing.append("xcb-cursor")
    if which("xdotool") is None:
        missing.append("xdotool")
    if which("xwininfo") is None:
        missing.append("xwininfo")
    if which("tesseract") is None:
        missing.append("tesseract")
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

    if os.geteuid() == 0:
        return command
    if which("sudo") is not None:
        return ["sudo", *command]
    return None


def install_system_dependencies(project_dir: Path) -> int:
    """
    Installs Linux runtime packages required for Qt.

    Args:
        project_dir: Project root directory.

    Returns:
        int: Exit code.
    """

    missing = detect_missing_system_dependencies()
    if not missing:
        return 0

    package_manager = detect_package_manager()
    packages_for_hint = SYSTEM_PACKAGE_MAP.get(package_manager or "", [])
    if os.geteuid() != 0 and not sys.stdin.isatty():
        if which("pkexec") is None:
            print("Snappix installer error: pkexec is required for automatic system package install in GUI mode.")
            print("Please install policykit-1 and retry.")
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
        )

    if package_manager is None:
        print("Snappix installer warning: no supported package manager found.")
        print("Please install xcb cursor runtime manually for your distro.")
        return 0

    packages = SYSTEM_PACKAGE_MAP[package_manager]
    print(f"Snappix installer: installing system dependencies via {package_manager}...")

    commands: list[list[str]]
    if package_manager == "apt-get":
        commands = [
            ["apt-get", "update"],
            ["apt-get", "install", "-y", *packages],
        ]
    elif package_manager == "dnf":
        commands = [["dnf", "install", "-y", *packages]]
    elif package_manager == "pacman":
        commands = [["pacman", "-Sy", "--noconfirm", *packages]]
    else:
        commands = [["zypper", "--non-interactive", "install", *packages]]

    for command in commands:
        privileged = with_privilege(command)
        if privileged is None:
            print("Snappix installer error: root/sudo permissions are required for system packages.")
            print(f"Please install manually: {' '.join(command)}")
            return 1
        command_code = run_command(privileged, project_dir)
        if command_code != 0:
            print("Snappix installer error: failed to install system packages.")
            print(f"Please run manually: {' '.join(privileged)}")
            return command_code

    if detect_missing_system_dependencies():
        print("Snappix installer error: system dependency installation did not resolve all libraries.")
        return 1
    return 0


def ensure_venv(project_dir: Path, python_bin: str) -> int:
    """
    Creates a virtual environment when missing.

    Args:
        project_dir: Project root directory.
        python_bin: Python interpreter path.

    Returns:
        int: Exit code.
    """

    venv_dir = project_dir / ".venv"
    if venv_dir.exists():
        return 0
    print("Snappix installer: creating virtual environment...")
    return run_command([python_bin, "-m", "venv", str(venv_dir)], project_dir)


def install_packages(project_dir: Path) -> int:
    """
    Installs Python packages into local virtual environment.

    Args:
        project_dir: Project root directory.

    Returns:
        int: Exit code.
    """

    venv_python = project_dir / ".venv" / "bin" / "python3"
    if not venv_python.exists():
        venv_python = project_dir / ".venv" / "bin" / "python"
    if not venv_python.exists():
        print("Snappix installer error: .venv Python executable not found.")
        return 1

    print("Snappix installer: installing dependencies...")
    upgrade_code = run_command([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"], project_dir)
    if upgrade_code != 0:
        return upgrade_code
    return run_command([str(venv_python), "-m", "pip", "install", "-r", "requirements.txt"], project_dir)


def main() -> int:
    """
    Runs the complete dependency bootstrap flow.

    Returns:
        int: Exit code.
    """

    project_dir = Path(__file__).resolve().parent

    install_system_only = "--install-system-deps-only" in sys.argv
    if install_system_only:
        return install_system_dependencies(project_dir)

    system_code = install_system_dependencies(project_dir)
    if system_code != 0:
        return system_code
    create_code = ensure_venv(project_dir, sys.executable)
    if create_code != 0:
        return create_code
    install_code = install_packages(project_dir)
    if install_code != 0:
        return install_code
    print("Snappix installer: done.")
    print("Start command: .venv/bin/python3 run.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
