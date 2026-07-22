#!/usr/bin/env python3
"""
Snappix application entry point.
"""

from __future__ import annotations

import fcntl
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING


def _prepare_linux_session_env() -> None:
    """
    Prepares Linux session environment before GUI libraries initialize.

    Returns:
        None
    """

    if sys.platform != "linux":
        return

    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", "").strip()
    if not runtime_dir:
        return

    dconf_user = Path(runtime_dir) / "dconf" / "user"
    if dconf_user.exists() and not os.access(dconf_user, os.W_OK):
        os.environ.setdefault("GSETTINGS_BACKEND", "memory")


_prepare_linux_session_env()

from src.autostart import AutostartManager
from src.config import (
    EDITOR_LAST_TAB_CLOSE_WINDOW,
    POST_CAPTURE_CLIPBOARD,
    POST_CAPTURE_SAVE,
    AppConfig,
    ConfigManager,
    default_capture_save_directory,
    normalize_export_preset,
)
from src.constants import ABOUT_GITHUB, APP_FILE_EXTENSION, APP_NAME
from src.theme import (
    THEME_DARK,
    THEME_LIGHT,
    build_application_stylesheet,
    build_editor_accent_stylesheet,
    normalize_theme_name,
    set_current_theme,
)

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

    return _project_root() / "assets" / "snappix.svg"


def _editor_icon_path() -> Path:
    """
    Returns the red editor icon path.

    Returns:
        Path: Editor icon file path.
    """

    return _project_root() / "assets" / "snappix-red.svg"


def _build_capture_icon():
    """
    Builds the blue capture taskbar icon.

    Returns:
        QIcon: Capture icon with theme fallback.
    """

    from PySide6.QtGui import QIcon

    return QIcon.fromTheme("snappix", QIcon(str(_icon_path())))


def _build_editor_icon():
    """
    Builds the red editor taskbar icon.

    Returns:
        QIcon: Editor icon with theme fallback.
    """

    from PySide6.QtGui import QIcon

    return QIcon.fromTheme("snappix-editor", QIcon(str(_editor_icon_path())))


def _refresh_icon_theme_cache(hicolor_dir: Path) -> None:
    """
    Refreshes the local hicolor icon cache when possible.

    Args:
        hicolor_dir: Hicolor icon theme directory.

    Returns:
        None
    """

    cache_tool = shutil.which("gtk-update-icon-cache")
    if cache_tool is None:
        return
    try:
        subprocess.run(
            [cache_tool, "-f", "-t", str(hicolor_dir)],
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def _install_application_icons() -> None:
    """
    Installs capture and editor icons into the local icon theme.

    Returns:
        None
    """

    icon_root = (
        Path.home() / ".local" / "share" / "icons" / "hicolor" / "scalable" / "apps"
    )
    icon_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_icon_path(), icon_root / "snappix.svg")
    shutil.copy2(_editor_icon_path(), icon_root / "snappix-editor.svg")
    _refresh_icon_theme_cache(icon_root.parent.parent)


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

    if os.environ.get("SNAPPIX_REEXECUTED") == "1":
        return

    venv_python = _resolve_venv_python(project_root)
    if not venv_python.exists():
        return
    if Path(sys.executable).resolve() == venv_python.resolve():
        return

    env = dict(os.environ)
    env["SNAPPIX_REEXECUTED"] = "1"
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
            print("Snappix setup failed: .venv interpreter missing after installation.")
            return 1

        env = dict(os.environ)
        env["SNAPPIX_REEXECUTED"] = "1"
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

    script_path = _project_root() / "run.py"
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
        "StartupWMClass=snappix\n"
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
        shortcut_path = desktop_dir / "Snappix.desktop"
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
        "Would you like to create a desktop shortcut for Snappix?",
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

    _install_application_icons()
    launcher_dir = Path.home() / ".local" / "share" / "applications"
    launcher_path = launcher_dir / "snappix.desktop"
    editor_launcher_path = launcher_dir / "snappix-editor.desktop"
    launcher_dir.mkdir(parents=True, exist_ok=True)
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        "Comment=Screenshot and annotation tool\n"
        f"Exec={_autostart_exec_command()}\n"
        "Icon=snappix\n"
        "Terminal=false\n"
        "Categories=Graphics;Utility;\n"
        "StartupWMClass=snappix\n"
    )
    launcher_path.write_text(content, encoding="utf-8")
    editor_content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME} Editor\n"
        "Comment=Screenshot editor window identity\n"
        f"Exec={_autostart_exec_command()}\n"
        "Icon=snappix-editor\n"
        "Terminal=false\n"
        "Categories=Graphics;Utility;\n"
        "StartupWMClass=snappix-editor\n"
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
    lock_dir = Path.home() / ".cache" / "snappix"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / "snappix.lock"
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

    def __init__(self, app: QApplication, startup_project_path: str = "") -> None:
        """
        Initializes controller state.

        Args:
            app: Qt application instance.
        """

        from PySide6.QtCore import Qt, Signal
        from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QShortcut
        from PySide6.QtWidgets import (
            QFileDialog,
            QHBoxLayout,
            QLabel,
            QMainWindow,
            QMenu,
            QMessageBox,
            QPushButton,
            QStackedWidget,
            QSystemTrayIcon,
            QTabWidget,
            QVBoxLayout,
            QWidget,
        )
        from src.capture import CapturePanel

        class EditorHostWindow(QMainWindow):
            close_requested = Signal()

            def __init__(self) -> None:
                super().__init__()
                self.setObjectName("editorHost")
                self._minimize_to_tray_on_close = True

            def set_minimize_to_tray_on_close(self, enabled: bool) -> None:
                self._minimize_to_tray_on_close = enabled

            def showEvent(self, event) -> None:
                from src.platform import apply_linux_window_identity

                apply_linux_window_identity(
                    self,
                    desktop_file_name="snappix-editor",
                    wm_instance="snappix-editor",
                    wm_class="snappix-editor",
                )
                super().showEvent(event)

            def closeEvent(self, event) -> None:
                if self._minimize_to_tray_on_close:
                    self.close_requested.emit()
                    event.ignore()
                    return
                super().closeEvent(event)

        self._QMessageBox = QMessageBox
        self.app = app
        self._startup_project_path = startup_project_path.strip()
        self._is_quitting = False
        self._tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        self._capture_icon = _build_capture_icon()
        self._editor_icon = _build_editor_icon()
        self.capture_panel = CapturePanel()
        self.capture_panel.setWindowIcon(self._capture_icon)
        self.capture_panel.capture_requested.connect(self.start_capture)
        self.capture_panel.color_pick_requested.connect(self.start_color_pick)
        self.capture_panel.autostart_toggled.connect(self.toggle_autostart)
        self.capture_panel.close_requested.connect(self._on_capture_panel_close)
        self.capture_panel.editor_requested.connect(self.open_editor_from_capture)
        self.editors: list[EditorWindow] = []

        config_dir = Path.home() / ".config" / "snappix"
        self.config_manager = ConfigManager(config_dir / "config.json")
        self.autostart_manager = AutostartManager(
            Path.home() / ".config" / "autostart" / "snappix.desktop"
        )
        self.config: AppConfig = self.config_manager.load()
        if self.autostart_manager.is_enabled():
            self.config.autostart_enabled = True
            try:
                # Refresh legacy/broken autostart entries to current Exec command.
                self.autostart_manager.enable(
                    _autostart_exec_command(),
                    APP_NAME,
                    str(_icon_path()),
                )
            except OSError:
                pass
        self.capture_panel.set_autostart_checked(self.config.autostart_enabled)

        from src.global_hotkeys import GlobalHotkeyManager, HotkeyBridge

        self._hotkey_bridge = HotkeyBridge()
        self._hotkey_bridge.triggered.connect(self._on_global_hotkey)
        self._hotkey_manager = GlobalHotkeyManager(self._hotkey_bridge)
        self._capture_in_progress = False
        self.editor_host = EditorHostWindow()
        self.editor_host.setWindowIcon(self._editor_icon)
        self.editor_host.setWindowTitle(f"{APP_NAME} Editor")
        self.editor_host.resize(1240, 860)
        self.editor_stack = QStackedWidget(self.editor_host)
        self.editor_tabs = QTabWidget(self.editor_stack)
        self.editor_tabs.setTabsClosable(True)
        self.editor_tabs.tabCloseRequested.connect(self._close_editor_tab_by_index)
        self.editor_empty_state = QWidget(self.editor_stack)
        empty_layout = QVBoxLayout(self.editor_empty_state)
        empty_layout.setContentsMargins(40, 40, 40, 40)
        empty_layout.setSpacing(14)
        empty_layout.addStretch(1)
        empty_title = QLabel("No open tabs")
        empty_title.setObjectName("editorEmptyTitle")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_title)
        empty_text = QLabel(
            "Create a new canvas or open an existing Snappix project."
        )
        empty_text.setObjectName("editorEmptyText")
        empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_text)
        empty_actions = QHBoxLayout()
        empty_actions.setSpacing(10)
        empty_actions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        new_canvas_button = QPushButton("New Canvas")
        new_canvas_button.setToolTip("Create a blank canvas (Ctrl+N).")
        new_canvas_button.clicked.connect(
            lambda: self.create_new_canvas_tab(self.editor_host),
        )
        empty_actions.addWidget(new_canvas_button)
        new_tab_button = QPushButton("New Tab")
        new_tab_button.setToolTip("Open a new empty editor tab (Ctrl+T).")
        new_tab_button.clicked.connect(self.create_empty_editor_tab)
        empty_actions.addWidget(new_tab_button)
        open_project_button = QPushButton("Open Project")
        open_project_button.setToolTip("Open an existing project file (Ctrl+O).")
        open_project_button.clicked.connect(self._open_project_from_editor_host)
        empty_actions.addWidget(open_project_button)
        empty_layout.addLayout(empty_actions)
        empty_layout.addStretch(1)
        self.editor_stack.addWidget(self.editor_empty_state)
        self.editor_stack.addWidget(self.editor_tabs)
        self.editor_host.setCentralWidget(self.editor_stack)
        self._sync_editor_host_view()
        self._host_shortcuts: dict[str, object] = {}
        self._install_host_editor_shortcuts()
        self.editor_host.close_requested.connect(self._on_editor_host_close)
        self._QFileDialog = QFileDialog

        self.tray_icon = QSystemTrayIcon(self.app.windowIcon(), self.capture_panel)
        if self._tray_available:
            self.tray_icon.setToolTip(APP_NAME)
            tray_menu = QMenu()
            show_action = QAction("Show Snappix", tray_menu)
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
            theme_menu = tray_menu.addMenu("Theme")
            self._theme_action_group = QActionGroup(tray_menu)
            self._theme_action_group.setExclusive(True)
            self.theme_dark_action = QAction("Dark", theme_menu)
            self.theme_dark_action.setCheckable(True)
            self.theme_dark_action.triggered.connect(
                lambda: self.set_theme(THEME_DARK)
            )
            self._theme_action_group.addAction(self.theme_dark_action)
            theme_menu.addAction(self.theme_dark_action)
            self.theme_light_action = QAction("Light", theme_menu)
            self.theme_light_action.setCheckable(True)
            self.theme_light_action.triggered.connect(
                lambda: self.set_theme(THEME_LIGHT)
            )
            self._theme_action_group.addAction(self.theme_light_action)
            theme_menu.addAction(self.theme_light_action)
            tray_menu.addSeparator()
            settings_action = QAction("Settings...", tray_menu)
            settings_action.triggered.connect(self.show_settings_dialog)
            tray_menu.addAction(settings_action)
            tray_menu.addSeparator()
            about_action = QAction("About", tray_menu)
            about_action.triggered.connect(self.show_about_dialog)
            tray_menu.addAction(about_action)
            quit_action = QAction("Quit Snappix", tray_menu)
            quit_action.triggered.connect(self.quit_application)
            tray_menu.addAction(quit_action)
            self.tray_icon.setContextMenu(tray_menu)
            self.tray_icon.activated.connect(self._on_tray_activated)
            self.tray_icon.show()
        else:
            self._theme_action_group = None
            self.theme_dark_action = None
            self.theme_light_action = None

        self.capture_panel.set_minimize_to_tray_on_close(True)
        self.editor_host.set_minimize_to_tray_on_close(True)

        self._apply_theme(self.config.theme, persist=False)
        self._apply_hotkeys()

    def _apply_hotkeys(self) -> None:
        """
        Registers global hotkeys from the current configuration.

        Returns:
            None
        """

        if not self._hotkey_manager.apply_config(self.config):
            if self.config.hotkeys_enabled and self._hotkey_manager.last_error:
                self._QMessageBox.warning(
                    self.capture_panel,
                    "Global Hotkeys",
                    self._hotkey_manager.last_error,
                )

    def _on_global_hotkey(self, action: str) -> None:
        """
        Handles one global hotkey action.

        Args:
            action: Hotkey action identifier.

        Returns:
            None
        """

        from src.capture import CaptureMode, CaptureRequest

        if self._capture_in_progress:
            return

        mode_by_action = {
            "capture_region": CaptureMode.REGION,
            "capture_window": CaptureMode.WINDOW,
            "capture_fullscreen": CaptureMode.FULL_SCREEN,
        }
        mode = mode_by_action.get(action)
        if mode is None:
            return

        request = CaptureRequest(
            mode=mode,
            delay_seconds=int(self.capture_panel.delay_slider.value()),
        )
        self.start_capture(request)

    def show_settings_dialog(self) -> None:
        """
        Opens the application settings dialog.

        Returns:
            None
        """

        from src.settings_dialog import SettingsDialog

        dialog = SettingsDialog(self.config, self.capture_panel)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        self.config = dialog.build_config()
        self.config_manager.save(self.config)
        self._apply_hotkeys()
        self._install_host_editor_shortcuts()
        for editor in list(self.editors):
            editor.set_auto_crop_on_shrink(self.config.auto_crop_on_shrink)
            editor.apply_editor_shortcuts(self.config.editor_shortcuts)

    def _capture_save_directory(self) -> Path:
        """
        Resolves the directory used for automatic capture saves.

        Returns:
            Path: Existing or newly created save directory.
        """

        configured = self.config.capture_save_directory.strip()
        if configured:
            target = Path(configured).expanduser()
        else:
            target = Path(default_capture_save_directory())
        target.mkdir(parents=True, exist_ok=True)
        return target

    def _save_capture_pixmap(self, pixmap) -> Path | None:
        """
        Saves one capture pixmap to the configured save folder.

        Args:
            pixmap: Captured screenshot pixmap.

        Returns:
            Path | None: Saved file path or None on failure.
        """

        filename = datetime.now().strftime("snappix_%Y-%m-%d_%H-%M-%S.png")
        target_path = self._capture_save_directory() / filename
        if not pixmap.save(str(target_path), "PNG"):
            return None
        return target_path

    def _handle_capture_result(self, pixmap) -> None:
        """
        Applies the configured post-capture action to one screenshot.

        Args:
            pixmap: Captured screenshot pixmap.

        Returns:
            None
        """

        from PySide6.QtGui import QGuiApplication

        if pixmap.isNull():
            self._QMessageBox.warning(
                self.capture_panel,
                "Capture Error",
                "No screenshot could be captured.",
            )
            self.capture_panel.show()
            return

        action = self.config.post_capture_action
        if action == POST_CAPTURE_CLIPBOARD:
            QGuiApplication.clipboard().setPixmap(pixmap)
            self.capture_panel.show()
            if self._tray_available and self.tray_icon.isVisible():
                self.tray_icon.showMessage(
                    APP_NAME,
                    "Screenshot copied to clipboard.",
                    self.tray_icon.MessageIcon.Information,
                    2200,
                )
            return

        if action == POST_CAPTURE_SAVE:
            saved_path = self._save_capture_pixmap(pixmap)
            self.capture_panel.show()
            if saved_path is None:
                self._QMessageBox.warning(
                    self.capture_panel,
                    "Save Error",
                    "Could not save the screenshot.",
                )
                return
            if self._tray_available and self.tray_icon.isVisible():
                self.tray_icon.showMessage(
                    APP_NAME,
                    f"Screenshot saved to {saved_path}",
                    self.tray_icon.MessageIcon.Information,
                    2800,
                )
            return

        self._create_editor_tab(
            pixmap,
            f"Screenshot {self.editor_tabs.count() + 1}",
        )
        self.capture_panel.show()

    def _sync_theme_tray_actions(self, theme_name: str) -> None:
        """
        Updates tray theme action checked states.

        Args:
            theme_name: Active theme identifier.

        Returns:
            None
        """

        if not self._tray_available:
            return
        if self.theme_dark_action is None or self.theme_light_action is None:
            return
        normalized = normalize_theme_name(theme_name)
        self.theme_dark_action.blockSignals(True)
        self.theme_light_action.blockSignals(True)
        self.theme_dark_action.setChecked(normalized == THEME_DARK)
        self.theme_light_action.setChecked(normalized == THEME_LIGHT)
        self.theme_dark_action.blockSignals(False)
        self.theme_light_action.blockSignals(False)

    def _sync_editor_theme_actions(self, theme_name: str) -> None:
        """
        Updates theme menu actions on all open editor tabs.

        Args:
            theme_name: Active theme identifier.

        Returns:
            None
        """

        for editor in list(self.editors):
            try:
                editor.set_theme_selection(theme_name)
            except RuntimeError:
                continue

    def _apply_theme(self, theme_name: str, *, persist: bool = True) -> None:
        """
        Applies one UI theme across the application.

        Args:
            theme_name: Theme identifier to activate.
            persist: Whether to save the theme to user config.

        Returns:
            None
        """

        normalized = normalize_theme_name(theme_name)
        set_current_theme(normalized)
        self.app.setStyleSheet(build_application_stylesheet(normalized))
        self.editor_host.setStyleSheet(build_editor_accent_stylesheet(normalized))
        self.config.theme = normalized
        if persist:
            self.config_manager.save(self.config)
        self._sync_editor_theme_actions(normalized)
        self._sync_theme_tray_actions(normalized)
        for editor in list(self.editors):
            try:
                editor.refresh_theme_styles()
            except RuntimeError:
                continue

    def set_theme(self, theme_name: str) -> None:
        """
        Switches the active UI theme and persists the choice.

        Args:
            theme_name: Theme identifier to activate.

        Returns:
            None
        """

        if normalize_theme_name(theme_name) == normalize_theme_name(self.config.theme):
            self._sync_theme_tray_actions(theme_name)
            self._sync_editor_theme_actions(theme_name)
            return
        self._apply_theme(theme_name, persist=True)

    def _on_editor_export_preset_changed(self, preset_key: str) -> None:
        """
        Persists the last selected export preset from any editor tab.

        Args:
            preset_key: Newly selected export preset key.

        Returns:
            None
        """

        normalized = normalize_export_preset(preset_key)
        if normalized == self.config.export_preset:
            return
        self.config.export_preset = normalized
        self.config_manager.save(self.config)

    def _on_editor_batch_profiles_changed(
        self,
        profiles: object,
        selected_key: str,
    ) -> None:
        """
        Persists named batch export profiles and active selection.

        Args:
            profiles: Updated profile list payload.
            selected_key: Active profile key.

        Returns:
            None
        """

        if not isinstance(profiles, list):
            return
        self.config.batch_export_profiles = [
            dict(profile)
            for profile in profiles
            if isinstance(profile, dict)
        ]
        self.config.batch_export_profile_key = selected_key.strip().lower()
        self.config_manager.save(self.config)
        for editor in list(self.editors):
            try:
                editor.set_batch_export_profiles(
                    self.config.batch_export_profiles,
                    selected_key=self.config.batch_export_profile_key,
                    emit_signal=False,
                )
            except RuntimeError:
                continue

    def _on_editor_batch_export_directory_changed(self, directory_path: str) -> None:
        """
        Persists the last used batch export output directory.

        Args:
            directory_path: Selected output directory path.

        Returns:
            None
        """

        self.config.batch_export_last_directory = directory_path.strip()
        self.config_manager.save(self.config)

    def _apply_capture_taskbar_identity(self) -> None:
        """
        Applies blue capture identity for the taskbar and app icon.

        Returns:
            None
        """

        from src.platform import apply_linux_window_identity

        self.capture_panel.setWindowIcon(self._capture_icon)
        self.app.setWindowIcon(self._capture_icon)
        if self.capture_panel.isVisible():
            apply_linux_window_identity(
                self.capture_panel,
                desktop_file_name="snappix",
                wm_instance="snappix",
                wm_class="snappix",
            )

    def _apply_editor_taskbar_identity(self) -> None:
        """
        Applies red editor identity for the taskbar and app icon.

        Returns:
            None
        """

        from src.platform import apply_linux_window_identity

        self.editor_host.setWindowIcon(self._editor_icon)
        self.app.setWindowIcon(self._editor_icon)
        apply_linux_window_identity(
            self.editor_host,
            desktop_file_name="snappix-editor",
            wm_instance="snappix-editor",
            wm_class="snappix-editor",
        )

    def show(self) -> None:
        """
        Shows the capture panel.

        Returns:
            None
        """

        self._apply_capture_taskbar_identity()
        self.capture_panel.show()
        if self._startup_project_path:
            self._open_project_in_editor(self._startup_project_path)
            return
        self._maybe_restore_recovery_snapshot()

    def _create_editor_tab(
        self,
        screenshot,
        title: str,
        *,
        recovery_path: str = "",
        source_path: str = "",
        persist_session: bool = True,
    ) -> "EditorWindow":
        """
        Creates one editor tab for a screenshot and focuses editor host.

        Args:
            screenshot: Screenshot pixmap for the new tab.
            title: Tab title text.
            recovery_path: Optional existing recovery project path.
            source_path: Optional source project path for the tab.
            persist_session: When True, flush and persist the editor session.

        Returns:
            EditorWindow: Created editor instance.
        """

        from src.editor_window import EditorWindow
        from src.session_recovery import create_tab_recovery_path

        editor = EditorWindow(screenshot)
        editor.set_recovery_path(recovery_path or create_tab_recovery_path())
        editor.set_theme_selection(self.config.theme)
        editor.set_export_preset(self.config.export_preset, emit_signal=False)
        editor.set_auto_crop_on_shrink(self.config.auto_crop_on_shrink)
        editor.apply_editor_shortcuts(self.config.editor_shortcuts)
        editor.set_batch_export_profiles(
            self.config.batch_export_profiles,
            selected_key=self.config.batch_export_profile_key,
            emit_signal=False,
        )
        editor.set_batch_export_last_directory(
            self.config.batch_export_last_directory,
            emit_signal=False,
        )
        editor.theme_changed.connect(self.set_theme)
        editor.export_preset_changed.connect(self._on_editor_export_preset_changed)
        editor.batch_export_profiles_changed.connect(
            self._on_editor_batch_profiles_changed
        )
        editor.batch_export_last_directory_changed.connect(
            self._on_editor_batch_export_directory_changed
        )
        editor.settings_requested.connect(self.show_settings_dialog)
        editor.new_canvas_requested.connect(
            lambda: self.create_new_canvas_tab(editor),
        )
        editor.new_tab_requested.connect(self.create_empty_editor_tab)
        editor.setWindowIcon(self._editor_icon)
        editor.set_minimize_to_tray_on_close(False)
        editor.setParent(self.editor_tabs)
        tab_index = self.editor_tabs.addTab(editor, title)
        self.editor_tabs.setCurrentIndex(tab_index)
        self._sync_editor_host_view()
        editor.show()
        editor.destroyed.connect(lambda *_: self._on_editor_closed(editor))
        self.editors.append(editor)
        if source_path:
            editor._current_project_path = source_path
            editor._update_window_title()
        self._show_editor_host()
        if persist_session:
            self._save_editor_session()
        return editor

    def _flush_editor_tab_recovery(self, editor) -> None:
        """
        Writes one editor tab state to its recovery project file.

        Args:
            editor: Editor tab widget.

        Returns:
            None
        """

        try:
            editor.flush_recovery_snapshot()
        except RuntimeError:
            return

    def _collect_editor_session_tabs(self) -> list:
        """
        Builds the current editor session tab list for recovery persistence.

        Returns:
            list: Serializable editor session tabs.
        """

        from src.session_recovery import EditorSessionTab, ensure_tab_recovery_path

        tabs: list[EditorSessionTab] = []
        for tab_index in range(self.editor_tabs.count()):
            editor = self.editor_tabs.widget(tab_index)
            if editor is None:
                continue
            try:
                self._flush_editor_tab_recovery(editor)
                title = self.editor_tabs.tabText(tab_index).strip() or f"Tab {tab_index + 1}"
                recovery_path = ensure_tab_recovery_path(editor.recovery_path())
                editor.set_recovery_path(recovery_path)
                source_path = getattr(editor, "_current_project_path", "")
            except RuntimeError:
                continue
            if not recovery_path:
                continue
            tabs.append(
                EditorSessionTab(
                    title=title,
                    recovery_path=recovery_path,
                    source_path=str(source_path or ""),
                )
            )
        return tabs

    def _save_editor_session(self) -> None:
        """
        Persists all open editor tabs for startup recovery.

        Returns:
            None
        """

        from src.session_recovery import save_editor_session

        save_editor_session(self._collect_editor_session_tabs())

    def _maybe_restore_recovery_snapshot(self) -> None:
        """
        Restores auto-saved recovery data at startup when available.

        Returns:
            None
        """

        from src.editor_window import EditorWindow
        from src.session_recovery import (
            load_editor_session,
            load_legacy_recovery_tab,
        )
        from src.storage import base64_png_to_pixmap, load_project

        if not EditorWindow.has_recovery_snapshot():
            return

        session_tabs = load_editor_session()
        if not session_tabs:
            legacy_tab = load_legacy_recovery_tab()
            if legacy_tab is not None:
                session_tabs = [legacy_tab]

        if not session_tabs:
            return

        restored_count = 0
        for tab_entry in session_tabs:
            try:
                recovered_model = load_project(tab_entry.recovery_path)
            except Exception as exc:
                self._QMessageBox.warning(
                    self.capture_panel,
                    "Recovery",
                    f"Recovery snapshot could not be loaded:\n{exc}",
                )
                continue

            screenshot = base64_png_to_pixmap(recovered_model.screenshot_png_base64)
            editor = self._create_editor_tab(
                screenshot,
                tab_entry.title,
                recovery_path=tab_entry.recovery_path,
                source_path=tab_entry.source_path,
                persist_session=False,
            )
            editor.load_project_model(recovered_model, tab_entry.source_path)
            restored_count += 1

        if restored_count == 0:
            return

        self._show_editor_host()
        self._save_editor_session()

    def _open_project_in_editor(self, project_path: str) -> None:
        """
        Loads one project file into a new editor tab.

        Args:
            project_path: Project file path.

        Returns:
            None
        """

        from src.storage import base64_png_to_pixmap, load_project

        try:
            model = load_project(project_path)
        except Exception as exc:
            self._QMessageBox.warning(
                self.capture_panel,
                "Open Project",
                f"Could not open project:\n{exc}",
            )
            return
        screenshot = base64_png_to_pixmap(model.screenshot_png_base64)
        tab_title = Path(project_path).name
        editor = self._create_editor_tab(screenshot, tab_title)
        editor.load_project_model(model, project_path)

    def start_capture(self, request: CaptureRequest) -> None:
        """
        Starts screenshot capture sequence.

        Args:
            request: Capture request payload.

        Returns:
            None
        """

        from src.capture import execute_capture_request

        if self._capture_in_progress:
            return

        self._capture_in_progress = True
        self.capture_panel.hide()

        def on_capture_done(pixmap) -> None:
            self._capture_in_progress = False
            self._handle_capture_result(pixmap)

        def on_capture_cancelled() -> None:
            self._capture_in_progress = False
            self.capture_panel.show()

        execute_capture_request(
            request=request,
            on_capture=on_capture_done,
            on_cancel=on_capture_cancelled,
        )

    def start_color_pick(self) -> None:
        """
        Starts capture overlay mode for copying one screen color.

        Returns:
            None
        """

        from PySide6.QtGui import QGuiApplication
        from src.capture import execute_color_pick

        self.capture_panel.hide()

        def on_color_picked(hex_color: str) -> None:
            QGuiApplication.clipboard().setText(hex_color)
            self.capture_panel.show()
            if self._tray_available and self.tray_icon.isVisible():
                self.tray_icon.showMessage(
                    APP_NAME,
                    f"Copied color {hex_color} to clipboard.",
                    self.tray_icon.MessageIcon.Information,
                    2200,
                )

        def on_color_pick_cancelled() -> None:
            self.capture_panel.show()

        execute_color_pick(
            on_picked=on_color_picked,
            on_cancel=on_color_pick_cancelled,
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

        self._show_editor_host()

    def _install_host_editor_shortcuts(self) -> None:
        """
        Installs tab/host File shortcuts on the editor window (application-wide).

        Returns:
            None
        """

        from PySide6.QtCore import Qt
        from PySide6.QtGui import QKeySequence, QShortcut

        from src.shortcuts import sequences_for_action

        overrides = self.config.editor_shortcuts
        bindings = {
            "new_canvas": (
                lambda: self.create_new_canvas_tab(self.editor_host),
            ),
            "new_tab": (self.create_empty_editor_tab,),
            "open_project": (self._open_project_from_editor_host,),
            "close_tab": (self._close_current_editor_tab,),
        }
        if not hasattr(self, "_host_shortcuts"):
            self._host_shortcuts = {}

        for action_id, callbacks in bindings.items():
            sequences = sequences_for_action(action_id, overrides)
            shortcut = self._host_shortcuts.get(action_id)
            if shortcut is None:
                shortcut = QShortcut(self.editor_host)
                shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
                for callback in callbacks:
                    shortcut.activated.connect(callback)
                self._host_shortcuts[action_id] = shortcut
            if sequences:
                shortcut.setKeys(sequences)
                shortcut.setEnabled(True)
            else:
                shortcut.setKeys([])
                shortcut.setEnabled(False)

    def create_new_canvas_tab(self, parent=None) -> None:
        """
        Prompts for canvas size and opens one blank editor tab.

        Args:
            parent: Optional parent widget for the size dialog.

        Returns:
            None
        """

        from PySide6.QtWidgets import QDialog

        from src.new_canvas_dialog import NewCanvasDialog

        dialog = NewCanvasDialog(parent or self.capture_panel)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        selected_size = dialog.selected_size()
        if selected_size is None:
            return

        width, height = selected_size
        pixmap = self._build_blank_canvas_pixmap(width, height)
        editor = self._create_editor_tab(pixmap, f"New Canvas {width}×{height}")
        editor.canvas.set_blank_document(True)

    def create_empty_editor_tab(self) -> None:
        """
        Opens one empty editor tab using the default canvas size.

        Returns:
            None
        """

        from src.canvas_size import DEFAULT_CANVAS_HEIGHT, DEFAULT_CANVAS_WIDTH

        pixmap = self._build_blank_canvas_pixmap(
            DEFAULT_CANVAS_WIDTH,
            DEFAULT_CANVAS_HEIGHT,
        )
        tab_number = self.editor_tabs.count() + 1
        editor = self._create_editor_tab(
            pixmap,
            f"Tab {tab_number}",
        )
        editor.canvas.set_blank_document(True)

    def _build_blank_canvas_pixmap(self, width: int, height: int):
        """
        Creates one blank white canvas pixmap.

        Args:
            width: Canvas width in pixels.
            height: Canvas height in pixels.

        Returns:
            QPixmap: Blank canvas pixmap.
        """

        from PySide6.QtGui import QColor, QPixmap

        pixmap = QPixmap(width, height)
        pixmap.fill(QColor(255, 255, 255, 255))
        return pixmap

    def _show_editor_host(self) -> None:
        """
        Shows and focuses the editor host.

        Returns:
            None
        """

        from src.platform import raise_qt_window

        self._sync_editor_host_view()
        self._apply_editor_taskbar_identity()
        self._ensure_editor_host_geometry()
        self.editor_host.show()
        self.editor_host.raise_()
        self.editor_host.activateWindow()
        raise_qt_window(self.editor_host)

    def capture_region_from_tray(self) -> None:
        """
        Starts region capture directly from tray menu.

        Returns:
            None
        """

        from src.capture import CaptureMode, CaptureRequest

        request = CaptureRequest(
            mode=CaptureMode.REGION,
            delay_seconds=int(self.capture_panel.delay_slider.value()),
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
            delay_seconds=int(self.capture_panel.delay_slider.value()),
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
            self._handle_empty_editor_tabs()
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
            self.editor_host.resize(1240, 860)
            return
        available = screen.availableGeometry()
        width = max(1080, int(available.width() * 0.72))
        height = max(680, int(available.height() * 0.78))
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
        if not self._is_quitting:
            try:
                if hasattr(tab_widget, "confirm_close_if_needed") and not tab_widget.confirm_close_if_needed():
                    return
            except RuntimeError:
                return
        self.editor_tabs.removeTab(index)
        if tab_widget in self.editors:
            self.editors.remove(tab_widget)
        tab_widget.deleteLater()
        self._handle_empty_editor_tabs()

    def _close_current_editor_tab(self) -> None:
        """
        Closes the currently selected editor tab when available.

        Returns:
            None
        """

        current_index = self.editor_tabs.currentIndex()
        if current_index < 0:
            return
        self._close_editor_tab_by_index(current_index)

    def _open_project_from_editor_host(self) -> None:
        """
        Opens a project file picker from the editor host empty state.

        Returns:
            None
        """

        file_path, _ = self._QFileDialog.getOpenFileName(
            self.editor_host,
            "Open Project",
            "",
            f"{APP_NAME} Project (*{APP_FILE_EXTENSION});;Legacy Project (*.lshot *.json)",
        )
        if not file_path:
            return
        self._open_project_in_editor(file_path)

    def _sync_editor_host_view(self) -> None:
        """
        Switches editor host central view between tabs and empty-state panel.

        Returns:
            None
        """

        if self.editor_tabs.count() > 0:
            self.editor_stack.setCurrentWidget(self.editor_tabs)
            return
        self.editor_stack.setCurrentWidget(self.editor_empty_state)

    def _handle_empty_editor_tabs(self) -> None:
        """
        Applies configured behavior when no editor tabs remain open.

        Returns:
            None
        """

        self._sync_editor_host_view()
        if self.editor_tabs.count() != 0:
            return
        if self.config.editor_last_tab_behavior == EDITOR_LAST_TAB_CLOSE_WINDOW:
            self.editor_host.hide()
            self.capture_panel.show()
            self.capture_panel.raise_()
            self._apply_capture_taskbar_identity()

    def _on_editor_host_close(self) -> None:
        """
        Hides only the editor host and keeps the capture panel available.

        Returns:
            None
        """

        if self._is_quitting:
            return
        self._save_editor_session()
        self.editor_host.hide()
        self.capture_panel.show()
        self.capture_panel.raise_()
        self.capture_panel.activateWindow()
        self._apply_capture_taskbar_identity()

    def _on_capture_panel_close(self) -> None:
        """
        Hides only the capture panel and leaves open editors untouched.

        Returns:
            None
        """

        if self._is_quitting:
            return
        self._save_editor_session()
        self.capture_panel.hide()
        if self._tray_available and self.tray_icon.isVisible():
            self.tray_icon.showMessage(
                APP_NAME,
                "Capture panel hidden. Use tray menu to reopen or quit.",
                self.tray_icon.MessageIcon.Information,
                2500,
            )

    def _show_from_tray(self) -> None:
        """
        Restores the capture panel from the system tray.

        Returns:
            None
        """

        self.capture_panel.show()
        self.capture_panel.raise_()
        self.capture_panel.activateWindow()
        self._apply_capture_taskbar_identity()

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
        Completely exits Snappix.

        Returns:
            None
        """

        self._is_quitting = True
        self._save_editor_session()
        self._hotkey_manager.stop()
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
                "Capture screenshots, annotate visuals, blur sensitive data, run OCR, and export fast.\n\n"
                "Joachim Ruf\n"
                "Loresoft\n"
                "https://www.loresoft.de\n"
                f"{ABOUT_GITHUB}\n"
            ),
        )


def main() -> int:
    """
    Launches the Snappix desktop application.

    Returns:
        int: Process exit code.
    """

    runtime_code = _ensure_qt_runtime()
    if runtime_code != 0:
        return runtime_code
    cli_commands = {"capture", "pick-color", "export", "batch-export", "open"}
    if len(sys.argv) > 1 and sys.argv[1] in cli_commands:
        from src.cli import run_cli

        def launch_gui_with_project(project_path: str) -> int:
            return _launch_gui(startup_project_path=project_path)

        return run_cli(sys.argv[1:], launch_gui_with_project)
    return _launch_gui()


def _launch_gui(startup_project_path: str = "") -> int:
    """
    Starts the Qt GUI application.

    Args:
        startup_project_path: Optional project path to open at startup.

    Returns:
        int: Process exit code.
    """

    if not _acquire_single_instance_lock():
        print("Snappix is already running.")
        return 0
    _ensure_desktop_launcher()

    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    QGuiApplication.setDesktopFileName("snappix")
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    capture_icon = _build_capture_icon()
    app.setWindowIcon(capture_icon)
    _maybe_prompt_desktop_shortcut()
    controller = AppController(app, startup_project_path=startup_project_path)
    app.aboutToQuit.connect(controller._save_editor_session)
    controller.show()
    return app.exec()


if __name__ == "__main__":
    _reexec_into_venv_if_available(_project_root())
    raise SystemExit(main())

