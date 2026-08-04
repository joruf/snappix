# Snappix — User Manual

Snappix captures screenshots and screen recordings, annotates them, and exports the
result. This manual walks through it in the order you actually meet it: capture first,
then annotate, then export.

For a labelled picture of every part of the interface, see
[UI_OVERVIEW.md](UI_OVERVIEW.md). For how the app is built, see
[TECHNICAL.md](TECHNICAL.md).

---

## 1. First run

On first launch Snappix asks where to keep its workspace folder (default `~/.snappix/`).
Unsaved tabs live there, so a crash or a reboot does not lose work.

Snappix then sits in the system tray. Click the tray icon to open the **Capture Panel**,
or use a global shortcut from section 2.

---

## 2. Capturing

Open the Capture Panel and pick a mode:

| Mode | What it does | Global shortcut |
| --- | --- | --- |
| Area | Drag a rectangle over any part of the screen | `Ctrl+Shift+A` |
| Window | Click a window to capture it | `Ctrl+Shift+W` |
| Fullscreen | The whole screen | `Ctrl+Shift+F` |
| Scroll | Captures a long page in pieces and stitches them | — |
| Video | Records the screen to MP4 | `Ctrl+Shift+V` |

While recording, `Ctrl+Shift+P` pauses and resumes, `Ctrl+Shift+R` stops.

`Esc` cancels an active region overlay.

**MeasureBox** is also on the Capture Panel: a resizable on-screen rectangle that reports
its own pixel size, for checking layout dimensions without taking a screenshot at all.

### What happens after a capture

Settings decide this: open the Image Editor (default), copy straight to the clipboard, or
save straight to a file.

---

## 3. The Image Editor

The captured image becomes a **document**, with annotations as separate objects on top.
Nothing is burned in until you export, so every annotation stays editable.

Tabs across the top hold several open images or video projects at once.

### 3.1 Drawing tools

The tool strip groups tools by purpose:

- **Select** — pick and move objects, select pixel regions, magic wand
- **Paint** — brush, eraser, fill, blur/pixelate for hiding sensitive content
- **Shapes** — rectangle, circle, triangle, star, polygon
- **Lines** — line, polyline, arrow, double arrow, bent arrow
- **Marks** — cross, checkmark, spotlight, numbered step
- **Text** — plain text and callout bubbles
- **Image** — crop, canvas size, import an image as a layer, OCR

Numbered **steps** auto-increment, so clicking four times gives you 1, 2, 3, 4.

**Spotlight** dims everything except one region — useful when a screenshot has one
relevant control in a busy window.

### 3.2 Editing what you drew

Select an object to reveal its handles. Drag to move, drag a handle to resize. Hold `Ctrl`
(or `Shift`) while dragging a handle to keep the object's proportions — hold it before you
grab the corner, and keep it held.

For **polyline, polygon, and bent arrow**, each vertex gets its own handle: drag a single
vertex to reshape the object without moving it as a whole. Hold `Shift` while dragging to
lock the vertex to one axis.

The **selection footer** under the canvas reports the selection's size and position in
whole pixels, and lists every vertex of a multi-point shape.

### Reusing part of an image

Mark a region with a selection tool and press `Ctrl+C`. The marked region alone goes to the
clipboard — not the whole tab — and `Ctrl+V` drops it back in as a movable layer.

Paste as often as you like: each `Ctrl+V` adds another copy, stepped down and to the right
so the copies do not hide each other. The cutout also pastes into any other tab, and into
other applications, because it is a plain image on the system clipboard.

`Ctrl+A` marks the whole drawing area, so `Ctrl+A` `Ctrl+C` `Ctrl+V` copies and pastes the
entire tab — the same three keys, whether you want a region or all of it.

### 3.3 Styling — the Edit tab

| Control | Effect |
| --- | --- |
| Border / Fill colors | Stroke and fill of the selection |
| Thickness | Stroke width |
| Style | Solid, dash, dot, dash-dot |
| Radius | Corner rounding for rectangles and triangles |
| Halo | A contrasting outline behind the annotation |

**Halo** solves a specific problem: a red arrow on a red error banner is invisible. The
halo puts a contrasting outline behind the annotation without changing its color — your
brand red stays exactly that red, it just gains an edge. The outline is white behind dark
annotations and black behind light ones.

It is off by default. The checkbox works two ways: with something selected it changes that
object, and with nothing selected it sets how the next annotation will be drawn. Switch it
on for anything you place over a busy or unpredictable background.

A note on **Radius**: rounding is capped by the shape's own size — a corner cannot round
further than half the shorter edge. On a small shape the slider therefore stops having an
effect well before its maximum. On triangles the sharpest corner limits it further, since
rounding a sharp point requires pulling the arc a long way back from the tip.

### 3.4 Arranging — the Arrange tab

Layer order, visibility and locking, exact X/Y/W/H entry, rotation, flip, skew, and
alignment. **Snap** and **Grid** help place objects consistently; **Distribute H/V** spaces
three or more selected objects evenly.

Lock an object you have finished with, so later edits cannot disturb it.

### 3.5 History

Undo and redo are labelled, and the history list lets you jump back to any earlier state
rather than stepping one action at a time.

---

## 4. Exporting

`Ctrl+Shift+E` exports. The **Export** tab controls how.

| Control | Effect |
| --- | --- |
| Preset | Quality preset |
| Scale | @1x, @2x, or @3x output resolution |
| Keep transparency | Off fills transparent pixels with white (JPEG needs this) |
| Presentation | Frames the export — see below |
| Batch | Export to several formats at once via a named profile |

Formats: PNG, JPEG, PDF, SVG. Use **@2x** for anything that will be viewed on a modern
display; @1x looks soft.

### 4.1 The presentation frame

`Presentation` places the finished screenshot on a larger canvas with padding, rounded
corners, a drop shadow, and a backdrop. It is what makes a screenshot look deliberate in a
document or on a slide, rather than a bare rectangle with hard edges.

`Presentation...` opens the settings with a live preview of the actual image you are about
to export:

- **Padding** — a percentage of the longer edge, so one setting looks right on a small
  crop and on a full-screen capture alike
- **Corners** — rounding of the screenshot itself
- **Shadow** — subtle by default, so it never competes with your annotations
- **Backdrop** — solid, a soft gradient, or transparent
- **Aspect** — Auto, or a fixed 16:9 / 4:3 / 3:2 / 1:1 frame

Aspect presets **letterbox**: the frame grows around the screenshot, so a preset can never
crop away part of your image.

The frame is applied last, to the finished image, so it applies to every export format.
JPEG cannot store transparency, so a transparent backdrop is filled with white for JPEG
rather than turning black.

---

## 5. The Video Editor

A video capture opens in the Video Editor. Annotations here are **timed**: each one has a
start and an end on the timeline.

- **Playback controls** play, stop, and mute the preview
- The **time ruler** scrubs; click anywhere to move the playhead
- Each annotation gets a **track bar** showing when it appears
- Right-click a bar to add **Fade, Zoom, or Slide** entry and exit effects; active effects
  are summarised in brackets on the bar
- **Show all objects** reveals every annotation regardless of the playhead, for editing
- `Del` removes the selected annotation; the previous one is selected afterwards

The drawing tools, the Edit tab, and the selection footer work as they do in the Image
Editor.

Export writes an MP4 with the annotations burned in permanently — unlike image export,
this is not reversible, so keep the project file if you may need to edit later.

---

## 6. Projects and recovery

Save a project (`Ctrl+S`) to keep annotations editable. Image projects use `.sfp`, video
projects `.sfpv` with the source video embedded.

Unsaved tabs are written to the workspace folder continuously. If Snappix is closed
unexpectedly, the tabs come back on the next launch.

---

## 7. Keyboard shortcuts

### In the editor

| Shortcut | Action |
| --- | --- |
| `Ctrl+N` | New canvas |
| `Ctrl+T` | New empty tab |
| `Ctrl+O` | Open project |
| `Ctrl+S` / `Ctrl+Shift+S` | Save / Save as |
| `Ctrl+Shift+E` | Export |
| `Ctrl+P` | Print |
| `Ctrl+W` | Close tab |
| `Ctrl+A` | Select the whole drawing area |
| `Ctrl+Z` | Undo |
| `Ctrl+Y` / `Ctrl+Shift+Z` | Redo |
| `Ctrl+D` | Duplicate selection |
| `Ctrl+C` / `Ctrl+V` | Copy / Paste |
| `Ctrl+Shift+C` / `Ctrl+Shift+V` | Copy / paste drawing area across tabs |
| `Ctrl++` / `Ctrl+-` / `Ctrl+0` | Zoom in / out / reset |
| `Ctrl+Shift++` / `Ctrl+Shift+-` | Grow / shrink selection |
| `Enter` | Apply crop |
| `Esc` | Cancel crop or overlay |
| `Del` | Delete selection |

### Global

| Shortcut | Action |
| --- | --- |
| `Ctrl+Shift+A` | Capture area |
| `Ctrl+Shift+W` | Capture window |
| `Ctrl+Shift+F` | Capture fullscreen |
| `Ctrl+Shift+V` | Start video capture |
| `Ctrl+Shift+P` | Pause / resume recording |
| `Ctrl+Shift+R` | Stop recording |

Every toolbar and property control has a tooltip — hover it if a control is unclear.

---

## 8. If something goes wrong

**A capture mode does nothing.** Not every mode works on every desktop. On Linux, Wayland
restricts what applications may capture, and some modes need helper tools installed.
Windows does not support video capture or OCR at all. Settings shows what is available on
your system.

**Global shortcuts do not fire.** Another application may have claimed the same
combination; change it in Settings.

**A restored tab reports it could not be loaded.** The recovery file is unreadable or the
disk is full. A full disk is the common cause — Snappix needs room to unpack an embedded
video before it can show it.

**Exports look soft.** Set Scale to @2x.

**Snappix crashed.** Unsaved tabs are recovered on the next launch, and the crash is
recorded in `~/.cache/snappix/crash.log`. Attach that file to a bug report: it holds the
exact Python frames, any Qt warning that preceded the crash, and a short trail of what you
did just before it — which action, on which kind of object.

---

## 9. Updating

`Help -> Check for Updates...` in the editor, or `Check for Updates...` in the tray menu —
the tray entry works with no editor tab open.

Snappix compares the commit it runs from against the head of the repository's main branch.
When it is behind, it offers to install and restart.

Running from a git checkout, the update is a `git pull --ff-only` and is **refused if you
have local changes** — it never discards your work. Otherwise the branch archive is
unpacked over the installation; the workspace folder, configuration, and saved projects
live elsewhere and are untouched.
