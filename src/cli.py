"""
Command-line interface for Snappix.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QEventLoop, QTimer, Qt
from PySide6.QtGui import QPageLayout, QPageSize, QPagedPaintDevice, QPainter, QPdfWriter
from PySide6.QtWidgets import QApplication

from src.capture import CaptureMode, CaptureRequest, capture_full_screen, execute_capture_request, execute_color_pick
from src.editor_canvas import EditorCanvas
from src.storage import base64_png_to_pixmap, load_project


def build_cli_parser() -> argparse.ArgumentParser:
    """
    Builds the Snappix command-line parser.

    Returns:
        argparse.ArgumentParser: Configured parser.
    """

    parser = argparse.ArgumentParser(
        prog="snappix",
        description="Snappix command line interface",
    )
    subparsers = parser.add_subparsers(dest="command")

    capture_parser = subparsers.add_parser("capture", help="Capture screenshot to file")
    capture_parser.add_argument(
        "--mode",
        choices=[CaptureMode.FULL_SCREEN, CaptureMode.REGION, CaptureMode.WINDOW],
        default=CaptureMode.FULL_SCREEN,
        help="Capture mode",
    )
    capture_parser.add_argument(
        "--delay",
        type=int,
        default=0,
        help="Delay in seconds before capture starts",
    )
    capture_parser.add_argument(
        "--output",
        required=True,
        help="Output image path (extension auto-added when missing)",
    )

    color_parser = subparsers.add_parser("pick-color", help="Pick one screen color")
    color_parser.add_argument(
        "--clipboard",
        action="store_true",
        help="Copy picked color to clipboard",
    )

    export_parser = subparsers.add_parser("export", help="Export one .sfp project")
    export_parser.add_argument("--project", required=True, help="Path to .sfp project")
    export_parser.add_argument(
        "--format",
        choices=["png", "jpg", "pdf"],
        required=True,
        help="Target export format",
    )
    export_parser.add_argument("--output", required=True, help="Output file path")
    export_parser.add_argument(
        "--jpg-quality",
        type=int,
        default=90,
        help="JPEG quality (1-100)",
    )
    export_parser.add_argument(
        "--pdf-dpi",
        type=int,
        default=300,
        help="PDF resolution (72-1200)",
    )

    open_parser = subparsers.add_parser("open", help="Open editor with project")
    open_parser.add_argument("--project", required=True, help="Path to .sfp project")

    return parser


def run_cli(
    argv: list[str],
    launch_gui_with_project: Callable[[str], int],
) -> int:
    """
    Executes one CLI command.

    Args:
        argv: Raw command-line arguments excluding executable path.
        launch_gui_with_project: Callback to start GUI with project file.

    Returns:
        int: Process exit code.
    """

    parser = build_cli_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 1

    if args.command == "open":
        return launch_gui_with_project(str(args.project))

    app = QApplication.instance()
    created_app = False
    if app is None:
        app = QApplication(["snappix-cli"])
        created_app = True
    app.setQuitOnLastWindowClosed(False)

    try:
        if args.command == "capture":
            return _run_capture_command(
                app=app,
                mode=str(args.mode),
                delay=max(0, int(args.delay)),
                output_path=str(args.output),
            )
        if args.command == "pick-color":
            return _run_pick_color_command(
                app=app,
                copy_to_clipboard=bool(args.clipboard),
            )
        if args.command == "export":
            return _run_export_command(
                project_path=str(args.project),
                output_path=str(args.output),
                fmt=str(args.format),
                jpg_quality=int(args.jpg_quality),
                pdf_dpi=int(args.pdf_dpi),
            )
        parser.print_help()
        return 1
    finally:
        if created_app:
            app.quit()


def _run_capture_command(
    app: QApplication,
    mode: str,
    delay: int,
    output_path: str,
) -> int:
    """
    Handles the `capture` CLI command.

    Args:
        app: Active Qt application instance.
        mode: Capture mode.
        delay: Delay before capture.
        output_path: Output file path.

    Returns:
        int: Command exit code.
    """

    resolved_path = _resolve_output_path(output_path, "png")
    if mode == CaptureMode.FULL_SCREEN:
        snapshot = capture_full_screen()
        if snapshot.pixmap.isNull():
            print("Capture failed: no screen content available.")
            return 2
        if not snapshot.pixmap.save(resolved_path, "PNG"):
            print(f"Capture failed: could not write file: {resolved_path}")
            return 2
        print(resolved_path)
        return 0

    loop = QEventLoop()
    result = {"code": 2}

    def on_capture_done(pixmap) -> None:
        if pixmap.isNull():
            result["code"] = 2
            loop.quit()
            return
        if not pixmap.save(resolved_path, "PNG"):
            result["code"] = 2
            loop.quit()
            return
        print(resolved_path)
        result["code"] = 0
        loop.quit()

    def on_capture_cancelled() -> None:
        print("Capture cancelled.")
        result["code"] = 2
        loop.quit()

    execute_capture_request(
        request=CaptureRequest(mode=mode, delay_seconds=delay),
        on_capture=on_capture_done,
        on_cancel=on_capture_cancelled,
    )
    if delay > 0:
        QTimer.singleShot((delay + 1) * 1000, lambda: None)
    loop.exec()
    return int(result["code"])


def _run_pick_color_command(app: QApplication, copy_to_clipboard: bool) -> int:
    """
    Handles the `pick-color` CLI command.

    Args:
        app: Active Qt application instance.
        copy_to_clipboard: True to copy output color into clipboard.

    Returns:
        int: Command exit code.
    """

    loop = QEventLoop()
    result = {"code": 2}

    def on_picked(hex_color: str) -> None:
        if copy_to_clipboard:
            app.clipboard().setText(hex_color)
        print(hex_color)
        result["code"] = 0
        loop.quit()

    def on_cancel() -> None:
        print("Color picking cancelled.")
        result["code"] = 2
        loop.quit()

    execute_color_pick(on_picked=on_picked, on_cancel=on_cancel)
    loop.exec()
    return int(result["code"])


def _run_export_command(
    project_path: str,
    output_path: str,
    fmt: str,
    jpg_quality: int,
    pdf_dpi: int,
) -> int:
    """
    Handles the `export` CLI command.

    Args:
        project_path: Source project file path.
        output_path: Target export file path.
        fmt: Export format (png/jpg/pdf).
        jpg_quality: JPEG quality value.
        pdf_dpi: PDF DPI value.

    Returns:
        int: Command exit code.
    """

    if not os.path.isfile(project_path):
        print(f"Export failed: project not found: {project_path}")
        return 2

    model = load_project(project_path)
    canvas = EditorCanvas()
    canvas.set_screenshot(base64_png_to_pixmap(model.screenshot_png_base64))
    canvas.load_annotations(model.annotations)
    pixmap = canvas.export_composited_pixmap()
    if pixmap.isNull():
        print("Export failed: rendered image is empty.")
        return 2

    if fmt == "png":
        target = _resolve_output_path(output_path, "png")
        if not pixmap.save(target, "PNG"):
            print(f"Export failed: could not write PNG: {target}")
            return 2
        print(target)
        return 0
    if fmt == "jpg":
        target = _resolve_output_path(output_path, "jpg")
        quality = max(1, min(100, jpg_quality))
        if not pixmap.save(target, "JPG", quality):
            print(f"Export failed: could not write JPG: {target}")
            return 2
        print(target)
        return 0

    target = _resolve_output_path(output_path, "pdf")
    _write_pdf(pixmap, target, max(72, min(1200, pdf_dpi)))
    if not os.path.isfile(target):
        print(f"Export failed: could not write PDF: {target}")
        return 2
    print(target)
    return 0


def _resolve_output_path(path_value: str, extension: str) -> str:
    """
    Ensures output path ends with the expected extension.

    Args:
        path_value: Raw output path from CLI.
        extension: Required extension without leading dot.

    Returns:
        str: Normalized output path.
    """

    suffix = f".{extension.lower()}"
    candidate = Path(path_value)
    if candidate.suffix.lower() != suffix:
        candidate = candidate.with_suffix(suffix)
    return str(candidate)


def _write_pdf(pixmap, output_path: str, dpi: int) -> None:
    """
    Exports one pixmap into a PDF document.

    Args:
        pixmap: Rendered export pixmap.
        output_path: Destination file path.
        dpi: Output resolution in DPI.

    Returns:
        None
    """

    writer = QPdfWriter(output_path)
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageOrientation(QPageLayout.Orientation.Landscape)
    writer.setResolution(dpi)
    writer.setColorModel(QPagedPaintDevice.ColorModel.Rgb)

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
