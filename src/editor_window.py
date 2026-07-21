"""
Main screenshot editing window for SnapAgent.
"""

from __future__ import annotations

import tempfile
import os
from typing import Any

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QBrush,
    QColor,
    QFontDatabase,
    QGuiApplication,
    QIcon,
    QKeySequence,
    QPainter,
    QPageLayout,
    QPageSize,
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
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src.constants import (
    ABOUT_AUTHOR,
    ABOUT_GITHUB,
    ABOUT_WEBSITE,
    APP_FILE_EXTENSION,
    APP_NAME,
)
from src.annotation_items import (
    STROKE_STYLE_DASH,
    STROKE_STYLE_DASH_DOT,
    STROKE_STYLE_DOT,
    STROKE_STYLE_SOLID,
)
from src.annotation_shapes import TEXT_STYLE_BOX, TEXT_STYLE_BUBBLE, TEXT_STYLE_PLAIN
from src.editor_canvas import EditorCanvas, Tool
from src.flow_layout import FlowLayoutWidget, sort_widgets_by_area_descending
from src.models import AnnotationModel, ProjectModel
from src.storage import (
    base64_png_to_pixmap,
    build_project_model,
    load_project,
    pixmap_to_base64_png,
    save_project,
)
from src.theme import (
    THEME_DARK,
    THEME_LIGHT,
    color_preview_button_stylesheet,
    get_editor_accent_colors,
    normalize_theme_name,
    palette_button_stylesheet,
)


class EditorWindow(QMainWindow):
    """
    Hosts the SnapAgent screenshot editor UI.
    """

    close_requested = Signal()
    theme_changed = Signal(str)
    settings_requested = Signal()

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
        self._recovery_path = ""
        self._minimize_to_tray_on_close = True
        self._jpeg_quality = 90
        self._pdf_dpi = 300

        self._record_history = True
        self._history: list[dict[str, Any]] = []
        self._history_labels: list[str] = []
        self._history_index = -1
        self._pending_history_label: str | None = None
        self._syncing_history_list = False
        self._toolbar_groups: list[QWidget] = []
        self._palette_buttons: list[QPushButton] = []
        self._active_tool = Tool.SELECT
        self._locked_tool: str | None = None
        self._one_shot_tool: str | None = None
        self._tool_button_order: list[str] = []
        self._tool_button_labels: dict[str, str] = {}
        self._tool_button_to_key: dict[QToolButton, str] = {}
        self._tool_button_fixed_width = 116
        self._tools_buttons_columns = 4
        self._current_stroke_color = QColor(231, 76, 60, 255)
        self._current_fill_color = QColor(231, 76, 60, 80)
        self._current_text_color = QColor(44, 62, 80, 255)
        self._text_bold_enabled = False
        self._text_italic_enabled = False
        self._text_underline_enabled = False

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

    def _build_toolbar(self) -> QWidget:
        """
        Creates the slim top tool panel.

        Returns:
            QWidget: Toolbar container widget.
        """

        bar = QWidget(self)
        bar.setObjectName("editorToolbar")
        root_layout = QVBoxLayout(bar)
        root_layout.setContentsMargins(4, 2, 4, 2)
        root_layout.setSpacing(3)

        self._toolbar_groups_container = FlowLayoutWidget(
            bar,
            horizontal_spacing=6,
            vertical_spacing=3,
        )
        self._toolbar_groups_layout = self._toolbar_groups_container.flow_layout
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

        tools_group, tools_content = self._create_toolbar_group("Tools")
        tools_vertical_layout = QVBoxLayout()
        tools_vertical_layout.setContentsMargins(0, 0, 0, 0)
        tools_vertical_layout.setSpacing(2)
        tools_content.addLayout(tools_vertical_layout)

        self._tools_buttons_container = QWidget(tools_group)
        self._tools_buttons_container.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Maximum,
        )
        button_spacing = 4
        tools_grid_width = (
            self._tools_buttons_columns * self._tool_button_fixed_width
            + (self._tools_buttons_columns - 1) * button_spacing
        )
        self._tools_buttons_container.setFixedWidth(tools_grid_width)
        self._tools_buttons_layout = QGridLayout(self._tools_buttons_container)
        self._tools_buttons_layout.setContentsMargins(0, 0, 0, 0)
        self._tools_buttons_layout.setHorizontalSpacing(button_spacing)
        self._tools_buttons_layout.setVerticalSpacing(button_spacing)
        tools_vertical_layout.addWidget(self._tools_buttons_container)

        self._tool_buttons: dict[str, QToolButton] = {}
        for index, (tool_key, label) in enumerate(
            [
            (Tool.SELECT, "Select"),
            (Tool.RECT, "Rectangle"),
            (Tool.ELLIPSE, "Circle"),
            (Tool.LINE, "Line"),
            (Tool.ARROW, "Arrow"),
            (Tool.TEXT, "Text"),
            (Tool.FILL_BG, "Bg Fill"),
            (Tool.BLUR, "Blur"),
            (Tool.STEP, "Step"),
            (Tool.OCR, "OCR"),
            (Tool.CROP, "Crop"),
            ]
        ):
            button = QToolButton()
            button.setText(label)
            button.setCheckable(True)
            button.setIcon(self._build_tool_icon(tool_key))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setFixedWidth(self._tool_button_fixed_width)
            self._configure_compact_toolbar_height(button, 26)
            button.clicked.connect(
                lambda _checked=False, t=tool_key: self._on_tool_button_clicked(t)
            )
            button.installEventFilter(self)
            self._tool_buttons[tool_key] = button
            self._tool_button_order.append(tool_key)
            self._tool_button_labels[tool_key] = label
            self._tool_button_to_key[button] = tool_key
            row = index // self._tools_buttons_columns
            column = index % self._tools_buttons_columns
            self._tools_buttons_layout.addWidget(button, row, column)
        self._tool_buttons[Tool.SELECT].setChecked(True)

        tools_actions_row = QHBoxLayout()
        tools_actions_row.setContentsMargins(0, 0, 0, 0)
        tools_actions_row.setSpacing(3)
        self.apply_crop_button = QPushButton("Apply Crop")
        self.apply_crop_button.setEnabled(False)
        self.apply_crop_button.clicked.connect(self.canvas.apply_pending_crop)
        self._configure_compact_toolbar_height(self.apply_crop_button)
        tools_actions_row.addWidget(self.apply_crop_button)

        tools_actions_row.addWidget(QLabel("Border"))
        self.stroke_size_spin = QSpinBox()
        self.stroke_size_spin.setRange(1, 32)
        self.stroke_size_spin.setValue(3)
        self.stroke_size_spin.valueChanged.connect(self._stroke_width_changed)
        self._configure_compact_toolbar_height(self.stroke_size_spin)
        tools_actions_row.addWidget(self.stroke_size_spin)

        tools_actions_row.addWidget(QLabel("Line"))
        self.stroke_style_combo = QComboBox()
        self.stroke_style_combo.addItem("Solid", STROKE_STYLE_SOLID)
        self.stroke_style_combo.addItem("Dash", STROKE_STYLE_DASH)
        self.stroke_style_combo.addItem("Dot", STROKE_STYLE_DOT)
        self.stroke_style_combo.addItem("Dash dot", STROKE_STYLE_DASH_DOT)
        self.stroke_style_combo.currentIndexChanged.connect(self._stroke_style_changed)
        self._configure_compact_toolbar_height(self.stroke_style_combo)
        tools_actions_row.addWidget(self.stroke_style_combo)

        tools_actions_row.addWidget(QLabel("Blur px"))
        self.blur_block_spin = QSpinBox()
        self.blur_block_spin.setRange(4, 64)
        self.blur_block_spin.setValue(self.canvas.blur_block_size())
        self.blur_block_spin.valueChanged.connect(self._blur_block_size_changed)
        self._configure_compact_toolbar_height(self.blur_block_spin)
        tools_actions_row.addWidget(self.blur_block_spin)
        tools_vertical_layout.addLayout(tools_actions_row)
        self._finalize_compact_tools_group(tools_group)

        colors_group, colors_content = self._create_toolbar_group("Colors")
        colors_layout = QVBoxLayout()
        colors_layout.setContentsMargins(0, 0, 0, 0)
        colors_layout.setSpacing(2)
        colors_content.addLayout(colors_layout)

        stroke_row = QHBoxLayout()
        stroke_row.setContentsMargins(0, 0, 0, 0)
        stroke_row.setSpacing(3)
        self.stroke_button = QPushButton("Border")
        self.stroke_button.setFixedWidth(110)
        self.stroke_button.clicked.connect(self._choose_stroke_color)
        self._configure_compact_toolbar_height(self.stroke_button)
        stroke_row.addWidget(self.stroke_button)
        for color in palette_colors:
            stroke_row.addWidget(self._create_palette_button(color, "stroke"))
        stroke_row.addWidget(QLabel("Opacity"))
        self.stroke_alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.stroke_alpha_slider.setRange(0, 100)
        self.stroke_alpha_slider.setValue(100)
        self.stroke_alpha_slider.setFixedWidth(90)
        self.stroke_alpha_slider.valueChanged.connect(self._stroke_alpha_changed)
        self._configure_compact_toolbar_height(self.stroke_alpha_slider, 22)
        stroke_row.addWidget(self.stroke_alpha_slider)
        self.stroke_alpha_label = QLabel("100%")
        self._configure_compact_toolbar_height(self.stroke_alpha_label, 22)
        stroke_row.addWidget(self.stroke_alpha_label)
        stroke_row.addStretch(1)
        colors_layout.addLayout(stroke_row)

        fill_row = QHBoxLayout()
        fill_row.setContentsMargins(0, 0, 0, 0)
        fill_row.setSpacing(3)
        self.fill_button = QPushButton("Background")
        self.fill_button.setFixedWidth(110)
        self.fill_button.clicked.connect(self._choose_fill_color)
        self._configure_compact_toolbar_height(self.fill_button)
        fill_row.addWidget(self.fill_button)
        for color in palette_colors:
            fill_row.addWidget(self._create_palette_button(color, "fill"))
        fill_row.addWidget(QLabel("Opacity"))
        self.fill_alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.fill_alpha_slider.setRange(0, 100)
        self.fill_alpha_slider.setValue(31)
        self.fill_alpha_slider.setFixedWidth(90)
        self.fill_alpha_slider.valueChanged.connect(self._fill_alpha_changed)
        self._configure_compact_toolbar_height(self.fill_alpha_slider, 22)
        fill_row.addWidget(self.fill_alpha_slider)
        self.fill_alpha_label = QLabel("31%")
        self._configure_compact_toolbar_height(self.fill_alpha_label, 22)
        fill_row.addWidget(self.fill_alpha_label)
        fill_row.addStretch(1)
        colors_layout.addLayout(fill_row)

        text_row = QHBoxLayout()
        text_row.setContentsMargins(0, 0, 0, 0)
        text_row.setSpacing(3)
        self.text_color_button = QPushButton("Text")
        self.text_color_button.setFixedWidth(110)
        self.text_color_button.clicked.connect(self._choose_text_color)
        self._configure_compact_toolbar_height(self.text_color_button)
        text_row.addWidget(self.text_color_button)
        for color in palette_colors:
            text_row.addWidget(self._create_palette_button(color, "text"))
        text_row.addWidget(QLabel("Opacity"))
        self.text_alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.text_alpha_slider.setRange(0, 100)
        self.text_alpha_slider.setValue(100)
        self.text_alpha_slider.setFixedWidth(90)
        self.text_alpha_slider.valueChanged.connect(self._text_alpha_changed)
        self._configure_compact_toolbar_height(self.text_alpha_slider, 22)
        text_row.addWidget(self.text_alpha_slider)
        self.text_alpha_label = QLabel("100%")
        self._configure_compact_toolbar_height(self.text_alpha_label, 22)
        text_row.addWidget(self.text_alpha_label)
        text_row.addStretch(1)
        colors_layout.addLayout(text_row)
        self._toolbar_groups.append(colors_group)

        text_group, text_content = self._create_toolbar_group("Text Style")
        text_rows = QVBoxLayout()
        text_rows.setContentsMargins(0, 0, 0, 0)
        text_rows.setSpacing(2)
        text_content.addLayout(text_rows)

        font_row = QHBoxLayout()
        font_row.setContentsMargins(0, 0, 0, 0)
        font_row.setSpacing(3)
        font_row.addWidget(QLabel("Font"))
        self.font_family_combo = QComboBox()
        self.font_family_combo.addItems(sorted(QFontDatabase.families()))
        self.font_family_combo.currentTextChanged.connect(self._font_family_changed)
        self._configure_compact_combo(self.font_family_combo, 128)
        font_row.addWidget(self.font_family_combo)

        font_row.addWidget(QLabel("Size"))
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
        self._configure_compact_combo(self.font_size_combo, 46)
        font_row.addWidget(self.font_size_combo)
        text_rows.addLayout(font_row)

        style_row = QHBoxLayout()
        style_row.setContentsMargins(0, 0, 0, 0)
        style_row.setSpacing(3)
        style_row.addWidget(QLabel("Style"))
        self.text_style_combo = QComboBox()
        self.text_style_combo.addItem("Plain", TEXT_STYLE_PLAIN)
        self.text_style_combo.addItem("Box", TEXT_STYLE_BOX)
        self.text_style_combo.addItem("Bubble", TEXT_STYLE_BUBBLE)
        self.text_style_combo.currentIndexChanged.connect(self._text_style_changed)
        self._configure_compact_combo(self.text_style_combo, 78)
        style_row.addWidget(self.text_style_combo)

        self.text_bold_button = QToolButton()
        self.text_bold_button.setText("B")
        self.text_bold_button.setCheckable(True)
        self.text_bold_button.clicked.connect(self._text_bold_toggled)
        self._configure_compact_icon_button(self.text_bold_button)
        style_row.addWidget(self.text_bold_button)

        self.text_italic_button = QToolButton()
        self.text_italic_button.setText("I")
        self.text_italic_button.setCheckable(True)
        self.text_italic_button.clicked.connect(self._text_italic_toggled)
        self._configure_compact_icon_button(self.text_italic_button)
        style_row.addWidget(self.text_italic_button)

        self.text_underline_button = QToolButton()
        self.text_underline_button.setText("U")
        self.text_underline_button.setCheckable(True)
        self.text_underline_button.clicked.connect(self._text_underline_toggled)
        self._configure_compact_icon_button(self.text_underline_button)
        style_row.addWidget(self.text_underline_button)
        text_rows.addLayout(style_row)
        self._toolbar_groups.append(text_group)

        align_group, align_content = self._create_toolbar_group("Align & Grid")
        align_row = QHBoxLayout()
        align_row.setContentsMargins(0, 0, 0, 0)
        align_row.setSpacing(3)
        align_content.addLayout(align_row)
        self.snap_to_grid_button = QToolButton()
        self.snap_to_grid_button.setText("Snap")
        self.snap_to_grid_button.setCheckable(True)
        self.snap_to_grid_button.clicked.connect(self._snap_toggled)
        self._configure_compact_toolbar_height(self.snap_to_grid_button)
        align_row.addWidget(self.snap_to_grid_button)

        self.grid_visible_button = QToolButton()
        self.grid_visible_button.setText("Grid")
        self.grid_visible_button.setCheckable(True)
        self.grid_visible_button.clicked.connect(self._grid_toggled)
        self._configure_compact_toolbar_height(self.grid_visible_button)
        align_row.addWidget(self.grid_visible_button)

        align_row.addWidget(QLabel("Size"))
        self.grid_size_combo = QComboBox()
        self.grid_size_combo.addItems(["8", "12", "16", "20", "24", "32", "40", "48"])
        self.grid_size_combo.setCurrentText("16")
        self.grid_size_combo.currentTextChanged.connect(self._grid_size_changed)
        self._configure_compact_combo(self.grid_size_combo, 52)
        self._configure_compact_toolbar_height(self.grid_size_combo)
        align_row.addWidget(self.grid_size_combo)
        self._toolbar_groups.append(align_group)

        history_group, history_content = self._create_toolbar_group("History")
        history_row = QHBoxLayout()
        history_row.setContentsMargins(0, 0, 0, 0)
        history_row.setSpacing(3)
        history_content.addLayout(history_row)
        self.history_undo_button = QPushButton("Undo")
        self.history_undo_button.clicked.connect(self.undo)
        self._configure_compact_toolbar_height(self.history_undo_button)
        history_row.addWidget(self.history_undo_button)
        self.history_redo_button = QPushButton("Redo")
        self.history_redo_button.clicked.connect(self.redo)
        self._configure_compact_toolbar_height(self.history_redo_button)
        history_row.addWidget(self.history_redo_button)
        self.history_list_combo = QComboBox()
        self.history_list_combo.setMinimumWidth(160)
        self.history_list_combo.currentIndexChanged.connect(self._on_history_entry_selected)
        self._configure_compact_toolbar_height(self.history_list_combo)
        history_row.addWidget(self.history_list_combo)
        self.history_status_label = QLabel("1/1")
        self._configure_compact_toolbar_height(self.history_status_label, 22)
        history_row.addWidget(self.history_status_label)
        self._toolbar_groups.append(history_group)

        zoom_group, zoom_content = self._create_toolbar_group("Zoom")
        zoom_row = QHBoxLayout()
        zoom_row.setContentsMargins(0, 0, 0, 0)
        zoom_row.setSpacing(3)
        zoom_content.addLayout(zoom_row)
        self.zoom_label = QLabel("100%")
        self._configure_compact_toolbar_height(self.zoom_label, 22)
        zoom_row.addWidget(self.zoom_label)

        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(10, 400)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(120)
        self.zoom_slider.setToolTip("Zoom: left smaller, right larger")
        self.zoom_slider.valueChanged.connect(self._zoom_slider_changed)
        self._configure_compact_toolbar_height(self.zoom_slider, 22)
        zoom_row.addWidget(self.zoom_slider)

        self.zoom_in_button = QPushButton("+")
        self.zoom_in_button.clicked.connect(self.canvas.zoom_in)
        self._configure_compact_action_button(self.zoom_in_button)
        self._configure_compact_toolbar_height(self.zoom_in_button)
        zoom_row.addWidget(self.zoom_in_button)
        self.zoom_out_button = QPushButton("-")
        self.zoom_out_button.clicked.connect(self.canvas.zoom_out)
        self._configure_compact_action_button(self.zoom_out_button)
        self._configure_compact_toolbar_height(self.zoom_out_button)
        zoom_row.addWidget(self.zoom_out_button)
        self.zoom_reset_button = QPushButton("Reset")
        self.zoom_reset_button.clicked.connect(self.canvas.reset_zoom)
        self._configure_compact_action_button(self.zoom_reset_button)
        self._configure_compact_toolbar_height(self.zoom_reset_button)
        zoom_row.addWidget(self.zoom_reset_button)
        self._toolbar_groups.append(zoom_group)
        self._toolbar_groups.append(tools_group)
        self._reflow_toolbar_groups()
        self._update_color_button_preview(self.stroke_button, QColor("#e74c3c"))
        self._update_color_button_preview(self.fill_button, QColor(231, 76, 60, 80))
        self._update_color_button_preview(self.text_color_button, QColor("#2c3e50"))
        self._apply_toolbar_tooltips()
        return bar

    def _reflow_toolbar_groups(self) -> None:
        """
        Populates toolbar groups and applies float-style wrapping for the current width.

        Returns:
            None
        """

        if not hasattr(self, "_toolbar_groups_layout"):
            return
        if not self._toolbar_groups:
            self._toolbar_groups_layout.clear()
            return

        sorted_groups = sort_widgets_by_area_descending(self._toolbar_groups)
        self._toolbar_groups_container.set_flow_widgets(sorted_groups)

    def _update_toolbar_flow_layout(self) -> None:
        """
        Reflows toolbar containers after the editor width changed.

        Returns:
            None
        """

        if hasattr(self, "_toolbar_groups_container"):
            self._toolbar_groups_container.update_flow_geometry()

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
        accent_pen = QPen(QColor(get_editor_accent_colors()[0]), 1.6)

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
        elif tool == Tool.BLUR:
            painter.setPen(QPen(QColor("#c39bd3"), 1.6))
            painter.setBrush(QBrush(QColor(155, 89, 182, 120)))
            painter.drawRect(QRectF(3.0, 3.0, 5.0, 5.0))
            painter.drawRect(QRectF(9.0, 3.0, 5.0, 5.0))
            painter.drawRect(QRectF(3.0, 9.0, 5.0, 5.0))
            painter.drawRect(QRectF(9.0, 9.0, 5.0, 5.0))
        elif tool == Tool.STEP:
            painter.setPen(stroke_pen)
            painter.setBrush(QBrush(QColor(231, 76, 60, 230)))
            painter.drawEllipse(QRectF(3.0, 3.0, 12.0, 12.0))
            painter.setPen(QColor(255, 255, 255, 255))
            painter.drawText(QRectF(3.0, 2.0, 12.0, 14.0), int(Qt.AlignmentFlag.AlignCenter), "1")
        elif tool == Tool.OCR:
            painter.setPen(QPen(QColor("#2ecc71"), 1.6))
            text_font = painter.font()
            text_font.setBold(True)
            text_font.setPointSize(8)
            painter.setFont(text_font)
            painter.drawText(QRectF(1.0, 2.0, 16.0, 14.0), "OCR")
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

    def _create_toolbar_group(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        """
        Creates a framed toolbar group with a compact side title label.

        Args:
            title: Visible group caption.

        Returns:
            tuple[QFrame, QVBoxLayout]: Group widget and content layout.
        """

        frame = QFrame(self)
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setProperty("toolbarGroup", True)
        frame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        group_layout = QHBoxLayout(frame)
        group_layout.setContentsMargins(4, 2, 4, 2)
        group_layout.setSpacing(4)

        title_label = QLabel(title)
        title_label.setObjectName("mutedLabel")
        title_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        title_label.setFixedWidth(max(48, title_label.fontMetrics().horizontalAdvance(title) + 6))
        group_layout.addWidget(title_label)

        content_host = QWidget()
        content_host.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        content_layout = QVBoxLayout(content_host)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(2)
        group_layout.addWidget(content_host, 1)
        return frame, content_layout

    def _finalize_compact_tools_group(self, tools_group: QFrame) -> None:
        """
        Sizes the Tools toolbar group to its content width only.

        Args:
            tools_group: Tools group frame widget.

        Returns:
            None
        """

        tools_group.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Maximum,
        )
        group_layout = tools_group.layout()
        if isinstance(group_layout, QHBoxLayout):
            group_layout.setStretch(0, 0)
            if group_layout.count() >= 2:
                group_layout.setStretch(1, 0)
                content_host = group_layout.itemAt(1).widget()
                if content_host is not None:
                    content_host.setSizePolicy(
                        QSizePolicy.Policy.Fixed,
                        QSizePolicy.Policy.Maximum,
                    )
        tools_group.adjustSize()
        tools_group.setFixedWidth(tools_group.sizeHint().width())

    def _configure_compact_toolbar_height(self, widget: QWidget, height: int = 24) -> None:
        """
        Applies a fixed compact height to one toolbar control.

        Args:
            widget: Target widget.
            height: Fixed height in pixels.

        Returns:
            None
        """

        widget.setFixedHeight(height)
        widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def _configure_compact_combo(self, combo: QComboBox, width: int) -> None:
        """
        Applies a fixed compact width to one toolbar combo box.

        Args:
            combo: Target combo box.
            width: Fixed width in pixels.

        Returns:
            None
        """

        combo.setFixedWidth(width)
        combo.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._configure_compact_toolbar_height(combo)

    def _configure_compact_icon_button(self, button: QToolButton) -> None:
        """
        Applies compact dimensions to one icon-style toolbar button.

        Args:
            button: Target tool button.

        Returns:
            None
        """

        button.setFixedSize(24, 24)
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def _configure_compact_action_button(self, button: QPushButton) -> None:
        """
        Applies minimum necessary width to one compact action button.

        Args:
            button: Target push button.

        Returns:
            None
        """

        button.setFixedWidth(max(24, button.sizeHint().width()))
        self._configure_compact_toolbar_height(button)

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
        button.setProperty("paletteColor", color.name(QColor.NameFormat.HexArgb))
        button.setStyleSheet(palette_button_stylesheet(color))
        button.clicked.connect(
            lambda _checked=False, t=target, c=QColor(color): self._apply_palette_color(
                target=t,
                color=c,
            )
        )
        self._palette_buttons.append(button)
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
            Tool.BLUR: "Blur one area for redaction. Double-click to lock tool.",
            Tool.STEP: "Insert numbered step badges for tutorials.",
            Tool.OCR: "Select a region and copy recognized text to clipboard.",
            Tool.CROP: "Create a crop selection area.",
        }
        for tool_key, button in self._tool_buttons.items():
            button.setToolTip(tooltips.get(tool_key, "Use this tool."))

        self.apply_crop_button.setToolTip("Apply current crop selection.")
        self.stroke_size_spin.setToolTip("Set border line width.")
        self.stroke_style_combo.setToolTip("Select line style for lines and arrows.")
        self.blur_block_spin.setToolTip("Set blur pixel block size for redaction.")
        self.text_style_combo.setToolTip("Select plain text, text box, or speech bubble.")
        self.stroke_button.setToolTip("Open border color picker.")
        self.fill_button.setToolTip("Open background color picker.")
        self.text_color_button.setToolTip("Open text color picker.")
        self.stroke_alpha_slider.setToolTip("Set border opacity.")
        self.fill_alpha_slider.setToolTip("Set background opacity.")
        self.text_alpha_slider.setToolTip("Set text opacity.")
        self.font_family_combo.setToolTip("Select text font family.")
        self.font_size_combo.setToolTip("Select text font size.")
        self.text_bold_button.setToolTip("Toggle bold text style.")
        self.text_italic_button.setToolTip("Toggle italic text style.")
        self.text_underline_button.setToolTip("Toggle underline text style.")
        self.snap_to_grid_button.setToolTip("Snap drawing and movement to grid.")
        self.grid_visible_button.setToolTip("Show or hide the alignment grid.")
        self.grid_size_combo.setToolTip("Choose grid spacing in pixels.")
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
        view_menu = menu.addMenu("View")
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

        duplicate_action = QAction("Duplicate", self)
        duplicate_action.setShortcut(QKeySequence("Ctrl+D"))
        duplicate_action.setToolTip("Duplicate the current selection.")
        duplicate_action.triggered.connect(self._duplicate_selection)
        edit_menu.addAction(duplicate_action)

        edit_menu.addSeparator()

        bring_forward_action = QAction("Bring Forward", self)
        bring_forward_action.setToolTip("Move selection one layer up.")
        bring_forward_action.triggered.connect(self.canvas.bring_selected_forward)
        edit_menu.addAction(bring_forward_action)

        send_backward_action = QAction("Send Backward", self)
        send_backward_action.setToolTip("Move selection one layer down.")
        send_backward_action.triggered.connect(self.canvas.send_selected_backward)
        edit_menu.addAction(send_backward_action)

        bring_to_front_action = QAction("Bring to Front", self)
        bring_to_front_action.setToolTip("Move selection to the top layer.")
        bring_to_front_action.triggered.connect(self.canvas.bring_selected_to_front)
        edit_menu.addAction(bring_to_front_action)

        send_to_back_action = QAction("Send to Back", self)
        send_to_back_action.setToolTip("Move selection to the bottom layer.")
        send_to_back_action.triggered.connect(self.canvas.send_selected_to_back)
        edit_menu.addAction(send_to_back_action)

        edit_menu.addSeparator()

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

        theme_menu = view_menu.addMenu("Theme")
        self._theme_action_group = QActionGroup(self)
        self._theme_action_group.setExclusive(True)
        self.theme_dark_action = QAction("Dark", self)
        self.theme_dark_action.setCheckable(True)
        self.theme_dark_action.setToolTip("Use the dark application theme.")
        self.theme_dark_action.triggered.connect(
            lambda: self.theme_changed.emit(THEME_DARK)
        )
        self._theme_action_group.addAction(self.theme_dark_action)
        theme_menu.addAction(self.theme_dark_action)
        self.theme_light_action = QAction("Light", self)
        self.theme_light_action.setCheckable(True)
        self.theme_light_action.setToolTip("Use the light application theme.")
        self.theme_light_action.triggered.connect(
            lambda: self.theme_changed.emit(THEME_LIGHT)
        )
        self._theme_action_group.addAction(self.theme_light_action)
        theme_menu.addAction(self.theme_light_action)

        settings_action = QAction("Settings...", self)
        settings_action.setToolTip("Configure hotkeys and capture behavior.")
        settings_action.triggered.connect(self.settings_requested.emit)
        view_menu.addAction(settings_action)

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
            Tool.BLUR,
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

        button.setStyleSheet(color_preview_button_stylesheet(color))

    def set_theme_selection(self, theme_name: str) -> None:
        """
        Updates theme menu actions without emitting change signal.

        Args:
            theme_name: Theme identifier to select.

        Returns:
            None
        """

        normalized = normalize_theme_name(theme_name)
        self.theme_dark_action.blockSignals(True)
        self.theme_light_action.blockSignals(True)
        self.theme_dark_action.setChecked(normalized == THEME_DARK)
        self.theme_light_action.setChecked(normalized == THEME_LIGHT)
        self.theme_dark_action.blockSignals(False)
        self.theme_light_action.blockSignals(False)

    def refresh_theme_styles(self) -> None:
        """
        Refreshes widget styles that depend on the active theme.

        Returns:
            None
        """

        for button in self._palette_buttons:
            color_value = button.property("paletteColor")
            if isinstance(color_value, str) and color_value:
                button.setStyleSheet(palette_button_stylesheet(QColor(color_value)))
        self._update_color_button_preview(self.stroke_button, self._current_stroke_color)
        self._update_color_button_preview(self.fill_button, self._current_fill_color)
        self._update_color_button_preview(self.text_color_button, self._current_text_color)

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

    def _blur_block_size_changed(self, value: int) -> None:
        """
        Updates blur block size for the blur tool.

        Args:
            value: Pixel block size.

        Returns:
            None
        """

        self.canvas.set_blur_block_size(value)

    def _stroke_style_changed(self, _index: int) -> None:
        """
        Updates the active line style for lines and arrows.

        Args:
            _index: Selected combo box index.

        Returns:
            None
        """

        stroke_style = self.stroke_style_combo.currentData()
        if not isinstance(stroke_style, str):
            return
        self._set_next_history_label("Change line style")
        self.canvas.set_style(stroke_style=stroke_style)
        self._push_history_state()

    def _text_style_changed(self, _index: int) -> None:
        """
        Updates the active text container style.

        Args:
            _index: Selected combo box index.

        Returns:
            None
        """

        text_style = self.text_style_combo.currentData()
        if not isinstance(text_style, str):
            return
        self.canvas.set_style(text_style=text_style)

    def _duplicate_selection(self) -> None:
        """
        Duplicates the current canvas selection.

        Returns:
            None
        """

        if self.canvas.duplicate_selected_items():
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

    def _text_bold_toggled(self, checked: bool) -> None:
        """
        Updates active and selected text bold style.

        Args:
            checked: True when bold is enabled.

        Returns:
            None
        """

        self._text_bold_enabled = bool(checked)
        self._set_next_history_label("Toggle bold text")
        self.canvas.set_style(font_bold=self._text_bold_enabled)
        self._push_history_state()

    def _text_italic_toggled(self, checked: bool) -> None:
        """
        Updates active and selected text italic style.

        Args:
            checked: True when italic is enabled.

        Returns:
            None
        """

        self._text_italic_enabled = bool(checked)
        self._set_next_history_label("Toggle italic text")
        self.canvas.set_style(font_italic=self._text_italic_enabled)
        self._push_history_state()

    def _text_underline_toggled(self, checked: bool) -> None:
        """
        Updates active and selected text underline style.

        Args:
            checked: True when underline is enabled.

        Returns:
            None
        """

        self._text_underline_enabled = bool(checked)
        self._set_next_history_label("Toggle underline text")
        self.canvas.set_style(font_underline=self._text_underline_enabled)
        self._push_history_state()

    def _snap_toggled(self, checked: bool) -> None:
        """
        Enables or disables snap-to-grid behavior on the canvas.

        Args:
            checked: True when snapping is enabled.

        Returns:
            None
        """

        self.canvas.set_snap_enabled(bool(checked))
        self.statusBar().showMessage("Snap enabled" if checked else "Snap disabled")

    def _grid_toggled(self, checked: bool) -> None:
        """
        Enables or disables the visible alignment grid overlay.

        Args:
            checked: True to show the grid.

        Returns:
            None
        """

        self.canvas.set_grid_visible(bool(checked))
        self.statusBar().showMessage("Grid visible" if checked else "Grid hidden")

    def _grid_size_changed(self, value: str) -> None:
        """
        Updates the canvas grid spacing.

        Args:
            value: Selected grid size text.

        Returns:
            None
        """

        if not value.isdigit():
            return
        self.canvas.set_grid_size(int(value))

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
            Tool.BLUR: "Blur region",
            Tool.STEP: "Insert step",
            Tool.OCR: "Copy OCR text",
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
        font_bold = payload.get("font_bold")
        if isinstance(font_bold, bool):
            self._text_bold_enabled = font_bold
            self.text_bold_button.blockSignals(True)
            self.text_bold_button.setChecked(font_bold)
            self.text_bold_button.blockSignals(False)
        font_italic = payload.get("font_italic")
        if isinstance(font_italic, bool):
            self._text_italic_enabled = font_italic
            self.text_italic_button.blockSignals(True)
            self.text_italic_button.setChecked(font_italic)
            self.text_italic_button.blockSignals(False)
        font_underline = payload.get("font_underline")
        if isinstance(font_underline, bool):
            self._text_underline_enabled = font_underline
            self.text_underline_button.blockSignals(True)
            self.text_underline_button.setChecked(font_underline)
            self.text_underline_button.blockSignals(False)

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

    def set_recovery_path(self, path: str) -> None:
        """
        Sets the auto-save target path for this editor tab.

        Args:
            path: Recovery project file path.

        Returns:
            None
        """

        self._recovery_path = path.strip()

    def recovery_path(self) -> str:
        """
        Returns the auto-save target path for this editor tab.

        Returns:
            str: Recovery project file path.
        """

        return self._recovery_path

    @classmethod
    def recovery_snapshot_path(cls) -> str:
        """
        Returns the shared auto-recovery project file path.

        Returns:
            str: Recovery snapshot path.
        """

        return f"{tempfile.gettempdir()}/snapagent-autosave{APP_FILE_EXTENSION}"

    @classmethod
    def has_recovery_snapshot(cls) -> bool:
        """
        Indicates whether a recoverable editor session exists.

        Returns:
            bool: True when recovery data exists.
        """

        from src.session_recovery import has_recovery_data

        return has_recovery_data()

    @classmethod
    def discard_recovery_snapshot(cls) -> None:
        """
        Removes current editor recovery data if it exists.

        Returns:
            None
        """

        from src.session_recovery import clear_editor_session

        clear_editor_session()

    def load_project_model(
        self,
        project_model: ProjectModel,
        source_path: str = "",
    ) -> None:
        """
        Loads one already parsed project model into the editor.

        Args:
            project_model: Parsed project model to load.
            source_path: Optional source file path for title display.

        Returns:
            None
        """

        self._record_history = False
        self.canvas.set_screenshot(base64_png_to_pixmap(project_model.screenshot_png_base64))
        self.canvas.load_annotations(project_model.annotations)
        self._record_history = True
        self._history.clear()
        self._history_labels.clear()
        self._history_index = -1
        self._set_next_history_label("Recovered project" if not source_path else "Open project")
        self._push_history_state()
        self._current_project_path = source_path
        self._update_window_title()

    def load_recovery_snapshot(self) -> bool:
        """
        Loads the auto-recovery snapshot into the current editor tab.

        Returns:
            bool: True when recovery data was loaded.
        """

        if not self.has_recovery_snapshot():
            return False
        recovery_path = self.recovery_path() or self.recovery_snapshot_path()
        project_model = load_project(recovery_path)
        self.load_project_model(project_model, "")
        self.statusBar().showMessage("Recovered auto-saved project")
        return True

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
        if fmt == "JPG":
            quality = self._ask_jpeg_quality(self._jpeg_quality)
            if quality is None:
                return
            self._jpeg_quality = quality
            pixmap.save(file_path, fmt, quality)
        else:
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
            quality = self._ask_jpeg_quality(self._jpeg_quality)
            if quality is None:
                return
            self._jpeg_quality = quality
            self.canvas.export_composited_pixmap().save(file_path, "JPG", quality)
            self.statusBar().showMessage("Exported JPG")
            return

        if not file_path.lower().endswith(".pdf"):
            file_path = f"{file_path}.pdf"
        dpi = self._ask_pdf_dpi(self._pdf_dpi)
        if dpi is None:
            return
        self._pdf_dpi = dpi
        self._write_pdf_to_path(file_path, dpi)
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
        dpi = self._ask_pdf_dpi(self._pdf_dpi)
        if dpi is None:
            return
        self._pdf_dpi = dpi
        self._write_pdf_to_path(file_path, dpi)
        self.statusBar().showMessage("Exported PDF")

    def _write_pdf_to_path(self, file_path: str, dpi: int) -> None:
        """
        Writes current composited image as PDF to target path.

        Args:
            file_path: PDF output path.
            dpi: Export resolution in dots per inch.

        Returns:
            None
        """

        writer = QPdfWriter(file_path)
        writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        writer.setPageOrientation(QPageLayout.Orientation.Landscape)
        writer.setResolution(max(72, min(1200, int(dpi))))
        writer.setColorModel(QPdfWriter.ColorModel.RGB)

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

    def _ask_jpeg_quality(self, default: int) -> int | None:
        """
        Opens quality input dialog for JPEG exports.

        Args:
            default: Default quality value from previous export.

        Returns:
            int | None: Selected quality or None when cancelled.
        """

        quality, accepted = QInputDialog.getInt(
            self,
            "JPEG Quality",
            "Choose JPEG quality (1-100):",
            max(1, min(100, int(default))),
            1,
            100,
            1,
        )
        if not accepted:
            return None
        return quality

    def _ask_pdf_dpi(self, default: int) -> int | None:
        """
        Opens resolution input dialog for PDF exports.

        Args:
            default: Default DPI value from previous export.

        Returns:
            int | None: Selected DPI or None when cancelled.
        """

        dpi, accepted = QInputDialog.getInt(
            self,
            "PDF DPI",
            "Choose PDF DPI (72-1200):",
            max(72, min(1200, int(default))),
            72,
            1200,
            1,
        )
        if not accepted:
            return None
        return dpi

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
            f"Website: {ABOUT_WEBSITE}\n"
            f"GitHub: {ABOUT_GITHUB}\n\n"
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
        self._update_toolbar_flow_layout()

    def showEvent(self, event) -> None:
        """
        Reflows toolbar containers once the editor becomes visible.

        Args:
            event: Qt show event.

        Returns:
            None
        """

        super().showEvent(event)
        self._update_toolbar_flow_layout()

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

        self.flush_recovery_snapshot()

    def flush_recovery_snapshot(self) -> None:
        """
        Persists the current tab state to its recovery project file.

        Returns:
            None
        """

        if not self._recovery_path:
            return

        model = build_project_model(
            screenshot=self.canvas.screenshot(),
            annotation_models=self.canvas.collect_annotations(),
        )
        save_project(self._recovery_path, model)

        if self._current_project_path:
            save_project(self._current_project_path, model)

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

