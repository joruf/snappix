"""
German user interface: language state and the translation dictionary.

Deliberately free of Qt imports. ``run.py`` must stay importable before PySide6
is installed so the bootstrap can install it, and the configuration module reads
the language constants from here -- one Qt import at this level would break that
chain. The widget-walking half lives in :mod:`src.i18n_widgets`.

Snappix was written with its texts inline. Wrapping ~20k lines in ``tr()`` calls
would be a large, risky edit for a purely cosmetic feature, so translation runs
one level higher: when a window is shown, its widget tree is walked and any text
that exactly matches a dictionary entry is replaced. Unknown text is left alone,
which keeps user content, file names, and computed strings untouched.

The trade-off is deliberate and worth stating: static labels, menus, buttons,
tooltips, tab titles, and window titles are translated; strings assembled at
runtime (status messages carrying numbers, error texts from tools) stay English.
"""

from __future__ import annotations

LANGUAGE_SYSTEM = "system"
LANGUAGE_ENGLISH = "en"
LANGUAGE_GERMAN = "de"
DEFAULT_LANGUAGE = LANGUAGE_SYSTEM
VALID_LANGUAGES = frozenset({LANGUAGE_SYSTEM, LANGUAGE_ENGLISH, LANGUAGE_GERMAN})
LANGUAGES = {
    LANGUAGE_SYSTEM: "System language",
    LANGUAGE_ENGLISH: "English",
    LANGUAGE_GERMAN: "Deutsch",
}

GERMAN: dict[str, str] = {
    # Capture panel
    "Capture Fullscreen": "Vollbild aufnehmen",
    "Capture Screen": "Bildschirm aufnehmen",
    "Capture Area": "Bereich aufnehmen",
    "Capture Window": "Fenster aufnehmen",
    "Capture Video": "Video aufnehmen",
    "Scroll": "Scrollen",
    "Open Editor": "Editor öffnen",
    "Delay:": "Verzögerung:",
    "Capturing soon — press Esc to cancel": "Aufnahme startet gleich — Esc bricht ab",
    # Menus
    "File": "Datei",
    "Edit": "Bearbeiten",
    "View": "Ansicht",
    "Help": "Hilfe",
    "New": "Neu",
    "New Canvas": "Neue Leinwand",
    "New Canvas...": "Neue Leinwand …",
    "New Tab": "Neuer Tab",
    "Open Project...": "Projekt öffnen …",
    "Save Project": "Projekt speichern",
    "Save Project As...": "Projekt speichern unter …",
    "Import Image...": "Bild einfügen …",
    "Import Image as New Tab...": "Bild als neuen Tab öffnen …",
    "Import Video...": "Video öffnen …",
    "Export": "Exportieren",
    "Export...": "Exportieren …",
    "Export as PNG...": "Als PNG exportieren …",
    "Export as JPEG...": "Als JPEG exportieren …",
    "Export as PDF...": "Als PDF exportieren …",
    "Export as SVG...": "Als SVG exportieren …",
    "Export MP4...": "Als MP4 exportieren …",
    "Export GIF...": "Als GIF exportieren …",
    "Batch Export...": "Stapelexport …",
    "Batch Export": "Stapelexport",
    "Print...": "Drucken …",
    "Close": "Schließen",
    "Close Tab": "Tab schließen",
    "Capture Panel": "Aufnahmefenster",
    "Close Editor Window": "Editorfenster schließen",
    "Undo": "Rückgängig",
    "Redo": "Wiederherstellen",
    "Duplicate": "Duplizieren",
    "Flatten Annotations": "Anmerkungen einbrennen",
    "Image Size...": "Bildgröße …",
    "Image Size": "Bildgröße",
    "Pin to Screen": "Am Bildschirm anheften",
    "Bring Forward": "Nach vorn",
    "Send Backward": "Nach hinten",
    "Bring to Front": "Ganz nach vorn",
    "Send to Back": "Ganz nach hinten",
    "Select All": "Alles auswählen",
    "Copy": "Kopieren",
    "Paste": "Einfügen",
    "Copy Drawing Area": "Zeichenfläche kopieren",
    "Paste Drawing Area": "Zeichenfläche einfügen",
    "Theme": "Design",
    "Dark": "Dunkel",
    "Light": "Hell",
    "Slate": "Schiefer",
    "Sepia": "Sepia",
    "Zoom In": "Vergrößern",
    "Zoom Out": "Verkleinern",
    "Reset Zoom": "Zoom zurücksetzen",
    "Scale Selection Up": "Auswahl vergrößern",
    "Scale Selection Down": "Auswahl verkleinern",
    "Settings...": "Einstellungen …",
    "Check for Updates...": "Nach Updates suchen …",
    "About": "Über",
    "Manual": "Handbuch",
    "Drag Out": "Herausziehen",
    # Editor panels
    "Tools": "Werkzeuge",
    "Style": "Stil",
    "Arrange": "Anordnen",
    "History": "Verlauf",
    "Effects": "Effekte",
    "Playback": "Wiedergabe",
    "Presentation": "Präsentation",
    "Presentation...": "Präsentation …",
    "Presentation Frame": "Präsentationsrahmen",
    "Thickness": "Stärke",
    "Smoothing": "Glättung",
    "Hard": "Härte",
    "Radius": "Radius",
    "Border": "Rand",
    "Fill": "Füllung",
    "Halo": "Kontrastsaum",
    "Padding": "Innenabstand",
    "Corners": "Ecken",
    "Shadow": "Schatten",
    "Drop shadow": "Schlagschatten",
    "Backdrop": "Hintergrund",
    "Size:": "Größe:",
    "Text": "Text",
    "Text:": "Text:",
    "Insert Text": "Text einfügen",
    "Apply": "Übernehmen",
    "Free": "Frei",
    "Original": "Original",
    "Crop": "Zuschneiden",
    "Apply Crop": "Zuschnitt anwenden",
    "Cancel Crop": "Zuschnitt abbrechen",
    "Reset": "Zurücksetzen",
    "Remove": "Entfernen",
    "Rename": "Umbenennen",
    "Manage": "Verwalten",
    "Visible": "Sichtbar",
    "Lock": "Sperren",
    "Up": "Hoch",
    "Down": "Runter",
    "Flip H": "Horizontal spiegeln",
    "Flip V": "Vertikal spiegeln",
    "Skew": "Neigen",
    "Zoom": "Zoom",
    "Format": "Format",
    "Format:": "Format:",
    "Profile": "Profil",
    "Symbol": "Symbol",
    "Explanation": "Erklärung",
    "Tolerance": "Toleranz",
    "Contiguous": "Zusammenhängend",
    "Pixel block": "Pixelblock",
    "Show all objects": "Alle Objekte zeigen",
    "Increase Element Size": "Element vergrößern",
    "Decrease Element Size": "Element verkleinern",
    "Keep transparency": "Transparenz erhalten",
    "Frame exports": "Exporte rahmen",
    "Duration:": "Dauer:",
    "Effect:": "Effekt:",
    "Add Effect": "Effekt hinzufügen",
    "Applied effects:": "Angewendete Effekte:",
    "Apply to:": "Anwenden auf:",
    "Erase: Fill color": "Löschen: Füllfarbe",
    "Erase: Transparent": "Löschen: Transparent",
    "Sample → Border": "Aufnehmen → Rand",
    "Sample → Fill": "Aufnehmen → Füllung",
    # Dialogs
    "Snappix Settings": "Snappix-Einstellungen",
    "General": "Allgemein",
    "Editor Shortcuts": "Editor-Tastenkürzel",
    "Enable global hotkeys": "Globale Tastenkürzel aktivieren",
    "Capture area:": "Bereich aufnehmen:",
    "Capture window:": "Fenster aufnehmen:",
    "Capture fullscreen:": "Vollbild aufnehmen:",
    "Capture current screen:": "Aktuellen Bildschirm aufnehmen:",
    "Capture same area:": "Gleichen Bereich aufnehmen:",
    "Capture video:": "Video aufnehmen:",
    "Pause/resume recording:": "Aufnahme pausieren/fortsetzen:",
    "Stop recording:": "Aufnahme beenden:",
    "Start MeasureBox:": "MeasureBox starten:",
    "After capture:": "Nach der Aufnahme:",
    "Screenshot source:": "Screenshot-Quelle:",
    "File name:": "Dateiname:",
    "Save folder:": "Speicherordner:",
    "Workspace folder:": "Arbeitsordner:",
    "When last tab closes:": "Wenn der letzte Tab schließt:",
    "Selection handle size:": "Größe der Anfasser:",
    "Selection handle position:": "Position der Anfasser:",
    "Auto-crop canvas when content shrinks": "Leinwand automatisch beschneiden",
    "Canvas:": "Leinwand:",
    "Browse...": "Durchsuchen …",
    "Choose...": "Auswählen …",
    "Reset All Shortcuts": "Alle Tastenkürzel zurücksetzen",
    "Width:": "Breite:",
    "Height:": "Höhe:",
    "Preset:": "Vorgabe:",
    "Keep aspect ratio": "Seitenverhältnis beibehalten",
    "Line color:": "Linienfarbe:",
    "Fill color:": "Füllfarbe:",
    "Show pixel ruler (px)": "Pixel-Lineal zeigen (px)",
    "Ruler outside rectangle": "Lineal außerhalb des Rechtecks",
    "Show Left Shift crosshair": "Fadenkreuz mit linker Umschalttaste",
    "Export Video": "Video exportieren",
    "Export Video Options": "Video-Exportoptionen",
    "Include audio in exported video": "Ton in den Export übernehmen",
    "Choose formats to export:": "Zu exportierende Formate:",
    "Batch Export Formats": "Stapelexport-Formate",
    "Manage Batch Export Profiles": "Stapelexport-Profile verwalten",
    "Saved profiles:": "Gespeicherte Profile:",
    "PDF DPI": "PDF-DPI",
    "Global Hotkeys": "Globale Tastenkürzel",
    "Snappix Pin": "Snappix-Anheftung",
    "Language:": "Sprache:",
}

_ACTIVE: dict[str, str] = {}
_LANGUAGE = DEFAULT_LANGUAGE


def normalize_language(code: str) -> str:
    """
    Returns a supported language identifier.

    Args:
        code: Requested language code.

    Returns:
        str: One of ``system``, ``en``, or ``de``.
    """

    normalized = str(code or "").strip().lower()
    if normalized in VALID_LANGUAGES:
        return normalized
    return DEFAULT_LANGUAGE


def resolve_language(code: str) -> str:
    """
    Resolves ``system`` to a concrete language using the OS locale.

    Args:
        code: Configured language code.

    Returns:
        str: ``en`` or ``de``.
    """

    normalized = normalize_language(code)
    if normalized != LANGUAGE_SYSTEM:
        return normalized
    return LANGUAGE_GERMAN if system_language_is_german() else LANGUAGE_ENGLISH


def system_language_is_german() -> bool:
    """
    Reports whether the operating system is set to German.

    Reads the environment rather than ``QLocale`` so this module stays free of
    Qt; both agree on the platforms Snappix supports.

    Returns:
        bool: True when the system locale is German.
    """

    import locale as locale_module
    import os

    for variable in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        value = os.environ.get(variable, "").strip()
        if value:
            return value.lower().startswith("de")
    try:
        system_locale = locale_module.getlocale()[0] or ""
    except (TypeError, ValueError):
        system_locale = ""
    return system_locale.lower().startswith("de")


def set_language(code: str) -> str:
    """
    Activates one interface language.

    Args:
        code: Language code, including ``system``.

    Returns:
        str: The resolved language actually activated.
    """

    global _LANGUAGE

    _LANGUAGE = resolve_language(code)
    _ACTIVE.clear()
    if _LANGUAGE == LANGUAGE_GERMAN:
        _ACTIVE.update(GERMAN)
    return _LANGUAGE


def current_language() -> str:
    """
    Returns the active interface language.

    Returns:
        str: ``en`` or ``de``.
    """

    return _LANGUAGE


def has_translations() -> bool:
    """
    Reports whether a translation dictionary is active.

    Returns:
        bool: True when texts would be replaced.
    """

    return bool(_ACTIVE)


def translate(text: str) -> str:
    """
    Translates one interface string.

    Only exact matches are replaced, so user content, file names, and computed
    strings pass through untouched.

    Args:
        text: Source text.

    Returns:
        str: Translated text, or the original when it is not in the dictionary.
    """

    if not text:
        return text
    return _ACTIVE.get(text, text)
