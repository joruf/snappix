# Snappix Technical Documentation

This document describes the Snappix architecture, module responsibilities, data formats, and extension points for developers.

## Overview

Snappix is a Linux desktop application written in Python 3.11+ with PySide6 (Qt 6). It follows a controller-driven architecture:

```text
run.py (AppController)
├── CapturePanel + capture overlays (src/capture.py)
├── EditorHostWindow + EditorWindow tabs (run.py, src/editor_window.py)
├── System tray + settings (run.py, src/settings_dialog.py)
├── Config persistence (src/config.py)
├── Global hotkeys (src/global_hotkeys.py)
└── Theme engine (src/theme.py)
```

The application enforces a single running instance via a file lock in `~/.cache/snappix/snappix.lock`.

## Entry Points

| Entry | File | Purpose |
|-------|------|---------|
| Main GUI | `run.py` | Desktop startup, tray, capture/editor coordination |
| Package entry | `src/__main__.py` | `python -m src` |
| CLI | `src/cli.py` | Headless capture, export, open project |
| Installer | `install_dependencies.py` | Creates `.venv`, installs system packages and pip deps |

Startup sequence:

1. Re-exec into `.venv` if available.
2. Ensure PySide6 exists (Tkinter installer UI if missing).
3. Acquire single-instance lock.
4. Create `QApplication`, load config, apply theme.
5. Show capture panel and optionally restore recovery snapshot or startup project.

## Source Module Map

| Module | Responsibility |
|--------|----------------|
| `run.py` | `AppController`, tray menu, editor host, hotkey wiring, post-capture actions |
| `src/capture.py` | Capture panel, region/window/scroll overlays, color picker, capture engine |
| `src/editor_window.py` | Editor UI shell, toolbar, menus, export/print, history |
| `src/editor_canvas.py` | Interactive canvas, tools, zoom, crop, paste, z-order, OCR region |
| `src/annotation_items.py` | Annotation serialization, pens, arrows, scene conversion |
| `src/annotation_shapes.py` | Step badges, styled text (box/bubble) |
| `src/crop_item.py` | Resizable crop frame and resize overlay handles |
| `src/models.py` | `AnnotationModel`, `ProjectModel` dataclasses |
| `src/storage.py` | `.sfp` ZIP save/load, legacy JSON support |
| `src/config.py` | User settings JSON persistence |
| `src/theme.py` | Light/dark QSS generation and color tokens |
| `src/global_hotkeys.py` | System-wide shortcuts via `pynput` |
| `src/settings_dialog.py` | Hotkeys, post-capture action, save folder UI |
| `src/image_effects.py` | Screenshot pixelation for blur/redaction |
| `src/platform.py` | Wayland detection, grim/slurp, tesseract availability |
| `src/auto_scroll_capture.py` | Automatic window scroll capture and scrollbar detection |
| `src/scroll_capture.py` | Vertical frame stitching for scroll capture |
| `src/ocr.py` | Tesseract OCR wrapper |
| `src/cli.py` | Non-GUI commands |
| `src/autostart.py` | XDG autostart desktop entry management |
| `src/constants.py` | App name, project format version |

## Capture Pipeline

### Capture modes

| Mode | Constant | Description |
|------|----------|-------------|
| Fullscreen | `CaptureMode.FULL_SCREEN` | Virtual desktop composite |
| Region | `CaptureMode.REGION` | Drag selection overlay |
| Window | `CaptureMode.WINDOW` | X11 window selection via `xdotool` |
| Scroll | `CaptureMode.SCROLL` | Multi-frame vertical stitching |
| Color pick | N/A | Full-screen eyedropper overlay |

### Desktop snapshot

`capture_full_screen()` composites all `QScreen` instances into one virtual desktop pixmap using each screen's geometry.

### Region capture

1. Capture full virtual desktop snapshot.
2. Show `RegionCaptureOverlay` with dimmed mask.
3. User drags a rectangle; on release, crop and emit pixmap.

On Wayland, when `grim` and `slurp` are installed, region capture can bypass the Qt overlay and use native Wayland tools instead.

### Window capture (X11)

1. Capture desktop snapshot.
2. Run `xdotool selectwindow`.
3. Resolve window geometry via `xwininfo`.
4. Crop snapshot to window rectangle.

On Wayland, window capture is not supported reliably; the app shows an informational dialog and recommends region or scroll capture.

### Scroll capture

1. User picks a target window with `xdotool selectwindow` (same flow as window capture).
2. `perform_auto_scroll_capture()` detects a vertical scrollbar, jumps to the top, captures frames while scrolling down, and stops at the bottom.
3. Frames are stitched vertically using overlap detection in `src/scroll_capture.py`.
4. The stitched screenshot opens in the editor.
5. **Esc** cancels during window selection.

### Post-capture actions

Configured in `~/.config/snappix/config.json`:

| Value | Behavior |
|-------|----------|
| `editor` | Open result in a new editor tab (default) |
| `clipboard` | Copy pixmap to clipboard |
| `save` | Save PNG to configured or default folder |

Default save folder: `~/Pictures/Snappix/`

## Editor Architecture

### Editor host

`AppController` owns one `EditorHostWindow` with a closable `QTabWidget`. Each tab is an `EditorWindow` instance.

### Canvas and tools

`EditorCanvas` extends `QGraphicsView` and manages:

- Background screenshot item (`QGraphicsPixmapItem`)
- Annotation items with type metadata (`ITEM_ROLE_TYPE = 1001`)
- Tool state machine
- Undo/redo via full state snapshots in `EditorWindow`
- Non-destructive crop with annotation coordinate transform

### Tool identifiers

| Tool ID | Description |
|---------|-------------|
| `select` | Move/select annotations |
| `rect` | Rectangle |
| `ellipse` | Ellipse/circle |
| `line` | Line |
| `arrow` | Arrow with head |
| `text` | Text (plain, box, or bubble) |
| `fill_bg` | Fill screenshot pixels in rectangle |
| `blur` | Pixelate screenshot region (redaction) |
| `step` | Numbered step badge |
| `ocr` | OCR region → clipboard |
| `crop` | Non-destructive crop selection |

### Drawing modes

- **One-shot:** After drawing, tool returns to Select (unless locked).
- **Lock mode:** Double-click a drawing tool button to persist the tool until clicked again.

### Style state

`StyleState` in `src/annotation_items.py` holds active defaults:

- Stroke/fill/text colors and opacity
- Stroke width
- Line style: `solid`, `dash`, `dot`, `dash_dot`
- Font family, size, bold/italic/underline
- Text container style: `plain`, `box`, `speech_bubble`

### Layer order

Z-order is stored in each annotation's `payload.z_index`. Edit menu actions and `duplicate_selected_items()` update z-values accordingly.

## Annotation Model

`AnnotationModel` fields:

| Field | Type | Notes |
|-------|------|-------|
| `annotation_type` | str | `rect`, `ellipse`, `line`, `arrow`, `text`, `image`, `step` |
| `x`, `y`, `width`, `height` | float | Geometry in scene coordinates |
| `stroke_rgba`, `fill_rgba` | list[int] | RGBA 0–255 |
| `stroke_width` | float | Pen width |
| `text` | str | Text content or step number |
| `font_*` | various | Text styling |
| `payload` | dict | Extensions: `stroke_style`, `text_style`, `z_index`, `step_number`, `image_png_base64` |

Custom items:

- `StepBadgeItem` — numbered callout circles
- `StyledTextItem` — text with box or speech-bubble background
- `ArrowItem` — line with triangular arrowhead

## Project Storage (`.sfp`)

Version: `PROJECT_FORMAT_VERSION = 3` (see `src/constants.py`)

Container: ZIP with `ZIP_DEFLATED`

| Path | Content |
|------|---------|
| `manifest.json` | Project metadata and annotation list |
| `assets/screenshot.png` | Base screenshot |
| `assets/image-*.png` | Externalized pasted images |

Legacy plain JSON/`.lshot` files can still be loaded.

Auto-recovery snapshot: `{tempdir}/snappix-autosave.sfp` every 30 seconds.

## Configuration

Path: `~/.config/snappix/config.json`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `autostart_enabled` | bool | `false` | XDG autostart |
| `theme` | str | `"dark"` | `"dark"` or `"light"` |
| `hotkeys_enabled` | bool | `true` | Global shortcut registration |
| `hotkey_capture_region` | str | `ctrl+shift+a` | Region capture hotkey |
| `hotkey_capture_window` | str | `ctrl+shift+w` | Window capture hotkey |
| `hotkey_capture_fullscreen` | str | `ctrl+shift+f` | Fullscreen capture hotkey |
| `post_capture_action` | str | `editor` | Post-capture behavior |
| `capture_save_directory` | str | `""` | Save folder override |

Theme selection UI: **View → Theme** in editor, tray submenu **Theme**.

Settings UI: **View → Settings** (editor) or tray **Settings**.

## Theming

`src/theme.py` defines color tokens for light and dark themes and builds a global Qt Style Sheet applied via `QApplication.setStyleSheet()`.

Dynamic widgets (palette swatches, color preview buttons) refresh through `EditorWindow.refresh_theme_styles()`.

Object names used in QSS:

| Object name | Usage |
|-------------|-------|
| `primaryButton` | Capture action buttons |
| `linkButton` | Open Editor link |
| `mutedLabel` | Toolbar group titles |
| `titleLabel` | Capture panel title |

## Global Hotkeys

Implemented in `src/global_hotkeys.py` using `pynput.keyboard.GlobalHotKeys`.

Hotkey strings are normalized to lowercase (e.g. `ctrl+shift+a`) and converted to pynput syntax (`<ctrl>+<shift>+a`).

Callbacks are forwarded to the Qt main thread through `HotkeyBridge` (`QObject` + `Signal`).

**Note:** Global hotkeys work reliably on X11. On Wayland, behavior depends on the compositor and may be restricted.

## Platform Support

| Feature | X11 | Wayland |
|---------|-----|---------|
| Fullscreen capture | Yes | Yes (Qt screen grab) |
| Region capture | Overlay | Overlay or grim+slurp |
| Window capture | xdotool/xwininfo | Not supported (info dialog) |
| Scroll capture | Yes | Yes |
| Global hotkeys | pynput | Limited |
| Color picker | Overlay | Overlay |

Optional system packages:

```bash
# Wayland region capture
sudo apt install grim slurp

# OCR
sudo apt install tesseract-ocr
```

## OCR

Flow:

1. User selects **OCR** tool and drags a region.
2. Canvas exports composited pixmap, crops to region.
3. `src/ocr.py` writes temp PNG and calls `tesseract` CLI.
4. Recognized text is copied to clipboard.

Requires `tesseract` on `PATH`.

## CLI Reference

| Command | Description |
|---------|-------------|
| `capture` | Headless capture (`--mode`, `--delay`, `--output`) |
| `pick-color` | Interactive color pick (`--clipboard`) |
| `export` | Render project to PNG/JPG/PDF |
| `open` | Launch GUI with project |

## Testing

Tests live in `tests/` and use Python's `unittest` runner:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Coverage includes config, storage, annotations, crop handles, canvas resize, editor history, theme, hotkeys, image effects, scroll stitching, and E2E editor flows.

## Packaging

| Script | Output |
|--------|--------|
| `packaging/build_deb.sh` | `dist/snappix_{version}_{arch}.deb` |
| `packaging/build_appimage.sh` | `dist/Snappix-{version}-x86_64.AppImage` |

## Dependencies

Python packages (`requirements.txt`):

| Package | Purpose |
|---------|---------|
| PySide6 | Qt 6 GUI |
| Pillow | Image processing (blur, scroll helpers) |
| requests | Clipboard image URL paste |
| pynput | Global hotkeys |

## Extension Points

| Goal | Suggested location |
|------|-------------------|
| New annotation type | `src/annotation_items.py`, `src/annotation_shapes.py`, `EditorCanvas` tool handler |
| New capture mode | `CaptureMode` + `execute_capture_request()` in `src/capture.py` |
| New export format | `EditorWindow.export_*` methods |
| New setting | `AppConfig` + `ConfigManager` + `SettingsDialog` |
| New theme token | `ThemeColors` + `build_application_stylesheet()` in `src/theme.py` |

## Known Limitations

- PDF export uses Qt's `QPdfWriter`; compatibility varies across PySide6 versions.
- Window capture requires X11 tooling.
- Scroll stitching assumes primarily vertical scrolling with visible overlap between frames.
- OCR quality depends on Tesseract language packs and screenshot clarity.
