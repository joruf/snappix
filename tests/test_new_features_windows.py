"""
Windows contract for the new features.

The features are developed and tested on Linux, so what Windows would trip over
is asserted here explicitly instead of being discovered on the other machine:
the new code must not shell out to Linux tools, must produce file names Windows
accepts, and must not depend on X11-only behaviour.
"""

from __future__ import annotations

import ast
import pathlib
import unittest
from unittest.mock import patch

try:
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QColor, QImage, QPixmap

    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False

# Modules added or reworked in this round.
NEW_MODULES = [
    "src/document_scale.py",
    "src/drag_export.py",
    "src/i18n.py",
    "src/i18n_widgets.py",
    "src/image_size_dialog.py",
    "src/pin_window.py",
    "src/post_capture_service.py",
]

# Executables that exist on Linux only; calling one unconditionally would make a
# feature silently dead on Windows.
LINUX_ONLY_TOOLS = ("xdotool", "xwininfo", "xprop", "grim", "slurp", "xdg-open", "xwd")


class TestNoLinuxOnlyDependencies(unittest.TestCase):
    """
    Verifies the new modules stay platform neutral.
    """

    def _source(self, relative: str) -> str:
        """
        Reads one project file.

        Args:
            relative: Repository-relative path.

        Returns:
            str: File contents.
        """

        root = pathlib.Path(__file__).resolve().parent.parent
        return (root / relative).read_text(encoding="utf-8")

    def test_new_modules_call_no_linux_only_tools(self) -> None:
        """
        Ensures nothing added here depends on an X11 helper binary.
        """

        offenders = []
        for relative in NEW_MODULES:
            source = self._source(relative)
            for tool in LINUX_ONLY_TOOLS:
                if f'"{tool}"' in source or f"'{tool}'" in source:
                    offenders.append(f"{relative}: {tool}")
        self.assertEqual(offenders, [])

    def test_new_modules_build_paths_portably(self) -> None:
        """
        Ensures no hardcoded POSIX path separators or /tmp assumptions.
        """

        offenders = []
        for relative in NEW_MODULES:
            for line in self._source(relative).splitlines():
                stripped = line.strip()
                if stripped.startswith("#") or '"""' in stripped:
                    continue
                if '"/tmp' in stripped or "'/tmp" in stripped:
                    offenders.append(f"{relative}: {stripped}")
                if '"/home' in stripped or '"/usr' in stripped:
                    offenders.append(f"{relative}: {stripped}")
        self.assertEqual(offenders, [])

    def test_new_modules_parse(self) -> None:
        """
        Ensures every new module is syntactically valid, which a Windows-only
        import error would otherwise reveal first.
        """

        for relative in NEW_MODULES:
            ast.parse(self._source(relative))


class TestWindowsFilenameRules(unittest.TestCase):
    """
    Verifies saved captures get names Windows accepts.
    """

    def test_every_reserved_character_is_removed(self) -> None:
        """
        Ensures no capture can fail to save because of its name.
        """

        from src.post_capture_service import sanitize_filename_stem

        for character in '<>:"/\\|?*':
            cleaned = sanitize_filename_stem(f"na{character}me")
            self.assertNotIn(character, cleaned)

    def test_control_characters_are_removed(self) -> None:
        """
        Ensures a pasted newline cannot end up in a file name.
        """

        from src.post_capture_service import sanitize_filename_stem

        self.assertNotIn("\n", sanitize_filename_stem("a\nb"))
        self.assertNotIn("\t", sanitize_filename_stem("a\tb"))

    def test_name_length_stays_within_limits(self) -> None:
        """
        Ensures a long template cannot exceed the Windows path budget.
        """

        from src.post_capture_service import format_capture_filename

        self.assertLessEqual(len(format_capture_filename("x" * 500)), 130)

    def test_shared_file_names_are_sanitized_too(self) -> None:
        """
        Ensures the drag-out file inherits the same rules; it is written with a
        name derived from the tab title.
        """

        from src.drag_export import cleanup_session_export_dir, write_shareable_png

        try:
            image = QImage(8, 8, QImage.Format.Format_ARGB32)
            image.fill(QColor(10, 20, 30))
            path = write_shareable_png(QPixmap.fromImage(image), 'a:b*c?d"e')
            self.assertIsNotNone(path)
            for character in ':*?"':
                self.assertNotIn(character, path.name)
        finally:
            cleanup_session_export_dir()


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestWindowsBehaviour(unittest.TestCase):
    """
    Verifies the new features behave under a simulated Windows platform.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def test_capture_modes_work_without_x11_helpers(self) -> None:
        """
        Ensures the two new capture modes are pure geometry: they crop an
        existing snapshot and need no platform tool at all.
        """

        from src.capture import DesktopSnapshot, crop_snapshot_to_rect

        image = QImage(3840, 1080, QImage.Format.Format_ARGB32)
        image.fill(QColor(120, 120, 120))
        snapshot = DesktopSnapshot(
            pixmap=QPixmap.fromImage(image),
            virtual_geometry=QRect(0, 0, 3840, 1080),
        )
        with patch("src.paths.is_windows", return_value=True):
            crop = crop_snapshot_to_rect(snapshot, QRect(1920, 0, 1920, 1080))
        self.assertEqual((crop.width(), crop.height()), (1920, 1080))

    def test_gif_command_uses_no_platform_specific_input(self) -> None:
        """
        Ensures GIF export reads the recorded file, not an X11 display -- the
        recorder already handles the platform difference when capturing.
        """

        from pathlib import Path

        from src.video_recorder import build_gif_export_command

        command = build_gif_export_command(Path("in.mp4"), [], Path("out.gif"))
        joined = " ".join(command)
        self.assertNotIn("x11grab", joined)
        self.assertNotIn("gdigrab", joined)
        self.assertIn("in.mp4", joined)

    def test_pin_window_uses_portable_window_flags(self) -> None:
        """
        Ensures the pin relies on Qt flags that exist on both platforms rather
        than on an X11 window-manager hint.
        """

        from PySide6.QtCore import Qt

        from src.pin_window import PinWindow

        image = QImage(40, 30, QImage.Format.Format_ARGB32)
        image.fill(QColor(90, 90, 90))
        window = PinWindow(QPixmap.fromImage(image))
        self.addCleanup(window.close)
        flags = window.windowFlags()
        self.assertTrue(flags & Qt.WindowType.WindowStaysOnTopHint)
        self.assertTrue(flags & Qt.WindowType.FramelessWindowHint)

    def test_language_detection_reads_the_environment(self) -> None:
        """
        Ensures language detection works on Windows too, where the Linux locale
        variables are usually absent.
        """

        from src.i18n import LANGUAGE_ENGLISH, LANGUAGE_GERMAN, resolve_language

        with patch.dict("os.environ", {"LANG": "de_DE.UTF-8"}, clear=True):
            self.assertEqual(resolve_language("system"), LANGUAGE_GERMAN)
        with patch.dict("os.environ", {"LANG": "en_US.UTF-8"}, clear=True):
            self.assertEqual(resolve_language("system"), LANGUAGE_ENGLISH)
        with patch.dict("os.environ", {}, clear=True), patch(
            "locale.getlocale", return_value=(None, None)
        ):
            self.assertEqual(resolve_language("system"), LANGUAGE_ENGLISH)

    def test_share_directory_is_created_below_the_system_temp(self) -> None:
        """
        Ensures the shared-file directory follows the platform temp location
        instead of assuming /tmp.
        """

        import tempfile

        from src.drag_export import cleanup_session_export_dir, session_export_dir

        try:
            directory = session_export_dir()
            self.assertTrue(
                str(directory).startswith(tempfile.gettempdir()),
                f"{directory} is not below {tempfile.gettempdir()}",
            )
        finally:
            cleanup_session_export_dir()


if __name__ == "__main__":
    unittest.main()
