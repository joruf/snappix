"""
Main screenshot editing window for Snappix.
"""

from __future__ import annotations

import json
import tempfile
import os
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QByteArray,
    QBuffer,
    QEvent,
    QIODevice,
    QPointF,
    QRectF,
    Qt,
    Signal,
    QMimeData,
)
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
    QApplication,
    QCheckBox,
    QComboBox,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QTabWidget,
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
from src.config import (
    EXPORT_PRESET_DOCS,
    EXPORT_PRESET_LIGHTWEIGHT,
    EXPORT_PRESET_PRINT,
    EXPORT_PRESET_WEB,
    normalize_export_preset,
)
from src.annotation_items import (
    STROKE_STYLE_DASH,
    STROKE_STYLE_DASH_DOT,
    STROKE_STYLE_DOT,
    STROKE_STYLE_SOLID,
)
from src.annotation_shapes import TEXT_STYLE_BOX, TEXT_STYLE_BUBBLE, TEXT_STYLE_PLAIN
from src.editor_canvas import EditorCanvas, Tool
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


_SELECTION_TYPE_LABELS: dict[str, str] = {
    "rect": "Rectangle",
    "ellipse": "Ellipse",
    "line": "Line",
    "arrow": "Arrow",
    "text": "Text",
    "image": "Image",
    "step": "Step",
}

_STROKE_STYLE_LABELS: dict[str, str] = {
    STROKE_STYLE_SOLID: "Solid",
    STROKE_STYLE_DASH: "Dashed",
    STROKE_STYLE_DOT: "Dotted",
    STROKE_STYLE_DASH_DOT: "Dash-dot",
}
_CANVAS_CLIPBOARD_MIME = "application/x-snappix-canvas"


def _format_rgba_color(rgba: list[Any]) -> str:
    """
    Formats an RGBA list for compact status bar display.

    Args:
        rgba: Color components [r, g, b, a].

    Returns:
        str: Hex or rgba() color string.
    """

    if len(rgba) != 4:
        return ""
    red, green, blue, alpha = (int(value) for value in rgba)
    if alpha >= 255:
        return f"#{red:02X}{green:02X}{blue:02X}"
    return f"rgba({red},{green},{blue},{alpha})"


def format_selection_info(payload: dict[str, Any]) -> str:
    """
    Formats selected annotation details for the editor status bar.

    Args:
        payload: Selection detail payload from the canvas.

    Returns:
        str: Human-readable selection summary.
    """

    annotation_type = str(payload.get("type") or "").strip()
    if not annotation_type:
        return ""

    parts: list[str] = []
    type_label = _SELECTION_TYPE_LABELS.get(annotation_type, annotation_type.title())
    selected_count = payload.get("count")
    if isinstance(selected_count, int) and selected_count > 1:
        parts.append(f"{type_label} (+{selected_count - 1} more)")
    else:
        parts.append(type_label)

    width = payload.get("width")
    height = payload.get("height")
    if isinstance(width, (int, float)) and isinstance(height, (int, float)):
        parts.append(f"{width:g}×{height:g}")

    x_pos = payload.get("x")
    y_pos = payload.get("y")
    if isinstance(x_pos, (int, float)) and isinstance(y_pos, (int, float)):
        parts.append(f"@ {x_pos:g}, {y_pos:g}")

    step_number = payload.get("step_number")
    if isinstance(step_number, int):
        parts.append(f"Step {step_number}")

    text_preview = payload.get("text_preview")
    if isinstance(text_preview, str) and text_preview.strip():
        preview = text_preview.strip()
        if len(preview) > 28:
            preview = f"{preview[:25]}..."
        parts.append(f'"{preview}"')

    text_style = payload.get("text_style")
    if isinstance(text_style, str) and text_style.strip():
        parts.append(text_style.replace("_", " ").title())

    stroke_rgba = payload.get("stroke_rgba")
    if isinstance(stroke_rgba, list):
        stroke_color = _format_rgba_color(stroke_rgba)
        if stroke_color:
            parts.append(f"Stroke {stroke_color}")

    fill_rgba = payload.get("fill_rgba")
    if isinstance(fill_rgba, list):
        fill_color = _format_rgba_color(fill_rgba)
        if fill_color:
            parts.append(f"Fill {fill_color}")

    text_rgba = payload.get("text_rgba")
    if isinstance(text_rgba, list):
        text_color = _format_rgba_color(text_rgba)
        if text_color:
            parts.append(f"Text {text_color}")

    stroke_width = payload.get("stroke_width")
    if isinstance(stroke_width, (int, float)) and stroke_width > 0:
        width_value = int(stroke_width) if float(stroke_width).is_integer() else round(float(stroke_width), 1)
        parts.append(f"{width_value}px")

    stroke_style = payload.get("stroke_style")
    if isinstance(stroke_style, str) and stroke_style.strip():
        style_label = _STROKE_STYLE_LABELS.get(stroke_style, stroke_style.replace("_", " ").title())
        parts.append(style_label)

    font_size = payload.get("font_size")
    font_family = payload.get("font_family")
    if isinstance(font_size, int):
        if isinstance(font_family, str) and font_family.strip():
            parts.append(f"{font_family.strip()} {font_size}pt")
        else:
            parts.append(f"{font_size}pt")

    font_traits: list[str] = []
    if payload.get("font_bold") is True:
        font_traits.append("Bold")
    if payload.get("font_italic") is True:
        font_traits.append("Italic")
    if payload.get("font_underline") is True:
        font_traits.append("Underline")
    if font_traits:
        parts.append(", ".join(font_traits))

    z_index = payload.get("z_index")
    if isinstance(z_index, (int, float)):
        parts.append(f"Layer {z_index:g}")

    return "  ·  ".join(parts)


class EditorWindow(QMainWindow):
    """
    Hosts the Snappix screenshot editor UI.
    """

    close_requested = Signal()
    theme_changed = Signal(str)
    batch_export_profiles_changed = Signal(object, str)
    batch_export_last_directory_changed = Signal(str)
    settings_requested = Signal()
    new_canvas_requested = Signal()
    export_preset_changed = Signal(str)

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
        self._export_presets: dict[str, tuple[str, int, int]] = {
            EXPORT_PRESET_WEB: ("Web", 82, 150),
            EXPORT_PRESET_DOCS: ("Docs", 90, 300),
            EXPORT_PRESET_PRINT: ("Print", 96, 600),
            EXPORT_PRESET_LIGHTWEIGHT: ("Lightweight", 72, 120),
        }
        self._batch_export_profiles: list[dict[str, Any]] = [
            {
                "key": "web_fast",
                "label": "Web Fast",
                "formats": ["png", "jpg"],
                "jpg_quality": 82,
                "pdf_dpi": 150,
            },
            {
                "key": "docs_hq",
                "label": "Docs HQ",
                "formats": ["png", "jpg", "pdf"],
                "jpg_quality": 90,
                "pdf_dpi": 300,
            },
            {
                "key": "print_master",
                "label": "Print Master",
                "formats": ["png", "jpg", "pdf"],
                "jpg_quality": 96,
                "pdf_dpi": 600,
            },
        ]
        self._batch_export_profile_key = "docs_hq"
        self._batch_export_last_directory = ""

        self._record_history = True
        self._history: list[dict[str, Any]] = []
        self._history_labels: list[str] = []
        self._history_index = -1
        self._pending_history_label: str | None = None
        self._syncing_history_list = False
        self._syncing_layer_panel = False
        self._palette_buttons: list[QPushButton] = []
        self._active_tool = Tool.SELECT
        self._locked_tool: str | None = None
        self._one_shot_tool: str | None = None
        self._tool_button_order: list[str] = []
        self._tool_button_labels: dict[str, str] = {}
        self._tool_button_to_key: dict[QToolButton, str] = {}
        self._current_stroke_color = QColor(231, 76, 60, 255)
        self._current_fill_color = QColor(231, 76, 60, 80)
        self._current_text_color = QColor(44, 62, 80, 255)
        self._text_bold_enabled = False
        self._text_italic_enabled = False
        self._text_underline_enabled = False
        self._text_letter_spacing = 0.0
        self._text_line_spacing = 1.2
        self._text_box_padding = 10.0
        self._text_corner_radius = 6.0

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
        root.addWidget(self._toolbar_widget, 0)
        root.addWidget(self.canvas, 1)

        self._selection_info_label = QLabel("")
        self._selection_info_label.setObjectName("editorSelectionInfo")
        self._selection_info_label.setMinimumWidth(360)
        self.statusBar().addPermanentWidget(self._selection_info_label)
        self.statusBar().showMessage("Ready")
        self._build_menu()
        self.set_export_preset(EXPORT_PRESET_DOCS, emit_signal=False)
        self.set_batch_export_profiles(
            self._batch_export_profiles,
            selected_key=self._batch_export_profile_key,
            emit_signal=False,
        )
        self._push_history_state()
        self._refresh_layer_panel()
        self._autosave_timer = self.startTimer(30_000)

    def _build_toolbar(self) -> QWidget:
        """
        Creates the compact tool strip and tabbed property panels.

        Returns:
            QWidget: Toolbar container widget.
        """

        bar = QWidget(self)
        bar.setObjectName("editorToolbar")
        bar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        root_layout = QVBoxLayout(bar)
        root_layout.setContentsMargins(4, 1, 4, 1)
        root_layout.setSpacing(1)

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

        strip = QWidget(bar)
        strip.setObjectName("editorToolStrip")
        strip.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        strip_layout = QHBoxLayout(strip)
        strip_layout.setContentsMargins(2, 0, 2, 0)
        strip_layout.setSpacing(3)
        strip_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._tool_buttons: dict[str, QToolButton] = {}
        for tool_key, label in [
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
        ]:
            button = QToolButton()
            button.setText(label)
            button.setCheckable(True)
            button.setIcon(self._build_tool_icon(tool_key))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setFixedSize(26, 24)
            button.setToolTip(label)
            self._configure_compact_toolbar_height(button, 24)
            button.clicked.connect(
                lambda _checked=False, t=tool_key: self._on_tool_button_clicked(t)
            )
            button.installEventFilter(self)
            self._tool_buttons[tool_key] = button
            self._tool_button_order.append(tool_key)
            self._tool_button_labels[tool_key] = label
            self._tool_button_to_key[button] = tool_key
            strip_layout.addWidget(button)
        self._tool_buttons[Tool.SELECT].setChecked(True)

        strip_layout.addSpacing(8)
        self.history_undo_button = QPushButton("Undo")
        self.history_undo_button.clicked.connect(self.undo)
        self._configure_compact_toolbar_height(self.history_undo_button)
        strip_layout.addWidget(self.history_undo_button)
        self.history_redo_button = QPushButton("Redo")
        self.history_redo_button.clicked.connect(self.redo)
        self._configure_compact_toolbar_height(self.history_redo_button)
        strip_layout.addWidget(self.history_redo_button)
        self.history_list_combo = QComboBox()
        self.history_list_combo.setMinimumWidth(160)
        self.history_list_combo.currentIndexChanged.connect(self._on_history_entry_selected)
        self._configure_compact_toolbar_height(self.history_list_combo)
        strip_layout.addWidget(self.history_list_combo)
        self.history_status_label = QLabel("1/1")
        self._configure_compact_toolbar_height(self.history_status_label, 22)
        strip_layout.addWidget(self.history_status_label)

        strip_layout.addStretch(1)

        self.zoom_out_button = QPushButton("-")
        self.zoom_out_button.clicked.connect(self.canvas.zoom_out)
        self._configure_compact_action_button(self.zoom_out_button)
        self._configure_compact_toolbar_height(self.zoom_out_button)
        strip_layout.addWidget(self.zoom_out_button)

        self.zoom_label = QLabel("100%")
        self.zoom_label.setMinimumWidth(42)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._configure_compact_toolbar_height(self.zoom_label, 22)
        strip_layout.addWidget(self.zoom_label)

        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(10, 400)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(100)
        self.zoom_slider.setToolTip("Zoom: left smaller, right larger")
        self.zoom_slider.valueChanged.connect(self._zoom_slider_changed)
        self._configure_compact_toolbar_height(self.zoom_slider, 22)
        strip_layout.addWidget(self.zoom_slider)

        self.zoom_in_button = QPushButton("+")
        self.zoom_in_button.clicked.connect(self.canvas.zoom_in)
        self._configure_compact_action_button(self.zoom_in_button)
        self._configure_compact_toolbar_height(self.zoom_in_button)
        strip_layout.addWidget(self.zoom_in_button)

        self.zoom_reset_button = QPushButton("Reset")
        self.zoom_reset_button.clicked.connect(self.canvas.reset_zoom)
        self._configure_compact_action_button(self.zoom_reset_button)
        self._configure_compact_toolbar_height(self.zoom_reset_button)
        strip_layout.addWidget(self.zoom_reset_button)

        root_layout.addWidget(strip)

        self._property_tabs = QTabWidget(bar)
        self._property_tabs.setObjectName("editorPropertyTabs")
        self._property_tabs.setDocumentMode(True)
        self._property_tabs.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum,
        )
        self._PROPERTY_TAB_STYLE = 0
        self._PROPERTY_TAB_TEXT = 1
        self._PROPERTY_TAB_ARRANGE = 2
        self._PROPERTY_TAB_EXPORT = 3

        style_tab = QWidget()
        style_layout = QHBoxLayout(style_tab)
        style_layout.setContentsMargins(4, 0, 4, 0)
        style_layout.setSpacing(3)
        style_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.stroke_button = QPushButton("Border")
        self.stroke_button.setFixedWidth(64)
        self.stroke_button.clicked.connect(self._choose_stroke_color)
        self._configure_compact_toolbar_height(self.stroke_button)
        style_layout.addWidget(self.stroke_button)
        for color in palette_colors:
            style_layout.addWidget(self._create_palette_button(color, "stroke"))
        self.stroke_alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.stroke_alpha_slider.setRange(0, 100)
        self.stroke_alpha_slider.setValue(100)
        self.stroke_alpha_slider.setFixedWidth(56)
        self.stroke_alpha_slider.setToolTip("Border opacity")
        self.stroke_alpha_slider.valueChanged.connect(self._stroke_alpha_changed)
        self._configure_compact_toolbar_height(self.stroke_alpha_slider, 22)
        style_layout.addWidget(self.stroke_alpha_slider)
        self.stroke_alpha_label = QLabel("100%")
        self._configure_compact_toolbar_height(self.stroke_alpha_label, 22)
        style_layout.addWidget(self.stroke_alpha_label)

        style_layout.addSpacing(6)
        self.fill_button = QPushButton("Fill")
        self.fill_button.setFixedWidth(52)
        self.fill_button.clicked.connect(self._choose_fill_color)
        self._configure_compact_toolbar_height(self.fill_button)
        style_layout.addWidget(self.fill_button)
        for color in palette_colors:
            style_layout.addWidget(self._create_palette_button(color, "fill"))
        self.fill_alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.fill_alpha_slider.setRange(0, 100)
        self.fill_alpha_slider.setValue(31)
        self.fill_alpha_slider.setFixedWidth(56)
        self.fill_alpha_slider.setToolTip("Fill opacity")
        self.fill_alpha_slider.valueChanged.connect(self._fill_alpha_changed)
        self._configure_compact_toolbar_height(self.fill_alpha_slider, 22)
        style_layout.addWidget(self.fill_alpha_slider)
        self.fill_alpha_label = QLabel("31%")
        self._configure_compact_toolbar_height(self.fill_alpha_label, 22)
        style_layout.addWidget(self.fill_alpha_label)

        style_layout.addSpacing(6)
        self.text_color_button = QPushButton("Text")
        self.text_color_button.setFixedWidth(52)
        self.text_color_button.clicked.connect(self._choose_text_color)
        self._configure_compact_toolbar_height(self.text_color_button)
        style_layout.addWidget(self.text_color_button)
        for color in palette_colors:
            style_layout.addWidget(self._create_palette_button(color, "text"))
        self.text_alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.text_alpha_slider.setRange(0, 100)
        self.text_alpha_slider.setValue(100)
        self.text_alpha_slider.setFixedWidth(56)
        self.text_alpha_slider.setToolTip("Text opacity")
        self.text_alpha_slider.valueChanged.connect(self._text_alpha_changed)
        self._configure_compact_toolbar_height(self.text_alpha_slider, 22)
        style_layout.addWidget(self.text_alpha_slider)
        self.text_alpha_label = QLabel("100%")
        self._configure_compact_toolbar_height(self.text_alpha_label, 22)
        style_layout.addWidget(self.text_alpha_label)

        style_layout.addSpacing(6)
        self.apply_crop_button = QPushButton("Apply Crop")
        self.apply_crop_button.setEnabled(False)
        self.apply_crop_button.clicked.connect(self.canvas.apply_pending_crop)
        self._configure_compact_toolbar_height(self.apply_crop_button)
        style_layout.addWidget(self.apply_crop_button)
        style_layout.addWidget(self._create_toolbar_label("Width"))
        self.stroke_size_spin = QSpinBox()
        self.stroke_size_spin.setRange(1, 32)
        self.stroke_size_spin.setValue(3)
        self.stroke_size_spin.valueChanged.connect(self._stroke_width_changed)
        self._configure_compact_toolbar_height(self.stroke_size_spin)
        style_layout.addWidget(self.stroke_size_spin)
        style_layout.addWidget(self._create_toolbar_label("Line"))
        self.stroke_style_combo = QComboBox()
        self.stroke_style_combo.addItem("Solid", STROKE_STYLE_SOLID)
        self.stroke_style_combo.addItem("Dash", STROKE_STYLE_DASH)
        self.stroke_style_combo.addItem("Dot", STROKE_STYLE_DOT)
        self.stroke_style_combo.addItem("Dash dot", STROKE_STYLE_DASH_DOT)
        self.stroke_style_combo.currentIndexChanged.connect(self._stroke_style_changed)
        self._configure_compact_toolbar_height(self.stroke_style_combo)
        style_layout.addWidget(self.stroke_style_combo)
        style_layout.addWidget(self._create_toolbar_label("Blur"))
        self.blur_block_spin = QSpinBox()
        self.blur_block_spin.setRange(4, 64)
        self.blur_block_spin.setValue(self.canvas.blur_block_size())
        self.blur_block_spin.valueChanged.connect(self._blur_block_size_changed)
        self._configure_compact_toolbar_height(self.blur_block_spin)
        style_layout.addWidget(self.blur_block_spin)
        style_layout.addStretch(1)
        self._property_tabs.addTab(style_tab, "Style")

        text_tab = QWidget()
        text_layout = QHBoxLayout(text_tab)
        text_layout.setContentsMargins(4, 0, 4, 0)
        text_layout.setSpacing(3)
        text_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        text_layout.addWidget(self._create_toolbar_label("Font"))
        self.font_family_combo = QComboBox()
        self.font_family_combo.addItems(sorted(QFontDatabase.families()))
        self.font_family_combo.currentTextChanged.connect(self._font_family_changed)
        self._configure_compact_combo(self.font_family_combo, 120)
        text_layout.addWidget(self.font_family_combo)
        text_layout.addWidget(self._create_toolbar_label("Size"))
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
        text_layout.addWidget(self.font_size_combo)
        text_layout.addWidget(self._create_toolbar_label("Style"))
        self.text_style_combo = QComboBox()
        self.text_style_combo.addItem("Plain", TEXT_STYLE_PLAIN)
        self.text_style_combo.addItem("Box", TEXT_STYLE_BOX)
        self.text_style_combo.addItem("Bubble", TEXT_STYLE_BUBBLE)
        self.text_style_combo.currentIndexChanged.connect(self._text_style_changed)
        self._configure_compact_combo(self.text_style_combo, 78)
        text_layout.addWidget(self.text_style_combo)
        self.text_bold_button = QToolButton()
        self.text_bold_button.setText("B")
        self.text_bold_button.setCheckable(True)
        self.text_bold_button.clicked.connect(self._text_bold_toggled)
        self._configure_compact_icon_button(self.text_bold_button)
        text_layout.addWidget(self.text_bold_button)
        self.text_italic_button = QToolButton()
        self.text_italic_button.setText("I")
        self.text_italic_button.setCheckable(True)
        self.text_italic_button.clicked.connect(self._text_italic_toggled)
        self._configure_compact_icon_button(self.text_italic_button)
        text_layout.addWidget(self.text_italic_button)
        self.text_underline_button = QToolButton()
        self.text_underline_button.setText("U")
        self.text_underline_button.setCheckable(True)
        self.text_underline_button.clicked.connect(self._text_underline_toggled)
        self._configure_compact_icon_button(self.text_underline_button)
        text_layout.addWidget(self.text_underline_button)
        text_layout.addWidget(self._create_toolbar_label("Letter"))
        self.text_letter_spacing_spin = QDoubleSpinBox()
        self.text_letter_spacing_spin.setDecimals(1)
        self.text_letter_spacing_spin.setSingleStep(0.2)
        self.text_letter_spacing_spin.setRange(-4.0, 20.0)
        self.text_letter_spacing_spin.setValue(self._text_letter_spacing)
        self.text_letter_spacing_spin.valueChanged.connect(self._text_letter_spacing_changed)
        self._configure_compact_combo(self.text_letter_spacing_spin, 56)
        self.text_letter_spacing_spin.setEnabled(False)
        text_layout.addWidget(self.text_letter_spacing_spin)
        text_layout.addWidget(self._create_toolbar_label("Line"))
        self.text_line_spacing_spin = QDoubleSpinBox()
        self.text_line_spacing_spin.setDecimals(2)
        self.text_line_spacing_spin.setSingleStep(0.05)
        self.text_line_spacing_spin.setRange(0.7, 3.0)
        self.text_line_spacing_spin.setValue(self._text_line_spacing)
        self.text_line_spacing_spin.valueChanged.connect(self._text_line_spacing_changed)
        self._configure_compact_combo(self.text_line_spacing_spin, 56)
        self.text_line_spacing_spin.setEnabled(False)
        text_layout.addWidget(self.text_line_spacing_spin)
        text_layout.addWidget(self._create_toolbar_label("Pad"))
        self.text_padding_spin = QDoubleSpinBox()
        self.text_padding_spin.setDecimals(1)
        self.text_padding_spin.setSingleStep(1.0)
        self.text_padding_spin.setRange(0.0, 80.0)
        self.text_padding_spin.setValue(self._text_box_padding)
        self.text_padding_spin.valueChanged.connect(self._text_padding_changed)
        self._configure_compact_combo(self.text_padding_spin, 56)
        self.text_padding_spin.setEnabled(False)
        text_layout.addWidget(self.text_padding_spin)
        text_layout.addWidget(self._create_toolbar_label("Radius"))
        self.text_radius_spin = QDoubleSpinBox()
        self.text_radius_spin.setDecimals(1)
        self.text_radius_spin.setSingleStep(1.0)
        self.text_radius_spin.setRange(0.0, 80.0)
        self.text_radius_spin.setValue(self._text_corner_radius)
        self.text_radius_spin.valueChanged.connect(self._text_radius_changed)
        self._configure_compact_combo(self.text_radius_spin, 56)
        self.text_radius_spin.setEnabled(False)
        text_layout.addWidget(self.text_radius_spin)
        text_layout.addStretch(1)
        self._property_tabs.addTab(text_tab, "Text")

        arrange_tab = QWidget()
        arrange_layout = QHBoxLayout(arrange_tab)
        arrange_layout.setContentsMargins(4, 0, 4, 0)
        arrange_layout.setSpacing(3)
        arrange_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.snap_to_grid_button = QToolButton()
        self.snap_to_grid_button.setText("Snap")
        self.snap_to_grid_button.setCheckable(True)
        self.snap_to_grid_button.clicked.connect(self._snap_toggled)
        self._configure_compact_toolbar_height(self.snap_to_grid_button)
        arrange_layout.addWidget(self.snap_to_grid_button)
        self.grid_visible_button = QToolButton()
        self.grid_visible_button.setText("Grid")
        self.grid_visible_button.setCheckable(True)
        self.grid_visible_button.clicked.connect(self._grid_toggled)
        self._configure_compact_toolbar_height(self.grid_visible_button)
        arrange_layout.addWidget(self.grid_visible_button)
        arrange_layout.addWidget(self._create_toolbar_label("Size"))
        self.grid_size_combo = QComboBox()
        self.grid_size_combo.addItems(["8", "12", "16", "20", "24", "32", "40", "48"])
        self.grid_size_combo.setCurrentText("16")
        self.grid_size_combo.currentTextChanged.connect(self._grid_size_changed)
        self._configure_compact_combo(self.grid_size_combo, 52)
        self._configure_compact_toolbar_height(self.grid_size_combo)
        arrange_layout.addWidget(self.grid_size_combo)
        arrange_layout.addSpacing(6)
        arrange_layout.addWidget(self._create_toolbar_label("Layer"))
        self.layer_combo = QComboBox()
        self.layer_combo.setMinimumWidth(150)
        self.layer_combo.currentIndexChanged.connect(self._on_layer_combo_changed)
        self._configure_compact_toolbar_height(self.layer_combo)
        arrange_layout.addWidget(self.layer_combo)
        self.layer_visible_check = QCheckBox("Visible")
        self.layer_visible_check.toggled.connect(self._toggle_selected_layer_visibility)
        self._configure_compact_toolbar_height(self.layer_visible_check, 22)
        arrange_layout.addWidget(self.layer_visible_check)
        self.layer_lock_check = QCheckBox("Lock")
        self.layer_lock_check.toggled.connect(self._toggle_selected_layer_lock)
        self._configure_compact_toolbar_height(self.layer_lock_check, 22)
        arrange_layout.addWidget(self.layer_lock_check)
        self.layer_up_button = QPushButton("Up")
        self.layer_up_button.clicked.connect(self._move_selected_layer_up)
        self._configure_compact_toolbar_height(self.layer_up_button)
        arrange_layout.addWidget(self.layer_up_button)
        self.layer_down_button = QPushButton("Down")
        self.layer_down_button.clicked.connect(self._move_selected_layer_down)
        self._configure_compact_toolbar_height(self.layer_down_button)
        arrange_layout.addWidget(self.layer_down_button)
        arrange_layout.addSpacing(6)
        arrange_layout.addWidget(self._create_toolbar_label("X"))
        self.geometry_x_spin = QSpinBox()
        self.geometry_x_spin.setRange(-10000, 100000)
        self._configure_compact_combo(self.geometry_x_spin, 64)
        arrange_layout.addWidget(self.geometry_x_spin)
        arrange_layout.addWidget(self._create_toolbar_label("Y"))
        self.geometry_y_spin = QSpinBox()
        self.geometry_y_spin.setRange(-10000, 100000)
        self._configure_compact_combo(self.geometry_y_spin, 64)
        arrange_layout.addWidget(self.geometry_y_spin)
        arrange_layout.addWidget(self._create_toolbar_label("W"))
        self.geometry_w_spin = QSpinBox()
        self.geometry_w_spin.setRange(2, 100000)
        self._configure_compact_combo(self.geometry_w_spin, 64)
        arrange_layout.addWidget(self.geometry_w_spin)
        arrange_layout.addWidget(self._create_toolbar_label("H"))
        self.geometry_h_spin = QSpinBox()
        self.geometry_h_spin.setRange(2, 100000)
        self._configure_compact_combo(self.geometry_h_spin, 64)
        arrange_layout.addWidget(self.geometry_h_spin)
        self.geometry_apply_button = QPushButton("Apply")
        self.geometry_apply_button.clicked.connect(self._apply_selected_geometry)
        self._configure_compact_toolbar_height(self.geometry_apply_button)
        arrange_layout.addWidget(self.geometry_apply_button)
        arrange_layout.addStretch(1)
        self._property_tabs.addTab(arrange_tab, "Arrange")

        export_tab = QWidget()
        export_layout = QHBoxLayout(export_tab)
        export_layout.setContentsMargins(4, 0, 4, 0)
        export_layout.setSpacing(3)
        export_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        export_layout.addWidget(self._create_toolbar_label("Preset"))
        self.export_preset_combo = QComboBox()
        for preset_key, preset_values in self._export_presets.items():
            self.export_preset_combo.addItem(preset_values[0], preset_key)
        self.export_preset_combo.currentIndexChanged.connect(self._on_export_preset_index_changed)
        self._configure_compact_combo(self.export_preset_combo, 110)
        export_layout.addWidget(self.export_preset_combo)
        export_layout.addWidget(self._create_toolbar_label("Batch"))
        self.batch_profile_combo = QComboBox()
        self.batch_profile_combo.currentIndexChanged.connect(
            self._on_batch_profile_index_changed
        )
        self._configure_compact_combo(self.batch_profile_combo, 130)
        export_layout.addWidget(self.batch_profile_combo)
        self.manage_batch_profiles_button = QPushButton("Manage")
        self.manage_batch_profiles_button.clicked.connect(self.manage_batch_profiles)
        self._configure_compact_toolbar_height(self.manage_batch_profiles_button)
        export_layout.addWidget(self.manage_batch_profiles_button)
        self.export_batch_button = QPushButton("Batch Export")
        self.export_batch_button.clicked.connect(self.export_batch_with_dialog)
        self._configure_compact_toolbar_height(self.export_batch_button)
        export_layout.addWidget(self.export_batch_button)
        export_layout.addStretch(1)
        self._property_tabs.addTab(export_tab, "Export")
        self._fit_property_tabs_height()

        root_layout.addWidget(self._property_tabs)
        self._update_color_button_preview(self.stroke_button, QColor("#e74c3c"))
        self._update_color_button_preview(self.fill_button, QColor(231, 76, 60, 80))
        self._update_color_button_preview(self.text_color_button, QColor("#2c3e50"))
        self._apply_toolbar_tooltips()
        return bar

    def _fit_property_tabs_height(self) -> None:
        """
        Constrains property tabs to the height required by tab bar and content.

        Returns:
            None
        """

        if not hasattr(self, "_property_tabs"):
            return
        tab_bar_height = max(18, self._property_tabs.tabBar().sizeHint().height())
        content_height = 24
        for index in range(self._property_tabs.count()):
            page = self._property_tabs.widget(index)
            if page is None:
                continue
            content_height = max(content_height, page.sizeHint().height())
        # Border and pane chrome around the active page.
        self._property_tabs.setFixedHeight(tab_bar_height + content_height + 2)

    def _focus_property_tab_for_context(
        self,
        tool: str | None = None,
        selection_type: str | None = None,
    ) -> None:
        """
        Switches the property tab based on active tool or selection.

        Args:
            tool: Active tool identifier.
            selection_type: Selected annotation type when available.

        Returns:
            None
        """

        if not hasattr(self, "_property_tabs"):
            return
        resolved_type = str(selection_type or "").strip().lower()
        resolved_tool = str(tool or self._active_tool)
        if resolved_type == "text" or resolved_tool == Tool.TEXT:
            self._property_tabs.setCurrentIndex(self._PROPERTY_TAB_TEXT)
            return
        if resolved_tool in {
            Tool.RECT,
            Tool.ELLIPSE,
            Tool.LINE,
            Tool.ARROW,
            Tool.FILL_BG,
            Tool.BLUR,
            Tool.STEP,
            Tool.CROP,
        } or resolved_type in {"rect", "ellipse", "line", "arrow", "step", "image"}:
            self._property_tabs.setCurrentIndex(self._PROPERTY_TAB_STYLE)

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

    def _create_toolbar_label(self, text: str) -> QLabel:
        """
        Creates a compact label sized to the toolbar control row height.

        Args:
            text: Visible label caption.

        Returns:
            QLabel: Compact toolbar label.
        """

        label = QLabel(text)
        label.setObjectName("toolbarFieldLabel")
        label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self._configure_compact_toolbar_height(label, 22)
        return label

    def _configure_compact_combo(self, combo: QWidget, width: int) -> None:
        """
        Applies a fixed compact width to one toolbar combo or spin box.

        Args:
            combo: Target combo or spin box.
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
        self.text_letter_spacing_spin.setToolTip("Adjust text letter spacing.")
        self.text_line_spacing_spin.setToolTip("Adjust multiline line spacing.")
        self.text_padding_spin.setToolTip("Adjust text box inner padding.")
        self.text_radius_spin.setToolTip("Adjust text box corner radius.")
        self.snap_to_grid_button.setToolTip("Snap drawing and movement to grid.")
        self.grid_visible_button.setToolTip("Show or hide the alignment grid.")
        self.grid_size_combo.setToolTip("Choose grid spacing in pixels.")
        self.zoom_slider.setToolTip("Adjust zoom level. Shortcut: Shift+Mouse Wheel.")
        self.zoom_in_button.setToolTip("Zoom in. Shortcut: Ctrl++ or Shift+Mouse Wheel.")
        self.zoom_out_button.setToolTip("Zoom out. Shortcut: Ctrl+- or Shift+Mouse Wheel.")
        self.zoom_reset_button.setToolTip("Reset zoom to fit.")
        self.history_undo_button.setToolTip("Undo the last change.")
        self.history_redo_button.setToolTip("Redo the last undone change.")
        self.history_list_combo.setToolTip("History entries with action names.")
        self.history_status_label.setToolTip("Current history position.")
        self.layer_combo.setToolTip("Select one layer to inspect or edit.")
        self.layer_visible_check.setToolTip("Toggle visibility for selected layer.")
        self.layer_lock_check.setToolTip("Lock selected layer against edits.")
        self.layer_up_button.setToolTip("Move selected layer one step up.")
        self.layer_down_button.setToolTip("Move selected layer one step down.")
        self.geometry_x_spin.setToolTip("Set selected layer X position.")
        self.geometry_y_spin.setToolTip("Set selected layer Y position.")
        self.geometry_w_spin.setToolTip("Set selected layer width.")
        self.geometry_h_spin.setToolTip("Set selected layer height.")
        self.geometry_apply_button.setToolTip("Apply X/Y/W/H values to selected layer.")
        self.export_preset_combo.setToolTip("Select export quality preset.")
        self.batch_profile_combo.setToolTip("Select named batch export profile.")
        self.manage_batch_profiles_button.setToolTip("Rename, duplicate, delete, and reorder batch profiles.")
        self.export_batch_button.setToolTip("Export current tab to multiple formats.")

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

        new_canvas_action = QAction("New Canvas...", self)
        new_canvas_action.setShortcut(QKeySequence.StandardKey.New)
        new_canvas_action.setToolTip("Create a blank canvas with a custom size.")
        new_canvas_action.triggered.connect(self.new_canvas_requested.emit)
        file_menu.addAction(new_canvas_action)

        file_menu.addSeparator()

        open_action = QAction("Open Project...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.setToolTip("Open an existing Snappix project.")
        open_action.triggered.connect(self.open_project)
        file_menu.addAction(open_action)

        save_as_action = QAction("Save Project As...", self)
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_action.setToolTip("Save project under a new file name.")
        save_as_action.triggered.connect(self.save_project_as)
        file_menu.addAction(save_as_action)

        save_action = QAction("Save Project", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.setToolTip("Save changes to the current project.")
        save_action.triggered.connect(self.save_project)
        file_menu.addAction(save_action)

        export_action = QAction("Export...", self)
        export_action.setShortcut(QKeySequence("Ctrl+Shift+E"))
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

        export_batch = QAction("Batch Export...", self)
        export_batch.setToolTip("Export current tab to multiple formats at once.")
        export_batch.triggered.connect(self.export_batch_with_dialog)
        file_menu.addAction(export_batch)

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

        import_image_action = QAction("Import Image...", self)
        import_image_action.setToolTip("Insert an image file into the current document.")
        import_image_action.triggered.connect(self.import_image)
        edit_menu.addAction(import_image_action)

        paste_action = QAction("Paste", self)
        paste_action.setShortcut(QKeySequence.StandardKey.Paste)
        paste_action.setToolTip("Paste text or image from clipboard.")
        paste_action.triggered.connect(self.paste_from_clipboard)
        edit_menu.addAction(paste_action)

        copy_canvas_area_action = QAction("Copy Drawing Area", self)
        copy_canvas_area_action.setShortcut(QKeySequence("Ctrl+Shift+C"))
        copy_canvas_area_action.setToolTip("Copy this tab drawing area for another tab.")
        copy_canvas_area_action.triggered.connect(self.copy_drawing_area_to_clipboard)
        edit_menu.addAction(copy_canvas_area_action)

        paste_canvas_area_action = QAction("Paste Drawing Area", self)
        paste_canvas_area_action.setShortcut(QKeySequence("Ctrl+Shift+V"))
        paste_canvas_area_action.setToolTip("Paste copied drawing area into this tab.")
        paste_canvas_area_action.triggered.connect(self.paste_drawing_area_from_clipboard)
        edit_menu.addAction(paste_canvas_area_action)

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

        view_menu.addSeparator()
        zoom_in_action = QAction("Zoom In", self)
        zoom_in_action.setShortcuts(
            [
                QKeySequence.StandardKey.ZoomIn,
                QKeySequence("Ctrl++"),
                QKeySequence("Ctrl+="),
            ]
        )
        zoom_in_action.setToolTip("Zoom in on the canvas.")
        zoom_in_action.triggered.connect(self.canvas.zoom_in)
        view_menu.addAction(zoom_in_action)

        zoom_out_action = QAction("Zoom Out", self)
        zoom_out_action.setShortcuts(
            [
                QKeySequence.StandardKey.ZoomOut,
                QKeySequence("Ctrl+-"),
            ]
        )
        zoom_out_action.setToolTip("Zoom out on the canvas.")
        zoom_out_action.triggered.connect(self.canvas.zoom_out)
        view_menu.addAction(zoom_out_action)

        zoom_reset_action = QAction("Reset Zoom", self)
        zoom_reset_action.setShortcut(QKeySequence("Ctrl+0"))
        zoom_reset_action.setToolTip("Reset zoom to fit the document.")
        zoom_reset_action.triggered.connect(self.canvas.reset_zoom)
        view_menu.addAction(zoom_reset_action)

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
        self._focus_property_tab_for_context(tool=tool)
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
        self.canvas.refresh_workspace_theme()

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

    def _text_letter_spacing_changed(self, value: float) -> None:
        """
        Updates active and selected text letter spacing.

        Args:
            value: Letter spacing in pixels.

        Returns:
            None
        """

        self._text_letter_spacing = float(value)
        self._set_next_history_label("Change letter spacing")
        self.canvas.set_style(letter_spacing=self._text_letter_spacing)
        self._push_history_state()

    def _text_line_spacing_changed(self, value: float) -> None:
        """
        Updates active and selected text line spacing.

        Args:
            value: Line spacing multiplier.

        Returns:
            None
        """

        self._text_line_spacing = float(value)
        self._set_next_history_label("Change line spacing")
        self.canvas.set_style(line_spacing_factor=self._text_line_spacing)
        self._push_history_state()

    def _text_padding_changed(self, value: float) -> None:
        """
        Updates active and selected text box padding.

        Args:
            value: Inner box padding in pixels.

        Returns:
            None
        """

        self._text_box_padding = float(value)
        self._set_next_history_label("Change text box padding")
        self.canvas.set_style(box_padding=self._text_box_padding)
        self._push_history_state()

    def _text_radius_changed(self, value: float) -> None:
        """
        Updates active and selected text box corner radius.

        Args:
            value: Corner radius in pixels.

        Returns:
            None
        """

        self._text_corner_radius = float(value)
        self._set_next_history_label("Change text box radius")
        self.canvas.set_style(corner_radius=self._text_corner_radius)
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
        self._refresh_layer_panel()
        self._show_canvas_action_notification(action_label)
        self._apply_one_shot_tool_completion(action_label)

    def _show_canvas_action_notification(self, action_label: str) -> None:
        """
        Shows user-facing notifications for important canvas actions.

        Args:
            action_label: Last canvas action label.

        Returns:
            None
        """

        message_by_action = {
            "Copy OCR text": "OCR text copied to clipboard.",
            "OCR found no text": "OCR completed, but no text was found.",
            "OCR unavailable: install tesseract-ocr": "OCR unavailable. Please install tesseract-ocr.",
        }
        message = message_by_action.get(action_label)
        if message is None:
            return
        self.statusBar().showMessage(message, 4500)

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

        selection_type = str(payload.get("type", "") or "").strip().lower()
        if selection_type:
            self._focus_property_tab_for_context(selection_type=selection_type)

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
            self._set_target_color("stroke", color, apply_to_canvas=False)

        fill_rgba = payload.get("fill_rgba")
        if isinstance(fill_rgba, list) and len(fill_rgba) == 4:
            color = QColor(
                int(fill_rgba[0]),
                int(fill_rgba[1]),
                int(fill_rgba[2]),
                int(fill_rgba[3]),
            )
            self._set_target_color("fill", color, apply_to_canvas=False)

        text_rgba = payload.get("text_rgba")
        if isinstance(text_rgba, list) and len(text_rgba) == 4:
            color = QColor(
                int(text_rgba[0]),
                int(text_rgba[1]),
                int(text_rgba[2]),
                int(text_rgba[3]),
            )
            self._set_target_color("text", color, apply_to_canvas=False)

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
        letter_spacing = payload.get("letter_spacing")
        if isinstance(letter_spacing, (int, float)):
            self._text_letter_spacing = float(letter_spacing)
            self.text_letter_spacing_spin.blockSignals(True)
            self.text_letter_spacing_spin.setValue(float(letter_spacing))
            self.text_letter_spacing_spin.blockSignals(False)
        line_spacing_factor = payload.get("line_spacing_factor")
        if isinstance(line_spacing_factor, (int, float)):
            self._text_line_spacing = float(line_spacing_factor)
            self.text_line_spacing_spin.blockSignals(True)
            self.text_line_spacing_spin.setValue(float(line_spacing_factor))
            self.text_line_spacing_spin.blockSignals(False)
        box_padding = payload.get("box_padding")
        if isinstance(box_padding, (int, float)):
            self._text_box_padding = float(box_padding)
            self.text_padding_spin.blockSignals(True)
            self.text_padding_spin.setValue(float(box_padding))
            self.text_padding_spin.blockSignals(False)
        corner_radius = payload.get("corner_radius")
        if isinstance(corner_radius, (int, float)):
            self._text_corner_radius = float(corner_radius)
            self.text_radius_spin.blockSignals(True)
            self.text_radius_spin.setValue(float(corner_radius))
            self.text_radius_spin.blockSignals(False)
        has_text_selection = str(payload.get("type") or "") == "text"
        text_style = str(payload.get("text_style") or TEXT_STYLE_PLAIN)
        supports_container_layout = text_style in {TEXT_STYLE_BOX, TEXT_STYLE_BUBBLE}
        self.text_letter_spacing_spin.setEnabled(has_text_selection)
        self.text_line_spacing_spin.setEnabled(supports_container_layout)
        self.text_padding_spin.setEnabled(supports_container_layout)
        self.text_radius_spin.setEnabled(supports_container_layout)

        self._update_geometry_controls_from_payload(payload)
        self._sync_layer_controls_from_payload(payload)
        self._selection_info_label.setText(format_selection_info(payload))

    def _refresh_layer_panel(self) -> None:
        """
        Rebuilds layer list and keeps the selected entry in sync.

        Returns:
            None
        """

        layer_payloads = self.canvas.list_layer_payloads()
        selected_id = ""
        for payload in layer_payloads:
            if bool(payload.get("selected")):
                selected_id = str(payload.get("id") or "")
                break

        self._syncing_layer_panel = True
        self.layer_combo.clear()
        for payload in layer_payloads:
            label = str(payload.get("name") or "Layer")
            layer_id = str(payload.get("id") or "")
            self.layer_combo.addItem(label, layer_id)
        if selected_id:
            selected_index = self.layer_combo.findData(selected_id)
            if selected_index >= 0:
                self.layer_combo.setCurrentIndex(selected_index)
        self._syncing_layer_panel = False
        self._set_layer_controls_enabled(bool(layer_payloads))

    def _set_layer_controls_enabled(self, enabled: bool) -> None:
        """
        Enables or disables layer and geometry controls.

        Args:
            enabled: True to enable controls.

        Returns:
            None
        """

        self.layer_combo.setEnabled(enabled)
        self.layer_visible_check.setEnabled(enabled)
        self.layer_lock_check.setEnabled(enabled)
        self.layer_up_button.setEnabled(enabled)
        self.layer_down_button.setEnabled(enabled)
        self.geometry_x_spin.setEnabled(enabled)
        self.geometry_y_spin.setEnabled(enabled)
        self.geometry_w_spin.setEnabled(enabled)
        self.geometry_h_spin.setEnabled(enabled)
        self.geometry_apply_button.setEnabled(enabled)

    def _selected_layer_id(self) -> str:
        """
        Returns currently selected layer id from the layer combo.

        Returns:
            str: Selected layer id or empty string.
        """

        data = self.layer_combo.currentData()
        if not isinstance(data, str):
            return ""
        return data.strip()

    def _on_layer_combo_changed(self, _index: int) -> None:
        """
        Selects a layer on canvas when layer combo selection changes.

        Args:
            _index: Current combo index.

        Returns:
            None
        """

        if self._syncing_layer_panel:
            return
        layer_id = self._selected_layer_id()
        if not layer_id:
            return
        self.canvas.select_layer_by_id(layer_id)

    def _toggle_selected_layer_visibility(self, checked: bool) -> None:
        """
        Toggles visibility for the currently selected layer.

        Args:
            checked: True when layer should stay visible.

        Returns:
            None
        """

        if self._syncing_layer_panel:
            return
        layer_id = self._selected_layer_id()
        if not layer_id:
            return
        if self.canvas.set_layer_visible(layer_id, bool(checked)):
            self._set_next_history_label("Toggle layer visibility")
            self._push_history_state()
        self._refresh_layer_panel()

    def _toggle_selected_layer_lock(self, checked: bool) -> None:
        """
        Toggles lock state for the currently selected layer.

        Args:
            checked: True when layer should be locked.

        Returns:
            None
        """

        if self._syncing_layer_panel:
            return
        layer_id = self._selected_layer_id()
        if not layer_id:
            return
        if self.canvas.set_layer_locked(layer_id, bool(checked)):
            self._set_next_history_label("Toggle layer lock")
            self._push_history_state()
        self._refresh_layer_panel()

    def _move_selected_layer_up(self) -> None:
        """
        Moves current selected layer one step forward.

        Returns:
            None
        """

        self._set_next_history_label("Move layer up")
        self.canvas.bring_selected_forward()
        self._refresh_layer_panel()

    def _move_selected_layer_down(self) -> None:
        """
        Moves current selected layer one step backward.

        Returns:
            None
        """

        self._set_next_history_label("Move layer down")
        self.canvas.send_selected_backward()
        self._refresh_layer_panel()

    def _update_geometry_controls_from_payload(self, payload: dict[str, Any]) -> None:
        """
        Synchronizes X/Y/W/H controls from current selection payload.

        Args:
            payload: Selection payload from canvas.

        Returns:
            None
        """

        x_value = payload.get("x")
        y_value = payload.get("y")
        width_value = payload.get("width")
        height_value = payload.get("height")
        if not (
            isinstance(x_value, (int, float))
            and isinstance(y_value, (int, float))
            and isinstance(width_value, (int, float))
            and isinstance(height_value, (int, float))
        ):
            return
        self.geometry_x_spin.blockSignals(True)
        self.geometry_y_spin.blockSignals(True)
        self.geometry_w_spin.blockSignals(True)
        self.geometry_h_spin.blockSignals(True)
        self.geometry_x_spin.setValue(int(round(x_value)))
        self.geometry_y_spin.setValue(int(round(y_value)))
        self.geometry_w_spin.setValue(max(2, int(round(width_value))))
        self.geometry_h_spin.setValue(max(2, int(round(height_value))))
        self.geometry_x_spin.blockSignals(False)
        self.geometry_y_spin.blockSignals(False)
        self.geometry_w_spin.blockSignals(False)
        self.geometry_h_spin.blockSignals(False)

    def _sync_layer_controls_from_payload(self, payload: dict[str, Any]) -> None:
        """
        Synchronizes layer controls from current selection payload.

        Args:
            payload: Selection payload from canvas.

        Returns:
            None
        """

        layer_id = payload.get("layer_id")
        if isinstance(layer_id, str) and layer_id:
            if self.layer_combo.findData(layer_id) >= 0:
                self._syncing_layer_panel = True
                self.layer_combo.setCurrentIndex(self.layer_combo.findData(layer_id))
                self._syncing_layer_panel = False
        self.layer_visible_check.blockSignals(True)
        self.layer_lock_check.blockSignals(True)
        self.layer_visible_check.setChecked(bool(payload.get("visible", True)))
        self.layer_lock_check.setChecked(bool(payload.get("locked", False)))
        self.layer_visible_check.blockSignals(False)
        self.layer_lock_check.blockSignals(False)

    def _apply_selected_geometry(self) -> None:
        """
        Applies inspector X/Y/W/H values to current selected layer.

        Returns:
            None
        """

        if self.canvas.set_selected_geometry(
            x=float(self.geometry_x_spin.value()),
            y=float(self.geometry_y_spin.value()),
            width=float(self.geometry_w_spin.value()),
            height=float(self.geometry_h_spin.value()),
        ):
            self._set_next_history_label("Set selection geometry")
            self._push_history_state()
            self._refresh_layer_panel()

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
            "base_content": self.canvas.base_content_payload(),
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
        self.canvas.restore_base_content_payload(snapshot.get("base_content"))
        self._record_history = True
        self._refresh_layer_panel()

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

    def import_image(self) -> None:
        """
        Prompts for one image file and inserts it into the canvas.

        Returns:
            None
        """

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Image",
            "",
            "Images (*.png *.jpg *.jpeg *.gif *.bmp *.webp *.tif *.tiff);;All Files (*)",
        )
        if not file_path:
            return
        if not self.canvas.import_image_file(file_path):
            QMessageBox.warning(
                self,
                APP_NAME,
                "Could not import the selected image file.",
            )
            return
        self.statusBar().showMessage("Image imported")

    def save_project_as(self) -> None:
        """
        Saves current screenshot project to a Snappix file.

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
        Loads a Snappix project from disk.

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
        self._refresh_layer_panel()
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

        return f"{tempfile.gettempdir()}/snappix-autosave{APP_FILE_EXTENSION}"

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
        self._refresh_layer_panel()
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
        if not os.path.isfile(recovery_path):
            return False
        try:
            project_model = load_project(recovery_path)
        except OSError:
            return False
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

    def _on_export_preset_index_changed(self, _index: int) -> None:
        """
        Handles export preset combo-box selection changes.

        Args:
            _index: Current combo index.

        Returns:
            None
        """

        preset_key = self.export_preset()
        if not preset_key:
            return
        self._apply_export_preset_values(preset_key)
        self.export_preset_changed.emit(preset_key)

    def _apply_export_preset_values(self, preset_key: str) -> None:
        """
        Applies quality defaults from one export preset.

        Args:
            preset_key: Export preset key.

        Returns:
            None
        """

        values = self._export_presets.get(normalize_export_preset(preset_key))
        if values is None:
            return
        label, jpeg_quality, pdf_dpi = values
        self._jpeg_quality = jpeg_quality
        self._pdf_dpi = pdf_dpi
        self.statusBar().showMessage(
            f"Preset '{label}' applied: JPG {self._jpeg_quality}, PDF {self._pdf_dpi} DPI",
            2500,
        )

    def set_export_preset(self, preset_key: str, *, emit_signal: bool = False) -> None:
        """
        Selects the export preset in the toolbar.

        Args:
            preset_key: Export preset key to select.
            emit_signal: True to emit the changed signal.

        Returns:
            None
        """

        normalized = normalize_export_preset(preset_key)
        index = self.export_preset_combo.findData(normalized)
        if index < 0:
            return
        self.export_preset_combo.blockSignals(True)
        self.export_preset_combo.setCurrentIndex(index)
        self.export_preset_combo.blockSignals(False)
        self._apply_export_preset_values(normalized)
        if emit_signal:
            self.export_preset_changed.emit(normalized)

    def set_auto_crop_on_shrink(self, enabled: bool) -> None:
        """
        Enables or disables automatic canvas crop when content shrinks.

        Args:
            enabled: True to crop unused margins automatically.

        Returns:
            None
        """

        self.canvas.set_auto_crop_on_shrink(enabled)

    def export_preset(self) -> str:
        """
        Returns the currently selected export preset key.

        Returns:
            str: Export preset key.
        """

        data = self.export_preset_combo.currentData()
        if not isinstance(data, str):
            return EXPORT_PRESET_DOCS
        return normalize_export_preset(data)

    def _normalize_batch_profile_key(self, value: str) -> str:
        """
        Normalizes one batch profile key string.

        Args:
            value: Raw key or label text.

        Returns:
            str: Normalized key value.
        """

        normalized = "".join(
            character.lower()
            if character.isalnum() or character == "_"
            else "_"
            for character in value.strip()
        ).strip("_")
        return normalized or "profile"

    def _sanitize_batch_export_profiles(
        self,
        profiles: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Sanitizes batch export profile entries for runtime use.

        Args:
            profiles: Raw profile list.

        Returns:
            list[dict[str, Any]]: Validated profile list.
        """

        sanitized: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        for index, profile in enumerate(profiles):
            if not isinstance(profile, dict):
                continue
            key = self._normalize_batch_profile_key(str(profile.get("key", "")))
            if key in seen_keys:
                continue
            label = str(profile.get("label", "")).strip() or f"Profile {index + 1}"
            formats = [
                str(value).strip().lower()
                for value in list(profile.get("formats", []))
                if str(value).strip().lower() in {"png", "jpg", "pdf"}
            ]
            if not formats:
                formats = ["png"]
            sanitized.append(
                {
                    "key": key,
                    "label": label,
                    "formats": formats,
                    "jpg_quality": max(1, min(100, int(profile.get("jpg_quality", 90)))),
                    "pdf_dpi": max(72, min(1200, int(profile.get("pdf_dpi", 300)))),
                }
            )
            seen_keys.add(key)
        if sanitized:
            return sanitized
        return [
            {
                "key": "docs_hq",
                "label": "Docs HQ",
                "formats": ["png", "jpg", "pdf"],
                "jpg_quality": 90,
                "pdf_dpi": 300,
            }
        ]

    def set_batch_export_profiles(
        self,
        profiles: list[dict[str, Any]],
        *,
        selected_key: str = "",
        emit_signal: bool = False,
    ) -> None:
        """
        Sets available batch export profiles and refreshes profile selector.

        Args:
            profiles: Profile definitions.
            selected_key: Preferred selected profile key.
            emit_signal: True to emit profile-changed signal.

        Returns:
            None
        """

        self._batch_export_profiles = self._sanitize_batch_export_profiles(profiles)
        preferred_key = self._normalize_batch_profile_key(selected_key)
        available_keys = {profile["key"] for profile in self._batch_export_profiles}
        if preferred_key not in available_keys:
            preferred_key = self._batch_export_profiles[0]["key"]
        self._batch_export_profile_key = preferred_key
        self.batch_profile_combo.blockSignals(True)
        self.batch_profile_combo.clear()
        for profile in self._batch_export_profiles:
            self.batch_profile_combo.addItem(profile["label"], profile["key"])
        selected_index = self.batch_profile_combo.findData(self._batch_export_profile_key)
        if selected_index >= 0:
            self.batch_profile_combo.setCurrentIndex(selected_index)
        self.batch_profile_combo.blockSignals(False)
        if emit_signal:
            self.batch_export_profiles_changed.emit(
                [dict(profile) for profile in self._batch_export_profiles],
                self._batch_export_profile_key,
            )

    def batch_export_profiles(self) -> list[dict[str, Any]]:
        """
        Returns the current batch export profile list.

        Returns:
            list[dict[str, Any]]: Batch profile definitions.
        """

        return [dict(profile) for profile in self._batch_export_profiles]

    def set_batch_export_last_directory(
        self,
        path: str,
        *,
        emit_signal: bool = False,
    ) -> None:
        """
        Sets the remembered batch export output directory.

        Args:
            path: Directory path.
            emit_signal: True to emit directory-changed signal.

        Returns:
            None
        """

        self._batch_export_last_directory = path.strip()
        if emit_signal:
            self.batch_export_last_directory_changed.emit(self._batch_export_last_directory)

    def batch_export_last_directory(self) -> str:
        """
        Returns the remembered batch export output directory.

        Returns:
            str: Last used directory path.
        """

        return self._batch_export_last_directory

    def _selected_batch_profile_definition(self) -> dict[str, Any]:
        """
        Returns the active batch profile definition.

        Returns:
            dict[str, Any]: Selected batch profile.
        """

        if not self._batch_export_profiles:
            return {
                "key": "docs_hq",
                "label": "Docs HQ",
                "formats": ["png", "jpg", "pdf"],
                "jpg_quality": 90,
                "pdf_dpi": 300,
            }
        for profile in self._batch_export_profiles:
            if profile["key"] == self._batch_export_profile_key:
                return profile
        return self._batch_export_profiles[0]

    def _on_batch_profile_index_changed(self, _index: int) -> None:
        """
        Updates active batch profile from selector changes.

        Args:
            _index: Current profile combo index.

        Returns:
            None
        """

        data = self.batch_profile_combo.currentData()
        if not isinstance(data, str):
            return
        self._batch_export_profile_key = self._normalize_batch_profile_key(data)
        self.batch_export_profiles_changed.emit(
            [dict(profile) for profile in self._batch_export_profiles],
            self._batch_export_profile_key,
        )

    def manage_batch_profiles(self) -> None:
        """
        Opens profile management dialog for renaming and deleting profiles.

        Returns:
            None
        """

        profiles_working = [dict(profile) for profile in self._batch_export_profiles]

        dialog = QDialog(self)
        dialog.setWindowTitle("Manage Batch Export Profiles")
        dialog.setModal(True)
        dialog.resize(420, 300)
        root_layout = QVBoxLayout(dialog)
        root_layout.addWidget(QLabel("Saved profiles:"))

        list_widget = QListWidget(dialog)
        list_widget.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        list_widget.setDefaultDropAction(Qt.DropAction.MoveAction)
        list_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        for profile in profiles_working:
            item = QListWidgetItem(f"{profile['label']} ({profile['key']})")
            item.setData(Qt.ItemDataRole.UserRole, profile["key"])
            list_widget.addItem(item)
        selected_index = 0
        for index, profile in enumerate(profiles_working):
            if profile["key"] == self._batch_export_profile_key:
                selected_index = index
                break
        if list_widget.count() > 0:
            list_widget.setCurrentRow(selected_index)
        root_layout.addWidget(list_widget)

        actions_row = QHBoxLayout()
        rename_button = QPushButton("Rename", dialog)
        duplicate_button = QPushButton("Duplicate", dialog)
        delete_button = QPushButton("Delete", dialog)
        actions_row.addWidget(rename_button)
        actions_row.addWidget(duplicate_button)
        actions_row.addWidget(delete_button)
        actions_row.addStretch(1)
        root_layout.addLayout(actions_row)

        def profile_order_from_list() -> list[str]:
            order: list[str] = []
            for row in range(list_widget.count()):
                item = list_widget.item(row)
                if item is None:
                    continue
                key = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(key, str) and key.strip():
                    order.append(key.strip())
            return order

        def sync_profiles_from_list() -> None:
            nonlocal profiles_working
            key_order = profile_order_from_list()
            by_key = {
                str(profile["key"]): dict(profile)
                for profile in profiles_working
            }
            reordered: list[dict[str, Any]] = []
            for key in key_order:
                profile = by_key.get(key)
                if profile is not None:
                    reordered.append(profile)
            # Keep any profiles that were not represented in the widget.
            represented = {str(profile["key"]) for profile in reordered}
            for profile in profiles_working:
                key = str(profile["key"])
                if key in represented:
                    continue
                reordered.append(dict(profile))
            profiles_working = reordered

        def index_for_key(profile_key: str) -> int:
            for idx, profile in enumerate(profiles_working):
                if str(profile["key"]) == profile_key:
                    return idx
            return -1

        def selected_profile_key() -> str:
            item = list_widget.currentItem()
            if item is None:
                return ""
            key = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(key, str):
                return ""
            return key.strip()

        def selected_profile_index() -> int:
            key = selected_profile_key()
            if not key:
                return -1
            sync_profiles_from_list()
            return index_for_key(key)

        def refresh_list_labels() -> None:
            label_by_key = {
                str(profile["key"]): str(profile["label"])
                for profile in profiles_working
            }
            for row in range(list_widget.count()):
                item = list_widget.item(row)
                if item is None:
                    continue
                key = item.data(Qt.ItemDataRole.UserRole)
                if not isinstance(key, str):
                    continue
                label = label_by_key.get(key.strip(), key.strip())
                item.setText(f"{label} ({key.strip()})")

        def unique_profile_key(base_value: str) -> str:
            seed = self._normalize_batch_profile_key(base_value)
            existing = {
                str(profile["key"])
                for profile in profiles_working
            }
            if seed not in existing:
                return seed
            counter = 2
            while f"{seed}_{counter}" in existing:
                counter += 1
            return f"{seed}_{counter}"

        def rename_selected_profile() -> None:
            index = selected_profile_index()
            if index < 0:
                return
            current_profile = profiles_working[index]
            next_label, accepted = QInputDialog.getText(
                dialog,
                "Rename Profile",
                "Profile name:",
                QLineEdit.EchoMode.Normal,
                str(current_profile["label"]),
            )
            if not accepted:
                return
            cleaned_label = next_label.strip()
            if not cleaned_label:
                return
            current_profile["label"] = cleaned_label
            refresh_list_labels()

        def duplicate_selected_profile() -> None:
            index = selected_profile_index()
            if index < 0:
                return
            source_profile = dict(profiles_working[index])
            suggested_name = f"{source_profile['label']} Copy"
            profile_name, accepted = QInputDialog.getText(
                dialog,
                "Duplicate Profile",
                "New profile name:",
                QLineEdit.EchoMode.Normal,
                suggested_name,
            )
            if not accepted:
                return
            cleaned_name = profile_name.strip() or suggested_name
            new_key = unique_profile_key(cleaned_name)
            duplicated = {
                "key": new_key,
                "label": cleaned_name,
                "formats": list(source_profile.get("formats", ["png"])),
                "jpg_quality": int(source_profile.get("jpg_quality", 90)),
                "pdf_dpi": int(source_profile.get("pdf_dpi", 300)),
            }
            profiles_working.append(duplicated)
            item = QListWidgetItem(f"{duplicated['label']} ({duplicated['key']})")
            item.setData(Qt.ItemDataRole.UserRole, duplicated["key"])
            list_widget.addItem(item)
            list_widget.setCurrentRow(list_widget.count() - 1)

        def delete_selected_profile() -> None:
            index = selected_profile_index()
            if index < 0:
                return
            if len(profiles_working) <= 1:
                QMessageBox.warning(
                    dialog,
                    APP_NAME,
                    "At least one profile must remain.",
                )
                return
            profile = profiles_working[index]
            answer = QMessageBox.question(
                dialog,
                "Delete Profile",
                f"Delete profile '{profile['label']}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            profiles_working.pop(index)
            row = list_widget.currentRow()
            if row >= 0:
                list_widget.takeItem(row)
            if list_widget.count() > 0:
                list_widget.setCurrentRow(max(0, min(row, list_widget.count() - 1)))

        rename_button.clicked.connect(rename_selected_profile)
        duplicate_button.clicked.connect(duplicate_selected_profile)
        delete_button.clicked.connect(delete_selected_profile)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        root_layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        sync_profiles_from_list()
        selected_row = list_widget.currentRow()
        selected_key = self._batch_export_profile_key
        if 0 <= selected_row < list_widget.count():
            item = list_widget.item(selected_row)
            if item is not None:
                key = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(key, str) and key.strip():
                    selected_key = key.strip()
        self.set_batch_export_profiles(
            profiles_working,
            selected_key=selected_key,
            emit_signal=True,
        )

    def export_batch_with_dialog(self) -> None:
        """
        Opens a dialog to export the current tab in multiple formats.

        Returns:
            None
        """

        start_dir = self._batch_export_last_directory
        if not start_dir and self._current_project_path:
            start_dir = str(Path(self._current_project_path).resolve().parent)
        directory_path = QFileDialog.getExistingDirectory(
            self,
            "Select Batch Export Folder",
            start_dir,
        )
        if not directory_path:
            return
        self.set_batch_export_last_directory(directory_path, emit_signal=True)

        default_base = "snappix-export"
        if self._current_project_path:
            default_base = Path(self._current_project_path).stem

        base_name, accepted = QInputDialog.getText(
            self,
            "Batch Export",
            "Base file name:",
            QLineEdit.EchoMode.Normal,
            default_base,
        )
        if not accepted:
            return

        export_options = self._ask_batch_export_options(
            current_profile=self._selected_batch_profile_definition(),
            profiles=self.batch_export_profiles(),
        )
        if export_options is None:
            return
        include_png = bool(export_options["include_png"])
        include_jpg = bool(export_options["include_jpg"])
        include_pdf = bool(export_options["include_pdf"])
        self._jpeg_quality = int(export_options["jpg_quality"])
        self._pdf_dpi = int(export_options["pdf_dpi"])
        selected_profile_key = str(export_options["selected_profile_key"])
        custom_profile_name = str(export_options["save_profile_name"]).strip()
        self._batch_export_profile_key = self._normalize_batch_profile_key(selected_profile_key)
        if custom_profile_name:
            custom_key = self._normalize_batch_profile_key(custom_profile_name)
            updated_profile = {
                "key": custom_key,
                "label": custom_profile_name,
                "formats": [
                    fmt
                    for fmt, enabled in (
                        ("png", include_png),
                        ("jpg", include_jpg),
                        ("pdf", include_pdf),
                    )
                    if enabled
                ],
                "jpg_quality": self._jpeg_quality,
                "pdf_dpi": self._pdf_dpi,
            }
            merged = [profile for profile in self._batch_export_profiles if profile["key"] != custom_key]
            merged.append(updated_profile)
            self.set_batch_export_profiles(
                merged,
                selected_key=custom_key,
                emit_signal=True,
            )
        else:
            self.set_batch_export_profiles(
                self._batch_export_profiles,
                selected_key=self._batch_export_profile_key,
                emit_signal=True,
            )

        normalized_base = base_name.strip() or default_base
        target_root = Path(directory_path)
        pixmap = self.canvas.export_composited_pixmap()
        if pixmap.isNull():
            QMessageBox.warning(self, APP_NAME, "Could not render image for batch export.")
            return

        queue: list[tuple[str, Path]] = []
        if include_png:
            queue.append(("png", target_root / f"{normalized_base}.png"))
        if include_jpg:
            queue.append(("jpg", target_root / f"{normalized_base}.jpg"))
        if include_pdf:
            queue.append(("pdf", target_root / f"{normalized_base}.pdf"))

        progress = QProgressDialog(
            "Starting batch export...",
            "Cancel",
            0,
            len(queue),
            self,
        )
        progress.setWindowTitle("Batch Export")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        saved_targets: list[str] = []
        for index, (fmt, target) in enumerate(queue, start=1):
            progress.setLabelText(f"Exporting {fmt.upper()} ({index}/{len(queue)})...")
            QApplication.processEvents()
            if progress.wasCanceled():
                break
            if fmt == "png":
                if pixmap.save(str(target), "PNG"):
                    saved_targets.append(str(target))
            elif fmt == "jpg":
                if pixmap.save(str(target), "JPG", max(1, min(100, self._jpeg_quality))):
                    saved_targets.append(str(target))
            else:
                self._write_pdf_to_path(str(target), max(72, min(1200, self._pdf_dpi)))
                if target.is_file():
                    saved_targets.append(str(target))
            progress.setValue(index)
            QApplication.processEvents()

        progress.close()

        if not saved_targets:
            if progress.wasCanceled():
                self.statusBar().showMessage("Batch export cancelled.", 2500)
            else:
                QMessageBox.warning(self, APP_NAME, "Batch export failed.")
            return
        self.statusBar().showMessage(
            f"Batch export complete ({len(saved_targets)} files)",
            3500,
        )

    def _ask_batch_export_options(
        self,
        current_profile: dict[str, Any],
        profiles: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """
        Prompts for target formats and profile settings used by batch export.

        Args:
            current_profile: Currently selected profile definition.
            profiles: Available saved profiles.

        Returns:
            dict[str, Any] | None: Selected batch export settings.
        """

        dialog = QDialog(self)
        dialog.setWindowTitle("Batch Export Formats")
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)
        profile_combo = QComboBox()
        for profile in profiles:
            profile_combo.addItem(str(profile["label"]), str(profile["key"]))
        selected_index = profile_combo.findData(str(current_profile["key"]))
        if selected_index >= 0:
            profile_combo.setCurrentIndex(selected_index)
        layout.addWidget(QLabel("Profile"))
        layout.addWidget(profile_combo)

        layout.addWidget(QLabel("Choose formats to export:"))
        png_check = QCheckBox("PNG")
        png_check.setChecked("png" in list(current_profile.get("formats", [])))
        jpg_check = QCheckBox("JPEG")
        jpg_check.setChecked("jpg" in list(current_profile.get("formats", [])))
        pdf_check = QCheckBox("PDF")
        pdf_check.setChecked("pdf" in list(current_profile.get("formats", [])))
        layout.addWidget(png_check)
        layout.addWidget(jpg_check)
        layout.addWidget(pdf_check)

        quality_row = QHBoxLayout()
        quality_row.setSpacing(6)
        quality_row.addWidget(QLabel("JPG"))
        jpg_quality_spin = QSpinBox()
        jpg_quality_spin.setRange(1, 100)
        jpg_quality_spin.setValue(int(current_profile.get("jpg_quality", self._jpeg_quality)))
        quality_row.addWidget(jpg_quality_spin)
        quality_row.addWidget(QLabel("PDF DPI"))
        pdf_dpi_spin = QSpinBox()
        pdf_dpi_spin.setRange(72, 1200)
        pdf_dpi_spin.setValue(int(current_profile.get("pdf_dpi", self._pdf_dpi)))
        quality_row.addWidget(pdf_dpi_spin)
        quality_row.addStretch(1)
        layout.addLayout(quality_row)

        save_profile_name_edit = QLineEdit()
        save_profile_name_edit.setPlaceholderText("Optional: save current options as profile name")
        layout.addWidget(save_profile_name_edit)

        profile_map = {
            str(profile["key"]): dict(profile)
            for profile in profiles
        }

        def on_profile_changed() -> None:
            selected_key = str(profile_combo.currentData() or "")
            selected_profile = profile_map.get(selected_key)
            if selected_profile is None:
                return
            selected_formats = list(selected_profile.get("formats", []))
            png_check.setChecked("png" in selected_formats)
            jpg_check.setChecked("jpg" in selected_formats)
            pdf_check.setChecked("pdf" in selected_formats)
            jpg_quality_spin.setValue(int(selected_profile.get("jpg_quality", 90)))
            pdf_dpi_spin.setValue(int(selected_profile.get("pdf_dpi", 300)))

        profile_combo.currentIndexChanged.connect(lambda _index: on_profile_changed())

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        include_png = bool(png_check.isChecked())
        include_jpg = bool(jpg_check.isChecked())
        include_pdf = bool(pdf_check.isChecked())
        if not any((include_png, include_jpg, include_pdf)):
            QMessageBox.warning(self, APP_NAME, "Select at least one format.")
            return None
        selected_profile_key = str(profile_combo.currentData() or current_profile["key"])
        return {
            "include_png": include_png,
            "include_jpg": include_jpg,
            "include_pdf": include_pdf,
            "jpg_quality": int(jpg_quality_spin.value()),
            "pdf_dpi": int(pdf_dpi_spin.value()),
            "selected_profile_key": self._normalize_batch_profile_key(selected_profile_key),
            "save_profile_name": save_profile_name_edit.text(),
        }

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

        mime_data = self._build_canvas_clipboard_mime_data()
        QGuiApplication.clipboard().setMimeData(mime_data)
        self._show_drawing_area_copied_feedback()

    def copy_drawing_area_to_clipboard(self) -> None:
        """
        Copies the full editable drawing area to clipboard for cross-tab paste.

        Returns:
            None
        """

        mime_data = self._build_canvas_clipboard_mime_data()
        QGuiApplication.clipboard().setMimeData(mime_data)
        self._show_drawing_area_copied_feedback()

    def _show_drawing_area_copied_feedback(self) -> None:
        """
        Shows canvas and status-bar feedback after copying the drawing area.

        Returns:
            None
        """

        self.canvas.flash_copy_feedback()
        document = self.canvas.document_rect()
        width = max(1, int(round(document.width())))
        height = max(1, int(round(document.height())))
        annotation_count = len(self.canvas.collect_annotations())
        annotation_label = "annotation" if annotation_count == 1 else "annotations"
        self.statusBar().showMessage(
            f"Drawing area copied ({width}×{height}, {annotation_count} {annotation_label})",
            3500,
        )

    def _build_canvas_clipboard_mime_data(self) -> QMimeData:
        """
        Builds clipboard payload containing Snappix canvas and image data.

        Returns:
            QMimeData: Clipboard object with custom and image formats.
        """

        payload = {
            "screenshot_png_base64": pixmap_to_base64_png(self.canvas.screenshot()),
            "annotations": [
                annotation.to_dict()
                for annotation in self.canvas.collect_annotations()
            ],
        }
        encoded = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        composited = self.canvas.export_composited_pixmap()
        image_bytes = QByteArray()
        buffer = QBuffer(image_bytes)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        composited.save(buffer, "PNG")
        buffer.close()

        mime_data = QMimeData()
        mime_data.setData(_CANVAS_CLIPBOARD_MIME, encoded)
        mime_data.setData("image/png", bytes(image_bytes))
        mime_data.setImageData(composited.toImage())
        return mime_data

    def paste_drawing_area_from_clipboard(self) -> bool:
        """
        Pastes a copied drawing area from another tab into this tab.

        Returns:
            bool: True when a drawing area payload was pasted.
        """

        clipboard = QGuiApplication.clipboard()
        mime_data = clipboard.mimeData()
        if mime_data is None or not mime_data.hasFormat(_CANVAS_CLIPBOARD_MIME):
            return False
        raw_data = bytes(mime_data.data(_CANVAS_CLIPBOARD_MIME))
        try:
            payload = json.loads(raw_data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        screenshot_data = payload.get("screenshot_png_base64")
        annotations_data = payload.get("annotations")
        if not isinstance(screenshot_data, str) or not isinstance(annotations_data, list):
            return False
        annotations = [
            AnnotationModel.from_dict(item)
            for item in annotations_data
            if isinstance(item, dict)
        ]
        source_screenshot = base64_png_to_pixmap(screenshot_data)
        if source_screenshot.isNull():
            return False
        if not self.canvas.merge_canvas_payload(source_screenshot, annotations):
            return False
        self._refresh_layer_panel()
        self.statusBar().showMessage(
            f"Drawing area pasted ({len(annotations)} annotations)",
            2500,
        )
        return True

    def paste_from_clipboard(self) -> None:
        """
        Pastes clipboard content, preferring Snappix drawing area payloads.

        Returns:
            None
        """

        if self.paste_drawing_area_from_clipboard():
            return
        self.canvas.paste_from_clipboard()

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
            "Capture screenshots, annotate visuals, blur sensitive data, run OCR, and export fast.",
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
            "Ctrl+S: Save project\n"
            "Ctrl+Shift+E: Export dialog\n"
            "Ctrl+P: Print dialog\n"
            "Ctrl+Shift+S: Save project as\n"
            "Ctrl+O: Open project\n"
            "Ctrl+Z: Undo\n"
            "Ctrl+Y / Ctrl+Shift+Z: Redo\n"
            "Ctrl+C: Copy drawing area and composited image\n"
            "Ctrl+Shift+C: Copy drawing area (for another tab)\n"
            "Ctrl+V: Paste text/image/image file/image URL\n"
            "Ctrl+Shift+V: Paste drawing area from another tab\n"
            "Ctrl++ / Ctrl+=: Zoom in\n"
            "Ctrl+-: Zoom out\n"
            "Ctrl+0: Reset zoom\n"
            "Shift+Mouse Wheel: Zoom on canvas\n"
            "Mouse Wheel / side wheel: Scroll canvas\n"
            "Ctrl+Shift++ / Ctrl+Shift+-: Scale selection\n"
            "Arrow keys: Nudge selected layer by 1 px\n"
            "Shift+Arrow keys: Nudge selected layer by 10 px\n"
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
            "Ctrl+S  - Save project (.sfp)\n"
            "Ctrl+Shift+E  - Open export dialog (PNG/JPG/PDF)\n"
            "Ctrl+P  - Open print dialog\n"
            "Ctrl+Shift+S  - Save project as (.sfp)\n"
            "Ctrl+O  - Open project\n"
            "Ctrl+Z  - Undo\n"
            "Ctrl+Y / Ctrl+Shift+Z  - Redo\n"
            "Ctrl+C  - Copy drawing area and composited image\n"
            "Ctrl+Shift+C  - Copy drawing area (cross-tab)\n"
            "Ctrl+V  - Paste text/image/image file/image URL\n"
            "Ctrl+Shift+V  - Paste drawing area (cross-tab)\n"
            "Ctrl++ / Ctrl+=  - Zoom in\n"
            "Ctrl+-  - Zoom out\n"
            "Ctrl+0  - Reset zoom\n"
            "Shift+Mouse Wheel  - Zoom on canvas\n"
            "Mouse Wheel / side wheel  - Scroll canvas\n"
            "Ctrl+Shift++ / Ctrl+Shift+-  - Scale selection\n"
            "Arrow keys  - Nudge selection by 1 px\n"
            "Shift+Arrow keys  - Nudge selection by 10 px\n"
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

        from src.session_recovery import ensure_tab_recovery_path

        self._recovery_path = ensure_tab_recovery_path(self._recovery_path)

        model = build_project_model(
            screenshot=self.canvas.screenshot(),
            annotation_models=self.canvas.collect_annotations(),
        )
        try:
            save_project(self._recovery_path, model)
        except OSError:
            return

        if self._current_project_path and self._current_project_path != self._recovery_path:
            try:
                save_project(self._current_project_path, model)
            except OSError:
                return

    def set_minimize_to_tray_on_close(self, enabled: bool) -> None:
        """
        Enables or disables close-to-tray behavior.

        Args:
            enabled: True to hide on close, False to close normally.

        Returns:
            None
        """

        self._minimize_to_tray_on_close = enabled

    def has_drawn_annotations(self) -> bool:
        """
        Indicates whether this tab currently contains annotations.

        Returns:
            bool: True when at least one annotation exists.
        """

        return len(self.canvas.collect_annotations()) > 0

    def confirm_close_if_needed(self) -> bool:
        """
        Requests close confirmation when this tab has drawn annotations.

        Returns:
            bool: True when tab may be closed.
        """

        if not self.has_drawn_annotations():
            return True
        answer = QMessageBox.question(
            self,
            "Close Tab",
            "This tab contains annotations. Close it anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

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
        if not self.confirm_close_if_needed():
            event.ignore()
            return
        super().closeEvent(event)

