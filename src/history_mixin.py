"""
Shared undo/redo history-stack management for the image and video editor windows.
"""

from __future__ import annotations


class EditorHistoryMixin:
    """
    Manages a linear undo/redo history stack of serialized editor snapshots.

    Host classes must provide ``self._history``, ``self._history_labels``,
    ``self._history_index``, ``self._pending_history_label``,
    ``self._record_history``, and ``self._syncing_history_list``, plus
    ``_serialize_state()``, ``_restore_state(snapshot)``, and
    ``_update_undo_redo_actions()`` (widget wiring differs enough between
    hosts that it is not shared here). Override ``_default_history_label()``
    and ``_on_history_navigated()`` for host-specific behavior.
    """

    def _default_history_label(self) -> str:
        """
        Returns the fallback history label used when no label is pending.

        Returns:
            str: Fallback label.
        """

        return "Edit"

    def _on_history_navigated(self) -> None:
        """
        Runs extra bookkeeping after undo/redo/history-list navigation;
        no-op unless overridden.

        Returns:
            None
        """

        return

    def _set_next_history_label(self, label: str) -> None:
        """
        Sets a pending label for the next history snapshot.

        Args:
            label: Action label shown in the history list.

        Returns:
            None
        """

        self._pending_history_label = label.strip() or "Edit"

    def _consume_history_label(self) -> str:
        """
        Resolves the next history label from pending state or a fallback.

        Returns:
            str: Chosen history label.
        """

        if self._pending_history_label:
            label = self._pending_history_label
            self._pending_history_label = None
            return label
        return self._default_history_label()

    def _push_history_state(self) -> None:
        """
        Adds the current state to the undo history.

        Returns:
            None
        """

        if not self._record_history:
            return
        snapshot = self._serialize_state()
        if self._history and snapshot == self._history[self._history_index]:
            self._pending_history_label = None
            return
        label = self._consume_history_label()
        self._history = self._history[: self._history_index + 1]
        self._history_labels = self._history_labels[: self._history_index + 1]
        self._history.append(snapshot)
        if not self._history_labels:
            self._history_labels.append("Initial state")
        else:
            self._history_labels.append(label)
        self._history_index += 1
        self._update_undo_redo_actions()

    def _reset_history(self) -> None:
        """
        Clears undo history and stores the current state as the initial entry.

        Returns:
            None
        """

        self._history.clear()
        self._history_labels.clear()
        self._history_index = -1
        self._pending_history_label = None
        self._push_history_state()

    def _on_history_entry_selected(self, index: int) -> None:
        """
        Restores a specific history entry selected in the history list.

        Args:
            index: Selected history index.

        Returns:
            None
        """

        if self._syncing_history_list:
            return
        if index < 0 or index >= len(self._history):
            return
        if index == self._history_index:
            return
        self._history_index = index
        self._restore_state(self._history[self._history_index])
        self._update_undo_redo_actions()
        self._on_history_navigated()

    def undo(self) -> None:
        """
        Restores the previous history snapshot.

        Returns:
            None
        """

        if self._history_index <= 0:
            return
        self._history_index -= 1
        self._restore_state(self._history[self._history_index])
        self._update_undo_redo_actions()
        self._on_history_navigated()

    def redo(self) -> None:
        """
        Restores the next history snapshot.

        Returns:
            None
        """

        if self._history_index >= len(self._history) - 1:
            return
        self._history_index += 1
        self._restore_state(self._history[self._history_index])
        self._update_undo_redo_actions()
        self._on_history_navigated()
