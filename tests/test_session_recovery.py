"""
Unit tests for multi-tab editor session recovery.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.constants import APP_FILE_EXTENSION
from src.session_recovery import (
    EditorSessionTab,
    clear_editor_session,
    create_tab_recovery_path,
    has_editor_session,
    load_editor_session,
    load_legacy_recovery_tab,
    save_editor_session,
    session_manifest_path,
)


class TestSessionRecovery(unittest.TestCase):
    """
    Verifies editor session manifest persistence.
    """

    def setUp(self) -> None:
        """
        Clears recovery data before each test.

        Returns:
            None
        """

        clear_editor_session()

    def tearDown(self) -> None:
        """
        Clears recovery data after each test.

        Returns:
            None
        """

        clear_editor_session()

    def test_save_and_load_editor_session_restores_all_tabs(self) -> None:
        """
        Ensures all saved tabs are returned by the session loader.
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            first_path = str(Path(temp_dir) / f"tab-a{APP_FILE_EXTENSION}")
            second_path = str(Path(temp_dir) / f"tab-b{APP_FILE_EXTENSION}")
            Path(first_path).write_text("first", encoding="utf-8")
            Path(second_path).write_text("second", encoding="utf-8")
            tabs = [
                EditorSessionTab(title="First", recovery_path=first_path, source_path=""),
                EditorSessionTab(title="Second", recovery_path=second_path, source_path="/tmp/b.sfp"),
            ]

            with patch("src.session_recovery._session_root_dir", return_value=Path(temp_dir)):
                save_editor_session(tabs)
                loaded = load_editor_session()

            self.assertEqual(len(loaded), 2)
            self.assertEqual(loaded[0].title, "First")
            self.assertEqual(loaded[1].title, "Second")
            self.assertEqual(loaded[1].source_path, "/tmp/b.sfp")

    def test_save_editor_session_keeps_previous_manifest_when_no_tabs_remain(self) -> None:
        """
        Ensures an empty tab list does not overwrite the last saved session manifest.
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            recovery_path = str(Path(temp_dir) / f"tab-a{APP_FILE_EXTENSION}")
            Path(recovery_path).write_text("first", encoding="utf-8")
            session_dir = Path(temp_dir)

            with patch("src.session_recovery._session_root_dir", return_value=session_dir):
                save_editor_session([EditorSessionTab(title="Only", recovery_path=recovery_path)])
                save_editor_session([])
                self.assertTrue(has_editor_session())
                loaded = load_editor_session()
            self.assertEqual(len(loaded), 1)

    def test_load_editor_session_skips_missing_recovery_files(self) -> None:
        """
        Ensures tabs without recovery files are ignored during session restore.
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            existing_path = str(Path(temp_dir) / f"tab-a{APP_FILE_EXTENSION}")
            missing_path = str(Path(temp_dir) / f"tab-b{APP_FILE_EXTENSION}")
            Path(existing_path).write_bytes(b"PK\x03\x04")
            session_dir = Path(temp_dir)
            session_dir.mkdir(parents=True, exist_ok=True)
            (session_dir / "session.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "tabs": [
                            {"title": "A", "recovery_path": existing_path, "source_path": ""},
                            {"title": "B", "recovery_path": missing_path, "source_path": ""},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with patch("src.session_recovery._session_root_dir", return_value=session_dir):
                loaded = load_editor_session()

            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].title, "A")

    def test_create_tab_recovery_path_is_unique(self) -> None:
        """
        Ensures each new tab receives its own recovery file path.
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("src.session_recovery._session_root_dir", return_value=Path(temp_dir)):
                first = create_tab_recovery_path()
                second = create_tab_recovery_path()
            self.assertNotEqual(first, second)

    def test_load_legacy_recovery_tab_reads_single_snapshot(self) -> None:
        """
        Ensures the legacy single-tab snapshot can still be restored.
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            legacy_path = Path(temp_dir) / f"snapagent-autosave{APP_FILE_EXTENSION}"
            legacy_path.write_text("legacy", encoding="utf-8")
            with patch("src.session_recovery.legacy_recovery_snapshot_path", return_value=legacy_path):
                tab = load_legacy_recovery_tab()
            self.assertIsNotNone(tab)
            assert tab is not None
            self.assertEqual(tab.recovery_path, str(legacy_path))

    def test_session_manifest_is_written_as_json(self) -> None:
        """
        Ensures the session manifest uses the expected JSON structure.
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            recovery_path = str(Path(temp_dir) / f"tab-a{APP_FILE_EXTENSION}")
            Path(recovery_path).write_text("first", encoding="utf-8")
            session_dir = Path(temp_dir)

            with patch("src.session_recovery._session_root_dir", return_value=session_dir):
                save_editor_session([EditorSessionTab(title="Tab 1", recovery_path=recovery_path)])
                manifest = json.loads(session_manifest_path().read_text(encoding="utf-8"))

            self.assertEqual(manifest["version"], 1)
            self.assertEqual(len(manifest["tabs"]), 1)
            self.assertEqual(manifest["tabs"][0]["title"], "Tab 1")
