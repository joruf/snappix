"""
Tests for the folder order behind browsing images with the arrow keys.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.image_folder import images_in_folder, natural_key, neighbours


def _touch(directory: Path, *names: str) -> list[Path]:
    """
    Creates empty files.

    Args:
        directory: Folder to create them in.
        *names: File names.

    Returns:
        list[Path]: The created files.
    """

    paths = []
    for name in names:
        path = directory / name
        path.write_bytes(b"x")
        paths.append(path)
    return paths


class TestOrder(unittest.TestCase):
    """
    Verifies the order images are browsed in.
    """

    def test_numbers_are_ordered_by_value(self) -> None:
        """
        Ensures img2 comes before img10, as a file manager shows them.
        """

        with TemporaryDirectory() as directory:
            _touch(Path(directory), "img10.png", "img2.png", "img1.png")

            names = [path.name for path in images_in_folder(Path(directory) / "img1.png")]

        self.assertEqual(names, ["img1.png", "img2.png", "img10.png"])

    def test_case_is_ignored(self) -> None:
        """
        Ensures Zebra does not jump ahead of apple.
        """

        with TemporaryDirectory() as directory:
            _touch(Path(directory), "Zebra.png", "apple.png", "Mango.png")

            names = [path.name for path in images_in_folder(Path(directory) / "apple.png")]

        self.assertEqual(names, ["apple.png", "Mango.png", "Zebra.png"])

    def test_only_images_are_listed(self) -> None:
        """
        Ensures documents and folders are not part of the browsing.
        """

        with TemporaryDirectory() as directory:
            folder = Path(directory)
            _touch(folder, "a.png", "notes.txt", "b.JPG", "clip.mp4", "c.sfp")
            (folder / "sub.png").mkdir()

            names = [path.name for path in images_in_folder(folder / "a.png")]

        self.assertEqual(names, ["a.png", "b.JPG"])

    def test_the_key_never_compares_text_with_numbers(self) -> None:
        """
        Ensures names that start differently sort without raising.
        """

        names = ["10.png", "b.png", "1a.png", "a.png", "2.png"]

        self.assertEqual(
            sorted(names, key=natural_key), ["1a.png", "2.png", "10.png", "a.png", "b.png"]
        )

    def test_an_unreadable_folder_gives_an_empty_list(self) -> None:
        """
        Ensures a folder that vanished does not raise.
        """

        with patch("pathlib.Path.iterdir", side_effect=PermissionError("no")):
            self.assertEqual(images_in_folder("/nonexistent/place/a.png"), [])


class TestNeighbours(unittest.TestCase):
    """
    Verifies which image comes next.
    """

    def _folder(self, *names: str):
        """
        Creates a folder with files and returns it with its path.

        Args:
            *names: File names.

        Returns:
            tuple: The temporary directory and its path.
        """

        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        _touch(Path(directory.name), *names)
        return Path(directory.name)

    def test_forward_lists_the_following_images_nearest_first(self) -> None:
        """
        Ensures the next image is first and the list wraps to the start.
        """

        folder = self._folder("a.png", "b.png", "c.png", "d.png")

        names = [path.name for path in neighbours(folder / "b.png", 1)]

        self.assertEqual(names, ["c.png", "d.png", "a.png"])

    def test_backward_lists_the_preceding_images_nearest_first(self) -> None:
        """
        Ensures the previous image is first and the list wraps to the end.
        """

        folder = self._folder("a.png", "b.png", "c.png", "d.png")

        names = [path.name for path in neighbours(folder / "b.png", -1)]

        self.assertEqual(names, ["a.png", "d.png", "c.png"])

    def test_the_last_image_wraps_to_the_first(self) -> None:
        """
        Ensures browsing is a loop.
        """

        folder = self._folder("a.png", "b.png", "c.png")

        self.assertEqual(neighbours(folder / "c.png", 1)[0].name, "a.png")
        self.assertEqual(neighbours(folder / "a.png", -1)[0].name, "c.png")

    def test_a_lone_image_has_no_neighbour(self) -> None:
        """
        Ensures there is nothing to switch to.
        """

        folder = self._folder("only.png", "notes.txt")

        self.assertEqual(neighbours(folder / "only.png", 1), [])
        self.assertEqual(neighbours(folder / "only.png", -1), [])

    def test_a_file_that_is_gone_has_no_place(self) -> None:
        """
        Ensures a deleted file does not make the browsing jump somewhere.
        """

        folder = self._folder("a.png", "b.png")

        self.assertEqual(neighbours(folder / "missing.png", 1), [])

    def test_every_other_image_appears_exactly_once(self) -> None:
        """
        Ensures a caller that skips unreadable files reaches them all.
        """

        folder = self._folder(*[f"{n}.png" for n in range(1, 8)])

        found = [path.name for path in neighbours(folder / "4.png", 1)]

        self.assertEqual(sorted(found), sorted(f"{n}.png" for n in (1, 2, 3, 5, 6, 7)))
        self.assertEqual(len(found), len(set(found)))


if __name__ == "__main__":
    unittest.main()
