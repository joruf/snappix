"""
Tests for the GitHub update check.
"""

from __future__ import annotations

import subprocess
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from src import updater


class RepositorySlugTests(unittest.TestCase):
    """
    Class RepositorySlugTests

    Covers deriving owner/name from the configured repository URL.
    """

    def test_plain_github_url(self) -> None:
        """
        Returns:
            None
        """

        self.assertEqual(updater.repository_slug("https://github.com/joruf/snappix"), "joruf/snappix")

    def test_git_suffix_and_trailing_slash_are_stripped(self) -> None:
        """
        Returns:
            None
        """

        self.assertEqual(updater.repository_slug("https://github.com/a/b.git"), "a/b")
        self.assertEqual(updater.repository_slug("https://github.com/a/b/"), "a/b")

    def test_non_github_url_yields_nothing(self) -> None:
        """
        Returns:
            None
        """

        self.assertEqual(updater.repository_slug("https://gitlab.com/a/b"), "")

    def test_configured_url_resolves(self) -> None:
        """
        Returns:
            None
        """

        self.assertTrue(updater.repository_slug())


class CheckTests(unittest.TestCase):
    """
    Class CheckTests

    Covers the check reporting failures instead of raising.
    """

    def test_network_failure_is_reported_not_raised(self) -> None:
        """
        A missing network connection must never take the app down.

        Returns:
            None
        """

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
            info = updater.check()
        self.assertFalse(info.available)
        self.assertIn("offline", info.error)

    def test_non_github_repository_is_reported(self) -> None:
        """
        Returns:
            None
        """

        with patch.object(updater, "repository_slug", return_value=""):
            info = updater.check()
        self.assertTrue(info.error)
        self.assertFalse(info.available)

    def test_matching_commit_means_no_update(self) -> None:
        """
        Returns:
            None
        """

        sha = "a" * 40
        with patch.object(updater, "local_commit", return_value=sha), patch.object(
            updater, "_fetch_head", return_value=(sha, "some message")
        ):
            info = updater.check()
        self.assertFalse(info.available)

    def test_differing_commit_means_an_update(self) -> None:
        """
        Returns:
            None
        """

        with patch.object(updater, "local_commit", return_value="a" * 40), patch.object(
            updater, "_fetch_head", return_value=("b" * 40, "newer work")
        ):
            info = updater.check()
        self.assertTrue(info.available)
        self.assertEqual(info.summary, "newer work")

    def test_unknown_local_commit_never_claims_an_update(self) -> None:
        """
        Without a local commit there is nothing to compare, so claiming an
        update would mean offering to overwrite an unknown installation.

        Returns:
            None
        """

        with patch.object(updater, "local_commit", return_value=""), patch.object(
            updater, "_fetch_head", return_value=("b" * 40, "")
        ):
            info = updater.check()
        self.assertFalse(info.available)


class ApplyGitTests(unittest.TestCase):
    """
    Class ApplyGitTests

    Covers the git path refusing to discard local work.
    """

    def test_dirty_tree_is_refused(self) -> None:
        """
        Returns:
            None
        """

        with patch.object(updater, "_run", return_value=(0, " M src/foo.py\n")):
            success, message = updater._apply_git(Path("/tmp"))
        self.assertFalse(success)
        self.assertIn("local changes", message)

    def test_failed_status_is_refused(self) -> None:
        """
        Returns:
            None
        """

        with patch.object(updater, "_run", return_value=(128, "not a repository")):
            success, _ = updater._apply_git(Path("/tmp"))
        self.assertFalse(success)

    def test_clean_tree_pulls_fast_forward_only(self) -> None:
        """
        Returns:
            None
        """

        calls: list[list[str]] = []

        def fake_run(command, cwd, timeout=60.0):
            calls.append(command)
            # A clean tree means status prints nothing; only the pull talks.
            if command[:2] == ["git", "status"]:
                return (0, "")
            return (0, "Fast-forward")

        with patch.object(updater, "_run", side_effect=fake_run):
            success, _ = updater._apply_git(Path("/tmp"))

        self.assertTrue(success)
        self.assertIn(["git", "pull", "--ff-only"], calls)


class ArchiveKeepTests(unittest.TestCase):
    """
    Class ArchiveKeepTests

    Covers user state surviving an archive update.
    """

    def test_user_state_is_never_overwritten(self) -> None:
        """
        Returns:
            None
        """

        for name in (".git", "config.json"):
            self.assertIn(name, updater._KEEP)


class RunTests(unittest.TestCase):
    """
    Class RunTests

    Covers the subprocess helper swallowing process failures.
    """

    def test_missing_binary_is_reported_not_raised(self) -> None:
        """
        Returns:
            None
        """

        with patch("subprocess.run", side_effect=OSError("no git")):
            code, output = updater._run(["git", "status"], Path("/tmp"))
        self.assertEqual(code, 1)
        self.assertIn("no git", output)

    def test_timeout_is_reported_not_raised(self) -> None:
        """
        Returns:
            None
        """

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 1)):
            code, _ = updater._run(["git", "status"], Path("/tmp"))
        self.assertEqual(code, 1)


class RestartCommandTests(unittest.TestCase):
    """
    Class RestartCommandTests

    Covers the relaunch command pointing at this installation.
    """

    def test_command_targets_run_py(self) -> None:
        """
        Returns:
            None
        """

        command = updater.restart_command()
        self.assertEqual(len(command), 2)
        self.assertTrue(command[1].endswith("run.py"))


if __name__ == "__main__":
    unittest.main()
