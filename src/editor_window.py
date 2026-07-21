"""
Main screenshot editing window for SnapAgent.
"""

from __future__ import annotations

import tempfile
from typing import Any

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QFontDatabase,
    QGuiApplication,
    QIcon,
    QKeySequence,
    QPainter,
    QPageLayout,
    QPageSize,
    QPagedPaintDevice,
    QPen,
    QPolygonF,
    QPdfWriter,
    QPixmap,
)
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QComboBox,
    QColorDialog,
    QFrame,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src.constants import (
    ABOUT_AUTHOR,
    ABOUT_WEBSITE,
    APP_FILE_EXTENSION,
    APP_NAME,
)
from src.editor_canvas import EditorCanvas, Tool
from src.models import AnnotationModel
from src.storage import (
    base64_png_to_pixmap,
    build_project_model,
    load_project,
    pixmap_to_base64_png,
    save_project,
)


class EditorWindow(QMainWindow):
    """
    Hosts the SnapAgent screenshot editor UI.
    """

    close_requested = Signal()

    def __init__(self, screenshot: QPixmap) -> None:
        """
        Initializes the editor with a screenshot image.

        Args:
            screenshot: Captured screenshot pixmap.
        """

        super().__init__()
        self.setWindowTitle(f"{APP_NAME} Editor")
        self.resize(1400, 900)
        self._current_project_path = ""
        self._recovery_path = f"{tempfile.gettempdir()}/snapagent-autosave{APP_FILE_EXTENSION}"
        self._minimize_to_tray_on_close = True

        self._record_history = True
        self._history: list[dict[str, Any]] = []
        self._history_labels: list[str] = []
        self._history_index = -1
        self._pending_history_label: str | None = None
        self._syncing_history_list = False
        self._toolbar_groups: list[QWidget] = []
        self._active_tool = Tool.SELECT
        self._locked_tool: str | None = None
        self._one_shot_tool: str | None = None
        self._tool_button_order: list[str] = []
        self._tool_button_labels: dict[str, str] = {}
        self._tool_button_to_key: dict[QToolButton, str] = {}
        self._current_stroke_color = QColor(231, 76, 60, 255)
        self._current_fill_color = QColor(231, 76, 60, 80)
        self._current_text_color = QColor(44, 62, 80, 255)

        container = QWidget(self)
        self.setCentralWidget(container)
        root = QVBoxLayout(container)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.canvas = EditorCanvas()
        self.canvas.set_screenshot(screenshot)
        self.canvas.content_changed.connect(self._on_canvas_changed)
        self.canvas.zoom_changed.connect(self._on_zoom_changed)
        self.canvas.selection_style_changed.connect(self._on_selection_style_changed)
        self.canvas.crop_selection_changed.connect(self._on_crop_state_changed)
        self.canvas.crop_applied.connect(self._on_crop_applied)

        self._toolbar_widget = self._build_toolbar()
        root.addWidget(self._toolbar_widget)
        root.addWidget(self.canvas)

        self.statusBar().showMessage("Ready")
        self._build_menu()
        self._push_history_state()
        self._autosave_timer = self.startTimer(30_000)
        self.setStyleSheet(
            "QMainWindow { background: #1f2430; color: #e7ecf2; }"
            "QMenuBar, QMenu, QStatusBar { background: #232938; color: #e7ecf2; }"
            "QToolButton, QPushButton { background: #2f3543; color: #e7ecf2; border: 1px solid #434d63; border-radius: 4px; padding: 4px 8px; }"
            "QToolButton:checked { background: #2f7dd1; border: 1px solid #2f7dd1; color: white; }"
            "QPushButton:hover, QToolButton:hover { background: #3a4357; }"
            "QSpinBox, QComboBox { background: #2f3543; color: #e7ecf2; border: 1px solid #434d63; border-radius: 4px; padding: 3px; }"
            "QComboBox QAbstractItemView { background: #2a3040; color: #ffffff; selection-background-color: #2f7dd1; selection-color: #ffffff; border: 1px solid #434d63; }"
            "QFrame[toolbarGroup=\"true\"] { border: 1px solid #3b4559; border-radius: 6px; background: #222938; }"
            "QFrame[toolbarGroup=\"true\"] QLabel { color: #ffffff; }"
        )

    def _build_toolbar(self) -> QWidget:
        """
        Creates the slim top tool panel.

        Returns:
            QWidget: Toolbar container widget.
        """

        bar = QWidget(self)
        root_layout = QVBoxLayout(bar)
        root_layout.setContentsMargins(8, 6, 8, 6)
        root_layout.setSpacing(6)

        self._toolbar_groups_container = QWidget(bar)
        self._toolbar_groups_layout = QGridLayout(self._toolbar_groups_container)
        self._toolbar_groups_layout.setContentsMargins(0, 0, 0, 0)
        self._toolbar_groups_layout.setHorizontalSpacing(8)
        self._toolbar_groups_layout.setVerticalSpacing(6)
        root_layout.addWidget(self._toolbar_groups_container)

        palette_colors = [
            QColor("#e74c3c"),
            QColor("#f39c12"),
            QColor("#f1c40f"),
            QColor("#2ecc71"),
            QColor("#1abc9c"),
            QColor("#3498db"),
            QColor("#9b59b6"),
            QColor("#ecf0f1"),
            QColor("#2c3e50"),
            QColor("#000000"),
        ]

        tools_group, tools_layout = self._create_toolbar_group("Tools")
        self._tool_buttons: dict[str, QToolButton] = {}
        for tool_key, label in [
            (Tool.SELECT, "Select"),
            (Tool.RECT, "Rectangle"),
            (Tool.ELLIPSE, "Circle"),
            (Tool.LINE, "Line"),
            (Tool.ARROW, "Arrow"),
            (Tool.TEXT, "Text"),
            (Tool.FILL_BG, "Bg Fill"),
            (Tool.CROP, "Crop"),
        ]:
            button = QToolButton()
            button.setText(label)
            button.setCheckable(True)
            button.setIcon(self._build_tool_icon(tool_key))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.clicked.connect(
                lambda _checked=False, t=tool_key: self._on_tool_button_clicked(t)
            )
            button.installEventFilter(self)
            tools_layout.addWidget(button)
            self._tool_buttons[tool_key] = button
            self._tool_button_order.append(tool_key)
            self._tool_button_labels[tool_key] = label
            self._tool_button_to_key[button] = tool_key
        self._tool_buttons[Tool.SELECT].setChecked(True)

        self.apply_crop_button = QPushButton("Apply Crop")
        self.apply_crop_button.setEnabled(False)
        self.apply_crop_button.clicked.connect(self.canvas.apply_pending_crop)
        tools_layout.addWidget(self.apply_crop_button)

        tools_layout.addWidget(QLabel("Border"))
        self.stroke_size_spin = QSpinBox()
        self.stroke_size_spin.setRange(1, 32)
        self.stroke_size_spin.setValue(3)
        self.stroke_size_spin.valueChanged.connect(self._stroke_width_changed)
        tools_layout.addWidget(self.stroke_size_spin)
        self._toolbar_groups.append(tools_group)

        colors_group = QFrame(self)
        colors_group.setFrameShape(QFrame.Shape.StyledPanel)
        colors_group.setProperty("toolbarGroup", True)
        colors_main_layout = QVBoxLayout(colors_group)
        colors_main_layout.setContentsMargins(6, 4, 6, 4)
        colors_main_layout.setSpacing(4)
        colors_title = QLabel("Color Palette")
        colors_title.setStyleSheet("font-size: 11px; color: #9fb2c9;")
        colors_main_layout.addWidget(colors_title)

        colors_layout = QVBoxLayout()
        colors_layout.setContentsMargins(0, 0, 0, 0)
        colors_layout.setSpacing(4)
        colors_main_layout.addLayout(colors_layout)

        stroke_row = QHBoxLayout()
        stroke_row.setContentsMargins(0, 0, 0, 0)
        stroke_row.setSpacing(4)
        self.stroke_button = QPushButton("Border")
        self.stroke_button.clicked.connect(self._choose_stroke_color)
        stroke_row.addWidget(self.stroke_button)
        for color in palette_colors:
            stroke_row.addWidget(self._create_palette_button(color, "stroke"))
        stroke_row.addWidget(QLabel("Opacity"))
        self.stroke_alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.stroke_alpha_slider.setRange(0, 100)
        self.stroke_alpha_slider.setValue(100)
        self.stroke_alpha_slider.setFixedWidth(90)
        self.stroke_alpha_slider.valueChanged.connect(self._stroke_alpha_changed)
        stroke_row.addWidget(self.stroke_alpha_slider)
        self.stroke_alpha_label = QLabel("100%")
        stroke_row.addWidget(self.stroke_alpha_label)
        stroke_row.addStretch(1)
        colors_layout.addLayout(stroke_row)

        fill_row = QHBoxLayout()
        fill_row.setContentsMargins(0, 0, 0, 0)
        fill_row.setSpacing(4)
        self.fill_button = QPushButton("Background")
        self.fill_button.clicked.connect(self._choose_fill_color)
        fill_row.addWidget(self.fill_button)
        for color in palette_colors:
            fill_row.addWidget(self._create_palette_button(color, "fill"))
        fill_row.addWidget(QLabel("Opacity"))
        self.fill_alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.fill_alpha_slider.setRange(0, 100)
        self.fill_alpha_slider.setValue(31)
        self.fill_alpha_slider.setFixedWidth(90)
        self.fill_alpha_slider.valueChanged.connect(self._fill_alpha_changed)
        fill_row.addWidget(self.fill_alpha_slider)
        self.fill_alpha_label = QLabel("31%")
        fill_row.addWidget(self.fill_alpha_label)
        fill_row.addStretch(1)
        colors_layout.addLayout(fill_row)

        text_row = QHBoxLayout()
        text_row.setContentsMargins(0, 0, 0, 0)
        text_row.setSpacing(4)
        self.text_color_button = QPushButton("Text")
        self.text_color_button.clicked.connect(self._choose_text_color)
        text_row.addWidget(self.text_color_button)
        for color in palette_colors:
            text_row.addWidget(self._create_palette_button(color, "text"))
        text_row.addWidget(QLabel("Opacity"))
        self.text_alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.text_alpha_slider.setRange(0, 100)
        self.text_alpha_slider.setValue(100)
        self.text_alpha_slider.setFixedWidth(90)
        self.text_alpha_slider.valueChanged.connect(self._text_alpha_changed)
        text_row.addWidget(self.text_alpha_slider)
        self.text_alpha_label = QLabel("100%")
        text_row.addWidget(self.text_alpha_label)
        text_row.addStretch(1)
        colors_layout.addLayout(text_row)
        self._toolbar_groups.append(colors_group)

        text_group, text_layout = self._create_toolbar_group("Text Style")
        text_layout.addWidget(QLabel("Font"))
        self.font_family_combo = QComboBox()
        self.font_family_combo.setMinimumWidth(220)
        self.font_family_combo.addItems(sorted(QFontDatabase.families()))
        self.font_family_combo.currentTextChanged.connect(self._font_family_changed)
        text_layout.addWidget(self.font_family_combo)

        text_layout.addWidget(QLabel("Size"))
        self.font_size_combo = QComboBox()
        self.font_size_combo.addItems(
            [
                "8",
                "9",
                "10",
                "11",
                "12",
                "14",
                "16",
                "18",
                "20",
                "24",
                "28",
                "32",
                "40",
                "48",
                "56",
                "64",
                "72",
                "96",
                "120",
            ]
        )
        self.font_size_combo.setCurrentText("16")
        self.font_size_combo.currentTextChanged.connect(self._font_size_changed)
        text_layout.addWidget(self.font_size_combo)
        self._toolbar_groups.append(text_group)

        history_group, history_layout = self._create_toolbar_group("History")
        self.history_undo_button = QPushButton("Undo")
        self.history_undo_button.clicked.connect(self.undo)
        history_layout.addWidget(self.history_undo_button)
        self.history_redo_button = QPushButton("Redo")
        self.history_redo_button.clicked.connect(self.redo)
        history_layout.addWidget(self.history_redo_button)
        self.history_list_combo = QComboBox()
        self.history_list_combo.setMinimumWidth(220)
        self.history_list_combo.currentIndexChanged.connect(self._on_history_entry_selected)
        history_layout.addWidget(self.history_list_combo)
        self.history_status_label = QLabel("1/1")
        history_layout.addWidget(self.history_status_label)
        self._toolbar_groups.append(history_group)

        zoom_group, zoom_layout = self._create_toolbar_group("Zoom")
        self.zoom_label = QLabel("100%")
        zoom_layout.addWidget(self.zoom_label)

        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(10, 400)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(140)
        self.zoom_slider.setToolTip("Zoom: left smaller, right larger")
        self.zoom_slider.valueChanged.connect(self._zoom_slider_changed)
        zoom_layout.addWidget(self.zoom_slider)

        self.zoom_in_button = QPushButton("+")
        self.zoom_in_button.clicked.connect(self.canvas.zoom_in)
        zoom_layout.addWidget(self.zoom_in_button)
        self.zoom_out_button = QPushButton("-")
        self.zoom_out_button.clicked.connect(self.canvas.zoom_out)
        zoom_layout.addWidget(self.zoom_out_button)
        self.zoom_reset_button = QPushButton("Reset")
        self.zoom_reset_button.clicked.connect(self.canvas.reset_zoom)
        zoom_layout.addWidget(self.zoom_reset_button)
        self._toolbar_groups.append(zoom_group)
        self._reflow_toolbar_groups()
        self._update_color_button_preview(self.stroke_button, QColor("#e74c3c"))
        self._update_color_button_preview(self.fill_button, QColor(231, 76, 60, 80))
        self._update_color_button_preview(self.text_color_button, QColor("#2c3e50"))
        self._apply_toolbar_tooltips()
        return bar

    def _reflow_toolbar_groups(self) -> None:
        """
        Reflows toolbar groups into multiple rows based on available width.

        Returns:
            None
        """

        if not hasattr(self, "_toolbar_groups_layout"):
            return
        layout = self._toolbar_groups_layout
        while layout.count() > 0:
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(self._toolbar_groups_container)

        if not self._toolbar_groups:
            return

        available_width = max(320, self._toolbar_groups_container.width())
        x_cursor = 0
        row = 0
        col = 0
        for group in self._toolbar_groups:
            group_width = group.sizeHint().width()
            spacing = layout.horizontalSpacing()
            if col > 0 and x_cursor + group_width > available_width:
                row += 1
                col = 0
                x_cursor = 0
            layout.addWidget(group, row, col)
            x_cursor += group_width + max(0, spacing)
            col += 1

    def _build_tool_icon(self, tool: str) -> QIcon:
        """
        Builds a compact vector icon for one toolbar drawing tool.

        Args:
            tool: Tool identifier.

        Returns:
            QIcon: Rendered icon.
        """

        pixmap = QPixmap(18, 18)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        stroke_pen = QPen(QColor("#d7e3f1"), 1.6)
        accent_pen = QPen(QColor("#4aa3ff"), 1.6)

        if tool == Tool.SELECT:
            painter.setPen(stroke_pen)
            pointer_shape = QPolygonF(
                [
                    QPointF(3.0, 2.5),
                    QPointF(3.0, 14.5),
                    QPointF(7.0, 10.8),
                    QPointF(10.8, 15.5),
                    QPointF(12.4, 14.1),
                    QPointF(8.6, 9.6),
                    QPointF(14.5, 9.2),
                ]
            )
            painter.drawPolygon(pointer_shape)
        elif tool == Tool.RECT:
            painter.setPen(stroke_pen)
            painter.setBrush(QBrush(QColor(74, 163, 255, 70)))
            painter.drawRect(QRectF(3.0, 4.0, 12.0, 10.0))
        elif tool == Tool.ELLIPSE:
            painter.setPen(stroke_pen)
            painter.setBrush(QBrush(QColor(74, 163, 255, 70)))
            painter.drawEllipse(QRectF(3.0, 4.0, 12.0, 10.0))
        elif tool == Tool.LINE:
            painter.setPen(stroke_pen)
            painter.drawLine(3, 14, 15, 4)
        elif tool == Tool.ARROW:
            painter.setPen(accent_pen)
            painter.drawLine(3, 14, 13, 5)
            painter.drawLine(13, 5, 11, 5)
            painter.drawLine(13, 5, 13, 7)
        elif tool == Tool.TEXT:
            painter.setPen(stroke_pen)
            text_font = painter.font()
            text_font.setBold(True)
            text_font.setPointSize(10)
            painter.setFont(text_font)
            painter.drawText(QRectF(2.0, 1.0, 14.0, 16.0), "T")
        elif tool == Tool.FILL_BG:
            painter.setPen(stroke_pen)
            painter.setBrush(QBrush(QColor(74, 163, 255, 100)))
            painter.drawRect(QRectF(2.5, 9.0, 13.0, 6.0))
            painter.drawLine(5, 8, 9, 4)
            painter.drawLine(9, 4, 12, 7)
        elif tool == Tool.CROP:
            painter.setPen(accent_pen)
            painter.drawLine(3, 3, 9, 3)
            painter.drawLine(3, 3, 3, 9)
            painter.drawLine(15, 15, 9, 15)
            painter.drawLine(15, 15, 15, 9)
            painter.setPen(stroke_pen)
            painter.drawRect(QRectF(5.0, 5.0, 8.0, 8.0))
        else:
            painter.setPen(stroke_pen)
            painter.drawRect(QRectF(4.0, 4.0, 10.0, 10.0))

        painter.end()
        return QIcon(pixmap)

    def _create_toolbar_group(self, title: str) -> tuple[QFrame, QHBoxLayout]:
        """
        Creates a framed toolbar group with a title label.

        Args:
            title: Visible group caption.

        Returns:
            tuple[QFrame, QHBoxLayout]: Group widget and content layout.
        """

        frame = QFrame(self)
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setProperty("toolbarGroup", True)
        group_layout = QVBoxLayout(frame)
        group_layout.setContentsMargins(6, 4, 6, 4)
        group_layout.setSpacing(4)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 11px; color: #9fb2c9;")
        group_layout.addWidget(title_label)

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(4)
        group_layout.addLayout(content_layout)
        return frame, content_layout

    def _create_palette_button(self, color: QColor, target: str) -> QPushButton:
        """
        Builds one compact palette button for direct color assignment.

        Args:
            color: Palette color to apply.
            target: Style target key (stroke, fill, text).

        Returns:
            QPushButton: Palette button.
        """

        button = QPushButton("")
        button.setFixedSize(18, 18)
        button.setToolTip(f"Apply {color.name()} to {target}")
        button.setStyleSheet(
            "QPushButton {"
            f"background: {color.name(QColor.NameFormat.HexArgb)};"
            "border: 1px solid #59657c;"
            "border-radius: 3px;"
            "padding: 0px;"
            "}"
        )
        button.clicked.connect(
            lambda _checked=False, t=target, c=QColor(color): self._apply_palette_color(
                target=t,
                color=c,
            )
        )
        return button

    def _apply_toolbar_tooltips(self) -> None:
        """
        Adds English tooltip text to all toolbar controls.

        Returns:
            None
        """

        tooltips = {
            Tool.SELECT: "Select and move annotations.",
            Tool.RECT: "Draw one rectangle. Double-click to lock tool.",
            Tool.ELLIPSE: "Draw one ellipse. Double-click to lock tool.",
            Tool.LINE: "Draw one line. Double-click to lock tool.",
            Tool.ARROW: "Draw one arrow. Double-click to lock tool.",
            Tool.TEXT: "Insert one text item. Double-click to lock tool.",
            Tool.FILL_BG: "Fill one area. Double-click to lock tool.",
            Tool.CROP: "Create a crop selection area.",
        }
        for tool_key, button in self._tool_buttons.items():
            button.setToolTip(tooltips.get(tool_key, "Use this tool."))

        self.apply_crop_button.setToolTip("Apply current crop selection.")
        self.stroke_size_spin.setToolTip("Set border line width.")
        self.stroke_button.setToolTip("Open border color picker.")
        self.fill_button.setToolTip("Open background color picker.")
        self.text_color_button.setToolTip("Open text color picker.")
        self.stroke_alpha_slider.setToolTip("Set border opacity.")
        self.fill_alpha_slider.setToolTip("Set background opacity.")
        self.text_alpha_slider.setToolTip("Set text opacity.")
        self.font_family_combo.setToolTip("Select text font family.")
        self.font_size_combo.setToolTip("Select text font size.")
        self.zoom_slider.setToolTip("Adjust zoom level.")
        self.zoom_in_button.setToolTip("Zoom in.")
        self.zoom_out_button.setToolTip("Zoom out.")
        self.zoom_reset_button.setToolTip("Reset zoom to fit.")
        self.history_undo_button.setToolTip("Undo the last change.")
        self.history_redo_button.setToolTip("Redo the last undone change.")
        self.history_list_combo.setToolTip("History entries with action names.")
        self.history_status_label.setToolTip("Current history position.")

    def _build_menu(self) -> None:
        """
        Builds application menus and actions.

        Returns:
            None
        """

        menu = self.menuBar()
        file_menu = menu.addMenu("File")
        edit_menu = menu.addMenu("Edit")
        help_menu = menu.addMenu("Help")

        open_action = QAction("Open Project...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.setToolTip("Open an existing SnapAgent project.")
        open_action.triggered.connect(self.open_project)
        file_menu.addAction(open_action)

        save_action = QAction("Save Project As...", self)
        save_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_action.setToolTip("Save project under a new file name.")
        save_action.triggered.connect(self.save_project_as)
        file_menu.addAction(save_action)

        save_action = QAction("Save Project", self)
        save_action.setToolTip("Save changes to the current project.")
        save_action.triggered.connect(self.save_project)
        file_menu.addAction(save_action)

        export_action = QAction("Export...", self)
        export_action.setShortcut(QKeySequence.StandardKey.Save)
        export_action.setToolTip("Open export dialog for image or PDF.")
        export_action.triggered.connect(self.export_with_dialog)
        file_menu.addAction(export_action)

        export_png = QAction("Export as PNG...", self)
        export_png.setToolTip("Export the composited image as PNG.")
        export_png.triggered.connect(lambda: self.export_image("PNG"))
        file_menu.addAction(export_png)

        export_jpg = QAction("Export as JPEG...", self)
        export_jpg.setToolTip("Export the composited image as JPEG.")
        export_jpg.triggered.connect(lambda: self.export_image("JPG"))
        file_menu.addAction(export_jpg)

        export_pdf = QAction("Export as PDF...", self)
        export_pdf.setToolTip("Export the composited image as PDF.")
        export_pdf.triggered.connect(self.export_pdf)
        file_menu.addAction(export_pdf)

        file_menu.addSeparator()

        print_action = QAction("Print...", self)
        print_action.setShortcut(QKeySequence.StandardKey.Print)
        print_action.setToolTip("Print the composited image.")
        print_action.triggered.connect(self.print_image)
        file_menu.addAction(print_action)

        file_menu.addSeparator()

        close_action = QAction("Close", self)
        close_action.setShortcut(QKeySequence.StandardKey.Close)
        close_action.setToolTip("Close this editor tab.")
        close_action.triggered.connect(self.close)
        file_menu.addAction(close_action)

        self.undo_action = QAction("Undo", self)
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.setToolTip("Undo the last change.")
        self.undo_action.triggered.connect(self.undo)
        edit_menu.addAction(self.undo_action)

        self.redo_action = QAction("Redo", self)
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.redo_action.setShortcuts(
            [
                QKeySequence.StandardKey.Redo,
                QKeySequence("Ctrl+Shift+Z"),
            ]
        )
        self.redo_action.setToolTip("Redo the last undone change.")
        self.redo_action.triggered.connect(self.redo)
        edit_menu.addAction(self.redo_action)

        paste_action = QAction("Paste", self)
        paste_action.setShortcut(QKeySequence.StandardKey.Paste)
        paste_action.setToolTip("Paste text or image from clipboard.")
        paste_action.triggered.connect(lambda: self.canvas.paste_from_clipboard())
        edit_menu.addAction(paste_action)

        copy_image_action = QAction("Copy Image", self)
        copy_image_action.setShortcut(QKeySequence.StandardKey.Copy)
        copy_image_action.setToolTip("Copy current composited image to clipboard.")
        copy_image_action.triggered.connect(self.copy_current_image_to_clipboard)
        edit_menu.addAction(copy_image_action)

        about_action = QAction("About", self)
        about_action.setToolTip("Show application information.")
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

        shortcuts_action = QAction("Shortcuts & Manual", self)
        shortcuts_action.setToolTip("Show manual and keyboard shortcuts.")
        shortcuts_action.triggered.connect(self.show_manual)
        help_menu.addAction(shortcuts_action)

        shortcuts_reference_action = QAction("Keyboard Shortcuts", self)
        shortcuts_reference_action.setToolTip("Show keyboard shortcut reference.")
        shortcuts_reference_action.triggered.connect(self.show_shortcuts_reference)
        help_menu.addAction(shortcuts_reference_action)

        self._update_undo_redo_actions()

    def _set_tool(self, tool: str) -> None:
        """
        Sets active tool and updates button selection state.

        Args:
            tool: Tool identifier.

        Returns:
            None
        """

        self._active_tool = tool
        for key, button in self._tool_buttons.items():
            button.setChecked(key == tool)
        self.canvas.set_tool(tool)
        self.statusBar().showMessage(f"Tool: {tool}")

    def eventFilter(self, watched, event) -> bool:
        """
        Handles double-click locking for drawing tool buttons.

        Args:
            watched: Watched QObject.
            event: Incoming Qt event.

        Returns:
            bool: True when handled.
        """

        if isinstance(watched, QToolButton):
            tool_key = self._tool_button_to_key.get(watched)
            if tool_key is not None and event.type() == QEvent.Type.MouseButtonDblClick:
                self._toggle_tool_lock(tool_key)
                return True
        return super().eventFilter(watched, event)

    def _is_lockable_tool(self, tool: str) -> bool:
        """
        Indicates whether a tool supports drawing lock mode.

        Args:
            tool: Tool identifier.

        Returns:
            bool: True when tool can be locked.
        """

        return tool in {
            Tool.RECT,
            Tool.ELLIPSE,
            Tool.LINE,
            Tool.ARROW,
            Tool.TEXT,
            Tool.FILL_BG,
        }

    def _on_tool_button_clicked(self, tool: str) -> None:
        """
        Handles normal single-click behavior for tool buttons.

        Args:
            tool: Clicked tool identifier.

        Returns:
            None
        """

        if self._locked_tool is not None and tool == self._locked_tool:
            self._clear_tool_lock()
            self._set_tool(Tool.SELECT)
            self._one_shot_tool = None
            return

        if tool == Tool.SELECT:
            self._clear_tool_lock()
            self._one_shot_tool = None
            self._set_tool(Tool.SELECT)
            return

        if self._locked_tool is not None and tool != self._locked_tool:
            self._clear_tool_lock()

        self._set_tool(tool)
        self._one_shot_tool = tool if self._is_lockable_tool(tool) else None

    def _toggle_tool_lock(self, tool: str) -> None:
        """
        Enables or disables persistent lock mode for one drawing tool.

        Args:
            tool: Tool identifier.

        Returns:
            None
        """

        if not self._is_lockable_tool(tool):
            self._one_shot_tool = None
            self._set_tool(tool)
            return

        if self._locked_tool == tool:
            self._clear_tool_lock()
            self._set_tool(Tool.SELECT)
            self._one_shot_tool = None
            return

        self._locked_tool = tool
        self._one_shot_tool = None
        self._update_tool_lock_visuals()
        self._set_tool(tool)

    def _clear_tool_lock(self) -> None:
        """
        Disables any active tool lock and updates button visuals.

        Returns:
            None
        """

        self._locked_tool = None
        self._update_tool_lock_visuals()

    def _update_tool_lock_visuals(self) -> None:
        """
        Updates tool button captions and lock symbol visibility.

        Returns:
            None
        """

        for tool_key in self._tool_button_order:
            button = self._tool_buttons[tool_key]
            base_label = self._tool_button_labels[tool_key]
            if tool_key == self._locked_tool:
                button.setText(f"{base_label} 🔒")
            else:
                button.setText(base_label)

    def _set_next_history_label(self, label: str) -> None:
        """
        Sets a pending label for the next history snapshot.

        Args:
            label: Action label shown in history list.

        Returns:
            None
        """

        self._pending_history_label = label.strip() or "Edit"

    def _consume_history_label(self) -> str:
        """
        Resolves the next history label from pending or canvas action.

        Returns:
            str: Chosen history label.
        """

        if self._pending_history_label:
            label = self._pending_history_label
            self._pending_history_label = None
            return label
        return self.canvas.consume_last_action_label()

    def _choose_stroke_color(self) -> None:
        """
        Opens alpha-enabled color picker for stroke color.

        Returns:
            None
        """

        color = QColorDialog.getColor(
            options=QColorDialog.ColorDialogOption.ShowAlphaChannel,
            parent=self,
            title="Select Stroke Color",
        )
        if color.isValid():
            self._set_next_history_label("Change border color")
            self._set_target_color("stroke", color, apply_to_canvas=False)
            self._push_history_state()

    def _choose_fill_color(self) -> None:
        """
        Opens alpha-enabled color picker for fill color.

        Returns:
            None
        """

        color = QColorDialog.getColor(
            options=QColorDialog.ColorDialogOption.ShowAlphaChannel,
            parent=self,
            title="Select Fill Color",
        )
        if color.isValid():
            self._set_next_history_label("Change background color")
            self._set_target_color("fill", color, apply_to_canvas=False)
            self._push_history_state()

    def _choose_text_color(self) -> None:
        """
        Opens alpha-enabled color picker for text color.

        Returns:
            None
        """

        color = QColorDialog.getColor(
            options=QColorDialog.ColorDialogOption.ShowAlphaChannel,
            parent=self,
            title="Select Text Color",
        )
        if color.isValid():
            self._set_next_history_label("Change text color")
            self._set_target_color("text", color, apply_to_canvas=False)
            self._push_history_state()

    def _apply_palette_color(self, target: str, color: QColor) -> None:
        """
        Applies one predefined palette color to a style target.

        Args:
            target: Style target key (stroke, fill, text).
            color: Selected palette color.

        Returns:
            None
        """

        current = self._color_for_target(target)
        updated = QColor(color)
        updated.setAlpha(current.alpha())
        if target == "stroke":
            self._set_next_history_label("Apply border palette color")
        elif target == "fill":
            self._set_next_history_label("Apply background palette color")
        else:
            self._set_next_history_label("Apply text palette color")
        self._set_target_color(target, updated)
        self._push_history_state()

    def _set_target_color(self, target: str, color: QColor, apply_to_canvas: bool = True) -> None:
        """
        Applies one target color to canvas and toolbar state.

        Args:
            target: Style target key (stroke, fill, text).
            color: New target color.
            apply_to_canvas: True to apply style changes to selected canvas items.

        Returns:
            None
        """

        if target == "stroke":
            self._current_stroke_color = QColor(color)
            if apply_to_canvas:
                self.canvas.set_style(stroke_color=color)
            self._update_color_button_preview(self.stroke_button, color)
            self._set_alpha_slider_value(self.stroke_alpha_slider, self.stroke_alpha_label, color)
            return
        if target == "fill":
            self._current_fill_color = QColor(color)
            if apply_to_canvas:
                self.canvas.set_style(fill_color=color)
            self._update_color_button_preview(self.fill_button, color)
            self._set_alpha_slider_value(self.fill_alpha_slider, self.fill_alpha_label, color)
            return
        self._current_text_color = QColor(color)
        if apply_to_canvas:
            self.canvas.set_style(text_color=color)
        self._update_color_button_preview(self.text_color_button, color)
        self._set_alpha_slider_value(self.text_alpha_slider, self.text_alpha_label, color)

    def _color_for_target(self, target: str) -> QColor:
        """
        Returns current toolbar color for one style target.

        Args:
            target: Style target key.

        Returns:
            QColor: Current target color.
        """

        if target == "stroke":
            return QColor(self._current_stroke_color)
        if target == "fill":
            return QColor(self._current_fill_color)
        return QColor(self._current_text_color)

    def _update_color_button_preview(self, button: QPushButton, color: QColor) -> None:
        """
        Sets the button background to preview the active color.

        Args:
            button: Button to style.
            color: Displayed color.

        Returns:
            None
        """

        button.setStyleSheet(
            "QPushButton {"
            f"background: {color.name(QColor.NameFormat.HexArgb)};"
            "color: #e7ecf2;"
            "border: 1px solid #434d63;"
            "border-radius: 4px;"
            "padding: 4px 8px;"
            "}"
        )

    def _stroke_width_changed(self, value: int) -> None:
        """
        Updates active and selected item stroke width.

        Args:
            value: New stroke width.

        Returns:
            None
        """

        self._set_next_history_label("Change border width")
        self.canvas.set_style(stroke_width=float(value))
        self._push_history_state()

    def _stroke_alpha_changed(self, value: int) -> None:
        """
        Updates stroke opacity from toolbar slider.

        Args:
            value: Opacity percentage.

        Returns:
            None
        """

        self._set_next_history_label("Change border opacity")
        self._apply_target_alpha("stroke", value)
        self._push_history_state()

    def _fill_alpha_changed(self, value: int) -> None:
        """
        Updates background opacity from toolbar slider.

        Args:
            value: Opacity percentage.

        Returns:
            None
        """

        self._set_next_history_label("Change background opacity")
        self._apply_target_alpha("fill", value)
        self._push_history_state()

    def _text_alpha_changed(self, value: int) -> None:
        """
        Updates text opacity from toolbar slider.

        Args:
            value: Opacity percentage.

        Returns:
            None
        """

        self._set_next_history_label("Change text opacity")
        self._apply_target_alpha("text", value)
        self._push_history_state()

    def _apply_target_alpha(self, target: str, value: int) -> None:
        """
        Applies alpha percentage to current target color.

        Args:
            target: Style target key.
            value: Opacity percentage from 0 to 100.

        Returns:
            None
        """

        alpha_value = max(0, min(255, round((value / 100.0) * 255)))
        color = self._color_for_target(target)
        color.setAlpha(alpha_value)
        self._set_target_color(target, color)

    def _set_alpha_slider_value(self, slider: QSlider, label: QLabel, color: QColor) -> None:
        """
        Synchronizes one opacity slider and label from color alpha.

        Args:
            slider: Slider control for opacity.
            label: Label showing opacity percent.
            color: Source color with alpha channel.

        Returns:
            None
        """

        percent = max(0, min(100, round((color.alpha() / 255.0) * 100)))
        slider.blockSignals(True)
        slider.setValue(percent)
        slider.blockSignals(False)
        label.setText(f"{percent}%")

    def _set_font_size_combo_value(self, value: int) -> None:
        """
        Synchronizes font-size select box with one numeric value.

        Args:
            value: Font size in points.

        Returns:
            None
        """

        text_value = str(value)
        if self.font_size_combo.findText(text_value) < 0:
            self.font_size_combo.addItem(text_value)
        self.font_size_combo.blockSignals(True)
        self.font_size_combo.setCurrentText(text_value)
        self.font_size_combo.blockSignals(False)

    def _font_size_changed(self, value: str) -> None:
        """
        Updates active and selected text font size.

        Args:
            value: New font size in points as text.

        Returns:
            None
        """

        if not value.isdigit():
            return
        self._set_next_history_label("Change font size")
        self.canvas.set_style(font_size=int(value))
        self._push_history_state()

    def _font_family_changed(self, value: str) -> None:
        """
        Updates active and selected text font family.

        Args:
            value: New font family name.

        Returns:
            None
        """

        self._set_next_history_label("Change font family")
        self.canvas.set_style(font_family=value)
        self._push_history_state()

    def _on_zoom_changed(self, zoom_factor: float) -> None:
        """
        Refreshes zoom status text.

        Args:
            zoom_factor: Current zoom factor.

        Returns:
            None
        """

        zoom_percent = int(zoom_factor * 100)
        self.zoom_label.setText(f"{zoom_percent}%")
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(max(10, min(400, zoom_percent)))
        self.zoom_slider.blockSignals(False)

    def _zoom_slider_changed(self, value: int) -> None:
        """
        Applies absolute zoom from slider percentage value.

        Args:
            value: Slider zoom percentage.

        Returns:
            None
        """

        self.canvas.set_zoom_factor(float(value) / 100.0)

    def _on_canvas_changed(self) -> None:
        """
        Captures history state when canvas content changes.

        Returns:
            None
        """

        action_label = self.canvas.consume_last_action_label()
        self._set_next_history_label(action_label)
        self._push_history_state()
        self._apply_one_shot_tool_completion(action_label)

    def _apply_one_shot_tool_completion(self, action_label: str) -> None:
        """
        Switches back to select after one-shot drawing completion.

        Args:
            action_label: Last canvas action label.

        Returns:
            None
        """

        if self._one_shot_tool is None:
            return
        if self._locked_tool is not None:
            return
        expected_action_by_tool = {
            Tool.RECT: "Draw rectangle",
            Tool.ELLIPSE: "Draw ellipse",
            Tool.LINE: "Draw line",
            Tool.ARROW: "Draw arrow",
            Tool.TEXT: "Insert text",
            Tool.FILL_BG: "Fill background",
        }
        expected = expected_action_by_tool.get(self._one_shot_tool)
        if expected is None:
            return
        if action_label != expected:
            return
        self._one_shot_tool = None
        self._set_tool(Tool.SELECT)

    def _on_selection_style_changed(self, payload: dict[str, Any]) -> None:
        """
        Synchronizes toolbar controls to selected object style.

        Args:
            payload: Selected style payload.

        Returns:
            None
        """

        stroke_width = payload.get("stroke_width")
        if isinstance(stroke_width, (float, int)):
            self.stroke_size_spin.blockSignals(True)
            self.stroke_size_spin.setValue(max(1, int(stroke_width)))
            self.stroke_size_spin.blockSignals(False)

        stroke_rgba = payload.get("stroke_rgba")
        if isinstance(stroke_rgba, list) and len(stroke_rgba) == 4:
            color = QColor(
                int(stroke_rgba[0]),
                int(stroke_rgba[1]),
                int(stroke_rgba[2]),
                int(stroke_rgba[3]),
            )
            self._set_target_color("stroke", color)

        fill_rgba = payload.get("fill_rgba")
        if isinstance(fill_rgba, list) and len(fill_rgba) == 4:
            color = QColor(
                int(fill_rgba[0]),
                int(fill_rgba[1]),
                int(fill_rgba[2]),
                int(fill_rgba[3]),
            )
            self._set_target_color("fill", color)

        text_rgba = payload.get("text_rgba")
        if isinstance(text_rgba, list) and len(text_rgba) == 4:
            color = QColor(
                int(text_rgba[0]),
                int(text_rgba[1]),
                int(text_rgba[2]),
                int(text_rgba[3]),
            )
            self._set_target_color("text", color)

        font_size = payload.get("font_size")
        if isinstance(font_size, int):
            self._set_font_size_combo_value(font_size)
        font_family = payload.get("font_family")
        if isinstance(font_family, str) and font_family.strip():
            self.font_family_combo.blockSignals(True)
            self.font_family_combo.setCurrentText(font_family.strip())
            self.font_family_combo.blockSignals(False)

    def _on_crop_state_changed(self, is_active: bool) -> None:
        """
        Enables or disables crop apply button.

        Args:
            is_active: True when crop selection exists.

        Returns:
            None
        """

        self.apply_crop_button.setEnabled(is_active)

    def _on_crop_applied(self) -> None:
        """
        Switches back to select tool after crop apply.

        Returns:
            None
        """

        self._one_shot_tool = None
        self._clear_tool_lock()
        self._set_tool(Tool.SELECT)

    def _serialize_state(self) -> dict[str, Any]:
        """
        Serializes complete editor state for undo history.

        Returns:
            dict[str, Any]: Snapshot payload.
        """

        return {
            "screenshot_png_base64": pixmap_to_base64_png(self.canvas.screenshot()),
            "annotations": [item.to_dict() for item in self.canvas.collect_annotations()],
        }

    def _restore_state(self, snapshot: dict[str, Any]) -> None:
        """
        Restores editor state from a history snapshot.

        Args:
            snapshot: Stored snapshot payload.

        Returns:
            None
        """

        screenshot = base64_png_to_pixmap(str(snapshot["screenshot_png_base64"]))
        annotations = [
            AnnotationModel.from_dict(item)
            for item in list(snapshot.get("annotations", []))
            if isinstance(item, dict)
        ]

        self._record_history = False
        self.canvas.set_screenshot(screenshot)
        self.canvas.load_annotations(annotations)
        self._record_history = True

    def _push_history_state(self) -> None:
        """
        Adds the current state to the undo history.

        Returns:
            None
        """

        if not self._record_history:
            return
        snapshot = self._serialize_state()
        if self._history and snapshot == self._history[self._history_index]:
            self._pending_history_label = None
            return
        label = self._consume_history_label()
        self._history = self._history[: self._history_index + 1]
        self._history_labels = self._history_labels[: self._history_index + 1]
        self._history.append(snapshot)
        if not self._history_labels:
            self._history_labels.append("Initial state")
        else:
            self._history_labels.append(label)
        self._history_index += 1
        self._update_undo_redo_actions()

    def _update_undo_redo_actions(self) -> None:
        """
        Enables or disables undo and redo actions.

        Returns:
            None
        """

        can_undo = self._history_index > 0
        can_redo = self._history_index < len(self._history) - 1
        self.undo_action.setEnabled(can_undo)
        self.redo_action.setEnabled(can_redo)
        self.history_undo_button.setEnabled(can_undo)
        self.history_redo_button.setEnabled(can_redo)
        self.history_list_combo.setEnabled(bool(self._history))
        total_states = max(1, len(self._history))
        current_state = max(1, self._history_index + 1)
        self.history_status_label.setText(f"{current_state}/{total_states}")
        self._refresh_history_list()

    def _refresh_history_list(self) -> None:
        """
        Synchronizes visible history list entries and current position.

        Returns:
            None
        """

        self._syncing_history_list = True
        self.history_list_combo.clear()
        for index, label in enumerate(self._history_labels, start=1):
            self.history_list_combo.addItem(f"{index}: {label}")
        if self._history_index >= 0:
            self.history_list_combo.setCurrentIndex(self._history_index)
        self._syncing_history_list = False

    def _on_history_entry_selected(self, index: int) -> None:
        """
        Restores a specific history entry selected in the history list.

        Args:
            index: Selected history index.

        Returns:
            None
        """

        if self._syncing_history_list:
            return
        if index < 0 or index >= len(self._history):
            return
        if index == self._history_index:
            return
        self._history_index = index
        self._restore_state(self._history[self._history_index])
        self._update_undo_redo_actions()

    def undo(self) -> None:
        """
        Restores the previous history snapshot.

        Returns:
            None
        """

        if self._history_index <= 0:
            return
        self._history_index -= 1
        self._restore_state(self._history[self._history_index])
        self._update_undo_redo_actions()

    def redo(self) -> None:
        """
        Restores the next history snapshot.

        Returns:
            None
        """

        if self._history_index >= len(self._history) - 1:
            return
        self._history_index += 1
        self._restore_state(self._history[self._history_index])
        self._update_undo_redo_actions()

    def save_project_as(self) -> None:
        """
        Saves current screenshot project to a SnapAgent file.

        Returns:
            None
        """

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Project",
            "",
            f"{APP_NAME} Project (*{APP_FILE_EXTENSION})",
        )
        if not file_path:
            return
        if not file_path.lower().endswith(APP_FILE_EXTENSION):
            file_path = f"{file_path}{APP_FILE_EXTENSION}"
        model = build_project_model(
            screenshot=self.canvas.screenshot(),
            annotation_models=self.canvas.collect_annotations(),
        )
        save_project(file_path, model)
        self._current_project_path = file_path
        self.statusBar().showMessage("Project saved")
        self._update_window_title()

    def save_project(self) -> None:
        """
        Saves project to current path or opens Save As.

        Returns:
            None
        """

        if not self._current_project_path:
            self.save_project_as()
            return
        model = build_project_model(
            screenshot=self.canvas.screenshot(),
            annotation_models=self.canvas.collect_annotations(),
        )
        save_project(self._current_project_path, model)
        self.statusBar().showMessage("Project saved")

    def open_project(self) -> None:
        """
        Loads a SnapAgent project from disk.

        Returns:
            None
        """

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project",
            "",
            f"{APP_NAME} Project (*{APP_FILE_EXTENSION});;Legacy Project (*.lshot *.json)",
        )
        if not file_path:
            return
        model = load_project(file_path)
        self._record_history = False
        self.canvas.set_screenshot(base64_png_to_pixmap(model.screenshot_png_base64))
        self.canvas.load_annotations(model.annotations)
        self._record_history = True
        self._history.clear()
        self._history_labels.clear()
        self._history_index = -1
        self._push_history_state()
        self._current_project_path = file_path
        self._update_window_title()
        self.statusBar().showMessage("Project loaded")

    def export_image(self, fmt: str) -> None:
        """
        Exports composited image to PNG/JPG formats.

        Args:
            fmt: Target format (PNG/JPG).

        Returns:
            None
        """

        ext = fmt.lower()
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            f"Export as {fmt}",
            "",
            f"{fmt} Files (*.{ext});;All Files (*)",
        )
        if not file_path:
            return
        if fmt == "PNG" and not file_path.lower().endswith(".png"):
            file_path = f"{file_path}.png"
        if fmt == "JPG" and not file_path.lower().endswith((".jpg", ".jpeg")):
            file_path = f"{file_path}.jpg"
        pixmap = self.canvas.export_composited_pixmap()
        pixmap.save(file_path, fmt)
        self.statusBar().showMessage(f"Exported {fmt}")

    def export_with_dialog(self) -> None:
        """
        Opens one unified export dialog for PNG, JPG, and PDF.

        Returns:
            None
        """

        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export",
            "",
            "PNG Files (*.png);;JPEG Files (*.jpg *.jpeg);;PDF Files (*.pdf)",
        )
        if not file_path:
            return

        if "PNG" in selected_filter:
            if not file_path.lower().endswith(".png"):
                file_path = f"{file_path}.png"
            self.canvas.export_composited_pixmap().save(file_path, "PNG")
            self.statusBar().showMessage("Exported PNG")
            return

        if "JPEG" in selected_filter:
            if not file_path.lower().endswith((".jpg", ".jpeg")):
                file_path = f"{file_path}.jpg"
            self.canvas.export_composited_pixmap().save(file_path, "JPG")
            self.statusBar().showMessage("Exported JPG")
            return

        if not file_path.lower().endswith(".pdf"):
            file_path = f"{file_path}.pdf"
        self._write_pdf_to_path(file_path)
        self.statusBar().showMessage("Exported PDF")

    def export_pdf(self) -> None:
        """
        Exports composited screenshot as a PDF page.

        Returns:
            None
        """

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export as PDF",
            "",
            "PDF Files (*.pdf);;All Files (*)",
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".pdf"):
            file_path = f"{file_path}.pdf"
        self._write_pdf_to_path(file_path)
        self.statusBar().showMessage("Exported PDF")

    def _write_pdf_to_path(self, file_path: str) -> None:
        """
        Writes current composited image as PDF to target path.

        Args:
            file_path: PDF output path.

        Returns:
            None
        """

        writer = QPdfWriter(file_path)
        writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        writer.setPageOrientation(QPageLayout.Orientation.Landscape)
        writer.setResolution(300)
        writer.setColorModel(QPagedPaintDevice.ColorModel.Rgb)

        pixmap = self.canvas.export_composited_pixmap()
        painter = QPainter(writer)
        page_rect = writer.pageLayout().paintRectPixels(writer.resolution())
        scaled = pixmap.scaled(
            page_rect.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        x_offset = int((page_rect.width() - scaled.width()) / 2)
        y_offset = int((page_rect.height() - scaled.height()) / 2)
        painter.drawPixmap(x_offset, y_offset, scaled)
        painter.end()

    def print_image(self) -> None:
        """
        Opens a print dialog and prints composited image.

        Returns:
            None
        """

        printer = QPrinter()
        dialog = QPrintDialog(printer, self)
        if not dialog.exec():
            return
        painter = QPainter(printer)
        pixmap = self.canvas.export_composited_pixmap()
        rect = painter.viewport()
        scaled = pixmap.scaled(rect.size(), Qt.AspectRatioMode.KeepAspectRatio)
        painter.drawPixmap(0, 0, scaled)
        painter.end()

    def copy_current_image_to_clipboard(self) -> None:
        """
        Copies current composited tab image into clipboard.

        Returns:
            None
        """

        pixmap = self.canvas.export_composited_pixmap()
        clipboard = QGuiApplication.clipboard()
        clipboard.setPixmap(pixmap)
        self.statusBar().showMessage("Image copied to clipboard")

    def show_about(self) -> None:
        """
        Displays About dialog information.

        Returns:
            None
        """

        QMessageBox.information(
            self,
            f"About {APP_NAME}",
            f"{APP_NAME}\n"
            f"Author: {ABOUT_AUTHOR}\n"
            f"Website: {ABOUT_WEBSITE}\n\n"
            "A Linux screenshot editor inspired by SnagIt.",
        )

    def show_manual(self) -> None:
        """
        Displays quick manual and shortcut list.

        Returns:
            None
        """

        QMessageBox.information(
            self,
            "Manual and Shortcuts",
            "How it works:\n"
            "1) Use the capture panel to create a screenshot.\n"
            "2) Annotate with tools in the top bar.\n"
            "3) Save project, export image, or print from File menu.\n\n"
            "Keyboard shortcuts (standard behavior):\n"
            "Ctrl+S: Export dialog\n"
            "Ctrl+P: Print dialog\n"
            "Ctrl+Shift+S: Save project as\n"
            "Ctrl+O: Open project\n"
            "Ctrl+Z: Undo\n"
            "Ctrl+Y / Ctrl+Shift+Z: Redo\n"
            "Ctrl+C: Copy composited image\n"
            "Ctrl+V: Paste text/image/image URL\n"
            "Ctrl + Mouse Wheel: Zoom\n"
            "Enter: Apply crop selection\n"
            "Esc: Cancel crop selection or capture overlays\n\n"
            "Project shortcuts:\n"
            "Ctrl+O: Open project\n"
            "Use File > Save Project to update current .sfp file.",
        )

    def show_shortcuts_reference(self) -> None:
        """
        Displays a dedicated keyboard shortcut reference.

        Returns:
            None
        """

        QMessageBox.information(
            self,
            "Keyboard Shortcuts",
            "Editor shortcuts:\n"
            "Ctrl+S  - Open export dialog (PNG/JPG/PDF)\n"
            "Ctrl+P  - Open print dialog\n"
            "Ctrl+Shift+S  - Save project as (.sfp)\n"
            "Ctrl+O  - Open project\n"
            "Ctrl+Z  - Undo\n"
            "Ctrl+Y / Ctrl+Shift+Z  - Redo\n"
            "Ctrl+C  - Copy composited image\n"
            "Ctrl+V  - Paste text/image/image URL\n"
            "Ctrl+Mouse Wheel  - Zoom in/out\n"
            "Enter  - Apply crop\n"
            "Esc  - Cancel crop or capture overlay\n",
        )

    def _update_window_title(self) -> None:
        """
        Updates title with current project file name.

        Returns:
            None
        """

        if not self._current_project_path:
            self.setWindowTitle(f"{APP_NAME} Editor")
            return
        self.setWindowTitle(f"{APP_NAME} Editor - {self._current_project_path}")

    def resizeEvent(self, event) -> None:
        """
        Reflows toolbar groups when the editor window is resized.

        Args:
            event: Qt resize event.

        Returns:
            None
        """

        super().resizeEvent(event)
        self._reflow_toolbar_groups()

    def timerEvent(self, event) -> None:
        """
        Runs periodic auto-save every 30 seconds.

        Args:
            event: Timer event from Qt.

        Returns:
            None
        """

        if event.timerId() != self._autosave_timer:
            super().timerEvent(event)
            return

        if not self._current_project_path:
            target_path = self._recovery_path
        else:
            target_path = self._current_project_path
        model = build_project_model(
            screenshot=self.canvas.screenshot(),
            annotation_models=self.canvas.collect_annotations(),
        )
        save_project(target_path, model)

    def set_minimize_to_tray_on_close(self, enabled: bool) -> None:
        """
        Enables or disables close-to-tray behavior.

        Args:
            enabled: True to hide on close, False to close normally.

        Returns:
            None
        """

        self._minimize_to_tray_on_close = enabled

    def closeEvent(self, event) -> None:
        """
        Handles close button behavior for tray minimization.

        Args:
            event: Qt close event.

        Returns:
            None
        """

        if self._minimize_to_tray_on_close:
            self.close_requested.emit()
            event.ignore()
            return
        super().closeEvent(event)

