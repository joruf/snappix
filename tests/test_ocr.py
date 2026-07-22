"""
Unit tests for OCR text extraction helpers.
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.ocr import extract_text_from_png_bytes, format_ocr_copied_status


class TestOcr(unittest.TestCase):
    """
    Verifies OCR wrapper behavior around Tesseract.
    """

    @patch("src.ocr.has_tesseract", return_value=False)
    def test_extract_text_returns_empty_without_tesseract(self, _mock_tesseract: MagicMock) -> None:
        """
        Ensures OCR returns empty string when tesseract is unavailable.
        """

        self.assertEqual(extract_text_from_png_bytes(b"png"), "")

    @patch("src.ocr.has_tesseract", return_value=True)
    def test_extract_text_returns_empty_for_empty_input(self, _mock_tesseract: MagicMock) -> None:
        """
        Ensures empty PNG input yields empty output.
        """

        self.assertEqual(extract_text_from_png_bytes(b""), "")

    @patch("src.ocr.subprocess.run")
    @patch("src.ocr.has_tesseract", return_value=True)
    def test_extract_text_reads_tesseract_output(
        self,
        _mock_tesseract: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        """
        Ensures recognized text is read from the tesseract output file.
        """

        def fake_run(command: list[str], **_kwargs) -> MagicMock:
            output_base = command[2]
            Path(f"{output_base}.txt").write_text("Hello OCR\n", encoding="utf-8")
            return MagicMock()

        mock_run.side_effect = fake_run
        text = extract_text_from_png_bytes(b"fake-png-bytes")
        self.assertEqual(text, "Hello OCR")

    @patch("src.ocr.subprocess.run")
    @patch("src.ocr.has_tesseract", return_value=True)
    def test_extract_text_handles_subprocess_failure(
        self,
        _mock_tesseract: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        """
        Ensures subprocess errors return empty string.
        """

        mock_run.side_effect = subprocess.SubprocessError("failed")
        self.assertEqual(extract_text_from_png_bytes(b"fake-png"), "")

    def test_format_ocr_copied_status_includes_text_preview(self) -> None:
        """
        Ensures the footer message includes a compact OCR text preview.
        """

        self.assertEqual(
            format_ocr_copied_status("Hello\n  world"),
            "OCR copied: Hello world",
        )
        long_text = "a" * 250
        formatted = format_ocr_copied_status(long_text, max_length=40)
        self.assertTrue(formatted.startswith("OCR copied: "))
        self.assertLessEqual(len(formatted) - len("OCR copied: "), 40)
        self.assertTrue(formatted.endswith("…"))
