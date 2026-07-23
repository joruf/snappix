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
    "apt-get": ["grim", "slurp"],
    "dnf": ["grim", "slurp"],
    "pacman": ["grim", "slurp"],
    "zypper": ["grim", "slurp"],
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

    missing: list[str] = []
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
    Detects missing recommended Wayland capture tools.

    Returns:
        list[str]: Missing recommended dependency keys.
    """

    missing: list[str] = []
    if which("grim") is None:
        missing.append("grim")
    if which("slurp") is None:
        missing.append("slurp")
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

    return os.geteuid() != 0 and not sys.stdin.isatty()


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


def install_system_dependencies(project_dir: Path) -> int:
    """
    Installs Linux runtime packages required for Qt and capture tools.

    Recommended Wayland tools never fail the bootstrap. Required package
    elevation failures are reported, but callers may continue with Python setup.

    Args:
        project_dir: Project root directory.

    Returns:
        int: Exit code (0 when required deps are satisfied or already present).
    """

    missing = detect_missing_system_dependencies()
    recommended_missing = detect_missing_recommended_dependencies()
    print("Snappix installer: checking system packages...")
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
            + ". Wayland region capture may be limited."
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
            _run_package_commands(
                project_dir,
                _build_install_commands(package_manager, recommended_packages),
            )
        still_recommended = detect_missing_recommended_dependencies()
        if still_recommended:
            print(
                "Snappix installer warning: recommended tools still missing: "
                + ", ".join(still_recommended)
                + ". Wayland region capture may be limited."
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
                + ". Wayland region capture may be limited."
            )
        return 0

    print(f"Snappix installer: installing system dependencies via {package_manager}...")
    install_code = _run_package_commands(
        project_dir,
        _build_install_commands(package_manager, packages),
    )
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
            + ". Wayland region capture may be limited."
        )
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
    upgrade_code = run_command(
        [str(venv_python), "-m", "pip", "install", "--upgrade", "pip"],
        project_dir,
    )
    if upgrade_code != 0:
        return upgrade_code
    return run_command(
        [str(venv_python), "-m", "pip", "install", "-r", "requirements.txt"],
        project_dir,
    )


def bootstrap(project_dir: Path, python_bin: str | None = None) -> int:
    """
    Runs system package setup plus local virtualenv package installation.

    Args:
        project_dir: Project root directory.
        python_bin: Python interpreter used to create the virtualenv.

    Returns:
        int: Exit code (0 when Python packages are installed successfully).
    """

    interpreter = python_bin or sys.executable
    print("Snappix installer: checking installation requirements...")
    system_code = install_system_dependencies(project_dir)
    create_code = ensure_venv(project_dir, interpreter)
    if create_code != 0:
        print(
            "Snappix installer error: could not create .venv. "
            "Install python3-venv and retry."
        )
        return create_code
    install_code = install_packages(project_dir)
    if install_code != 0:
        return install_code

    if system_code != 0 and detect_missing_system_dependencies():
        print(
            "Snappix installer: Python packages installed, but some required "
            "system packages are still missing: "
            + ", ".join(detect_missing_system_dependencies())
        )
        print("Snappix installer: done with warnings.")
        print("Start command: .venv/bin/python3 run.py")
        # Soft success: app can start; missing system tools degrade features.
        return 0

    print("Snappix installer: done.")
    print("Start command: .venv/bin/python3 run.py")
    return 0


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
    return bootstrap(project_dir, sys.executable)


if __name__ == "__main__":
    raise SystemExit(main())
