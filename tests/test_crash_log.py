"""
Tests for crash and fault logging.
"""

from __future__ import annotations

import threading
import unittest
from unittest.mock import patch

from src import crash_log


class BreadcrumbTests(unittest.TestCase):
    """
    Class BreadcrumbTests

    Covers the action trail that tells a crash report what the user was doing.
    """

    def setUp(self) -> None:
        """
        Returns:
            None
        """

        crash_log._BREADCRUMBS.clear()

    def test_actions_are_recorded_in_order(self) -> None:
        """
        Returns:
            None
        """

        crash_log.breadcrumb("press tool=select on=arrow")
        crash_log.breadcrumb("move arrow")
        trail = crash_log.recent_breadcrumbs()
        self.assertEqual(len(trail), 2)
        self.assertIn("press tool=select on=arrow", trail[0])
        self.assertIn("move arrow", trail[1])

    def test_trail_is_bounded(self) -> None:
        """
        An unbounded trail would grow for the life of the process.

        Returns:
            None
        """

        for index in range(200):
            crash_log.breadcrumb(f"action {index}")
        trail = crash_log.recent_breadcrumbs()
        self.assertLessEqual(len(trail), crash_log._BREADCRUMBS.maxlen)
        self.assertIn("action 199", trail[-1])

    def test_recording_is_thread_safe(self) -> None:
        """
        Returns:
            None
        """

        def spam() -> None:
            for index in range(50):
                crash_log.breadcrumb(f"t{index}")

        threads = [threading.Thread(target=spam) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertLessEqual(len(crash_log.recent_breadcrumbs()), crash_log._BREADCRUMBS.maxlen)


class DumpTests(unittest.TestCase):
    """
    Class DumpTests

    Covers crash blocks carrying both the fault and the action trail.
    """

    def setUp(self) -> None:
        """
        Returns:
            None
        """

        crash_log._BREADCRUMBS.clear()

    def test_dump_includes_the_breadcrumb_trail(self) -> None:
        """
        Returns:
            None
        """

        written: list[str] = []
        crash_log.breadcrumb("move arrow")
        with patch.object(crash_log, "_write", side_effect=written.append):
            crash_log._dump("Qt QtWarningMsg", "already deleted")

        blob = "".join(written)
        self.assertIn("already deleted", blob)
        self.assertIn("move arrow", blob)
        self.assertIn("Recent actions", blob)

    def test_dump_without_breadcrumbs_still_writes(self) -> None:
        """
        Returns:
            None
        """

        written: list[str] = []
        with patch.object(crash_log, "_write", side_effect=written.append):
            crash_log._dump("Uncaught exception", "boom")
        self.assertIn("boom", "".join(written))

    def test_uncaught_exception_is_recorded(self) -> None:
        """
        Returns:
            None
        """

        written: list[str] = []
        try:
            raise ValueError("kaputt")
        except ValueError:
            import sys

            exc_type, exc_value, exc_tb = sys.exc_info()
            with patch.object(crash_log, "_write", side_effect=written.append), patch.object(
                sys, "__excepthook__"
            ):
                crash_log._excepthook(exc_type, exc_value, exc_tb)

        blob = "".join(written)
        self.assertIn("ValueError", blob)
        self.assertIn("kaputt", blob)

    def test_thread_exception_names_the_thread(self) -> None:
        """
        Returns:
            None
        """

        written: list[str] = []

        class Args:
            """Stand-in for threading.ExceptHookArgs."""

            exc_type = RuntimeError
            exc_value = RuntimeError("worker died")
            exc_traceback = None
            thread = threading.current_thread()

        with patch.object(crash_log, "_write", side_effect=written.append):
            crash_log._thread_excepthook(Args())

        blob = "".join(written)
        self.assertIn("worker died", blob)
        self.assertIn(threading.current_thread().name, blob)


class RobustnessTests(unittest.TestCase):
    """
    Class RobustnessTests

    Covers diagnostics never becoming the failure they are meant to report.
    """

    def test_write_survives_an_unwritable_log(self) -> None:
        """
        Returns:
            None
        """

        class Broken:
            """A handle that fails on every write."""

            def write(self, _text: str) -> None:
                raise OSError("disk full")

            def flush(self) -> None:
                raise OSError("disk full")

        with patch.object(crash_log, "_HANDLE", Broken()):
            crash_log._write("anything")  # must not raise

    def test_write_without_a_handle_is_a_no_op(self) -> None:
        """
        Returns:
            None
        """

        with patch.object(crash_log, "_HANDLE", None):
            crash_log._write("anything")

    def test_install_returns_a_path_and_enables_faulthandler(self) -> None:
        """
        Returns:
            None
        """

        import faulthandler

        path = crash_log.install()
        self.assertTrue(faulthandler.is_enabled())
        if path is not None:
            self.assertEqual(path.name, "crash.log")


if __name__ == "__main__":
    unittest.main()
