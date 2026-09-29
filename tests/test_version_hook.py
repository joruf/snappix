"""
Tests for the commit hook that keeps the ``VERSION`` file current.

The hook runs against a real throwaway repository: a hook that only looks
right on paper is exactly the kind that silently stops writing the file.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import install_dependencies

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HOOK = PROJECT_ROOT / ".githooks" / "post-commit"


def _git(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """
    Runs one git command in ``root``.

    Args:
        root: Repository directory.
        *arguments: Arguments after ``git``.

    Returns:
        subprocess.CompletedProcess[str]: The finished command.
    """

    environment = {
        key: value for key, value in os.environ.items() if key != "SNAPPIX_VERSION"
    }
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )


def _checkout_with_hook(root: Path, *, with_version_module: bool = True) -> Path:
    """
    Builds a repository laid out like Snappix, with the hook activated.

    Args:
        root: Directory to initialize.
        with_version_module: False to leave ``src/version.py`` out.

    Returns:
        Path: The repository directory.
    """

    (root / ".githooks").mkdir()
    shutil.copy2(HOOK, root / ".githooks" / "post-commit")
    if with_version_module:
        (root / "src").mkdir()
        shutil.copy2(PROJECT_ROOT / "src" / "version.py", root / "src" / "version.py")
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "core.hooksPath", ".githooks")
    return root


def _commit(root: Path, subject: str) -> None:
    """
    Adds one file and commits it.

    Args:
        root: Repository directory.
        subject: Commit subject.
    """

    index = len(list(root.glob("file*.txt")))
    (root / f"file{index}.txt").write_text(str(index), encoding="utf-8")
    _git(root, "add", "file%d.txt" % index)
    _git(root, "commit", "-q", "-m", subject)


class TestPostCommitHook(unittest.TestCase):
    """
    Verifies the hook as git runs it.
    """

    def test_the_hook_is_executable(self) -> None:
        """
        Ensures git will run it at all; a non-executable hook is skipped silently.
        """

        self.assertTrue(os.access(HOOK, os.X_OK))

    def test_every_commit_writes_the_file(self) -> None:
        """
        Ensures the file follows each commit without anyone starting Snappix.
        """

        with TemporaryDirectory() as temporary:
            root = _checkout_with_hook(Path(temporary))
            _commit(root, "Add capture")
            first = (root / "VERSION").read_text(encoding="utf-8").split()
            _commit(root, "Fix one")
            second = (root / "VERSION").read_text(encoding="utf-8").split()
            head = _git(root, "rev-parse", "--short", "HEAD").stdout.strip()

        self.assertEqual(first[:2], ["0.1.0", "1"])
        self.assertEqual(second[:2], ["0.1.1", "2"])
        self.assertEqual(second[2], head)

    def test_a_broken_hook_never_fails_the_commit(self) -> None:
        """
        Ensures the version file is best effort and never blocks a commit.
        """

        with TemporaryDirectory() as temporary:
            root = _checkout_with_hook(Path(temporary), with_version_module=False)
            _commit(root, "Add capture")
            count = _git(root, "rev-list", "--count", "HEAD").stdout.strip()

        self.assertEqual(count, "1")

    def test_the_file_is_not_checked_in(self) -> None:
        """
        Ensures a derived file cannot go stale in the repository.
        """

        done = subprocess.run(
            ["git", "check-ignore", "-q", "VERSION"],
            cwd=PROJECT_ROOT,
            check=False,
        )
        self.assertEqual(done.returncode, 0)


class TestInstallerActivatesHook(unittest.TestCase):
    """
    Verifies the installer turns the hook on for a checkout.
    """

    def _hooks_path(self, root: Path) -> str:
        """
        Reads ``core.hooksPath`` of ``root``.

        Args:
            root: Repository directory.

        Returns:
            str: The configured value, empty when unset.
        """

        done = subprocess.run(
            ["git", "-C", str(root), "config", "--get", "core.hooksPath"],
            capture_output=True,
            text=True,
            check=False,
        )
        return done.stdout.strip()

    def test_a_checkout_gets_the_hook(self) -> None:
        """
        Ensures nobody has to remember the git config line.
        """

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".githooks").mkdir()
            _git(root, "init", "-q")
            self.assertTrue(install_dependencies.enable_version_hook(root))
            self.assertEqual(self._hooks_path(root), ".githooks")

    def test_an_own_hooks_path_is_left_alone(self) -> None:
        """
        Ensures somebody's own hooks are not silently switched off.
        """

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".githooks").mkdir()
            _git(root, "init", "-q")
            _git(root, "config", "core.hooksPath", "my-hooks")
            self.assertFalse(install_dependencies.enable_version_hook(root))
            self.assertEqual(self._hooks_path(root), "my-hooks")

    def test_a_copy_without_history_is_skipped(self) -> None:
        """
        Ensures a package folder is not turned into something it is not.
        """

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".githooks").mkdir()
            self.assertFalse(install_dependencies.enable_version_hook(root))

    def test_the_install_run_activates_it(self) -> None:
        """
        Ensures the activation is wired into the installer, not only defined.
        """

        with patch.object(install_dependencies, "enable_version_hook") as enable, patch.object(
            install_dependencies, "record_project_dir"
        ), patch.object(
            install_dependencies, "install_system_dependencies", return_value=0
        ), patch(
            "src.runtime_bootstrap.bootstrap_managed_runtime", return_value=1
        ):
            install_dependencies.bootstrap(PROJECT_ROOT)

        enable.assert_called_once_with(PROJECT_ROOT)


if __name__ == "__main__":
    unittest.main()
