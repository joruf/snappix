"""
Install manifest for Snappix dependency and integration tracking.

Records only artifacts that Snappix created or installed so uninstall can remove
them without touching pre-existing system packages or user files.
"""

from __future__ import annotations

import json
import os
from src.py_compat import dataclass, field, is_relative_to
from pathlib import Path


MANIFEST_VERSION = 1


def manifest_path() -> Path:
    """
    Returns the install manifest file path.

    Returns:
        Path: Manifest JSON path under the user config directory.
    """

    from src.paths import user_config_dir

    return user_config_dir() / "install-manifest.json"

def _normalize_path(path: str | Path) -> str:
    """
    Stores one path in a stable, home-relative string form when possible.

    Args:
        path: Absolute or relative path.

    Returns:
        str: Normalized path string.
    """

    expanded = Path(path).expanduser()
    try:
        resolved = expanded.resolve()
    except OSError:
        resolved = expanded
    home = Path.home()
    if is_relative_to(resolved, home):
        return str(resolved.relative_to(home))
    return str(resolved)


def _expand_manifest_path(path: str) -> Path:
    """
    Expands one manifest path back to an absolute filesystem path.

    Args:
        path: Stored manifest path.

    Returns:
        Path: Absolute path.
    """

    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate
    return Path.home() / candidate


@dataclass(slots=True)
class InstallManifest:
    """
    Describes Snappix-owned install artifacts for safe uninstall.

    Attributes:
        version: Manifest schema version.
        project_dir: Snappix project root used during install.
        package_manager: Package manager used for system installs.
        system_packages_installed: System packages Snappix installed.
        venv_created: True when Snappix created the project .venv.
        runtime_created: True when Snappix created ``.snappix-runtime``.
        user_files: User-level files Snappix created.
    """

    version: int = MANIFEST_VERSION
    project_dir: str = ""
    package_manager: str = ""
    system_packages_installed: list[str] = field(default_factory=list)
    venv_created: bool = False
    runtime_created: bool = False
    user_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """
        Serializes the manifest to a JSON-compatible dictionary.

        Returns:
            dict: Manifest payload.
        """

        return {
            "version": self.version,
            "project_dir": self.project_dir,
            "package_manager": self.package_manager,
            "system_packages_installed": list(self.system_packages_installed),
            "venv_created": self.venv_created,
            "runtime_created": self.runtime_created,
            "user_files": list(self.user_files),
        }

    @classmethod
    def from_dict(cls, payload: dict) -> InstallManifest:
        """
        Parses one manifest dictionary.

        Args:
            payload: Stored manifest payload.

        Returns:
            InstallManifest: Parsed manifest.
        """

        packages = payload.get("system_packages_installed", [])
        files = payload.get("user_files", [])
        return cls(
            version=int(payload.get("version", MANIFEST_VERSION)),
            project_dir=str(payload.get("project_dir", "")).strip(),
            package_manager=str(payload.get("package_manager", "")).strip(),
            system_packages_installed=[str(item).strip() for item in packages if str(item).strip()],
            venv_created=bool(payload.get("venv_created", False)),
            runtime_created=bool(payload.get("runtime_created", False)),
            user_files=[str(item).strip() for item in files if str(item).strip()],
        )


def load_manifest() -> InstallManifest | None:
    """
    Loads the install manifest when present.

    Returns:
        InstallManifest | None: Parsed manifest or None when missing.
    """

    path = manifest_path()
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    return InstallManifest.from_dict(payload)


def save_manifest(manifest: InstallManifest) -> None:
    """
    Persists the install manifest to disk.

    Args:
        manifest: Manifest to write.

    Returns:
        None
    """

    path = manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")


def _update_manifest(mutator) -> InstallManifest:
    """
    Loads, mutates, and saves the install manifest.

    Args:
        mutator: Callable receiving the manifest to update in place.

    Returns:
        InstallManifest: Updated manifest.
    """

    manifest = load_manifest() or InstallManifest()
    mutator(manifest)
    save_manifest(manifest)
    return manifest


def record_project_dir(project_dir: str | Path) -> None:
    """
    Records the Snappix project directory used for installation.

    Args:
        project_dir: Project root path.

    Returns:
        None
    """

    normalized = _normalize_path(project_dir)

    def _apply(manifest: InstallManifest) -> None:
        manifest.project_dir = normalized

    _update_manifest(_apply)


def record_package_manager(package_manager: str) -> None:
    """
    Records the package manager used for system dependency installation.

    Args:
        package_manager: Detected package manager name.

    Returns:
        None
    """

    def _apply(manifest: InstallManifest) -> None:
        manifest.package_manager = package_manager.strip()

    _update_manifest(_apply)


def record_system_packages_installed(packages: list[str]) -> None:
    """
    Appends system packages that Snappix installed to the manifest.

    Args:
        packages: Newly installed package names.

    Returns:
        None
    """

    additions = [package.strip() for package in packages if package.strip()]
    if not additions:
        return

    def _apply(manifest: InstallManifest) -> None:
        existing = set(manifest.system_packages_installed)
        for package in additions:
            if package not in existing:
                manifest.system_packages_installed.append(package)
                existing.add(package)

    _update_manifest(_apply)


def record_venv_created(project_dir: str | Path) -> None:
    """
    Marks that Snappix created the project virtual environment.

    Args:
        project_dir: Project root path.

    Returns:
        None
    """

    def _apply(manifest: InstallManifest) -> None:
        manifest.project_dir = manifest.project_dir or _normalize_path(project_dir)
        manifest.venv_created = True

    _update_manifest(_apply)


def record_runtime_created(project_dir: str | Path) -> None:
    """
    Marks that Snappix created the managed ``.snappix-runtime`` toolchain.

    Args:
        project_dir: Project root path.

    Returns:
        None
    """

    def _apply(manifest: InstallManifest) -> None:
        manifest.project_dir = manifest.project_dir or _normalize_path(project_dir)
        manifest.runtime_created = True

    _update_manifest(_apply)


def record_user_file(path: str | Path) -> None:
    """
    Records one user-level file created by Snappix.

    Args:
        path: Created file path.

    Returns:
        None
    """

    normalized = _normalize_path(path)

    def _apply(manifest: InstallManifest) -> None:
        if normalized not in manifest.user_files:
            manifest.user_files.append(normalized)

    _update_manifest(_apply)


def clear_manifest() -> None:
    """
    Removes the install manifest file.

    Returns:
        None
    """

    path = manifest_path()
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def manifest_user_file_paths(manifest: InstallManifest) -> list[Path]:
    """
    Resolves user file paths stored in one manifest.

    Args:
        manifest: Install manifest.

    Returns:
        list[Path]: Absolute file paths.
    """

    return [_expand_manifest_path(path) for path in manifest.user_files]


def manifest_project_dir(manifest: InstallManifest) -> Path | None:
    """
    Resolves the project directory stored in one manifest.

    Args:
        manifest: Install manifest.

    Returns:
        Path | None: Project root or None when unavailable.
    """

    if not manifest.project_dir.strip():
        return None
    return _expand_manifest_path(manifest.project_dir)


def manifest_venv_dir(manifest: InstallManifest) -> Path | None:
    """
    Resolves the project virtual environment directory when Snappix created it.

    Args:
        manifest: Install manifest.

    Returns:
        Path | None: `.venv` path or None.
    """

    project_dir = manifest_project_dir(manifest)
    if project_dir is None or not manifest.venv_created:
        return None
    return project_dir / ".venv"


def manifest_runtime_dir(manifest: InstallManifest) -> Path | None:
    """
    Resolves the managed runtime directory when Snappix created it.

    Args:
        manifest: Install manifest.

    Returns:
        Path | None: ``.snappix-runtime`` path or None.
    """

    project_dir = manifest_project_dir(manifest)
    if project_dir is None or not manifest.runtime_created:
        return None
    from src.runtime_bootstrap import RUNTIME_DIRNAME

    return project_dir / RUNTIME_DIRNAME
