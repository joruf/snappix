"""
Effects dialog: add, edit, and remove timeline entry/exit effects (fade,
slide, zoom) on one video annotation.
"""

from __future__ import annotations

from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.video_effects import (
    DEFAULT_EFFECT_DURATION_MS,
    EFFECT_EDGE_END,
    EFFECT_EDGE_START,
    EFFECT_KIND_FADE,
    EFFECT_KINDS,
    MAX_EFFECT_DURATION_MS,
    MIN_EFFECT_DURATION_MS,
    effect_display_name,
    effect_kind_label,
    get_annotation_effects,
)
from src.video_models import VideoAnnotationModel


class EffectsDialog(QDialog):
    """
    Manages the list of entry/exit effects attached to one video annotation.
    """

    def __init__(self, annotation: VideoAnnotationModel, parent: QWidget | None = None) -> None:
        """
        Initializes the dialog with a working copy of the annotation's effects.

        Args:
            annotation: Annotation whose effects are being edited.
            parent: Owner widget for the dialog.
        """

        super().__init__(parent)
        self.setWindowTitle("Effects")
        self.setMinimumWidth(420)
        self._effects: list[dict] = [dict(effect) for effect in get_annotation_effects(annotation)]
        self._editing_effect_id: str | None = None

        root = QVBoxLayout(self)

        form_container = QWidget(self)
        form = QFormLayout(form_container)
        form.setContentsMargins(0, 0, 0, 0)
        root.addWidget(form_container)

        self.kind_combo = QComboBox(self)
        for kind in EFFECT_KINDS:
            self.kind_combo.addItem(effect_kind_label(kind), kind)
        self.kind_combo.setToolTip(
            "Visual transform to play at the start or end of this object's time range."
        )
        form.addRow("Effect:", self.kind_combo)

        self.edge_combo = QComboBox(self)
        self.edge_combo.addItem("Start (In)", EFFECT_EDGE_START)
        self.edge_combo.addItem("End (Out)", EFFECT_EDGE_END)
        self.edge_combo.setToolTip("Whether the effect plays at the start or the end of the object.")
        form.addRow("Apply to:", self.edge_combo)

        self.duration_spin = QSpinBox(self)
        self.duration_spin.setRange(MIN_EFFECT_DURATION_MS, MAX_EFFECT_DURATION_MS)
        self.duration_spin.setSingleStep(50)
        self.duration_spin.setSuffix(" ms")
        self.duration_spin.setValue(DEFAULT_EFFECT_DURATION_MS)
        self.duration_spin.setToolTip(
            "How long the effect takes to play, from its start to its end."
        )
        form.addRow("Duration:", self.duration_spin)

        form_buttons = QHBoxLayout()
        form_buttons.addStretch(1)
        self.new_button = QPushButton("New", self)
        self.new_button.setToolTip("Clear the form to add another effect.")
        self.new_button.clicked.connect(self._reset_form)
        form_buttons.addWidget(self.new_button)
        self.add_button = QPushButton("Add Effect", self)
        self.add_button.setToolTip("Adds the configured effect to this object.")
        self.add_button.clicked.connect(self._add_or_update_effect)
        form_buttons.addWidget(self.add_button)
        root.addLayout(form_buttons)

        root.addWidget(QLabel("Applied effects:", self))
        self.effects_list = QListWidget(self)
        self.effects_list.setToolTip(
            "Effects applied to this object. Select one to edit it, or remove it below."
        )
        self.effects_list.itemSelectionChanged.connect(self._on_selection_changed)
        root.addWidget(self.effects_list, 1)

        list_buttons = QHBoxLayout()
        list_buttons.addStretch(1)
        self.remove_button = QPushButton("Remove", self)
        self.remove_button.setToolTip("Removes the selected effect from this object.")
        self.remove_button.setEnabled(False)
        self.remove_button.clicked.connect(self._remove_selected_effect)
        list_buttons.addWidget(self.remove_button)
        root.addLayout(list_buttons)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        root.addWidget(button_box)

        self._refresh_list()

    def effects(self) -> list[dict]:
        """
        Returns the working effect list as edited in this dialog.

        Callers should only apply this back to the annotation when the
        dialog was accepted (``exec() == QDialog.DialogCode.Accepted``).

        Returns:
            list[dict]: Current effect entries.
        """

        return list(self._effects)

    def _selected_kind(self) -> str:
        return str(self.kind_combo.currentData() or EFFECT_KIND_FADE)

    def _selected_edge(self) -> str:
        return str(self.edge_combo.currentData() or EFFECT_EDGE_START)

    def _reset_form(self) -> None:
        """
        Clears the form back to "add a new effect" mode.

        Returns:
            None
        """

        self.effects_list.setCurrentRow(-1)
        self._editing_effect_id = None
        self.kind_combo.setCurrentIndex(0)
        self.edge_combo.setCurrentIndex(0)
        self.duration_spin.setValue(DEFAULT_EFFECT_DURATION_MS)
        self.add_button.setText("Add Effect")

    def _add_or_update_effect(self) -> None:
        """
        Adds a new effect, or applies edits to the effect currently selected
        for editing, then refreshes the list.

        Returns:
            None
        """

        kind = self._selected_kind()
        edge = self._selected_edge()
        duration_ms = int(self.duration_spin.value())

        if self._editing_effect_id is not None:
            for effect in self._effects:
                if effect.get("id") == self._editing_effect_id:
                    effect["kind"] = kind
                    effect["edge"] = edge
                    effect["duration_ms"] = duration_ms
                    break
        else:
            self._effects.append(
                {
                    "id": uuid4().hex,
                    "kind": kind,
                    "edge": edge,
                    "duration_ms": duration_ms,
                }
            )

        self._refresh_list()
        self._reset_form()

    def _remove_selected_effect(self) -> None:
        """
        Removes the currently selected effect from the working list.

        Returns:
            None
        """

        effect_id = self._current_list_effect_id()
        if effect_id is None:
            return
        self._effects = [effect for effect in self._effects if effect.get("id") != effect_id]
        self._refresh_list()
        self._reset_form()

    def _current_list_effect_id(self) -> str | None:
        item = self.effects_list.currentItem()
        if item is None:
            return None
        return str(item.data(Qt.ItemDataRole.UserRole))

    def _on_selection_changed(self) -> None:
        """
        Loads the selected effect's settings into the form for editing.

        Returns:
            None
        """

        effect_id = self._current_list_effect_id()
        self.remove_button.setEnabled(effect_id is not None)
        if effect_id is None:
            return
        effect = next((item for item in self._effects if item.get("id") == effect_id), None)
        if effect is None:
            return
        self._editing_effect_id = effect_id
        kind_index = self.kind_combo.findData(effect.get("kind"))
        if kind_index >= 0:
            self.kind_combo.setCurrentIndex(kind_index)
        edge_index = self.edge_combo.findData(effect.get("edge"))
        if edge_index >= 0:
            self.edge_combo.setCurrentIndex(edge_index)
        self.duration_spin.setValue(
            int(effect.get("duration_ms", DEFAULT_EFFECT_DURATION_MS) or DEFAULT_EFFECT_DURATION_MS)
        )
        self.add_button.setText("Update Effect")

    def _refresh_list(self) -> None:
        """
        Rebuilds the effect list widget from the working effect list.

        Returns:
            None
        """

        self.effects_list.clear()
        for effect in self._effects:
            label = effect_display_name(str(effect.get("kind", "")), str(effect.get("edge", "")))
            duration_ms = int(effect.get("duration_ms", DEFAULT_EFFECT_DURATION_MS) or 0)
            item = QListWidgetItem(f"{label} — {duration_ms} ms")
            item.setData(Qt.ItemDataRole.UserRole, effect.get("id"))
            self.effects_list.addItem(item)
        self.remove_button.setEnabled(False)
