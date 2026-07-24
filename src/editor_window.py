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
    QSize,
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
    QPainter,
    QPageLayout,
    QPageSize,
    QPen,
    QPolygonF,
    QPdfWriter,
    QPixmap,
    QTextCursor,
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
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from src.constants import (
    APP_FILE_EXTENSION,
    APP_NAME,
    build_about_dialog_html,
)
from src.flow_layout import FlowLayoutWidget
from src.config import (
    EXPORT_PRESET_DOCS,
    EXPORT_PRESET_LIGHTWEIGHT,
    EXPORT_PRESET_PRINT,
    EXPORT_PRESET_WEB,
    BRUSH_WIDTH_TOOLS,
    HARDNESS_AWARE_TOOLS,
    STYLE_AWARE_TOOLS,
    WIDTH_AWARE_TOOLS,
    normalize_brush_hardness,
    normalize_export_preset,
    normalize_named_stroke_style,
    normalize_stroke_width,
    normalize_tool_brush_hardness,
    normalize_tool_stroke_styles,
    normalize_tool_stroke_widths,
)
from src.annotation_items import (
    STROKE_STYLE_DASH,
    STROKE_STYLE_DASH_DOT,
    STROKE_STYLE_DOT,
    STROKE_STYLE_SOLID,
)
from src.annotation_shapes import TEXT_STYLE_BOX, TEXT_STYLE_BUBBLE, TEXT_STYLE_PLAIN
from src.editor_canvas import (
    ERASE_MODE_FILL,
    ERASE_MODE_TRANSPARENT,
    EditorCanvas,
    Tool,
)
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
    THEME_SEPIA,
    THEME_SLATE,
    color_preview_button_stylesheet,
    get_editor_accent_colors,
    get_theme_colors,
    normalize_theme_name,
    palette_button_stylesheet,
)
from src.ocr import format_ocr_copied_status
from src.shortcuts import (
    HOST_OWNED_SHORTCUT_IDS,
    build_shortcuts_reference_text,
    format_shortcut_for_display,
    normalize_editor_shortcuts,
    resolved_shortcut_text,
    sequences_for_action,
)
from src.tool_reference import format_tool_tooltip
from src.tool_reference_dialog import ToolReferenceDialog


_SELECTION_TYPE_LABELS: dict[str, str] = {
    "rect": "Rectangle",
    "ellipse": "Ellipse",
    "triangle": "Triangle",
    "round_rect": "Rounded Rectangle",
    "star": "Star",
    "highlight": "Highlight",
    "spotlight": "Spotlight",
    "cross": "Cross",
    "checkmark": "Checkmark",
    "line": "Line",
    "arrow": "Arrow",
    "double_arrow": "Double Arrow",
    "polyline": "Polyline",
    "polygon": "Polygon",
    "bent_arrow": "Bent Arrow",
    "callout": "Callout",
    "text": "Text",
    "image": "Image",
    "step": "Step",
    "document": "Document",
}

_STROKE_STYLE_LABELS: dict[str, str] = {
    STROKE_STYLE_SOLID: "Solid",
    STROKE_STYLE_DASH: "Dashed",
    STROKE_STYLE_DOT: "Dotted",
    STROKE_STYLE_DASH_DOT: "Dash-dot",
}
_CANVAS_CLIPBOARD_MIME = "application/x-snappix-canvas"
_ANNOTATIONS_CLIPBOARD_MIME = "application/x-snappix-annotations"

# Style-tab color targets available for annotation types / drawing tools.
_COLOR_TARGETS_STROKE_FILL = frozenset({"stroke", "fill"})
_COLOR_TARGETS_STROKE = frozenset({"stroke"})
_COLOR_TARGETS_FILL = frozenset({"fill"})
_COLOR_TARGETS_TEXT = frozenset({"text", "stroke", "fill"})
_COLOR_TARGETS_BY_SELECTION: dict[str, frozenset[str]] = {
    "rect": _COLOR_TARGETS_STROKE_FILL,
    "ellipse": _COLOR_TARGETS_STROKE_FILL,
    "triangle": _COLOR_TARGETS_STROKE_FILL,
    "round_rect": _COLOR_TARGETS_STROKE_FILL,
    "star": _COLOR_TARGETS_STROKE_FILL,
    "highlight": _COLOR_TARGETS_STROKE_FILL,
    "polygon": _COLOR_TARGETS_STROKE_FILL,
    "spotlight": _COLOR_TARGETS_STROKE_FILL,
    "cross": _COLOR_TARGETS_STROKE_FILL,
    "checkmark": _COLOR_TARGETS_STROKE_FILL,
    "step": _COLOR_TARGETS_STROKE_FILL,
    "line": _COLOR_TARGETS_STROKE,
    "arrow": _COLOR_TARGETS_STROKE,
    "double_arrow": _COLOR_TARGETS_STROKE,
    "polyline": _COLOR_TARGETS_STROKE,
    "bent_arrow": _COLOR_TARGETS_STROKE,
    "text": _COLOR_TARGETS_TEXT,
    "callout": _COLOR_TARGETS_TEXT,
}
_COLOR_TARGETS_BY_TOOL: dict[str, frozenset[str]] = {
    Tool.RECT: _COLOR_TARGETS_STROKE_FILL,
    Tool.ELLIPSE: _COLOR_TARGETS_STROKE_FILL,
    Tool.TRIANGLE: _COLOR_TARGETS_STROKE_FILL,
    Tool.STAR: _COLOR_TARGETS_STROKE_FILL,
    Tool.POLYGON: _COLOR_TARGETS_STROKE_FILL,
    Tool.SPOTLIGHT: _COLOR_TARGETS_STROKE_FILL,
    Tool.CROSS: _COLOR_TARGETS_STROKE_FILL,
    Tool.CHECKMARK: _COLOR_TARGETS_STROKE_FILL,
    Tool.STEP: _COLOR_TARGETS_STROKE_FILL,
    Tool.LINE: _COLOR_TARGETS_STROKE,
    Tool.POLYLINE: _COLOR_TARGETS_STROKE,
    Tool.ARROW: _COLOR_TARGETS_STROKE,
    Tool.DOUBLE_ARROW: _COLOR_TARGETS_STROKE,
    Tool.BENT_ARROW: _COLOR_TARGETS_STROKE,
    Tool.BRUSH: _COLOR_TARGETS_STROKE,
    Tool.BUCKET: _COLOR_TARGETS_FILL,
    Tool.FILL_BG: _COLOR_TARGETS_FILL,
    Tool.EYEDROPPER: _COLOR_TARGETS_STROKE_FILL,
    Tool.TEXT: _COLOR_TARGETS_TEXT,
    Tool.CALLOUT: _COLOR_TARGETS_TEXT,
}
# Tools that edit existing content: Style colors follow the selection, not the tool.
_COLOR_SELECTION_CONTEXT_TOOLS = frozenset(
    {
        Tool.SELECT,
        Tool.SELECT_RECT,
        Tool.SELECT_ELLIPSE,
        Tool.SELECT_PATH,
        Tool.MAGIC_WAND,
        Tool.CROP,
        Tool.OCR,
        Tool.BLUR,
        Tool.ERASER,
    }
)


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
    Formats selected annotation or document details for the editor status bar.

    Args:
        payload: Selection detail payload from the canvas.

    Returns:
        str: Human-readable selection summary.
    """

    annotation_type = str(payload.get("type") or "").strip()
    if not annotation_type:
        return ""

    if annotation_type == "document":
        return _format_document_info(payload)

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
    if isinstance(stroke_width, (int, float)) and stroke_width >= 0:
        width_value = int(stroke_width) if float(stroke_width).is_integer() else round(float(stroke_width), 1)
        if float(width_value) <= 0:
            parts.append("No border")
        else:
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


def _format_document_info(payload: dict[str, Any]) -> str:
    """
    Formats document/canvas details for the editor status bar.

    Args:
        payload: Document detail payload from the canvas.

    Returns:
        str: Human-readable document summary.
    """

    parts: list[str] = ["Document"]
    width = payload.get("width")
    height = payload.get("height")
    if isinstance(width, (int, float)) and isinstance(height, (int, float)):
        parts.append(f"{width:g}×{height:g} px")

    pixel_width = payload.get("pixel_width")
    pixel_height = payload.get("pixel_height")
    dpr = payload.get("dpr")
    if (
        isinstance(pixel_width, int)
        and isinstance(pixel_height, int)
        and isinstance(dpr, (int, float))
        and float(dpr) > 1.01
        and isinstance(width, (int, float))
        and isinstance(height, (int, float))
        and (abs(pixel_width - width) > 0.5 or abs(pixel_height - height) > 0.5)
    ):
        parts.append(f"Raster {pixel_width}×{pixel_height}")

    zoom = payload.get("zoom")
    if isinstance(zoom, (int, float)):
        parts.append(f"Zoom {int(round(float(zoom)))}%")

    annotation_count = payload.get("annotation_count")
    if isinstance(annotation_count, int):
        if annotation_count == 1:
            parts.append("1 annotation")
        else:
            parts.append(f"{annotation_count} annotations")

    if payload.get("blank") is True:
        parts.append("Blank canvas")

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
    new_tab_requested = Signal()
    export_preset_changed = Signal(str)
    export_scale_changed = Signal(float)
    export_keep_transparency_changed = Signal(bool)
    tool_stroke_widths_changed = Signal(object)
    tool_brush_hardness_changed = Signal(object)
    tool_stroke_styles_changed = Signal(object)

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
        self._color_target_widgets: dict[str, list[QWidget]] = {
            "stroke": [],
            "fill": [],
            "text": [],
        }
        self._color_group_gaps: dict[str, QWidget] = {}
        self._active_tool = Tool.SELECT
        self._locked_tool: str | None = None
        self._one_shot_tool: str | None = None
        self._tool_button_order: list[str] = []
        self._tool_button_labels: dict[str, str] = {}
        self._tool_button_to_key: dict[QToolButton, str] = {}
        self._current_stroke_color = QColor(231, 76, 60, 255)
        self._current_fill_color = QColor(231, 76, 60, 80)
        self._current_text_color = QColor(44, 62, 80, 255)
        self._eyedropper_color_target = "stroke"
        self._export_scale = 1.0
        self._export_keep_transparency = True
        self._text_bold_enabled = False
        self._text_italic_enabled = False
        self._text_underline_enabled = False
        self._text_letter_spacing = 0.0
        self._text_line_spacing = 1.2
        self._text_box_padding = 10.0
        self._text_corner_radius = 6.0
        self._rect_corner_radius = 0.0
        self._shortcut_actions: dict[str, QAction] = {}
        self._editor_shortcut_overrides: dict[str, str] = {}
        self._tool_stroke_widths: dict[str, int] = normalize_tool_stroke_widths(None)
        self._tool_brush_hardness: dict[str, int] = normalize_tool_brush_hardness(None)
        self._tool_stroke_styles: dict[str, str] = normalize_tool_stroke_styles(None)
        self._tool_width_sliders: dict[str, QSlider] = {}
        self._tool_width_labels: dict[str, QLabel] = {}
        self._tool_hardness_sliders: dict[str, QSlider] = {}
        self._tool_hardness_labels: dict[str, QLabel] = {}
        self._tool_style_combos: dict[str, QComboBox] = {}
        self._tool_radius_spins: dict[str, QDoubleSpinBox] = {}

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
        self.canvas.status_message.connect(self._on_canvas_status_message)

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
        self._autosave_flushing = False
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

        strip = FlowLayoutWidget(
            bar,
            horizontal_spacing=6,
            vertical_spacing=4,
            margin=2,
        )
        strip.setObjectName("editorToolStrip")
        strip_widgets: list[QWidget] = []

        self._tool_buttons: dict[str, QToolButton] = {}
        tool_categories: list[tuple[str, list[tuple[str, str]]]] = [
            (
                "Select",
                [
                    (Tool.SELECT, "Select"),
                    (Tool.SELECT_RECT, "Sel Rect"),
                    (Tool.SELECT_ELLIPSE, "Sel Ellipse"),
                    (Tool.SELECT_PATH, "Lasso"),
                    (Tool.MAGIC_WAND, "Magic Wand"),
                ],
            ),
            (
                "Paint",
                [
                    (Tool.BRUSH, "Brush"),
                    (Tool.ERASER, "Eraser"),
                    (Tool.BUCKET, "Fill"),
                    (Tool.EYEDROPPER, "Color Picker"),
                ],
            ),
            (
                "Shapes",
                [
                    (Tool.RECT, "Rectangle"),
                    (Tool.ELLIPSE, "Circle"),
                    (Tool.TRIANGLE, "Triangle"),
                    (Tool.STAR, "Star"),
                    (Tool.POLYGON, "Polygon"),
                ],
            ),
            (
                "Lines",
                [
                    (Tool.LINE, "Line"),
                    (Tool.POLYLINE, "Polyline"),
                    (Tool.ARROW, "Arrow"),
                    (Tool.DOUBLE_ARROW, "Double Arrow"),
                    (Tool.BENT_ARROW, "Bent Arrow"),
                ],
            ),
            (
                "Marks",
                [
                    (Tool.CROSS, "Cross"),
                    (Tool.CHECKMARK, "Checkmark"),
                    (Tool.SPOTLIGHT, "Spotlight"),
                    (Tool.STEP, "Step"),
                ],
            ),
            (
                "Text",
                [
                    (Tool.TEXT, "Text"),
                    (Tool.CALLOUT, "Callout"),
                ],
            ),
            (
                "Image",
                [
                    (Tool.FILL_BG, "Bg Fill"),
                    (Tool.BLUR, "Blur"),
                    (Tool.OCR, "OCR"),
                    (Tool.CROP, "Crop"),
                ],
            ),
        ]
        for category_title, tools in tool_categories:
            category_box = QGroupBox(category_title, strip)
            category_box.setObjectName("toolCategoryBox")
            category_box.setSizePolicy(
                QSizePolicy.Policy.Maximum,
                QSizePolicy.Policy.Maximum,
            )
            category_layout = QHBoxLayout(category_box)
            category_layout.setContentsMargins(4, 10, 4, 4)
            category_layout.setSpacing(4)
            for tool_key, label in tools:
                button = QToolButton()
                button.setText(label)
                button.setCheckable(True)
                button.setIcon(self._build_tool_icon(tool_key))
                button.setIconSize(QSize(28, 28))
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                button.setFixedSize(38, 34)
                button.setToolTip(label)
                self._configure_compact_toolbar_height(button, 34)
                button.clicked.connect(
                    lambda _checked=False, t=tool_key: self._on_tool_button_clicked(t)
                )
                button.installEventFilter(self)
                self._tool_buttons[tool_key] = button
                self._tool_button_order.append(tool_key)
                self._tool_button_labels[tool_key] = label
                self._tool_button_to_key[button] = tool_key
                category_layout.addWidget(button)
            strip_widgets.append(category_box)

        self._tool_buttons[Tool.SELECT].setChecked(True)
        self._setup_pixel_tool_option_menus()
        self._setup_stroke_width_tool_menus()
        self._setup_text_tool_option_menu()

        help_box = QGroupBox("Help", strip)
        help_box.setObjectName("toolCategoryBox")
        help_box.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        help_layout = QHBoxLayout(help_box)
        help_layout.setContentsMargins(4, 10, 4, 4)
        help_layout.setSpacing(4)
        self.tools_help_button = QToolButton()
        self.tools_help_button.setText("?")
        self.tools_help_button.setToolTip("Open the tools reference table.")
        self.tools_help_button.setFixedSize(38, 34)
        self._configure_compact_toolbar_height(self.tools_help_button, 34)
        self.tools_help_button.clicked.connect(self.show_tools_reference)
        help_layout.addWidget(self.tools_help_button)
        strip_widgets.append(help_box)

        history_box = QGroupBox("History", strip)
        history_box.setObjectName("toolCategoryBox")
        history_box.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        history_layout = QHBoxLayout(history_box)
        history_layout.setContentsMargins(4, 10, 4, 4)
        history_layout.setSpacing(4)
        self.history_undo_button = QPushButton("Undo")
        self.history_undo_button.clicked.connect(self.undo)
        self._configure_compact_toolbar_height(self.history_undo_button)
        history_layout.addWidget(self.history_undo_button)
        self.history_redo_button = QPushButton("Redo")
        self.history_redo_button.clicked.connect(self.redo)
        self._configure_compact_toolbar_height(self.history_redo_button)
        history_layout.addWidget(self.history_redo_button)
        self.history_list_combo = QComboBox()
        self.history_list_combo.setMinimumWidth(160)
        self.history_list_combo.setMaxVisibleItems(16)
        self.history_list_combo.currentIndexChanged.connect(self._on_history_entry_selected)
        self._configure_compact_toolbar_height(self.history_list_combo)
        history_layout.addWidget(self.history_list_combo)
        self.history_status_label = QLabel("1/1")
        self._configure_compact_toolbar_height(self.history_status_label, 22)
        history_layout.addWidget(self.history_status_label)
        strip_widgets.append(history_box)

        zoom_box = QGroupBox("Zoom", strip)
        zoom_box.setObjectName("toolCategoryBox")
        zoom_box.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        zoom_layout = QHBoxLayout(zoom_box)
        zoom_layout.setContentsMargins(4, 10, 4, 4)
        zoom_layout.setSpacing(4)
        self.zoom_out_button = QPushButton("-")
        self.zoom_out_button.clicked.connect(self.canvas.zoom_out)
        self._configure_compact_action_button(self.zoom_out_button)
        self._configure_compact_toolbar_height(self.zoom_out_button)
        zoom_layout.addWidget(self.zoom_out_button)

        self.zoom_label = QLabel("100%")
        self.zoom_label.setMinimumWidth(42)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._configure_compact_toolbar_height(self.zoom_label, 22)
        zoom_layout.addWidget(self.zoom_label)

        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(10, 400)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(100)
        self.zoom_slider.setToolTip("Zoom: left smaller, right larger")
        self.zoom_slider.valueChanged.connect(self._zoom_slider_changed)
        self._configure_compact_toolbar_height(self.zoom_slider, 22)
        zoom_layout.addWidget(self.zoom_slider)

        self.zoom_in_button = QPushButton("+")
        self.zoom_in_button.clicked.connect(self.canvas.zoom_in)
        self._configure_compact_action_button(self.zoom_in_button)
        self._configure_compact_toolbar_height(self.zoom_in_button)
        zoom_layout.addWidget(self.zoom_in_button)

        self.zoom_reset_button = QPushButton("Reset")
        self.zoom_reset_button.clicked.connect(self.canvas.reset_zoom)
        self._configure_compact_action_button(self.zoom_reset_button)
        self._configure_compact_toolbar_height(self.zoom_reset_button)
        zoom_layout.addWidget(self.zoom_reset_button)
        strip_widgets.append(zoom_box)

        strip.set_flow_widgets(strip_widgets)
        root_layout.addWidget(strip)

        self._property_tabs = QTabWidget(bar)
        self._property_tabs.setObjectName("editorPropertyTabs")
        self._property_tabs.setDocumentMode(True)
        self._property_tabs.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        self._fitting_property_tabs = False
        self._PROPERTY_TAB_STYLE = 0
        self._PROPERTY_TAB_ARRANGE = 1
        self._PROPERTY_TAB_EXPORT = 2

        style_tab = FlowLayoutWidget(
            self._property_tabs,
            horizontal_spacing=3,
            vertical_spacing=2,
            margin=2,
        )
        style_widgets: list[QWidget] = []
        stroke_widgets: list[QWidget] = []
        fill_widgets: list[QWidget] = []
        text_widgets: list[QWidget] = []

        self.stroke_button = QPushButton("Border")
        self.stroke_button.setFixedWidth(64)
        self.stroke_button.clicked.connect(self._choose_stroke_color)
        self._configure_compact_toolbar_height(self.stroke_button)
        stroke_widgets.append(self.stroke_button)
        stroke_widgets.append(self._create_palette_row(palette_colors, "stroke"))
        self.stroke_alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.stroke_alpha_slider.setRange(0, 100)
        self.stroke_alpha_slider.setValue(100)
        self.stroke_alpha_slider.setFixedWidth(56)
        self.stroke_alpha_slider.setToolTip("Border opacity")
        self.stroke_alpha_slider.valueChanged.connect(self._stroke_alpha_changed)
        self.stroke_alpha_slider.sliderReleased.connect(self._stroke_alpha_committed)
        self._configure_compact_toolbar_height(self.stroke_alpha_slider, 22)
        stroke_widgets.append(self.stroke_alpha_slider)
        self.stroke_alpha_label = QLabel("100%")
        self._configure_compact_toolbar_height(self.stroke_alpha_label, 22)
        stroke_widgets.append(self.stroke_alpha_label)
        style_widgets.extend(stroke_widgets)

        fill_gap = self._create_toolbar_gap(6)
        self._color_group_gaps["fill"] = fill_gap
        style_widgets.append(fill_gap)
        self.fill_button = QPushButton("Fill")
        self.fill_button.setFixedWidth(52)
        self.fill_button.clicked.connect(self._choose_fill_color)
        self._configure_compact_toolbar_height(self.fill_button)
        fill_widgets.append(self.fill_button)
        fill_widgets.append(self._create_palette_row(palette_colors, "fill"))
        self.fill_alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.fill_alpha_slider.setRange(0, 100)
        self.fill_alpha_slider.setValue(31)
        self.fill_alpha_slider.setFixedWidth(56)
        self.fill_alpha_slider.setToolTip("Fill opacity")
        self.fill_alpha_slider.valueChanged.connect(self._fill_alpha_changed)
        self._configure_compact_toolbar_height(self.fill_alpha_slider, 22)
        fill_widgets.append(self.fill_alpha_slider)
        self.fill_alpha_label = QLabel("31%")
        self._configure_compact_toolbar_height(self.fill_alpha_label, 22)
        fill_widgets.append(self.fill_alpha_label)
        style_widgets.extend(fill_widgets)

        text_gap = self._create_toolbar_gap(6)
        self._color_group_gaps["text"] = text_gap
        style_widgets.append(text_gap)
        self.text_color_button = QPushButton("Text")
        self.text_color_button.setFixedWidth(52)
        self.text_color_button.clicked.connect(self._choose_text_color)
        self._configure_compact_toolbar_height(self.text_color_button)
        text_widgets.append(self.text_color_button)
        text_widgets.append(self._create_palette_row(palette_colors, "text"))
        self.text_alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.text_alpha_slider.setRange(0, 100)
        self.text_alpha_slider.setValue(100)
        self.text_alpha_slider.setFixedWidth(56)
        self.text_alpha_slider.setToolTip("Text opacity")
        self.text_alpha_slider.valueChanged.connect(self._text_alpha_changed)
        self._configure_compact_toolbar_height(self.text_alpha_slider, 22)
        text_widgets.append(self.text_alpha_slider)
        self.text_alpha_label = QLabel("100%")
        self._configure_compact_toolbar_height(self.text_alpha_label, 22)
        text_widgets.append(self.text_alpha_label)
        style_widgets.extend(text_widgets)

        self._color_target_widgets = {
            "stroke": stroke_widgets,
            "fill": fill_widgets,
            "text": text_widgets,
        }
        style_tab.set_flow_widgets(style_widgets)
        self._property_tabs.addTab(style_tab, "Style")

        arrange_tab = FlowLayoutWidget(
            self._property_tabs,
            horizontal_spacing=3,
            vertical_spacing=2,
            margin=2,
        )
        arrange_widgets: list[QWidget] = []
        self.snap_to_grid_button = QToolButton()
        self.snap_to_grid_button.setText("Snap")
        self.snap_to_grid_button.setCheckable(True)
        self.snap_to_grid_button.clicked.connect(self._snap_toggled)
        self._configure_compact_toolbar_height(self.snap_to_grid_button)
        arrange_widgets.append(self.snap_to_grid_button)
        self.grid_visible_button = QToolButton()
        self.grid_visible_button.setText("Grid")
        self.grid_visible_button.setCheckable(True)
        self.grid_visible_button.clicked.connect(self._grid_toggled)
        self._configure_compact_toolbar_height(self.grid_visible_button)
        arrange_widgets.append(self.grid_visible_button)
        arrange_widgets.append(self._create_toolbar_label("Size"))
        self.grid_size_combo = QComboBox()
        self.grid_size_combo.addItems(["8", "12", "16", "20", "24", "32", "40", "48"])
        self.grid_size_combo.setCurrentText("16")
        self.grid_size_combo.currentTextChanged.connect(self._grid_size_changed)
        self._configure_compact_combo(self.grid_size_combo, 52)
        self._configure_compact_toolbar_height(self.grid_size_combo)
        arrange_widgets.append(self.grid_size_combo)
        arrange_widgets.append(self._create_toolbar_gap(6))
        arrange_widgets.append(self._create_toolbar_label("Layer"))
        self.layer_combo = QComboBox()
        self.layer_combo.setMinimumWidth(150)
        self.layer_combo.currentIndexChanged.connect(self._on_layer_combo_changed)
        self._configure_compact_toolbar_height(self.layer_combo)
        arrange_widgets.append(self.layer_combo)
        self.layer_visible_check = QCheckBox("Visible")
        self.layer_visible_check.toggled.connect(self._toggle_selected_layer_visibility)
        self._configure_compact_toolbar_height(self.layer_visible_check, 22)
        arrange_widgets.append(self.layer_visible_check)
        self.layer_lock_check = QCheckBox("Lock")
        self.layer_lock_check.toggled.connect(self._toggle_selected_layer_lock)
        self._configure_compact_toolbar_height(self.layer_lock_check, 22)
        arrange_widgets.append(self.layer_lock_check)
        self.layer_up_button = QPushButton("Up")
        self.layer_up_button.clicked.connect(self._move_selected_layer_up)
        self._configure_compact_toolbar_height(self.layer_up_button)
        arrange_widgets.append(self.layer_up_button)
        self.layer_down_button = QPushButton("Down")
        self.layer_down_button.clicked.connect(self._move_selected_layer_down)
        self._configure_compact_toolbar_height(self.layer_down_button)
        arrange_widgets.append(self.layer_down_button)
        arrange_widgets.append(self._create_toolbar_gap(6))
        arrange_widgets.append(self._create_toolbar_label("X"))
        self.geometry_x_spin = QSpinBox()
        self.geometry_x_spin.setRange(-10000, 100000)
        self._configure_compact_combo(self.geometry_x_spin, 64)
        arrange_widgets.append(self.geometry_x_spin)
        arrange_widgets.append(self._create_toolbar_label("Y"))
        self.geometry_y_spin = QSpinBox()
        self.geometry_y_spin.setRange(-10000, 100000)
        self._configure_compact_combo(self.geometry_y_spin, 64)
        arrange_widgets.append(self.geometry_y_spin)
        arrange_widgets.append(self._create_toolbar_label("W"))
        self.geometry_w_spin = QSpinBox()
        self.geometry_w_spin.setRange(2, 100000)
        self._configure_compact_combo(self.geometry_w_spin, 64)
        arrange_widgets.append(self.geometry_w_spin)
        arrange_widgets.append(self._create_toolbar_label("H"))
        self.geometry_h_spin = QSpinBox()
        self.geometry_h_spin.setRange(2, 100000)
        self._configure_compact_combo(self.geometry_h_spin, 64)
        arrange_widgets.append(self.geometry_h_spin)
        self.geometry_apply_button = QPushButton("Apply")
        self.geometry_apply_button.clicked.connect(self._apply_selected_geometry)
        self._configure_compact_toolbar_height(self.geometry_apply_button)
        arrange_widgets.append(self.geometry_apply_button)
        arrange_widgets.append(self._create_toolbar_gap(6))
        arrange_widgets.append(self._create_toolbar_label("Align"))
        for mode, label in (
            ("left", "L"),
            ("center_h", "C"),
            ("right", "R"),
            ("top", "T"),
            ("middle_v", "M"),
            ("bottom", "B"),
        ):
            button = QPushButton(label)
            button.setFixedWidth(28)
            button.setToolTip(f"Align selection {mode.replace('_', ' ')}")
            button.clicked.connect(
                lambda _checked=False, align_mode=mode: self._align_selection(align_mode)
            )
            self._configure_compact_toolbar_height(button)
            arrange_widgets.append(button)
        arrange_widgets.append(self._create_toolbar_label("Dist"))
        self.distribute_h_button = QPushButton("H")
        self.distribute_h_button.setFixedWidth(28)
        self.distribute_h_button.setToolTip("Distribute selection horizontally (3+ items)")
        self.distribute_h_button.clicked.connect(
            lambda: self._distribute_selection("horizontal")
        )
        self._configure_compact_toolbar_height(self.distribute_h_button)
        arrange_widgets.append(self.distribute_h_button)
        self.distribute_v_button = QPushButton("V")
        self.distribute_v_button.setFixedWidth(28)
        self.distribute_v_button.setToolTip("Distribute selection vertically (3+ items)")
        self.distribute_v_button.clicked.connect(
            lambda: self._distribute_selection("vertical")
        )
        self._configure_compact_toolbar_height(self.distribute_v_button)
        arrange_widgets.append(self.distribute_v_button)
        arrange_widgets.append(self._create_toolbar_gap(6))
        arrange_widgets.append(self._create_toolbar_label("Rotate"))
        self.rotate_ccw_button = QPushButton("-15°")
        self.rotate_ccw_button.clicked.connect(lambda: self._rotate_selection(-15.0))
        self._configure_compact_toolbar_height(self.rotate_ccw_button)
        arrange_widgets.append(self.rotate_ccw_button)
        self.rotate_cw_button = QPushButton("+15°")
        self.rotate_cw_button.clicked.connect(lambda: self._rotate_selection(15.0))
        self._configure_compact_toolbar_height(self.rotate_cw_button)
        arrange_widgets.append(self.rotate_cw_button)
        self.rotation_spin = QDoubleSpinBox()
        self.rotation_spin.setRange(-360.0, 360.0)
        self.rotation_spin.setDecimals(1)
        self.rotation_spin.setSuffix("°")
        self.rotation_spin.setFixedWidth(78)
        self._configure_compact_toolbar_height(self.rotation_spin)
        arrange_widgets.append(self.rotation_spin)
        self.rotation_apply_button = QPushButton("Set°")
        self.rotation_apply_button.clicked.connect(self._apply_rotation_spin)
        self._configure_compact_toolbar_height(self.rotation_apply_button)
        arrange_widgets.append(self.rotation_apply_button)
        self.flip_h_button = QPushButton("Flip H")
        self.flip_h_button.clicked.connect(lambda: self._flip_selection(horizontal=True))
        self._configure_compact_toolbar_height(self.flip_h_button)
        arrange_widgets.append(self.flip_h_button)
        self.flip_v_button = QPushButton("Flip V")
        self.flip_v_button.clicked.connect(lambda: self._flip_selection(vertical=True))
        self._configure_compact_toolbar_height(self.flip_v_button)
        arrange_widgets.append(self.flip_v_button)
        arrange_widgets.append(self._create_toolbar_label("Skew"))
        self.skew_x_spin = QDoubleSpinBox()
        self.skew_x_spin.setRange(-60.0, 60.0)
        self.skew_x_spin.setDecimals(1)
        self.skew_x_spin.setPrefix("X ")
        self.skew_x_spin.setSuffix("°")
        self.skew_x_spin.setFixedWidth(82)
        self._configure_compact_toolbar_height(self.skew_x_spin)
        arrange_widgets.append(self.skew_x_spin)
        self.skew_y_spin = QDoubleSpinBox()
        self.skew_y_spin.setRange(-60.0, 60.0)
        self.skew_y_spin.setDecimals(1)
        self.skew_y_spin.setPrefix("Y ")
        self.skew_y_spin.setSuffix("°")
        self.skew_y_spin.setFixedWidth(82)
        self._configure_compact_toolbar_height(self.skew_y_spin)
        arrange_widgets.append(self.skew_y_spin)
        self.skew_apply_button = QPushButton("Skew")
        self.skew_apply_button.clicked.connect(self._apply_skew_spins)
        self._configure_compact_toolbar_height(self.skew_apply_button)
        arrange_widgets.append(self.skew_apply_button)
        arrange_tab.set_flow_widgets(arrange_widgets)
        self._property_tabs.addTab(arrange_tab, "Arrange")

        export_tab = FlowLayoutWidget(
            self._property_tabs,
            horizontal_spacing=3,
            vertical_spacing=2,
            margin=2,
        )
        export_widgets: list[QWidget] = []
        export_widgets.append(self._create_toolbar_label("Preset"))
        self.export_preset_combo = QComboBox()
        for preset_key, preset_values in self._export_presets.items():
            self.export_preset_combo.addItem(preset_values[0], preset_key)
        self.export_preset_combo.currentIndexChanged.connect(self._on_export_preset_index_changed)
        self._configure_compact_combo(self.export_preset_combo, 110)
        export_widgets.append(self.export_preset_combo)
        export_widgets.append(self._create_toolbar_label("Scale"))
        self.export_scale_combo = QComboBox()
        self.export_scale_combo.addItem("@1x", 1.0)
        self.export_scale_combo.addItem("@2x", 2.0)
        self.export_scale_combo.addItem("@3x", 3.0)
        self.export_scale_combo.setCurrentIndex(0)
        self.export_scale_combo.currentIndexChanged.connect(self._on_export_scale_changed)
        self._configure_compact_combo(self.export_scale_combo, 64)
        export_widgets.append(self.export_scale_combo)
        self.export_keep_transparency_check = QCheckBox("Keep transparency")
        self.export_keep_transparency_check.setChecked(True)
        self.export_keep_transparency_check.setToolTip(
            "When unchecked, transparent pixels are filled with white (needed for JPEG)."
        )
        self.export_keep_transparency_check.toggled.connect(
            self._on_export_keep_transparency_toggled
        )
        self._configure_compact_toolbar_height(self.export_keep_transparency_check, 22)
        export_widgets.append(self.export_keep_transparency_check)
        export_widgets.append(self._create_toolbar_label("Batch"))
        self.batch_profile_combo = QComboBox()
        self.batch_profile_combo.currentIndexChanged.connect(
            self._on_batch_profile_index_changed
        )
        self._configure_compact_combo(self.batch_profile_combo, 130)
        export_widgets.append(self.batch_profile_combo)
        self.manage_batch_profiles_button = QPushButton("Manage")
        self.manage_batch_profiles_button.clicked.connect(self.manage_batch_profiles)
        self._configure_compact_toolbar_height(self.manage_batch_profiles_button)
        export_widgets.append(self.manage_batch_profiles_button)
        self.export_batch_button = QPushButton("Batch Export")
        self.export_batch_button.clicked.connect(self.export_batch_with_dialog)
        self._configure_compact_toolbar_height(self.export_batch_button)
        export_widgets.append(self.export_batch_button)
        export_tab.set_flow_widgets(export_widgets)
        self._property_tabs.addTab(export_tab, "Export")
        self._property_tabs.installEventFilter(self)
        self._fit_property_tabs_height()

        root_layout.addWidget(self._property_tabs)
        self._update_color_button_preview(self.stroke_button, QColor("#e74c3c"))
        self._update_color_button_preview(self.fill_button, QColor(231, 76, 60, 80))
        self._update_color_button_preview(self.text_color_button, QColor("#2c3e50"))
        self._apply_toolbar_tooltips()
        self._update_style_color_visibility()
        return bar

    def _resolve_style_color_targets(
        self,
        *,
        tool: str | None = None,
        selection_type: str | None = None,
    ) -> frozenset[str]:
        """
        Resolves which Style color groups apply to the current context.

        Selection wins while an annotation is selected in Select mode; otherwise
        the active drawing tool decides. Empty means hide all color controls.

        Args:
            tool: Optional tool override; defaults to the active tool.
            selection_type: Optional selection type override.

        Returns:
            frozenset[str]: Target keys among ``stroke``, ``fill``, and ``text``.
        """

        resolved_tool = str(tool or self._active_tool)
        resolved_type = str(selection_type or "").strip().lower()
        if resolved_type == "document":
            return frozenset()
        use_selection_context = (
            resolved_tool in _COLOR_SELECTION_CONTEXT_TOOLS
            or resolved_tool not in _COLOR_TARGETS_BY_TOOL
        )
        if use_selection_context:
            if not resolved_type:
                payload = self._primary_selection_payload()
                if payload is not None:
                    resolved_type = str(payload.get("type") or "").strip().lower()
            if resolved_type and resolved_type != "document":
                return _COLOR_TARGETS_BY_SELECTION.get(resolved_type, frozenset())
            return frozenset()
        return _COLOR_TARGETS_BY_TOOL.get(resolved_tool, frozenset())

    def _update_style_color_visibility(
        self,
        *,
        tool: str | None = None,
        selection_type: str | None = None,
    ) -> None:
        """
        Shows only the Style color groups relevant to tool or selection.

        Args:
            tool: Optional tool override.
            selection_type: Optional selection type override.

        Returns:
            None
        """

        if not hasattr(self, "_property_tabs"):
            return
        targets = self._resolve_style_color_targets(
            tool=tool,
            selection_type=selection_type,
        )
        for target_name, widgets in self._color_target_widgets.items():
            visible = target_name in targets
            for widget in widgets:
                widget.setVisible(visible)

        ordered = [name for name in ("stroke", "fill", "text") if name in targets]
        for gap_name, gap in self._color_group_gaps.items():
            # Show the leading gap only when a previous group is also visible.
            if gap_name not in targets:
                gap.setVisible(False)
                continue
            index = ordered.index(gap_name) if gap_name in ordered else -1
            gap.setVisible(index > 0)

        style_visible = bool(targets)
        self._property_tabs.setTabVisible(self._PROPERTY_TAB_STYLE, style_visible)
        if style_visible:
            self._fit_property_tabs_height()
        elif self._property_tabs.currentIndex() == self._PROPERTY_TAB_STYLE:
            self._property_tabs.setCurrentIndex(self._PROPERTY_TAB_ARRANGE)
            self._fit_property_tabs_height()
        else:
            self._fit_property_tabs_height()

    def _create_toolbar_gap(self, width: int = 6) -> QWidget:
        """
        Creates a fixed-width spacer used between groups in flow toolbars.

        Args:
            width: Spacer width in pixels.

        Returns:
            QWidget: Invisible fixed-width gap widget.
        """

        gap = QWidget()
        gap.setFixedWidth(max(1, int(width)))
        gap.setFixedHeight(1)
        return gap

    def _fit_property_tabs_height(self) -> None:
        """
        Constrains property tabs to the height required by tab bar and content.

        Returns:
            None
        """

        if not hasattr(self, "_property_tabs"):
            return
        if self._fitting_property_tabs:
            return
        self._fitting_property_tabs = True
        try:
            tab_bar_height = max(18, self._property_tabs.tabBar().sizeHint().height())
            available_width = max(1, self._property_tabs.contentsRect().width())
            content_height = 24
            for index in range(self._property_tabs.count()):
                page = self._property_tabs.widget(index)
                if page is None:
                    continue
                if page.hasHeightForWidth():
                    content_height = max(
                        content_height,
                        page.heightForWidth(available_width),
                    )
                else:
                    content_height = max(content_height, page.sizeHint().height())
            # Border and pane chrome around the active page.
            target_height = tab_bar_height + content_height + 2
            if self._property_tabs.height() != target_height:
                self._property_tabs.setFixedHeight(target_height)
        finally:
            self._fitting_property_tabs = False

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
        self._update_style_color_visibility(tool=tool, selection_type=selection_type)
        targets = self._resolve_style_color_targets(
            tool=tool,
            selection_type=selection_type,
        )
        if targets:
            self._property_tabs.setCurrentIndex(self._PROPERTY_TAB_STYLE)

    def _build_tool_icon(self, tool: str, *, locked: bool = False) -> QIcon:
        """
        Builds a vector icon for one toolbar drawing tool.

        Args:
            tool: Tool identifier.
            locked: True to overlay a lock badge on the icon.

        Returns:
            QIcon: Rendered icon.
        """

        size = 28
        scale = size / 18.0
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.scale(scale, scale)

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
        elif tool == Tool.TRIANGLE:
            painter.setPen(stroke_pen)
            painter.setBrush(QBrush(QColor(74, 163, 255, 70)))
            painter.drawPolygon(
                QPolygonF(
                    [
                        QPointF(9.0, 3.0),
                        QPointF(15.0, 14.0),
                        QPointF(3.0, 14.0),
                    ]
                )
            )
        elif tool == Tool.STAR:
            painter.setPen(stroke_pen)
            painter.setBrush(QBrush(QColor(241, 196, 15, 160)))
            painter.drawPolygon(
                QPolygonF(
                    [
                        QPointF(9.0, 2.5),
                        QPointF(10.5, 7.0),
                        QPointF(15.0, 7.2),
                        QPointF(11.4, 10.0),
                        QPointF(12.7, 14.5),
                        QPointF(9.0, 12.0),
                        QPointF(5.3, 14.5),
                        QPointF(6.6, 10.0),
                        QPointF(3.0, 7.2),
                        QPointF(7.5, 7.0),
                    ]
                )
            )
        elif tool == Tool.POLYGON:
            # Irregular freeform outline with vertex dots (not a regular pentagon).
            painter.setPen(stroke_pen)
            painter.setBrush(QBrush(QColor(74, 163, 255, 70)))
            polygon_points = [
                QPointF(3.0, 5.5),
                QPointF(7.5, 2.5),
                QPointF(14.5, 4.0),
                QPointF(12.5, 10.5),
                QPointF(15.0, 14.5),
                QPointF(8.0, 13.0),
                QPointF(3.5, 14.0),
            ]
            painter.drawPolygon(QPolygonF(polygon_points))
            painter.setBrush(QBrush(QColor("#d7e3f1")))
            painter.setPen(QPen(QColor("#8fa3b8"), 0.8))
            for point in polygon_points:
                painter.drawEllipse(point, 1.15, 1.15)
        elif tool == Tool.LINE:
            painter.setPen(stroke_pen)
            painter.drawLine(3, 14, 15, 4)
        elif tool == Tool.POLYLINE:
            painter.setPen(stroke_pen)
            painter.drawPolyline(
                QPolygonF(
                    [
                        QPointF(3.0, 13.0),
                        QPointF(7.0, 6.0),
                        QPointF(11.0, 11.0),
                        QPointF(15.0, 4.0),
                    ]
                )
            )
        elif tool == Tool.ARROW:
            painter.setPen(accent_pen)
            painter.drawLine(3, 14, 13, 5)
            painter.drawLine(13, 5, 11, 5)
            painter.drawLine(13, 5, 13, 7)
        elif tool == Tool.DOUBLE_ARROW:
            painter.setPen(accent_pen)
            painter.drawLine(4, 14, 14, 4)
            painter.drawLine(4, 14, 4, 11)
            painter.drawLine(4, 14, 7, 14)
            painter.drawLine(14, 4, 14, 7)
            painter.drawLine(14, 4, 11, 4)
        elif tool == Tool.BENT_ARROW:
            painter.setPen(accent_pen)
            painter.drawPolyline(
                QPolygonF(
                    [
                        QPointF(3.0, 13.0),
                        QPointF(3.0, 6.0),
                        QPointF(12.0, 6.0),
                    ]
                )
            )
            painter.drawLine(12, 6, 10, 4)
            painter.drawLine(12, 6, 10, 8)
        elif tool == Tool.SPOTLIGHT:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(0, 0, 0, 140)))
            painter.drawRect(QRectF(2.0, 2.0, 14.0, 14.0))
            painter.setBrush(QBrush(QColor(0, 0, 0, 0)))
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.drawEllipse(QRectF(5.0, 5.0, 8.0, 8.0))
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setPen(QPen(QColor("#f1c40f"), 1.3))
            painter.drawEllipse(QRectF(5.0, 5.0, 8.0, 8.0))
        elif tool == Tool.CROSS:
            painter.setPen(QPen(QColor("#e74c3c"), 2.0))
            painter.drawLine(4, 4, 14, 14)
            painter.drawLine(14, 4, 4, 14)
        elif tool == Tool.CHECKMARK:
            painter.setPen(QPen(QColor("#27ae60"), 2.0))
            painter.drawPolyline(
                QPolygonF(
                    [
                        QPointF(3.5, 9.5),
                        QPointF(7.5, 13.5),
                        QPointF(14.5, 4.5),
                    ]
                )
            )
        elif tool == Tool.TEXT:
            painter.setPen(stroke_pen)
            text_font = painter.font()
            text_font.setBold(True)
            text_font.setPointSize(10)
            painter.setFont(text_font)
            painter.drawText(QRectF(2.0, 1.0, 14.0, 16.0), "T")
        elif tool == Tool.CALLOUT:
            painter.setPen(stroke_pen)
            painter.setBrush(QBrush(QColor(255, 255, 255, 220)))
            painter.drawRoundedRect(QRectF(2.5, 2.5, 13.0, 9.0), 2.0, 2.0)
            painter.drawPolygon(
                QPolygonF(
                    [
                        QPointF(5.0, 11.0),
                        QPointF(8.0, 11.0),
                        QPointF(6.0, 15.0),
                    ]
                )
            )
        elif tool == Tool.FILL_BG:
            painter.setPen(stroke_pen)
            painter.setBrush(QBrush(QColor(74, 163, 255, 100)))
            painter.drawRect(QRectF(2.5, 9.0, 13.0, 6.0))
            painter.drawLine(5, 8, 9, 4)
            painter.drawLine(9, 4, 12, 7)
        elif tool == Tool.SELECT_RECT:
            painter.setPen(QPen(QColor("#f5f5f5"), 1.4, Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(QColor(52, 152, 219, 60)))
            painter.drawRect(QRectF(3.0, 4.0, 12.0, 10.0))
        elif tool == Tool.SELECT_ELLIPSE:
            painter.setPen(QPen(QColor("#f5f5f5"), 1.4, Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(QColor(52, 152, 219, 60)))
            painter.drawEllipse(QRectF(3.0, 4.0, 12.0, 10.0))
        elif tool == Tool.SELECT_PATH:
            painter.setPen(QPen(QColor("#f5f5f5"), 1.4, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolyline(
                QPolygonF(
                    [
                        QPointF(3.0, 12.0),
                        QPointF(6.0, 5.0),
                        QPointF(11.0, 8.0),
                        QPointF(15.0, 4.0),
                    ]
                )
            )
        elif tool == Tool.MAGIC_WAND:
            wand_pen = QPen(QColor("#f5d76e"), 1.8)
            wand_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(wand_pen)
            painter.drawLine(QPointF(4.5, 15.0), QPointF(11.5, 7.0))
            star_center = QPointF(12.5, 5.0)
            star_points = QPolygonF(
                [
                    QPointF(star_center.x(), star_center.y() - 3.6),
                    QPointF(star_center.x() + 1.0, star_center.y() - 1.0),
                    QPointF(star_center.x() + 3.6, star_center.y()),
                    QPointF(star_center.x() + 1.0, star_center.y() + 1.0),
                    QPointF(star_center.x(), star_center.y() + 3.6),
                    QPointF(star_center.x() - 1.0, star_center.y() + 1.0),
                    QPointF(star_center.x() - 3.6, star_center.y()),
                    QPointF(star_center.x() - 1.0, star_center.y() - 1.0),
                ]
            )
            painter.setPen(QPen(QColor("#f7e27a"), 1.0))
            painter.setBrush(QBrush(QColor("#f1c40f")))
            painter.drawPolygon(star_points)
            spark_pen = QPen(QColor("#fff6c2"), 1.2)
            spark_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(spark_pen)
            painter.drawLine(QPointF(15.2, 2.2), QPointF(16.4, 1.0))
            painter.drawLine(QPointF(15.8, 4.8), QPointF(17.0, 4.8))
            painter.drawLine(QPointF(13.8, 1.4), QPointF(13.8, 0.2))
        elif tool == Tool.BRUSH:
            painter.setPen(stroke_pen)
            painter.setBrush(QBrush(QColor(74, 163, 255, 180)))
            painter.drawEllipse(QRectF(4.0, 3.0, 5.0, 5.0))
            painter.drawLine(6, 8, 13, 15)
        elif tool == Tool.ERASER:
            painter.setPen(stroke_pen)
            painter.setBrush(QBrush(QColor(236, 240, 241, 220)))
            painter.drawRoundedRect(QRectF(4.0, 5.0, 10.0, 8.0), 1.5, 1.5)
            painter.drawLine(5, 7, 13, 7)
        elif tool == Tool.BUCKET:
            painter.setPen(stroke_pen)
            painter.setBrush(QBrush(QColor(74, 163, 255, 120)))
            painter.drawRect(QRectF(4.0, 7.0, 9.0, 7.0))
            painter.drawLine(7, 7, 10, 3)
        elif tool == Tool.EYEDROPPER:
            painter.setPen(QPen(QColor("#f5f5f5"), 1.6))
            painter.drawLine(QPointF(5.0, 14.0), QPointF(11.0, 8.0))
            painter.setBrush(QBrush(QColor("#e74c3c")))
            painter.drawEllipse(QRectF(10.0, 3.0, 5.0, 5.0))
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
            painter.drawText(
                QRectF(3.0, 2.0, 12.0, 14.0),
                int(Qt.AlignmentFlag.AlignCenter),
                "1",
            )
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

        if locked:
            painter.resetTransform()
            badge_bg = QColor(20, 24, 32, 230)
            badge_pen = QPen(QColor("#f1c40f"), 1.2)
            painter.setPen(badge_pen)
            painter.setBrush(QBrush(badge_bg))
            body = QRectF(size - 10.0, size - 8.5, 8.5, 6.5)
            painter.drawRoundedRect(body, 1.2, 1.2)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            shackle = QRectF(size - 8.4, size - 12.2, 5.2, 5.0)
            painter.drawArc(shackle, 0 * 16, 180 * 16)

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
        if isinstance(widget, QComboBox):
            widget.setMaxVisibleItems(16)

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

    def _configure_menu_tool_button(self, button: QToolButton) -> None:
        """
        Configures a tool strip button that shows a dropdown menu arrow.

        Marks the button for stylesheet icon padding so the glyph sits in the
        left content area instead of being centered over the menu strip.

        Args:
            button: Tool button that already has a menu attached.

        Returns:
            None
        """

        button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        button.setFixedSize(50, 34)
        button.setProperty("menuTool", True)
        style = button.style()
        if style is not None:
            style.unpolish(button)
            style.polish(button)
        button.update()

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

    def _create_palette_row(self, colors: list[QColor], target: str) -> QWidget:
        """
        Builds one compact horizontal row of palette swatches.

        Args:
            colors: Palette colors to show.
            target: Style target key (stroke, fill, text).

        Returns:
            QWidget: Row widget with 2px horizontal spacing between swatches.
        """

        row = QWidget()
        row.setObjectName("paletteSwatchRow")
        row.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        for color in colors:
            layout.addWidget(self._create_palette_button(color, target))
        return row

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
        button.setObjectName("paletteSwatch")
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

    def _tool_tooltip_text(self, tool: str) -> str:
        """
        Returns the English tooltip for one drawing tool button.

        Args:
            tool: Tool identifier.

        Returns:
            str: Descriptive tooltip text.
        """

        return format_tool_tooltip(tool)

    def _apply_toolbar_tooltips(self) -> None:
        """
        Adds English tooltip text to all toolbar controls.

        Returns:
            None
        """

        for tool_key, button in self._tool_buttons.items():
            button.setToolTip(self._tool_tooltip_text(tool_key))

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
        Builds the application menu bar and registers shortcut actions.

        Returns:
            None
        """

        menu = self.menuBar()
        file_menu = menu.addMenu("File")
        edit_menu = menu.addMenu("Edit")
        view_menu = menu.addMenu("View")
        help_menu = menu.addMenu("Help")

        new_canvas_action = QAction("New Canvas...", self)
        new_canvas_action.setToolTip("Create a blank canvas with a custom size.")
        new_canvas_action.triggered.connect(self.new_canvas_requested.emit)
        file_menu.addAction(new_canvas_action)
        self._register_shortcut_action("new_canvas", new_canvas_action)

        new_tab_action = QAction("New Tab", self)
        new_tab_action.setToolTip("Open a new empty editor tab.")
        new_tab_action.triggered.connect(self.new_tab_requested.emit)
        file_menu.addAction(new_tab_action)
        self._register_shortcut_action("new_tab", new_tab_action)

        file_menu.addSeparator()

        open_action = QAction("Open Project...", self)
        open_action.setToolTip("Open an existing Snappix project.")
        open_action.triggered.connect(self.open_project)
        file_menu.addAction(open_action)
        self._register_shortcut_action("open_project", open_action)

        save_as_action = QAction("Save Project As...", self)
        save_as_action.setToolTip("Save project under a new file name.")
        save_as_action.triggered.connect(self.save_project_as)
        file_menu.addAction(save_as_action)
        self._register_shortcut_action("save_project_as", save_as_action)

        save_action = QAction("Save Project", self)
        save_action.setToolTip("Save changes to the current project.")
        save_action.triggered.connect(self.save_project)
        file_menu.addAction(save_action)
        self._register_shortcut_action("save_project", save_action)

        export_action = QAction("Export...", self)
        export_action.setToolTip("Open export dialog for image or PDF.")
        export_action.triggered.connect(self.export_with_dialog)
        file_menu.addAction(export_action)
        self._register_shortcut_action("export", export_action)

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

        export_svg = QAction("Export as SVG...", self)
        export_svg.setToolTip(
            "Export the composited image as a standard SVG (raster embedded)."
        )
        export_svg.triggered.connect(self.export_svg)
        file_menu.addAction(export_svg)

        export_batch = QAction("Batch Export...", self)
        export_batch.setToolTip("Export current tab to multiple formats at once.")
        export_batch.triggered.connect(self.export_batch_with_dialog)
        file_menu.addAction(export_batch)

        file_menu.addSeparator()

        print_action = QAction("Print...", self)
        print_action.setToolTip("Print the composited image.")
        print_action.triggered.connect(self.print_image)
        file_menu.addAction(print_action)
        self._register_shortcut_action("print", print_action)

        file_menu.addSeparator()

        close_action = QAction("Close", self)
        close_action.setToolTip("Close this editor tab.")
        close_action.triggered.connect(self.close)
        file_menu.addAction(close_action)
        self._register_shortcut_action("close_tab", close_action)

        self.undo_action = QAction("Undo", self)
        self.undo_action.setToolTip("Undo the last change.")
        self.undo_action.triggered.connect(self.undo)
        edit_menu.addAction(self.undo_action)
        self._register_shortcut_action("undo", self.undo_action)

        self.redo_action = QAction("Redo", self)
        self.redo_action.setToolTip("Redo the last undone change.")
        self.redo_action.triggered.connect(self.redo)
        edit_menu.addAction(self.redo_action)
        self._register_shortcut_action("redo", self.redo_action)

        duplicate_action = QAction("Duplicate", self)
        duplicate_action.setToolTip("Duplicate the current selection.")
        duplicate_action.triggered.connect(self._duplicate_selection)
        edit_menu.addAction(duplicate_action)
        self._register_shortcut_action("duplicate", duplicate_action)

        edit_menu.addSeparator()

        flatten_action = QAction("Flatten Annotations", self)
        flatten_action.setToolTip(
            "Burn all annotations into the screenshot as one fixed image."
        )
        flatten_action.triggered.connect(self.canvas.flatten_annotations)
        edit_menu.addAction(flatten_action)
        self._register_shortcut_action("flatten", flatten_action)

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

        copy_image_action = QAction("Copy", self)
        copy_image_action.setToolTip(
            "Copy selected annotations, or the full drawing area when nothing is selected."
        )
        copy_image_action.triggered.connect(self.copy_current_image_to_clipboard)
        edit_menu.addAction(copy_image_action)
        self._register_shortcut_action("copy", copy_image_action)

        paste_action = QAction("Paste", self)
        paste_action.setToolTip("Paste text, image, or Snappix clipboard payloads.")
        paste_action.triggered.connect(self.paste_from_clipboard)
        edit_menu.addAction(paste_action)
        self._register_shortcut_action("paste", paste_action)

        copy_canvas_area_action = QAction("Copy Drawing Area", self)
        copy_canvas_area_action.setToolTip("Copy this tab drawing area for another tab.")
        copy_canvas_area_action.triggered.connect(self.copy_drawing_area_to_clipboard)
        edit_menu.addAction(copy_canvas_area_action)
        self._register_shortcut_action("copy_drawing_area", copy_canvas_area_action)

        paste_canvas_area_action = QAction("Paste Drawing Area", self)
        paste_canvas_area_action.setToolTip("Paste copied drawing area into this tab.")
        paste_canvas_area_action.triggered.connect(self.paste_drawing_area_from_clipboard)
        edit_menu.addAction(paste_canvas_area_action)
        self._register_shortcut_action("paste_drawing_area", paste_canvas_area_action)

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
        self.theme_slate_action = QAction("Slate", self)
        self.theme_slate_action.setCheckable(True)
        self.theme_slate_action.setToolTip("Use the cool slate application theme.")
        self.theme_slate_action.triggered.connect(
            lambda: self.theme_changed.emit(THEME_SLATE)
        )
        self._theme_action_group.addAction(self.theme_slate_action)
        theme_menu.addAction(self.theme_slate_action)
        self.theme_sepia_action = QAction("Sepia", self)
        self.theme_sepia_action.setCheckable(True)
        self.theme_sepia_action.setToolTip("Use the warm sepia application theme.")
        self.theme_sepia_action.triggered.connect(
            lambda: self.theme_changed.emit(THEME_SEPIA)
        )
        self._theme_action_group.addAction(self.theme_sepia_action)
        theme_menu.addAction(self.theme_sepia_action)

        view_menu.addSeparator()
        zoom_in_action = QAction("Zoom In", self)
        zoom_in_action.setToolTip("Zoom in on the canvas.")
        zoom_in_action.triggered.connect(self.canvas.zoom_in)
        view_menu.addAction(zoom_in_action)
        self._register_shortcut_action("zoom_in", zoom_in_action)

        zoom_out_action = QAction("Zoom Out", self)
        zoom_out_action.setToolTip("Zoom out on the canvas.")
        zoom_out_action.triggered.connect(self.canvas.zoom_out)
        view_menu.addAction(zoom_out_action)
        self._register_shortcut_action("zoom_out", zoom_out_action)

        zoom_reset_action = QAction("Reset Zoom", self)
        zoom_reset_action.setToolTip("Reset zoom to fit the document.")
        zoom_reset_action.triggered.connect(self.canvas.reset_zoom)
        view_menu.addAction(zoom_reset_action)
        self._register_shortcut_action("zoom_reset", zoom_reset_action)

        scale_up_action = QAction("Scale Selection Up", self)
        scale_up_action.setToolTip("Scale the current selection larger.")
        scale_up_action.triggered.connect(lambda: self.canvas.resize_selected_items(1.1))
        view_menu.addAction(scale_up_action)
        self._register_shortcut_action("scale_selection_up", scale_up_action)

        scale_down_action = QAction("Scale Selection Down", self)
        scale_down_action.setToolTip("Scale the current selection smaller.")
        scale_down_action.triggered.connect(lambda: self.canvas.resize_selected_items(0.9))
        view_menu.addAction(scale_down_action)
        self._register_shortcut_action("scale_selection_down", scale_down_action)

        settings_action = QAction("Settings...", self)
        settings_action.setToolTip("Configure hotkeys, shortcuts, and capture behavior.")
        settings_action.triggered.connect(self.settings_requested.emit)
        view_menu.addAction(settings_action)

        about_action = QAction("About", self)
        about_action.setToolTip("Show application information.")
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

        manual_action = QAction("Manual", self)
        manual_action.setToolTip("Show a short manual and the current keyboard shortcuts.")
        manual_action.triggered.connect(self.show_manual)
        help_menu.addAction(manual_action)

        for action_id, tool_key in [
            ("tool_select_rect", Tool.SELECT_RECT),
            ("tool_select_ellipse", Tool.SELECT_ELLIPSE),
            ("tool_select_path", Tool.SELECT_PATH),
            ("tool_magic_wand", Tool.MAGIC_WAND),
            ("tool_brush", Tool.BRUSH),
            ("tool_eraser", Tool.ERASER),
            ("tool_bucket", Tool.BUCKET),
            ("tool_eyedropper", Tool.EYEDROPPER),
        ]:
            tool_action = QAction(self)
            tool_action.triggered.connect(
                lambda _checked=False, selected=tool_key: self._on_tool_button_clicked(selected)
            )
            self.addAction(tool_action)
            self._register_shortcut_action(action_id, tool_action)

        self.apply_editor_shortcuts({})
        self._update_undo_redo_actions()

    def _register_shortcut_action(self, action_id: str, action: QAction) -> None:
        """
        Registers one menu action for configurable keyboard shortcuts.

        Args:
            action_id: Stable shortcut identifier.
            action: Qt action that receives the binding.

        Returns:
            None
        """

        self._shortcut_actions[action_id] = action

    def apply_editor_shortcuts(self, overrides: dict[str, str] | None) -> None:
        """
        Applies configured editor shortcuts to registered actions.

        Args:
            overrides: Shortcut overrides from application settings.

        Returns:
            None
        """

        self._editor_shortcut_overrides = normalize_editor_shortcuts(overrides)
        for action_id, action in self._shortcut_actions.items():
            binding = format_shortcut_for_display(
                resolved_shortcut_text(action_id, self._editor_shortcut_overrides)
            )
            tip = action.toolTip().split(" Shortcut:")[0].rstrip()
            if binding != "(none)":
                action.setToolTip(f"{tip} Shortcut: {binding}.")
            else:
                action.setToolTip(tip)
            if action_id in HOST_OWNED_SHORTCUT_IDS:
                # Host QShortcuts own these keys; keep menu actions clickable only.
                action.setShortcuts([])
                continue
            sequences = sequences_for_action(action_id, self._editor_shortcut_overrides)
            action.setShortcuts(sequences)

    def _setup_pixel_tool_option_menus(self) -> None:
        """
        Attaches popup menus for Contiguous and Delete erase mode to pixel tools.

        Returns:
            None
        """

        self.wand_contiguous_action = QAction("Contiguous", self)
        self.wand_contiguous_action.setCheckable(True)
        self.wand_contiguous_action.setChecked(self.canvas.wand_contiguous())
        self.wand_contiguous_action.setToolTip(
            "When checked, Magic Wand selects only connected matching pixels. "
            "When unchecked, all matching colors are selected."
        )
        self.wand_contiguous_action.toggled.connect(self._wand_contiguous_changed)

        self.erase_transparent_action = QAction("Erase: Transparent", self)
        self.erase_transparent_action.setCheckable(True)
        self.erase_transparent_action.setToolTip(
            "Delete clears the pixel selection to transparent."
        )
        self.erase_fill_action = QAction("Erase: Fill color", self)
        self.erase_fill_action.setCheckable(True)
        self.erase_fill_action.setToolTip(
            "Delete fills the pixel selection with the current Fill color."
        )
        erase_group = QActionGroup(self)
        erase_group.setExclusive(True)
        erase_group.addAction(self.erase_transparent_action)
        erase_group.addAction(self.erase_fill_action)
        if self.canvas.erase_mode() == ERASE_MODE_FILL:
            self.erase_fill_action.setChecked(True)
        else:
            self.erase_transparent_action.setChecked(True)
        self.erase_transparent_action.triggered.connect(self._erase_mode_action_changed)
        self.erase_fill_action.triggered.connect(self._erase_mode_action_changed)

        selection_tools = (
            Tool.SELECT_RECT,
            Tool.SELECT_ELLIPSE,
            Tool.SELECT_PATH,
        )
        erase_menu = QMenu(self)
        erase_menu.addAction(self.erase_transparent_action)
        erase_menu.addAction(self.erase_fill_action)
        for tool_key in selection_tools:
            button = self._tool_buttons[tool_key]
            button.setMenu(erase_menu)
            self._configure_menu_tool_button(button)

        wand_menu = QMenu(self)
        tolerance_action = QWidgetAction(wand_menu)
        tolerance_row = QWidget(wand_menu)
        tolerance_layout = QHBoxLayout(tolerance_row)
        tolerance_layout.setContentsMargins(10, 8, 10, 8)
        tolerance_layout.setSpacing(8)
        tolerance_title = QLabel("Tolerance", tolerance_row)
        tolerance_title.setToolTip(
            "Magic Wand color tolerance (0–255). Higher values select a wider color range."
        )
        tolerance_layout.addWidget(tolerance_title)
        self.wand_tolerance_slider = QSlider(Qt.Orientation.Horizontal, tolerance_row)
        self.wand_tolerance_slider.setRange(0, 255)
        self.wand_tolerance_slider.setValue(self.canvas.wand_tolerance())
        self.wand_tolerance_slider.setMinimumWidth(120)
        self.wand_tolerance_slider.setToolTip(
            "Magic Wand color tolerance (0–255). Higher values select a wider color range."
        )
        self.wand_tolerance_slider.valueChanged.connect(self._wand_tolerance_changed)
        tolerance_layout.addWidget(self.wand_tolerance_slider, 1)
        self.wand_tolerance_label = QLabel(str(self.canvas.wand_tolerance()), tolerance_row)
        self.wand_tolerance_label.setMinimumWidth(28)
        self.wand_tolerance_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tolerance_layout.addWidget(self.wand_tolerance_label)
        tolerance_action.setDefaultWidget(tolerance_row)
        wand_menu.addAction(tolerance_action)
        wand_menu.addSeparator()
        wand_menu.addAction(self.wand_contiguous_action)
        wand_menu.addSeparator()
        wand_menu.addAction(self.erase_transparent_action)
        wand_menu.addAction(self.erase_fill_action)
        wand_button = self._tool_buttons[Tool.MAGIC_WAND]
        wand_button.setMenu(wand_menu)
        self._configure_menu_tool_button(wand_button)

        eyedropper_menu = QMenu(self)
        self.eyedropper_stroke_action = QAction("Sample → Border", self)
        self.eyedropper_stroke_action.setCheckable(True)
        self.eyedropper_stroke_action.setChecked(True)
        self.eyedropper_fill_action = QAction("Sample → Fill", self)
        self.eyedropper_fill_action.setCheckable(True)
        eyedropper_group = QActionGroup(self)
        eyedropper_group.setExclusive(True)
        eyedropper_group.addAction(self.eyedropper_stroke_action)
        eyedropper_group.addAction(self.eyedropper_fill_action)
        self.eyedropper_stroke_action.triggered.connect(
            lambda: self._set_eyedropper_target("stroke")
        )
        self.eyedropper_fill_action.triggered.connect(
            lambda: self._set_eyedropper_target("fill")
        )
        eyedropper_menu.addAction(self.eyedropper_stroke_action)
        eyedropper_menu.addAction(self.eyedropper_fill_action)
        eyedropper_button = self._tool_buttons[Tool.EYEDROPPER]
        eyedropper_button.setMenu(eyedropper_menu)
        self._configure_menu_tool_button(eyedropper_button)

        self._setup_blur_tool_option_menu()

    def _setup_stroke_width_tool_menus(self) -> None:
        """
        Attaches Width / Harden / Style popup menus to drawing tools.

        Returns:
            None
        """

        width_tools = (
            Tool.BRUSH,
            Tool.ERASER,
            Tool.RECT,
            Tool.ELLIPSE,
            Tool.TRIANGLE,
            Tool.STAR,
            Tool.POLYGON,
            Tool.LINE,
            Tool.POLYLINE,
            Tool.ARROW,
            Tool.DOUBLE_ARROW,
            Tool.BENT_ARROW,
            Tool.SPOTLIGHT,
        )
        for tool_key in width_tools:
            button = self._tool_buttons.get(tool_key)
            if button is None:
                continue
            menu = QMenu(self)
            panel_action = QWidgetAction(menu)
            panel = QWidget(menu)
            root = QVBoxLayout(panel)
            root.setContentsMargins(10, 8, 10, 8)
            root.setSpacing(6)

            width_row = QHBoxLayout()
            width_row.setSpacing(8)
            width_title = QLabel("Width", panel)
            width_title.setMinimumWidth(44)
            width_title.setToolTip(
                "Default stroke thickness for new draws with this tool "
                "(0 = no border for shapes). Selected elements keep their own width "
                "unless you change Width while they are selected."
            )
            width_row.addWidget(width_title)
            slider = QSlider(Qt.Orientation.Horizontal, panel)
            minimum = 1 if tool_key in BRUSH_WIDTH_TOOLS else 0
            slider.setRange(minimum, 64)
            slider.setValue(self._tool_stroke_widths.get(tool_key, 6))
            slider.setMinimumWidth(120)
            slider.setProperty("widthTool", tool_key)
            slider.valueChanged.connect(self._tool_menu_width_changed)
            width_row.addWidget(slider, 1)
            value_label = QLabel(str(slider.value()), panel)
            value_label.setMinimumWidth(28)
            value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            slider.valueChanged.connect(
                lambda value, label=value_label: label.setText(str(int(value)))
            )
            width_row.addWidget(value_label)
            root.addLayout(width_row)
            self._tool_width_sliders[tool_key] = slider
            self._tool_width_labels[tool_key] = value_label

            if tool_key in HARDNESS_AWARE_TOOLS:
                hard_row = QHBoxLayout()
                hard_row.setSpacing(8)
                hard_title = QLabel("Hard", panel)
                hard_title.setMinimumWidth(44)
                hard_title.setToolTip(
                    "Brush / eraser edge hardness for this tool "
                    "(0 = soft edge, 100 = hard edge)."
                )
                hard_row.addWidget(hard_title)
                hard_slider = QSlider(Qt.Orientation.Horizontal, panel)
                hard_slider.setRange(0, 100)
                hard_slider.setValue(self._tool_brush_hardness.get(tool_key, 80))
                hard_slider.setMinimumWidth(120)
                hard_slider.setProperty("hardnessTool", tool_key)
                hard_slider.valueChanged.connect(self._tool_menu_hardness_changed)
                hard_row.addWidget(hard_slider, 1)
                hard_label = QLabel(f"{hard_slider.value()}%", panel)
                hard_label.setMinimumWidth(36)
                hard_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                hard_slider.valueChanged.connect(
                    lambda value, label=hard_label: label.setText(f"{int(value)}%")
                )
                hard_row.addWidget(hard_label)
                root.addLayout(hard_row)
                self._tool_hardness_sliders[tool_key] = hard_slider
                self._tool_hardness_labels[tool_key] = hard_label

            if tool_key in STYLE_AWARE_TOOLS:
                style_row = QHBoxLayout()
                style_row.setSpacing(8)
                style_title = QLabel("Style", panel)
                style_title.setMinimumWidth(44)
                style_title.setToolTip(
                    "Default line/border style for new draws with this tool. "
                    "Selected lines/shapes update when changed while selected."
                )
                style_row.addWidget(style_title)
                style_combo = QComboBox(panel)
                style_combo.addItem("Solid", STROKE_STYLE_SOLID)
                style_combo.addItem("Dash", STROKE_STYLE_DASH)
                style_combo.addItem("Dot", STROKE_STYLE_DOT)
                style_combo.addItem("Dash dot", STROKE_STYLE_DASH_DOT)
                current_style = self._tool_stroke_styles.get(tool_key, STROKE_STYLE_SOLID)
                style_index = style_combo.findData(current_style)
                if style_index >= 0:
                    style_combo.setCurrentIndex(style_index)
                style_combo.setProperty("styleTool", tool_key)
                style_combo.setMinimumWidth(120)
                style_combo.currentIndexChanged.connect(self._tool_menu_style_changed)
                style_row.addWidget(style_combo, 1)
                root.addLayout(style_row)
                self._tool_style_combos[tool_key] = style_combo

            if tool_key == Tool.RECT:
                radius_row = QHBoxLayout()
                radius_row.setSpacing(8)
                radius_title = QLabel("Radius", panel)
                radius_title.setMinimumWidth(44)
                radius_title.setToolTip(
                    "Corner radius for rectangles (0 = sharp corners). "
                    "Applies to new draws and to a selected rectangle."
                )
                radius_row.addWidget(radius_title)
                radius_spin = QDoubleSpinBox(panel)
                radius_spin.setDecimals(1)
                radius_spin.setSingleStep(1.0)
                radius_spin.setRange(0.0, 200.0)
                radius_spin.setValue(float(self._rect_corner_radius))
                radius_spin.setMinimumWidth(120)
                radius_spin.setProperty("radiusTool", tool_key)
                radius_spin.valueChanged.connect(self._tool_menu_radius_changed)
                radius_row.addWidget(radius_spin, 1)
                root.addLayout(radius_row)
                self._tool_radius_spins[tool_key] = radius_spin

            panel_action.setDefaultWidget(panel)
            menu.addAction(panel_action)
            menu.aboutToShow.connect(
                lambda _checked=False, key=tool_key: self._prepare_stroke_tool_menu(key)
            )
            button.setMenu(menu)
            self._configure_menu_tool_button(button)

    def _tool_menu_width_changed(self, value: int) -> None:
        """
        Applies a width change from a tool popup slider.

        Args:
            value: New width.

        Returns:
            None
        """

        sender = self.sender()
        tool = ""
        if isinstance(sender, QSlider):
            tool = str(sender.property("widthTool") or "")
        self._apply_tool_stroke_width(
            value,
            tool=tool or None,
            persist=True,
        )

    def _tool_menu_hardness_changed(self, value: int) -> None:
        """
        Applies a hardness change from a Brush/Eraser popup slider.

        Args:
            value: New hardness percentage.

        Returns:
            None
        """

        sender = self.sender()
        tool = ""
        if isinstance(sender, QSlider):
            tool = str(sender.property("hardnessTool") or "")
        self._apply_tool_brush_hardness(
            value,
            tool=tool or None,
            persist=True,
        )

    def _tool_menu_style_changed(self, _index: int) -> None:
        """
        Applies a stroke-style change from a shape-tool popup combo.

        Args:
            _index: Selected combo index.

        Returns:
            None
        """

        sender = self.sender()
        tool = ""
        style = ""
        if isinstance(sender, QComboBox):
            tool = str(sender.property("styleTool") or "")
            data = sender.currentData()
            if isinstance(data, str):
                style = data
        if not style:
            return
        self._apply_tool_stroke_style(
            style,
            tool=tool or None,
            persist=True,
        )

    def _tool_menu_radius_changed(self, value: float) -> None:
        """
        Applies a rectangle corner-radius change from the Rectangle tool menu.

        Args:
            value: New corner radius in pixels.

        Returns:
            None
        """

        sender = self.sender()
        tool = ""
        if isinstance(sender, QDoubleSpinBox):
            tool = str(sender.property("radiusTool") or "")
        if tool and tool != Tool.RECT:
            return
        resolved = max(0.0, float(value))
        self._rect_corner_radius = resolved
        self.canvas.set_rect_corner_radius(
            resolved,
            apply_to_selection=True,
            emit_history=True,
        )

    def _prepare_stroke_tool_menu(self, tool_key: str) -> None:
        """
        Refreshes one stroke-tool popup from selection or tool defaults.

        Args:
            tool_key: Tool identifier for the opening menu.

        Returns:
            None
        """

        payload = self._primary_selection_payload()
        if payload is not None and self._selection_uses_stroke_menu(payload, tool_key):
            self._sync_stroke_tool_menu_widgets(payload, tool_key=tool_key)
            return
        self._restore_stroke_tool_menu_widgets(tool_key=tool_key)

    def _prepare_text_tool_menu(self) -> None:
        """
        Refreshes the Text tool popup from selection or text defaults.

        Returns:
            None
        """

        payload = self._primary_selection_payload()
        if payload is not None and str(payload.get("type") or "") == "text":
            self._sync_text_tool_menu_widgets(payload)
            return
        self._restore_text_tool_menu_widgets()

    def _primary_selection_payload(self) -> dict[str, Any] | None:
        """
        Returns the primary selected annotation payload, if any.

        Returns:
            dict[str, Any] | None: Selection details or None.
        """

        selected = self.canvas._selected_annotation_items()  # pylint: disable=protected-access
        if not selected:
            return None
        return self.canvas._build_selection_payload(selected[0])  # pylint: disable=protected-access

    def _selection_uses_stroke_menu(self, payload: dict[str, Any], tool_key: str) -> bool:
        """
        Checks whether a selection should drive one stroke-tool popup.

        Args:
            payload: Selection payload.
            tool_key: Tool menu being prepared.

        Returns:
            bool: True when the selection maps to this menu.
        """

        selection_type = str(payload.get("type") or "")
        if tool_key in {Tool.BRUSH, Tool.ERASER}:
            # Brush/eraser menus always edit tool defaults; raster strokes are not
            # re-editable annotation objects.
            return False
        if selection_type in {"rect", "ellipse", "triangle", "round_rect", "star", "highlight", "spotlight", "cross", "checkmark", "line", "arrow", "double_arrow", "polyline", "polygon", "bent_arrow"}:
            return True
        return False

    def _set_width_slider_value(self, tool_key: str, width: int) -> None:
        """
        Updates one tool Width slider without emitting change handlers.

        Args:
            tool_key: Tool identifier.
            width: Width to display.

        Returns:
            None
        """

        slider = self._tool_width_sliders.get(tool_key)
        if tool_key == Tool.TEXT:
            slider = getattr(self, "text_width_menu_slider", None)
        if slider is None:
            return
        minimum = 1 if tool_key in BRUSH_WIDTH_TOOLS else 0
        resolved = normalize_stroke_width(width, minimum=minimum)
        if slider.value() == resolved:
            return
        slider.blockSignals(True)
        slider.setValue(resolved)
        slider.blockSignals(False)
        label = self._tool_width_labels.get(tool_key)
        if tool_key == Tool.TEXT:
            label = getattr(self, "text_width_menu_label", None)
        if label is not None:
            label.setText(str(resolved))

    def _set_style_combo_value(self, tool_key: str, stroke_style: str) -> None:
        """
        Updates one tool Style combo without emitting change handlers.

        Args:
            tool_key: Tool identifier.
            stroke_style: Named stroke style.

        Returns:
            None
        """

        combo = self._tool_style_combos.get(tool_key)
        if combo is None:
            return
        resolved = normalize_named_stroke_style(stroke_style)
        index = combo.findData(resolved)
        if index < 0 or combo.currentIndex() == index:
            return
        combo.blockSignals(True)
        combo.setCurrentIndex(index)
        combo.blockSignals(False)

    def _set_hardness_slider_value(self, tool_key: str, hardness: int) -> None:
        """
        Updates one Hard slider without emitting change handlers.

        Args:
            tool_key: Tool identifier.
            hardness: Hardness percentage.

        Returns:
            None
        """

        slider = self._tool_hardness_sliders.get(tool_key)
        if slider is None:
            return
        resolved = normalize_brush_hardness(hardness)
        if slider.value() == resolved:
            return
        slider.blockSignals(True)
        slider.setValue(resolved)
        slider.blockSignals(False)
        label = self._tool_hardness_labels.get(tool_key)
        if label is not None:
            label.setText(f"{resolved}%")

    def _sync_stroke_tool_menu_widgets(
        self,
        payload: dict[str, Any],
        *,
        tool_key: str | None = None,
    ) -> None:
        """
        Shows selected annotation stroke properties in tool popup widgets.

        Args:
            payload: Selection payload.
            tool_key: Optional single tool menu to update; all when omitted.

        Returns:
            None
        """

        stroke_width = payload.get("stroke_width")
        stroke_style = payload.get("stroke_style")
        targets = (
            [tool_key]
            if tool_key
            else [
                key
                for key in self._tool_width_sliders.keys()
                if key not in {Tool.BRUSH, Tool.ERASER}
            ]
        )
        for key in targets:
            if key is None or key in {Tool.BRUSH, Tool.ERASER}:
                continue
            if isinstance(stroke_width, (int, float)) and key in WIDTH_AWARE_TOOLS:
                self._set_width_slider_value(key, int(round(float(stroke_width))))
            if (
                isinstance(stroke_style, str)
                and key in STYLE_AWARE_TOOLS
                and key in self._tool_style_combos
            ):
                self._set_style_combo_value(key, stroke_style)
            if key == Tool.RECT and str(payload.get("type") or "") == "rect":
                corner_radius = payload.get("corner_radius")
                if isinstance(corner_radius, (int, float)):
                    self._set_radius_spin_value(key, float(corner_radius))

    def _restore_stroke_tool_menu_widgets(self, *, tool_key: str | None = None) -> None:
        """
        Restores stroke-tool popup widgets to persisted tool defaults.

        Args:
            tool_key: Optional single tool menu to restore; all when omitted.

        Returns:
            None
        """

        targets = (
            [tool_key]
            if tool_key
            else list(
                dict.fromkeys(
                    list(self._tool_width_sliders.keys())
                    + list(self._tool_hardness_sliders.keys())
                    + list(self._tool_style_combos.keys())
                    + list(self._tool_radius_spins.keys())
                )
            )
        )
        for key in targets:
            if key is None:
                continue
            if key in WIDTH_AWARE_TOOLS and key in self._tool_width_sliders:
                self._set_width_slider_value(
                    key,
                    self._tool_stroke_widths.get(key, 6),
                )
            if key in HARDNESS_AWARE_TOOLS:
                self._set_hardness_slider_value(
                    key,
                    self._tool_brush_hardness.get(key, 80),
                )
            if key in STYLE_AWARE_TOOLS:
                self._set_style_combo_value(
                    key,
                    self._tool_stroke_styles.get(key, STROKE_STYLE_SOLID),
                )
            if key == Tool.RECT and key in self._tool_radius_spins:
                self._set_radius_spin_value(key, float(self._rect_corner_radius))

    def _set_radius_spin_value(self, tool_key: str, radius: float) -> None:
        """
        Updates one tool Radius spin without emitting change handlers.

        Args:
            tool_key: Tool identifier.
            radius: Corner radius to display.

        Returns:
            None
        """

        spin = self._tool_radius_spins.get(tool_key)
        if spin is None:
            return
        resolved = max(0.0, float(radius))
        if abs(spin.value() - resolved) < 0.001:
            return
        spin.blockSignals(True)
        spin.setValue(resolved)
        spin.blockSignals(False)

    def _sync_text_tool_menu_widgets(self, payload: dict[str, Any]) -> None:
        """
        Shows selected text properties in the Text tool popup.

        Does not overwrite stored Text-tool defaults used for new annotations.

        Args:
            payload: Text selection payload.

        Returns:
            None
        """

        font_family = payload.get("font_family")
        if isinstance(font_family, str) and font_family.strip():
            self.font_family_combo.blockSignals(True)
            self.font_family_combo.setCurrentText(font_family.strip())
            self.font_family_combo.blockSignals(False)
        font_size = payload.get("font_size")
        if isinstance(font_size, int):
            self._set_font_size_combo_value(font_size)
        for attr, button_name in (
            ("font_bold", "text_bold_button"),
            ("font_italic", "text_italic_button"),
            ("font_underline", "text_underline_button"),
        ):
            value = payload.get(attr)
            button = getattr(self, button_name, None)
            if isinstance(value, bool) and button is not None:
                button.blockSignals(True)
                button.setChecked(value)
                button.blockSignals(False)
        letter_spacing = payload.get("letter_spacing")
        if isinstance(letter_spacing, (int, float)):
            self.text_letter_spacing_spin.blockSignals(True)
            self.text_letter_spacing_spin.setValue(float(letter_spacing))
            self.text_letter_spacing_spin.blockSignals(False)
        line_spacing_factor = payload.get("line_spacing_factor")
        if isinstance(line_spacing_factor, (int, float)):
            self.text_line_spacing_spin.blockSignals(True)
            self.text_line_spacing_spin.setValue(float(line_spacing_factor))
            self.text_line_spacing_spin.blockSignals(False)
        box_padding = payload.get("box_padding")
        if isinstance(box_padding, (int, float)):
            self.text_padding_spin.blockSignals(True)
            self.text_padding_spin.setValue(float(box_padding))
            self.text_padding_spin.blockSignals(False)
        corner_radius = payload.get("corner_radius")
        if isinstance(corner_radius, (int, float)):
            self.text_radius_spin.blockSignals(True)
            self.text_radius_spin.setValue(float(corner_radius))
            self.text_radius_spin.blockSignals(False)
        text_style = str(payload.get("text_style") or TEXT_STYLE_PLAIN)
        style_index = self.text_style_combo.findData(text_style)
        if style_index >= 0:
            self.text_style_combo.blockSignals(True)
            self.text_style_combo.setCurrentIndex(style_index)
            self.text_style_combo.blockSignals(False)
        supports_container = text_style in {TEXT_STYLE_BOX, TEXT_STYLE_BUBBLE}
        self.text_letter_spacing_spin.setEnabled(True)
        self.text_line_spacing_spin.setEnabled(supports_container)
        self.text_padding_spin.setEnabled(supports_container)
        self.text_radius_spin.setEnabled(supports_container)
        stroke_width = payload.get("stroke_width")
        if isinstance(stroke_width, (int, float)):
            self._set_width_slider_value(Tool.TEXT, int(round(float(stroke_width))))

    def _restore_text_tool_menu_widgets(self) -> None:
        """
        Restores Text tool popup widgets to defaults for new text annotations.

        Returns:
            None
        """

        style = self.canvas._style  # pylint: disable=protected-access
        family = style.font_family.strip() if style.font_family else ""
        if family:
            self.font_family_combo.blockSignals(True)
            self.font_family_combo.setCurrentText(family)
            self.font_family_combo.blockSignals(False)
        self._set_font_size_combo_value(int(style.font_size))
        self.text_bold_button.blockSignals(True)
        self.text_bold_button.setChecked(self._text_bold_enabled)
        self.text_bold_button.blockSignals(False)
        self.text_italic_button.blockSignals(True)
        self.text_italic_button.setChecked(self._text_italic_enabled)
        self.text_italic_button.blockSignals(False)
        self.text_underline_button.blockSignals(True)
        self.text_underline_button.setChecked(self._text_underline_enabled)
        self.text_underline_button.blockSignals(False)
        self.text_letter_spacing_spin.blockSignals(True)
        self.text_letter_spacing_spin.setValue(float(self._text_letter_spacing))
        self.text_letter_spacing_spin.blockSignals(False)
        self.text_line_spacing_spin.blockSignals(True)
        self.text_line_spacing_spin.setValue(float(self._text_line_spacing))
        self.text_line_spacing_spin.blockSignals(False)
        self.text_padding_spin.blockSignals(True)
        self.text_padding_spin.setValue(float(self._text_box_padding))
        self.text_padding_spin.blockSignals(False)
        self.text_radius_spin.blockSignals(True)
        self.text_radius_spin.setValue(float(self._text_corner_radius))
        self.text_radius_spin.blockSignals(False)
        style_index = self.text_style_combo.findData(style.text_style)
        if style_index >= 0:
            self.text_style_combo.blockSignals(True)
            self.text_style_combo.setCurrentIndex(style_index)
            self.text_style_combo.blockSignals(False)
        supports_container = style.text_style in {TEXT_STYLE_BOX, TEXT_STYLE_BUBBLE}
        self.text_letter_spacing_spin.setEnabled(True)
        self.text_line_spacing_spin.setEnabled(supports_container)
        self.text_padding_spin.setEnabled(supports_container)
        self.text_radius_spin.setEnabled(supports_container)
        self._set_width_slider_value(
            Tool.TEXT,
            self._tool_stroke_widths.get(Tool.TEXT, 2),
        )

    def _apply_text_menu_style(self, history_label: str, **style_kwargs: Any) -> None:
        """
        Applies Text-menu properties to selection or Text-tool defaults.

        Args:
            history_label: History entry label.
            **style_kwargs: Style fields forwarded to ``canvas.set_style``.

        Returns:
            None
        """

        if self.canvas.has_text_selection():
            self.canvas.set_style(
                **style_kwargs,
                emit_history=False,
                apply_to_selection=True,
                update_active_style=False,
            )
            self._set_next_history_label(history_label)
            self._push_history_state()
            return
        self.canvas.set_style(
            **style_kwargs,
            emit_history=False,
            apply_to_selection=False,
            update_active_style=True,
        )

    def _setup_text_tool_option_menu(self) -> None:
        """
        Attaches typography and text-container options to the Text tool popup.

        Returns:
            None
        """

        button = self._tool_buttons.get(Tool.TEXT)
        if button is None:
            return

        menu = QMenu(self)
        panel_action = QWidgetAction(menu)
        panel = QWidget(menu)
        root = QVBoxLayout(panel)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)

        def add_row(label_text: str, widget: QWidget) -> None:
            row = QHBoxLayout()
            row.setSpacing(8)
            label = QLabel(label_text, panel)
            label.setMinimumWidth(52)
            row.addWidget(label)
            row.addWidget(widget, 1)
            root.addLayout(row)

        self.font_family_combo = QComboBox(panel)
        self.font_family_combo.addItems(sorted(QFontDatabase.families()))
        self.font_family_combo.currentTextChanged.connect(self._font_family_changed)
        self.font_family_combo.setMinimumWidth(180)
        add_row("Font", self.font_family_combo)

        self.font_size_combo = QComboBox(panel)
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
        self.font_size_combo.setMinimumWidth(72)
        add_row("Size", self.font_size_combo)

        self.text_style_combo = QComboBox(panel)
        self.text_style_combo.addItem("Plain", TEXT_STYLE_PLAIN)
        self.text_style_combo.addItem("Box", TEXT_STYLE_BOX)
        self.text_style_combo.addItem("Bubble", TEXT_STYLE_BUBBLE)
        self.text_style_combo.currentIndexChanged.connect(self._text_style_changed)
        add_row("Style", self.text_style_combo)

        style_row = QHBoxLayout()
        style_row.setSpacing(6)
        style_row.addWidget(QLabel("Format", panel))
        self.text_bold_button = QToolButton(panel)
        self.text_bold_button.setText("B")
        self.text_bold_button.setCheckable(True)
        self.text_bold_button.clicked.connect(self._text_bold_toggled)
        self._configure_compact_icon_button(self.text_bold_button)
        style_row.addWidget(self.text_bold_button)
        self.text_italic_button = QToolButton(panel)
        self.text_italic_button.setText("I")
        self.text_italic_button.setCheckable(True)
        self.text_italic_button.clicked.connect(self._text_italic_toggled)
        self._configure_compact_icon_button(self.text_italic_button)
        style_row.addWidget(self.text_italic_button)
        self.text_underline_button = QToolButton(panel)
        self.text_underline_button.setText("U")
        self.text_underline_button.setCheckable(True)
        self.text_underline_button.clicked.connect(self._text_underline_toggled)
        self._configure_compact_icon_button(self.text_underline_button)
        style_row.addWidget(self.text_underline_button)
        style_row.addStretch(1)
        root.addLayout(style_row)

        self.text_letter_spacing_spin = QDoubleSpinBox(panel)
        self.text_letter_spacing_spin.setDecimals(1)
        self.text_letter_spacing_spin.setSingleStep(0.2)
        self.text_letter_spacing_spin.setRange(-4.0, 20.0)
        self.text_letter_spacing_spin.setValue(self._text_letter_spacing)
        self.text_letter_spacing_spin.valueChanged.connect(self._text_letter_spacing_changed)
        self.text_letter_spacing_spin.setEnabled(False)
        add_row("Letter", self.text_letter_spacing_spin)

        self.text_line_spacing_spin = QDoubleSpinBox(panel)
        self.text_line_spacing_spin.setDecimals(2)
        self.text_line_spacing_spin.setSingleStep(0.05)
        self.text_line_spacing_spin.setRange(0.7, 3.0)
        self.text_line_spacing_spin.setValue(self._text_line_spacing)
        self.text_line_spacing_spin.valueChanged.connect(self._text_line_spacing_changed)
        self.text_line_spacing_spin.setEnabled(False)
        add_row("Line", self.text_line_spacing_spin)

        self.text_padding_spin = QDoubleSpinBox(panel)
        self.text_padding_spin.setDecimals(1)
        self.text_padding_spin.setSingleStep(1.0)
        self.text_padding_spin.setRange(0.0, 80.0)
        self.text_padding_spin.setValue(self._text_box_padding)
        self.text_padding_spin.valueChanged.connect(self._text_padding_changed)
        self.text_padding_spin.setEnabled(False)
        add_row("Pad", self.text_padding_spin)

        self.text_radius_spin = QDoubleSpinBox(panel)
        self.text_radius_spin.setDecimals(1)
        self.text_radius_spin.setSingleStep(1.0)
        self.text_radius_spin.setRange(0.0, 80.0)
        self.text_radius_spin.setValue(self._text_corner_radius)
        self.text_radius_spin.valueChanged.connect(self._text_radius_changed)
        self.text_radius_spin.setEnabled(False)
        add_row("Radius", self.text_radius_spin)

        width_row = QHBoxLayout()
        width_row.setSpacing(8)
        width_title = QLabel("Width", panel)
        width_title.setMinimumWidth(52)
        width_title.setToolTip(
            "Border thickness for boxed/bubble text (0 = no border). "
            "Selected text keeps its own width unless Width is changed while selected."
        )
        width_row.addWidget(width_title)
        self.text_width_menu_slider = QSlider(Qt.Orientation.Horizontal, panel)
        self.text_width_menu_slider.setRange(0, 64)
        self.text_width_menu_slider.setValue(self._tool_stroke_widths.get(Tool.TEXT, 6))
        self.text_width_menu_slider.setMinimumWidth(120)
        self.text_width_menu_slider.setProperty("widthTool", Tool.TEXT)
        self.text_width_menu_slider.valueChanged.connect(self._tool_menu_width_changed)
        width_row.addWidget(self.text_width_menu_slider, 1)
        self.text_width_menu_label = QLabel(
            str(self.text_width_menu_slider.value()),
            panel,
        )
        self.text_width_menu_label.setMinimumWidth(28)
        self.text_width_menu_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_width_menu_slider.valueChanged.connect(
            lambda value: self.text_width_menu_label.setText(str(int(value)))
        )
        width_row.addWidget(self.text_width_menu_label)
        root.addLayout(width_row)

        panel_action.setDefaultWidget(panel)
        menu.addAction(panel_action)
        menu.aboutToShow.connect(self._prepare_text_tool_menu)
        button.setMenu(menu)
        self._configure_menu_tool_button(button)

    def _setup_blur_tool_option_menu(self) -> None:
        """
        Attaches a Blur toolbar popup with the pixel-block size slider.

        Returns:
            None
        """

        blur_menu = QMenu(self)
        blur_action = QWidgetAction(blur_menu)
        row = QWidget(blur_menu)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(10, 8, 10, 8)
        row_layout.setSpacing(8)
        title = QLabel("Pixel block", row)
        title.setToolTip(
            "Blur pixel block size for redaction (larger = stronger pixelation)."
        )
        row_layout.addWidget(title)
        self.blur_block_menu_slider = QSlider(Qt.Orientation.Horizontal, row)
        self.blur_block_menu_slider.setRange(4, 64)
        self.blur_block_menu_slider.setValue(self.canvas.blur_block_size())
        self.blur_block_menu_slider.setMinimumWidth(120)
        self.blur_block_menu_slider.setToolTip(
            "Blur pixel block size for redaction (larger = stronger pixelation)."
        )
        self.blur_block_menu_slider.valueChanged.connect(self._blur_block_size_changed)
        row_layout.addWidget(self.blur_block_menu_slider, 1)
        self.blur_block_menu_label = QLabel(str(self.canvas.blur_block_size()), row)
        self.blur_block_menu_label.setMinimumWidth(24)
        self.blur_block_menu_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row_layout.addWidget(self.blur_block_menu_label)
        blur_action.setDefaultWidget(row)
        blur_menu.addAction(blur_action)

        blur_button = self._tool_buttons[Tool.BLUR]
        blur_button.setMenu(blur_menu)
        self._configure_menu_tool_button(blur_button)

    def _popup_pixel_tool_options(self, tool: str) -> None:
        """
        Opens the option menu for one pixel-selection toolbar tool.

        Args:
            tool: Tool identifier.

        Returns:
            None
        """

        button = self._tool_buttons.get(tool)
        if button is None:
            return
        menu = button.menu()
        if menu is None:
            return
        menu.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def _set_tool(self, tool: str) -> None:
        """
        Sets active tool and updates button selection state.

        Tool default widths are restored into the active draw style used for
        newly drawn items. Selected annotation widths stay unchanged.

        Args:
            tool: Tool identifier.

        Returns:
            None
        """

        self._active_tool = tool
        for key, button in self._tool_buttons.items():
            button.setChecked(key == tool)
        self.canvas.set_tool(tool)
        if tool in WIDTH_AWARE_TOOLS:
            minimum = 1 if tool in BRUSH_WIDTH_TOOLS else 0
            resolved = normalize_stroke_width(
                self._tool_stroke_widths.get(tool, 6),
                minimum=minimum,
            )
            self.canvas.set_style(
                stroke_width=float(resolved),
                emit_history=False,
                apply_to_selection=False,
                update_active_style=True,
            )
        if tool in HARDNESS_AWARE_TOOLS:
            self.canvas.set_brush_hardness(
                float(self._tool_brush_hardness.get(tool, 80))
            )
        if tool in STYLE_AWARE_TOOLS:
            self.canvas.set_style(
                stroke_style=self._tool_stroke_styles.get(tool, STROKE_STYLE_SOLID),
                emit_history=False,
                apply_to_selection=False,
                update_active_style=True,
            )
        self._focus_property_tab_for_context(tool=tool)
        self.statusBar().showMessage(f"Tool: {tool}")

    def apply_tool_stroke_widths(
        self,
        widths: dict[str, int] | None,
        *,
        emit_signal: bool = False,
    ) -> None:
        """
        Restores persisted per-tool stroke widths.

        Args:
            widths: Tool id → width mapping.
            emit_signal: When True, notifies the host to persist again.

        Returns:
            None
        """

        self._tool_stroke_widths = normalize_tool_stroke_widths(widths)
        for tool_key, slider in self._tool_width_sliders.items():
            resolved = self._tool_stroke_widths.get(tool_key, 6)
            if slider.value() != resolved:
                slider.blockSignals(True)
                slider.setValue(resolved)
                slider.blockSignals(False)
        if hasattr(self, "text_width_menu_slider"):
            text_width = self._tool_stroke_widths.get(Tool.TEXT, 2)
            if self.text_width_menu_slider.value() != text_width:
                self.text_width_menu_slider.blockSignals(True)
                self.text_width_menu_slider.setValue(text_width)
                self.text_width_menu_slider.blockSignals(False)
        if self._active_tool in WIDTH_AWARE_TOOLS:
            self._apply_tool_stroke_width(
                self._tool_stroke_widths[self._active_tool],
                tool=self._active_tool,
                persist=False,
            )
        if emit_signal:
            self.tool_stroke_widths_changed.emit(dict(self._tool_stroke_widths))

    def apply_tool_brush_hardness(
        self,
        hardness: dict[str, int] | None,
        *,
        emit_signal: bool = False,
    ) -> None:
        """
        Restores persisted per-tool brush/eraser hardness.

        Args:
            hardness: Tool id → hardness mapping.
            emit_signal: When True, notifies the host to persist again.

        Returns:
            None
        """

        self._tool_brush_hardness = normalize_tool_brush_hardness(hardness)
        for tool_key, slider in self._tool_hardness_sliders.items():
            resolved = self._tool_brush_hardness.get(tool_key, 80)
            if slider.value() != resolved:
                slider.blockSignals(True)
                slider.setValue(resolved)
                slider.blockSignals(False)
        if self._active_tool in HARDNESS_AWARE_TOOLS:
            self._apply_tool_brush_hardness(
                self._tool_brush_hardness[self._active_tool],
                tool=self._active_tool,
                persist=False,
            )
        if emit_signal:
            self.tool_brush_hardness_changed.emit(dict(self._tool_brush_hardness))

    def apply_tool_stroke_styles(
        self,
        styles: dict[str, str] | None,
        *,
        emit_signal: bool = False,
    ) -> None:
        """
        Restores persisted per-tool stroke styles.

        Args:
            styles: Tool id → stroke style mapping.
            emit_signal: When True, notifies the host to persist again.

        Returns:
            None
        """

        self._tool_stroke_styles = normalize_tool_stroke_styles(styles)
        for tool_key, combo in self._tool_style_combos.items():
            resolved = self._tool_stroke_styles.get(tool_key, STROKE_STYLE_SOLID)
            index = combo.findData(resolved)
            if index >= 0 and combo.currentIndex() != index:
                combo.blockSignals(True)
                combo.setCurrentIndex(index)
                combo.blockSignals(False)
        if self._active_tool in STYLE_AWARE_TOOLS:
            self._apply_tool_stroke_style(
                self._tool_stroke_styles[self._active_tool],
                tool=self._active_tool,
                persist=False,
            )
        if emit_signal:
            self.tool_stroke_styles_changed.emit(dict(self._tool_stroke_styles))

    def _apply_tool_stroke_width(
        self,
        width: int,
        *,
        tool: str | None = None,
        persist: bool = True,
    ) -> None:
        """
        Updates stroke width for the current selection or a tool default.

        With a stroke-capable selection the width is written only to those
        elements. Without a selection it updates the tool default used for
        newly drawn items (``0`` disables shape/text borders).

        Args:
            width: Stroke width in pixels.
            tool: Tool to store the width for; defaults to the active tool.
            persist: Whether to emit the persistence signal.

        Returns:
            None
        """

        target_tool = tool if tool in WIDTH_AWARE_TOOLS else self._active_tool
        minimum = 1 if target_tool in BRUSH_WIDTH_TOOLS else 0
        resolved = normalize_stroke_width(width, minimum=minimum)

        # Brush/eraser menus always edit tool defaults. Shape/line/text menus edit
        # the current selection when one exists.
        if (
            target_tool not in BRUSH_WIDTH_TOOLS
            and self.canvas.has_stroke_width_selection()
        ):
            self.canvas.set_style(
                stroke_width=float(resolved),
                emit_history=False,
                apply_to_selection=True,
                update_active_style=False,
            )
            self._set_next_history_label("Change border width")
            self._push_history_state()
            return

        if target_tool in WIDTH_AWARE_TOOLS:
            self._tool_stroke_widths[target_tool] = resolved
            slider = self._tool_width_sliders.get(target_tool)
            if slider is not None and slider.value() != resolved:
                slider.blockSignals(True)
                slider.setValue(resolved)
                slider.blockSignals(False)
        if target_tool == self._active_tool or tool is None:
            self.canvas.set_style(
                stroke_width=float(resolved),
                emit_history=False,
                apply_to_selection=False,
                update_active_style=True,
            )
        if persist:
            self.tool_stroke_widths_changed.emit(dict(self._tool_stroke_widths))

    def _apply_tool_brush_hardness(
        self,
        hardness: int,
        *,
        tool: str | None = None,
        persist: bool = True,
    ) -> None:
        """
        Updates brush/eraser hardness for one tool default.

        Args:
            hardness: Hardness percentage from 0 to 100.
            tool: Tool to store the hardness for; defaults to the active tool.
            persist: Whether to emit the persistence signal.

        Returns:
            None
        """

        target_tool = tool if tool in HARDNESS_AWARE_TOOLS else self._active_tool
        resolved = normalize_brush_hardness(hardness)
        if target_tool in HARDNESS_AWARE_TOOLS:
            self._tool_brush_hardness[target_tool] = resolved
            slider = self._tool_hardness_sliders.get(target_tool)
            if slider is not None and slider.value() != resolved:
                slider.blockSignals(True)
                slider.setValue(resolved)
                slider.blockSignals(False)
        if target_tool == self._active_tool or tool is None:
            if target_tool in HARDNESS_AWARE_TOOLS:
                self.canvas.set_brush_hardness(float(resolved))
        if persist:
            self.tool_brush_hardness_changed.emit(dict(self._tool_brush_hardness))

    def _apply_tool_stroke_style(
        self,
        stroke_style: str,
        *,
        tool: str | None = None,
        persist: bool = True,
    ) -> None:
        """
        Updates stroke style for the current selection or a tool default.

        Args:
            stroke_style: Named stroke style.
            tool: Tool to store the style for; defaults to the active tool.
            persist: Whether to emit the persistence signal.

        Returns:
            None
        """

        target_tool = tool if tool in STYLE_AWARE_TOOLS else self._active_tool
        resolved = normalize_named_stroke_style(stroke_style)

        if self.canvas.has_stroke_style_selection():
            self.canvas.set_style(
                stroke_style=resolved,
                emit_history=False,
                apply_to_selection=True,
                update_active_style=False,
            )
            self._set_next_history_label("Change line style")
            self._push_history_state()
            return

        if target_tool in STYLE_AWARE_TOOLS:
            self._tool_stroke_styles[target_tool] = resolved
            combo = self._tool_style_combos.get(target_tool)
            if combo is not None:
                index = combo.findData(resolved)
                if index >= 0 and combo.currentIndex() != index:
                    combo.blockSignals(True)
                    combo.setCurrentIndex(index)
                    combo.blockSignals(False)
        if target_tool == self._active_tool or tool is None:
            self.canvas.set_style(
                stroke_style=resolved,
                emit_history=False,
                apply_to_selection=False,
                update_active_style=True,
            )
        if persist:
            self.tool_stroke_styles_changed.emit(dict(self._tool_stroke_styles))

    def eventFilter(self, watched, event) -> bool:
        """
        Handles double-click locking for drawing tool buttons and property-tab reflow.

        Args:
            watched: Watched QObject.
            event: Incoming Qt event.

        Returns:
            bool: True when handled.
        """

        if watched is getattr(self, "_property_tabs", None) and event.type() == QEvent.Type.Resize:
            self._fit_property_tabs_height()
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
            Tool.TRIANGLE,
            Tool.STAR,
            Tool.POLYGON,
            Tool.LINE,
            Tool.POLYLINE,
            Tool.ARROW,
            Tool.DOUBLE_ARROW,
            Tool.BENT_ARROW,
            Tool.SPOTLIGHT,
            Tool.CROSS,
            Tool.CHECKMARK,
            Tool.TEXT,
            Tool.CALLOUT,
            Tool.FILL_BG,
            Tool.BLUR,
            Tool.STEP,
            Tool.OCR,
            Tool.BRUSH,
            Tool.ERASER,
            Tool.BUCKET,
            Tool.EYEDROPPER,
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

        already_active = self._active_tool == tool
        if (
            tool == Tool.CROP
            and already_active
            and self.canvas.has_pending_crop()
        ):
            self.canvas.apply_pending_crop()
            return

        self._set_tool(tool)
        self._one_shot_tool = tool if self._is_lockable_tool(tool) else None
        # Re-clicking an active option tool opens its popup immediately.
        if already_active and tool in {
            Tool.SELECT_RECT,
            Tool.SELECT_ELLIPSE,
            Tool.SELECT_PATH,
            Tool.MAGIC_WAND,
            Tool.BLUR,
            Tool.BRUSH,
            Tool.ERASER,
            Tool.RECT,
            Tool.ELLIPSE,
            Tool.LINE,
            Tool.ARROW,
            Tool.TEXT,
        }:
            self._popup_pixel_tool_options(tool)

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
        Updates tool button icons to show a lock badge when locked.

        Returns:
            None
        """

        for tool_key in self._tool_button_order:
            button = self._tool_buttons[tool_key]
            locked = tool_key == self._locked_tool
            button.setIcon(self._build_tool_icon(tool_key, locked=locked))
            base_tip = self._tool_tooltip_text(tool_key)
            if locked:
                button.setToolTip(f"{base_tip} Currently locked – double-click to unlock.")
            else:
                button.setToolTip(base_tip)

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

    def _set_target_color(
        self,
        target: str,
        color: QColor,
        apply_to_canvas: bool = True,
        *,
        emit_history: bool = True,
    ) -> None:
        """
        Applies one target color to canvas and toolbar state.

        Args:
            target: Style target key (stroke, fill, text).
            color: New target color.
            apply_to_canvas: True to apply style changes to selected canvas items.
            emit_history: When False, skips canvas history emission for live previews.

        Returns:
            None
        """

        if target == "stroke":
            self._eyedropper_color_target = "stroke"
            self.canvas.set_eyedropper_target("stroke")
            self._current_stroke_color = QColor(color)
            if apply_to_canvas:
                self.canvas.set_style(stroke_color=color, emit_history=emit_history)
            self._update_color_button_preview(self.stroke_button, color)
            self._set_alpha_slider_value(self.stroke_alpha_slider, self.stroke_alpha_label, color)
            return
        if target == "fill":
            self._eyedropper_color_target = "fill"
            self.canvas.set_eyedropper_target("fill")
            self._current_fill_color = QColor(color)
            if apply_to_canvas:
                self.canvas.set_style(fill_color=color, emit_history=emit_history)
            self._update_color_button_preview(self.fill_button, color)
            self._set_alpha_slider_value(self.fill_alpha_slider, self.fill_alpha_label, color)
            return
        self._current_text_color = QColor(color)
        if apply_to_canvas:
            self.canvas.set_style(text_color=color, emit_history=emit_history)
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
        for action in (
            self.theme_dark_action,
            self.theme_light_action,
            self.theme_slate_action,
            self.theme_sepia_action,
        ):
            action.blockSignals(True)
        self.theme_dark_action.setChecked(normalized == THEME_DARK)
        self.theme_light_action.setChecked(normalized == THEME_LIGHT)
        self.theme_slate_action.setChecked(normalized == THEME_SLATE)
        self.theme_sepia_action.setChecked(normalized == THEME_SEPIA)
        for action in (
            self.theme_dark_action,
            self.theme_light_action,
            self.theme_slate_action,
            self.theme_sepia_action,
        ):
            action.blockSignals(False)

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

    def _blur_block_size_changed(self, value: int) -> None:
        """
        Updates blur block size for the blur tool.

        Args:
            value: Pixel block size.

        Returns:
            None
        """

        resolved = max(4, min(64, int(value)))
        self.canvas.set_blur_block_size(resolved)
        if self.blur_block_menu_slider.value() != resolved:
            self.blur_block_menu_slider.blockSignals(True)
            self.blur_block_menu_slider.setValue(resolved)
            self.blur_block_menu_slider.blockSignals(False)
        self.blur_block_menu_label.setText(str(resolved))

    def _wand_tolerance_changed(self, value: int) -> None:
        """
        Updates magic wand color tolerance.

        Args:
            value: Channel tolerance (0-255).

        Returns:
            None
        """

        resolved = max(0, min(255, int(value)))
        self.canvas.set_wand_tolerance(resolved)
        if self.wand_tolerance_slider.value() != resolved:
            self.wand_tolerance_slider.blockSignals(True)
            self.wand_tolerance_slider.setValue(resolved)
            self.wand_tolerance_slider.blockSignals(False)
        self.wand_tolerance_label.setText(str(resolved))

    def _wand_contiguous_changed(self, checked: bool) -> None:
        """
        Updates magic wand contiguous matching mode.

        Args:
            checked: True for connected pixels only.

        Returns:
            None
        """

        self.canvas.set_wand_contiguous(checked)
        if self.wand_contiguous_action.isChecked() != checked:
            self.wand_contiguous_action.blockSignals(True)
            self.wand_contiguous_action.setChecked(checked)
            self.wand_contiguous_action.blockSignals(False)

    def _erase_mode_action_changed(self) -> None:
        """
        Applies Delete-key erase mode from the toolbar popup actions.

        Returns:
            None
        """

        if self.erase_fill_action.isChecked():
            self.canvas.set_erase_mode(ERASE_MODE_FILL)
        else:
            self.canvas.set_erase_mode(ERASE_MODE_TRANSPARENT)

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
        self._apply_text_menu_style("Change text style", text_style=text_style)

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

        self._apply_target_alpha("stroke", value, emit_history=False)
        if not self.stroke_alpha_slider.isSliderDown():
            self._set_next_history_label("Change border opacity")
            self._push_history_state()

    def _stroke_alpha_committed(self) -> None:
        """
        Records border opacity history after a slider drag completes.

        Returns:
            None
        """

        self._set_next_history_label("Change border opacity")
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

    def _apply_target_alpha(
        self,
        target: str,
        value: int,
        *,
        emit_history: bool = True,
    ) -> None:
        """
        Applies alpha percentage to current target color.

        Args:
            target: Style target key.
            value: Opacity percentage from 0 to 100.
            emit_history: When False, skips canvas history emission.

        Returns:
            None
        """

        alpha_value = max(0, min(255, round((value / 100.0) * 255)))
        color = self._color_for_target(target)
        color.setAlpha(alpha_value)
        self._set_target_color(target, color, emit_history=emit_history)

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
        Updates selected text font size or the Text-tool default.

        Args:
            value: New font size in points as text.

        Returns:
            None
        """

        if not value.isdigit():
            return
        size = int(value)
        if not self.canvas.has_text_selection():
            # Keep combo/default in sync for newly inserted text.
            pass
        self._apply_text_menu_style("Change font size", font_size=size)

    def _font_family_changed(self, value: str) -> None:
        """
        Updates selected text font family or the Text-tool default.

        Args:
            value: New font family name.

        Returns:
            None
        """

        self._apply_text_menu_style("Change font family", font_family=value)

    def _text_bold_toggled(self, checked: bool) -> None:
        """
        Updates selected text bold style or the Text-tool default.

        Args:
            checked: True when bold is enabled.

        Returns:
            None
        """

        if not self.canvas.has_text_selection():
            self._text_bold_enabled = bool(checked)
        self._apply_text_menu_style("Toggle bold text", font_bold=bool(checked))

    def _text_italic_toggled(self, checked: bool) -> None:
        """
        Updates selected text italic style or the Text-tool default.

        Args:
            checked: True when italic is enabled.

        Returns:
            None
        """

        if not self.canvas.has_text_selection():
            self._text_italic_enabled = bool(checked)
        self._apply_text_menu_style("Toggle italic text", font_italic=bool(checked))

    def _text_underline_toggled(self, checked: bool) -> None:
        """
        Updates selected text underline style or the Text-tool default.

        Args:
            checked: True when underline is enabled.

        Returns:
            None
        """

        if not self.canvas.has_text_selection():
            self._text_underline_enabled = bool(checked)
        self._apply_text_menu_style(
            "Toggle underline text",
            font_underline=bool(checked),
        )

    def _text_letter_spacing_changed(self, value: float) -> None:
        """
        Updates selected text letter spacing or the Text-tool default.

        Args:
            value: Letter spacing in pixels.

        Returns:
            None
        """

        if not self.canvas.has_text_selection():
            self._text_letter_spacing = float(value)
        self._apply_text_menu_style(
            "Change letter spacing",
            letter_spacing=float(value),
        )

    def _text_line_spacing_changed(self, value: float) -> None:
        """
        Updates selected text line spacing or the Text-tool default.

        Args:
            value: Line spacing multiplier.

        Returns:
            None
        """

        if not self.canvas.has_text_selection():
            self._text_line_spacing = float(value)
        self._apply_text_menu_style(
            "Change line spacing",
            line_spacing_factor=float(value),
        )

    def _text_padding_changed(self, value: float) -> None:
        """
        Updates selected text box padding or the Text-tool default.

        Args:
            value: Inner box padding in pixels.

        Returns:
            None
        """

        if not self.canvas.has_text_selection():
            self._text_box_padding = float(value)
        self._apply_text_menu_style(
            "Change text box padding",
            box_padding=float(value),
        )

    def _text_radius_changed(self, value: float) -> None:
        """
        Updates selected text box corner radius or the Text-tool default.

        Args:
            value: Corner radius in pixels.

        Returns:
            None
        """

        if not self.canvas.has_text_selection():
            self._text_corner_radius = float(value)
        self._apply_text_menu_style(
            "Change text box radius",
            corner_radius=float(value),
        )

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
        self._apply_one_shot_tool_completion(action_label)
        self._show_canvas_action_notification(action_label)

    def _on_canvas_status_message(self, message: str) -> None:
        """
        Shows a canvas status message in the footer status bar.

        OCR results are also written to the permanent selection-info label so
        the recognized text remains visible after tool switches.

        Args:
            message: Status text from the canvas.

        Returns:
            None
        """

        timeout_ms = 8000 if message.startswith("OCR") else 4500
        self.statusBar().showMessage(message, timeout_ms)
        if message.startswith("OCR"):
            self._selection_info_label.setText(message)

    def _show_canvas_action_notification(self, action_label: str) -> None:
        """
        Shows user-facing notifications for important canvas actions.

        Args:
            action_label: Last canvas action label.

        Returns:
            None
        """

        message_by_action = {
            "Copy OCR text": format_ocr_copied_status(self.canvas.last_ocr_copied_text()),
            "OCR found no text": "OCR completed, but no text was found.",
            "OCR unavailable: install tesseract-ocr": "OCR unavailable. Please install tesseract-ocr.",
        }
        message = message_by_action.get(action_label)
        if message is None:
            return
        self._on_canvas_status_message(message)

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
            Tool.TRIANGLE: "Draw triangle",
            Tool.STAR: "Draw star",
            Tool.POLYGON: "Draw polygon",
            Tool.LINE: "Draw line",
            Tool.POLYLINE: "Draw polyline",
            Tool.ARROW: "Draw arrow",
            Tool.DOUBLE_ARROW: "Draw double arrow",
            Tool.BENT_ARROW: "Draw bent arrow",
            Tool.SPOTLIGHT: "Draw spotlight",
            Tool.CROSS: "Draw cross",
            Tool.CHECKMARK: "Draw checkmark",
            Tool.TEXT: "Insert text",
            Tool.CALLOUT: "Insert callout",
            Tool.FILL_BG: "Fill background",
            Tool.BLUR: "Blur region",
            Tool.STEP: "Insert step",
            Tool.OCR: "Copy OCR text",
            Tool.BRUSH: "Brush stroke",
            Tool.ERASER: "Eraser stroke",
            Tool.BUCKET: "Fill selection",
            Tool.EYEDROPPER: {
                "Change border color",
                "Change fill color",
            },
        }
        expected = expected_action_by_tool.get(self._one_shot_tool)
        if expected is None:
            return
        if isinstance(expected, set):
            if action_label not in expected:
                return
        elif action_label != expected:
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
        if selection_type == "document" or not selection_type:
            self._restore_stroke_tool_menu_widgets()
            self._restore_text_tool_menu_widgets()
            self._update_style_color_visibility(selection_type="document")
            self._selection_info_label.setText(format_selection_info(payload))
            return

        self._focus_property_tab_for_context(selection_type=selection_type)

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

        if selection_type in {"rect", "ellipse", "triangle", "round_rect", "star", "highlight", "spotlight", "cross", "checkmark", "line", "arrow", "double_arrow", "polyline", "polygon", "bent_arrow"}:
            self._sync_stroke_tool_menu_widgets(payload)
        elif selection_type == "text":
            self._sync_text_tool_menu_widgets(payload)
        else:
            self._restore_stroke_tool_menu_widgets()
            self._restore_text_tool_menu_widgets()

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

    def _align_selection(self, mode: str) -> None:
        """
        Aligns the current multi-selection.

        Args:
            mode: Align mode identifier.

        Returns:
            None
        """

        if self.canvas.align_selected(mode):
            self._push_history_state()
            self._refresh_layer_panel()

    def _distribute_selection(self, axis: str) -> None:
        """
        Distributes the current multi-selection.

        Args:
            axis: ``horizontal`` or ``vertical``.

        Returns:
            None
        """

        if self.canvas.distribute_selected(axis):
            self._push_history_state()
            self._refresh_layer_panel()

    def _rotate_selection(self, degrees: float) -> None:
        """
        Rotates the selection by a relative angle.

        Args:
            degrees: Rotation delta in degrees.

        Returns:
            None
        """

        if self.canvas.transform_selected(rotate_delta=float(degrees)):
            self._push_history_state()
            self._refresh_layer_panel()

    def _apply_rotation_spin(self) -> None:
        """
        Applies absolute rotation from the Arrange spin box.

        Returns:
            None
        """

        if self.canvas.transform_selected(rotation=float(self.rotation_spin.value())):
            self._push_history_state()
            self._refresh_layer_panel()

    def _flip_selection(self, *, horizontal: bool = False, vertical: bool = False) -> None:
        """
        Mirrors the current selection.

        Args:
            horizontal: Flip horizontally when True.
            vertical: Flip vertically when True.

        Returns:
            None
        """

        if self.canvas.flip_selected(horizontal=horizontal, vertical=vertical):
            self._push_history_state()
            self._refresh_layer_panel()

    def _apply_skew_spins(self) -> None:
        """
        Applies skew angles from the Arrange spin boxes.

        Returns:
            None
        """

        if self.canvas.transform_selected(
            skew_x=float(self.skew_x_spin.value()),
            skew_y=float(self.skew_y_spin.value()),
        ):
            self._push_history_state()
            self._refresh_layer_panel()

    def _set_eyedropper_target(self, target: str) -> None:
        """
        Sets whether the color picker writes border or fill color.

        Args:
            target: ``stroke`` or ``fill``.

        Returns:
            None
        """

        resolved = "fill" if str(target).strip().lower() == "fill" else "stroke"
        self._eyedropper_color_target = resolved
        self.canvas.set_eyedropper_target(resolved)
        if resolved == "fill":
            self.eyedropper_fill_action.setChecked(True)
        else:
            self.eyedropper_stroke_action.setChecked(True)

    def _on_export_scale_changed(self, _index: int) -> None:
        """
        Updates the preferred export scale factor.

        Args:
            _index: Combo index (unused).

        Returns:
            None
        """

        scale = self.export_scale_combo.currentData()
        self._export_scale = float(scale) if isinstance(scale, (int, float)) else 1.0
        self.export_scale_changed.emit(float(self._export_scale))

    def _on_export_keep_transparency_toggled(self, checked: bool) -> None:
        """
        Updates whether exports preserve alpha.

        Args:
            checked: True to keep transparency.

        Returns:
            None
        """

        self._export_keep_transparency = bool(checked)
        self.export_keep_transparency_changed.emit(bool(checked))

    def export_scale(self) -> float:
        """
        Returns the active export scale factor.

        Returns:
            float: Scale multiplier.
        """

        return float(self._export_scale)

    def set_export_scale(self, scale: float) -> None:
        """
        Applies an export scale preference to the Export tab.

        Args:
            scale: Desired scale (1, 2, or 3).

        Returns:
            None
        """

        resolved = float(scale)
        if abs(resolved - 3.0) < 0.001:
            resolved = 3.0
        elif abs(resolved - 2.0) < 0.001:
            resolved = 2.0
        else:
            resolved = 1.0
        self._export_scale = resolved
        if hasattr(self, "export_scale_combo"):
            index = self.export_scale_combo.findData(resolved)
            if index >= 0:
                self.export_scale_combo.blockSignals(True)
                self.export_scale_combo.setCurrentIndex(index)
                self.export_scale_combo.blockSignals(False)

    def export_keep_transparency(self) -> bool:
        """
        Returns whether exports preserve transparency.

        Returns:
            bool: Transparency preference.
        """

        return bool(self._export_keep_transparency)

    def set_export_keep_transparency(self, keep: bool) -> None:
        """
        Applies the export transparency preference.

        Args:
            keep: True to preserve alpha.

        Returns:
            None
        """

        self._export_keep_transparency = bool(keep)
        if hasattr(self, "export_keep_transparency_check"):
            self.export_keep_transparency_check.blockSignals(True)
            self.export_keep_transparency_check.setChecked(bool(keep))
            self.export_keep_transparency_check.blockSignals(False)

    def _export_output_pixmap(self, *, for_jpeg: bool = False) -> QPixmap:
        """
        Builds a composited export pixmap using Export-tab preferences.

        Args:
            for_jpeg: True when the target format cannot store alpha.

        Returns:
            QPixmap: Scaled composited image.
        """

        keep_alpha = bool(self._export_keep_transparency) and not for_jpeg
        background = None if keep_alpha else QColor(255, 255, 255, 255)
        return self.canvas.export_composited_pixmap(
            scale=float(self._export_scale),
            background=background,
        )

    def _on_crop_state_changed(self, is_active: bool) -> None:
        """
        Shows guidance when a crop selection becomes available.

        Args:
            is_active: True when crop selection exists.

        Returns:
            None
        """

        if is_active:
            self.statusBar().showMessage(
                "Crop ready — press Enter or click Crop again to apply.",
                5000,
            )

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
        pixmap = self._export_output_pixmap(for_jpeg=(fmt == "JPG"))
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
        Opens one unified export dialog for PNG, JPG, PDF, and SVG.

        Returns:
            None
        """

        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export",
            "",
            "PNG Files (*.png);;JPEG Files (*.jpg *.jpeg);;PDF Files (*.pdf);;SVG Files (*.svg)",
        )
        if not file_path:
            return

        if "PNG" in selected_filter:
            if not file_path.lower().endswith(".png"):
                file_path = f"{file_path}.png"
            self._export_output_pixmap(for_jpeg=False).save(file_path, "PNG")
            self.statusBar().showMessage("Exported PNG")
            return

        if "JPEG" in selected_filter:
            if not file_path.lower().endswith((".jpg", ".jpeg")):
                file_path = f"{file_path}.jpg"
            quality = self._ask_jpeg_quality(self._jpeg_quality)
            if quality is None:
                return
            self._jpeg_quality = quality
            self._export_output_pixmap(for_jpeg=True).save(file_path, "JPG", quality)
            self.statusBar().showMessage("Exported JPG")
            return

        if "SVG" in selected_filter or file_path.lower().endswith(".svg"):
            if not file_path.lower().endswith(".svg"):
                file_path = f"{file_path}.svg"
            if self._write_svg_to_path(file_path):
                self.statusBar().showMessage("Exported SVG")
            else:
                QMessageBox.warning(self, APP_NAME, "SVG export failed.")
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

    def export_svg(self) -> None:
        """
        Exports the composited screenshot as a standard SVG file.

        Returns:
            None
        """

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export as SVG",
            "",
            "SVG Files (*.svg);;All Files (*)",
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".svg"):
            file_path = f"{file_path}.svg"
        if self._write_svg_to_path(file_path):
            self.statusBar().showMessage("Exported SVG")
            return
        QMessageBox.warning(self, APP_NAME, "SVG export failed.")

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

        pixmap = self._export_output_pixmap(for_jpeg=False)
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

    def _write_svg_to_path(self, file_path: str) -> bool:
        """
        Writes the current composited image as a standard SVG file.

        Args:
            file_path: SVG output path.

        Returns:
            bool: True when the SVG file was written.
        """

        from src.image_export import write_pixmap_as_svg

        pixmap = self._export_output_pixmap(for_jpeg=False)
        return write_pixmap_as_svg(pixmap, file_path)

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
                if str(value).strip().lower() in {"png", "jpg", "pdf", "svg"}
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
        include_svg = bool(export_options["include_svg"])
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
                        ("svg", include_svg),
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
        pixmap_png = self._export_output_pixmap(for_jpeg=False)
        pixmap_jpg = self._export_output_pixmap(for_jpeg=True)
        if pixmap_png.isNull():
            QMessageBox.warning(self, APP_NAME, "Could not render image for batch export.")
            return

        queue: list[tuple[str, Path]] = []
        if include_png:
            queue.append(("png", target_root / f"{normalized_base}.png"))
        if include_jpg:
            queue.append(("jpg", target_root / f"{normalized_base}.jpg"))
        if include_pdf:
            queue.append(("pdf", target_root / f"{normalized_base}.pdf"))
        if include_svg:
            queue.append(("svg", target_root / f"{normalized_base}.svg"))

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
                if pixmap_png.save(str(target), "PNG"):
                    saved_targets.append(str(target))
            elif fmt == "jpg":
                if pixmap_jpg.save(str(target), "JPG", max(1, min(100, self._jpeg_quality))):
                    saved_targets.append(str(target))
            elif fmt == "svg":
                if self._write_svg_to_path(str(target)):
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
        svg_check = QCheckBox("SVG")
        svg_check.setChecked("svg" in list(current_profile.get("formats", [])))
        layout.addWidget(png_check)
        layout.addWidget(jpg_check)
        layout.addWidget(pdf_check)
        layout.addWidget(svg_check)

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
            svg_check.setChecked("svg" in selected_formats)
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
        include_svg = bool(svg_check.isChecked())
        if not any((include_png, include_jpg, include_pdf, include_svg)):
            QMessageBox.warning(self, APP_NAME, "Select at least one format.")
            return None
        selected_profile_key = str(profile_combo.currentData() or current_profile["key"])
        return {
            "include_png": include_png,
            "include_jpg": include_jpg,
            "include_pdf": include_pdf,
            "include_svg": include_svg,
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
        pixmap = self._export_output_pixmap(for_jpeg=False)
        rect = painter.viewport()
        scaled = pixmap.scaled(rect.size(), Qt.AspectRatioMode.KeepAspectRatio)
        painter.drawPixmap(0, 0, scaled)
        painter.end()

    def copy_current_image_to_clipboard(self) -> None:
        """
        Copies selected annotations or the full drawing area to the clipboard.

        Returns:
            None
        """

        if self.canvas.has_selected_annotations():
            self.copy_selected_annotations_to_clipboard()
            return

        mime_data = self._build_canvas_clipboard_mime_data()
        QGuiApplication.clipboard().setMimeData(mime_data)
        self._show_drawing_area_copied_feedback()

    def copy_selected_annotations_to_clipboard(self) -> bool:
        """
        Copies currently selected annotations for cross-tab paste.

        Returns:
            bool: True when a selection payload was copied.
        """

        annotations = self.canvas.collect_selected_annotations()
        if not annotations:
            return False

        payload = {
            "kind": "annotations",
            "annotations": [annotation.to_dict() for annotation in annotations],
        }
        encoded = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        mime_data = QMimeData()
        mime_data.setData(_ANNOTATIONS_CLIPBOARD_MIME, encoded)
        # Keep canvas MIME compatibility for older paste paths when useful.
        mime_data.setData(
            _CANVAS_CLIPBOARD_MIME,
            json.dumps(
                {
                    "kind": "annotations",
                    "screenshot_png_base64": "",
                    "annotations": payload["annotations"],
                },
                ensure_ascii=True,
            ).encode("utf-8"),
        )
        QGuiApplication.clipboard().setMimeData(mime_data)

        bounds = self.canvas.selected_annotations_bounds()
        self.canvas.flash_copy_feedback(bounds)
        count = len(annotations)
        label = "annotation" if count == 1 else "annotations"
        self.statusBar().showMessage(f"Copied {count} {label}", 3500)
        return True

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
            "kind": "canvas",
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

    def paste_selected_annotations_from_clipboard(self) -> bool:
        """
        Pastes copied annotation selection into this tab.

        Returns:
            bool: True when a selection payload was pasted.
        """

        clipboard = QGuiApplication.clipboard()
        mime_data = clipboard.mimeData()
        if mime_data is None:
            return False

        annotations_data: list[Any] | None = None
        if mime_data.hasFormat(_ANNOTATIONS_CLIPBOARD_MIME):
            raw_data = bytes(mime_data.data(_ANNOTATIONS_CLIPBOARD_MIME))
            try:
                payload = json.loads(raw_data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return False
            candidate = payload.get("annotations")
            if isinstance(candidate, list):
                annotations_data = candidate
        elif mime_data.hasFormat(_CANVAS_CLIPBOARD_MIME):
            raw_data = bytes(mime_data.data(_CANVAS_CLIPBOARD_MIME))
            try:
                payload = json.loads(raw_data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return False
            if str(payload.get("kind") or "") != "annotations":
                return False
            candidate = payload.get("annotations")
            if isinstance(candidate, list):
                annotations_data = candidate

        if not isinstance(annotations_data, list):
            return False

        annotations = [
            AnnotationModel.from_dict(item)
            for item in annotations_data
            if isinstance(item, dict)
        ]
        if not annotations:
            return False
        if not self.canvas.merge_annotations_payload(annotations):
            return False
        self._refresh_layer_panel()
        count = len(annotations)
        label = "annotation" if count == 1 else "annotations"
        self.statusBar().showMessage(f"Pasted {count} {label}", 2500)
        return True

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
        if str(payload.get("kind") or "canvas") == "annotations":
            return False
        screenshot_data = payload.get("screenshot_png_base64")
        annotations_data = payload.get("annotations")
        if not isinstance(screenshot_data, str) or not isinstance(annotations_data, list):
            return False
        if not screenshot_data:
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
        Pastes clipboard content, preferring Snappix selection then drawing area.

        Returns:
            None
        """

        if self.paste_selected_annotations_from_clipboard():
            return
        if self.paste_drawing_area_from_clipboard():
            return
        self.canvas.paste_from_clipboard()

    def show_about(self) -> None:
        """
        Displays About dialog information with clickable website links.

        Returns:
            None
        """

        box = QMessageBox(self)
        box.setWindowTitle(f"About {APP_NAME}")
        box.setIcon(QMessageBox.Icon.Information)
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(build_about_dialog_html())
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        # QMessageBox labels do not open links unless explicitly enabled.
        colors = get_theme_colors()
        for label in box.findChildren(QLabel):
            label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextBrowserInteraction
            )
            label.setOpenExternalLinks(True)
            label.setStyleSheet(
                f"QLabel {{ color: {colors.text}; }}"
                f"QLabel a {{ color: {colors.link}; text-decoration: underline; }}"
            )
        box.exec()

    def show_manual(self) -> None:
        """
        Displays a short manual and the currently configured shortcuts.

        Returns:
            None
        """

        dialog = QDialog(self)
        dialog.setWindowTitle("Manual")
        dialog.setModal(True)
        dialog.resize(720, 560)
        dialog.setMinimumSize(640, 420)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        text = QPlainTextEdit(dialog)
        text.setReadOnly(True)
        text.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        text.setPlainText(
            "How it works:\n"
            "1) Use the capture panel to create a screenshot.\n"
            "2) Annotate with tools in the top bar.\n"
            "3) Save project, export image, or print from File menu.\n\n"
            "Open the ? toolbar button for icon explanations.\n\n"
            + build_shortcuts_reference_text(self._editor_shortcut_overrides)
        )
        text.setUndoRedoEnabled(False)
        text.moveCursor(QTextCursor.MoveOperation.Start)
        layout.addWidget(text, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dialog)
        close_button = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_button is not None:
            close_button.clicked.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        dialog.exec()

    def show_tools_reference(self) -> None:
        """
        Displays the tools reference table with icons and explanations.

        Returns:
            None
        """

        dialog = ToolReferenceDialog(self, self._build_tool_icon)
        dialog.exec()

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
        if getattr(self, "_autosave_flushing", False):
            return

        from shiboken6 import isValid

        if not isValid(self):
            return
        canvas = getattr(self, "canvas", None)
        if canvas is None or not isValid(canvas):
            return

        from src.session_recovery import ensure_tab_recovery_path

        self._autosave_flushing = True
        try:
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
        except RuntimeError:
            # Shiboken raises when underlying Qt objects were already deleted.
            return
        finally:
            self._autosave_flushing = False

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
        autosave_timer = getattr(self, "_autosave_timer", 0)
        if autosave_timer:
            self.killTimer(autosave_timer)
            self._autosave_timer = 0
        super().closeEvent(event)

