"""
Tests for browsing a folder's images with Left and Right.

An image opened from a file can be paged through with the arrow keys: Right for
the next image of its folder, Left for the previous one. The tests press the
keys on a real canvas inside a real controller, because the chain from key to
tab title to loaded picture is where this can break.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPixmap
    from PySide6.QtTest import QTest

    from tests.test_capture_tabs import CaptureTabCase

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False
    CaptureTabCase = unittest.TestCase  # type: ignore[assignment,misc]


def _write(directory: Path, name: str, width: int, height: int = 100) -> Path:
    """
    Writes an image whose size tells which file it is.

    Args:
        directory: Folder to write into.
        name: File name.
        width: Width in pixels, different for every file of a test.
        height: Height in pixels.

    Returns:
        Path: The written file.
    """

    pixmap = QPixmap(width, height)
    pixmap.fill(QColor(40, 90, 160))
    path = directory / name
    assert pixmap.save(str(path))
    return path


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class BrowsingCase(CaptureTabCase):
    """
    Shared setup: a folder of three images, the middle one open.
    """

    def setUp(self) -> None:
        """
        Creates the folder and opens its middle image.
        """

        super().setUp()
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.folder_path = Path(directory.name)
        self.a = _write(self.folder_path, "a.png", 210)
        self.b = _write(self.folder_path, "b.png", 220)
        self.c = _write(self.folder_path, "c.png", 230)
        self.controller = self._controller()
        self.controller.open_files([str(self.b)])
        self._app.processEvents()
        self.editor = self.controller.editors[-1]
        self.canvas = self.editor.canvas

    def _press(self, key, modifiers=Qt.KeyboardModifier.NoModifier) -> None:
        """
        Presses a key on the canvas.

        Args:
            key: Qt key.
            modifiers: Held modifiers.
        """

        self.canvas.setFocus()
        QTest.keyClick(self.canvas, key, modifiers)
        self._app.processEvents()

    def _shown_width(self) -> int:
        """
        Returns the width of the image the tab shows, which names the file.

        Returns:
            int: Width in pixels.
        """

        return self.canvas.screenshot().width()


class TestArrowKeys(BrowsingCase):
    """
    Verifies Left and Right.
    """

    def test_right_shows_the_next_image(self) -> None:
        """
        Ensures the tab moves on to the following file.
        """

        self._press(Qt.Key.Key_Right)

        self.assertEqual(self._shown_width(), 230)
        self.assertEqual(self.editor.opened_from(), str(self.c))

    def test_left_shows_the_previous_image(self) -> None:
        """
        Ensures the tab goes back to the preceding file.
        """

        self._press(Qt.Key.Key_Left)

        self.assertEqual(self._shown_width(), 210)
        self.assertEqual(self.editor.opened_from(), str(self.a))

    def test_it_stays_in_the_same_tab(self) -> None:
        """
        Ensures browsing replaces the picture instead of opening tabs.
        """

        self._press(Qt.Key.Key_Right)
        self._press(Qt.Key.Key_Left)

        self.assertEqual(self.controller.editor_tabs.count(), 1)

    def test_the_tab_title_follows_the_file(self) -> None:
        """
        Ensures the tab says which image it shows.
        """

        self._press(Qt.Key.Key_Right)

        self.assertEqual(self.controller.editor_tabs.tabText(0), "c.png")

    def test_the_last_image_wraps_to_the_first(self) -> None:
        """
        Ensures Right at the end starts over.
        """

        self._press(Qt.Key.Key_Right)
        self._press(Qt.Key.Key_Right)

        self.assertEqual(self._shown_width(), 210)

    def test_the_first_image_wraps_to_the_last(self) -> None:
        """
        Ensures Left at the start goes to the end.
        """

        self._press(Qt.Key.Key_Left)
        self._press(Qt.Key.Key_Left)

        self.assertEqual(self._shown_width(), 230)

    def test_a_walk_through_the_whole_folder_returns_to_the_start(self) -> None:
        """
        Ensures three steps forward land on the image we began with.
        """

        for _ in range(3):
            self._press(Qt.Key.Key_Right)

        self.assertEqual(self._shown_width(), 220)

    def test_the_new_image_is_shown_at_its_original_size(self) -> None:
        """
        Ensures every image appears at 100 %, not at the previous zoom.
        """

        self.canvas.set_zoom_factor(3.0)
        self._press(Qt.Key.Key_Right)
        self._app.processEvents()

        self.assertAlmostEqual(self.canvas.transform().m11(), 1.0)

    def test_browsing_can_go_on_indefinitely(self) -> None:
        """
        Ensures a shown image counts as untouched, so the next key works too.
        """

        for _ in range(7):
            self._press(Qt.Key.Key_Right)

        self.assertEqual(self._shown_width(), 230)

    def test_the_files_are_not_touched(self) -> None:
        """
        Ensures browsing is read-only.
        """

        before = {path: path.read_bytes() for path in (self.a, self.b, self.c)}
        for _ in range(4):
            self._press(Qt.Key.Key_Right)

        self.assertEqual({path: path.read_bytes() for path in before}, before)

    def test_files_that_are_not_images_are_skipped(self) -> None:
        """
        Ensures a text file between two images is not a page.
        """

        (self.folder_path / "b2.txt").write_text("not an image", encoding="utf-8")

        self._press(Qt.Key.Key_Right)

        self.assertEqual(self._shown_width(), 230)

    def test_an_unreadable_image_is_skipped(self) -> None:
        """
        Ensures a damaged file does not block the way to the next one.
        """

        (self.folder_path / "bb.png").write_bytes(b"this is not a png")

        self._press(Qt.Key.Key_Right)

        self.assertEqual(self._shown_width(), 230)

    def test_a_lone_image_stays_and_says_so(self) -> None:
        """
        Ensures there is feedback when there is nothing to switch to.
        """

        self.a.unlink()
        self.c.unlink()

        self._press(Qt.Key.Key_Right)

        self.assertEqual(self._shown_width(), 220)
        self.assertIn("no other image", self.editor.statusBar().currentMessage().lower())

    def test_opening_the_shown_file_again_brings_the_tab_forward(self) -> None:
        """
        Ensures the tab counts as showing its new file for the duplicate check.
        """

        self._press(Qt.Key.Key_Right)
        self.controller.open_files([str(self.c)])

        self.assertEqual(self.controller.editor_tabs.count(), 1)


class TestWhenTheKeysMeanSomethingElse(BrowsingCase):
    """
    Verifies where the arrow keys keep their other jobs.
    """

    def test_with_a_selected_annotation_the_arrow_moves_it(self) -> None:
        """
        Ensures nudging still works and the image does not change.
        """

        from src.editor_canvas import Tool

        # Annotations make the tab "changed", so browsing is off anyway; what
        # matters here is that the key moved the annotation.
        self.canvas.set_tool(Tool.RECT)
        self.canvas.set_tool(Tool.SELECT)
        with patch.object(self.canvas, "nudge_selected_items", return_value=True) as nudge:
            self._press(Qt.Key.Key_Right)

        nudge.assert_called_once_with(1.0, 0.0)
        self.assertEqual(self._shown_width(), 220)

    def test_a_selected_but_locked_annotation_does_not_start_browsing(self) -> None:
        """
        Ensures the key is not taken from a selection that merely cannot move.
        """

        item = MagicMock()
        with patch.object(self.canvas, "_selected_annotation_items", return_value=[item]), patch.object(
            self.canvas, "nudge_selected_items", return_value=False
        ):
            self._press(Qt.Key.Key_Right)

        self.assertEqual(self._shown_width(), 220)

    def test_shift_arrow_does_not_browse(self) -> None:
        """
        Ensures only the bare arrow keys page through images.
        """

        self._press(Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)

        self.assertEqual(self._shown_width(), 220)

    def test_up_and_down_do_not_browse(self) -> None:
        """
        Ensures the vertical arrows are left alone.
        """

        self._press(Qt.Key.Key_Up)
        self._press(Qt.Key.Key_Down)

        self.assertEqual(self._shown_width(), 220)

    def test_drawn_work_is_never_replaced(self) -> None:
        """
        Ensures a stray arrow key cannot throw an annotation away.
        """

        self._draw(self.editor)
        self.assertTrue(self.editor.has_drawn_annotations())
        # The new stroke is selected, and the arrow would nudge it; deselect so
        # the key reaches the browsing.
        self.canvas.scene().clearSelection()

        self._press(Qt.Key.Key_Right)

        # A stroke near the edge can grow the canvas, so the file name is the proof.
        self.assertEqual(self.editor.opened_from(), str(self.b))
        self.assertTrue(self.editor.has_drawn_annotations())
        self.assertIn("changes", self.editor.statusBar().currentMessage().lower())

    def test_an_edited_image_is_not_replaced_either(self) -> None:
        """
        Ensures changes other than annotations are protected too.
        """

        self.editor._history_index = 2

        self._press(Qt.Key.Key_Right)

        self.assertEqual(self._shown_width(), 220)

    def test_a_captured_tab_does_not_browse(self) -> None:
        """
        Ensures only tabs opened from an image file page through a folder.
        """

        editor = self._capture(self.controller)
        before = editor.canvas.screenshot().width()
        editor.canvas.setFocus()
        QTest.keyClick(editor.canvas, Qt.Key.Key_Right)

        self.assertEqual(editor.canvas.screenshot().width(), before)
        self.assertEqual(editor.opened_from(), "")

    def test_the_editor_method_ignores_tabs_without_a_file(self) -> None:
        """
        Ensures the public entry point does nothing for a plain tab.
        """

        editor = self._capture(self.controller)

        self.assertFalse(editor.navigate_folder_image(1))


if __name__ == "__main__":
    unittest.main()
