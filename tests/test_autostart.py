"""
Unit tests for Linux autostart integration.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.autostart import AutostartManager


class TestAutostartManager(unittest.TestCase):
    """
    Verifies enable/disable desktop entry operations.
    """

    def test_enable_writes_desktop_file(self) -> None:
        """
        Ensures desktop entry contains required launch fields.
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            desktop_path = Path(tmp_dir) / "autostart" / "snappix.desktop"
            manager = AutostartManager(desktop_path)
            manager.enable(
                exec_command="/usr/bin/python3 /app/run.py",
                app_name="Snappix",
                icon_path="/app/assets/snappix.svg",
            )

            self.assertTrue(desktop_path.exists())
            content = desktop_path.read_text(encoding="utf-8")
            self.assertIn("Type=Application", content)
            self.assertIn("Name=Snappix", content)
            self.assertIn("Exec=/usr/bin/python3 /app/run.py", content)
            self.assertIn("Icon=/app/assets/snappix.svg", content)
            self.assertIn("StartupWMClass=snappix", content)
            self.assertTrue(manager.is_enabled())

    def test_disable_removes_desktop_file(self) -> None:
        """
        Ensures disabling autostart removes the entry file.
        """

        with tempfile.TemporaryDirectory() as tmp_dir:
            desktop_path = Path(tmp_dir) / "autostart" / "snappix.desktop"
            desktop_path.parent.mkdir(parents=True, exist_ok=True)
            desktop_path.write_text("x", encoding="utf-8")
            manager = AutostartManager(desktop_path)

            self.assertTrue(manager.is_enabled())
            manager.disable()
            self.assertFalse(manager.is_enabled())

