"""
Desktop autostart integration (Linux XDG and Windows Startup folder).
"""

from __future__ import annotations

from pathlib import Path

from src.paths import is_windows


class AutostartManager:
    """
    Manages an autostart entry for the current desktop session.
    """

    def __init__(self, entry_path: Path) -> None:
        """
        Initializes autostart manager.

        Args:
            entry_path: Full target path for the autostart file
                (``.desktop`` on Linux, ``.bat`` on Windows).
        """

        self.entry_path = entry_path
        # Backward-compatible alias used by older call sites / tests.
        self.desktop_path = entry_path

    def is_enabled(self) -> bool:
        """
        Checks whether autostart is currently enabled.

        Returns:
            bool: True when the autostart entry file exists.
        """

        return self.entry_path.exists()

    def enable(self, exec_command: str, app_name: str, icon_path: str = "") -> None:
        """
        Enables autostart by writing a platform-specific entry.

        Args:
            exec_command: Launch command used by the desktop session.
            app_name: Visible application name.
            icon_path: Optional icon path (Linux desktop entries only).

        Returns:
            None
        """

        self.entry_path.parent.mkdir(parents=True, exist_ok=True)
        if is_windows() or self.entry_path.suffix.lower() == ".bat":
            content = (
                "@echo off\r\n"
                f"rem {app_name} autostart\r\n"
                f'start "" {exec_command}\r\n'
            )
            self.entry_path.write_text(content, encoding="utf-8", newline="\r\n")
        else:
            content = (
                "[Desktop Entry]\n"
                "Type=Application\n"
                f"Name={app_name}\n"
                "Comment=Screenshot and annotation tool\n"
                f"Exec={exec_command}\n"
                f"Icon={icon_path}\n"
                "Terminal=false\n"
                "StartupWMClass=snappix\n"
                "X-GNOME-Autostart-enabled=true\n"
            )
            self.entry_path.write_text(content, encoding="utf-8")
        from src.install_manifest import record_user_file

        record_user_file(self.entry_path)

    def disable(self) -> None:
        """
        Disables autostart by removing the entry file.

        Returns:
            None
        """

        if self.entry_path.exists():
            self.entry_path.unlink()
