"""
Unit tests for the Effects dialog: add/edit/remove flow and Cancel discarding
unsaved changes.
"""

from __future__ import annotations

import unittest

try:
    from src.editor_canvas import Tool
    from src.effects_dialog import EffectsDialog
    from src.video_effects import (
        EFFECT_EDGE_END,
        EFFECT_EDGE_START,
        EFFECT_KIND_FADE,
        EFFECT_KIND_ZOOM,
        add_annotation_effect,
        get_annotation_effects,
    )
    from src.video_models import VideoAnnotationModel
    from tests.qt_test_utils import ensure_qapp

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False


def _annotation() -> "VideoAnnotationModel":
    """
    Builds one bare rectangle annotation for dialog tests.

    Returns:
        VideoAnnotationModel: Sample annotation.
    """

    return VideoAnnotationModel(
        annotation_type=Tool.RECT,
        start_ms=0,
        end_ms=2000,
        x=0.0,
        y=0.0,
        width=100.0,
        height=50.0,
        stroke_rgba=[255, 0, 0, 255],
        fill_rgba=[255, 0, 0, 70],
        stroke_width=2.0,
    )


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is required for effects dialog tests")
class TestEffectsDialog(unittest.TestCase):
    """
    Verifies the dialog's working-copy add/edit/remove behavior.
    """

    @classmethod
    def setUpClass(cls) -> None:
        ensure_qapp()

    def test_starts_with_a_copy_of_existing_effects(self) -> None:
        """
        Ensures the dialog loads the annotation's existing effects into its
        list on open.
        """

        annotation = _annotation()
        add_annotation_effect(annotation, kind=EFFECT_KIND_FADE, edge=EFFECT_EDGE_START, duration_ms=400)

        dialog = EffectsDialog(annotation)

        self.assertEqual(dialog.effects_list.count(), 1)
        self.assertEqual(len(dialog.effects()), 1)

    def test_add_effect_appends_to_working_list_without_touching_annotation(self) -> None:
        """
        Ensures adding an effect updates the dialog's own list only -- the
        source annotation is untouched until the caller applies the result.
        """

        annotation = _annotation()
        dialog = EffectsDialog(annotation)

        dialog.duration_spin.setValue(700)
        dialog._add_or_update_effect()  # pylint: disable=protected-access

        self.assertEqual(len(dialog.effects()), 1)
        self.assertEqual(dialog.effects()[0]["duration_ms"], 700)
        self.assertEqual(get_annotation_effects(annotation), [])

    def test_selecting_a_list_item_loads_it_for_editing(self) -> None:
        """
        Ensures selecting an effect in the list populates the form and
        switches the Add button to "Update Effect".
        """

        annotation = _annotation()
        add_annotation_effect(annotation, kind=EFFECT_KIND_FADE, edge=EFFECT_EDGE_START, duration_ms=400)
        dialog = EffectsDialog(annotation)

        dialog.effects_list.setCurrentRow(0)

        self.assertEqual(dialog.add_button.text(), "Update Effect")
        self.assertEqual(dialog.duration_spin.value(), 400)
        self.assertTrue(dialog.remove_button.isEnabled())

    def test_updating_selected_effect_changes_it_in_place(self) -> None:
        """
        Ensures editing a selected effect and clicking "Update Effect"
        modifies that entry rather than adding a new one.
        """

        annotation = _annotation()
        add_annotation_effect(annotation, kind=EFFECT_KIND_FADE, edge=EFFECT_EDGE_START, duration_ms=400)
        dialog = EffectsDialog(annotation)
        dialog.effects_list.setCurrentRow(0)

        zoom_index = dialog.kind_combo.findData(EFFECT_KIND_ZOOM)
        dialog.kind_combo.setCurrentIndex(zoom_index)
        end_index = dialog.edge_combo.findData(EFFECT_EDGE_END)
        dialog.edge_combo.setCurrentIndex(end_index)
        dialog.duration_spin.setValue(900)
        dialog._add_or_update_effect()  # pylint: disable=protected-access

        self.assertEqual(len(dialog.effects()), 1)
        updated = dialog.effects()[0]
        self.assertEqual(updated["kind"], EFFECT_KIND_ZOOM)
        self.assertEqual(updated["edge"], EFFECT_EDGE_END)
        self.assertEqual(updated["duration_ms"], 900)

    def test_remove_selected_effect_drops_it_from_the_working_list(self) -> None:
        """
        Ensures the Remove button deletes only the currently selected effect.
        """

        annotation = _annotation()
        keep = add_annotation_effect(
            annotation, kind=EFFECT_KIND_FADE, edge=EFFECT_EDGE_START, duration_ms=300
        )
        add_annotation_effect(annotation, kind=EFFECT_KIND_ZOOM, edge=EFFECT_EDGE_END, duration_ms=300)
        dialog = EffectsDialog(annotation)
        dialog.effects_list.setCurrentRow(1)

        dialog._remove_selected_effect()  # pylint: disable=protected-access

        remaining_ids = [effect["id"] for effect in dialog.effects()]
        self.assertEqual(remaining_ids, [keep["id"]])

    def test_new_button_resets_form_to_add_mode(self) -> None:
        """
        Ensures clicking "New" after selecting an effect clears the editing
        state and restores the "Add Effect" button label.
        """

        annotation = _annotation()
        add_annotation_effect(annotation, kind=EFFECT_KIND_FADE, edge=EFFECT_EDGE_START, duration_ms=400)
        dialog = EffectsDialog(annotation)
        dialog.effects_list.setCurrentRow(0)

        dialog._reset_form()  # pylint: disable=protected-access

        self.assertEqual(dialog.add_button.text(), "Add Effect")
        self.assertIsNone(dialog._editing_effect_id)  # pylint: disable=protected-access


if __name__ == "__main__":
    unittest.main()
