"""
Unit tests for the editor host menu bar shown while no tab is open.

Each editor tab is a QMainWindow with its own menu bar drawn inside the tab, so
an editor without tabs used to expose no menu at all -- File, View, and Help
(Check for Updates, About, Manual) were unreachable. The host window therefore
carries its own menu bar that is visible exactly while no tab can provide one.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

try:
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


def _make_controller():
    """
    Builds a bare AppController with only what the host menu code touches.

    Follows the project's ``object.__new__(AppController)`` test pattern to skip
    the heavy real ``__init__`` (tray icon, hotkeys, capture panel).

    Returns:
        AppController: Bare controller with a real editor host window.
    """

    from PySide6.QtWidgets import QMainWindow

    from run import AppController
    from src.config import AppConfig

    controller = object.__new__(AppController)
    controller.config = AppConfig()
    controller.editor_host = QMainWindow()
    controller.editor_tabs = MagicMock()
    controller.editor_stack = MagicMock()
    controller.editor_empty_state = MagicMock()
    controller.capture_panel = MagicMock()
    controller.set_theme = MagicMock()
    controller.quit_application = MagicMock()
    controller.show_settings_dialog = MagicMock()
    controller.create_new_canvas_tab = MagicMock()
    controller.create_empty_editor_tab = MagicMock()
    controller._open_project_from_editor_host = MagicMock()
    controller.import_image_as_new_tab = MagicMock()
    controller.import_video_as_new_tab = MagicMock()
    controller._apply_capture_taskbar_identity = MagicMock()
    controller._build_editor_host_menu()
    return controller


def _menu_titles(controller) -> list[str]:
    """
    Returns the top-level menu titles of the editor host menu bar.

    Args:
        controller: Controller under test.

    Returns:
        list[str]: Menu titles in display order.
    """

    return [
        action.menu().title()
        for action in controller._host_menu_bar.actions()
        if action.menu() is not None
    ]


def _find_menu(controller, title: str):
    """
    Returns one top-level menu of the editor host menu bar.

    Args:
        controller: Controller under test.
        title: Menu title to look up.

    Returns:
        QMenu: Matching menu.
    """

    menu = controller._host_menus.get(title)
    if menu is None:
        raise AssertionError(f"menu {title!r} not found")
    return menu


def _entry_labels(menu) -> list[str]:
    """
    Returns menu entry labels without their shortcut hint column.

    Args:
        menu: Menu to read.

    Returns:
        list[str]: Entry labels, separators excluded.
    """

    return [
        action.text().split("\t")[0]
        for action in menu.actions()
        if not action.isSeparator()
    ]


def _trigger(menu, label: str) -> None:
    """
    Triggers one menu entry by its label.

    Args:
        menu: Menu holding the entry.
        label: Entry label without shortcut hint.

    Returns:
        None
    """

    for action in menu.actions():
        if action.text().split("\t")[0] == label:
            action.trigger()
            return
    raise AssertionError(f"menu entry {label!r} not found")


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for editor host menu tests")
class TestEditorHostMenu(unittest.TestCase):
    """
    Verifies the editor host menu exists and stays usable without any tab.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists for widget tests.
        """

        cls._app = ensure_qapp()

    def test_host_menu_has_file_view_and_help_menus(self) -> None:
        """
        Ensures the tabless editor still offers the main menu structure.
        """

        controller = _make_controller()
        self.assertEqual(_menu_titles(controller), ["File", "View", "Help"])

    def test_help_menu_exposes_update_about_and_manual(self) -> None:
        """
        Ensures the Help entries the tab menu provides stay reachable.
        """

        controller = _make_controller()
        self.assertEqual(
            _entry_labels(_find_menu(controller, "Help")),
            ["Check for Updates...", "About", "Manual"],
        )

    def test_file_menu_offers_document_creation_entries(self) -> None:
        """
        Ensures documents can be created from the menu with no tab open.
        """

        controller = _make_controller()
        labels = _entry_labels(_find_menu(controller, "File"))
        for expected in (
            "New Canvas...",
            "New Tab",
            "Open Project...",
            "Import Image as New Tab...",
            "Import Video...",
        ):
            self.assertIn(expected, labels)

    def test_file_entries_call_host_actions(self) -> None:
        """
        Ensures menu entries invoke the controller actions, not a bool-carrying
        ``triggered`` slot that would land in a parent/file-path argument.
        """

        controller = _make_controller()
        file_menu = _find_menu(controller, "File")

        _trigger(file_menu, "New Tab")
        controller.create_empty_editor_tab.assert_called_once_with()

        _trigger(file_menu, "New Canvas...")
        controller.create_new_canvas_tab.assert_called_once_with(controller.editor_host)

        _trigger(file_menu, "Import Image as New Tab...")
        controller.import_image_as_new_tab.assert_called_once_with(controller.editor_host)

    def test_help_entries_open_shared_dialogs(self) -> None:
        """
        Ensures About and Manual open the same dialogs an editor tab opens.
        """

        controller = _make_controller()
        help_menu = _find_menu(controller, "Help")

        with patch("src.help_dialogs.show_about_dialog") as about:
            _trigger(help_menu, "About")
        about.assert_called_once_with(controller.editor_host)

        with patch("src.help_dialogs.show_manual_dialog") as manual:
            _trigger(help_menu, "Manual")
        manual.assert_called_once()
        self.assertIs(manual.call_args.args[0], controller.editor_host)

        with patch("src.update_dialog.check_for_updates") as updates:
            _trigger(help_menu, "Check for Updates...")
        updates.assert_called_once_with(controller.editor_host)

    def test_shortcut_hint_is_text_only_and_registers_no_key_sequence(self) -> None:
        """
        Ensures menu entries show their binding without claiming it.

        The host bindings are QShortcut objects on the same window; a second
        active binding for one sequence makes Qt report an ambiguous shortcut
        and fire neither, so the hint lives in the menu text instead.
        """

        controller = _make_controller()
        for action in _find_menu(controller, "File").actions():
            self.assertTrue(action.shortcut().isEmpty())
        new_tab = [
            action
            for action in _find_menu(controller, "File").actions()
            if action.text().startswith("New Tab")
        ][0]
        self.assertIn("\t", new_tab.text())

    def test_theme_menu_reflects_and_changes_active_theme(self) -> None:
        """
        Ensures theme switching works from the tabless editor window.
        """

        from src.theme import THEME_DARK, THEME_LIGHT

        controller = _make_controller()
        controller.config.theme = THEME_DARK
        controller._sync_host_theme_actions(THEME_DARK)
        self.assertTrue(controller._host_theme_actions[THEME_DARK].isChecked())
        self.assertFalse(controller._host_theme_actions[THEME_LIGHT].isChecked())

        controller._host_theme_actions[THEME_LIGHT].trigger()
        controller.set_theme.assert_called_once_with(THEME_LIGHT)

    def test_menu_bar_visibility_follows_tab_count(self) -> None:
        """
        Ensures the host menu shows without tabs and hides once a tab draws its
        own menu bar, so the editor never stacks two menu bars.
        """

        controller = _make_controller()
        controller.editor_host.show()

        controller.editor_tabs.count.return_value = 0
        controller._sync_editor_host_view()
        self.assertFalse(controller._host_menu_bar.isHidden())

        controller.editor_tabs.count.return_value = 1
        controller._sync_editor_host_view()
        self.assertTrue(controller._host_menu_bar.isHidden())

        controller.editor_tabs.count.return_value = 0
        controller._sync_editor_host_view()
        self.assertFalse(controller._host_menu_bar.isHidden())
        controller.editor_host.close()


if __name__ == "__main__":
    unittest.main()
