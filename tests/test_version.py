"""
Tests for the version derived from the commit history.

Every commit is a new version, so nobody has to remember to raise a number --
and nothing may invent one either: a made-up version looks real and sends bug
reports in the wrong direction.
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.version import (
    ENVIRONMENT_VARIABLE,
    UNKNOWN,
    VERSION_FILE_NAME,
    version,
    version_string,
    write_version_file,
)


def _repository(directory: Path, subjects: list[str]) -> Path:
    """
    Builds a throwaway repository with one commit per subject.

    Args:
        directory: Directory to initialize.
        subjects: Commit subjects in order.

    Returns:
        Path: The repository directory.
    """

    def run(*arguments: str) -> None:
        """Runs one git command inside the repository."""
        subprocess.run(
            ["git", *arguments],
            cwd=directory,
            check=True,
            capture_output=True,
        )

    run("init", "-q")
    run("config", "user.email", "test@example.invalid")
    run("config", "user.name", "Test")
    for index, subject in enumerate(subjects):
        (directory / f"file{index}.txt").write_text(str(index), encoding="utf-8")
        run("add", ".")
        run("commit", "-q", "-m", subject)
    return directory


class TestDerivedFromHistory(unittest.TestCase):
    """
    Verifies how the number follows the commits.
    """

    def _version_of(self, subjects: list[str]) -> tuple[str, str]:
        """
        Returns the version a history of these subjects produces.

        Args:
            subjects: Commit subjects in order.

        Returns:
            tuple[str, str]: Name and build.
        """

        from src import version as version_module

        with TemporaryDirectory() as temporary:
            root = _repository(Path(temporary), subjects)
            with patch.dict("os.environ", {}, clear=True), patch.object(
                version_module, "project_root", return_value=root
            ):
                return version(refresh=True)

    def test_the_build_counts_every_commit(self) -> None:
        """
        Ensures the number changes with every commit, as asked.
        """

        _name, build = self._version_of(["Initial commit", "Fix a thing", "Add a thing"])
        self.assertEqual(build, "3")

    def test_a_feature_commit_raises_the_minor(self) -> None:
        """
        Ensures adding something is visible in the number.
        """

        name, _build = self._version_of(
            ["Initial commit", "Add capture", "Add export"]
        )
        self.assertTrue(name.startswith("0.2."), name)

    def test_a_feature_commit_resets_the_patch(self) -> None:
        """
        Ensures the patch counts changes *since* the last feature round.
        """

        name, _build = self._version_of(
            ["Initial commit", "Fix one", "Add capture", "Fix two", "Fix three"]
        )
        self.assertEqual(name, "0.1.2")

    def test_non_feature_commits_only_raise_the_patch(self) -> None:
        """
        Ensures a fix does not claim to be a feature round.
        """

        name, _build = self._version_of(["Add capture", "Fix one", "Keep two"])
        self.assertEqual(name, "0.1.2")

    def test_the_classification_ignores_capitalisation(self) -> None:
        """
        Ensures the rule does not depend on how a subject happens to be typed.
        """

        name, _build = self._version_of(["add capture", "ADD export"])
        self.assertTrue(name.startswith("0.2."), name)

    def test_major_stays_at_zero_until_a_release(self) -> None:
        """
        Ensures nothing claims to be 1.0 on its own.
        """

        name, _build = self._version_of(["Add one", "Add two", "Add three"])
        self.assertTrue(name.startswith("0."), name)


class TestSources(unittest.TestCase):
    """
    Verifies which source wins, and what happens without any.
    """

    def test_the_environment_wins(self) -> None:
        """
        Ensures a run can be pinned for a test or a one-off.
        """

        with patch.dict("os.environ", {ENVIRONMENT_VARIABLE: "9.9.9 42"}):
            self.assertEqual(version(refresh=True), ("9.9.9", "42"))

    def test_a_packaged_copy_reads_the_written_file(self) -> None:
        """
        Ensures a package without the history still knows its version.
        """

        from src import version as version_module

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / VERSION_FILE_NAME).write_text("1.2.3 77\n", encoding="utf-8")
            with patch.dict("os.environ", {}, clear=True), patch.object(
                version_module, "project_root", return_value=root
            ):
                self.assertEqual(version(refresh=True), ("1.2.3", "77"))

    def test_nothing_found_says_so_instead_of_inventing(self) -> None:
        """
        Ensures no made-up number is ever reported.

        An invented version looks real, so a bug report against it points at a
        state that never existed.
        """

        from src import version as version_module

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.dict("os.environ", {}, clear=True), patch.object(
                version_module, "project_root", return_value=root
            ):
                name, build = version(refresh=True)

        self.assertEqual(name, UNKNOWN)
        self.assertEqual(build, "")
        self.assertNotIn("0.0.0", name)

    def test_the_written_file_can_be_read_back(self) -> None:
        """
        Ensures packaging and reading agree on the format.
        """

        from src import version as version_module

        with patch.dict("os.environ", {ENVIRONMENT_VARIABLE: "2.5.1 90"}):
            with TemporaryDirectory() as temporary:
                root = Path(temporary)
                written = write_version_file(root)
                self.assertEqual(written.read_text(encoding="utf-8").strip(), "2.5.1 90")

                with patch.dict("os.environ", {}, clear=True), patch.object(
                    version_module, "project_root", return_value=root
                ):
                    self.assertEqual(version(refresh=True), ("2.5.1", "90"))


class TestDisplay(unittest.TestCase):
    """
    Verifies how the version reads.
    """

    def test_name_and_build_are_shown_together(self) -> None:
        """
        Ensures the build number is visible, since that is what identifies the
        exact commit.
        """

        with patch.dict("os.environ", {ENVIRONMENT_VARIABLE: "0.37.8 124"}):
            self.assertEqual(version_string(refresh=True), "0.37.8 (124)")

    def test_an_unknown_version_is_not_dressed_up(self) -> None:
        """
        Ensures nothing shows an empty build as a real one.
        """

        with patch.dict("os.environ", {ENVIRONMENT_VARIABLE: "0.1.0"}):
            self.assertEqual(version_string(refresh=True), "0.1.0")

    def test_this_checkout_reports_a_real_version(self) -> None:
        """
        Ensures the project itself is not sitting on "unknown".
        """

        with patch.dict("os.environ", {}, clear=True):
            name, build = version(refresh=True)

        self.assertNotEqual(name, UNKNOWN)
        self.assertTrue(build.isdigit(), build)


if __name__ == "__main__":
    unittest.main()
