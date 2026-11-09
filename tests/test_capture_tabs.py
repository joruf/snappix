"""
Tests for captures that live as files from the moment they are taken.

Every screenshot and recording opens as a tab *and* sits in the capture folder.
The tab's X deletes both, File > Close style closing keeps the file, and a tab
that got lost is rebuilt from the folder on the next start. These tests drive a
real controller against an isolated home, because the wiring between capture,
tab, session and folder is where this can break.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

try:
    from PySide6.QtCore import QCoreApplication, QEvent, QPointF, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtGui import QColor, QPixmap

    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False

CONFIRM = "src.close_tab_dialog.confirm_close_tab"


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class CaptureTabCase(unittest.TestCase):
    """
    Shared setup: an isolated home and a way to start a controller in it.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def setUp(self) -> None:
        """
        Points every per-user location at a temporary home.
        """

        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = temporary.name
        environment = patch.dict(
            os.environ,
            {
                "HOME": self.home,
                "USERPROFILE": self.home,
                "LOCALAPPDATA": self.home,
                "XDG_CONFIG_HOME": f"{self.home}/.config",
                "XDG_DATA_HOME": f"{self.home}/.local/share",
                "XDG_CACHE_HOME": f"{self.home}/.cache",
            },
        )
        environment.start()
        self.addCleanup(environment.stop)

        # A dialog that appears when it should not must fail a test, not hang it.
        modal = patch("PySide6.QtWidgets.QMessageBox.exec", return_value=0)
        modal.start()
        self.addCleanup(modal.stop)

        # The controller styles the whole application, and Qt re-polishes every
        # widget that exists in the process for each change. With the leftovers
        # of a full test run that costs seconds per controller, so the sheet is
        # left out; nothing here asserts on it.
        sheet = patch("PySide6.QtWidgets.QApplication.setStyleSheet", MagicMock())
        sheet.start()
        self.addCleanup(sheet.stop)

        # A real manager would grab global hotkeys on whatever desktop runs the
        # tests, and its listener threads sometimes block on the X server.
        hotkeys = patch("src.global_hotkeys.GlobalHotkeyManager", MagicMock())
        hotkeys.start()
        self.addCleanup(hotkeys.stop)

        from src.theme import current_theme_name, set_current_theme

        self.addCleanup(set_current_theme, current_theme_name())

        from src.session_recovery import reset_workspace_root

        reset_workspace_root()
        self.addCleanup(reset_workspace_root)
        self.folder = Path(self.home) / "Downloads" / "snappix"

    def _controller(self):
        """
        Starts a controller the way the application does.

        Returns:
            AppController: Controller living in the temporary home.
        """

        import run

        controller = run.AppController(self._app, startup_project_path="", autostart_launch=False)
        self.addCleanup(self._dispose, controller)
        return controller

    def _dispose(self, controller) -> None:
        """
        Releases what a controller created, without touching any file.

        Args:
            controller: Controller to release.
        """

        controller._is_quitting = True
        while controller.editor_tabs.count() > 0:
            controller._close_editor_tab_by_index(0)
        controller.tray_icon.hide()
        for widget in (controller.editor_host, controller.capture_panel, controller.tray_icon):
            widget.deleteLater()
        self._app.processEvents()
        # deleteLater() only runs inside an event loop; without this every test
        # leaves its windows alive and each stylesheet change gets slower.
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        # The controller styles the whole application; left in place, that
        # stylesheet slows every widget any later test creates.
        self._app.setStyleSheet("")

    def _capture(self, controller) -> object:
        """
        Delivers one screenshot as the capture flow does.

        Args:
            controller: Controller under test.

        Returns:
            EditorWindow: The tab that opened.
        """

        pixmap = QPixmap(120, 80)
        pixmap.fill(QColor(200, 40, 40))
        before = len(controller.editors)
        controller._handle_capture_result(pixmap)
        self._app.processEvents()
        self.assertEqual(len(controller.editors), before + 1)
        return controller.editors[-1]

    def _draw(self, editor) -> None:
        """
        Adds one stroke, which is a change the capture file does not hold.

        Args:
            editor: Editor to draw on.
        """

        from src.editor_canvas import Tool

        canvas = editor.canvas
        canvas.set_tool(Tool.FREEHAND)
        canvas._begin_freehand_stroke(QPointF(10.0, 10.0))
        for index in range(1, 12):
            canvas._extend_freehand_stroke(QPointF(10.0 + index * 6.0, 20.0 + index))
        canvas._finalize_poly_draw()
        self._app.processEvents()

    def _files(self) -> list[str]:
        """
        Lists the capture files, leaving the hidden index out.

        Returns:
            list[str]: File names in the capture folder.
        """

        if not self.folder.is_dir():
            return []
        return sorted(name for name in os.listdir(self.folder) if not name.startswith("."))


class TestCaptureBecomesAFile(CaptureTabCase):
    """
    Verifies that a screenshot is a file before anyone touches the tab.
    """

    def test_a_capture_is_written_to_the_folder_at_once(self) -> None:
        """
        Ensures the file exists the moment the tab opens.
        """

        controller = self._controller()
        editor = self._capture(controller)

        files = self._files()
        self.assertEqual(len(files), 1)
        self.assertEqual(Path(editor.capture_file()), self.folder / files[0])
        self.assertFalse(QPixmap(editor.capture_file()).isNull())

    def test_the_file_is_indexed_as_a_snappix_capture(self) -> None:
        """
        Ensures the file counts as ours, so it may be restored and deleted.
        """

        from src.capture_files import is_registered

        controller = self._controller()
        editor = self._capture(controller)
        self.assertTrue(is_registered(editor.capture_file()))

    def test_a_failing_write_still_opens_the_tab(self) -> None:
        """
        Ensures a full disk costs the file, never the screenshot.
        """

        controller = self._controller()
        with patch.object(controller, "_save_capture_pixmap", side_effect=OSError("full")):
            editor = self._capture(controller)

        self.assertEqual(editor.capture_file(), "")
        self.assertEqual(self._files(), [])

    def test_two_captures_do_not_overwrite_each_other(self) -> None:
        """
        Ensures captures within one second keep separate files.
        """

        controller = self._controller()
        first = self._capture(controller)
        second = self._capture(controller)

        self.assertNotEqual(first.capture_file(), second.capture_file())
        self.assertEqual(len(self._files()), 2)


class TestTabClosePair(CaptureTabCase):
    """
    Verifies the two close buttons on a capture-backed tab.
    """

    def _pair(self, controller, index: int = 0):
        """
        Returns the close-button pair of one tab.

        Args:
            controller: Controller under test.
            index: Tab index.

        Returns:
            TabClosePair: The widget the tab bar holds for that tab.
        """

        from PySide6.QtWidgets import QStyle, QTabBar

        from src.tab_close_buttons import TabClosePair

        tab_bar = controller.editor_tabs.tabBar()
        position = QTabBar.ButtonPosition(
            tab_bar.style().styleHint(QStyle.StyleHint.SH_TabBar_CloseButtonPosition)
        )
        widget = tab_bar.tabButton(index, position)
        self.assertIsInstance(widget, TabClosePair)
        return widget

    def test_a_capture_tab_has_two_close_buttons(self) -> None:
        """
        Ensures a capture-backed tab offers both ways of closing.
        """

        controller = self._controller()
        self._capture(controller)

        pair = self._pair(controller)

        self.assertEqual(pair.keep_button.kind, "keep")
        self.assertEqual(pair.delete_button.kind, "delete")

    def test_a_tab_without_a_capture_keeps_the_single_default_x(self) -> None:
        """
        Ensures only tabs with a file get the pair.
        """

        from src.tab_close_buttons import TabClosePair

        controller = self._controller()
        pixmap = QPixmap(60, 40)
        pixmap.fill(QColor(10, 10, 10))
        controller._create_editor_tab(pixmap, "Imported")

        tab_bar = controller.editor_tabs.tabBar()
        for position in (tab_bar.ButtonPosition.LeftSide, tab_bar.ButtonPosition.RightSide):
            self.assertNotIsInstance(tab_bar.tabButton(0, position), TabClosePair)

    def test_the_keep_button_closes_and_keeps_the_image(self) -> None:
        """
        Ensures the X leaves the file in the project folder.
        """

        controller = self._controller()
        self._capture(controller)

        QTest.mouseClick(self._pair(controller).keep_button, Qt.MouseButton.LeftButton)

        self.assertEqual(controller.editor_tabs.count(), 0)
        self.assertEqual(len(self._files()), 1)

    def test_the_delete_button_closes_and_deletes_the_image(self) -> None:
        """
        Ensures the trash can removes the file from the project folder.
        """

        controller = self._controller()
        self._capture(controller)

        QTest.mouseClick(self._pair(controller).delete_button, Qt.MouseButton.LeftButton)

        self.assertEqual(controller.editor_tabs.count(), 0)
        self.assertEqual(self._files(), [])

    def test_a_kept_image_is_not_brought_back_as_a_tab(self) -> None:
        """
        Ensures keeping the image does not make the tab return on the next start.
        """

        controller = self._controller()
        self._capture(controller)
        QTest.mouseClick(self._pair(controller).keep_button, Qt.MouseButton.LeftButton)

        restarted = self._controller()
        restarted._maybe_restore_recovery_snapshot()

        self.assertEqual(restarted.editor_tabs.count(), 0)
        self.assertEqual(len(self._files()), 1)

    def test_each_button_acts_on_its_own_tab(self) -> None:
        """
        Ensures a button closes the tab it sits on, whatever the tab order.
        """

        controller = self._controller()
        first = self._capture(controller)
        second = self._capture(controller)

        QTest.mouseClick(self._pair(controller, 0).delete_button, Qt.MouseButton.LeftButton)

        self.assertEqual(controller.editor_tabs.count(), 1)
        self.assertIs(controller.editor_tabs.widget(0), second)
        self.assertFalse(Path(first.capture_file()).exists())
        self.assertTrue(Path(second.capture_file()).exists())

    def test_annotations_are_confirmed_for_either_button(self) -> None:
        """
        Ensures drawn work is never dropped without the usual question.
        """

        for kind in ("keep_button", "delete_button"):
            with self.subTest(kind=kind):
                controller = self._controller()
                editor = self._capture(controller)
                self._draw(editor)

                with patch(CONFIRM, return_value=False) as confirm:
                    QTest.mouseClick(
                        getattr(self._pair(controller, controller.editor_tabs.count() - 1), kind),
                        Qt.MouseButton.LeftButton,
                    )

                confirm.assert_called_once()
                self.assertGreaterEqual(controller.editor_tabs.count(), 1)
                self.assertTrue(Path(editor.capture_file()).exists())

    def test_confirming_annotations_then_deletes(self) -> None:
        """
        Ensures the delete button still deletes once the annotations are confirmed.
        """

        controller = self._controller()
        editor = self._capture(controller)
        self._draw(editor)
        file = Path(editor.capture_file())

        with patch(CONFIRM, return_value=True):
            QTest.mouseClick(self._pair(controller).delete_button, Qt.MouseButton.LeftButton)

        self.assertFalse(file.exists())
        self.assertEqual(controller.editor_tabs.count(), 0)

    def test_a_tab_without_annotations_asks_nothing(self) -> None:
        """
        Ensures the buttons are the decision, with no extra dialog.
        """

        controller = self._controller()
        self._capture(controller)

        with patch(CONFIRM, side_effect=AssertionError("asked")) as confirm:
            QTest.mouseClick(self._pair(controller).delete_button, Qt.MouseButton.LeftButton)

        confirm.assert_not_called()

    def test_somebody_elses_file_is_not_deleted(self) -> None:
        """
        Ensures a tab pointing at an unindexed file cannot delete it.
        """

        controller = self._controller()
        pixmap = QPixmap(60, 40)
        pixmap.fill(QColor(10, 10, 10))
        self.folder.mkdir(parents=True)
        theirs = self.folder / "holiday.png"
        pixmap.save(str(theirs))
        editor = controller._create_editor_tab(pixmap, "Imported", capture_file="")
        editor.set_capture_file(str(theirs))
        controller._install_tab_close_buttons(editor)

        QTest.mouseClick(self._pair(controller).delete_button, Qt.MouseButton.LeftButton)

        self.assertTrue(theirs.is_file())

    def test_a_video_tab_gets_the_pair_too(self) -> None:
        """
        Ensures recordings can be closed both ways like screenshots.
        """

        controller = self._controller()
        self.folder.mkdir(parents=True)
        clip = self.folder / "clip.mp4"
        clip.write_bytes(b"not-a-real-video")
        controller._create_video_editor_tab(
            str(clip), 320, 240, "Recording", capture_file=str(clip)
        )

        self.assertEqual(self._pair(controller).delete_button.kind, "delete")


class TestTabClosePairLooksClear(CaptureTabCase):
    """
    Verifies that the two buttons are told apart at a glance and stay tidy.
    """

    def _tab_with_pair(self):
        """
        Opens an editor with one capture tab.

        Returns:
            tuple: The controller and the pair on its tab.
        """

        controller = self._controller()
        self._capture(controller)
        # A second tab takes the selection, so the first shows its normal colours.
        self._capture(controller)
        controller.editor_host.resize(900, 600)
        self._app.processEvents()
        tab_bar = controller.editor_tabs.tabBar()
        from PySide6.QtWidgets import QStyle, QTabBar

        position = QTabBar.ButtonPosition(
            tab_bar.style().styleHint(QStyle.StyleHint.SH_TabBar_CloseButtonPosition)
        )
        return controller, tab_bar.tabButton(0, position)

    def test_the_buttons_sit_directly_next_to_each_other(self) -> None:
        """
        Ensures a small gap, in a fixed order: keep first, delete second.
        """

        from src.tab_close_buttons import BUTTON_GAP

        _controller, pair = self._tab_with_pair()
        keep, delete = pair.keep_button.geometry(), pair.delete_button.geometry()

        self.assertLess(keep.right(), delete.left())
        self.assertEqual(delete.left() - keep.right() - 1, BUTTON_GAP)
        self.assertEqual(keep.top(), delete.top())

    def test_the_buttons_do_not_overlap_or_leave_the_tab(self) -> None:
        """
        Ensures the pair fits inside its tab, clear of the title.
        """

        controller, pair = self._tab_with_pair()
        tab_bar = controller.editor_tabs.tabBar()
        tab = tab_bar.tabRect(0)
        pair_rect = pair.geometry()

        self.assertTrue(tab.contains(pair_rect), f"{pair_rect} not inside {tab}")
        self.assertFalse(pair.keep_button.geometry().intersects(pair.delete_button.geometry()))
        text_width = tab_bar.fontMetrics().horizontalAdvance(tab_bar.tabText(0))
        # The title keeps its own room: tab width covers text plus both buttons.
        self.assertGreaterEqual(tab.width(), text_width + pair_rect.width())

    def test_the_tabs_do_not_overlap_each_other(self) -> None:
        """
        Ensures several capture tabs stay separate with a pair on each.
        """

        controller = self._controller()
        for _ in range(4):
            self._capture(controller)
        controller.editor_host.resize(1200, 600)
        self._app.processEvents()
        tab_bar = controller.editor_tabs.tabBar()

        rects = [tab_bar.tabRect(index) for index in range(tab_bar.count())]
        for left, right in zip(rects, rects[1:]):
            self.assertLessEqual(left.right(), right.left())

    def test_the_buttons_look_different(self) -> None:
        """
        Ensures the two are told apart by shape and colour, not only by tooltip.
        """

        _controller, pair = self._tab_with_pair()
        keep_image = pair.keep_button.grab().toImage()
        delete_image = pair.delete_button.grab().toImage()

        self.assertNotEqual(keep_image, delete_image)

    def test_the_delete_button_is_in_the_danger_colour(self) -> None:
        """
        Ensures the destructive button is the red one.
        """

        from src.tab_close_buttons import DANGER_COLOR

        _controller, pair = self._tab_with_pair()

        self.assertEqual(pair.delete_button.glyph_color().name(), DANGER_COLOR)
        self.assertNotEqual(pair.keep_button.glyph_color().name(), DANGER_COLOR)

    def test_the_keep_glyph_follows_the_theme(self) -> None:
        """
        Ensures the X is readable on every theme.
        """

        from src.theme import THEME_LIGHT, get_theme_colors, set_current_theme

        _controller, pair = self._tab_with_pair()
        set_current_theme(THEME_LIGHT)

        self.assertEqual(
            pair.keep_button.glyph_color().name(),
            get_theme_colors(THEME_LIGHT).text.lower(),
        )

    def test_the_selected_tab_uses_colours_made_for_its_background(self) -> None:
        """
        Ensures both glyphs stay readable on the accent-coloured selected tab.
        """

        from src.tab_close_buttons import DANGER_COLOR, DANGER_COLOR_ON_ACCENT
        from src.theme import get_theme_colors

        controller = self._controller()
        self._capture(controller)
        self._capture(controller)
        tab_bar = controller.editor_tabs.tabBar()
        from PySide6.QtWidgets import QStyle, QTabBar

        position = QTabBar.ButtonPosition(
            tab_bar.style().styleHint(QStyle.StyleHint.SH_TabBar_CloseButtonPosition)
        )
        controller.editor_tabs.setCurrentIndex(0)
        self._app.processEvents()
        selected = tab_bar.tabButton(0, position)
        other = tab_bar.tabButton(1, position)

        self.assertEqual(selected.delete_button.glyph_color().name(), DANGER_COLOR_ON_ACCENT)
        self.assertEqual(other.delete_button.glyph_color().name(), DANGER_COLOR)
        self.assertEqual(
            selected.keep_button.glyph_color().name(),
            get_theme_colors().button_checked_text.lower(),
        )

        controller.editor_tabs.setCurrentIndex(1)
        self._app.processEvents()
        self.assertEqual(selected.delete_button.glyph_color().name(), DANGER_COLOR)
        self.assertEqual(other.delete_button.glyph_color().name(), DANGER_COLOR_ON_ACCENT)

    def test_each_button_says_what_it_does(self) -> None:
        """
        Ensures the tooltips name the effect on the image, in plain words.
        """

        _controller, pair = self._tab_with_pair()

        self.assertIn("keep", pair.keep_button.toolTip().lower())
        self.assertIn("delete", pair.delete_button.toolTip().lower())
        self.assertNotEqual(pair.keep_button.toolTip(), pair.delete_button.toolTip())
        self.assertNotEqual(
            pair.keep_button.accessibleName(), pair.delete_button.accessibleName()
        )


class TestOtherCloseKeepsTheFile(CaptureTabCase):
    """
    Verifies closing that is not the X.
    """

    def test_closing_the_current_tab_keeps_the_file(self) -> None:
        """
        Ensures the keyboard close leaves the capture in the folder.
        """

        controller = self._controller()
        self._capture(controller)

        controller._close_current_editor_tab()

        self.assertEqual(controller.editor_tabs.count(), 0)
        self.assertEqual(len(self._files()), 1)

    def test_a_kept_file_is_not_brought_back_as_a_tab(self) -> None:
        """
        Ensures closing a tab means it stays closed after a restart.
        """

        controller = self._controller()
        self._capture(controller)
        controller._close_current_editor_tab()

        restarted = self._controller()
        restarted._maybe_restore_recovery_snapshot()

        self.assertEqual(restarted.editor_tabs.count(), 0)
        self.assertEqual(len(self._files()), 1)

    def test_quitting_deletes_nothing(self) -> None:
        """
        Ensures the files survive the application ending.
        """

        controller = self._controller()
        self._capture(controller)
        controller._is_quitting = True

        controller._close_editor_tab_by_index(0)

        self.assertEqual(len(self._files()), 1)


class TestStartRestoresTabs(CaptureTabCase):
    """
    Verifies what the next start does with the folder.
    """

    def test_open_tabs_come_back_bound_to_their_files(self) -> None:
        """
        Ensures a restored tab can still delete its file with the X.
        """

        controller = self._controller()
        self._capture(controller)
        controller._save_editor_session()

        restarted = self._controller()
        restarted._maybe_restore_recovery_snapshot()

        self.assertEqual(restarted.editor_tabs.count(), 1)
        restored = restarted.editors[-1]
        self.assertEqual(Path(restored.capture_file()), self.folder / self._files()[0])
        restarted._close_tab_of(restarted.editors[-1], delete_capture=True)
        self.assertEqual(self._files(), [])

    def test_a_lost_tab_is_rebuilt_from_the_folder(self) -> None:
        """
        Ensures a capture whose session is gone still gets its tab.
        """

        from src.session_recovery import clear_editor_session

        controller = self._controller()
        self._capture(controller)
        controller._save_editor_session()
        clear_editor_session()
        self.assertEqual(len(self._files()), 1)

        restarted = self._controller()
        restarted._maybe_restore_recovery_snapshot()

        self.assertEqual(restarted.editor_tabs.count(), 1)
        self.assertEqual(
            Path(restarted.editors[-1].capture_file()), self.folder / self._files()[0]
        )

    def test_a_lost_tab_keeps_its_annotations_when_recovery_survives(self) -> None:
        """
        Ensures the drawing is not lost just because the manifest was.
        """

        controller = self._controller()
        editor = self._capture(controller)
        self._draw(editor)
        controller._save_editor_session()
        manifest = Path(self.home) / ".snappix" / "session.json"
        manifest.unlink()

        restarted = self._controller()
        restarted._maybe_restore_recovery_snapshot()

        self.assertEqual(restarted.editor_tabs.count(), 1)
        self.assertTrue(restarted.editors[-1].has_drawn_annotations())

    def test_a_lost_tab_opens_from_the_file_when_recovery_is_gone(self) -> None:
        """
        Ensures the picture alone is enough to bring the tab back.
        """

        import shutil

        controller = self._controller()
        self._capture(controller)
        controller._save_editor_session()
        shutil.rmtree(Path(self.home) / ".snappix")

        restarted = self._controller()
        restarted._maybe_restore_recovery_snapshot()

        self.assertEqual(restarted.editor_tabs.count(), 1)
        tab = restarted.editors[-1]
        self.assertEqual(Path(tab.capture_file()), self.folder / self._files()[0])
        self.assertFalse(tab.canvas.screenshot().isNull())

    def test_a_file_that_is_not_ours_gets_no_tab(self) -> None:
        """
        Ensures older screenshots and other files in the folder stay untouched.
        """

        controller = self._controller()
        self._capture(controller)
        controller._save_editor_session()
        controller._close_current_editor_tab()
        pixmap = QPixmap(30, 30)
        pixmap.fill(QColor(0, 0, 255))
        pixmap.save(str(self.folder / "older.png"))

        restarted = self._controller()
        restarted._maybe_restore_recovery_snapshot()

        self.assertEqual(restarted.editor_tabs.count(), 0)
        self.assertTrue((self.folder / "older.png").is_file())

    def test_a_tab_already_open_is_not_opened_twice(self) -> None:
        """
        Ensures the folder scan skips captures a restored tab shows.
        """

        controller = self._controller()
        self._capture(controller)
        controller._save_editor_session()

        restarted = self._controller()
        restarted._maybe_restore_recovery_snapshot()

        self.assertEqual(restarted.editor_tabs.count(), 1)
        self.assertEqual(restarted._lost_capture_tabs([]), ([], []))


class TestRecordings(CaptureTabCase):
    """
    Verifies that a recording leaves the scratch folder as a capture file.
    """

    def test_a_finished_recording_moves_into_the_folder(self) -> None:
        """
        Ensures the recording is a capture file and the tab uses it.
        """

        controller = self._controller()
        scratch = self.folder / "tmp"
        scratch.mkdir(parents=True)
        recording = scratch / "snappix-recording_2026-10-28_08-00-00.mp4"
        recording.write_bytes(b"video")
        controller._video_recorder = MagicMock()
        controller._recording_rect = MagicMock(width=lambda: 320, height=lambda: 200)
        controller._close_recording_border_overlay = MagicMock()
        controller._recording_fits_editor_limit = MagicMock(return_value=True)
        controller._create_video_editor_tab = MagicMock()

        controller._on_recording_finished(str(recording))

        target = self.folder / recording.name
        self.assertTrue(target.is_file())
        self.assertFalse(recording.exists())
        args, kwargs = controller._create_video_editor_tab.call_args
        self.assertEqual(args[0], str(target))
        self.assertEqual(kwargs["capture_file"], str(target))

    def test_a_clashing_name_gets_a_counter(self) -> None:
        """
        Ensures an earlier recording of the same second survives.
        """

        controller = self._controller()
        self.folder.mkdir(parents=True)
        (self.folder / "clip.mp4").write_bytes(b"old")
        scratch = self.folder / "tmp"
        scratch.mkdir()
        recording = scratch / "clip.mp4"
        recording.write_bytes(b"new")

        moved = controller._move_recording_to_capture_folder(str(recording))

        self.assertEqual(Path(moved).name, "clip-1.mp4")
        self.assertEqual((self.folder / "clip.mp4").read_bytes(), b"old")

    def test_a_video_tab_releases_its_player_before_the_file_goes(self) -> None:
        """
        Ensures the open file is let go first; Windows cannot delete it otherwise.
        """

        import run
        from src.capture_files import register_capture

        self.folder.mkdir(parents=True)
        clip = self.folder / "clip.mp4"
        clip.write_bytes(b"video")
        register_capture(clip, "video")
        order: list[str] = []
        tab = MagicMock()
        tab._capture_file = str(clip)
        tab.shutdown_playback.side_effect = lambda: order.append(
            f"release:{clip.exists()}"
        )

        run.AppController._release_capture_file(tab, delete=True)

        self.assertEqual(order, ["release:True"])
        self.assertFalse(clip.exists())


class TestEditorWindowAroundCaptures(CaptureTabCase):
    """
    Verifies when the whole editor goes away and comes back.
    """

    def _start_capture(self, controller):
        """
        Starts a screenshot with the grab itself stubbed out.

        Args:
            controller: Controller under test.

        Returns:
            dict: The ``on_capture`` and ``on_cancel`` callbacks the capture got.
        """

        from src.capture import CaptureMode, CaptureRequest

        callbacks: dict = {}

        def fake_execute(*, request, on_capture, on_cancel) -> None:
            callbacks["capture"] = on_capture
            callbacks["cancel"] = on_cancel

        with patch("src.capture.execute_capture_request", fake_execute):
            controller.start_capture(CaptureRequest(mode=CaptureMode.REGION, delay_seconds=0))
        return callbacks

    def test_closing_the_last_tab_closes_the_editor(self) -> None:
        """
        Ensures no empty editor window is left behind.
        """

        controller = self._controller()
        self._capture(controller)
        self.assertTrue(controller.editor_host.isVisible())

        controller._close_tab_of(controller.editors[0], delete_capture=True)

        self.assertFalse(controller.editor_host.isVisible())
        self.assertTrue(controller.capture_panel.isVisible())

    def test_closing_a_tab_with_others_left_keeps_the_editor(self) -> None:
        """
        Ensures only the last tab takes the window with it.
        """

        controller = self._controller()
        self._capture(controller)
        self._capture(controller)

        controller._close_tab_of(controller.editors[0], delete_capture=True)

        self.assertEqual(controller.editor_tabs.count(), 1)
        self.assertTrue(controller.editor_host.isVisible())

    def test_the_editor_is_minimized_while_a_screenshot_is_taken(self) -> None:
        """
        Ensures an open editor cannot cover what the capture is meant to grab.
        """

        controller = self._controller()
        self._capture(controller)
        self.assertFalse(controller.editor_host.isMinimized())

        self._start_capture(controller)

        self.assertTrue(controller.editor_host.isMinimized())

    def test_the_editor_returns_once_the_screenshot_is_done(self) -> None:
        """
        Ensures the finished screenshot is on screen to be looked at.
        """

        controller = self._controller()
        self._capture(controller)
        callbacks = self._start_capture(controller)
        pixmap = QPixmap(50, 40)
        pixmap.fill(QColor(0, 120, 0))

        callbacks["capture"](pixmap)
        self._app.processEvents()

        self.assertFalse(controller.editor_host.isMinimized())
        self.assertTrue(controller.editor_host.isVisible())
        self.assertEqual(controller.editor_tabs.count(), 2)

    def test_the_editor_returns_when_the_screenshot_goes_to_the_clipboard(self) -> None:
        """
        Ensures the editor comes back even when no new tab opens.
        """

        controller = self._controller()
        self._capture(controller)
        controller.config.post_capture_action = "clipboard"
        callbacks = self._start_capture(controller)
        pixmap = QPixmap(50, 40)
        pixmap.fill(QColor(0, 120, 0))

        callbacks["capture"](pixmap)
        self._app.processEvents()

        self.assertEqual(controller.editor_tabs.count(), 1)
        self.assertFalse(controller.editor_host.isMinimized())

    def test_the_editor_returns_after_a_cancelled_screenshot(self) -> None:
        """
        Ensures cancelling leaves the editor as it was.
        """

        controller = self._controller()
        self._capture(controller)
        callbacks = self._start_capture(controller)

        callbacks["cancel"]()
        self._app.processEvents()

        self.assertFalse(controller.editor_host.isMinimized())
        self.assertTrue(controller.editor_host.isVisible())

    def test_a_closed_editor_is_not_opened_by_a_screenshot_that_is_cancelled(self) -> None:
        """
        Ensures only an editor that was showing is brought back.
        """

        controller = self._controller()
        self.assertFalse(controller.editor_host.isVisible())
        callbacks = self._start_capture(controller)

        callbacks["cancel"]()
        self._app.processEvents()

        self.assertFalse(controller.editor_host.isVisible())

    def test_an_editor_the_user_minimized_stays_minimized(self) -> None:
        """
        Ensures the capture does not pop up a window the user put away.
        """

        controller = self._controller()
        self._capture(controller)
        controller.editor_host.showMinimized()
        self._app.processEvents()
        callbacks = self._start_capture(controller)

        callbacks["cancel"]()
        self._app.processEvents()

        self.assertTrue(controller.editor_host.isMinimized())


if __name__ == "__main__":
    unittest.main()
