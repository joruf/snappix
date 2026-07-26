# Snappix UI Overview

English labeled screenshots of the Capture and Editor windows. Regenerate with:

```bash
.venv/bin/python scripts/generate_readme_screenshots.py
```

## Capture Panel

![Capture Panel — UI Overview](screenshots/capture-panel-annotated.png)

| Label | What it does |
| --- | --- |
| App title | Identifies the Capture window |
| Capture delay | Seconds to wait before capture starts (Esc cancels during countdown) |
| Capture actions | Fullscreen, Area, Window, Scroll, and Video capture |
| Screen color picker | Sample a screen color into the clipboard |
| Open Editor | Open the image editor without capturing |

Hover any control in the live app for a short English tooltip.

## Image Editor

![Image Editor — UI Overview](screenshots/editor-window-annotated.png)

| Label | What it does |
| --- | --- |
| Menu bar | File, Edit, View, and Help commands |
| Editor tabs | One tab per open image or video project |
| Tool strip | Drawing and selection tools grouped by category |
| History | Undo / redo and jump to earlier states |
| Zoom controls | Zoom the canvas view |
| Property tabs | Style, Arrange, and Export panels for the selection |
| Workspace | Pasteboard around the document |
| Document / canvas | Editable screenshot and annotations |
| Status bar | Feedback plus selection details |

Hover toolbar buttons and property controls for English tooltips.

## Video Editor

![Video Editor — UI Overview](screenshots/video-editor-annotated.png)

| Label | What it does |
| --- | --- |
| Menu bar | File and Edit commands (save project, export MP4, import) |
| Editor tabs | One tab per open image or video project |
| Tool strip | Drawing tools for time-based video annotations |
| History | Undo / redo and jump to earlier states |
| Playback controls | Play, stop/rewind, and mute the preview |
| Show all objects | Show every annotation even outside the playhead range |
| Zoom controls | Zoom the video preview |
| Style property tab | Border, fill, and text colors for annotations |
| Video preview | Plays the recording; place and edit overlays here |
| Time ruler / playhead | Scrub current time along the recording |
| Annotation tracks | Timed bars for each overlay (start/end on the timeline) |
| Timeline | Full timeline row with tracks and playhead |
| Timeline pan ◀ / ▶ | Scroll the timeline one page left or right |
| Status bar | Feedback messages |

Hover toolbar and timeline controls for English tooltips.
