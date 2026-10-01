"""
Unit tests for the single-file executable: its paths, launchers, version,
child processes, updates and build script.

The executable itself is never started here -- ``build-exe.py`` does that after
every build. These tests pretend to be frozen and check that nothing in that
mode reaches for a venv, pip, git or a Python interpreter that is not there.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

import run
from src import paths, updater, version

ROOT = Path(__file__).resolve().parent.parent


def _build_script():
    """
    Imports ``build-exe.py`` (its name is not a module name).

    Returns:
        module: The build script.
    """

    spec = importlib.util.spec_from_file_location("build_exe", str(ROOT / "build-exe.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Response(io.BytesIO):
    """
    Class _Response

    Minimal stand-in for what ``urlopen`` returns.
    """

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
        return False


class _FrozenTestCase(unittest.TestCase):
    """
    Class _FrozenTestCase

    Pretends to run as the executable, with a fake program file and data dir.
    """

    def setUp(self) -> None:
        """
        Returns:
            None
        """

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.tmp = Path(temporary.name)
        self.executable = self.tmp / "bin" / "snappix-linux-x86_64-0.1.0-build1"
        self.executable.parent.mkdir()
        self.executable.write_bytes(b"old")
        self.data_dir = self.tmp / "data"
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(paths, "IS_FROZEN", True))
        stack.enter_context(patch.object(sys, "executable", str(self.executable)))
        stack.enter_context(patch.object(paths, "user_data_dir", return_value=self.data_dir))
        stack.enter_context(patch.object(run, "user_data_dir", return_value=self.data_dir))
        stack.enter_context(patch.object(updater, "_updated_executable", None))


class ExecutableNameTests(unittest.TestCase):
    """
    Class ExecutableNameTests

    Covers the one name the build script and the updater agree on.
    """

    def test_name_per_platform_and_version(self) -> None:
        """
        Returns:
            None
        """

        cases = [
            ("linux", "x86_64", "snappix-linux-x86_64-0.39.0-build129"),
            ("linux", "aarch64", "snappix-linux-aarch64-0.39.0-build129"),
            ("windows", "AMD64", "snappix-windows-x86_64-0.39.0-build129.exe"),
            ("windows", "ARM64", "snappix-windows-aarch64-0.39.0-build129.exe"),
        ]
        for family, machine, expected in cases:
            with self.subTest(family=family, machine=machine), patch.object(
                paths, "os_family", return_value=family
            ), patch.object(paths.platform, "machine", return_value=machine):
                self.assertEqual(paths.executable_name("0.39.0", 129), expected)

    def test_name_defaults_to_this_version(self) -> None:
        """
        Returns:
            None
        """

        with patch("src.version.version", return_value=("0.7.2", "42")):
            self.assertIn("-0.7.2-build42", paths.executable_name())


class FrozenResourceTests(unittest.TestCase):
    """
    Class FrozenResourceTests

    Covers read-only resources coming from the unpacked bundle.
    """

    def test_resources_come_from_the_unpacked_bundle(self) -> None:
        """
        Returns:
            None
        """

        with tempfile.TemporaryDirectory() as bundle, patch.object(
            sys, "frozen", True, create=True
        ), patch.object(sys, "_MEIPASS", bundle, create=True):
            self.assertEqual(run._project_root(), Path(bundle))
            self.assertEqual(run._capture_icon_path(), Path(bundle) / "assets" / "snappix-red.svg")
            self.assertEqual(version.project_root(), Path(bundle))

    def test_a_checkout_finds_its_resources_next_to_run_py(self) -> None:
        """
        Returns:
            None
        """

        self.assertEqual(run._project_root(), ROOT)
        self.assertTrue(run._capture_icon_path().is_file())

    def test_the_frozen_version_comes_from_the_bundled_file_only(self) -> None:
        """
        No git, no environment override, and nothing written into the bundle.

        Returns:
            None
        """

        with tempfile.TemporaryDirectory() as bundle:
            (Path(bundle) / ".git").mkdir()
            stored = Path(bundle) / "VERSION"
            stored.write_text("0.9.1 77 abc1234 2026-09-30 marker\n", encoding="utf-8")
            with patch.object(sys, "frozen", True, create=True), patch.object(
                sys, "_MEIPASS", bundle, create=True
            ), patch.dict(os.environ, {"SNAPPIX_VERSION": "5.5.5 5"}), patch(
                "src.version.subprocess.run", side_effect=AssertionError("git must not run")
            ), patch(
                "src.version._write", side_effect=AssertionError("must not write")
            ):
                found = version.details(refresh=True)
            self.assertEqual((found["name"], found["build"]), ("0.9.1", "77"))
            self.assertEqual(stored.read_text(encoding="utf-8"), "0.9.1 77 abc1234 2026-09-30 marker\n")
        version.details(refresh=True)

    def test_version_flag_answers_before_any_gui_toolkit(self) -> None:
        """
        ``build-exe.py`` smoke-tests a fresh, headless build with ``--version``.

        Returns:
            None
        """

        probe = (
            "import builtins, runpy, sys\n"
            "_original = builtins.__import__\n"
            "def _blocking(name, *args, **kwargs):\n"
            "    if name == 'PySide6' or name.startswith('PySide6.'):\n"
            "        raise ModuleNotFoundError(name)\n"
            "    return _original(name, *args, **kwargs)\n"
            "builtins.__import__ = _blocking\n"
            f"sys.path.insert(0, {str(ROOT)!r})\n"
            f"sys.argv = [{str(ROOT / 'run.py')!r}, '--version']\n"
            f"runpy.run_path({str(ROOT / 'run.py')!r}, run_name='__main__')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(ROOT),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(version.version_string(), result.stdout)


class FrozenRuntimeToolTests(_FrozenTestCase):
    """
    Class FrozenRuntimeToolTests

    Covers ffmpeg and Tesseract living outside the temporary bundle.
    """

    def test_private_tools_live_in_the_user_data_directory(self) -> None:
        """
        Returns:
            None
        """

        from src.ffmpeg_setup import bundled_ffmpeg_dir
        from src.tesseract_setup import bundled_tesseract_dir

        bundle = self.tmp / "_MEI123"
        self.assertEqual(paths.runtime_parent(bundle), self.data_dir)
        self.assertEqual(bundled_ffmpeg_dir(bundle), self.data_dir / ".snappix-runtime" / "ffmpeg")
        self.assertEqual(
            bundled_tesseract_dir(bundle), self.data_dir / ".snappix-runtime" / "tesseract"
        )

    def test_a_checkout_keeps_them_in_the_project(self) -> None:
        """
        Returns:
            None
        """

        from src.ffmpeg_setup import bundled_ffmpeg_dir

        with patch.object(paths, "IS_FROZEN", False):
            self.assertEqual(bundled_ffmpeg_dir(ROOT), ROOT / ".snappix-runtime" / "ffmpeg")

    def test_install_flags_run_in_process(self) -> None:
        """
        ``--install-ffmpeg`` replaces ``install.bat`` for the executable.

        Returns:
            None
        """

        with patch.object(sys, "argv", ["snappix", "--install-ffmpeg"]), patch(
            "install_dependencies.install_ffmpeg_for_current_user", return_value=0
        ) as install, patch.object(paths, "use_system_environment_for_children") as clean, patch.object(
            updater, "finish_executable_update"
        ):
            self.assertEqual(run._start_frozen(), 0)
        install.assert_called_once()
        clean.assert_called_once()

    def test_a_normal_start_continues_into_the_app(self) -> None:
        """
        Returns:
            None
        """

        with patch.object(sys, "argv", ["snappix"]), patch.object(
            paths, "use_system_environment_for_children"
        ), patch.object(updater, "finish_executable_update") as finish:
            self.assertIsNone(run._start_frozen())
        finish.assert_called_once_with(run._point_launchers_at_executable)


class FrozenLaunchTests(_FrozenTestCase):
    """
    Class FrozenLaunchTests

    Covers launchers starting the executable itself.
    """

    def test_launch_command_is_the_executable(self) -> None:
        """
        Returns:
            None
        """

        expected = f'"{self.executable.resolve()}"'
        self.assertEqual(run._autostart_exec_command(), expected)
        self.assertEqual(run._autostart_login_exec_command(), f"{expected} --autostart")

    def test_desktop_entry_points_outside_the_bundle(self) -> None:
        """
        Returns:
            None
        """

        text = run._desktop_shortcut_content()
        self.assertIn(f'Exec="{self.executable.resolve()}"\n', text)
        self.assertNotIn("run.py", text)
        self.assertNotIn("Path=", text)
        self.assertIn(f"Icon={self.data_dir / 'snappix-red.svg'}\n", text)

    def test_launcher_icon_outlives_the_unpacked_files(self) -> None:
        """
        Returns:
            None
        """

        icon = run._icon_path()
        self.assertEqual(icon.parent, self.data_dir)
        self.assertTrue(icon.is_file())

    def test_launchers_are_moved_to_a_new_executable(self) -> None:
        """
        Returns:
            None
        """

        desktop = self.tmp / "Desktop"
        desktop.mkdir()
        (desktop / "Snappix.desktop").write_text("Exec=old\n", encoding="utf-8")
        autostart = self.tmp / "autostart" / "snappix.desktop"
        autostart.parent.mkdir()
        autostart.write_text("Exec=old\n", encoding="utf-8")
        with patch.object(run, "_user_desktop_dir", return_value=desktop), patch(
            "src.paths.default_autostart_path", return_value=autostart
        ), patch("src.paths.is_linux", return_value=True), patch(
            "src.install_manifest.record_user_file"
        ), patch("src.autostart.is_windows", return_value=False):
            run._point_launchers_at_executable()
        expected = f'Exec="{self.executable.resolve()}"'
        self.assertIn(expected, (desktop / "Snappix.desktop").read_text(encoding="utf-8"))
        self.assertIn(f"{expected} --autostart", autostart.read_text(encoding="utf-8"))


class NoInterpreterTests(_FrozenTestCase):
    """
    Class NoInterpreterTests

    ``sys.executable`` is the program itself: ``-c``, ``-m`` or a script path
    would start Snappix again instead of Python.
    """

    def test_no_reexec_into_a_venv(self) -> None:
        """
        Returns:
            None
        """

        venv_python = self.tmp / ".venv" / "bin" / "python3"
        venv_python.parent.mkdir(parents=True)
        venv_python.write_text("", encoding="utf-8")
        with patch.dict(os.environ, {}, clear=False), patch.object(
            run, "_resolve_venv_python", return_value=venv_python
        ), patch.object(run.subprocess, "run", side_effect=AssertionError("no probe")), patch.object(
            run.os, "execve", side_effect=AssertionError("no re-exec")
        ):
            os.environ.pop("SNAPPIX_REEXECUTED", None)
            run._reexec_into_venv_if_available(self.tmp)

    def test_no_runtime_bootstrap(self) -> None:
        """
        Returns:
            None
        """

        with patch("src.py_compat.is_supported_python", return_value=False), patch.object(
            run, "_bootstrap_then_reexec", side_effect=AssertionError("no bootstrap")
        ):
            run._ensure_supported_runtime(self.tmp)

    def test_no_installer_when_qt_is_missing(self) -> None:
        """
        Returns:
            None
        """

        import builtins

        original = builtins.__import__

        def blocking(name, *args, **kwargs):
            if name == "PySide6":
                raise ModuleNotFoundError(name)
            return original(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=blocking), patch(
            "src.install_progress_gui.run_installer_with_progress_gui",
            side_effect=AssertionError("no installer"),
        ), patch("sys.stderr", io.StringIO()):
            self.assertEqual(run._ensure_qt_runtime(), 1)

    def test_restart_starts_the_executable_itself(self) -> None:
        """
        Returns:
            None
        """

        self.assertEqual(updater.restart_command(), [str(self.executable.resolve())])


class ChildEnvironmentTests(unittest.TestCase):
    """
    Class ChildEnvironmentTests

    Covers child processes getting the system's libraries, not the bundled ones.
    """

    def test_children_get_no_paths_into_the_unpacked_files(self) -> None:
        """
        Returns:
            None
        """

        env = {
            "LD_LIBRARY_PATH": "/tmp/_MEIabc",
            "LD_LIBRARY_PATH_ORIG": "/opt/lib",
            "QT_PLUGIN_PATH": "/tmp/_MEIabc/PySide6/Qt/plugins",
            "XDG_DATA_DIRS": "/tmp/_MEIabc/share:/usr/share",
            "_PYI_ARCHIVE_FILE": "/home/me/snappix",
            "HOME": "/home/me",
        }
        with patch.object(paths, "IS_FROZEN", True), patch.object(
            sys, "_MEIPASS", "/tmp/_MEIabc", create=True
        ):
            self.assertEqual(
                paths.child_environment(env),
                {"LD_LIBRARY_PATH": "/opt/lib", "XDG_DATA_DIRS": "/usr/share", "HOME": "/home/me"},
            )
            self.assertNotIn(
                "LD_LIBRARY_PATH", paths.child_environment({"LD_LIBRARY_PATH": "/tmp/_MEIabc"})
            )

    def test_a_checkout_hands_its_environment_on_unchanged(self) -> None:
        """
        Returns:
            None
        """

        env = {"LD_LIBRARY_PATH": "/x", "_PYI_X": "y"}
        self.assertEqual(paths.child_environment(env), env)

    def test_every_popen_gets_the_clean_environment(self) -> None:
        """
        Returns:
            None
        """

        with patch.object(subprocess, "Popen", subprocess.Popen), patch.object(
            paths, "IS_FROZEN", True
        ), patch.object(sys, "_MEIPASS", "/tmp/_MEIabc", create=True), patch.dict(
            os.environ, {"SNAPPIX_PROBE": "/tmp/_MEIabc/lib"}
        ):
            paths.use_system_environment_for_children()
            paths.use_system_environment_for_children()
            output = subprocess.run(
                [sys.executable, "-c", "import os; print(os.environ.get('SNAPPIX_PROBE'))"],
                stdout=subprocess.PIPE,
                check=True,
            ).stdout.decode().strip()
            self.assertEqual(output, "None")
            self.assertFalse(
                getattr(subprocess.Popen.__bases__[0], "_snappix_clean_env", False),
                "patched only once",
            )

    def test_outside_the_executable_popen_stays_untouched(self) -> None:
        """
        Returns:
            None
        """

        with patch.object(subprocess, "Popen", subprocess.Popen):
            original = subprocess.Popen
            paths.use_system_environment_for_children()
            self.assertIs(subprocess.Popen, original)


class FrozenUpdaterTests(_FrozenTestCase):
    """
    Class FrozenUpdaterTests

    Covers updates from GitHub releases instead of the branch head.
    """

    def setUp(self) -> None:
        """
        Returns:
            None
        """

        super().setUp()
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(updater, "_running_build", return_value=129))
        stack.enter_context(patch("src.version.version_string", return_value="0.39.0 (129)"))
        stack.enter_context(patch.object(paths, "os_family", return_value="linux"))

    def _release(self, build: int, asset: str = "") -> dict:
        """
        Returns a fake GitHub release answer.

        Args:
            build: Build number of the release.
            asset: Asset name; defaults to this platform's.

        Returns:
            dict: The release.
        """

        name = asset or paths.executable_name("9.9.9", build)
        return {
            "tag_name": f"v9.9.9-build{build}",
            "name": f"Snappix 9.9.9 ({build})",
            "assets": [{"name": name, "browser_download_url": "https://example.invalid/" + name}],
        }

    def _serve(self, release: dict, payload: bytes = b"") -> None:
        """
        Answers the release API with ``release`` and the download with ``payload``.

        Args:
            release: Release returned by the API.
            payload: Bytes of the downloaded asset.

        Returns:
            None
        """

        def urlopen(request, timeout=None):
            if "api.github.com" in request.full_url:
                return _Response(json.dumps(release).encode("utf-8"))
            return _Response(payload)

        patcher = patch.object(updater.urllib.request, "urlopen", side_effect=urlopen)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_release_tag_carries_the_build_number(self) -> None:
        """
        Returns:
            None
        """

        self.assertEqual(updater.release_build("v0.39.0-build129"), 129)
        self.assertIsNone(updater.release_build("v1.2.0"))
        self.assertIsNone(updater.release_build("nightly"))

    def test_workflow_tags_releases_the_way_the_updater_reads_them(self) -> None:
        """
        Returns:
            None
        """

        workflow = (ROOT / ".github" / "workflows" / "release-exe.yml").read_text(encoding="utf-8")
        self.assertIn('TAG="v${VERSION}-build${BUILD}"', workflow)
        self.assertIn("fetch-depth: 0", workflow)
        self.assertTrue(updater.RELEASE_TAG.match("v0.39.0-build129"))

    def test_higher_build_is_an_update(self) -> None:
        """
        Returns:
            None
        """

        self._serve(self._release(130))
        info = updater.check()
        self.assertTrue(info.available, info.error)
        self.assertEqual(info.local, "0.39.0 (129)")
        self.assertEqual(info.remote, "9.9.9 (130)")

    def test_same_build_is_current(self) -> None:
        """
        Returns:
            None
        """

        self._serve(self._release(129))
        info = updater.check()
        self.assertFalse(info.available)
        self.assertFalse(info.error)

    def test_release_without_this_platform_is_an_error(self) -> None:
        """
        Returns:
            None
        """

        self._serve(self._release(130, asset="snappix-plan9-mips"))
        info = updater.check()
        self.assertTrue(info.error)
        self.assertFalse(info.available)

    def test_update_arrives_under_its_own_versioned_name(self) -> None:
        """
        Returns:
            None
        """

        new = b"N" * (2 * 1024 * 1024)
        self._serve(self._release(130), new)
        success, message = updater.apply()
        self.assertTrue(success, message)
        target = self.executable.with_name(paths.executable_name("9.9.9", 130))
        self.assertEqual(target.read_bytes(), new)
        self.assertEqual(self.executable.read_bytes(), b"old", "the running file is left alone")
        if os.name != "nt":
            self.assertTrue(target.stat().st_mode & 0o111)
        self.assertEqual(updater.restart_command(), [str(target.resolve())])

    def test_new_program_removes_the_old_one_and_moves_the_launchers(self) -> None:
        """
        Returns:
            None
        """

        self._serve(self._release(130), b"N" * (2 * 1024 * 1024))
        self.assertTrue(updater.apply()[0])
        target = self.executable.with_name(paths.executable_name("9.9.9", 130))
        launchers = MagicMock()
        with patch.object(sys, "executable", str(target)):
            updater.finish_executable_update(launchers)
            self.assertFalse(self.executable.exists())
            updater.finish_executable_update(launchers)
        launchers.assert_called_once_with()

    def test_old_program_started_again_never_deletes_itself(self) -> None:
        """
        Returns:
            None
        """

        self._serve(self._release(130), b"N" * (2 * 1024 * 1024))
        self.assertTrue(updater.apply()[0])
        launchers = MagicMock()
        updater.finish_executable_update(launchers)
        self.assertTrue(self.executable.exists())
        launchers.assert_not_called()

    def test_truncated_download_leaves_the_program_alone(self) -> None:
        """
        Returns:
            None
        """

        self._serve(self._release(130), b"<html>error</html>")
        success, _message = updater.apply()
        self.assertFalse(success)
        self.assertEqual(self.executable.read_bytes(), b"old")
        self.assertEqual(list(self.executable.parent.iterdir()), [self.executable])

    def test_restart_unpacks_the_new_file_afresh(self) -> None:
        """
        Returns:
            None
        """

        calls = []
        with patch.object(updater.sys, "platform", "linux"), patch.object(
            updater.os, "execve", side_effect=lambda *args: calls.append(args)
        ):
            updater.restart()
        self.assertEqual(calls[0][0], str(self.executable.resolve()))
        self.assertEqual(calls[0][2]["PYINSTALLER_RESET_ENVIRONMENT"], "1")

    def test_a_checkout_still_compares_commits(self) -> None:
        """
        Returns:
            None
        """

        with patch.object(paths, "IS_FROZEN", False), patch.object(
            updater, "local_commit", return_value="a" * 40
        ), patch.object(updater, "_fetch_head", return_value=("b" * 40, "newer")), patch.object(
            updater, "_fetch_release", side_effect=AssertionError("no release lookup")
        ):
            self.assertTrue(updater.check().available)


class BuildScriptTests(unittest.TestCase):
    """
    Class BuildScriptTests

    Covers the parts of ``build-exe.py`` that run without PyInstaller.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.build = _build_script()

    def test_packages_are_the_pinned_requirements_plus_pyinstaller(self) -> None:
        """
        Returns:
            None
        """

        packages = self.build.bundled_packages()
        self.assertTrue(packages[0].startswith("pyinstaller>="))
        self.assertIn("PySide6==6.11.1", packages)
        self.assertIn("pynput==1.8.2", packages)
        self.assertFalse(any(item.startswith("#") or not item for item in packages))

    def test_spec_file_compiles_and_names_the_platform(self) -> None:
        """
        Returns:
            None
        """

        staged = Path("/tmp/stage")
        text = self.build.spec_text(staged)
        compile(text, "snappix.spec", "exec")
        expected = paths.executable_name()
        if expected.endswith(".exe"):
            expected = expected[:-4]
        self.assertIn(f"name={expected!r}", text)
        self.assertIn("console=False", text)
        self.assertIn(repr([(str(staged), ".")]), text)
        self.assertIn("'PySide6.QtSvg'", text)
        self.assertIn("'scripts.fetch_ffmpeg_windows'", text)

    def test_pynput_backend_matches_the_platform(self) -> None:
        """
        Returns:
            None
        """

        with patch.object(paths, "os_family", return_value="windows"):
            self.assertIn("pynput.keyboard._win32", self.build.hidden_imports())
        with patch.object(paths, "os_family", return_value="linux"):
            hidden = self.build.hidden_imports()
        self.assertIn("pynput.keyboard._xorg", hidden)
        self.assertNotIn("pynput.keyboard._win32", hidden)

    def test_large_vendor_archive_stays_out(self) -> None:
        """
        Returns:
            None
        """

        self.assertNotIn("vendor", self.build.STAGED_DATA)
        self.assertIn("VERSION", self.build.STAGED_DATA)
        self.assertEqual(self.build.VENV_DIR, ROOT / "build" / "exe" / "venv")

    def test_build_output_is_ignored_by_git(self) -> None:
        """
        Returns:
            None
        """

        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn("/build", ignored)
        self.assertIn("/dist", ignored)


if __name__ == "__main__":
    unittest.main()
