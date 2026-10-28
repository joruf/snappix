"""
Tests for the index of capture files Snappix created.

The index decides which files come back as tabs and, above all, which files may
be deleted. The second job is the one that must never go wrong.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.capture_files import (
    INDEX_FILE_NAME,
    KIND_IMAGE,
    KIND_VIDEO,
    delete_capture,
    index_path,
    is_registered,
    register_capture,
    registered_captures,
    unregister_capture,
)


def _file(directory: str, name: str, content: bytes = b"x") -> Path:
    """
    Creates a file in a temporary folder.

    Args:
        directory: Folder path.
        name: File name.
        content: File content.

    Returns:
        Path: The created file.
    """

    path = Path(directory) / name
    path.write_bytes(content)
    return path


class TestRegistering(unittest.TestCase):
    """
    Verifies how files enter and leave the index.
    """

    def test_a_registered_file_is_listed_with_its_details(self) -> None:
        """
        Ensures kind and recovery project travel with the entry.
        """

        with TemporaryDirectory() as directory:
            shot = _file(directory, "a.png")
            self.assertTrue(register_capture(shot, KIND_IMAGE, "/work/tab-1.sfp"))
            entries = registered_captures(directory)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].path, shot)
        self.assertEqual(entries[0].kind, KIND_IMAGE)
        self.assertEqual(entries[0].recovery_path, "/work/tab-1.sfp")

    def test_registering_twice_updates_instead_of_duplicating(self) -> None:
        """
        Ensures a restored tab does not add its file a second time.
        """

        with TemporaryDirectory() as directory:
            shot = _file(directory, "a.png")
            register_capture(shot, KIND_IMAGE, "/old.sfp")
            register_capture(shot, KIND_IMAGE, "/new.sfp")
            entries = registered_captures(directory)

        self.assertEqual([entry.recovery_path for entry in entries], ["/new.sfp"])

    def test_unregistering_keeps_the_file(self) -> None:
        """
        Ensures letting go of a capture does not delete it.
        """

        with TemporaryDirectory() as directory:
            shot = _file(directory, "a.png")
            register_capture(shot)
            self.assertTrue(unregister_capture(shot))
            self.assertTrue(shot.is_file())
            self.assertEqual(registered_captures(directory), [])

    def test_a_file_that_vanished_is_not_listed(self) -> None:
        """
        Ensures a capture deleted by hand is not reopened as an empty tab.
        """

        with TemporaryDirectory() as directory:
            shot = _file(directory, "a.png")
            register_capture(shot)
            shot.unlink()
            self.assertEqual(registered_captures(directory), [])

    def test_the_index_goes_away_with_its_last_entry(self) -> None:
        """
        Ensures no empty index is left behind in the user's folder.
        """

        with TemporaryDirectory() as directory:
            shot = _file(directory, "a.png")
            register_capture(shot)
            self.assertTrue(index_path(directory).is_file())
            unregister_capture(shot)
            self.assertFalse(index_path(directory).exists())

    def test_a_damaged_index_reads_as_empty(self) -> None:
        """
        Ensures a corrupt index never raises into a capture.
        """

        with TemporaryDirectory() as directory:
            _file(directory, INDEX_FILE_NAME, b"{not json")
            self.assertEqual(registered_captures(directory), [])
            self.assertTrue(register_capture(_file(directory, "a.png")))
            self.assertEqual(len(registered_captures(directory)), 1)

    def test_registering_into_a_missing_folder_fails_quietly(self) -> None:
        """
        Ensures a vanished capture folder does not raise.
        """

        with TemporaryDirectory() as directory:
            self.assertFalse(register_capture(Path(directory) / "gone" / "a.png"))

    def test_a_path_in_the_index_cannot_leave_the_folder(self) -> None:
        """
        Ensures a hand-edited index cannot name a file elsewhere.
        """

        with TemporaryDirectory() as directory:
            outside = _file(directory, "outside.png")
            inner = Path(directory) / "inner"
            inner.mkdir()
            payload = {"files": [{"name": "../outside.png", "kind": KIND_IMAGE}]}
            (inner / INDEX_FILE_NAME).write_text(json.dumps(payload), encoding="utf-8")

            self.assertEqual(registered_captures(inner), [])
            self.assertFalse(delete_capture(inner / ".." / "outside.png"))
            self.assertTrue(outside.is_file())


class TestDeleting(unittest.TestCase):
    """
    Verifies that only Snappix's own captures can be deleted.
    """

    def test_a_registered_capture_is_deleted_with_its_entry(self) -> None:
        """
        Ensures the file and its entry go together.
        """

        with TemporaryDirectory() as directory:
            shot = _file(directory, "a.png")
            register_capture(shot)
            self.assertTrue(delete_capture(shot))
            self.assertFalse(shot.exists())
            self.assertFalse(is_registered(shot))

    def test_a_file_snappix_did_not_make_is_never_deleted(self) -> None:
        """
        Ensures somebody's own file in the same folder survives, even by path.
        """

        with TemporaryDirectory() as directory:
            mine = _file(directory, "mine.png")
            theirs = _file(directory, "holiday.png")
            register_capture(mine)

            self.assertFalse(delete_capture(theirs))
            self.assertTrue(theirs.is_file())
            self.assertTrue(mine.is_file())

    def test_deleting_a_file_already_gone_still_clears_the_entry(self) -> None:
        """
        Ensures a manually removed file does not stay indexed.
        """

        with TemporaryDirectory() as directory:
            shot = _file(directory, "a.png")
            register_capture(shot, KIND_VIDEO)
            shot.unlink()
            self.assertTrue(delete_capture(shot))
            self.assertFalse(is_registered(shot))


if __name__ == "__main__":
    unittest.main()
