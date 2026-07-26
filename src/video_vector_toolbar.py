"""
Vector drawing toolbar for the Snappix video editor (mirrors image editor UX).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSlider,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from src.config import (
    STYLE_AWARE_TOOLS,
    WIDTH_AWARE_TOOLS,
    normalize_stroke_width,
    normalize_tool_stroke_styles,
    normalize_tool_stroke_widths,
)
from src.annotation_items import (
    STROKE_STYLE_DASH,
    STROKE_STYLE_DASH_DOT,
    STROKE_STYLE_DOT,
    STROKE_STYLE_SOLID,
)
from src.editor_canvas import Tool
from src.flow_layout import FlowLayoutWidget
from src.theme import color_preview_button_stylesheet, palette_button_stylesheet
from src.tool_icons import build_tool_icon
from src.tool_reference import format_tool_tooltip
from src.tool_reference_dialog import ToolReferenceDialog

if TYPE_CHECKING:
    from src.video_editor_window import VideoEditorWindow

from src.draw_style_defaults import STYLE_PALETTE_COLORS, apply_tool_default_colors

VIDEO_TOOL_CATEGORIES: list[tuple[str, list[tuple[str, str]]]] = [
    ("Select", [(Tool.SELECT, "Select")]),
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
    ("Text", [(Tool.TEXT, "Text"), (Tool.CALLOUT, "Callout")]),
]

_COLOR_TARGETS_STROKE_FILL = frozenset({"stroke", "fill"})
_COLOR_TARGETS_STROKE = frozenset({"stroke"})
_COLOR_TARGETS_TEXT = frozenset({"text", "stroke", "fill"})
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
    Tool.TEXT: _COLOR_TARGETS_TEXT,
    Tool.CALLOUT: _COLOR_TARGETS_TEXT,
}
_COLOR_TARGETS_BY_SELECTION: dict[str, frozenset[str]] = {
    "rect": _COLOR_TARGETS_STROKE_FILL,
    "ellipse": _COLOR_TARGETS_STROKE_FILL,
    "triangle": _COLOR_TARGETS_STROKE_FILL,
    "star": _COLOR_TARGETS_STROKE_FILL,
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
_COLOR_SELECTION_CONTEXT_TOOLS = frozenset({Tool.SELECT})

_LOCKABLE_TOOLS = frozenset(
    {
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
        Tool.STEP,
    }
)

_ONE_SHOT_ACTIONS: dict[str, str] = {
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
    Tool.STEP: "Insert step",
}

_MENU_POPUP_TOOLS = frozenset(
    {Tool.RECT, Tool.ELLIPSE, Tool.LINE, Tool.ARROW, Tool.TEXT}
)


class VideoVectorToolbar:
    """
    Builds and manages the video editor vector drawing toolbar and style panel.
    """

    def __init__(self, host: VideoEditorWindow) -> None:
        self._host = host
        self._canvas = host.canvas
        self._active_tool = Tool.SELECT
        self._locked_tool: str | None = None
        self._one_shot_tool: str | None = None
        self._tool_buttons: dict[str, QToolButton] = {}
        self._tool_button_order: list[str] = []
        self._tool_button_to_key: dict[QToolButton, str] = {}
        self._tool_stroke_widths = normalize_tool_stroke_widths(None)
        self._tool_stroke_styles = normalize_tool_stroke_styles(None)
        self._rect_corner_radius = 0.0
        self._tool_width_sliders: dict[str, QSlider] = {}
        self._tool_style_combos: dict[str, QComboBox] = {}
        self._tool_radius_spins: dict[str, QDoubleSpinBox] = {}
        self._color_target_widgets: dict[str, list[QWidget]] = {
            "stroke": [],
            "fill": [],
            "text": [],
        }
        self._color_group_gaps: dict[str, QWidget] = {}
        self._property_tabs: QTabWidget | None = None
        self._fitting_property_tabs = False
        self._selection_type = ""

    def build(self) -> QWidget:
        """
        Creates the toolbar container with tool strip and Style tab.

        Returns:
            QWidget: Root toolbar widget.
        """

        bar = QWidget(self._host)
        bar.setObjectName("editorToolbar")
        root_layout = QVBoxLayout(bar)
        root_layout.setContentsMargins(4, 1, 4, 1)
        root_layout.setSpacing(1)

        strip = FlowLayoutWidget(bar, horizontal_spacing=6, vertical_spacing=4, margin=2)
        strip.setObjectName("editorToolStrip")
        strip_widgets: list[QWidget] = []

        for category_title, tools in VIDEO_TOOL_CATEGORIES:
            category_box = QGroupBox(category_title, strip)
            category_box.setObjectName("toolCategoryBox")
            category_layout = QHBoxLayout(category_box)
            category_layout.setContentsMargins(4, 10, 4, 4)
            category_layout.setSpacing(4)
            for tool_key, label in tools:
                button = QToolButton(category_box)
                button.setText(label)
                button.setCheckable(True)
                button.setIcon(build_tool_icon(tool_key))
                button.setIconSize(strip.sizeHint())  # placeholder, set below
                from PySide6.QtCore import QSize

                button.setIconSize(QSize(28, 28))
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                button.setFixedSize(38, 34)
                button.setToolTip(format_tool_tooltip(tool_key))
                button.clicked.connect(
                    lambda _checked=False, t=tool_key: self._on_tool_button_clicked(t)
                )
                button.installEventFilter(self._host)
                self._tool_buttons[tool_key] = button
                self._tool_button_order.append(tool_key)
                self._tool_button_to_key[button] = tool_key
                category_layout.addWidget(button)
            strip_widgets.append(category_box)

        self._tool_buttons[Tool.SELECT].setChecked(True)
        self._setup_stroke_width_tool_menus()

        help_box = QGroupBox("Help", strip)
        help_box.setObjectName("toolCategoryBox")
        help_layout = QHBoxLayout(help_box)
        help_layout.setContentsMargins(4, 10, 4, 4)
        help_button = QToolButton(help_box)
        help_button.setText("?")
        help_button.setToolTip("Open the tools reference table.")
        help_button.setFixedSize(38, 34)
        help_button.clicked.connect(self.show_tools_reference)
        help_layout.addWidget(help_button)
        strip_widgets.append(help_box)

        if hasattr(self._host, "build_history_strip_widgets"):
            strip_widgets.extend(self._host.build_history_strip_widgets(strip))

        if hasattr(self._host, "build_playback_zoom_strip_widgets"):
            strip_widgets.extend(self._host.build_playback_zoom_strip_widgets(strip))

        strip.set_flow_widgets(strip_widgets)
        root_layout.addWidget(strip)

        self._property_tabs = QTabWidget(bar)
        self._property_tabs.setObjectName("editorPropertyTabs")
        self._property_tabs.setDocumentMode(True)
        self._property_tabs.setToolTip(
            "Style tab: border, fill, and text colors for video annotations."
        )
        self._property_tabs.setTabToolTip(
            0,
            "Style: border, fill, and text colors for the active tool or selection.",
        )
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
        self.stroke_button.clicked.connect(lambda: self._choose_color("stroke"))
        stroke_widgets.append(self.stroke_button)
        stroke_widgets.append(self._create_palette_row("stroke"))
        self.stroke_alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.stroke_alpha_slider.setRange(0, 100)
        self.stroke_alpha_slider.setValue(100)
        self.stroke_alpha_slider.setFixedWidth(56)
        self.stroke_alpha_slider.valueChanged.connect(
            lambda value: self._alpha_changed("stroke", value)
        )
        stroke_widgets.append(self.stroke_alpha_slider)
        self.stroke_alpha_label = QLabel("100%")
        stroke_widgets.append(self.stroke_alpha_label)
        style_widgets.extend(stroke_widgets)

        fill_gap = self._create_gap()
        self._color_group_gaps["fill"] = fill_gap
        style_widgets.append(fill_gap)
        self.fill_button = QPushButton("Fill")
        self.fill_button.setFixedWidth(52)
        self.fill_button.clicked.connect(lambda: self._choose_color("fill"))
        fill_widgets.append(self.fill_button)
        fill_widgets.append(self._create_palette_row("fill"))
        self.fill_alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.fill_alpha_slider.setRange(0, 100)
        self.fill_alpha_slider.setValue(31)
        self.fill_alpha_slider.setFixedWidth(56)
        self.fill_alpha_slider.valueChanged.connect(
            lambda value: self._alpha_changed("fill", value)
        )
        fill_widgets.append(self.fill_alpha_slider)
        self.fill_alpha_label = QLabel("31%")
        fill_widgets.append(self.fill_alpha_label)
        style_widgets.extend(fill_widgets)

        text_gap = self._create_gap()
        self._color_group_gaps["text"] = text_gap
        style_widgets.append(text_gap)
        self.text_color_button = QPushButton("Text")
        self.text_color_button.setFixedWidth(52)
        self.text_color_button.clicked.connect(lambda: self._choose_color("text"))
        text_widgets.append(self.text_color_button)
        text_widgets.append(self._create_palette_row("text"))
        self.text_alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.text_alpha_slider.setRange(0, 100)
        self.text_alpha_slider.setValue(100)
        self.text_alpha_slider.setFixedWidth(56)
        self.text_alpha_slider.valueChanged.connect(
            lambda value: self._alpha_changed("text", value)
        )
        text_widgets.append(self.text_alpha_slider)
        self.text_alpha_label = QLabel("100%")
        text_widgets.append(self.text_alpha_label)
        style_widgets.extend(text_widgets)

        self._color_target_widgets = {
            "stroke": stroke_widgets,
            "fill": fill_widgets,
            "text": text_widgets,
        }
        style_tab.set_flow_widgets(style_widgets)
        self._property_tabs.addTab(style_tab, "Style")
        root_layout.addWidget(self._property_tabs)

        self._sync_style_buttons()
        self._update_style_color_visibility()
        self._canvas.set_rect_corner_radius(self._rect_corner_radius)
        return bar

    def handle_event_filter(self, watched: object, event: QEvent) -> bool:
        """
        Handles double-click lock on tool buttons.

        Returns:
            bool: True when the event was consumed.
        """

        if isinstance(watched, QToolButton):
            tool_key = self._tool_button_to_key.get(watched)
            if tool_key is not None and event.type() == QEvent.Type.MouseButtonDblClick:
                self._toggle_tool_lock(tool_key)
                return True
        return False

    def on_content_changed(self, action_label: str | None = None) -> None:
        """
        Applies one-shot tool completion after canvas edits.

        Args:
            action_label: Optional action label already consumed by the host.

        Returns:
            None
        """

        resolved_label = action_label
        if resolved_label is None:
            resolved_label = self._canvas.consume_last_action_label()
        self._apply_one_shot_tool_completion(resolved_label)

    def on_selection_style_changed(self, payload: dict[str, Any]) -> None:
        """
        Updates style tab visibility from the current canvas selection.

        Args:
            payload: Selection style payload from the canvas.

        Returns:
            None
        """

        self._selection_type = str(payload.get("type") or "").strip().lower()
        self._update_style_color_visibility(selection_type=self._selection_type)
        if self._selection_type in {"", "document"}:
            return

        stroke_rgba = payload.get("stroke_rgba")
        if isinstance(stroke_rgba, list) and len(stroke_rgba) == 4:
            self._set_target_color(
                "stroke",
                QColor(
                    int(stroke_rgba[0]),
                    int(stroke_rgba[1]),
                    int(stroke_rgba[2]),
                    int(stroke_rgba[3]),
                ),
                apply_to_canvas=False,
            )

        fill_rgba = payload.get("fill_rgba")
        if isinstance(fill_rgba, list) and len(fill_rgba) == 4:
            self._set_target_color(
                "fill",
                QColor(
                    int(fill_rgba[0]),
                    int(fill_rgba[1]),
                    int(fill_rgba[2]),
                    int(fill_rgba[3]),
                ),
                apply_to_canvas=False,
            )

        text_rgba = payload.get("text_rgba")
        if isinstance(text_rgba, list) and len(text_rgba) == 4:
            self._set_target_color(
                "text",
                QColor(
                    int(text_rgba[0]),
                    int(text_rgba[1]),
                    int(text_rgba[2]),
                    int(text_rgba[3]),
                ),
                apply_to_canvas=False,
            )

    def show_tools_reference(self) -> None:
        """
        Opens the shared tools reference dialog.

        Returns:
            None
        """

        dialog = ToolReferenceDialog(self._host, build_tool_icon)
        dialog.exec()

    def _create_gap(self, width: int = 6) -> QWidget:
        gap = QWidget()
        gap.setFixedWidth(max(1, width))
        gap.setFixedHeight(1)
        return gap

    def _create_palette_row(self, target: str) -> QWidget:
        row = QWidget()
        row.setObjectName("paletteSwatchRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        for color in STYLE_PALETTE_COLORS:
            button = QPushButton()
            button.setFixedSize(18, 18)
            button.setObjectName("paletteSwatch")
            button.setToolTip(color.name())
            button.setStyleSheet(palette_button_stylesheet(color))
            button.clicked.connect(
                lambda _checked=False, c=color, t=target: self._apply_palette_color(t, c)
            )
            layout.addWidget(button)
        return row

    def _sync_style_buttons(self) -> None:
        style = self._host.style_state()
        self.stroke_button.setStyleSheet(
            color_preview_button_stylesheet(style.stroke_color)
        )
        self.fill_button.setStyleSheet(color_preview_button_stylesheet(style.fill_color))
        self.text_color_button.setStyleSheet(
            color_preview_button_stylesheet(style.text_color)
        )
        self.stroke_alpha_slider.setValue(int(round(style.stroke_color.alpha() / 2.55)))
        self.fill_alpha_slider.setValue(int(round(style.fill_color.alpha() / 2.55)))
        self.text_alpha_slider.setValue(int(round(style.text_color.alpha() / 2.55)))
        self.stroke_alpha_label.setText(f"{self.stroke_alpha_slider.value()}%")
        self.fill_alpha_label.setText(f"{self.fill_alpha_slider.value()}%")
        self.text_alpha_label.setText(f"{self.text_alpha_slider.value()}%")

    def _choose_color(self, target: str) -> None:
        from PySide6.QtWidgets import QColorDialog

        style = self._host.style_state()
        current = {
            "stroke": style.stroke_color,
            "fill": style.fill_color,
            "text": style.text_color,
        }[target]
        chosen = QColorDialog.getColor(current, self._host, f"Choose {target} color")
        if not chosen.isValid():
            return
        chosen.setAlpha(current.alpha())
        self._set_target_color(target, chosen)

    def _apply_palette_color(self, target: str, color: QColor) -> None:
        style = self._host.style_state()
        current = {
            "stroke": style.stroke_color,
            "fill": style.fill_color,
            "text": style.text_color,
        }[target]
        chosen = QColor(color)
        chosen.setAlpha(current.alpha())
        self._set_target_color(target, chosen)

    def _alpha_changed(self, target: str, value: int) -> None:
        style = self._host.style_state()
        color = {
            "stroke": QColor(style.stroke_color),
            "fill": QColor(style.fill_color),
            "text": QColor(style.text_color),
        }[target]
        color.setAlpha(int(round(value * 2.55)))
        label = {
            "stroke": self.stroke_alpha_label,
            "fill": self.fill_alpha_label,
            "text": self.text_alpha_label,
        }[target]
        label.setText(f"{value}%")
        self._set_target_color(target, color)

    def _set_target_color(
        self,
        target: str,
        color: QColor,
        *,
        apply_to_canvas: bool = True,
    ) -> None:
        style = self._host.style_state()
        if target == "stroke":
            style.stroke_color = QColor(color)
            self.stroke_button.setStyleSheet(color_preview_button_stylesheet(color))
        elif target == "fill":
            style.fill_color = QColor(color)
            self.fill_button.setStyleSheet(color_preview_button_stylesheet(color))
        else:
            style.text_color = QColor(color)
            self.text_color_button.setStyleSheet(color_preview_button_stylesheet(color))
        if apply_to_canvas:
            kwargs = {
                "stroke": {"stroke_color": QColor(color)},
                "fill": {"fill_color": QColor(color)},
                "text": {"text_color": QColor(color)},
            }[target]
            self._canvas.update_style(**kwargs)
        self._sync_style_buttons()

    def _resolve_style_color_targets(
        self,
        *,
        tool: str | None = None,
        selection_type: str | None = None,
    ) -> frozenset[str]:
        resolved_tool = str(tool or self._active_tool)
        resolved_type = str(selection_type if selection_type is not None else self._selection_type)
        if resolved_type == "document":
            return frozenset()
        if resolved_tool in _COLOR_SELECTION_CONTEXT_TOOLS:
            if resolved_type:
                return _COLOR_TARGETS_BY_SELECTION.get(resolved_type, frozenset())
            return frozenset()
        return _COLOR_TARGETS_BY_TOOL.get(resolved_tool, frozenset())

    def _update_style_color_visibility(
        self,
        *,
        tool: str | None = None,
        selection_type: str | None = None,
    ) -> None:
        if self._property_tabs is None:
            return
        targets = self._resolve_style_color_targets(tool=tool, selection_type=selection_type)
        for target_name, widgets in self._color_target_widgets.items():
            visible = target_name in targets
            for widget in widgets:
                widget.setVisible(visible)
        ordered = [name for name in ("stroke", "fill", "text") if name in targets]
        for gap_name, gap in self._color_group_gaps.items():
            if gap_name not in targets:
                gap.setVisible(False)
                continue
            index = ordered.index(gap_name) if gap_name in ordered else -1
            gap.setVisible(index > 0)
        self._property_tabs.setTabVisible(0, bool(targets))

    def _configure_menu_tool_button(self, button: QToolButton) -> None:
        button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        button.setFixedSize(50, 34)
        button.setProperty("menuTool", True)
        style = button.style()
        if style is not None:
            style.unpolish(button)
            style.polish(button)
        button.update()

    def _setup_stroke_width_tool_menus(self) -> None:
        width_tools = (
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
            menu = QMenu(self._host)
            panel_action = QWidgetAction(menu)
            panel = QWidget(menu)
            root = QVBoxLayout(panel)
            root.setContentsMargins(10, 8, 10, 8)
            width_row = QHBoxLayout()
            width_row.addWidget(QLabel("Width", panel))
            slider = QSlider(Qt.Orientation.Horizontal, panel)
            slider.setRange(0, 64)
            slider.setValue(self._tool_stroke_widths.get(tool_key, 6))
            slider.setMinimumWidth(120)
            slider.setProperty("widthTool", tool_key)
            slider.valueChanged.connect(self._tool_menu_width_changed)
            width_row.addWidget(slider, 1)
            value_label = QLabel(str(slider.value()), panel)
            slider.valueChanged.connect(
                lambda value, label=value_label: label.setText(str(int(value)))
            )
            width_row.addWidget(value_label)
            root.addLayout(width_row)
            self._tool_width_sliders[tool_key] = slider

            if tool_key in STYLE_AWARE_TOOLS:
                style_row = QHBoxLayout()
                style_row.addWidget(QLabel("Style", panel))
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
                style_combo.currentIndexChanged.connect(self._tool_menu_style_changed)
                style_row.addWidget(style_combo, 1)
                root.addLayout(style_row)
                self._tool_style_combos[tool_key] = style_combo

            if tool_key == Tool.RECT:
                radius_row = QHBoxLayout()
                radius_row.addWidget(QLabel("Radius", panel))
                radius_spin = QDoubleSpinBox(panel)
                radius_spin.setDecimals(1)
                radius_spin.setRange(0.0, 200.0)
                radius_spin.setValue(self._rect_corner_radius)
                radius_spin.setProperty("radiusTool", tool_key)
                radius_spin.valueChanged.connect(self._tool_menu_radius_changed)
                radius_row.addWidget(radius_spin, 1)
                root.addLayout(radius_row)
                self._tool_radius_spins[tool_key] = radius_spin

            panel_action.setDefaultWidget(panel)
            menu.addAction(panel_action)
            button.setMenu(menu)
            self._configure_menu_tool_button(button)

    def _tool_menu_width_changed(self, value: int) -> None:
        slider = self.sender()
        if not isinstance(slider, QSlider):
            return
        tool_key = str(slider.property("widthTool") or "")
        if not tool_key:
            return
        self._tool_stroke_widths[tool_key] = int(value)
        if self._active_tool == tool_key:
            style = self._host.style_state()
            style.stroke_width = float(value)
            self._canvas.set_style(style)

    def _tool_menu_style_changed(self, _index: int) -> None:
        combo = self.sender()
        if not isinstance(combo, QComboBox):
            return
        tool_key = str(combo.property("styleTool") or "")
        if not tool_key:
            return
        self._tool_stroke_styles[tool_key] = str(combo.currentData())
        if self._active_tool == tool_key:
            style = self._host.style_state()
            style.stroke_style = str(combo.currentData())
            self._canvas.set_style(style)

    def _tool_menu_radius_changed(self, value: float) -> None:
        spin = self.sender()
        if not isinstance(spin, QDoubleSpinBox):
            return
        self._rect_corner_radius = float(value)
        self._canvas.set_rect_corner_radius(self._rect_corner_radius)

    def _on_tool_button_clicked(self, tool: str) -> None:
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
        self._set_tool(tool)
        self._one_shot_tool = tool if tool in _LOCKABLE_TOOLS else None
        if already_active and tool in _MENU_POPUP_TOOLS:
            button = self._tool_buttons.get(tool)
            if button is not None and button.menu() is not None:
                button.showMenu()

    def _toggle_tool_lock(self, tool: str) -> None:
        if tool not in _LOCKABLE_TOOLS:
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
        self._locked_tool = None
        self._update_tool_lock_visuals()

    def _update_tool_lock_visuals(self) -> None:
        for tool_key in self._tool_button_order:
            button = self._tool_buttons[tool_key]
            locked = tool_key == self._locked_tool
            button.setIcon(build_tool_icon(tool_key, locked=locked))
            base_tip = format_tool_tooltip(tool_key)
            if locked:
                button.setToolTip(f"{base_tip} Currently locked – double-click to unlock.")
            else:
                button.setToolTip(base_tip)

    def _set_tool(self, tool: str) -> None:
        self._active_tool = tool
        for key, button in self._tool_buttons.items():
            button.setChecked(key == tool)
        self._canvas.set_tool(tool)
        style = self._host.style_state()
        if apply_tool_default_colors(tool, style):
            self._canvas.set_style(style)
            self._sync_style_buttons()
        if tool in WIDTH_AWARE_TOOLS:
            resolved = normalize_stroke_width(self._tool_stroke_widths.get(tool, 6), minimum=0)
            style.stroke_width = float(resolved)
            self._canvas.set_style(style)
        if tool in STYLE_AWARE_TOOLS:
            style.stroke_style = self._tool_stroke_styles.get(tool, STROKE_STYLE_SOLID)
            self._canvas.set_style(style)
        self._update_style_color_visibility(tool=tool)
        self._host.statusBar().showMessage(f"Tool: {tool}")

    def apply_tool_stroke_widths(
        self,
        widths: dict[str, int] | None,
        *,
        emit_signal: bool = False,
    ) -> None:
        """
        Restores persisted per-tool stroke widths for the video toolbar.

        Args:
            widths: Tool id to width mapping.
            emit_signal: Unused; kept for parity with the image editor API.

        Returns:
            None
        """

        _ = emit_signal
        self._tool_stroke_widths = normalize_tool_stroke_widths(widths)
        for tool_key, slider in self._tool_width_sliders.items():
            resolved = self._tool_stroke_widths.get(tool_key, 6)
            if slider.value() != resolved:
                slider.blockSignals(True)
                slider.setValue(resolved)
                slider.blockSignals(False)
        if self._active_tool in WIDTH_AWARE_TOOLS:
            style = self._host.style_state()
            style.stroke_width = float(
                normalize_stroke_width(
                    self._tool_stroke_widths.get(self._active_tool, 6),
                    minimum=0,
                )
            )
            self._canvas.set_style(style)

    def apply_tool_stroke_styles(
        self,
        styles: dict[str, str] | None,
        *,
        emit_signal: bool = False,
    ) -> None:
        """
        Restores persisted per-tool stroke styles for the video toolbar.

        Args:
            styles: Tool id to stroke-style mapping.
            emit_signal: Unused; kept for parity with the image editor API.

        Returns:
            None
        """

        _ = emit_signal
        self._tool_stroke_styles = normalize_tool_stroke_styles(styles)
        for tool_key, combo in self._tool_style_combos.items():
            resolved = self._tool_stroke_styles.get(tool_key, STROKE_STYLE_SOLID)
            index = combo.findData(resolved)
            if index >= 0 and combo.currentIndex() != index:
                combo.blockSignals(True)
                combo.setCurrentIndex(index)
                combo.blockSignals(False)
        if self._active_tool in STYLE_AWARE_TOOLS:
            style = self._host.style_state()
            style.stroke_style = self._tool_stroke_styles.get(
                self._active_tool,
                STROKE_STYLE_SOLID,
            )
            self._canvas.set_style(style)

    def sync_tool_from_canvas(self, tool_id: str) -> None:
        """
        Updates toolbar check states when the canvas switches tools programmatically.

        Args:
            tool_id: Active canvas tool identifier.

        Returns:
            None
        """

        self._active_tool = tool_id
        for key, button in self._tool_buttons.items():
            button.setChecked(key == tool_id)

    def _apply_one_shot_tool_completion(self, action_label: str) -> None:
        if self._one_shot_tool is None or self._locked_tool is not None:
            return
        expected = _ONE_SHOT_ACTIONS.get(self._one_shot_tool)
        if expected is None or action_label != expected:
            return
        self._one_shot_tool = None
        self._set_tool(Tool.SELECT)
