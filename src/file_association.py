"""
Making Snappix an image viewer: the file types it opens and the system settings
that make it the program an image opens with.

Linux has a real switch for this (``xdg-mime``). Windows only lets a program
*offer* itself -- the choice of default app belongs to the user and cannot be
set from outside -- so there Snappix registers itself and opens the settings
page where that choice is made. Nothing here touches the system unless asked.

Every function that runs a program or writes the registry takes it as an
argument, so the tests can check exactly what would be done without doing it.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

#: Image types Snappix opens, as MIME types.
IMAGE_MIME_TYPES: tuple[str, ...] = (
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/bmp",
    "image/webp",
    "image/tiff",
)

#: The same types as file name suffixes, for Windows.
IMAGE_SUFFIXES: tuple[str, ...] = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".webp",
    ".tif",
    ".tiff",
)

DESKTOP_FILE_NAME = "snappix.desktop"

#: Windows registry names.
WINDOWS_PROG_ID = "Snappix.Image"
WINDOWS_APP_KEY = r"Software\Snappix"
WINDOWS_CAPABILITIES_KEY = r"Software\Snappix\Capabilities"
WINDOWS_SETTINGS_URI = "ms-settings:defaultapps"

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


@dataclass(frozen=True)
class AssociationResult:
    """
    The outcome of asking for Snappix to become the image viewer.

    Attributes:
        ok: True when the request did what it could.
        message: One sentence for the person who clicked.
        needs_user_choice: True when the system still waits for their choice.
    """

    ok: bool
    message: str
    needs_user_choice: bool = False


def mime_type_entry() -> str:
    """
    Returns the ``MimeType=`` value of the desktop entry.

    Returns:
        str: Semicolon-terminated list of the supported image types.
    """

    return ";".join(IMAGE_MIME_TYPES) + ";"


def files_from_arguments(arguments: Iterable[str]) -> list[str]:
    """
    Picks the image files out of the command line.

    A file manager passes paths, and some pass ``file://`` addresses; options
    and anything that is not an existing image file are left out.

    Args:
        arguments: Command-line arguments after the program name.

    Returns:
        list[str]: Absolute paths of existing image files, in the order given.
    """

    found: list[str] = []
    for argument in arguments:
        text = str(argument).strip()
        if not text or text.startswith("-"):
            continue
        if text.lower().startswith("file://"):
            text = unquote(urlparse(text).path)
        path = Path(text).expanduser()
        if path.suffix.lower() in IMAGE_SUFFIXES and path.is_file():
            resolved = str(path.resolve())
            if resolved not in found:
                found.append(resolved)
    return found


# ------------------------------------------------------------------- Linux


def default_viewer_on_linux(run: Runner = subprocess.run) -> bool:
    """
    Reports whether Snappix is the default program for every supported image type.

    Args:
        run: Function that runs a program, ``subprocess.run`` by default.

    Returns:
        bool: True when ``xdg-mime`` names Snappix for all of them.
    """

    for mime in IMAGE_MIME_TYPES:
        try:
            done = run(
                ["xdg-mime", "query", "default", mime],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        if done.returncode != 0 or done.stdout.strip() != DESKTOP_FILE_NAME:
            return False
    return True


def set_default_viewer_on_linux(run: Runner = subprocess.run) -> AssociationResult:
    """
    Makes Snappix the default program for the supported image types.

    The desktop entry has to exist already; Snappix writes it when it starts.

    Args:
        run: Function that runs a program, ``subprocess.run`` by default.

    Returns:
        AssociationResult: What happened.
    """

    try:
        done = run(
            ["xdg-mime", "default", DESKTOP_FILE_NAME, *IMAGE_MIME_TYPES],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return AssociationResult(False, f"Could not run xdg-mime: {exc}")
    if done.returncode != 0:
        return AssociationResult(False, "xdg-mime could not set Snappix as the default.")
    if not default_viewer_on_linux(run):
        return AssociationResult(
            False, "The desktop did not accept Snappix as the default image viewer."
        )
    return AssociationResult(True, "Snappix now opens images by default.")


# ----------------------------------------------------------------- Windows


def windows_registry_entries(command: str, icon: str = "") -> list[tuple[str, str, str]]:
    """
    Lists the registry values that make Snappix selectable for images.

    Everything is under the current user's own keys, so no administrator rights
    are needed.

    Args:
        command: Program and arguments that open one file, with ``%1`` for it.
        icon: Optional icon resource for the file type.

    Returns:
        list[tuple[str, str, str]]: Key path under HKEY_CURRENT_USER, value name
        (empty for the default value) and value.
    """

    prog = rf"Software\Classes\{WINDOWS_PROG_ID}"
    entries: list[tuple[str, str, str]] = [
        (prog, "", "Snappix image"),
        (rf"{prog}\shell\open\command", "", command),
        (WINDOWS_CAPABILITIES_KEY, "ApplicationName", "Snappix"),
        (
            WINDOWS_CAPABILITIES_KEY,
            "ApplicationDescription",
            "Capture, annotate and view images",
        ),
        (r"Software\RegisteredApplications", "Snappix", WINDOWS_CAPABILITIES_KEY),
    ]
    if icon:
        entries.append((rf"{prog}\DefaultIcon", "", icon))
    for suffix in IMAGE_SUFFIXES:
        entries.append((rf"{WINDOWS_CAPABILITIES_KEY}\FileAssociations", suffix, WINDOWS_PROG_ID))
        entries.append((rf"Software\Classes\{suffix}\OpenWithProgids", WINDOWS_PROG_ID, ""))
    return entries


def register_on_windows(
    command: str,
    icon: str = "",
    registry=None,
) -> bool:
    """
    Registers Snappix as a program that can open images.

    Args:
        command: Program and arguments that open one file, with ``%1`` for it.
        icon: Optional icon resource.
        registry: The ``winreg`` module; imported when omitted.

    Returns:
        bool: True when every value was written.
    """

    if registry is None:
        try:
            import winreg as registry  # type: ignore[no-redef]
        except ImportError:
            return False
    try:
        for key_path, name, value in windows_registry_entries(command, icon):
            with registry.CreateKeyEx(
                registry.HKEY_CURRENT_USER, key_path, 0, registry.KEY_SET_VALUE
            ) as key:
                registry.SetValueEx(key, name, 0, registry.REG_SZ, value)
    except OSError:
        return False
    return True


def open_windows_default_apps(opener: Callable[[str], object] | None = None) -> bool:
    """
    Opens the settings page where the default image app is chosen.

    Args:
        opener: Function that opens an address; ``os.startfile`` by default.

    Returns:
        bool: True when the page was asked for.
    """

    if opener is None:
        import os

        opener = getattr(os, "startfile", None)
        if opener is None:
            return False
    try:
        opener(WINDOWS_SETTINGS_URI)
    except OSError:
        return False
    return True


# ----------------------------------------------------------------- dispatch


class DefaultViewerService:
    """
    Offers "make Snappix the default image viewer" to the settings dialog.

    Attributes:
        command: Program and arguments that start Snappix, without a file.
    """

    def __init__(
        self,
        command: str,
        *,
        platform: str,
        run: Runner = subprocess.run,
        registry=None,
        opener: Callable[[str], object] | None = None,
        icon: str = "",
    ) -> None:
        """
        Creates the service.

        Args:
            command: Program and arguments that start Snappix.
            platform: ``linux``, ``windows`` or anything else for unsupported.
            run: Function that runs a program.
            registry: The ``winreg`` module, for tests.
            opener: Function that opens an address, for tests.
            icon: Icon resource for the Windows file type.
        """

        self.command = command
        self._platform = platform
        self._run = run
        self._registry = registry
        self._opener = opener
        self._icon = icon

    def is_supported(self) -> bool:
        """
        Reports whether this system can be asked at all.

        Returns:
            bool: True on Linux and Windows.
        """

        return self._platform in ("linux", "windows")

    def status(self) -> str:
        """
        Describes the current state in one short phrase.

        Returns:
            str: Text for a status label.
        """

        if self._platform == "linux":
            if default_viewer_on_linux(self._run):
                return "Snappix is the default image viewer."
            return "Another program opens images by default."
        if self._platform == "windows":
            return "Choose Snappix under Default apps."
        return "Not available on this system."

    def make_default(self) -> AssociationResult:
        """
        Asks the system to open images with Snappix.

        Returns:
            AssociationResult: What happened.
        """

        if self._platform == "linux":
            return set_default_viewer_on_linux(self._run)
        if self._platform == "windows":
            command = f'{self.command} "%1"'
            if not register_on_windows(command, self._icon, self._registry):
                return AssociationResult(False, "Could not register Snappix with Windows.")
            opened = open_windows_default_apps(self._opener)
            return AssociationResult(
                True,
                "Snappix is registered. Choose it under Default apps"
                + (" (the page is open)." if opened else "."),
                needs_user_choice=True,
            )
        return AssociationResult(False, "Setting the default viewer is not supported here.")
