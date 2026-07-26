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
3. Crop snapshot to window rect → editor tab.

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

### Image canvas

`EditorCanvas` (`QGraphicsView`):

- Screenshot background item + gray workspace chrome outside the document
- Annotation items tagged with `ITEM_ROLE_TYPE = 1001`
- Tool state machine, crop, pixel selection, soft brush buffer
- Document footer payload when nothing is selected (`type: document`)
- Rubber-band preview for polyline/polygon/bent-arrow path tools

### Video canvas + timeline

`VideoCanvas`:

- `QMediaPlayer` + `QGraphicsVideoItem` for playback
- Vector annotations visible only when playhead is inside `[start_ms, end_ms]`
- Cached duration for reliable session flush when the player shuts down

`TimelineWidget`:

- One row per annotation; draggable/resizable time-range bars
- Full-width track area; page-based pan (`◀` / `▶`, Ctrl+drag, Ctrl+wheel zoom)
- Initial view: full width for clips ≤20s; fixed 20s pages for longer clips (100s → five pages). Zoom/pan adjust afterward.

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
| `tool_stroke_widths` | brush, eraser, rect, ellipse, line, arrow, text, … | Tool popup **Width** |
| `tool_brush_hardness` | brush, eraser | Tool popup **Hard** |
| `tool_stroke_styles` | rect, ellipse, line, arrow, … | Tool popup **Style** |

With a matching selection, Width/Style updates apply to selected items instead of only the tool default.

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

## Configuration

Path: `~/.config/snappix/config.json`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `autostart_enabled` | bool | `false` | XDG autostart |
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

1. OCR tool → drag region.
2. Composited crop → temp PNG.
3. `tesseract` CLI → clipboard (+ status bar message).

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
