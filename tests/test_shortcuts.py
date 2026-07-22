"""
Unit tests for editor shortcut definitions and resolution.
"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtGui import QKeySequence

    from src.shortcuts import (
        build_shortcuts_reference_text,
        find_shortcut_conflicts,
        normalize_editor_shortcuts,
        resolved_shortcut_text,
        sequences_for_action,
    )
    from tests.qt_test_utils import ensure_qapp

    HAS_PYSIDE6 = True
except ModuleNotFoundError:
    HAS_PYSIDE6 = False


@unittest.skipUnless(HAS_PYSIDE6, "PySide6 is required for shortcut tests")
class TestEditorShortcuts(unittest.TestCase):
    """
    Verifies shortcut defaults, overrides, and conflict detection.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Ensures Qt application exists for key-sequence helpers.
        """

        cls._app = ensure_qapp()

    def test_resolved_shortcut_uses_override_or_default(self) -> None:
        """
        Ensures overrides replace defaults and empty values unbind actions.
        """

        self.assertEqual(resolved_shortcut_text("copy", {}), "Ctrl+C")
        self.assertEqual(resolved_shortcut_text("new_tab", {}), "Ctrl+T")
        from src.shortcuts import HOST_OWNED_SHORTCUT_IDS

        self.assertIn("new_tab", HOST_OWNED_SHORTCUT_IDS)
        self.assertEqual(resolved_shortcut_text("copy", {"copy": "F5"}), "F5")
        self.assertEqual(resolved_shortcut_text("copy", {"copy": ""}), "")
        sequences = sequences_for_action("redo", {})
        portable = [
            sequence.toString(QKeySequence.SequenceFormat.PortableText)
            for sequence in sequences
        ]
        self.assertIn("Ctrl+Y", portable)
        self.assertIn("Ctrl+Shift+Z", portable)

    def test_normalize_editor_shortcuts_drops_unknown_ids(self) -> None:
        """
        Ensures unknown action ids are removed from override maps.
        """

        normalized = normalize_editor_shortcuts(
            {"copy": " F8 ", "unknown": "F1", 12: "F2"}
        )
        self.assertEqual(normalized, {"copy": "F8"})

    def test_find_shortcut_conflicts_detects_duplicates(self) -> None:
        """
        Ensures duplicate bindings across actions are reported.
        """

        conflicts = find_shortcut_conflicts({"paste": "Ctrl+C"})
        self.assertTrue(conflicts)
        self.assertTrue(
            any("Ctrl+C" in conflict[0] or conflict[0] == "Ctrl+C" for conflict in conflicts)
        )

    def test_reference_text_mentions_settings(self) -> None:
        """
        Ensures the manual reference points users to Settings.
        """

        text = build_shortcuts_reference_text({})
        self.assertIn("Settings", text)
        self.assertIn("Copy", text)
