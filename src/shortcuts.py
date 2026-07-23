"""
Editor keyboard shortcut definitions and resolution helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtGui import QKeySequence


@dataclass(frozen=True, slots=True)
class ShortcutDefinition:
    """
    Describes one user-configurable editor shortcut.

    Attributes:
        action_id: Stable configuration key.
        label: Human-readable action name.
        category: Settings group label.
        default: Default shortcut text (``;`` separates alternatives).
    """

    action_id: str
    label: str
    category: str
    default: str


EDITOR_SHORTCUT_DEFINITIONS: tuple[ShortcutDefinition, ...] = (
    ShortcutDefinition("new_canvas", "New canvas", "File", "Ctrl+N"),
    ShortcutDefinition("new_tab", "New empty tab", "File", "Ctrl+T"),
    ShortcutDefinition("open_project", "Open project", "File", "Ctrl+O"),
    ShortcutDefinition("save_project", "Save project", "File", "Ctrl+S"),
    ShortcutDefinition("save_project_as", "Save project as", "File", "Ctrl+Shift+S"),
    ShortcutDefinition("export", "Export…", "File", "Ctrl+Shift+E"),
    ShortcutDefinition("print", "Print…", "File", "Ctrl+P"),
    ShortcutDefinition("close_tab", "Close tab", "File", "Ctrl+W"),
    ShortcutDefinition("undo", "Undo", "Edit", "Ctrl+Z"),
    ShortcutDefinition(
        "redo",
        "Redo",
        "Edit",
        "Ctrl+Y; Ctrl+Shift+Z",
    ),
    ShortcutDefinition("duplicate", "Duplicate selection", "Edit", "Ctrl+D"),
    ShortcutDefinition("copy", "Copy", "Edit", "Ctrl+C"),
    ShortcutDefinition("paste", "Paste", "Edit", "Ctrl+V"),
    ShortcutDefinition(
        "copy_drawing_area",
        "Copy drawing area",
        "Edit",
        "Ctrl+Shift+C",
    ),
    ShortcutDefinition(
        "paste_drawing_area",
        "Paste drawing area",
        "Edit",
        "Ctrl+Shift+V",
    ),
    ShortcutDefinition("zoom_in", "Zoom in", "View", "Ctrl++; Ctrl+="),
    ShortcutDefinition("zoom_out", "Zoom out", "View", "Ctrl+-"),
    ShortcutDefinition("zoom_reset", "Reset zoom", "View", "Ctrl+0"),
    ShortcutDefinition(
        "scale_selection_up",
        "Scale selection up",
        "View",
        "Ctrl+Shift++",
    ),
    ShortcutDefinition(
        "scale_selection_down",
        "Scale selection down",
        "View",
        "Ctrl+Shift+-",
    ),
    ShortcutDefinition("flatten", "Flatten annotations", "Edit", "Ctrl+Shift+F"),
    ShortcutDefinition("tool_select_rect", "Pixel select rectangle", "Tools", "M"),
    ShortcutDefinition("tool_select_ellipse", "Pixel select ellipse", "Tools", "Shift+M"),
    ShortcutDefinition("tool_select_path", "Pixel select lasso", "Tools", "L"),
    ShortcutDefinition("tool_magic_wand", "Magic Wand", "Tools", "W"),
    ShortcutDefinition("tool_brush", "Brush", "Tools", "B"),
    ShortcutDefinition("tool_eraser", "Eraser", "Tools", "E"),
    ShortcutDefinition("tool_bucket", "Fill selection", "Tools", "G"),
    ShortcutDefinition("tool_eyedropper", "Eyedropper", "Tools", "I"),
)

_EDITOR_SHORTCUT_BY_ID = {
    definition.action_id: definition for definition in EDITOR_SHORTCUT_DEFINITIONS
}

# Owned by the editor host window so embedded tab QMainWindows do not create
# ambiguous Ctrl+N / Ctrl+T / Ctrl+W / Ctrl+O bindings.
HOST_OWNED_SHORTCUT_IDS = frozenset(
    {
        "new_canvas",
        "new_tab",
        "open_project",
        "close_tab",
    }
)


def editor_shortcut_ids() -> frozenset[str]:
    """
    Returns all known editor shortcut action identifiers.

    Returns:
        frozenset[str]: Known action ids.
    """

    return frozenset(_EDITOR_SHORTCUT_BY_ID)


def default_editor_shortcuts() -> dict[str, str]:
    """
    Returns the default shortcut map for all editor actions.

    Returns:
        dict[str, str]: Action id to default shortcut text.
    """

    return {
        definition.action_id: definition.default
        for definition in EDITOR_SHORTCUT_DEFINITIONS
    }


def normalize_editor_shortcuts(
    overrides: dict[str, str] | None,
) -> dict[str, str]:
    """
    Sanitizes persisted editor shortcut overrides.

    Args:
        overrides: Raw action-id to shortcut mapping.

    Returns:
        dict[str, str]: Only known ids with trimmed values. Empty value clears
        the binding. Missing ids fall back to defaults at resolve time.
    """

    if not isinstance(overrides, dict):
        return {}
    known_ids = editor_shortcut_ids()
    normalized: dict[str, str] = {}
    for raw_key, raw_value in overrides.items():
        action_id = str(raw_key).strip()
        if action_id not in known_ids:
            continue
        normalized[action_id] = str(raw_value).strip()
    return normalized


def resolved_shortcut_text(
    action_id: str,
    overrides: dict[str, str] | None = None,
) -> str:
    """
    Resolves the effective shortcut text for one action.

    Args:
        action_id: Shortcut action identifier.
        overrides: Optional user overrides from configuration.

    Returns:
        str: Effective shortcut text, empty when unbound.
    """

    definition = _EDITOR_SHORTCUT_BY_ID.get(action_id)
    if definition is None:
        return ""
    cleaned = normalize_editor_shortcuts(overrides)
    if action_id in cleaned:
        return cleaned[action_id]
    return definition.default


def shortcut_spec_to_sequences(spec: str) -> list[QKeySequence]:
    """
    Converts a shortcut specification into Qt key sequences.

    Args:
        spec: Shortcut text such as ``Ctrl+S`` or ``Ctrl+Y; Ctrl+Shift+Z``.

    Returns:
        list[QKeySequence]: Parsed non-empty sequences.
    """

    from PySide6.QtGui import QKeySequence

    sequences: list[QKeySequence] = []
    for part in str(spec).replace("|", ";").split(";"):
        text = part.strip()
        if not text:
            continue
        sequence = QKeySequence(text)
        if sequence.isEmpty():
            continue
        sequences.append(sequence)
    return sequences


def sequences_for_action(
    action_id: str,
    overrides: dict[str, str] | None = None,
) -> list[QKeySequence]:
    """
    Returns Qt key sequences for one editor action.

    Args:
        action_id: Shortcut action identifier.
        overrides: Optional user overrides from configuration.

    Returns:
        list[QKeySequence]: Effective key sequences.
    """

    return shortcut_spec_to_sequences(resolved_shortcut_text(action_id, overrides))


def is_valid_shortcut_spec(spec: str) -> bool:
    """
    Validates one shortcut specification string.

    Args:
        spec: Shortcut text. Empty means intentionally unbound.

    Returns:
        bool: True when empty or at least one valid sequence is present.
    """

    text = str(spec).strip()
    if not text:
        return True
    return bool(shortcut_spec_to_sequences(text))


def format_shortcut_for_display(spec: str) -> str:
    """
    Formats a shortcut specification for UI display.

    Args:
        spec: Shortcut text.

    Returns:
        str: Native display text, or ``(none)`` when unbound.
    """

    from PySide6.QtGui import QKeySequence

    sequences = shortcut_spec_to_sequences(spec)
    if not sequences:
        return "(none)"
    return " / ".join(
        sequence.toString(QKeySequence.SequenceFormat.NativeText)
        for sequence in sequences
    )


def build_shortcuts_reference_text(overrides: dict[str, str] | None = None) -> str:
    """
    Builds a human-readable shortcut reference from current bindings.

    Args:
        overrides: Optional user overrides from configuration.

    Returns:
        str: Multi-line shortcut reference text.
    """

    lines: list[str] = ["Editor shortcuts (customize in Settings):", ""]
    current_category = ""
    for definition in EDITOR_SHORTCUT_DEFINITIONS:
        if definition.category != current_category:
            if current_category:
                lines.append("")
            current_category = definition.category
            lines.append(f"{current_category}:")
        binding = format_shortcut_for_display(
            resolved_shortcut_text(definition.action_id, overrides)
        )
        lines.append(f"  {definition.label}: {binding}")

    lines.extend(
        [
            "",
            "Canvas interactions:",
            "  Shift/Ctrl+Click: Multi-select annotations",
            "  Shift+Mouse Wheel: Zoom on canvas",
            "  Mouse Wheel / side wheel: Scroll canvas",
            "  Arrow keys: Nudge selection by 1 px",
            "  Shift+Arrow keys: Nudge selection by 10 px",
            "  Enter: Apply crop selection",
            "  Esc: Cancel crop, clear pixel selection, or capture overlays",
            "  Delete: Erase pixel selection (or delete annotations)",
            "  Lasso: click points, double-click to close path",
            "  Shift+selection tools / Magic Wand: Add to pixel selection",
            "",
            "Change bindings under Settings → Editor Shortcuts.",
        ]
    )
    return "\n".join(lines)


def find_shortcut_conflicts(
    overrides: dict[str, str] | None = None,
) -> list[tuple[str, str, str]]:
    """
    Finds duplicate key bindings across editor actions.

    Args:
        overrides: Optional user overrides from configuration.

    Returns:
        list[tuple[str, str, str]]: Conflict triples
        ``(sequence_display, first_action_id, second_action_id)``.
    """

    from PySide6.QtGui import QKeySequence

    owners: dict[str, str] = {}
    conflicts: list[tuple[str, str, str]] = []
    for definition in EDITOR_SHORTCUT_DEFINITIONS:
        for sequence in sequences_for_action(definition.action_id, overrides):
            key = sequence.toString(QKeySequence.SequenceFormat.PortableText)
            if not key:
                continue
            existing = owners.get(key)
            if existing is None:
                owners[key] = definition.action_id
                continue
            conflicts.append((key, existing, definition.action_id))
    return conflicts
