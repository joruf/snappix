#!/usr/bin/env python3
"""
Generates README screenshots for Snappix UI components.

Renders the current Qt layouts (capture panel, editor host tabs, video editor,
overlays, tray menu, setup splash) so docs/screenshots/ stays in sync with the
live application chrome.
"""

from __future__ import annotations

import math
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QIcon,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QMainWindow,
    QProgressBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.capture import CapturePanel, RegionCaptureOverlay, WindowCaptureOverlay
from src.constants import APP_NAME
from src.editor_window import EditorWindow
from src.models import AnnotationModel
from src.theme import (
    THEME_DARK,
    build_application_stylesheet,
    build_capture_accent_stylesheet,
    build_editor_accent_stylesheet,
    set_current_theme,
)
from src.video_editor_window import VideoEditorWindow
from src.video_models import VideoAnnotationModel

SCREENSHOT_DIR = PROJECT_ROOT / "docs" / "screenshots"
MOCK_WIDTH = 1280
MOCK_HEIGHT = 800
SAMPLE_VIDEO_PATH = SCREENSHOT_DIR / "_sample-video.mp4"


@dataclass(frozen=True)
class Callout:
    """
    One labeled arrow callout for annotated UI overview screenshots.

    Attributes:
        anchor: Point on the source screenshot the arrow tip should touch.
        label: English label text.
        label_pos: Top-left of the label bubble in padded overview coordinates.
    """

    anchor: QPoint
    label: str
    label_pos: QPoint


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


def _widget_center_in(host: QWidget, child: QWidget) -> QPoint:
    """
    Maps the center of ``child`` into ``host`` coordinates.

    Args:
        host: Root widget used for the screenshot grab.
        child: Nested widget to locate.

    Returns:
        QPoint: Center point in host coordinates.
    """

    top_left = child.mapTo(host, QPoint(0, 0))
    return QPoint(
        top_left.x() + max(1, child.width()) // 2,
        top_left.y() + max(1, child.height()) // 2,
    )


def _draw_arrow_head(painter: QPainter, tip: QPointF, direction: QPointF) -> None:
    """
    Draws a filled arrow head at ``tip`` pointing along ``direction``.

    Args:
        painter: Active painter.
        tip: Arrow tip point.
        direction: Vector from label toward the tip.

    Returns:
        None
    """

    length = math.hypot(direction.x(), direction.y())
    if length < 1.0:
        return
    unit = QPointF(direction.x() / length, direction.y() / length)
    ortho = QPointF(-unit.y(), unit.x())
    size = 10.0
    wing = 5.0
    base = tip - unit * size
    polygon = QPolygonF(
        [
            tip,
            base + ortho * wing,
            base - ortho * wing,
        ]
    )
    painter.drawPolygon(polygon)


def _annotate_screenshot(
    source: QPixmap,
    callouts: list[Callout],
    *,
    pad_left: int = 220,
    pad_top: int = 72,
    pad_right: int = 240,
    pad_bottom: int = 72,
    title: str = "",
) -> QPixmap:
    """
    Composites a UI screenshot with English arrow callouts around it.

    Args:
        source: Grabbed window or panel screenshot.
        callouts: Labels with anchors in source coordinates.
        pad_left: Left margin for labels.
        pad_top: Top margin for labels.
        pad_right: Right margin for labels.
        pad_bottom: Bottom margin for labels.
        title: Optional overview title drawn above the screenshot.

    Returns:
        QPixmap: Annotated overview image.
    """

    width = source.width() + pad_left + pad_right
    height = source.height() + pad_top + pad_bottom
    canvas = QPixmap(width, height)
    canvas.fill(QColor("#12161f"))
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    if title:
        painter.setPen(QColor("#f8fafc"))
        painter.setFont(QFont("Sans Serif", 14, QFont.Weight.Bold))
        painter.drawText(
            QRect(16, 16, width - 32, 36),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            title,
        )

    origin = QPoint(pad_left, pad_top)
    painter.drawPixmap(origin, source)
    painter.setPen(QPen(QColor("#334155"), 1))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRect(QRect(origin, source.size()).adjusted(0, 0, -1, -1))

    accent = QColor("#e11d48")
    label_bg = QColor(15, 23, 42, 235)
    label_border = QColor("#fb7185")
    label_font = QFont("Sans Serif", 10, QFont.Weight.Bold)
    painter.setFont(label_font)
    metrics = QFontMetrics(label_font)

    for callout in callouts:
        anchor = QPointF(origin.x() + callout.anchor.x(), origin.y() + callout.anchor.y())
        text_rect = metrics.boundingRect(callout.label)
        bubble = QRect(
            callout.label_pos.x(),
            callout.label_pos.y(),
            text_rect.width() + 16,
            text_rect.height() + 10,
        )
        bubble_center = QPointF(bubble.center())
        painter.setPen(QPen(accent, 2))
        painter.drawLine(bubble_center, anchor)
        painter.setBrush(accent)
        painter.setPen(Qt.PenStyle.NoPen)
        _draw_arrow_head(painter, anchor, anchor - bubble_center)

        painter.setBrush(label_bg)
        painter.setPen(QPen(label_border, 1))
        painter.drawRoundedRect(bubble, 6, 6)
        painter.setPen(QColor("#fff1f2"))
        painter.drawText(bubble, Qt.AlignmentFlag.AlignCenter, callout.label)

    painter.end()
    return canvas


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
        "docs.snappix.local — Getting Started",
    )
    painter.setPen(QColor("#475569"))
    painter.drawText(
        browser_rect.adjusted(24, 52, -24, -24),
        Qt.AlignmentFlag.AlignTop,
        "\n".join(
            [
                "Snappix Documentation",
                "",
                "Capture screenshots and record screen regions as video.",
                "Annotate with arrows, numbered steps, blur regions, and",
                "time-based overlays in the image and video editors.",
                "",
                "Unsaved tabs restore automatically from ~/.snappix.",
            ]
        ),
    )

    terminal_rect = QRect(920, 120, 300, 220)
    painter.fillRect(terminal_rect, QColor("#111827"))
    painter.setPen(QPen(QColor("#374151"), 1))
    painter.drawRect(terminal_rect.adjusted(0, 0, -1, -1))
    painter.setPen(QColor("#34d399"))
    painter.setFont(QFont("Monospace", 9))
    painter.drawText(
        terminal_rect.adjusted(12, 12, -12, -12),
        Qt.AlignmentFlag.AlignTop,
        "$ python3 run.py\nSnappix ready.\n$ python3 uninstall_dependencies.py",
    )

    files_rect = QRect(920, 380, 300, 300)
    painter.fillRect(files_rect, QColor("#ffffff"))
    painter.setPen(QPen(QColor("#cbd5e1"), 1))
    painter.drawRect(files_rect.adjusted(0, 0, -1, -1))
    painter.fillRect(QRect(files_rect.x(), files_rect.y(), files_rect.width(), 28), QColor("#eef2ff"))
    painter.setPen(QColor("#334155"))
    painter.setFont(QFont("Sans Serif", 9, QFont.Weight.Bold))
    painter.drawText(files_rect.x() + 10, files_rect.y() + 19, "Workspace")
    painter.setFont(QFont("Sans Serif", 9))
    painter.setPen(QColor("#64748b"))
    painter.drawText(
        files_rect.adjusted(12, 40, -12, -12),
        Qt.AlignmentFlag.AlignTop,
        "\n".join(
            [
                "session.json",
                "tabs/tab-image.sfp",
                "tabs/tab-recording.sfpv",
                "video-sources/",
            ]
        ),
    )

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

    painter.setPen(QColor("#0f172a"))
    painter.setFont(QFont("Sans Serif", 18, QFont.Weight.Bold))
    painter.drawText(28, 46, "Snappix — Capture Workflow")
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
        "Open the capture panel and choose fullscreen,\narea, window, scroll, or video capture.",
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
        "Add arrows, numbered steps, blur regions,\nbrush strokes, and text callouts.",
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


def _sample_image_annotations() -> list[AnnotationModel]:
    """
    Returns annotation models used in the image editor screenshot.

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
            payload={"z_index": 2.0, "stroke_style": "solid"},
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
            y=178.0,
            width=240.0,
            height=56.0,
            stroke_rgba=[52, 73, 94, 255],
            fill_rgba=[255, 255, 255, 230],
            stroke_width=2.0,
            text="Highlight key UI areas",
            font_size=15,
            font_family="Sans Serif",
            payload={
                "z_index": 4.0,
                "text_style": "box",
                "text_rgba": [15, 23, 42, 255],
                "box_padding": 8.0,
                "corner_radius": 6.0,
            },
        ),
    ]


def _sample_video_annotations() -> list[VideoAnnotationModel]:
    """
    Returns annotation models used in the video editor screenshot.

    Returns:
        list[VideoAnnotationModel]: Demo video annotations.
    """

    return [
        VideoAnnotationModel(
            annotation_type="rect",
            start_ms=500,
            end_ms=4200,
            x=120.0,
            y=80.0,
            width=280.0,
            height=160.0,
            stroke_rgba=[231, 76, 60, 255],
            fill_rgba=[231, 76, 60, 70],
            stroke_width=3.0,
        ),
        VideoAnnotationModel(
            annotation_type="arrow",
            start_ms=1800,
            end_ms=6500,
            x=520.0,
            y=220.0,
            width=160.0,
            height=-80.0,
            stroke_rgba=[46, 204, 113, 255],
            fill_rgba=[0, 0, 0, 0],
            stroke_width=3.0,
        ),
        VideoAnnotationModel(
            annotation_type="text",
            start_ms=2500,
            end_ms=7000,
            x=680.0,
            y=96.0,
            width=220.0,
            height=48.0,
            stroke_rgba=[44, 62, 80, 255],
            fill_rgba=[255, 255, 255, 220],
            stroke_width=2.0,
            text="Explain this step",
            font_size=16,
        ),
    ]


def _capture_icon() -> QIcon:
    """
    Loads the Snappix capture icon when available.

    Returns:
        QIcon: Capture icon.
    """

    icon_path = PROJECT_ROOT / "assets" / "snappix-red.svg"
    return QIcon.fromTheme("snappix", QIcon(str(icon_path)))


def _editor_icon() -> QIcon:
    """
    Loads the Snappix editor icon when available.

    Returns:
        QIcon: Editor icon.
    """

    icon_path = PROJECT_ROOT / "assets" / "snappix.svg"
    return QIcon.fromTheme("snappix-editor", QIcon(str(icon_path)))


def _ensure_sample_video() -> Path:
    """
    Ensures a small sample MP4 exists for the video editor screenshot.

    Returns:
        Path: Sample video file path.
    """

    if SAMPLE_VIDEO_PATH.is_file() and SAMPLE_VIDEO_PATH.stat().st_size > 0:
        return SAMPLE_VIDEO_PATH

    ffmpeg = "ffmpeg"
    try:
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=#243b53:s=960x540:d=8",
                "-pix_fmt",
                "yuv420p",
                str(SAMPLE_VIDEO_PATH),
            ],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False, dir=SCREENSHOT_DIR) as handle:
            fallback = Path(handle.name)
        fallback.write_bytes(b"")
        return fallback

    return SAMPLE_VIDEO_PATH


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
    panel.setStyleSheet(build_capture_accent_stylesheet(THEME_DARK))
    panel.set_video_capture_available(True)
    panel.delay_slider.setValue(3)
    panel._sync_delay_label_from_slider(3)  # pylint: disable=protected-access
    panel.adjustSize()
    panel.resize(max(panel.sizeHint().width(), 360), panel.sizeHint().height())
    return _save_widget(panel, "capture-panel.png")


def generate_capture_panel_annotated(app: QApplication) -> Path:
    """
    Captures an annotated Capture panel overview with English callouts.

    Args:
        app: Qt application instance.

    Returns:
        Path: Written screenshot path.
    """

    _apply_theme(app)
    panel = CapturePanel()
    panel.setWindowIcon(_capture_icon())
    panel.setStyleSheet(build_capture_accent_stylesheet(THEME_DARK))
    panel.set_video_capture_available(True)
    panel.delay_slider.setValue(3)
    panel._sync_delay_label_from_slider(3)  # pylint: disable=protected-access
    panel.adjustSize()
    panel.resize(max(panel.sizeHint().width(), 420), max(panel.sizeHint().height(), 220))
    panel.show()
    QApplication.processEvents()
    source = panel.grab()

    title = panel.findChild(QLabel, "titleLabel")
    delay_anchor = _widget_center_in(panel, panel.delay_slider)
    buttons_anchor = _widget_center_in(panel, panel.capture_fullscreen_button)
    color_anchor = _widget_center_in(panel, panel.pick_color_button)
    editor_anchor = _widget_center_in(panel, panel.open_editor_button)
    title_anchor = (
        _widget_center_in(panel, title)
        if title is not None
        else QPoint(source.width() // 2, 18)
    )

    pad_left, pad_top, pad_right, pad_bottom = 210, 70, 230, 80
    callouts = [
        Callout(title_anchor, "App title", QPoint(24, pad_top + 8)),
        Callout(delay_anchor, "Capture delay", QPoint(24, pad_top + delay_anchor.y() - 8)),
        Callout(
            buttons_anchor,
            "Capture actions",
            QPoint(pad_left + source.width() + 24, pad_top + buttons_anchor.y() - 10),
        ),
        Callout(
            color_anchor,
            "Screen color picker",
            QPoint(24, pad_top + color_anchor.y() - 8),
        ),
        Callout(
            editor_anchor,
            "Open Editor",
            QPoint(pad_left + source.width() + 24, pad_top + editor_anchor.y() - 8),
        ),
    ]
    annotated = _annotate_screenshot(
        source,
        callouts,
        pad_left=pad_left,
        pad_top=pad_top,
        pad_right=pad_right,
        pad_bottom=pad_bottom,
        title="Capture Panel — UI Overview",
    )
    panel.close()
    return _save_pixmap(annotated, "capture-panel-annotated.png")


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


def _build_editor_host_with_tab(editor: EditorWindow, tab_title: str) -> QMainWindow:
    """
    Wraps one editor tab inside an editor-host window for realistic screenshots.

    Args:
        editor: Editor tab widget.
        tab_title: Tab label text.

    Returns:
        QMainWindow: Editor host shell.
    """

    host = QMainWindow()
    host.setObjectName("editorHost")
    host.setWindowTitle(f"{APP_NAME} Editor")
    host.setWindowIcon(_editor_icon())
    host.setStyleSheet(build_editor_accent_stylesheet(THEME_DARK))
    tabs = QTabWidget()
    tabs.setDocumentMode(True)
    tabs.addTab(editor, tab_title)
    host.setCentralWidget(tabs)
    return host


def generate_editor_window(app: QApplication) -> Path:
    """
    Captures the tabbed image editor host screenshot.

    Args:
        app: Qt application instance.

    Returns:
        Path: Written screenshot path.
    """

    _apply_theme(app)
    editor = EditorWindow(_build_editor_sample_screenshot())
    editor.canvas.load_annotations(_sample_image_annotations())
    editor.canvas.set_tool("select")
    host = _build_editor_host_with_tab(editor, "Capture Workflow")
    host.resize(1320, 860)
    editor.canvas.refresh_workspace_theme(THEME_DARK)
    QApplication.processEvents()
    editor.canvas._apply_initial_screenshot_view()  # pylint: disable=protected-access
    QApplication.processEvents()
    return _save_widget(host, "editor-window.png")


def generate_editor_window_annotated(app: QApplication) -> Path:
    """
    Captures an annotated Editor window overview with English callouts.

    Args:
        app: Qt application instance.

    Returns:
        Path: Written screenshot path.
    """

    _apply_theme(app)
    editor = EditorWindow(_build_editor_sample_screenshot())
    editor.canvas.load_annotations(_sample_image_annotations())
    editor.canvas.set_tool("select")
    items = editor.canvas._annotation_items()  # pylint: disable=protected-access
    if items:
        items[0].setSelected(True)
        editor.canvas._refresh_selection_info()  # pylint: disable=protected-access
    editor._property_tabs.setCurrentIndex(editor._PROPERTY_TAB_ARRANGE)  # pylint: disable=protected-access
    host = _build_editor_host_with_tab(editor, "Capture Workflow")
    host.resize(1320, 860)
    editor.canvas.refresh_workspace_theme(THEME_DARK)
    host.show()
    QApplication.processEvents()
    editor.canvas._apply_initial_screenshot_view()  # pylint: disable=protected-access
    QApplication.processEvents()
    source = host.grab()

    tabs = host.centralWidget()
    assert isinstance(tabs, QTabWidget)
    toolbar = editor._toolbar_widget  # pylint: disable=protected-access
    property_tabs = editor._property_tabs  # pylint: disable=protected-access
    canvas = editor.canvas
    status = editor.statusBar()

    pad_left, pad_top, pad_right, pad_bottom = 200, 64, 220, 70
    menu_anchor = QPoint(80, 18)
    tab_anchor = _widget_center_in(host, tabs.tabBar())
    tools_anchor = _widget_center_in(host, toolbar)
    # Prefer the tool strip row near the top of the toolbar.
    tools_anchor = QPoint(tools_anchor.x(), min(tools_anchor.y(), toolbar.mapTo(host, QPoint(0, 28)).y()))
    props_anchor = _widget_center_in(host, property_tabs)
    canvas_anchor = _widget_center_in(host, canvas)
    document_anchor = QPoint(
        canvas.mapTo(host, QPoint(canvas.width() // 2, canvas.height() // 2)).x(),
        canvas.mapTo(host, QPoint(canvas.width() // 2, canvas.height() // 2)).y(),
    )
    status_anchor = _widget_center_in(host, status)
    history_anchor = _widget_center_in(host, editor.history_undo_button)
    zoom_anchor = _widget_center_in(host, editor.zoom_slider)

    callouts = [
        Callout(menu_anchor, "Menu bar", QPoint(24, 40)),
        Callout(tab_anchor, "Editor tabs", QPoint(pad_left + source.width() + 24, 48)),
        Callout(tools_anchor, "Tool strip", QPoint(24, pad_top + 70)),
        Callout(history_anchor, "History", QPoint(pad_left + source.width() + 24, pad_top + 90)),
        Callout(zoom_anchor, "Zoom controls", QPoint(pad_left + source.width() + 24, pad_top + 130)),
        Callout(props_anchor, "Property tabs (Arrange)", QPoint(24, pad_top + props_anchor.y() - 10)),
        Callout(canvas_anchor, "Workspace", QPoint(24, pad_top + canvas_anchor.y() - 10)),
        Callout(
            document_anchor,
            "Document / canvas",
            QPoint(pad_left + source.width() + 24, pad_top + document_anchor.y() - 10),
        ),
        Callout(
            status_anchor,
            "Status bar",
            QPoint(pad_left + status_anchor.x() - 40, pad_top + source.height() + 18),
        ),
    ]
    annotated = _annotate_screenshot(
        source,
        callouts,
        pad_left=pad_left,
        pad_top=pad_top,
        pad_right=pad_right,
        pad_bottom=pad_bottom,
        title="Image Editor — UI Overview",
    )
    host.close()
    return _save_pixmap(annotated, "editor-window-annotated.png")


def generate_video_editor(app: QApplication) -> Path:
    """
    Captures the video editor tab screenshot with timeline annotations.

    Args:
        app: Qt application instance.

    Returns:
        Path: Written screenshot path.
    """

    _apply_theme(app)
    sample_video = _ensure_sample_video()
    editor = VideoEditorWindow(str(sample_video), 960, 540)
    editor.setWindowIcon(_editor_icon())
    editor.setStyleSheet(build_editor_accent_stylesheet(THEME_DARK))
    editor._annotations.extend(_sample_video_annotations())  # pylint: disable=protected-access
    editor.canvas.set_annotations(editor._annotations)  # pylint: disable=protected-access
    editor.timeline.set_annotations(editor._annotations)  # pylint: disable=protected-access
    editor.timeline.set_duration(8000)
    editor.timeline.set_position(2200)
    editor.timeline.refresh()
    host = _build_editor_host_with_tab(editor, "Recording")
    host.resize(1320, 900)
    QApplication.processEvents()
    return _save_widget(host, "video-editor.png")


def generate_video_editor_annotated(app: QApplication) -> Path:
    """
    Captures an annotated Video Editor overview with English callouts.

    Args:
        app: Qt application instance.

    Returns:
        Path: Written screenshot path.
    """

    _apply_theme(app)
    sample_video = _ensure_sample_video()
    editor = VideoEditorWindow(str(sample_video), 960, 540)
    editor.setWindowIcon(_editor_icon())
    editor.setStyleSheet(build_editor_accent_stylesheet(THEME_DARK))
    editor._annotations.extend(_sample_video_annotations())  # pylint: disable=protected-access
    editor.canvas.set_annotations(editor._annotations)  # pylint: disable=protected-access
    editor.timeline.set_annotations(editor._annotations)  # pylint: disable=protected-access
    editor.timeline.set_duration(8000)
    editor.timeline.set_position(2200)
    editor.timeline.refresh()
    host = _build_editor_host_with_tab(editor, "Recording")
    host.resize(1320, 900)
    host.show()
    QApplication.processEvents()
    source = host.grab()

    tabs = host.centralWidget()
    assert isinstance(tabs, QTabWidget)
    toolbar = editor._toolbar_widget  # pylint: disable=protected-access
    property_tabs = host.findChild(QTabWidget, "editorPropertyTabs")
    canvas = editor.canvas
    timeline = editor.timeline
    status = editor.statusBar()

    pad_left, pad_top, pad_right, pad_bottom = 210, 64, 230, 78
    menu_anchor = QPoint(70, 18)
    tab_anchor = _widget_center_in(host, tabs.tabBar())
    tools_anchor = QPoint(
        toolbar.mapTo(host, QPoint(120, 28)).x(),
        toolbar.mapTo(host, QPoint(120, 28)).y(),
    )
    history_anchor = _widget_center_in(host, editor.history_undo_button)
    playback_anchor = _widget_center_in(host, editor.play_button)
    view_anchor = _widget_center_in(host, editor.show_all_objects_checkbox)
    zoom_anchor = _widget_center_in(host, editor.zoom_slider)
    props_anchor = (
        _widget_center_in(host, property_tabs)
        if property_tabs is not None
        else QPoint(tools_anchor.x(), tools_anchor.y() + 50)
    )
    canvas_anchor = _widget_center_in(host, canvas)
    timeline_anchor = _widget_center_in(host, timeline)
    # Point slightly above center so the label targets the time ruler / playhead area.
    playhead_anchor = QPoint(
        timeline.mapTo(host, QPoint(timeline.width() // 3, 18)).x(),
        timeline.mapTo(host, QPoint(timeline.width() // 3, 18)).y(),
    )
    tracks_anchor = QPoint(
        timeline.mapTo(host, QPoint(timeline.width() // 2, max(40, timeline.height() // 2))).x(),
        timeline.mapTo(host, QPoint(timeline.width() // 2, max(40, timeline.height() // 2))).y(),
    )
    pan_left_anchor = _widget_center_in(host, editor.timeline_pan_left)
    pan_right_anchor = _widget_center_in(host, editor.timeline_pan_right)
    status_anchor = _widget_center_in(host, status)

    callouts = [
        Callout(menu_anchor, "Menu bar", QPoint(24, 40)),
        Callout(tab_anchor, "Editor tabs", QPoint(pad_left + source.width() + 24, 48)),
        Callout(tools_anchor, "Tool strip", QPoint(24, pad_top + 70)),
        Callout(history_anchor, "History", QPoint(pad_left + source.width() + 24, pad_top + 85)),
        Callout(playback_anchor, "Playback controls", QPoint(24, pad_top + playback_anchor.y() - 10)),
        Callout(view_anchor, "Show all objects", QPoint(pad_left + source.width() + 24, pad_top + view_anchor.y() - 10)),
        Callout(zoom_anchor, "Zoom controls", QPoint(pad_left + source.width() + 24, pad_top + zoom_anchor.y() + 20)),
        Callout(props_anchor, "Style property tab", QPoint(24, pad_top + props_anchor.y() - 8)),
        Callout(canvas_anchor, "Video preview", QPoint(24, pad_top + canvas_anchor.y() - 10)),
        Callout(playhead_anchor, "Time ruler / playhead", QPoint(pad_left + source.width() + 24, pad_top + playhead_anchor.y() - 8)),
        Callout(tracks_anchor, "Annotation tracks", QPoint(24, pad_top + tracks_anchor.y() - 8)),
        Callout(timeline_anchor, "Timeline", QPoint(pad_left + source.width() + 24, pad_top + timeline_anchor.y() + 18)),
        Callout(pan_left_anchor, "Timeline pan ◀", QPoint(24, pad_top + pan_left_anchor.y() + 18)),
        Callout(pan_right_anchor, "Timeline pan ▶", QPoint(pad_left + source.width() + 24, pad_top + pan_right_anchor.y() + 40)),
        Callout(
            status_anchor,
            "Status bar",
            QPoint(pad_left + status_anchor.x() - 40, pad_top + source.height() + 20),
        ),
    ]
    annotated = _annotate_screenshot(
        source,
        callouts,
        pad_left=pad_left,
        pad_top=pad_top,
        pad_right=pad_right,
        pad_bottom=pad_bottom,
        title="Video Editor — UI Overview",
    )
    host.close()
    return _save_pixmap(annotated, "video-editor-annotated.png")


def generate_tray_menu(app: QApplication) -> Path:
    """
    Renders the system tray context menu screenshot.

    Args:
        app: Qt application instance.

    Returns:
        Path: Written screenshot path.
    """

    from PySide6.QtWidgets import QMenu

    _apply_theme(app)
    menu = QMenu()
    menu.addAction("Show Snappix")
    menu.addSeparator()
    menu.addAction("Capture Area")
    menu.addAction("Capture Window Under Cursor")
    menu.addAction("Capture Video")
    menu.addSeparator()
    pause_action = menu.addAction("Pause Recording")
    pause_action.setEnabled(False)
    stop_action = menu.addAction("Stop Recording")
    stop_action.setEnabled(False)
    menu.addSeparator()
    autostart_action = menu.addAction("Start at boot")
    autostart_action.setCheckable(True)
    autostart_action.setChecked(True)
    theme_menu = menu.addMenu("Theme")
    theme_group = QActionGroup(theme_menu)
    theme_group.setExclusive(True)
    for label, checked in (("Dark", True), ("Light", False), ("Slate", False), ("Sepia", False)):
        action = QAction(label, theme_menu)
        action.setCheckable(True)
        action.setChecked(checked)
        theme_group.addAction(action)
        theme_menu.addAction(action)
    menu.addSeparator()
    menu.addAction("Settings...")
    menu.addSeparator()
    menu.addAction("About")
    menu.addAction("Quit Snappix")
    menu.setStyleSheet(build_application_stylesheet(THEME_DARK))
    menu.adjustSize()
    pixmap = QPixmap(menu.size())
    pixmap.fill(Qt.GlobalColor.transparent)
    menu.render(pixmap)
    return _save_pixmap(pixmap, "system-tray-menu.png")


def generate_first_time_setup(app: QApplication) -> Path:
    """
    Captures the first-time setup splash screenshot.

    Args:
        app: Qt application instance.

    Returns:
        Path: Written screenshot path.
    """

    _apply_theme(app)
    container = QWidget()
    container.setStyleSheet(
        "QWidget { background-color: #1a1f2a; color: #f4f8ff; }"
        "QLabel#brandLabel { font-size: 18px; font-weight: 700; }"
        "QLabel#subtitleLabel { color: #9aa6b8; font-size: 11px; }"
        "QLabel#statusLabel { color: #d7dee8; font-size: 11px; }"
        "QLabel#hintLabel { color: #9fb2c9; font-size: 11px; }"
    )
    layout = QVBoxLayout(container)
    layout.setContentsMargins(36, 28, 36, 28)
    layout.setSpacing(12)

    logo_path = PROJECT_ROOT / "assets" / "snappix-splash.png"
    if logo_path.is_file():
        logo = QLabel()
        logo.setPixmap(QPixmap(str(logo_path)).scaledToWidth(220, Qt.TransformationMode.SmoothTransformation))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)
    else:
        fallback = QLabel(APP_NAME)
        fallback.setObjectName("brandLabel")
        fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(fallback)

    brand = QLabel(APP_NAME)
    brand.setObjectName("brandLabel")
    brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(brand)

    subtitle = QLabel("Checking installation…")
    subtitle.setObjectName("subtitleLabel")
    subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(subtitle)

    status = QLabel("Installing Python packages (PySide6, Pillow, requests, pynput)…")
    status.setObjectName("statusLabel")
    status.setAlignment(Qt.AlignmentFlag.AlignCenter)
    status.setWordWrap(True)
    layout.addWidget(status)

    progress = QProgressBar()
    progress.setRange(0, 0)
    progress.setFixedHeight(10)
    progress.setTextVisible(False)
    layout.addWidget(progress)

    hint = QLabel("If prompted, approve the administrator dialog for Linux system packages.")
    hint.setObjectName("hintLabel")
    hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
    hint.setWordWrap(True)
    layout.addWidget(hint)

    frame = QFrame()
    frame.setFixedWidth(480)
    frame_layout = QVBoxLayout(frame)
    frame_layout.addWidget(container)
    frame.adjustSize()
    return _save_widget(frame, "first-time-setup.png")


def main() -> int:
    """
    Generates all README screenshots.

    Returns:
        int: Process exit code.
    """

    _ensure_screenshot_dir()
    if not QGuiApplication.instance():
        app = QApplication(sys.argv)
    else:
        app = QApplication.instance()
    app.setApplicationName(APP_NAME)

    outputs = [
        generate_capture_panel(app),
        generate_capture_panel_annotated(app),
        generate_region_overlay(app),
        generate_window_overlay(app),
        generate_editor_window(app),
        generate_editor_window_annotated(app),
        generate_video_editor(app),
        generate_video_editor_annotated(app),
        generate_tray_menu(app),
        generate_first_time_setup(app),
    ]

    for path in outputs:
        print(f"Wrote {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
