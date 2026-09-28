"""
Tests for what a second launch does, and for the launcher's icon.

Starting Snappix again used to print a line into a terminal nobody is watching
and then exit. From the outside that is indistinguishable from "it does not
start", especially when the window sits in the tray or on another screen.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

try:
    from PySide6.QtNetwork import QLocalServer

    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Own name per test run: the developer's own Snappix may be listening.
TEST_SERVER_NAME = "snappix-instance-test-suite"


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestSecondLaunchRaisesTheFirst(unittest.TestCase):
    """
    Verifies that launching again brings the running window forward.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures a Qt application exists.
        """

        cls._app = ensure_qapp()

    def setUp(self) -> None:
        """
        Points the instance channel at a name of this test's own.
        """

        import run as snappix_run

        self._run = snappix_run
        patcher = patch.object(
            snappix_run, "_instance_server_name", return_value=TEST_SERVER_NAME
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(QLocalServer.removeServer, TEST_SERVER_NAME)

    def _listen(self, controller):
        """
        Starts the instance server for one controller.

        Args:
            controller: Object to bring forward.

        Returns:
            QLocalServer: The listening server.
        """

        server = self._run._start_instance_server(controller)
        self.assertIsNotNone(server, "server did not listen")
        self.addCleanup(server.close)
        return server

    def test_a_second_launch_is_answered(self) -> None:
        """
        Ensures the request reaches the running instance.
        """

        self._listen(MagicMock())
        self.assertTrue(self._run._signal_running_instance())

    def test_the_window_is_brought_forward(self) -> None:
        """
        Ensures the point of the exercise: the window comes back.
        """

        controller = MagicMock()
        self._listen(controller)

        self.assertTrue(self._run._signal_running_instance())
        for _ in range(50):
            self._app.processEvents()
            if controller._show_from_tray.called:
                break
        controller._show_from_tray.assert_called_once()

    def test_without_a_running_instance_nothing_is_claimed(self) -> None:
        """
        Ensures a first launch does not think it talked to itself.
        """

        QLocalServer.removeServer(TEST_SERVER_NAME)
        self.assertFalse(self._run._signal_running_instance())

    def test_a_leftover_socket_does_not_block_listening(self) -> None:
        """
        Ensures a crash cannot make every later launch do nothing.

        A killed process leaves its socket file on disk. Without clearing it
        the server never listens again, and from then on every second launch
        silently gives up -- the very failure this is meant to end.
        """

        probe = QLocalServer()
        self.assertTrue(probe.listen(TEST_SERVER_NAME))
        socket_path = Path(probe.fullServerName())
        probe.close()
        # Recreate the file a killed process would have left behind.
        socket_path.parent.mkdir(parents=True, exist_ok=True)
        socket_path.write_bytes(b"")
        self.addCleanup(lambda: socket_path.unlink(missing_ok=True))
        self.assertTrue(socket_path.exists(), "no leftover to test with")

        server = self._run._start_instance_server(MagicMock())
        self.assertIsNotNone(server, "leftover socket blocked the server")
        self.addCleanup(server.close)

    def test_a_blocked_launch_asks_the_running_instance(self) -> None:
        """
        Ensures the launch path actually uses the channel.

        The helper can work perfectly and still never be called; that is what
        made the second click look like nothing happening.
        """

        with patch.object(
            self._run, "_acquire_single_instance_lock", return_value=False
        ), patch.object(
            self._run, "_signal_running_instance", return_value=True
        ) as signal:
            code = self._run._launch_gui()

        self.assertEqual(code, 0)
        signal.assert_called_once()


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required")
class TestInstanceChannelName(unittest.TestCase):
    """
    Verifies the name the instances talk over.
    """

    def test_the_name_is_per_user(self) -> None:
        """
        Ensures two accounts on one machine do not share the channel.
        """

        import run as snappix_run

        with patch("getpass.getuser", return_value="someone"):
            self.assertIn("someone", snappix_run._instance_server_name())

    def test_a_failing_lookup_still_yields_a_name(self) -> None:
        """
        Ensures a locked-down account cannot break the channel entirely.
        """

        import run as snappix_run

        with patch("getpass.getuser", side_effect=OSError("no user")):
            self.assertTrue(snappix_run._instance_server_name())


class TestLauncherIcon(unittest.TestCase):
    """
    Verifies which icon the launcher beside the program shows.
    """

    def _launcher_text(self) -> str:
        """
        Returns the launcher file contents.

        Returns:
            str: File text.
        """

        return (PROJECT_ROOT / "Snappix.desktop").read_text(encoding="utf-8")

    def test_the_launcher_uses_the_red_capture_icon(self) -> None:
        """
        Ensures the launcher wears the capture icon, which is red.
        """

        icon_lines = [
            line
            for line in self._launcher_text().splitlines()
            if line.startswith("Icon=")
        ]
        self.assertEqual(len(icon_lines), 1)
        self.assertTrue(icon_lines[0].endswith("snappix-red.svg"), icon_lines[0])

    def test_the_blue_editor_icon_is_not_used(self) -> None:
        """
        Ensures the editor's blue icon does not creep back in.

        It did once before: the file was given "its own icon" and picked the
        editor's, which is why the launcher turned blue.
        """

        text = self._launcher_text()
        self.assertNotIn("assets/snappix.svg", text)

    def test_the_self_repair_writes_the_same_icon(self) -> None:
        """
        Ensures the launcher cannot repair itself back to the wrong icon.

        It rewrites its own ``Icon=`` line on every start, so a mismatch here
        would undo the fix at the next launch.
        """

        text = self._launcher_text()
        self.assertIn("assets/snappix-red.svg", text.split("Exec=", 1)[1].split("\n", 1)[0])

    def test_the_two_icons_really_differ_in_colour(self) -> None:
        """
        Ensures this is about the visible difference, not a renamed file.
        """

        red = (PROJECT_ROOT / "assets" / "snappix-red.svg").read_text(encoding="utf-8")
        blue = (PROJECT_ROOT / "assets" / "snappix.svg").read_text(encoding="utf-8")

        self.assertIn("#d64545", red)
        self.assertIn("#2f7dd1", blue)


if __name__ == "__main__":
    unittest.main()
