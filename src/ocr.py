"""
OCR helpers for extracting text from screenshots.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from src.platform import has_tesseract


def extract_text_from_png_bytes(png_bytes: bytes, language: str = "eng") -> str:
    """
    Runs Tesseract OCR on one PNG image buffer.

    Args:
        png_bytes: PNG encoded image bytes.
        language: Tesseract language code.

    Returns:
        str: Recognized text or empty string on failure.
    """

    if not has_tesseract() or not png_bytes:
        return ""

    with tempfile.TemporaryDirectory(prefix="snappix-ocr-") as temp_dir:
        input_path = Path(temp_dir) / "input.png"
        output_base = Path(temp_dir) / "output"
        input_path.write_bytes(png_bytes)
        try:
            subprocess.run(
                [
                    "tesseract",
                    str(input_path),
                    str(output_base),
                    "-l",
                    language,
                    "--psm",
                    "6",
                ],
                capture_output=True,
                check=True,
                timeout=60,
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        output_path = Path(f"{output_base}.txt")
        if not output_path.is_file():
            return ""
        try:
            return output_path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""


def format_ocr_copied_status(text: str, *, max_length: int = 180) -> str:
    """
    Builds a compact status-bar message for copied OCR text.

    Args:
        text: Recognized text that was copied to the clipboard.
        max_length: Maximum length of the preview portion after the prefix.

    Returns:
        str: Footer message including a single-line preview of the text.
    """

    compact = " ".join(str(text).split())
    if not compact:
        return "OCR completed, but no text was found."
    preview = compact
    if len(preview) > max_length:
        preview = f"{preview[: max_length - 1]}…"
    return f"OCR copied: {preview}"
