"""
Tests for Snappix as the program an image opens with.

Nothing here touches the real system: the programs it would run and the Windows
registry it would write are replaced by recorders, so each test can say exactly
what Snappix would have done. The developer's own default image viewer must
never change because a test ran.
"""

from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.file_association import (
    DESKTOP_FILE_NAME,
    IMAGE_MIME_TYPES,
    IMAGE_SUFFIXES,
    WINDOWS_CAPABILITIES_KEY,
    WINDOWS_PROG_ID,
    WINDOWS_SETTINGS_URI,
    DefaultViewerService,
    default_viewer_on_linux,
    files_from_arguments,
    mime_type_entry,
    open_windows_default_apps,
    register_on_windows,
    set_default_viewer_on_linux,
    windows_registry_entries,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class FakeXdgMime:
    """
    Stands in for ``xdg-mime``: remembers which program is default for which type.
    """

    def __init__(self, defaults: dict[str, str] | None = None, *, accept: bool = True) -> None:
        """
        Creates the stand-in.

        Args:
            defaults: Starting defaults, MIME type to desktop file.
            accept: False to make ``xdg-mime default`` fail.
        """

        self.defaults = dict(defaults or {})
        self.accept = accept
        self.calls: list[list[str]] = []

    def __call__(self, command, **_kwargs):
        """
        Answers one ``xdg-mime`` call.

        Args:
            command: Program and arguments.

        Returns:
            subprocess.CompletedProcess: What the real one would print.
        """

        self.calls.append(list(command))
        if command[:3] == ["xdg-mime", "query", "default"]:
            return subprocess.CompletedProcess(command, 0, self.defaults.get(command[3], "") + "\n", "")
        if command[:2] == ["xdg-mime", "default"]:
            if not self.accept:
                return subprocess.CompletedProcess(command, 1, "", "refused")
            for mime in command[3:]:
                self.defaults[mime] = command[2]
            return subprocess.CompletedProcess(command, 0, "", "")
        raise AssertionError(f"unexpected call {command}")


class FakeRegistry:
    """
    Stands in for ``winreg``: records every value written.
    """

    HKEY_CURRENT_USER = "HKCU"
    KEY_SET_VALUE = 2
    REG_SZ = 1

    def __init__(self, *, fail: bool = False) -> None:
        """
        Creates the stand-in.

        Args:
            fail: True to make opening a key raise, like a locked-down machine.
        """

        self.fail = fail
        self.values: list[tuple[str, str, str, str]] = []

    def CreateKeyEx(self, root, path, _reserved, _access):  # noqa: N802 - winreg name
        """
        Opens (creates) one key.

        Args:
            root: Registry hive.
            path: Key path.

        Returns:
            Context manager for the key.
        """

        if self.fail:
            raise PermissionError("denied")
        registry = self

        class _Key:
            def __init__(self) -> None:
                self.root, self.path = root, path

            def __enter__(self):
                return self

            def __exit__(self, *_exc) -> None:
                return None

        key = _Key()
        key.registry = registry
        return key

    def SetValueEx(self, key, name, _reserved, _kind, value) -> None:  # noqa: N802 - winreg name
        """
        Writes one value.

        Args:
            key: Key from ``CreateKeyEx``.
            name: Value name.
            value: Value.
        """

        self.values.append((key.root, key.path, name, value))


class TestArguments(unittest.TestCase):
    """
    Verifies which command-line arguments count as files to open.
    """

    def test_existing_images_are_taken_in_order(self) -> None:
        """
        Ensures every image is opened, in the order the file manager gave.
        """

        with TemporaryDirectory() as directory:
            first, second = Path(directory) / "b.png", Path(directory) / "a.jpg"
            first.write_bytes(b"x")
            second.write_bytes(b"x")

            found = files_from_arguments([str(first), str(second)])

        self.assertEqual([Path(item).name for item in found], ["b.png", "a.jpg"])

    def test_options_missing_files_and_other_types_are_ignored(self) -> None:
        """
        Ensures only real images get through.
        """

        with TemporaryDirectory() as directory:
            image = Path(directory) / "a.png"
            image.write_bytes(b"x")
            text = Path(directory) / "notes.txt"
            text.write_bytes(b"x")

            found = files_from_arguments(
                ["--autostart", "", str(Path(directory) / "gone.png"), str(text), str(image)]
            )

        self.assertEqual(len(found), 1)
        self.assertTrue(found[0].endswith("a.png"))

    def test_file_addresses_are_understood(self) -> None:
        """
        Ensures a manager that passes ``file://`` addresses works, spaces included.
        """

        with TemporaryDirectory() as directory:
            image = Path(directory) / "my shot.png"
            image.write_bytes(b"x")

            found = files_from_arguments([f"file://{directory}/my%20shot.png"])

        self.assertEqual(len(found), 1)
        self.assertTrue(found[0].endswith("my shot.png"))

    def test_the_same_file_twice_is_opened_once(self) -> None:
        """
        Ensures duplicates are dropped.
        """

        with TemporaryDirectory() as directory:
            image = Path(directory) / "a.png"
            image.write_bytes(b"x")

            found = files_from_arguments([str(image), str(image)])

        self.assertEqual(len(found), 1)

    def test_suffix_case_does_not_matter(self) -> None:
        """
        Ensures ``SHOT.PNG`` is an image too.
        """

        with TemporaryDirectory() as directory:
            image = Path(directory) / "SHOT.PNG"
            image.write_bytes(b"x")

            self.assertEqual(len(files_from_arguments([str(image)])), 1)

    def test_relative_paths_become_absolute(self) -> None:
        """
        Ensures a path given relative to the folder the launch happened in works.
        """

        with TemporaryDirectory() as directory:
            (Path(directory) / "a.png").write_bytes(b"x")
            previous = os.getcwd()
            os.chdir(directory)
            try:
                found = files_from_arguments(["a.png"])
            finally:
                os.chdir(previous)

        self.assertEqual(len(found), 1)
        self.assertTrue(os.path.isabs(found[0]))

    def test_every_supported_suffix_has_a_mime_type_and_back(self) -> None:
        """
        Ensures the two lists describe the same set of formats.
        """

        self.assertEqual(
            {"png", "jpeg", "gif", "bmp", "webp", "tiff"},
            {mime.split("/")[1] for mime in IMAGE_MIME_TYPES},
        )
        self.assertTrue({".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"} <= set(IMAGE_SUFFIXES))

    def test_the_suffixes_match_what_the_editor_can_import(self) -> None:
        """
        Ensures Snappix never claims a type it then refuses to open.
        """

        from src.media_import import SUPPORTED_IMAGE_SUFFIXES

        self.assertEqual(set(IMAGE_SUFFIXES), set(SUPPORTED_IMAGE_SUFFIXES))


class TestDesktopEntries(unittest.TestCase):
    """
    Verifies the Linux launchers advertise images and take files.
    """

    def test_the_mime_entry_is_a_terminated_list_of_all_types(self) -> None:
        """
        Ensures the ``MimeType=`` value is well formed.
        """

        entry = mime_type_entry()

        self.assertTrue(entry.endswith(";"))
        self.assertEqual(entry.rstrip(";").split(";"), list(IMAGE_MIME_TYPES))

    def test_the_project_launcher_lists_the_types_and_takes_files(self) -> None:
        """
        Ensures the checked-in launcher is a valid target for "Open with".
        """

        text = (PROJECT_ROOT / "Snappix.desktop").read_text(encoding="utf-8")
        mime_line = next(line for line in text.splitlines() if line.startswith("MimeType="))
        exec_line = next(line for line in text.splitlines() if line.startswith("Exec="))

        self.assertEqual(mime_line, f"MimeType={mime_type_entry()}")
        self.assertTrue(exec_line.rstrip().endswith("%k %F"))
        # The files arrive as "$@" inside the quoted shell command.
        self.assertIn(r'exec python3 ./run.py \\"\\$@\\"', exec_line)

    def test_the_generated_launcher_lists_the_types_and_takes_files(self) -> None:
        """
        Ensures the launcher Snappix writes for itself does too.
        """

        import run

        with TemporaryDirectory() as home, patch.dict(os.environ, {"HOME": home, "USERPROFILE": home}), patch.object(
            run, "_install_application_icons"
        ), patch.object(run, "_refresh_desktop_database") as refresh, patch(
            "src.install_manifest.record_user_file"
        ):
            run._ensure_desktop_launcher()
            written = (Path(home) / ".local/share/applications/snappix.desktop").read_text(encoding="utf-8")

        lines = written.splitlines()
        self.assertIn(f"MimeType={mime_type_entry()}", lines)
        self.assertTrue(next(l for l in lines if l.startswith("Exec=")).endswith(" %F"))
        refresh.assert_called_once()

    def test_an_unchanged_launcher_does_not_refresh_the_desktop_database(self) -> None:
        """
        Ensures starting Snappix does not run a helper program every time.
        """

        import run

        with TemporaryDirectory() as home, patch.dict(os.environ, {"HOME": home, "USERPROFILE": home}), patch.object(
            run, "_install_application_icons"
        ), patch.object(run, "_refresh_desktop_database") as refresh, patch(
            "src.install_manifest.record_user_file"
        ):
            run._ensure_desktop_launcher()
            refresh.reset_mock()
            run._ensure_desktop_launcher()

        refresh.assert_not_called()

    def test_the_launcher_name_is_the_one_xdg_mime_is_given(self) -> None:
        """
        Ensures the file Snappix writes is the file it names as the default.
        """

        self.assertEqual(DESKTOP_FILE_NAME, "snappix.desktop")


class TestLinuxDefault(unittest.TestCase):
    """
    Verifies making Snappix the default with ``xdg-mime``.
    """

    def test_it_sets_every_image_type_in_one_call(self) -> None:
        """
        Ensures the exact request is made.
        """

        xdg = FakeXdgMime({mime: "xviewer.desktop" for mime in IMAGE_MIME_TYPES})

        result = set_default_viewer_on_linux(xdg)

        self.assertTrue(result.ok)
        self.assertEqual(
            xdg.calls[0], ["xdg-mime", "default", DESKTOP_FILE_NAME, *IMAGE_MIME_TYPES]
        )
        self.assertTrue(all(value == DESKTOP_FILE_NAME for value in xdg.defaults.values()))

    def test_success_is_verified_not_assumed(self) -> None:
        """
        Ensures "ok" means the desktop really answers Snappix afterwards.
        """

        xdg = FakeXdgMime()
        xdg.defaults = {}

        class Stubborn(FakeXdgMime):
            def __call__(self, command, **kwargs):
                if command[:2] == ["xdg-mime", "default"]:
                    return subprocess.CompletedProcess(command, 0, "", "")
                return super().__call__(command, **kwargs)

        result = set_default_viewer_on_linux(Stubborn({mime: "other.desktop" for mime in IMAGE_MIME_TYPES}))

        self.assertFalse(result.ok)

    def test_a_refusal_is_reported(self) -> None:
        """
        Ensures a failing ``xdg-mime`` is not called a success.
        """

        result = set_default_viewer_on_linux(FakeXdgMime(accept=False))

        self.assertFalse(result.ok)

    def test_a_missing_tool_is_reported(self) -> None:
        """
        Ensures a desktop without ``xdg-mime`` gets a message, not a crash.
        """

        def missing(*_args, **_kwargs):
            raise FileNotFoundError("xdg-mime")

        result = set_default_viewer_on_linux(missing)

        self.assertFalse(result.ok)
        self.assertIn("xdg-mime", result.message)

    def test_default_means_every_type(self) -> None:
        """
        Ensures one type left to another program is not "the default".
        """

        everything = {mime: DESKTOP_FILE_NAME for mime in IMAGE_MIME_TYPES}
        self.assertTrue(default_viewer_on_linux(FakeXdgMime(everything)))

        everything["image/gif"] = "xviewer.desktop"
        self.assertFalse(default_viewer_on_linux(FakeXdgMime(everything)))

    def test_asking_changes_nothing(self) -> None:
        """
        Ensures querying the state is read-only.
        """

        xdg = FakeXdgMime()

        default_viewer_on_linux(xdg)

        self.assertTrue(all(call[1] == "query" for call in xdg.calls))


class TestWindowsRegistration(unittest.TestCase):
    """
    Verifies what is written so Snappix can be chosen under Default apps.
    """

    COMMAND = '"C:\\Snappix\\snappix.exe" "%1"'

    def test_the_open_command_receives_the_file(self) -> None:
        """
        Ensures the registered command is the one given, with the file placeholder.
        """

        entries = windows_registry_entries(self.COMMAND)

        self.assertIn(
            (rf"Software\Classes\{WINDOWS_PROG_ID}\shell\open\command", "", self.COMMAND), entries
        )

    def test_every_suffix_is_offered_and_associated(self) -> None:
        """
        Ensures all image types appear in Open with and in the capabilities.
        """

        entries = windows_registry_entries(self.COMMAND)

        for suffix in IMAGE_SUFFIXES:
            self.assertIn(
                (rf"{WINDOWS_CAPABILITIES_KEY}\FileAssociations", suffix, WINDOWS_PROG_ID), entries
            )
            self.assertIn(
                (rf"Software\Classes\{suffix}\OpenWithProgids", WINDOWS_PROG_ID, ""), entries
            )

    def test_the_program_is_listed_among_registered_applications(self) -> None:
        """
        Ensures it shows up in the Default apps settings at all.
        """

        entries = windows_registry_entries(self.COMMAND)

        self.assertIn(
            (r"Software\RegisteredApplications", "Snappix", WINDOWS_CAPABILITIES_KEY), entries
        )

    def test_an_icon_is_registered_only_when_given(self) -> None:
        """
        Ensures no empty icon entry is written.
        """

        without = windows_registry_entries(self.COMMAND)
        with_icon = windows_registry_entries(self.COMMAND, "C:\\Snappix\\snappix.exe,0")

        self.assertFalse(any("DefaultIcon" in key for key, _n, _v in without))
        self.assertTrue(any("DefaultIcon" in key for key, _n, _v in with_icon))

    def test_only_the_current_users_keys_are_written(self) -> None:
        """
        Ensures no administrator rights are needed.
        """

        registry = FakeRegistry()

        self.assertTrue(register_on_windows(self.COMMAND, registry=registry))

        self.assertTrue(registry.values)
        self.assertEqual({root for root, _p, _n, _v in registry.values}, {"HKCU"})
        self.assertEqual(len(registry.values), len(windows_registry_entries(self.COMMAND)))

    def test_a_locked_registry_is_reported(self) -> None:
        """
        Ensures a refused write is a False, not an exception.
        """

        self.assertFalse(register_on_windows(self.COMMAND, registry=FakeRegistry(fail=True)))

    def test_the_default_apps_page_is_opened(self) -> None:
        """
        Ensures the user is taken to where the choice is made.
        """

        opener = MagicMock()

        self.assertTrue(open_windows_default_apps(opener))
        opener.assert_called_once_with(WINDOWS_SETTINGS_URI)

    def test_a_failing_opener_is_reported(self) -> None:
        """
        Ensures the settings page not opening does not raise.
        """

        self.assertFalse(open_windows_default_apps(MagicMock(side_effect=OSError("no"))))


class TestService(unittest.TestCase):
    """
    Verifies the object the settings dialog talks to.
    """

    def test_linux_reports_the_state_in_words(self) -> None:
        """
        Ensures the status line says who opens images.
        """

        mine = FakeXdgMime({mime: DESKTOP_FILE_NAME for mime in IMAGE_MIME_TYPES})
        theirs = FakeXdgMime({mime: "xviewer.desktop" for mime in IMAGE_MIME_TYPES})

        self.assertIn("is the default", DefaultViewerService("x", platform="linux", run=mine).status())
        self.assertIn("Another program", DefaultViewerService("x", platform="linux", run=theirs).status())

    def test_linux_make_default_uses_xdg_mime(self) -> None:
        """
        Ensures the button ends up in the Linux path.
        """

        xdg = FakeXdgMime()

        result = DefaultViewerService("x", platform="linux", run=xdg).make_default()

        self.assertTrue(result.ok)
        self.assertFalse(result.needs_user_choice)

    def test_windows_registers_with_the_file_placeholder_and_opens_settings(self) -> None:
        """
        Ensures the Windows path registers the command and then opens Default apps.
        """

        registry, opener = FakeRegistry(), MagicMock()
        service = DefaultViewerService(
            '"C:\\Snappix\\snappix.exe"', platform="windows", registry=registry, opener=opener
        )

        result = service.make_default()

        self.assertTrue(result.ok)
        self.assertTrue(result.needs_user_choice)
        opener.assert_called_once_with(WINDOWS_SETTINGS_URI)
        commands = [value for _r, path, name, value in registry.values if path.endswith(r"shell\open\command")]
        self.assertEqual(commands, ['"C:\\Snappix\\snappix.exe" "%1"'])

    def test_windows_failure_does_not_open_settings(self) -> None:
        """
        Ensures nothing claims success when the registry refused.
        """

        opener = MagicMock()
        service = DefaultViewerService(
            "x", platform="windows", registry=FakeRegistry(fail=True), opener=opener
        )

        result = service.make_default()

        self.assertFalse(result.ok)
        opener.assert_not_called()

    def test_other_platforms_are_unsupported(self) -> None:
        """
        Ensures the settings row is hidden where nothing can be done.
        """

        service = DefaultViewerService("x", platform="other")

        self.assertFalse(service.is_supported())
        self.assertFalse(service.make_default().ok)


if __name__ == "__main__":
    unittest.main()
