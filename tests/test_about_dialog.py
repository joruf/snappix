"""
Unit tests for About dialog constants and clickable links.
"""

from __future__ import annotations

import unittest

from src.constants import (
    ABOUT_GITHUB,
    ABOUT_WEBSITE,
    APP_NAME,
    build_about_dialog_html,
    normalize_about_url,
)

try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPixmap
    from PySide6.QtWidgets import QLabel

    from src.editor_window import EditorWindow
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


class TestAboutConstants(unittest.TestCase):
    """
    Verifies About URL normalization and rich-text HTML content.
    """

    def test_normalize_about_url_adds_https_when_missing(self) -> None:
        """
        Ensures bare hostnames become https URLs.
        """

        self.assertEqual(normalize_about_url("loresoft.de"), "https://loresoft.de")
        self.assertEqual(
            normalize_about_url("https://github.com/joruf/snappix"),
            "https://github.com/joruf/snappix",
        )

    def test_build_about_dialog_html_contains_clickable_links(self) -> None:
        """
        Ensures About HTML includes href links for website and GitHub.
        """

        from src.theme import THEME_DARK, get_theme_colors, set_current_theme

        set_current_theme(THEME_DARK)
        html = build_about_dialog_html()
        link_color = get_theme_colors(THEME_DARK).link
        self.assertIn(f"<b>{APP_NAME}</b>", html)
        self.assertIn(f'href="{normalize_about_url(ABOUT_WEBSITE)}"', html)
        self.assertIn(f'href="{normalize_about_url(ABOUT_GITHUB)}"', html)
        self.assertIn(f"color: {link_color}", html)
        self.assertIn(ABOUT_WEBSITE, html)
        self.assertIn(ABOUT_GITHUB, html)


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for About dialog tests")
class TestAboutDialog(unittest.TestCase):
    """
    Verifies the About dialog enables external link interaction.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures Qt application exists for widget tests.
        """

        cls._app = ensure_qapp()

    def test_show_about_enables_open_external_links(self) -> None:
        """
        Ensures About message labels open links in the default browser.
        """

        pixmap = QPixmap(40, 30)
        pixmap.fill(QColor(200, 200, 200))
        window = EditorWindow(pixmap)

        from unittest.mock import patch
        from PySide6.QtWidgets import QMessageBox

        created: list[QMessageBox] = []
        real_init = QMessageBox.__init__

        def tracking_init(self, *args, **kwargs):
            real_init(self, *args, **kwargs)
            created.append(self)

        with patch.object(QMessageBox, "__init__", tracking_init), patch.object(
            QMessageBox, "exec", return_value=QMessageBox.StandardButton.Ok
        ):
            window.show_about()

        self.assertEqual(len(created), 1)
        box = created[0]
        self.assertEqual(box.textFormat(), Qt.TextFormat.RichText)
        self.assertIn('href="https://loresoft.de"', box.text())
        self.assertIn(f'href="{ABOUT_GITHUB}"', box.text())
        labels = [
            label
            for label in box.findChildren(QLabel)
            if label.openExternalLinks()
            and bool(
                label.textInteractionFlags()
                & Qt.TextInteractionFlag.LinksAccessibleByMouse
            )
        ]
        self.assertTrue(labels)
        window.close()


if __name__ == "__main__":
    unittest.main()
