#!/usr/bin/env python3
"""
SnapAgent application entry point.
"""

from __future__ import annotations

import fcntl
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from src.autostart import AutostartManager
from src.config import AppConfig, ConfigManager
from src.constants import APP_NAME

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication
    from src.capture import CaptureRequest
    from src.editor_window import EditorWindow


_INSTANCE_LOCK_HANDLE = None
_INITIALIZED_FILE = None


def _project_root() -> Path:
    """
    Returns project root path.

    Returns:
        Path: Project root.
    """

    return Path(__file__).resolve().parent


_INITIALIZED_FILE = _project_root() / ".initialized"


def _icon_path() -> Path:
    """
    Returns the application icon path.

    Returns:
        Path: Icon file path.
    """

    return _project_root() / "assets" / "snapagent.svg"


def _editor_icon_path() -> Path:
    """
    Returns the red editor icon path.

    Returns:
        Path: Editor icon file path.
    """

    return _project_root() / "assets" / "snapagent-red.svg"


def _resolve_venv_python(project_root: Path) -> Path:
    """
    Resolves preferred .venv Python interpreter.

    Args:
        project_root: Project root folder.

    Returns:
        Path: Python executable path.
    """

    python3_path = project_root / ".venv" / "bin" / "python3"
    if python3_path.exists():
        return python3_path
    return project_root / ".venv" / "bin" / "python"


def _reexec_into_venv_if_available(project_root: Path) -> None:
    """
    Re-executes current process with local .venv Python.

    Args:
        project_root: Project root folder.

    Returns:
        None
    """

    if os.environ.get("SNAPAGENT_REEXECUTED") == "1":
        return

    venv_python = _resolve_venv_python(project_root)
    if not venv_python.exists():
        return
    if Path(sys.executable).resolve() == venv_python.resolve():
        return

    env = dict(os.environ)
    env["SNAPAGENT_REEXECUTED"] = "1"
    os.execve(
        str(venv_python),
        [str(venv_python), str(project_root / "run.py"), *sys.argv[1:]],
        env,
    )


def _ensure_qt_runtime() -> int:
    """
    Ensures PySide6 is installed, using GUI installer if needed.

    Returns:
        int: 0 when runtime exists, else non-zero.
    """

    try:
        import PySide6  # noqa: F401
    except ModuleNotFoundError:
        from src.install_progress_gui import run_installer_with_progress_gui

        install_code = run_installer_with_progress_gui()
        if install_code != 0:
            return install_code

        venv_python = _resolve_venv_python(_project_root())
        if not venv_python.exists():
            print("SnapAgent setup failed: .venv interpreter missing after installation.")
            return 1

        env = dict(os.environ)
        env["SNAPAGENT_REEXECUTED"] = "1"
        os.execve(
            str(venv_python),
            [str(venv_python), str(_project_root() / "run.py"), *sys.argv[1:]],
            env,
        )

    return 0


def _autostart_exec_command() -> str:
    """
    Builds shell-safe autostart launch command.

    Returns:
        str: Command string for desktop entry.
    """

    script_path = _project_root() / "start_snapagent_desktop.py"
    return f"python3 \"{script_path}\""


def _user_desktop_dir() -> Path:
    """
    Resolves the user's desktop folder with XDG and localization fallback.

    Returns:
        Path: Preferred desktop folder path.
    """

    user_dirs_file = Path.home() / ".config" / "user-dirs.dirs"
    if user_dirs_file.is_file():
        try:
            for raw_line in user_dirs_file.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if not line.startswith("XDG_DESKTOP_DIR="):
                    continue
                value = line.split("=", 1)[1].strip().strip('"')
                if value.startswith("$HOME/"):
                    return Path.home() / value[len("$HOME/"):]
                if value == "$HOME":
                    return Path.home()
                return Path(value).expanduser()
        except OSError:
            pass

    for folder_name in ("Desktop", "Schreibtisch"):
        candidate = Path.home() / folder_name
        if candidate.is_dir():
            return candidate
    return Path.home() / "Desktop"


def _desktop_shortcut_content() -> str:
    """
    Builds desktop shortcut content for direct app start.

    Returns:
        str: Desktop entry file content.
    """

    return (
        "[Desktop Entry]\n"
        "Version=1.0\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        "Comment=Screenshot and annotation tool\n"
        f"Exec={_autostart_exec_command()}\n"
        f"Icon={_icon_path()}\n"
        "Terminal=false\n"
        "Categories=Graphics;Utility;\n"
        "StartupWMClass=snapagent\n"
        "StartupNotify=true\n"
    )


def _install_desktop_shortcut() -> bool:
    """
    Creates a launch shortcut on the user's desktop folder.

    Returns:
        bool: True on success, otherwise False.
    """

    try:
        desktop_dir = _user_desktop_dir()
        desktop_dir.mkdir(parents=True, exist_ok=True)
        shortcut_path = desktop_dir / "SnapAgent.desktop"
        shortcut_path.write_text(_desktop_shortcut_content(), encoding="utf-8")
        mode = shortcut_path.stat().st_mode
        shortcut_path.chmod(mode | 0o111)
        return True
    except OSError:
        return False


def _mark_initialized() -> None:
    """
    Creates first-run marker file in the project root.

    Returns:
        None
    """

    try:
        _INITIALIZED_FILE.touch(exist_ok=True)
    except OSError:
        pass


def _maybe_prompt_desktop_shortcut() -> None:
    """
    Asks once on first start whether a desktop shortcut should be created.

    Returns:
        None
    """

    if _INITIALIZED_FILE.exists():
        return

    from PySide6.QtWidgets import QMessageBox

    answer = QMessageBox.question(
        None,
        "Desktop Shortcut",
        "Would you like to create a desktop shortcut for SnapAgent?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes,
    )
    if answer == QMessageBox.StandardButton.Yes:
        if not _install_desktop_shortcut():
            QMessageBox.warning(
                None,
                "Desktop Shortcut",
                "Could not create the desktop shortcut.",
            )
    _mark_initialized()


def _ensure_desktop_launcher() -> None:
    """
    Ensures a user-local desktop launcher exists for taskbar integration.

    Returns:
        None
    """

    launcher_dir = Path.home() / ".local" / "share" / "applications"
    launcher_path = launcher_dir / "snapagent.desktop"
    editor_launcher_path = launcher_dir / "snapagent-editor.desktop"
    launcher_dir.mkdir(parents=True, exist_ok=True)
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        "Comment=Screenshot and annotation tool\n"
        f"Exec={_autostart_exec_command()}\n"
        f"Icon={_icon_path()}\n"
        "Terminal=false\n"
        "Categories=Graphics;Utility;\n"
        "StartupWMClass=snapagent\n"
    )
    launcher_path.write_text(content, encoding="utf-8")
    editor_content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME} Editor\n"
        "Comment=Screenshot editor window identity\n"
        f"Exec={_autostart_exec_command()}\n"
        f"Icon={_editor_icon_path()}\n"
        "Terminal=false\n"
        "Categories=Graphics;Utility;\n"
        "StartupWMClass=snapagent-editor\n"
        "NoDisplay=true\n"
    )
    editor_launcher_path.write_text(editor_content, encoding="utf-8")


def _acquire_single_instance_lock() -> bool:
    """
    Acquires a non-blocking process lock to enforce single instance.

    Returns:
        bool: True when lock was acquired, otherwise False.
    """

    global _INSTANCE_LOCK_HANDLE
    lock_dir = Path.home() / ".cache" / "snapagent"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / "snapagent.lock"
    handle = lock_path.open("w", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return False
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    _INSTANCE_LOCK_HANDLE = handle
    return True


class AppController:
    """
    Coordinates capture panel, editor windows, and app settings.
    """

    def __init__(self, app: QApplication) -> None:
        """
        Initializes controller state.

        Args:
            app: Qt application instance.
        """

        from PySide6.QtCore import Qt, Signal
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import QMainWindow, QMenu, QMessageBox, QSystemTrayIcon, QTabWidget
        from src.capture import CapturePanel

        class EditorHostWindow(QMainWindow):
            close_requested = Signal()

            def __init__(self) -> None:
                super().__init__()
                self._minimize_to_tray_on_close = True

            def set_minimize_to_tray_on_close(self, enabled: bool) -> None:
                self._minimize_to_tray_on_close = enabled

            def closeEvent(self, event) -> None:
                if self._minimize_to_tray_on_close:
                    self.close_requested.emit()
                    event.ignore()
                    return
                super().closeEvent(event)

        self._QMessageBox = QMessageBox
        self.app = app
        self._is_quitting = False
        self._tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        self.capture_panel = CapturePanel()
        self.capture_panel.capture_requested.connect(self.start_capture)
        self.capture_panel.autostart_toggled.connect(self.toggle_autostart)
        self.capture_panel.close_requested.connect(self._hide_to_tray)
        self.capture_panel.editor_requested.connect(self.open_editor_from_capture)
        self.editors: list[EditorWindow] = []

        config_dir = Path.home() / ".config" / "snapagent"
        self.config_manager = ConfigManager(config_dir / "config.json")
        self.autostart_manager = AutostartManager(
            Path.home() / ".config" / "autostart" / "snapagent.desktop"
        )
        self.config: AppConfig = self.config_manager.load()
        if self.autostart_manager.is_enabled():
            self.config.autostart_enabled = True
        self.capture_panel.set_autostart_checked(self.config.autostart_enabled)
        self.editor_host = EditorHostWindow()
        self.editor_host.setWindowTitle(f"{APP_NAME} Editor")
        self.editor_host.resize(1400, 900)
        self.editor_tabs = QTabWidget(self.editor_host)
        self.editor_tabs.setTabsClosable(True)
        self.editor_tabs.tabCloseRequested.connect(self._close_editor_tab_by_index)
        self.editor_host.setCentralWidget(self.editor_tabs)
        self.editor_host.close_requested.connect(self._hide_to_tray)

        self.tray_icon = QSystemTrayIcon(self.app.windowIcon(), self.capture_panel)
        if self._tray_available:
            self.tray_icon.setToolTip(APP_NAME)
            tray_menu = QMenu()
            show_action = QAction("Show SnapAgent", tray_menu)
            show_action.triggered.connect(self._show_from_tray)
            tray_menu.addAction(show_action)
            tray_menu.addSeparator()
            capture_region_action = QAction("Capture Area", tray_menu)
            capture_region_action.triggered.connect(self.capture_region_from_tray)
            tray_menu.addAction(capture_region_action)
            capture_window_action = QAction("Capture Window Under Cursor", tray_menu)
            capture_window_action.triggered.connect(self.capture_window_from_tray)
            tray_menu.addAction(capture_window_action)
            tray_menu.addSeparator()
            self.autostart_tray_action = QAction("Start at boot", tray_menu)
            self.autostart_tray_action.setCheckable(True)
            self.autostart_tray_action.setChecked(self.config.autostart_enabled)
            self.autostart_tray_action.toggled.connect(self.toggle_autostart)
            tray_menu.addAction(self.autostart_tray_action)
            tray_menu.addSeparator()
            about_action = QAction("About", tray_menu)
            about_action.triggered.connect(self.show_about_dialog)
            tray_menu.addAction(about_action)
            quit_action = QAction("Quit SnapAgent", tray_menu)
            quit_action.triggered.connect(self.quit_application)
            tray_menu.addAction(quit_action)
            self.tray_icon.setContextMenu(tray_menu)
            self.tray_icon.activated.connect(self._on_tray_activated)
            self.tray_icon.show()
        else:
            self.capture_panel.set_minimize_to_tray_on_close(False)
            self.editor_host.set_minimize_to_tray_on_close(False)

    def show(self) -> None:
        """
        Shows the capture panel.

        Returns:
            None
        """

        self.app.setWindowIcon(self.capture_panel.windowIcon())
        self.app.setDesktopFileName("snapagent")
        self.capture_panel.show()

    def start_capture(self, request: CaptureRequest) -> None:
        """
        Starts screenshot capture sequence.

        Args:
            request: Capture request payload.

        Returns:
            None
        """

        from src.capture import execute_capture_request
        from src.editor_window import EditorWindow

        self.capture_panel.hide()

        def on_capture_done(pixmap) -> None:
            if pixmap.isNull():
                self._QMessageBox.warning(
                    self.capture_panel,
                    "Capture Error",
                    "No screenshot could be captured.",
                )
                self.capture_panel.show()
                return

            editor = EditorWindow(pixmap)
            editor.setWindowIcon(self.editor_host.windowIcon())
            editor.set_minimize_to_tray_on_close(False)
            editor.setParent(self.editor_tabs)
            tab_index = self.editor_tabs.addTab(
                editor,
                f"Screenshot {self.editor_tabs.count() + 1}",
            )
            self.editor_tabs.setCurrentIndex(tab_index)
            self.app.setWindowIcon(self.editor_host.windowIcon())
            self.app.setDesktopFileName("snapagent-editor")
            self._ensure_editor_host_geometry()
            self.editor_host.show()
            self.editor_host.raise_()
            self.editor_host.activateWindow()
            editor.show()
            editor.destroyed.connect(lambda *_: self._on_editor_closed(editor))
            self.editors.append(editor)
            self.capture_panel.show()

        def on_capture_cancelled() -> None:
            self.capture_panel.show()

        execute_capture_request(
            request=request,
            on_capture=on_capture_done,
            on_cancel=on_capture_cancelled,
        )

    def toggle_autostart(self, enabled: bool) -> None:
        """
        Enables or disables autostart.

        Args:
            enabled: Desired autostart state.

        Returns:
            None
        """

        try:
            if enabled:
                self.autostart_manager.enable(
                    _autostart_exec_command(),
                    APP_NAME,
                    str(_icon_path()),
                )
            else:
                self.autostart_manager.disable()
        except OSError as exc:
            self._QMessageBox.warning(
                self.capture_panel,
                "Autostart Error",
                f"Could not update autostart setting:\n{exc}",
            )
            self.capture_panel.set_autostart_checked(self.autostart_manager.is_enabled())
            return

        self.config.autostart_enabled = enabled
        self.config_manager.save(self.config)
        self.capture_panel.set_autostart_checked(enabled)
        if self._tray_available:
            self.autostart_tray_action.blockSignals(True)
            self.autostart_tray_action.setChecked(enabled)
            self.autostart_tray_action.blockSignals(False)

    def open_editor_from_capture(self) -> None:
        """
        Opens editor host from capture panel without changing capture tool state.

        Returns:
            None
        """

        if self.editor_tabs.count() == 0:
            from PySide6.QtGui import QColor, QPixmap
            from src.editor_window import EditorWindow

            blank_pixmap = QPixmap(1280, 720)
            blank_pixmap.fill(QColor(255, 255, 255, 255))

            editor = EditorWindow(blank_pixmap)
            editor.setWindowIcon(self.editor_host.windowIcon())
            editor.set_minimize_to_tray_on_close(False)
            editor.setParent(self.editor_tabs)
            tab_index = self.editor_tabs.addTab(editor, "New Canvas")
            self.editor_tabs.setCurrentIndex(tab_index)
            editor.show()
            editor.destroyed.connect(lambda *_: self._on_editor_closed(editor))
            self.editors.append(editor)
        self.app.setWindowIcon(self.editor_host.windowIcon())
        self.app.setDesktopFileName("snapagent-editor")
        self._ensure_editor_host_geometry()
        self.editor_host.show()
        self.editor_host.raise_()
        self.editor_host.activateWindow()

    def capture_region_from_tray(self) -> None:
        """
        Starts region capture directly from tray menu.

        Returns:
            None
        """

        from src.capture import CaptureMode, CaptureRequest

        request = CaptureRequest(
            mode=CaptureMode.REGION,
            delay_seconds=int(self.capture_panel.delay_spin.value()),
        )
        self.start_capture(request)

    def capture_window_from_tray(self) -> None:
        """
        Starts window-under-cursor capture directly from tray menu.

        Returns:
            None
        """

        from src.capture import CaptureMode, CaptureRequest

        request = CaptureRequest(
            mode=CaptureMode.WINDOW,
            delay_seconds=int(self.capture_panel.delay_spin.value()),
        )
        self.start_capture(request)

    def _on_editor_closed(self, editor: EditorWindow) -> None:
        """
        Removes closed editor from tracking list.

        Args:
            editor: Closed editor window.

        Returns:
            None
        """

        if self._is_quitting:
            return
        if editor in self.editors:
            self.editors.remove(editor)
        try:
            tab_index = self.editor_tabs.indexOf(editor)
            if tab_index >= 0:
                self.editor_tabs.removeTab(tab_index)
            if self.editor_tabs.count() == 0:
                self.editor_host.hide()
                self.app.setWindowIcon(self.capture_panel.windowIcon())
                self.app.setDesktopFileName("snapagent")
        except RuntimeError:
            return

    def _ensure_editor_host_geometry(self) -> None:
        """
        Ensures editor host window opens with usable geometry.

        Returns:
            None
        """

        from PySide6.QtGui import QGuiApplication

        if self.editor_host.width() >= 900 and self.editor_host.height() >= 600:
            return
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.editor_host.resize(1400, 900)
            return
        available = screen.availableGeometry()
        width = max(1200, int(available.width() * 0.8))
        height = max(700, int(available.height() * 0.8))
        self.editor_host.resize(width, height)
    def _close_editor_tab_by_index(self, index: int) -> None:
        """
        Closes one editor tab and disposes its resources.

        Args:
            index: Target tab index.

        Returns:
            None
        """

        tab_widget = self.editor_tabs.widget(index)
        if tab_widget is None:
            return
        self.editor_tabs.removeTab(index)
        if tab_widget in self.editors:
            self.editors.remove(tab_widget)
        tab_widget.deleteLater()
        if self.editor_tabs.count() == 0:
            self.editor_host.hide()

    def _hide_to_tray(self) -> None:
        """
        Hides all windows and keeps app running in system tray.

        Returns:
            None
        """

        if self._is_quitting:
            return
        if not self._tray_available:
            return
        self.capture_panel.hide()
        self.editor_host.hide()
        if self.tray_icon.isVisible():
            self.tray_icon.showMessage(
                APP_NAME,
                "Running in system tray. Use tray menu to reopen or quit.",
                self.tray_icon.MessageIcon.Information,
                2500,
            )

    def _show_from_tray(self) -> None:
        """
        Restores the main capture panel from system tray.

        Returns:
            None
        """

        self.capture_panel.show()
        self.capture_panel.raise_()
        self.capture_panel.activateWindow()
        if self.editor_tabs.count() > 0:
            self.app.setWindowIcon(self.editor_host.windowIcon())
            self.app.setDesktopFileName("snapagent-editor")
            self.editor_host.show()
            self.editor_host.raise_()
            self.editor_host.activateWindow()
            return
        self.app.setWindowIcon(self.capture_panel.windowIcon())
        self.app.setDesktopFileName("snapagent")

    def _on_tray_activated(self, reason) -> None:
        """
        Restores app on tray icon activation.

        Args:
            reason: Activation reason from Qt.

        Returns:
            None
        """

        from PySide6.QtWidgets import QSystemTrayIcon

        if reason in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            self._show_from_tray()

    def quit_application(self) -> None:
        """
        Completely exits SnapAgent.

        Returns:
            None
        """

        self._is_quitting = True
        self.capture_panel.set_minimize_to_tray_on_close(False)
        self.editor_host.set_minimize_to_tray_on_close(False)
        while self.editor_tabs.count() > 0:
            self._close_editor_tab_by_index(0)
        self.editor_host.close()
        self.capture_panel.close()
        self.tray_icon.hide()
        self.app.quit()

    def show_about_dialog(self) -> None:
        """
        Shows About dialog with project and maintainer information.

        Returns:
            None
        """

        self._QMessageBox.information(
            None,
            f"About {APP_NAME}",
            (
                f"{APP_NAME}\n"
                "Screenshot and annotation tool inspired by SnagIt.\n\n"
                "Joachim Ruf\n"
                "Loresoft\n"
                "https://www.loresoft.de\n"
            ),
        )


def main() -> int:
    """
    Launches the SnapAgent desktop application.

    Returns:
        int: Process exit code.
    """

    _reexec_into_venv_if_available(_project_root())
    runtime_code = _ensure_qt_runtime()
    if runtime_code != 0:
        return runtime_code
    if not _acquire_single_instance_lock():
        print("SnapAgent is already running.")
        return 0
    _ensure_desktop_launcher()

    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setDesktopFileName("snapagent")
    app.setQuitOnLastWindowClosed(False)
    capture_icon = QIcon(str(_icon_path()))
    editor_icon = QIcon(str(_editor_icon_path()))
    app.setWindowIcon(capture_icon)
    _maybe_prompt_desktop_shortcut()
    controller = AppController(app)
    controller.capture_panel.setWindowIcon(capture_icon)
    controller.editor_host.setWindowIcon(editor_icon)
    controller.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

