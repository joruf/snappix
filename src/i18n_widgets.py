"""
Applying the interface language to live Qt widgets.

Split from :mod:`src.i18n` so the language state and dictionary stay importable
without PySide6 -- ``run.py`` is imported before the bootstrap installs Qt.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QGroupBox,
    QLabel,
    QMenu,
    QTabWidget,
    QWidget,
)

from src.i18n import has_translations, translate


def _translate_property(widget, getter: str, setter: str) -> None:
    """
    Translates one text property of a widget in place.

    Args:
        widget: Widget carrying the property.
        getter: Name of the reader method.
        setter: Name of the writer method.

    Returns:
        None
    """

    read = getattr(widget, getter, None)
    write = getattr(widget, setter, None)
    if read is None or write is None:
        return
    try:
        original = read()
    except Exception:
        return
    if not isinstance(original, str):
        return
    replacement = translate(original)
    if replacement != original:
        try:
            write(replacement)
        except Exception:
            return


def translate_widget_tree(widget: QWidget) -> None:
    """
    Translates every known text inside one widget and its children.

    Args:
        widget: Root widget, usually a window or dialog.

    Returns:
        None
    """

    if not has_translations() or widget is None:
        return

    _translate_property(widget, "windowTitle", "setWindowTitle")

    for child in widget.findChildren(QWidget):
        if isinstance(child, (QAbstractButton, QGroupBox, QLabel)):
            _translate_property(child, "text", "setText")
        _translate_property(child, "toolTip", "setToolTip")
        if isinstance(child, QTabWidget):
            for index in range(child.count()):
                child.setTabText(index, translate(child.tabText(index)))
        if isinstance(child, QComboBox):
            for index in range(child.count()):
                child.setItemText(index, translate(child.itemText(index)))

    for action in widget.findChildren(QAction):
        _translate_property(action, "text", "setText")
        _translate_property(action, "toolTip", "setToolTip")

    for menu in widget.findChildren(QMenu):
        _translate_property(menu, "title", "setTitle")
        for action in menu.actions():
            _translate_property(action, "text", "setText")
            _translate_property(action, "toolTip", "setToolTip")


class TranslationFilter(QObject):
    """
    Translates every top-level window the first time it is shown.

    A single application-wide filter avoids sprinkling translation calls through
    each window and dialog, and it also catches dialogs built on demand.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        """
        Initializes the filter.

        Args:
            parent: Optional parent object.
        """

        super().__init__(parent)
        self._seen: set[int] = set()

    def eventFilter(self, watched, event) -> bool:
        """
        Translates a widget when it is shown.

        Args:
            watched: Object receiving the event.
            event: Qt event.

        Returns:
            bool: False, so the event continues normally.
        """

        if (
            has_translations()
            and event.type() == QEvent.Type.Show
            and isinstance(watched, QWidget)
            and watched.isWindow()
        ):
            key = id(watched)
            if key not in self._seen:
                self._seen.add(key)
                translate_widget_tree(watched)
        return False

    def forget(self) -> None:
        """
        Forgets already-translated windows so they are processed again.

        Returns:
            None
        """

        self._seen.clear()


def install_translation_filter(app) -> TranslationFilter:
    """
    Installs the application-wide translation filter.

    Args:
        app: QApplication instance.

    Returns:
        TranslationFilter: Installed filter.
    """

    translation_filter = TranslationFilter(app)
    app.installEventFilter(translation_filter)
    return translation_filter
