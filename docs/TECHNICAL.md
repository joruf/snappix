# Snappix Technical Documentation

Architecture, modules, data formats, session workspace, and extension points for developers.

## Overview

Snappix is a Linux desktop app (Python 3.11+, PySide6 / Qt 6) with a controller-driven layout:

```text
run.py (AppController)
├── CapturePanel + overlays (src/capture.py)
├── EditorHostWindow + tabbed editors (run.py)
│   ├── EditorWindow tabs — image (src/editor_window.py)
│   └── VideoEditorWindow tabs — video (src/video_editor_window.py)
├── System tray + settings (run.py, src/settings_dialog.py)
├── Config (src/config.py) + shortcuts (src/shortcuts.py)
├── Session workspace (src/session_recovery.py)
├── Install / uninstall tracking (install_dependencies.py, uninstall_dependencies.py, src/install_manifest.py)
├── Video pipeline (src/video_recorder.py, src/video_storage.py, src/timeline_widget.py)
├── Global hotkeys (src/global_hotkeys.py)
└── Theme engine (src/theme.py)
```

Single-instance lock: `~/.cache/snappix/snappix.lock`.

User settings: `~/.config/snappix/config.json`  
Session workspace (default): `~/.snappix/`  
Install manifest (for deinstaller): `~/.config/snappix/install-manifest.json`

## Entry Points

| Entry | File | Purpose |
|-------|------|---------|
| Main GUI | `run.py` | Tray, capture/editor host, post-capture routing, session save/restore |
| Package | `src/__main__.py` | `python -m src` |
| CLI | `src/cli.py` | Headless capture, export, open |
| Installer | `install_dependencies.py`, `src/runtime_bootstrap.py` | Managed uv/Python 3.12, `.venv`, system packages, pip deps, install manifest |
| Launchers | `Snappix.bat`, `snappix.sh`, `install.bat`, `install.sh` | Zero-Python bootstrap + start (or install-only) |
| Uninstaller | `uninstall_dependencies.py` | Remove Snappix-owned packages/files/runtime only |
| Installer UI | `src/install_progress_gui.py` | Tk splash during first-run setup |
| Screenshot generator | `scripts/generate_readme_screenshots.py` | README UI captures |

Startup:

1. Re-exec into `.venv` when present and supported (Python 3.11+).
2. If the host interpreter is too old, bootstrap a managed CPython 3.12 runtime via uv, then re-exec.
3. Ensure PySide6 (Tk installer UI if missing).
4. Acquire single-instance lock.
5. Create `QApplication`, load config, apply theme, set workspace root.
6. Show capture panel; restore multi-tab session from workspace or open a startup project.

## Source Module Map

| Module | Responsibility |
|--------|----------------|
| `run.py` | `AppController`, tray, editor host tabs, hotkeys, session flush/restore, tab close cleanup |
| `src/capture.py` | Capture panel, region/window overlays, color picker, capture engine, recording border overlay |
| `src/auto_scroll_capture.py` | Automatic window scroll + frame collection |
| `src/scroll_capture.py` | Vertical stitch / overlap detection |
| `src/editor_window.py` | Image editor chrome, toolbars, property tabs, history, export/print |
| `src/editor_canvas.py` | Canvas tools, zoom, crop, paste, OCR region, document footer |
| `src/video_editor_window.py` | Video editor chrome, playback controls, timeline integration |
| `src/video_canvas.py` | Video playback canvas, vector tools, time-aware annotation visibility |
| `src/video_vector_toolbar.py` | Video editor toolbar (parity with image editor UX) |
| `src/timeline_widget.py` | Scrub ruler, annotation time bars, pan/zoom/page navigation |
| `src/annotation_render.py` | Renders selected annotation items to a transparent image for the system clipboard |
| `src/color_contrast.py` | WCAG luminance/contrast helpers so chrome stays readable over user-chosen colors |
| `src/selection_info.py` | Shared selection-footer formatting for both editors (whole pixels, vertex lists) |
| `src/video_recorder.py` | ffmpeg region recording, pause/resume, segment relocate on drag |
| `src/video_storage.py` | `.sfpv` ZIP save/load (embedded MP4 + manifest) |
| `src/video_models.py` | `VideoAnnotationModel`, `VideoProjectModel` |
| `src/brush_paint.py` | Soft brush/eraser stamps (hardness, opacity) |
| `src/pixel_selection.py` | Raster selection masks for wand/brush clip/fill |
| `src/annotation_items.py` | Serialization, pens, arrows, scene conversion |
| `src/annotation_shapes.py` | `StepBadgeItem`, `StyledTextItem` (plain/box/bubble) |
| `src/crop_item.py` | Crop frame + resize overlay handles |
| `src/models.py` | `AnnotationModel`, `ProjectModel` |
| `src/storage.py` | `.sfp` ZIP save/load (deep-copied payloads on save) |
| `src/session_recovery.py` | Workspace paths, session manifest, tab recovery, tab deletion |
| `src/install_manifest.py` | Records Snappix-installed system packages and user files |
| `src/config.py` | User JSON config, per-tool width/hardness/style maps |
| `src/shortcuts.py` | Editor shortcut definitions and conflict checks |
| `src/settings_dialog.py` | Hotkeys, post-capture, save/workspace folders, shortcut editors |
| `src/theme.py` | Dark/Light/Slate/Sepia QSS + capture/editor accent sheets |
| `src/global_hotkeys.py` | `pynput` global shortcuts → Qt signals |
| `src/image_effects.py` | Pixelation for blur redaction |
| `src/ocr.py` | Tesseract CLI wrapper |
| `src/platform.py` | Wayland detection, grim/slurp, tesseract checks |
| `src/cli.py` | Non-GUI commands |
| `src/autostart.py` | XDG autostart `.desktop` |
| `src/tool_reference.py` / `tool_reference_dialog.py` | In-app tools help |
| `src/help_dialogs.py` | Shared About / Manual dialogs for both editors and the editor host menu |
| `src/desktop_grab.py` | Blank-grab detection plus external screenshot backends (x11grab, maim, import, gnome-screenshot, grim) |
| `src/new_canvas_dialog.py` | Blank canvas size picker |
| `src/canvas_size.py` | Canvas size helpers |
| `src/constants.py` | App name, `.sfp` / `.sfpv` extensions, format versions |

## Capture Pipeline

### Modes

| Mode | Constant | Description |
|------|----------|-------------|
| Fullscreen | `CaptureMode.FULL_SCREEN` | Virtual desktop composite |
| Region | `CaptureMode.REGION` | Drag selection overlay |
| Window | `CaptureMode.WINDOW` | Window pick (X11 `xdotool` / Windows Win32) |
| Scroll | `CaptureMode.SCROLL` | Auto-scroll + vertical stitch |
| Video | N/A | Region select → ffmpeg recording |
| Color pick | N/A | Full-screen eyedropper overlay |

Before framebuffer grabs, the capture panel hides and the compositor is given a short settle window so Snappix chrome does not appear in screenshots (`CAPTURE_UI_SETTLE_MS` in `src/capture.py`).

### Grab sources and the blank-grab fallback

`QScreen.grabWindow(0)` is the fast path, but on some X11 stacks — virtual GPUs,
and compositors that do not keep the root window painted — it returns a pixmap
that is valid, not null, fully opaque, and **completely black**. Retrying does
not help and no error is raised, so the old `isNull()` guard passed it straight
into `RegionCaptureOverlay`: the overlay froze a black desktop and the export was
black. External tools reading the same screen through XGetImage or the
compositor still return real content in that state.

`capture_full_screen()` therefore tries an ordered list of sources and keeps the
first result that has visible content (`src/desktop_grab.py`):

| Source | Order | Notes |
|--------|-------|-------|
| Qt `grabWindow` | first on X11 | Instant; demoted for the rest of the session once it returns blank |
| `ffmpeg -f x11grab` | X11 fallback | ~1 s; `-draw_mouse 0` matches Qt's pointer-free grab |
| `maim`, ImageMagick `import` | X11 fallback | Region-aware, stdout PNG |
| `gnome-screenshot` | X11 fallback | Whole desktop only; result is cropped to the region |
| `grim` | Wayland only, first | Qt cannot grab on Wayland at all |

- `visible_pixmap_fraction()` samples a 64px grid (~2 ms on 5120x1440) and returns
  the share of samples that are opaque and above `BLANK_LUMA_THRESHOLD`.
- **Trust is decided per screen, not per composed image.** The failure is not
  always all-or-nothing: one monitor of two can come back black while the other
  is fine, and the composed desktop then still looks 50 % full — which an
  emptiness check on the whole image happily accepts, freezing a half-black
  desktop into the overlay. `_compose_qt_desktop_grab()` therefore also reports
  the *emptiest* screen's share, and anything below
  `SUSPICIOUS_VISIBLE_FRACTION` (2 %) is cross-checked against an external grab.
- Candidates are ranked `(trusted, overall_fraction)`: a trustworthy grab always
  wins over a suspicious one, even when the suspicious one covers more pixels.
  Content missing on one screen cannot be outvoted by content on another.
- A genuinely dark desktop costs nothing but time: both sources then report the
  same darkness, the image is identical, and it stays capturable.
- Degraded captures are written to the crash log via `crash_log.log_note()`
  ("Degraded screen capture", with backend, visible share, session type, and the
  available fallback tools), and every capture leaves a `breadcrumb()` naming the
  backend and share. An intermittent failure leaves evidence instead of only a
  user report.
- When *all* sources come back blank the image is still returned, with
  `DesktopSnapshot.blank` set — a genuinely black desktop must stay capturable —
  and `_warn_blank_capture_once()` explains the situation once per session.
- `AppConfig.capture_backend` (`auto` / `qt` / `external`, View → Settings →
  Screenshot source) forces one side; `AppController._apply_capture_backend()`
  mirrors it into the capture module.
- MeasureBox's eyedropper (`_sample_screen_pixel`) uses the external path only
  after a full capture proved the Qt grab blank: one black pixel on its own is
  indistinguishable from a legitimately black one.

### Region

1. Snapshot virtual desktop.
2. Show `RegionCaptureOverlay`.
3. On release, crop and emit pixmap.

On Wayland with `grim`/`slurp`, native tools may replace the Qt overlay.

### Window

1. Desktop snapshot (`capture_full_screen`).
2. Highlight overlay; pick target window:
   - **Linux X11:** `xdotool selectwindow` + `xwininfo` (click-through overlay).
   - **Windows:** Win32 `EnumWindows` hit-test (`src/win32_window.py`); overlay accepts the click.
3. Crop snapshot to window rect → editor tab. The crop comes from the snapshot
   taken in step 1, so nothing the overlay draws can ever land in the image.

**The overlay must not win its own hit-test.** It covers the whole virtual desktop
and X11 lists it in `_NET_CLIENT_LIST_STACKING` even though it is click-through, so
`_x11_window_id_at_point()` used to return the overlay for every point: the
highlight was drawn around the entire desktop and the frame disappeared onto the
outermost screen edge. Ownership is decided by `_NET_WM_PID` (`_x11_window_pid()`,
cached per window id) rather than by `winId()` — Qt recreates the native window
while showing it, so the id read in `__init__`/`showEvent` is not the one X lists.
`exclude_hwnds` is still honored on both platforms and is what Windows relies on.

**The highlight frame is drawn outside the target** (`_highlight_frame_rect()`), so
picking never covers pixels the capture will contain; the geometry label follows the
same rule and flips below the window when there is no room above
(`_label_y_outside()`). A window flush against a desktop edge has no outside on
that side, so the frame is pulled back on screen there — visible beats
correct-but-invisible.

On Wayland, window capture is not reliable; the UI recommends Area or Scroll.

### Scroll

1. Window pick (same as window capture: xdotool on Linux, Win32 overlay click on Windows).
2. `perform_auto_scroll_capture()` focuses content, scrolls top→bottom (xdotool keys / Win32 `SendInput` PageDown), captures frames.
3. `src/scroll_capture.py` stitches with overlap detection.
4. Result opens in the editor; **Esc** cancels during pick.

Windows scroll is best-effort for normal (non-elevated) desktop apps; custom/Electron scrollers may need focus in the right child.

### Video recording

1. User selects a screen region.
2. `VideoRecorder` runs ffmpeg in segments; pause/resume via SIGSTOP/SIGCONT.
3. `RecordingBorderOverlay` shows elapsed time and supports drag-to-relocate (segment restart).
4. On stop, segments are concatenated; result opens in `VideoEditorWindow`.

Requires `ffmpeg`. X11 only for now.

### Maximum video length

`MAX_VIDEO_DURATION_MS` (`src/constants.py`, 30 minutes) is the single limit for
every video entering the editor. `validate_video_duration()` and the shared
`video_too_long_message()` live in `src/media_import.py` and gate three paths in
`run.py`: finished recordings (`_recording_fits_editor_limit()`), video import,
and opening a `.sfpv` project. Playback itself streams through `QMediaPlayer` and
has no hard ceiling — the cap exists to keep timeline navigation and MP4 export
practical, so raising it is a one-constant change. A rejected recording is left
on disk and its path is named in the warning dialog.

### Cancelling a capture (Escape)

Most overlays handle Escape themselves. The Linux **window** and **scroll**
pickers cannot: their `WindowCaptureOverlay` is `WindowTransparentForInput` so
`xdotool selectwindow` can pick the window underneath, which also leaves no
window of the app able to receive key events — `keyPressEvent`, `grabKeyboard()`,
and the application-wide Escape `QShortcut` are all dead in that state. Both
paths therefore run an `EscapeListener` (`src/global_hotkeys.py`) for the
duration of the pick: a passive pynput listener that never suppresses the key
and marshals to the Qt thread via a signal. Without pynput the pick simply stays
click-only. Any new capture path that hides the app from the keyboard needs the
same listener.

### Post-capture actions

| Config value | Behavior |
|--------------|----------|
| `editor` | New editor tab (default) |
| `clipboard` | Copy pixmap |
| `save` | PNG to configured or `~/Downloads/snappix/` |

## Editor Architecture

### Host

`AppController` owns `EditorHostWindow` (`objectName: editorHost`) with a closable `QTabWidget`. Each tab is either:

- `EditorWindow` — image/screenshot editor (embedded `QMainWindow`)
- `VideoEditorWindow` — video editor with timeline

Accent styling: `build_editor_accent_stylesheet(theme)` on the host; capture panel uses `build_capture_accent_stylesheet(theme)`.

#### Host menu bar

Each tab is a `QMainWindow` that draws its own menu bar *inside* the tab, so with
zero tabs the editor had no menu at all. `_build_editor_host_menu()` gives the host
its own File / View / Help menu covering the tab-independent actions (new canvas,
open/import, capture panel, theme, settings, update/about/manual);
`_sync_editor_host_view()` shows it only while `editor_tabs.count() == 0` so two
menu bars are never stacked.

Two constraints shape that code:

- The host key bindings are `QShortcut` objects on the same window
  (`_install_host_editor_shortcuts()`). Giving the menu actions the same sequences
  would make Qt report an ambiguous shortcut and fire neither, so the binding is
  only *rendered* — `_host_menu_label()` appends `"\t<hint>"`, which Qt draws in the
  menu's shortcut column.
- PySide hands the menu bar and its menus to Python ownership; dropping the
  references destroys the C++ objects and leaves titles that open nothing. They are
  kept in `_host_menu_bar` / `_host_menus`.

### Image canvas

`EditorCanvas` (`QGraphicsView`):

- Screenshot background item + gray workspace chrome outside the document
- Annotation items tagged with `ITEM_ROLE_TYPE = 1001`
- Tool state machine, crop, pixel selection, soft brush buffer
- **Two text item classes**: `StyledTextItem` (plain/box/speech-bubble, `src/annotation_shapes.py`) and legacy `QGraphicsTextItem`. They share `font()` but *not* the setter — `set_font()` vs `setFont()` + `document().setDefaultFont()`. Always go through `apply_text_item_font()`; calling `setFont` on a `StyledTextItem` raises `AttributeError`, and the resize paths run inside Qt virtual overrides where that unwinds through C++ and segfaults the process a few events later. `CropSelectionItem._notify_geometry_changed()` now contains any callback failure and reports it via `crash_log.log_exception()` instead of letting it reach C++
- Document footer payload when nothing is selected (`type: document`)
- Rubber-band preview for polyline/polygon/bent-arrow path tools

### Video canvas + timeline

`VideoCanvas`:

- `QMediaPlayer` + `QGraphicsVideoItem` for playback
- Vector annotations visible only when playhead is inside `[start_ms, end_ms]`
- Cached duration for reliable session flush when the player shuts down
- `delete_annotations_by_ids()` removes models by id regardless of canvas selection; `delete_selected_annotations()` delegates to it after filtering out locked items

`TimelineWidget`:

- One row per annotation; draggable/resizable time-range bars (`ROW_HEIGHT` 20px)
- Painted entirely from `get_theme_colors()` tokens — ruler `surface_alt`, label column `surface`, track `window_bg`, grid `border`, ticks `text_muted`, selection `accent`. It previously hardcoded dark grays, which left it a near-black slab on the light and sepia themes.
- The playhead is deliberately achromatic (`timeline_playhead` over `timeline_playhead_halo`) with a handle in the ruler: every hue in `STYLE_PALETTE_COLORS` belongs to user content, and `DEFAULT_STROKE_COLOR` (`#e74c3c`) used to *be* the playhead color, so the playhead vanished inside the most common bar. Halo-over-core keeps it above WCAG 1.4.11's 3:1 against any bar underneath.
- Bar fills and borders run through `ensure_min_contrast()` (`src/color_contrast.py`) against the track, so an annotation colored close to the surface — a text object's dark navy on the dark themes — cannot sink into it and read as disabled. The tint alpha is applied *before* measuring; lifting the opaque color first lets the blend drag contrast back under the threshold.
- Selecting a bar and pressing `Del` emits `annotation_delete_requested`; `VideoEditorWindow` routes it to `VideoCanvas.delete_annotations_by_ids()` and pushes one history step, so row and canvas object are removed together. The widget uses `StrongFocus` so the key reaches it after a click.
- Because the timeline takes click focus, `VideoEditorWindow.keyPressEvent()` re-offers `CANVAS_FALLBACK_KEYS` (`Esc`, `Return`/`Enter`, `Del`) to `VideoCanvas` when they bubble up unhandled. Without that, clicking the timeline would strand the canvas's cancel-draw / finalize-polygon / delete-selection keys until the canvas was clicked again.
- Full-width track area; page-based pan (`◀` / `▶`, Ctrl+drag, Ctrl+wheel zoom)
- Initial view: full width for clips ≤20s; fixed 20s pages for longer clips (100s → five pages). Zoom/pan adjust afterward.
- A plain click anywhere on the timeline (ruler or empty track space) scrubs the playhead; double-click and hold, then drag, stretches/compresses the visible time range around the double-click point (`SizeHorCursor` while held)
- Right-click a bar → *Add Effect...* opens `EffectsDialog` (`src/effects_dialog.py`) to add/edit/remove Fade/Zoom/Slide entry/exit effects, stored per-annotation in `payload["effects"]` (see `src/video_effects.py`); the bar label shows a short summary (e.g. `[Fade In, Zoom Out]`). Effects render live via `apply_effect_render_state()` during playback/scrubbing, and are baked into MP4 export: `VideoEditorWindow.export_cut_points()` slices each effect window into at most `EXPORT_EFFECT_SLICES` steps (never below `EXPORT_MIN_SLICE_MS`), and `_paint_annotation_for_export()` applies the same opacity/scale/offset per slice

### Vertex editing (both editors)

`PolyPathItem` (`src/shape_items.py`) backs polyline, polygon, and bent arrow in
*both* editors, so vertex editing exists in both by construction. A selected
shape paints a handle per vertex; pressing one starts a vertex drag, pressing
anywhere else falls through to Qt's `ItemIsMovable` so the shape still moves as
a whole. Holding **Shift** during a vertex drag pins the axis that has travelled
less (`lock_vertex_target()`). `boundingRect()` is widened by `VERTEX_HANDLE_PX`
so handles at the outline are not clipped.

Triangle is *not* vertex-editable: it is a `PathShapeItem` inscribed in a
bounding rect (`build_triangle_path()`), so its corners are derived from
`x/y/width/height` and it has no per-vertex data to store. Making it freely
editable means giving it a points payload plus load/save/export handling — a
data-model change, not a UI tweak.

### Selection footer

`format_selection_info()` (`src/editor_window.py`) renders both editors' status
bars via `src/selection_info.py`. Geometry is reported as whole pixels —
`size(x/y):10x10px pos(x/y):30x20px` — because fractional values were scene-math
noise, not something a user can act on. Vertex shapes additionally list their
corners, truncated past `MAX_LISTED_VERTICES` so a traced polyline cannot push
the rest of the bar out of view. `VideoCanvas._refresh_selection_style()` emits
the same geometry keys as `EditorCanvas._build_selection_payload()`; without
them the video footer would render an empty summary.

### Tool identifiers (image editor)

| Tool ID | Description |
|---------|-------------|
| `select` | Move / select annotations |
| `select_rect` / `select_ellipse` / `select_path` | Pixel selection shapes / lasso |
| `magic_wand` | Color-based pixel selection |
| `brush` / `eraser` | Soft freehand paint / erase |
| `bucket` | Fill active pixel selection |
| `eyedropper` | Sample border or fill color |
| `rect` / `ellipse` / `line` / `arrow` | Vector annotations |
| `text` | Plain / box / bubble text |
| `fill_bg` | Paint rectangle on screenshot pixels |
| `blur` | Pixelate region |
| `step` | Numbered badge |
| `ocr` | OCR region → clipboard |
| `crop` | Non-destructive crop |

Video editor exposes a matching subset via `VideoVectorToolbar` and `VideoCanvas`.

### Drawing modes

- **One-shot:** After a completed draw action, switch back to Select (unless locked).
- **Lock:** Double-click a lockable tool to keep it until clicked again or another tool is chosen.

### Per-tool defaults (persisted)

Stored in `config.json` and restored on tool switch / editor open:

| Map | Tools | UI |
|-----|-------|-----|
| `tool_stroke_widths` | brush, eraser, rect, ellipse, line, arrow, text, … | Tool popup **Thickness** (config/JSON key kept as `tool_stroke_widths`/`stroke_width` for saved-file compatibility; only the UI label reads "Thickness") |
| `tool_brush_hardness` | brush, eraser | Tool popup **Hard** |
| `tool_stroke_styles` | rect, ellipse, line, arrow, … | Tool popup **Style** |

Tool popups (Thickness/Style/Radius) only ever set the tool's default for newly drawn objects — they no longer edit a live selection. Editing an existing object's thickness/style/(rect) radius happens via the **Style property tab** instead, alongside its colors; that tab shows only a single selected object's settings and hides entirely when nothing, or more than one object, is selected. Both `EditorWindow` and `VideoVectorToolbar` implement this the same way (`_SHAPE_THICKNESS_SELECTION_TYPES` / `_SHAPE_STYLE_SELECTION_TYPES` / `_SHAPE_RADIUS_SELECTION_TYPES`, kept in sync by `tests/test_editor_video_parity.py`). Brush/eraser hardness has no selectable object to re-edit (baked into raster pixels at draw time), so it stays tool-default-only in both editors.

### History and autosave

- Undo/redo: full canvas snapshots (screenshot + annotations + base content origin)
- Per-tab recovery: `flush_recovery_snapshot()` every 30 s
- Video tabs copy source MP4 into `video-sources/` and embed in `.sfpv` on flush
- Session manifest written on tab changes, host hide, and app quit
- Qt validity guards (`shiboken6.isValid`) prevent flush during teardown races

## Session Workspace

Configurable via `workspace_directory` in settings (default `~/.snappix`). Set at runtime through `session_recovery.set_workspace_root()`.

```text
~/.snappix/
  session.json                 # open tabs manifest (version 1)
  tabs/
    tab-<uuid>.sfp             # image recovery project
    tab-<uuid>.sfpv            # video recovery project
  video-sources/
    tab-<uuid>.mp4             # session-local video copies
  video-assets/
    tab-<uuid>/                # extracted MP4 for Qt playback on restore
```

### Lifecycle

| Event | Behavior |
|-------|----------|
| App quit with open tabs | Flush all tabs → write `session.json` |
| App start | Load manifest → recreate tabs → load models |
| Tab close (confirmed) | `delete_tab_recovery_data(path)` → update manifest |
| Last tab closed | `save_editor_session([])` → `clear_editor_session()` |
| Legacy `/tmp/snappix-session/` | Migrated into workspace on first use when empty |

### Key APIs (`src/session_recovery.py`)

| Function | Role |
|----------|------|
| `set_workspace_root(path)` | Configure workspace directory |
| `create_tab_recovery_path()` | New image tab `.sfp` under `tabs/` |
| `create_video_tab_recovery_path()` | New video tab `.sfpv` under `tabs/` |
| `save_editor_session(tabs)` | Write manifest; clear workspace when `tabs` is empty |
| `load_editor_session()` | Read manifest; skip missing/empty recovery files |
| `delete_tab_recovery_data(path)` | Remove tab project, video source, extract dir |
| `clear_editor_session()` | Remove manifest + workspace subdirectories |

## Install and Uninstall

Zero-Python entry points: `Snappix.bat` (Windows) and `snappix.sh` (Linux) download a project-local **uv** binary, install managed **CPython 3.12** under `.snappix-runtime/`, then run the Python installer and start the app.

### Installer (`install_dependencies.py` + `src/runtime_bootstrap.py`)

1. Detect missing required/recommended system packages.
2. Install via apt/dnf/pacman/zypper (Linux; sudo or pkexec in GUI mode) or winget (Windows: ffmpeg/tesseract).
3. Record **only newly installed** packages in `install-manifest.json`.
4. Ensure project-local uv + managed Python 3.12, create `.venv`, and `uv pip install -r requirements.txt`.
5. Record created `.venv`, `.snappix-runtime`, and user integration files (desktop entries, icons, autostart).

### Uninstaller (`uninstall_dependencies.py`)

Reads `install-manifest.json` and removes:

- Project `.venv` when Snappix created it
- Project `.snappix-runtime` when Snappix created it
- User files Snappix wrote (launchers, icons, autostart entry)
- System packages Snappix installed, **only when apt dry-run shows no foreign manual dependencies**

Pre-existing system packages are never recorded and never removed.

## Annotation Model

### Image (`AnnotationModel`)

| Field | Type | Notes |
|-------|------|-------|
| `annotation_type` | str | `rect`, `ellipse`, `line`, `arrow`, `text`, `image`, `step`, … |
| `x`, `y`, `width`, `height` | float | Scene geometry |
| `stroke_rgba`, `fill_rgba` | list[int] | RGBA 0–255 |
| `stroke_width` | float | `0` → NoPen for shapes/text borders |
| `text` / `font_*` | various | Text / step content |
| `payload` | dict | `stroke_style`, `text_style`, `z_index`, `step_number`, transforms, `image_png_base64` |

### Video (`VideoAnnotationModel`)

Adds `start_ms` and `end_ms` for timeline visibility. Stored inside `VideoProjectModel.annotations`.

Custom items: `StepBadgeItem`, `StyledTextItem`, `ArrowItem`.

## Project Storage

### Image (`.sfp`)

`PROJECT_FORMAT_VERSION = 3`

ZIP (`ZIP_DEFLATED`):

| Path | Content |
|------|---------|
| `manifest.json` | Metadata + annotations |
| `assets/screenshot.png` | Base screenshot |
| `assets/image-*.png` | Externalized pasted images |

`save_project` deep-copies annotation payloads before stripping image bytes so live models stay intact across autosaves.

Legacy JSON / `.lshot` still load.

### Video (`.sfpv`)

ZIP:

| Path | Content |
|------|---------|
| `manifest.json` | Video metadata + annotation timeline |
| `assets/source.mp4` | Embedded source video (`ZIP_STORED`) |

`save_video_project` reuses the existing embedded MP4 when the source file on disk is missing (recovery update path).

## Corner Radius

`build_rounded_polygon_path` in `src/shape_items.py` rounds any closed polygon with true circular
arcs -- the same arcs `addRoundedRect` produces, so a rectangle and a triangle look identical at the
same radius (pinned by a test comparing enclosed areas). `build_triangle_path` uses it; polygon and
star can adopt it unchanged.

Rounding a corner means walking back along both edges by `r / tan(angle/2)` and joining the tangent
points with an arc. Two consequences follow from that formula:

- **A sharper corner pushes its arc further from the vertex.** A 20px radius on an 11-degree triangle
  tip sits ~180px below the tip. This is correct circular geometry and matches vector editors; it is
  not a clamping bug.
- **Clamping is per edge, not per corner.** An edge is shared by two corners, so the constraint is
  `d(A) + d(B) <= edge length`. Capping each corner at half the edge instead would clamp a sharp apex
  even when its blunt neighbours leave most of the edge unused.

The slider's 0-90 value is passed through as a **pixel** radius, not an angle, and `build_rect_path`
clamps it to half the shorter edge. The usable range is therefore size-dependent: a 60x40 rectangle
saturates at 20, a 200x150 one at 75.

`SHAPE_RADIUS_TYPES` in `src/shape_items.py` lists the kinds whose corners can be rounded. Adding a
kind means honouring it along the *whole* chain -- applying to a selection (`set_rect_corner_radius`
in both canvases), serializing, and restoring. A kind present in the Edit panel's visibility set but
missing from the apply path shows the slider and silently ignores it.

Note the restore branch for `rect` hardcodes `configure_graphics_item(item, "rect")`, so other radius
kinds must go through the generic `PATH_SHAPE_KINDS` branch, which passes the annotation type
through correctly.

## Window Detection

`detect_window_at_point` answers "which window covers this screen coordinate?" -- used by the
capture overlay to highlight the window under the cursor.

On X11 it walks `_NET_CLIENT_LIST_STACKING` (from `xprop`, bottom-to-top) from the **top
down** and returns the first window whose geometry contains the point. Direction matters:
the desktop covers every point, so a bottom-up walk always returns it.

It must not use `xdotool getmouselocation`. That call can only ever answer for the real
pointer, so it silently ignores the coordinate it was asked about -- every point then
resolves to the same window, and once walked upward, usually the desktop. On screen that
reads as "the window highlight is missing", because a highlight frame around the whole
screen is indistinguishable from none. `tests/test_window_detection.py` pins this.

`getmouselocation` remains only as a fallback for window managers that publish no stacking
hint, where the pointer's own window is the best available answer.

## Crash Logging

`src/crash_log.py`, installed first thing in `main()` so it covers startup too. Four
sources feed `~/.cache/snappix/crash.log`:

| Source | Catches |
|--------|---------|
| `faulthandler` | Fatal signals (segfault, abort) -- the ones that otherwise leave nothing |
| `sys.excepthook` | Uncaught exceptions on the main thread |
| `threading.excepthook` | The same on workers, which otherwise die silently |
| `qInstallMessageHandler` | Qt's own warnings |

The Qt handler matters most for this app's crash class: PySide prints "Internal C++ object
already deleted" *before* the process dies, so the warning preceding a crash often names a
cause the C-level stack no longer can. It is installed after `QApplication` exists, which
is why it is a separate call from `install()`.

Breadcrumbs (`crash_log.breadcrumb`) record recent user actions in memory and are flushed
as part of any crash block. A segfault inside Qt's scene graph produces a stack that says
nothing about which interaction triggered it; the trail says "press tool=select on=arrow,
move arrow". Fed from `_emit_content_changed` (completed actions) and from the canvas mouse
press (drags that crash before completing). Bounded deque -- an unbounded trail would grow
for the life of the process.

Every path swallows its own errors: a full or unwritable disk must never turn a crash
report into a second crash.

## Presentation Frame

`src/presentation_frame.py` composites the export frame; `src/presentation_frame_dialog.py` is its
editor. It runs last in the export pipeline, on the already-flattened pixmap, and never inspects the
screenshot's own pixels -- it only places that pixmap on a larger canvas.

Every export path (PNG, JPEG, PDF, SVG, batch, clipboard) funnels through
`EditorWindow._export_output_pixmap`, so wiring the frame in there covers all of them at once.

| Setting | Unit | Why |
|---------|------|-----|
| `padding_percent` | % of the source's longer edge | One value looks the same on a 400px crop and a 4K capture |
| `corner_radius` | px at @1x, multiplied by export scale | Keeps roundness visually identical at @2x/@3x |
| shadow blur / offset | 3% / 1.5% of longer edge | Scales with the image; deliberately subtle so annotations stay the loudest elements |
| `shadow_opacity` | 0..1, painted as pure black | Gray shadows turn muddy over a colored backdrop; black-with-alpha stays correct on any color |
| `aspect_ratio` | preset or `auto` | Letterboxes only -- the frame grows, so a preset can never crop the screenshot |

The second gradient stop is derived from the first (hue +18 degrees, lightness -20) rather than being
picked separately: two stops far apart read as a poster, a narrow shift reads as a lit surface.

The shadow uses `QGraphicsDropShadowEffect` through a throwaway `QGraphicsScene` so the blur runs in
Qt rather than pixel-by-pixel in Python, which matters for @3x full-screen exports.

JPEG cannot store alpha, so `_export_output_pixmap` swaps a transparent backdrop for a white matte
before encoding -- otherwise the encoder flattens it to black.

Frame settings live for the session only, matching the existing export scale and transparency
preferences. `PresentationFrame.to_payload` / `from_payload` exist and sanitize their input, so
persisting them later is a wiring change, not a rewrite.

## Configuration

Path: `~/.config/snappix/config.json`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `autostart_enabled` | bool | `false` | XDG autostart; the generated autostart entry launches with `--autostart`, which keeps the app tray-only (no Capture window, no restored Editor tabs) — see `run.py:_autostart_login_exec_command` / `AppController(autostart_launch=...)` |
| `theme` | str | `"dark"` | `dark` / `light` / `slate` / `sepia` |
| `hotkeys_enabled` | bool | `true` | Global shortcuts |
| `hotkey_capture_region` | str | `ctrl+shift+a` | Area hotkey |
| `hotkey_capture_window` | str | `ctrl+shift+w` | Window hotkey |
| `hotkey_capture_fullscreen` | str | `ctrl+shift+f` | Fullscreen hotkey |
| `hotkey_capture_video` | str | `ctrl+shift+v` | Start video capture |
| `hotkey_recording_pause_resume` | str | `ctrl+shift+p` | Pause/resume recording |
| `hotkey_recording_stop` | str | `ctrl+shift+r` | Stop recording |
| `post_capture_action` | str | `editor` | Post-capture routing |
| `capture_save_directory` | str | `""` | Save folder override → `~/Downloads/snappix` |
| `workspace_directory` | str | `""` | Session workspace override → `~/.snappix` |
| `editor_last_tab_behavior` | str | `keep_open` | Last-tab close behavior |
| `export_preset` | str | `docs` | Last export preset |
| `export_scale` | float | `1.0` | Export scale 1 / 2 / 3 |
| `export_keep_transparency` | bool | `true` | PNG alpha |
| `batch_export_profiles` | list | built-ins | Named batch profiles |
| `batch_export_profile_key` | str | `docs_hq` | Active batch profile |
| `batch_export_last_directory` | str | `""` | Last batch output dir |
| `auto_crop_on_shrink` | bool | `true` | Shrink unused canvas margins |
| `editor_shortcuts` | dict | `{}` | Shortcut overrides |
| `tool_stroke_widths` | dict | see defaults | Per-tool widths |
| `tool_brush_hardness` | dict | brush/eraser `80` | Per-tool hardness |
| `tool_stroke_styles` | dict | all `solid` | Per-tool line styles |

## Theming

`src/theme.py` builds global QSS plus capture-red and editor-blue accent overrides.

Notable object names: `primaryButton`, `linkButton`, `mutedLabel`, `titleLabel`, `editorToolbar`, `editorHost`, `capturePanel`.

Four themes share one token system (`ThemeColors`); light-family themes include Light and Sepia.

## Global Hotkeys

`src/global_hotkeys.py` + `pynput`. Specs normalize to lowercase (`ctrl+shift+a`) and map to pynput syntax. Callbacks hop to the Qt thread via `HotkeyBridge`.

Reliable on X11; Wayland depends on the compositor.

## Platform Support

| Feature | X11 | Wayland | Windows |
|---------|-----|---------|---------|
| Fullscreen | Yes | Yes (Qt / grim) | Yes (Qt) |
| Region | Overlay | Overlay or grim+slurp | Overlay |
| Window | xdotool | Not supported | Win32 pick + snapshot crop |
| Scroll | Yes | Limited / best-effort | Win32 PageDown + stitch (best-effort) |
| Video recording | ffmpeg region | Not supported yet | ffmpeg gdigrab |
| Global hotkeys | pynput | Limited | pynput |
| Color picker | Overlay | Overlay | Overlay |

## OCR

Two entry points share `src/ocr.py`'s `extract_text_from_png_bytes()`:

1. **Editor OCR tool** (`Tool.OCR`) → drag a region on an open document → composited crop → temp PNG → `tesseract` CLI → clipboard (+ status bar message).
2. **Capture panel OCR button** (`src/capture.py:execute_text_recognition`) → drag a region directly off the screen (like Capture Area) → the captured pixmap is run through OCR and discarded; only the recognized text is copied to the clipboard. Hidden automatically when `tesseract` isn't installed (`CapturePanel.set_text_recognition_available`).

Requires `tesseract` on `PATH`.

## CLI

| Command | Description |
|---------|-------------|
| `capture` | `--mode`, `--delay`, `--output` |
| `pick-color` | Optional `--clipboard` |
| `export` | Project → PNG/JPG/PDF |
| `batch-export` | Multiple projects/formats |
| `open` | GUI with project |

## Testing

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Coverage includes config/storage, annotations, brush freeze guards, canvas resize/workspace, editor history/one-shot/lock, video canvas selection, timeline paging, session recovery/workspace, install/uninstall manifest, scroll stitch, and E2E editor flows.

Prefer deterministic unit tests over live X11 smoke as the release gate.

## Packaging

| Script | Output |
|--------|--------|
| `packaging/build_deb.sh` | `dist/snappix_{version}_{arch}.deb` |
| `packaging/build_appimage.sh` | `dist/Snappix-{version}-x86_64.AppImage` |

README screenshots: `scripts/generate_readme_screenshots.py` → `docs/screenshots/`.

Requires a Qt display (`DISPLAY` or `WAYLAND_DISPLAY`). The video-editor capture optionally uses `ffmpeg` to synthesize a short sample MP4.

## Dependencies

| Package | Purpose |
|---------|---------|
| PySide6 | Qt 6 GUI, multimedia, PDF |
| Pillow | Image helpers |
| requests | Paste image from URL |
| pynput | Global hotkeys |

System (installed on demand): `xdotool`, `x11-utils`, `tesseract-ocr`, `grim`, `slurp`, `ffmpeg`, …

## Extension Points

| Goal | Where |
|------|--------|
| New annotation type | `annotation_items.py`, `annotation_shapes.py`, `EditorCanvas` / `VideoCanvas` |
| New capture mode | `CaptureMode` + `execute_capture_request()` |
| New export format | `EditorWindow` / `VideoEditorWindow` export helpers + CLI |
| New setting | `AppConfig` + `ConfigManager` + `SettingsDialog` |
| Per-tool option | Tool popup in editor windows + normalize helpers in `config.py` |
| Theme token | `ThemeColors` + stylesheet builders |
| Workspace layout | `session_recovery.py` path helpers |

## Known Limitations

- PDF export uses `QPdfWriter`; behavior can vary by PySide6 build.
- Window capture needs X11 tooling on Linux; Windows uses Win32 pick + snapshot crop.
- Video recording uses ffmpeg (`x11grab` / `gdigrab`); pause semantics differ by OS.
- Scroll stitch assumes mostly vertical scroll with overlapping frames; Windows uses PageDown best-effort.
- OCR quality depends on Tesseract language packs and image clarity.
- Embedding `QMainWindow` tabs is intentional but unusual; destroy/autosave paths must keep Qt object validity checks.
- Changing the workspace folder in settings applies on next path resolution; migrate data manually if needed.
- MP4 export re-encodes with `libx264 -crf 18`; long videos take minutes. The progress dialog stays cancellable throughout, but there is no background-queue export.
