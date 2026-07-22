"""
Linux desktop autostart integration.
"""

from __future__ import annotations

from pathlib import Path


class AutostartManager:
    """
    Manages a desktop autostart entry file.
    """

    def __init__(self, desktop_path: Path) -> None:
        """
        Initializes autostart manager.

        Args:
            desktop_path: Full target path for .desktop file.
        """

        self.desktop_path = desktop_path

    def is_enabled(self) -> bool:
        """
        Checks whether autostart is currently enabled.

        Returns:
            bool: True when desktop file exists.
        """

        return self.desktop_path.exists()

    def enable(self, exec_command: str, app_name: str, icon_path: str = "") -> None:
        """
        Enables autostart by writing a desktop entry.

        Args:
            exec_command: Launch command used by desktop session.
            app_name: Visible application name.
            icon_path: Optional icon path for desktop environments.

        Returns:
            None
        """

        self.desktop_path.parent.mkdir(parents=True, exist_ok=True)
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
        self.desktop_path.write_text(content, encoding="utf-8")

    def disable(self) -> None:
        """
        Disables autostart by removing desktop entry.

        Returns:
            None
        """

        if self.desktop_path.exists():
            self.desktop_path.unlink()
