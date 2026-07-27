"""
Shared configurable-shortcut registration for the image and video editor windows.
"""

from __future__ import annotations

from PySide6.QtGui import QAction

from src.shortcuts import (
    HOST_OWNED_SHORTCUT_IDS,
    format_shortcut_for_display,
    normalize_editor_shortcuts,
    resolved_shortcut_text,
    sequences_for_action,
)


class ShortcutRegistryMixin:
    """
    Tracks QActions by stable shortcut id and applies user-configured bindings.

    Host classes must initialize ``self._shortcut_actions: dict[str, QAction]``
    and ``self._editor_shortcut_overrides: dict[str, str]`` before registering
    any action.
    """

    def _register_shortcut_action(self, action_id: str, action: QAction) -> None:
        """
        Registers one menu action for configurable keyboard shortcuts.

        Args:
            action_id: Stable shortcut identifier.
            action: Qt action that receives the binding.

        Returns:
            None
        """

        self._shortcut_actions[action_id] = action

    def apply_editor_shortcuts(self, overrides: dict[str, str] | None) -> None:
        """
        Applies configured editor shortcuts to registered actions.

        Args:
            overrides: Shortcut overrides from application settings.

        Returns:
            None
        """

        self._editor_shortcut_overrides = normalize_editor_shortcuts(overrides)
        for action_id, action in self._shortcut_actions.items():
            binding = format_shortcut_for_display(
                resolved_shortcut_text(action_id, self._editor_shortcut_overrides)
            )
            tip = action.toolTip().split(" Shortcut:")[0].rstrip()
            if binding != "(none)":
                action.setToolTip(f"{tip} Shortcut: {binding}.")
            else:
                action.setToolTip(tip)
            if action_id in HOST_OWNED_SHORTCUT_IDS:
                # Host QShortcuts own these keys; keep menu actions clickable only.
                action.setShortcuts([])
                continue
            sequences = sequences_for_action(action_id, self._editor_shortcut_overrides)
            action.setShortcuts(sequences)
