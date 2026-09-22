"""
Tests for saving a document.

Ctrl+S used to write the editable project file, which is rarely what a
screenshot is wanted as. It now offers image formats first while keeping every
other format, including the project file, one entry away.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

try:
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QColor, QImage, QPixmap

    from src.constants import APP_FILE_EXTENSION
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class SaveTestCase(unittest.TestCase):
    """
    Shared setup: an editor holding one annotated document.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def _editor(self):
        """
        Opens an editor with one stroke on it.

        Returns:
            EditorWindow: Editor under test.
        """

        from src.editor_canvas import Tool
        from src.editor_window import EditorWindow

        image = QImage(300, 200, QImage.Format.Format_RGB32)
        image.fill(QColor(230, 235, 240))
        editor = EditorWindow(QPixmap.fromImage(image))
        self.addCleanup(editor.close)
        editor.show()
        self._app.processEvents()

        canvas = editor.canvas
        canvas.set_tool(Tool.FREEHAND)
        canvas._begin_freehand_stroke(QPointF(20.0, 20.0))
        for index in range(1, 20):
            canvas._extend_freehand_stroke(
                QPointF(20.0 + index * 8.0, 40.0 + (index % 3) * 20.0)
            )
        canvas._finalize_poly_draw()
        self._app.processEvents()
        return editor


class TestImageIsTheDefault(SaveTestCase):
    """
    Verifies what saving offers first.
    """

    def test_the_first_offered_format_is_an_image(self) -> None:
        """
        Ensures the dialog opens on an image, not the project file.

        A screenshot tool's output is a picture; writing a file only Snappix can
        open was the wrong default.
        """

        from src.editor_window import SAVE_FORMATS

        self.assertEqual(SAVE_FORMATS[0][2], "png")

    def test_the_filter_list_starts_with_png(self) -> None:
        """
        Ensures the dialog's preselected entry is PNG.
        """

        editor = self._editor()
        self.assertTrue(editor._save_format_filters().startswith("PNG Image (*.png)"))

    def test_every_format_stays_reachable(self) -> None:
        """
        Ensures nothing was traded away for the new default.
        """

        editor = self._editor()
        filters = editor._save_format_filters()
        for fragment in ("*.png", "*.jpg", "*.webp", "*.bmp", "*.pdf", "*.svg"):
            self.assertIn(fragment, filters)
        self.assertIn(APP_FILE_EXTENSION, filters)

    def test_ctrl_s_saves_the_document_not_the_project(self) -> None:
        """
        Ensures the shortcut reaches the format-aware save.

        The menu entry can be renamed and still be wired to the old project
        save, which is exactly the behaviour being replaced.
        """

        editor = self._editor()
        action = editor._shortcut_actions["save_project"]

        with patch.object(editor, "save_document") as save_document, patch.object(
            editor, "save_project"
        ) as save_project:
            action.trigger()

        save_document.assert_called_once()
        save_project.assert_not_called()

    def test_shift_ctrl_s_asks_for_the_format(self) -> None:
        """
        Ensures "save as" offers the format list rather than only the project.
        """

        editor = self._editor()
        action = editor._shortcut_actions["save_project_as"]

        with patch.object(editor, "save_document_as") as save_as:
            action.trigger()
        save_as.assert_called_once()

    def test_the_project_format_keeps_its_own_entries(self) -> None:
        """
        Ensures saving an editable project is still one click away.
        """

        from PySide6.QtWidgets import QMenu

        editor = self._editor()
        titles = [
            action.text()
            for menu in editor.findChildren(QMenu)
            if menu.title() == "File"
            for action in menu.actions()
        ]
        self.assertIn("Save Project", titles)
        self.assertIn("Save Project As...", titles)

    def test_the_project_format_is_offered_last(self) -> None:
        """
        Ensures the editable file is still there, just not first.
        """

        editor = self._editor()
        self.assertTrue(editor._save_format_filters().rstrip().endswith(
            f"(*{APP_FILE_EXTENSION})"
        ))


class TestFormatResolution(SaveTestCase):
    """
    Verifies how a path and a chosen filter become a format.
    """

    def test_no_extension_takes_the_chosen_filter(self) -> None:
        """
        Ensures the drop-down decides when nothing was typed.
        """

        editor = self._editor()
        path, key = editor._resolve_save_format("/tmp/shot", "SVG Image (*.svg)")
        self.assertEqual((Path(path).suffix, key), (".svg", "svg"))

    def test_a_typed_extension_beats_the_filter(self) -> None:
        """
        Ensures writing ``shot.jpg`` means JPEG even with PNG still selected.
        """

        editor = self._editor()
        path, key = editor._resolve_save_format("/tmp/shot.jpg", "PNG Image (*.png)")
        self.assertEqual((path, key), ("/tmp/shot.jpg", "jpg"))

    def test_the_long_jpeg_extension_is_recognized(self) -> None:
        """
        Ensures ``.jpeg`` is not treated as an unknown format.
        """

        editor = self._editor()
        _path, key = editor._resolve_save_format("/tmp/shot.jpeg", "PNG Image (*.png)")
        self.assertEqual(key, "jpg")

    def test_the_project_extension_is_recognized(self) -> None:
        """
        Ensures typing the project extension still produces a project.
        """

        editor = self._editor()
        _path, key = editor._resolve_save_format(
            f"/tmp/shot{APP_FILE_EXTENSION}", "PNG Image (*.png)"
        )
        self.assertEqual(key, "project")

    def test_an_unknown_filter_falls_back_to_the_default(self) -> None:
        """
        Ensures a platform dialog that reports nothing usable still saves.
        """

        editor = self._editor()
        path, key = editor._resolve_save_format("/tmp/shot", "something else")
        self.assertEqual((Path(path).suffix, key), (".png", "png"))


class TestWriting(SaveTestCase):
    """
    Verifies that each format actually produces a file.
    """

    def test_every_offered_format_writes_a_file(self) -> None:
        """
        Ensures no entry in the list is a dead end.
        """

        from src.editor_window import SAVE_FORMATS

        editor = self._editor()
        with TemporaryDirectory() as directory:
            for _label, extension, key in SAVE_FORMATS:
                target = Path(directory) / f"probe{extension}"
                self.assertTrue(
                    editor._write_document(str(target), key, ask=False),
                    f"{key} reported failure",
                )
                self.assertGreater(target.stat().st_size, 0, f"{key} wrote nothing")

    def test_a_saved_png_is_a_real_image(self) -> None:
        """
        Ensures the written file opens as a picture of the right size.
        """

        editor = self._editor()
        with TemporaryDirectory() as directory:
            target = Path(directory) / "shot.png"
            editor._write_document(str(target), "png", ask=False)
            written = QImage(str(target))

        self.assertFalse(written.isNull())
        self.assertEqual(written.size(), QImage(300, 200, QImage.Format.Format_RGB32).size())

    def test_the_project_format_still_round_trips(self) -> None:
        """
        Ensures annotations stay editable when that format is chosen.
        """

        from src.storage import load_project

        editor = self._editor()
        with TemporaryDirectory() as directory:
            target = Path(directory) / f"shot{APP_FILE_EXTENSION}"
            editor._write_document(str(target), "project", ask=False)
            loaded = load_project(target)

        self.assertEqual(len(loaded.annotations), 1)

    def test_a_repeat_save_does_not_ask_again(self) -> None:
        """
        Ensures Ctrl+S stays a single keystroke.

        Asking for JPEG quality on every save would make repeat saving as slow
        as a full export.
        """

        editor = self._editor()
        with TemporaryDirectory() as directory:
            target = Path(directory) / "shot.jpg"
            with patch.object(editor, "_ask_jpeg_quality") as ask:
                editor._write_document(str(target), "jpg", ask=False)
            ask.assert_not_called()
            self.assertTrue(target.is_file())


class TestSaveAndResave(SaveTestCase):
    """
    Verifies the remembered target.
    """

    def test_saving_remembers_path_and_format(self) -> None:
        """
        Ensures the next save knows where to go.
        """

        editor = self._editor()
        with TemporaryDirectory() as directory:
            target = str(Path(directory) / "shot.png")
            with patch(
                "src.editor_window.QFileDialog.getSaveFileName",
                return_value=(target, "PNG Image (*.png)"),
            ):
                editor.save_document_as()

            self.assertEqual(editor._save_target, (target, "png"))

    def test_saving_again_writes_the_same_file_without_asking(self) -> None:
        """
        Ensures repeat saves do not reopen the dialog.
        """

        editor = self._editor()
        with TemporaryDirectory() as directory:
            target = str(Path(directory) / "shot.png")
            with patch(
                "src.editor_window.QFileDialog.getSaveFileName",
                return_value=(target, "PNG Image (*.png)"),
            ):
                editor.save_document_as()

            Path(target).unlink()
            with patch(
                "src.editor_window.QFileDialog.getSaveFileName"
            ) as dialog:
                editor.save_document()

            dialog.assert_not_called()
            self.assertTrue(Path(target).is_file())

    def test_the_first_save_asks(self) -> None:
        """
        Ensures a fresh document does not write somewhere unannounced.
        """

        editor = self._editor()
        with patch(
            "src.editor_window.QFileDialog.getSaveFileName", return_value=("", "")
        ) as dialog:
            editor.save_document()
        dialog.assert_called_once()

    def test_saving_a_project_is_remembered_too(self) -> None:
        """
        Ensures someone working on a project keeps saving the project.
        """

        editor = self._editor()
        with TemporaryDirectory() as directory:
            target = str(Path(directory) / f"shot{APP_FILE_EXTENSION}")
            with patch(
                "src.editor_window.QFileDialog.getSaveFileName",
                return_value=(target, f"Snappix Project (*{APP_FILE_EXTENSION})"),
            ):
                editor.save_document_as()

            self.assertEqual(editor._save_target, (target, "project"))

    def test_a_cancelled_dialog_changes_nothing(self) -> None:
        """
        Ensures backing out leaves no half-set target behind.
        """

        editor = self._editor()
        with patch(
            "src.editor_window.QFileDialog.getSaveFileName", return_value=("", "")
        ):
            editor.save_document_as()
        self.assertIsNone(editor._save_target)


if __name__ == "__main__":
    unittest.main()
