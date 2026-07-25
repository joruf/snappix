#!/usr/bin/env python3
"""
Remove Snappix-owned dependencies and integration files.

Only artifacts recorded in the install manifest are removed. Pre-existing system
packages and files created by other applications are left untouched.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from shutil import which

import install_dependencies as installer
from src.install_manifest import (
    InstallManifest,
    clear_manifest,
    load_manifest,
    manifest_project_dir,
    manifest_user_file_paths,
    manifest_venv_dir,
)


def run_command(command: list[str], *, cwd: Path | None = None) -> int:
    """
    Runs one command and returns its exit code.

    Args:
        command: Command with arguments.
        cwd: Optional working directory.

    Returns:
        int: Process return code.
    """

    result = subprocess.run(command, cwd=cwd, check=False)
    return result.returncode


def with_privilege(command: list[str]) -> list[str] | None:
    """
    Adds privilege escalation when required for system package removal.

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


def is_system_package_installed(package_manager: str, package: str) -> bool:
    """
    Checks whether one system package is currently installed.

    Args:
        package_manager: Package manager name.
        package: Package name.

    Returns:
        bool: True when the package is installed.
    """

    return installer.is_system_package_installed(package_manager, package)


def _apt_packages_marked_for_removal(package: str) -> set[str]:
    """
    Returns packages apt would remove when uninstalling one package.

    Args:
        package: Package name.

    Returns:
        set[str]: Packages included in a simulated removal.
    """

    result = subprocess.run(
        ["apt-get", "-s", "remove", package],
        capture_output=True,
        text=True,
        check=False,
    )
    marked: set[str] = set()
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("Remv "):
            parts = stripped.split()
            if len(parts) >= 2:
                marked.add(parts[1])
    return marked


def _apt_package_is_auto(package: str) -> bool:
    """
    Indicates whether apt marks one package as automatically installed.

    Args:
        package: Package name.

    Returns:
        bool: True when apt marks the package as auto-installed.
    """

    result = subprocess.run(
        ["apt-mark", "showauto", package],
        capture_output=True,
        text=True,
        check=False,
    )
    return package in {line.strip() for line in result.stdout.splitlines() if line.strip()}


def can_safely_remove_system_package(
    package_manager: str,
    package: str,
    installed_by_snappix: set[str],
) -> bool:
    """
    Checks whether removing one package would stay within Snappix-owned artifacts.

    Args:
        package_manager: Package manager name.
        package: Candidate package to remove.
        installed_by_snappix: Packages recorded as installed by Snappix.

    Returns:
        bool: True when removal appears safe.
    """

    if package not in installed_by_snappix:
        return False
    if not is_system_package_installed(package_manager, package):
        return False

    if package_manager == "apt-get":
        marked = _apt_packages_marked_for_removal(package)
        if package not in marked:
            return False
        extra = marked - installed_by_snappix
        return all(_apt_package_is_auto(extra_package) for extra_package in extra)

    if package_manager == "dnf":
        result = subprocess.run(
            ["dnf", "remove", "--assumeno", package],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    if package_manager == "pacman":
        result = subprocess.run(
            ["pacman", "-R", "--print", package],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    if package_manager == "zypper":
        result = subprocess.run(
            ["zypper", "--non-interactive", "remove", "--dry-run", package],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    return False


def _build_remove_commands(package_manager: str, packages: list[str]) -> list[list[str]]:
    """
    Builds package-manager removal commands.

    Args:
        package_manager: Package manager name.
        packages: Packages to remove.

    Returns:
        list[list[str]]: Ordered removal commands.
    """

    if not packages:
        return []
    if package_manager == "apt-get":
        return [["apt-get", "remove", "-y", *packages], ["apt-get", "autoremove", "-y"]]
    if package_manager == "dnf":
        return [["dnf", "remove", "-y", *packages]]
    if package_manager == "pacman":
        return [["pacman", "-R", "--noconfirm", *packages]]
    return [["zypper", "--non-interactive", "remove", "-y", *packages]]


def remove_system_packages(manifest: InstallManifest) -> tuple[list[str], list[str]]:
    """
    Removes Snappix-installed system packages when safe.

    Args:
        manifest: Install manifest.

    Returns:
        tuple[list[str], list[str]]: Removed packages and skipped packages.
    """

    package_manager = manifest.package_manager.strip()
    owned = set(manifest.system_packages_installed)
    if not package_manager or not owned:
        return [], []

    removable: list[str] = []
    skipped: list[str] = []
    for package in reversed(manifest.system_packages_installed):
        if can_safely_remove_system_package(package_manager, package, owned):
            removable.append(package)
        elif is_system_package_installed(package_manager, package):
            skipped.append(package)

    if not removable:
        return [], skipped

    for command in _build_remove_commands(package_manager, removable):
        privileged = with_privilege(command)
        if privileged is None:
            print("Snappix uninstaller error: sudo is required to remove system packages.")
            return [], list(owned)
        if run_command(privileged) != 0:
            print(f"Snappix uninstaller warning: command failed: {' '.join(privileged)}")
            return [], list(owned)

    removed = [package for package in removable if not is_system_package_installed(package_manager, package)]
    still_installed = set(owned) - set(removed)
    skipped.extend(
        package
        for package in manifest.system_packages_installed
        if package in still_installed and package not in skipped
    )
    return removed, skipped


def remove_user_files(manifest: InstallManifest) -> list[Path]:
    """
    Removes user-level files recorded in the manifest.

    Args:
        manifest: Install manifest.

    Returns:
        list[Path]: Removed file paths.
    """

    removed: list[Path] = []
    for path in manifest_user_file_paths(manifest):
        try:
            if path.is_file() or path.is_symlink():
                path.unlink()
                removed.append(path)
        except OSError as exc:
            print(f"Snappix uninstaller warning: could not remove {path}: {exc}")
    return removed


def remove_virtual_environment(manifest: InstallManifest) -> Path | None:
    """
    Removes the project virtual environment when Snappix created it.

    Args:
        manifest: Install manifest.

    Returns:
        Path | None: Removed `.venv` directory or None.
    """

    venv_dir = manifest_venv_dir(manifest)
    if venv_dir is None or not venv_dir.exists():
        return None
    try:
        shutil.rmtree(venv_dir)
    except OSError as exc:
        print(f"Snappix uninstaller warning: could not remove {venv_dir}: {exc}")
        return None
    return venv_dir


def remove_initialized_marker(manifest: InstallManifest) -> Path | None:
    """
    Removes the first-run marker in the project directory.

    Args:
        manifest: Install manifest.

    Returns:
        Path | None: Removed marker path or None.
    """

    project_dir = manifest_project_dir(manifest)
    if project_dir is None:
        return None
    marker = project_dir / ".initialized"
    try:
        if marker.is_file():
            marker.unlink()
            return marker
    except OSError as exc:
        print(f"Snappix uninstaller warning: could not remove {marker}: {exc}")
    return None


def remove_user_config(*, assume_yes: bool) -> Path | None:
    """
    Optionally removes the Snappix user configuration directory.

    Args:
        assume_yes: Skip confirmation when True.

    Returns:
        Path | None: Removed config directory or None.
    """

    config_dir = Path.home() / ".config" / "snappix"
    config_file = config_dir / "config.json"
    if not config_file.is_file():
        return None
    if not assume_yes:
        answer = input("Remove Snappix user settings (~/.config/snappix/config.json)? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            return None
    try:
        config_file.unlink()
        if config_dir.is_dir() and not any(config_dir.iterdir()):
            config_dir.rmdir()
    except OSError as exc:
        print(f"Snappix uninstaller warning: could not remove config: {exc}")
        return None
    return config_file


def uninstall(
    *,
    assume_yes: bool = False,
    remove_config: bool = False,
) -> int:
    """
    Removes Snappix-owned install artifacts.

    Args:
        assume_yes: Skip interactive confirmation.
        remove_config: Also remove user settings when True.

    Returns:
        int: Exit code.
    """

    manifest = load_manifest()
    if manifest is None:
        print("Snappix uninstaller: no install manifest found.")
        print("Nothing recorded to remove. Delete the Snappix folder manually if needed.")
        return 1

    if not assume_yes:
        print("Snappix uninstaller will remove only artifacts installed by Snappix:")
        if manifest.system_packages_installed:
            print("  System packages:", ", ".join(manifest.system_packages_installed))
        if manifest.venv_created:
            print("  Virtual environment:", manifest_venv_dir(manifest))
        if manifest.user_files:
            print("  User files:", ", ".join(manifest.user_files))
        answer = input("Continue? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("Snappix uninstaller: cancelled.")
            return 1

    removed_packages, skipped_packages = remove_system_packages(manifest)
    if removed_packages:
        print("Snappix uninstaller: removed system packages:", ", ".join(removed_packages))
    if skipped_packages:
        print(
            "Snappix uninstaller: kept system packages still needed elsewhere:",
            ", ".join(skipped_packages),
        )

    removed_files = remove_user_files(manifest)
    if removed_files:
        print("Snappix uninstaller: removed user files:", ", ".join(str(path) for path in removed_files))

    removed_venv = remove_virtual_environment(manifest)
    if removed_venv is not None:
        print(f"Snappix uninstaller: removed virtual environment: {removed_venv}")

    removed_marker = remove_initialized_marker(manifest)
    if removed_marker is not None:
        print(f"Snappix uninstaller: removed first-run marker: {removed_marker}")

    if remove_config:
        removed_config = remove_user_config(assume_yes=assume_yes)
        if removed_config is not None:
            print(f"Snappix uninstaller: removed user settings: {removed_config}")

    clear_manifest()
    print("Snappix uninstaller: done.")
    return 0


def main() -> int:
    """
    Runs the Snappix uninstall flow from the command line.

    Returns:
        int: Exit code.
    """

    parser = argparse.ArgumentParser(
        description="Remove Snappix dependencies and integration files installed by Snappix.",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Do not ask for confirmation.",
    )
    parser.add_argument(
        "--remove-config",
        action="store_true",
        help="Also remove ~/.config/snappix/config.json.",
    )
    args = parser.parse_args()
    return uninstall(assume_yes=args.yes, remove_config=args.remove_config)


if __name__ == "__main__":
    raise SystemExit(main())
