#!/usr/bin/env python3
"""
Generates README screenshots for SnapAgent UI components.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QFont,
    QGuiApplication,
    QIcon,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QProgressBar, QVBoxLayout, QWidget

from src.capture import CapturePanel, RegionCaptureOverlay, WindowCaptureOverlay
from src.constants import APP_NAME
from src.editor_window import EditorWindow
from src.models import AnnotationModel
from src.theme import (
    THEME_DARK,
    build_application_stylesheet,
    build_editor_accent_stylesheet,
    set_current_theme,
)

SCREENSHOT_DIR = PROJECT_ROOT / "docs" / "screenshots"
MOCK_WIDTH = 1280
MOCK_HEIGHT = 800


def _ensure_screenshot_dir() -> None:
    """
    Creates the screenshot output directory when missing.

    Returns:
        None
    """

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def _save_pixmap(pixmap: QPixmap, filename: str) -> Path:
    """
    Saves one pixmap to the docs screenshot folder.

    Args:
        pixmap: Image to save.
        filename: Target file name.

    Returns:
        Path: Written file path.
    """

    target = SCREENSHOT_DIR / filename
    pixmap.save(str(target), "PNG")
    return target


def _save_widget(widget: QWidget, filename: str) -> Path:
    """
    Renders one widget into a PNG screenshot.

    Args:
        widget: Widget to capture.
        filename: Target file name.

    Returns:
        Path: Written file path.
    """

    widget.show()
    QApplication.processEvents()
    return _save_pixmap(widget.grab(), filename)


def _apply_theme(app: QApplication) -> None:
    """
    Applies the dark application theme used in README screenshots.

    Args:
        app: Qt application instance.

    Returns:
        None
    """

    set_current_theme(THEME_DARK)
    app.setStyleSheet(build_application_stylesheet(THEME_DARK))


def _build_mock_desktop() -> QPixmap:
    """
    Builds a synthetic desktop screenshot for overlay previews.

    Returns:
        QPixmap: Mock desktop image.
    """

    pixmap = QPixmap(MOCK_WIDTH, MOCK_HEIGHT)
    pixmap.fill(QColor("#1a3a52"))
    painter = QPainter(pixmap)
    gradient = QLinearGradient(0, 0, MOCK_WIDTH, MOCK_HEIGHT)
    gradient.setColorAt(0.0, QColor("#274c77"))
    gradient.setColorAt(1.0, QColor("#1b263b"))
    painter.fillRect(pixmap.rect(), gradient)

    browser_rect = QRect(120, 90, 760, 520)
    painter.fillRect(browser_rect, QColor("#f4f6f8"))
    painter.setPen(QPen(QColor("#d0d7de"), 1))
    painter.drawRect(browser_rect.adjusted(0, 0, -1, -1))
    painter.fillRect(QRect(browser_rect.x(), browser_rect.y(), browser_rect.width(), 36), QColor("#e9eef3"))
    painter.setPen(QColor("#334155"))
    painter.setFont(QFont("Sans Serif", 10))
    painter.drawText(
        QRect(browser_rect.x() + 14, browser_rect.y() + 8, browser_rect.width() - 28, 24),
        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
        "docs.snapagent.local — Getting Started",
    )
    painter.setPen(QColor("#475569"))
    painter.drawText(browser_rect.adjusted(24, 52, -24, -24), Qt.AlignmentFlag.AlignTop, "\n".join([
        "SnapAgent Documentation",
        "",
        "Capture screenshots quickly and annotate them with arrows,",
        "step numbers, blur regions, and text callouts.",
        "",
        "Use Scroll Capture for long web pages and export to PNG,",
        "JPEG, or PDF when you are done editing.",
    ]))

    terminal_rect = QRect(920, 120, 300, 220)
    painter.fillRect(terminal_rect, QColor("#111827"))
    painter.setPen(QPen(QColor("#374151"), 1))
    painter.drawRect(terminal_rect.adjusted(0, 0, -1, -1))
    painter.setPen(QColor("#34d399"))
    painter.setFont(QFont("Monospace", 9))
    painter.drawText(
        terminal_rect.adjusted(12, 12, -12, -12),
        Qt.AlignmentFlag.AlignTop,
        "$ python3 run.py\nSnapAgent ready.\n$ python3 run.py capture --mode region",
    )

    files_rect = QRect(920, 380, 300, 300)
    painter.fillRect(files_rect, QColor("#ffffff"))
    painter.setPen(QPen(QColor("#cbd5e1"), 1))
    painter.drawRect(files_rect.adjusted(0, 0, -1, -1))
    painter.fillRect(QRect(files_rect.x(), files_rect.y(), files_rect.width(), 28), QColor("#eef2ff"))
    painter.setPen(QColor("#334155"))
    painter.setFont(QFont("Sans Serif", 9, QFont.Weight.Bold))
    painter.drawText(files_rect.x() + 10, files_rect.y() + 19, "Projects")
    painter.setFont(QFont("Sans Serif", 9))
    painter.setPen(QColor("#64748b"))
    painter.drawText(files_rect.adjusted(12, 40, -12, -12), Qt.AlignmentFlag.AlignTop, "\n".join([
        "capture-panel.sfp",
        "editor-window.sfp",
        "scroll-demo.sfp",
        "readme-export.png",
    ]))

    painter.end()
    return pixmap


def _build_editor_sample_screenshot() -> QPixmap:
    """
    Builds the screenshot content shown inside the editor tab.

    Returns:
        QPixmap: Sample editor document image.
    """

    pixmap = QPixmap(960, 640)
    pixmap.fill(QColor("#ffffff"))
    painter = QPainter(pixmap)
    painter.fillRect(pixmap.rect(), QColor("#fafafa"))
    painter.setPen(QPen(QColor("#e2e8f0"), 1))
    painter.drawRect(pixmap.rect().adjusted(0, 0, -1, -1))

    header_rect = QRect(0, 0, pixmap.width(), 72)
    painter.fillRect(header_rect, QColor("#ffffff"))
    painter.setPen(QColor("#0f172a"))
    painter.setFont(QFont("Sans Serif", 18, QFont.Weight.Bold))
    painter.drawText(28, 46, "SnapAgent — Capture Workflow")
    painter.setPen(QColor("#64748b"))
    painter.setFont(QFont("Sans Serif", 11))
    painter.drawText(28, 68, "Annotate screenshots with professional tools")

    card_rect = QRect(28, 96, 420, 220)
    painter.fillRect(card_rect, QColor("#ffffff"))
    painter.setPen(QPen(QColor("#dbeafe"), 1))
    painter.drawRoundedRect(card_rect, 8, 8)
    painter.setPen(QColor("#1e293b"))
    painter.setFont(QFont("Sans Serif", 12, QFont.Weight.Bold))
    painter.drawText(card_rect.adjusted(18, 18, -18, -18), Qt.AlignmentFlag.AlignTop, "1. Capture")
    painter.setFont(QFont("Sans Serif", 11))
    painter.setPen(QColor("#475569"))
    painter.drawText(
        card_rect.adjusted(18, 48, -18, -18),
        Qt.AlignmentFlag.AlignTop,
        "Open the capture panel and choose fullscreen,\narea, window, or scroll capture.",
    )

    card_rect = QRect(470, 96, 460, 220)
    painter.fillRect(card_rect, QColor("#ffffff"))
    painter.setPen(QPen(QColor("#dbeafe"), 1))
    painter.drawRoundedRect(card_rect, 8, 8)
    painter.setPen(QColor("#1e293b"))
    painter.setFont(QFont("Sans Serif", 12, QFont.Weight.Bold))
    painter.drawText(card_rect.adjusted(18, 18, -18, -18), Qt.AlignmentFlag.AlignTop, "2. Annotate")
    painter.setFont(QFont("Sans Serif", 11))
    painter.setPen(QColor("#475569"))
    painter.drawText(
        card_rect.adjusted(18, 48, -18, -18),
        Qt.AlignmentFlag.AlignTop,
        "Add arrows, numbered steps, blur regions,\nand text callouts on the gray pasteboard.",
    )

    button_rect = QRect(28, 360, 180, 44)
    painter.setBrush(QColor("#c73838"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(button_rect, 6, 6)
    painter.setPen(QColor("#ffffff"))
    painter.setFont(QFont("Sans Serif", 11, QFont.Weight.Bold))
    painter.drawText(button_rect, Qt.AlignmentFlag.AlignCenter, "Open Capture Panel")

    painter.end()
    return pixmap


def _sample_annotations() -> list[AnnotationModel]:
    """
    Returns annotation models used in the editor screenshot.

    Returns:
        list[AnnotationModel]: Demo annotations.
    """

    return [
        AnnotationModel(
            annotation_type="rect",
            x=24.0,
            y=88.0,
            width=430.0,
            height=236.0,
            stroke_rgba=[199, 56, 56, 255],
            fill_rgba=[199, 56, 56, 35],
            stroke_width=3.0,
            payload={"z_index": 1.0},
        ),
        AnnotationModel(
            annotation_type="arrow",
            x=470.0,
            y=300.0,
            width=180.0,
            height=-90.0,
            stroke_rgba=[46, 204, 113, 255],
            fill_rgba=[46, 204, 113, 0],
            stroke_width=4.0,
            payload={"z_index": 2.0},
        ),
        AnnotationModel(
            annotation_type="step",
            x=640.0,
            y=180.0,
            width=42.0,
            height=42.0,
            stroke_rgba=[255, 255, 255, 255],
            fill_rgba=[199, 56, 56, 255],
            stroke_width=2.0,
            payload={"z_index": 3.0, "step_number": 1},
        ),
        AnnotationModel(
            annotation_type="text",
            x=690.0,
            y=188.0,
            width=220.0,
            height=48.0,
            stroke_rgba=[15, 23, 42, 255],
            fill_rgba=[255, 255, 255, 0],
            stroke_width=1.0,
            text="Highlight key UI areas",
            font_size=15,
            font_family="Sans Serif",
            payload={"z_index": 4.0, "text_style": "plain"},
        ),
    ]


def _capture_icon() -> QIcon:
    """
    Loads the SnapAgent capture icon when available.

    Returns:
        QIcon: Capture icon.
    """

    icon_path = PROJECT_ROOT / "assets" / "snapagent-red.svg"
    return QIcon.fromTheme("snapagent", QIcon(str(icon_path)))


def generate_capture_panel(app: QApplication) -> Path:
    """
    Captures the capture panel screenshot.

    Args:
        app: Qt application instance.

    Returns:
        Path: Written screenshot path.
    """

    _apply_theme(app)
    panel = CapturePanel()
    panel.setWindowIcon(_capture_icon())
    panel.delay_slider.setValue(3)
    panel._sync_delay_label_from_slider(3)  # pylint: disable=protected-access
    panel.adjustSize()
    panel.resize(panel.size())
    return _save_widget(panel, "capture-panel.png")


def generate_region_overlay(app: QApplication) -> Path:  # pylint: disable=unused-argument
    """
    Captures the region selection overlay screenshot.

    Args:
        app: Qt application instance.

    Returns:
        Path: Written screenshot path.
    """

    desktop = _build_mock_desktop()
    geometry = QRect(0, 0, MOCK_WIDTH, MOCK_HEIGHT)
    overlay = RegionCaptureOverlay(desktop, geometry)
    overlay.resize(MOCK_WIDTH, MOCK_HEIGHT)
    overlay._dragging = True  # pylint: disable=protected-access
    overlay._start_point = QPoint(420, 180)  # pylint: disable=protected-access
    overlay._current_point = QPoint(930, 520)  # pylint: disable=protected-access
    return _save_widget(overlay, "region-overlay.png")


def generate_window_overlay(app: QApplication) -> Path:  # pylint: disable=unused-argument
    """
    Captures the window selection overlay screenshot.

    Args:
        app: Qt application instance.

    Returns:
        Path: Written screenshot path.
    """

    desktop = _build_mock_desktop()
    geometry = QRect(0, 0, MOCK_WIDTH, MOCK_HEIGHT)
    overlay = WindowCaptureOverlay(desktop, geometry)
    overlay.resize(MOCK_WIDTH, MOCK_HEIGHT)
    overlay._poll_timer.stop()  # pylint: disable=protected-access
    overlay._hover_rect = QRect(120, 90, 760, 520)  # pylint: disable=protected-access
    overlay._hover_label = "X:120 Y:90 W:760 H:520"  # pylint: disable=protected-access
    return _save_widget(overlay, "capture-window-preview.png")


def generate_editor_window(app: QApplication) -> Path:
    """
    Captures the editor window screenshot.

    Args:
        app: Qt application instance.

    Returns:
        Path: Written screenshot path.
    """

    _apply_theme(app)
    editor = EditorWindow(_build_editor_sample_screenshot())
    editor.setObjectName("editorHost")
    editor.setStyleSheet(build_editor_accent_stylesheet(THEME_DARK))
    editor.canvas.load_annotations(_sample_annotations())
    editor.canvas.set_tool("select")
    editor.resize(1280, 820)
    editor.canvas.refresh_workspace_theme(THEME_DARK)
    QApplication.processEvents()
    editor.canvas._apply_initial_screenshot_view()  # pylint: disable=protected-access
    QApplication.processEvents()
    return _save_widget(editor, "editor-window.png")


def generate_tray_menu(app: QApplication) -> Path:
    """
    Renders the system tray context menu screenshot.

    Args:
        app: Qt application instance.

    Returns:
        Path: Written screenshot path.
    """

    _apply_theme(app)
    menu = QMenu()
    menu.addAction("Show SnapAgent")
    menu.addSeparator()
    menu.addAction("Capture Area")
    menu.addAction("Capture Window Under Cursor")
    menu.addSeparator()
    autostart_action = menu.addAction("Start at boot")
    autostart_action.setCheckable(True)
    autostart_action.setChecked(True)
    theme_menu = menu.addMenu("Theme")
    theme_group = QActionGroup(theme_menu)
    theme_group.setExclusive(True)
    dark_action = QAction("Dark", theme_menu)
    dark_action.setCheckable(True)
    dark_action.setChecked(True)
    theme_group.addAction(dark_action)
    theme_menu.addAction(dark_action)
    light_action = QAction("Light", theme_menu)
    light_action.setCheckable(True)
    theme_group.addAction(light_action)
    theme_menu.addAction(light_action)
    menu.addSeparator()
    menu.addAction("Settings...")
    menu.addSeparator()
    menu.addAction("About")
    menu.addAction("Quit SnapAgent")
    menu.setStyleSheet(build_application_stylesheet(THEME_DARK))
    menu.adjustSize()
    pixmap = QPixmap(menu.size())
    pixmap.fill(Qt.GlobalColor.transparent)
    menu.render(pixmap)
    return _save_pixmap(pixmap, "system-tray-menu.png")


def generate_first_time_setup(app: QApplication) -> Path:
    """
    Captures the first-time setup progress dialog screenshot.

    Args:
        app: Qt application instance.

    Returns:
        Path: Written screenshot path.
    """

    _apply_theme(app)
    container = QWidget()
    container.setStyleSheet(build_application_stylesheet(THEME_DARK))
    layout = QVBoxLayout(container)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(12)

    title = QLabel(
        "SnapAgent is installing required dependencies.\n"
        "Please wait — this may take a few minutes."
    )
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title.setWordWrap(True)
    layout.addWidget(title)

    status = QLabel("Installing Python packages (PySide6, Pillow, requests)...")
    status.setAlignment(Qt.AlignmentFlag.AlignCenter)
    status.setWordWrap(True)
    layout.addWidget(status)

    progress = QProgressBar()
    progress.setRange(0, 0)
    progress.setFixedHeight(18)
    layout.addWidget(progress)

    hint = QLabel(
        "If prompted, enter your password in the terminal for system packages."
    )
    hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
    hint.setWordWrap(True)
    hint.setStyleSheet("color: #9fb2c9; font-size: 11px;")
    layout.addWidget(hint)

    container.adjustSize()
    container.resize(max(container.sizeHint().width(), 480), container.sizeHint().height())
    return _save_widget(container, "first-time-setup.png")


def main() -> int:
    """
    Generates all README screenshots.

    Returns:
        int: Process exit code.
    """

    _ensure_screenshot_dir()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)

    outputs = [
        generate_capture_panel(app),
        generate_region_overlay(app),
        generate_window_overlay(app),
        generate_editor_window(app),
        generate_tray_menu(app),
        generate_first_time_setup(app),
    ]

    for path in outputs:
        print(f"Wrote {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
