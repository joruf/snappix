"""
Dialog that lists editor tools with icons and explanations.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QWheelEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.theme import get_theme_colors
from src.tool_reference import TOOL_HELP_ENTRIES, ToolHelpEntry


class _SmoothScrollArea(QScrollArea):
    """
    Scroll area with pixel-based mouse-wheel scrolling.
    """

    def wheelEvent(self, event: QWheelEvent) -> None:
        """
        Scrolls the viewport in small pixel steps for smoother reading.

        Args:
            event: Wheel event from Qt.

        Returns:
            None
        """

        bar = self.verticalScrollBar()
        if not bar.isVisible() and bar.maximum() <= bar.minimum():
            super().wheelEvent(event)
            return

        pixel_delta = event.pixelDelta().y()
        if pixel_delta != 0:
            step = pixel_delta
        else:
            # angleDelta is typically ±120 per notch; use a gentler step.
            step = int(event.angleDelta().y() * 0.45)
            if step == 0 and event.angleDelta().y() != 0:
                step = 18 if event.angleDelta().y() > 0 else -18

        bar.setValue(bar.value() - step)
        event.accept()


class ToolReferenceDialog(QDialog):
    """
    Shows a scrollable list of tool icons with explanations.
    """

    def __init__(
        self,
        parent: QWidget | None,
        icon_provider: Callable[[str], QIcon],
    ) -> None:
        """
        Creates the tools reference dialog.

        Args:
            parent: Parent widget.
            icon_provider: Callable that returns the toolbar icon for a tool id.
        """

        super().__init__(parent)
        self.setWindowTitle("Tools")
        self.setModal(True)
        self.setObjectName("toolReferenceDialog")
        self.resize(680, 560)
        self.setMinimumSize(520, 420)

        colors = get_theme_colors()
        self.setStyleSheet(
            f"""
            QDialog#toolReferenceDialog {{
                background: {colors.window_bg};
            }}
            QLabel#toolReferenceIntro {{
                color: {colors.text_muted};
                padding: 2px 2px 8px 2px;
            }}
            QFrame#toolReferenceHeader {{
                background: {colors.surface_alt};
                border: 1px solid {colors.border};
                border-radius: 8px;
            }}
            QLabel#toolReferenceHeaderLabel {{
                color: {colors.text_muted};
                font-weight: 600;
                padding: 8px 12px;
            }}
            QScrollArea#toolReferenceScroll {{
                background: {colors.surface};
                border: 1px solid {colors.border};
                border-radius: 8px;
            }}
            QWidget#toolReferenceList {{
                background: {colors.surface};
            }}
            QFrame#toolReferenceRow {{
                background: transparent;
                border: none;
                border-bottom: 1px solid {colors.border};
            }}
            QFrame#toolReferenceRow:hover {{
                background: {colors.surface_alt};
            }}
            QLabel#toolReferenceIconBadge {{
                background: {colors.surface_alt};
                border: 1px solid {colors.border_strong};
                border-radius: 8px;
            }}
            QLabel#toolReferenceName {{
                color: {colors.text};
                font-weight: 600;
                font-size: 13px;
            }}
            QLabel#toolReferenceShortcut {{
                color: {colors.button_checked_text};
                background: {colors.accent};
                border-radius: 4px;
                padding: 1px 6px;
                font-size: 11px;
                font-weight: 600;
            }}
            QLabel#toolReferenceDescription {{
                color: {colors.text_muted};
                font-size: 12px;
                padding-top: 2px;
            }}
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        intro = QLabel(
            "Each toolbar icon is shown on the left with a short explanation on the right."
        )
        intro.setObjectName("toolReferenceIntro")
        intro.setWordWrap(True)
        root.addWidget(intro)

        header = QFrame()
        header.setObjectName("toolReferenceHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(4, 0, 4, 0)
        header_layout.setSpacing(0)
        symbol_header = QLabel("Symbol")
        symbol_header.setObjectName("toolReferenceHeaderLabel")
        symbol_header.setFixedWidth(84)
        explanation_header = QLabel("Explanation")
        explanation_header.setObjectName("toolReferenceHeaderLabel")
        header_layout.addWidget(symbol_header)
        header_layout.addWidget(explanation_header, 1)
        root.addWidget(header)

        self.scroll_area = _SmoothScrollArea(self)
        self.scroll_area.setObjectName("toolReferenceScroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        vertical_bar = self.scroll_area.verticalScrollBar()
        vertical_bar.setSingleStep(16)
        vertical_bar.setPageStep(140)

        self.list_widget = QWidget()
        self.list_widget.setObjectName("toolReferenceList")
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(0)

        self.rows: list[QFrame] = []
        for entry in TOOL_HELP_ENTRIES:
            row = self._build_row(entry, icon_provider(entry.tool))
            self.rows.append(row)
            self.list_layout.addWidget(row)
        self.list_layout.addStretch(1)

        self.scroll_area.setWidget(self.list_widget)
        root.addWidget(self.scroll_area, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        close_button = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_button is not None:
            close_button.clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _build_row(self, entry: ToolHelpEntry, icon: QIcon) -> QFrame:
        """
        Builds one tool reference row with symbol and explanation.

        Args:
            entry: Tool help catalog entry.
            icon: Toolbar icon for the tool.

        Returns:
            QFrame: Styled row widget.
        """

        row = QFrame()
        row.setObjectName("toolReferenceRow")
        row.setProperty("toolId", entry.tool)
        row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        layout = QHBoxLayout(row)
        layout.setContentsMargins(12, 12, 14, 12)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        icon_badge = QLabel()
        icon_badge.setObjectName("toolReferenceIconBadge")
        icon_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_badge.setPixmap(icon.pixmap(QSize(28, 28)))
        icon_badge.setFixedSize(56, 56)
        layout.addWidget(icon_badge, 0, Qt.AlignmentFlag.AlignTop)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 2, 0, 0)
        text_column.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)

        name_label = QLabel(entry.name)
        name_label.setObjectName("toolReferenceName")
        title_row.addWidget(name_label, 0, Qt.AlignmentFlag.AlignVCenter)

        if entry.shortcut_hint:
            shortcut_label = QLabel(entry.shortcut_hint)
            shortcut_label.setObjectName("toolReferenceShortcut")
            shortcut_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title_row.addWidget(shortcut_label, 0, Qt.AlignmentFlag.AlignVCenter)

        title_row.addStretch(1)
        text_column.addLayout(title_row)

        description = QLabel(entry.description)
        description.setObjectName("toolReferenceDescription")
        description.setWordWrap(True)
        description.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        description.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        text_column.addWidget(description)
        layout.addLayout(text_column, 1)
        return row

    def tool_row_count(self) -> int:
        """
        Returns the number of tool rows in the reference list.

        Returns:
            int: Row count.
        """

        return len(self.rows)

    def tool_row_texts(self) -> list[tuple[str, str]]:
        """
        Returns name/description pairs for each visible tool row.

        Returns:
            list[tuple[str, str]]: Name and description for each row.
        """

        texts: list[tuple[str, str]] = []
        for row in self.rows:
            name = row.findChild(QLabel, "toolReferenceName")
            description = row.findChild(QLabel, "toolReferenceDescription")
            texts.append(
                (
                    name.text() if name is not None else "",
                    description.text() if description is not None else "",
                )
            )
        return texts
