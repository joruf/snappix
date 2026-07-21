"""
Automatic window scroll capture for X11 sessions.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from shutil import which
from typing import Callable, Protocol

from PySide6.QtCore import QRect
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication

from src.platform import get_x11_focused_window_id, restore_x11_window_focus
from src.scroll_capture import (
    dedupe_scroll_frames,
    estimate_scroll_progress_rows,
    frame_has_meaningful_new_content,
    is_scroll_position_unchanged,
    stitch_vertical_pixmaps,
)

MAX_SCROLL_FRAMES = 40
SCROLL_SETTLE_SECONDS = 0.28
SCROLL_TOP_SETTLE_SECONDS = 0.45
MIN_CAPTURED_FRAMES = 1
SCROLLBAR_BOTTOM_MARGIN_PX = 8
SCROLLBAR_TOP_MARGIN_PX = 8
_CONTENT_FOCUS_Y_RATIO = 0.55
_SCROLL_TO_TOP_PAGE_UP_COUNT = 10


@dataclass(slots=True)
class ScrollbarInfo:
    """
    Describes one detected vertical scrollbar inside a window capture.

    Attributes:
        track_rect: Scrollbar track bounds relative to the window pixmap.
        thumb_rect: Optional thumb bounds relative to the window pixmap.
    """

    track_rect: QRect
    thumb_rect: QRect | None = None


@dataclass(slots=True)
class AutoScrollCaptureResult:
    """
    Contains the result of one automatic scroll capture run.

    Attributes:
        pixmap: Stitched screenshot pixmap.
        frame_count: Number of captured frames used for stitching.
        window_width: Captured window width in pixels.
        window_height: Captured window height in pixels.
        cancelled: True when capture was cancelled by the user.
        message: Human-readable status or failure reason.
    """

    pixmap: QPixmap
    frame_count: int = 0
    window_width: int = 0
    window_height: int = 0
    cancelled: bool = False
    message: str = ""

    @property
    def succeeded(self) -> bool:
        """
        Indicates whether stitching produced a usable screenshot.

        Returns:
            bool: True when a non-empty pixmap was created.
        """

        return not self.pixmap.isNull() and not self.cancelled


class DesktopSnapshotLike(Protocol):
    """
    Protocol for desktop snapshot objects used during auto scroll capture.
    """

    pixmap: QPixmap
    virtual_geometry: QRect


def detect_vertical_scrollbar(window_pixmap: QPixmap) -> ScrollbarInfo | None:
    """
    Detects a vertical scrollbar on the right edge of one window capture.

    Args:
        window_pixmap: Cropped window screenshot.

    Returns:
        ScrollbarInfo | None: Detected scrollbar metadata or None.
    """

    width = window_pixmap.width()
    height = window_pixmap.height()
    if width < 60 or height < 100:
        return None

    strip_width = min(18, max(10, width // 28))
    x_start = width - strip_width
    image = window_pixmap.toImage().convertToFormat(QImage.Format.Format_Grayscale8)
    if image.isNull():
        return None

    edge_score = _strip_vertical_uniformity(image, x_start, width)
    inner_start = max(0, x_start - strip_width - 8)
    inner_end = max(inner_start + 1, x_start - 2)
    inner_score = _strip_vertical_uniformity(image, inner_start, inner_end)

    row_values: list[float] = []
    for row_index in range(height):
        total = 0.0
        for column_index in range(x_start, width):
            total += float(image.pixelColor(column_index, row_index).red())
        row_values.append(total / strip_width)

    inner_values: list[float] = []
    for row_index in range(height):
        total = 0.0
        count = 0
        for column_index in range(inner_start, inner_end):
            total += float(image.pixelColor(column_index, row_index).red())
            count += 1
        if count:
            inner_values.append(total / count)
    edge_mean = sum(row_values) / len(row_values) if row_values else 0.0
    inner_mean = sum(inner_values) / len(inner_values) if inner_values else edge_mean

    value_range = max(row_values) - min(row_values)
    track_rect = QRect(x_start, 0, strip_width, height)
    if value_range < 6 and abs(edge_mean - inner_mean) < 8:
        return None
    if inner_score > 3 and edge_score >= inner_score * 0.92 and value_range < 6:
        return None
    if value_range < 6:
        return ScrollbarInfo(track_rect=track_rect, thumb_rect=None)

    median_value = sorted(row_values)[height // 2]
    threshold = max(5.0, value_range * 0.18)
    thumb_top: int | None = None
    thumb_bottom: int | None = None
    for row_index, value in enumerate(row_values):
        if abs(value - median_value) < threshold:
            continue
        if thumb_top is None:
            thumb_top = row_index
        thumb_bottom = row_index

    thumb_rect = None
    if thumb_top is not None and thumb_bottom is not None:
        thumb_height = thumb_bottom - thumb_top + 1
        if max(20, int(height * 0.04)) <= thumb_height <= int(height * 0.92):
            thumb_rect = QRect(x_start, thumb_top, strip_width, thumb_height)
    return ScrollbarInfo(track_rect=track_rect, thumb_rect=thumb_rect)


def frames_show_same_content(previous: QPixmap, current: QPixmap) -> bool:
    """
    Indicates whether two consecutive scroll frames show the same content.

    Args:
        previous: Previous captured frame.
        current: Current captured frame.

    Returns:
        bool: True when no further scrolling progress is visible.
    """

    return not frame_has_meaningful_new_content(previous, current)


def _scrollbar_thumb_position(scrollbar: ScrollbarInfo | None) -> tuple[int, int] | None:
    """
    Returns the detected scrollbar thumb position and height.

    Args:
        scrollbar: Detected scrollbar metadata.

    Returns:
        tuple[int, int] | None: ``(thumb_top, thumb_height)`` or None.
    """

    if scrollbar is None or scrollbar.thumb_rect is None:
        return None
    return (scrollbar.thumb_rect.y(), scrollbar.thumb_rect.height())


def _is_scrollbar_reliable(scrollbar: ScrollbarInfo | None) -> bool:
    """
    Indicates whether detected scrollbar geometry looks trustworthy.

    Args:
        scrollbar: Detected scrollbar metadata.

    Returns:
        bool: True when thumb size and track look like a real scrollbar.
    """

    if scrollbar is None or scrollbar.thumb_rect is None:
        return False
    track_height = max(1, scrollbar.track_rect.height())
    thumb_height = scrollbar.thumb_rect.height()
    thumb_ratio = thumb_height / track_height
    return 0.04 <= thumb_ratio <= 0.72


def _is_scrollbar_at_bottom(scrollbar: ScrollbarInfo | None) -> bool:
    """
    Indicates whether the detected scrollbar thumb reached the track bottom.

    Args:
        scrollbar: Detected scrollbar metadata.

    Returns:
        bool: True when the thumb sits at the bottom of its track.
    """

    if not _is_scrollbar_reliable(scrollbar):
        return False
    assert scrollbar is not None
    assert scrollbar.thumb_rect is not None
    track_top = scrollbar.track_rect.y()
    track_height = scrollbar.track_rect.height()
    thumb_top = scrollbar.thumb_rect.y()
    thumb_bottom = scrollbar.thumb_rect.y() + scrollbar.thumb_rect.height()
    track_bottom = track_top + track_height
    thumb_offset = thumb_top - track_top
    if thumb_offset < max(SCROLLBAR_TOP_MARGIN_PX, int(track_height * 0.08)):
        return False
    return thumb_bottom >= track_bottom - SCROLLBAR_BOTTOM_MARGIN_PX


def _is_scrollbar_at_top(scrollbar: ScrollbarInfo | None) -> bool:
    """
    Indicates whether the detected scrollbar thumb sits at the track top.

    Args:
        scrollbar: Detected scrollbar metadata.

    Returns:
        bool: True when the thumb is at the top of its track.
    """

    if not _is_scrollbar_reliable(scrollbar):
        return False
    assert scrollbar is not None
    assert scrollbar.thumb_rect is not None
    track_top = scrollbar.track_rect.y()
    return scrollbar.thumb_rect.y() <= track_top + SCROLLBAR_TOP_MARGIN_PX


def _estimate_overlap_from_scrollbars(
    previous_scrollbar: ScrollbarInfo | None,
    current_scrollbar: ScrollbarInfo | None,
    frame_height: int,
) -> int | None:
    """
    Estimates stitch overlap from consecutive scrollbar thumb positions.

    Args:
        previous_scrollbar: Scrollbar metadata from the previous frame.
        current_scrollbar: Scrollbar metadata from the current frame.
        frame_height: Frame height in pixels.

    Returns:
        int | None: Estimated overlap row count or None when unreliable.
    """

    if frame_height <= 1:
        return None
    if not _is_scrollbar_reliable(previous_scrollbar) or not _is_scrollbar_reliable(current_scrollbar):
        return None

    assert previous_scrollbar is not None
    assert current_scrollbar is not None
    assert previous_scrollbar.thumb_rect is not None
    assert current_scrollbar.thumb_rect is not None

    thumb_delta = current_scrollbar.thumb_rect.y() - previous_scrollbar.thumb_rect.y()
    if thumb_delta <= 0:
        return None

    track_height = max(1, previous_scrollbar.track_rect.height())
    thumb_height = max(
        previous_scrollbar.thumb_rect.height(),
        current_scrollbar.thumb_rect.height(),
    )
    track_travel = max(1, track_height - thumb_height)
    scrollable_rows = frame_height * (track_height / max(1, thumb_height) - 1.0)
    if scrollable_rows <= 0:
        return None

    new_content_rows = round(thumb_delta * scrollable_rows / track_travel)
    new_content_rows = max(1, min(new_content_rows, frame_height - 1))
    return frame_height - new_content_rows


def _build_scroll_overlap_hints(frames: list[QPixmap]) -> list[int | None]:
    """
    Builds optional overlap hints from scrollbar movement between consecutive frames.

    Args:
        frames: Capture frames from top to bottom.

    Returns:
        list[int | None]: Overlap hints for each consecutive frame pair.
    """

    if len(frames) < 2:
        return []

    scrollbars = [detect_vertical_scrollbar(frame) for frame in frames]
    hints: list[int | None] = []
    for frame_index in range(1, len(frames)):
        hints.append(
            _estimate_overlap_from_scrollbars(
                scrollbars[frame_index - 1],
                scrollbars[frame_index],
                frames[frame_index].height(),
            )
        )
    return hints


def _should_stop_without_scrollbar(
    previous_frame: QPixmap,
    current_frame: QPixmap,
    stationary_confirmations: int,
) -> tuple[bool, int]:
    """
    Fallback stop logic when no reliable scrollbar is visible.

    Args:
        previous_frame: Previous captured frame.
        current_frame: Current captured frame.
        stationary_confirmations: Number of consecutive unchanged captures so far.

    Returns:
        tuple[bool, int]: ``(should_stop, updated_confirmations)``.
    """

    if not frame_has_meaningful_new_content(previous_frame, current_frame):
        return True, stationary_confirmations

    if is_scroll_position_unchanged(previous_frame, current_frame):
        stationary_confirmations += 1
        if stationary_confirmations >= 2:
            return True, stationary_confirmations
        return False, stationary_confirmations

    progress_rows = estimate_scroll_progress_rows(previous_frame, current_frame)
    if progress_rows <= 3:
        stationary_confirmations += 1
        if stationary_confirmations >= 2:
            return True, stationary_confirmations
        return False, stationary_confirmations

    return False, 0


def perform_auto_scroll_capture(
    window_id: str,
    window_rect: QRect,
    capture_snapshot: Callable[[], DesktopSnapshotLike],
    is_cancelled: Callable[[], bool] | None = None,
    progress_callback: Callable[[str, int, int], None] | None = None,
    restore_focus_window_id: str = "",
) -> AutoScrollCaptureResult:
    """
    Scrolls one X11 window from top to bottom and stitches captured frames.

    Args:
        window_id: Target X11 window id.
        window_rect: Window bounds in global desktop coordinates.
        capture_snapshot: Callable returning one fresh desktop snapshot.
        is_cancelled: Optional callback that returns True when capture should stop.
        progress_callback: Optional callback for ``(message, current_step, max_steps)``.
        restore_focus_window_id: Optional previously focused window to restore afterward.

    Returns:
        AutoScrollCaptureResult: Capture result with stitched pixmap and metadata.
    """

    empty = QPixmap()
    window_width = window_rect.width()
    window_height = window_rect.height()
    previous_focus = restore_focus_window_id.strip() or get_x11_focused_window_id()

    if which("xdotool") is None or not window_id or window_rect.isNull():
        return AutoScrollCaptureResult(
            pixmap=empty,
            window_width=window_width,
            window_height=window_height,
            message="Scroll capture requires a valid X11 window.",
        )

    cancelled = is_cancelled or (lambda: False)

    def report(message: str, step: int = 0, max_steps: int = MAX_SCROLL_FRAMES) -> None:
        if progress_callback is not None:
            progress_callback(message, step, max_steps)
        QApplication.processEvents()

    try:
        report("Scrolling to top...", 0, MAX_SCROLL_FRAMES)
        if cancelled():
            return AutoScrollCaptureResult(
                pixmap=empty,
                window_width=window_width,
                window_height=window_height,
                cancelled=True,
                message="Scroll capture cancelled.",
            )

        _focus_window_content(window_id, window_rect)
        _scroll_window_to_top(window_id, window_rect)
        QApplication.processEvents()
        if cancelled():
            return AutoScrollCaptureResult(
                pixmap=empty,
                window_width=window_width,
                window_height=window_height,
                cancelled=True,
                message="Scroll capture cancelled.",
            )

        _pulse_scrollbar_visible(window_id)

        frames: list[QPixmap] = []
        previous_frame = QPixmap()
        scrollbar_mode = False
        stationary_confirmations = 0
        for frame_index in range(MAX_SCROLL_FRAMES):
            report(
                f"Capturing frame {frame_index + 1}...",
                frame_index + 1,
                MAX_SCROLL_FRAMES,
            )
            if cancelled():
                return AutoScrollCaptureResult(
                    pixmap=empty,
                    frame_count=len(frames),
                    window_width=window_width,
                    window_height=window_height,
                    cancelled=True,
                    message="Scroll capture cancelled.",
                )

            snapshot = capture_snapshot()
            QApplication.processEvents()
            frame = _crop_window_from_snapshot(snapshot, window_rect)
            if frame.isNull():
                break

            current_scrollbar = detect_vertical_scrollbar(frame)
            if _is_scrollbar_reliable(current_scrollbar):
                scrollbar_mode = True

            if scrollbar_mode and _is_scrollbar_at_bottom(current_scrollbar):
                if (
                    not previous_frame.isNull()
                    and is_scroll_position_unchanged(previous_frame, frame)
                ):
                    break
                frames.append(frame)
                break

            if scrollbar_mode:
                frames.append(frame)
                previous_frame = frame
            elif len(frames) >= MIN_CAPTURED_FRAMES and not previous_frame.isNull():
                should_stop, stationary_confirmations = _should_stop_without_scrollbar(
                    previous_frame,
                    frame,
                    stationary_confirmations,
                )
                if should_stop:
                    break
                frames.append(frame)
                previous_frame = frame
            else:
                frames.append(frame)
                previous_frame = frame

            if frame_index + 1 >= MAX_SCROLL_FRAMES:
                break

            report(
                f"Scrolling down ({frame_index + 1}/{MAX_SCROLL_FRAMES})...",
                frame_index + 1,
                MAX_SCROLL_FRAMES,
            )
            _scroll_window_down(window_id, window_rect)
            QApplication.processEvents()
            if cancelled():
                return AutoScrollCaptureResult(
                    pixmap=empty,
                    frame_count=len(frames),
                    window_width=window_width,
                    window_height=window_height,
                    cancelled=True,
                    message="Scroll capture cancelled.",
                )

        if not frames:
            return AutoScrollCaptureResult(
                pixmap=empty,
                window_width=window_width,
                window_height=window_height,
                message="No scroll frames could be captured from the selected window.",
            )

        merged_frames = dedupe_scroll_frames(frames)
        overlap_hints = _build_scroll_overlap_hints(merged_frames)
        stitched = stitch_vertical_pixmaps(merged_frames, overlap_hints=overlap_hints)
        if stitched.isNull():
            return AutoScrollCaptureResult(
                pixmap=empty,
                frame_count=len(merged_frames),
                window_width=window_width,
                window_height=window_height,
                message="Scroll frames could not be merged into one image.",
            )

        return AutoScrollCaptureResult(
            pixmap=stitched,
            frame_count=len(merged_frames),
            window_width=window_width,
            window_height=window_height,
            message=(
                f"Merged {len(merged_frames)} frame(s) into "
                f"{stitched.width()}×{stitched.height()} px."
            ),
        )
    finally:
        if previous_focus and previous_focus != window_id:
            restore_x11_window_focus(previous_focus)


def _strip_vertical_uniformity(image: QImage, x_start: int, x_end: int) -> float:
    """
    Computes how uniform one vertical image strip is across rows.

    Args:
        image: Source grayscale image.
        x_start: Strip start column.
        x_end: Strip end column exclusive.

    Returns:
        float: Uniformity score where lower values mean more scrollbar-like strips.
    """

    if x_end <= x_start:
        return 999.0

    height = image.height()
    row_means: list[float] = []
    for row_index in range(height):
        total = 0.0
        for column_index in range(x_start, x_end):
            total += float(image.pixelColor(column_index, row_index).red())
        row_means.append(total / (x_end - x_start))
    if not row_means:
        return 999.0
    mean_value = sum(row_means) / len(row_means)
    return sum(abs(value - mean_value) for value in row_means) / len(row_means)


def _crop_window_from_snapshot(snapshot: DesktopSnapshotLike, window_rect: QRect) -> QPixmap:
    """
    Crops one window rectangle from a desktop snapshot.

    Args:
        snapshot: Desktop snapshot.
        window_rect: Window bounds in global coordinates.

    Returns:
        QPixmap: Cropped window image or null pixmap.
    """

    local_rect = window_rect.translated(
        -snapshot.virtual_geometry.x(),
        -snapshot.virtual_geometry.y(),
    ).intersected(snapshot.pixmap.rect())
    if local_rect.width() <= 1 or local_rect.height() <= 1:
        return QPixmap()
    return snapshot.pixmap.copy(local_rect)


def _focus_window_content(window_id: str, window_rect: QRect) -> None:
    """
    Focuses the scrollable content area inside one window.

    Args:
        window_id: Target X11 window id.
        window_rect: Window bounds in global desktop coordinates.

    Returns:
        None
    """

    if window_rect.width() <= 0 or window_rect.height() <= 0:
        return
    click_x = max(1, window_rect.width() // 2)
    click_y = max(96, int(window_rect.height() * _CONTENT_FOCUS_Y_RATIO))
    _xdotool("mousemove", "--window", window_id, str(click_x), str(click_y))
    _xdotool("click", "--window", window_id, "1")
    time.sleep(0.12)


def _scroll_window_to_top(window_id: str, window_rect: QRect) -> None:
    """
    Moves one window scroll position to the top without stealing global focus.

    Args:
        window_id: Target X11 window id.
        window_rect: Window bounds in global desktop coordinates.

    Returns:
        None
    """

    _focus_window_content(window_id, window_rect)
    for _ in range(3):
        _xdotool("key", "--window", window_id, "ctrl+Home")
        _xdotool("key", "--window", window_id, "Home")
    for _ in range(_SCROLL_TO_TOP_PAGE_UP_COUNT):
        _xdotool("key", "--window", window_id, "Page_Up")
    time.sleep(SCROLL_TOP_SETTLE_SECONDS)


def _scroll_window_down(window_id: str, window_rect: QRect) -> None:
    """
    Scrolls one window down by roughly one viewport step without mouse input.

    Args:
        window_id: Target X11 window id.
        window_rect: Window bounds in global desktop coordinates.

    Returns:
        None
    """

    _xdotool("key", "--window", window_id, "Page_Down")
    time.sleep(SCROLL_SETTLE_SECONDS)


def _pulse_scrollbar_visible(window_id: str) -> None:
    """
    Briefly scrolls one window so overlay scrollbars become visible in captures.

    Args:
        window_id: Target X11 window id.

    Returns:
        None
    """

    _xdotool("key", "--window", window_id, "Down")
    time.sleep(0.06)
    _xdotool("key", "--window", window_id, "Up")
    time.sleep(0.1)


def _xdotool(*args: str) -> bool:
    """
    Executes one xdotool command.

    Args:
        *args: xdotool arguments.

    Returns:
        bool: True when command succeeded.
    """

    if which("xdotool") is None:
        return False
    try:
        subprocess.run(
            ["xdotool", *args],
            check=True,
            timeout=2.0,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False
