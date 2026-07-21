"""
Vertical scroll capture stitching helpers.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap

_OVERLAP_SAMPLE_STEP = 2
_SCROLLBAR_EXCLUDE_WIDTH = 22
_MAX_OVERLAP_SCORE = 18.0
_STOP_NEW_CONTENT_ROWS = 3
_STATIONARY_OVERLAP_RATIO = 0.92
_STATIONARY_MAX_NEW_ROWS = 8
_LENIENT_MIN_OVERLAP_RATIO = 0.40
_STATIONARY_PIXEL_DIFF_RATIO = 0.012
_CONTENT_TOP_SKIP_RATIO = 0.14
_CONTENT_BOTTOM_SKIP_RATIO = 0.02
_MIN_CONTENT_TOP_SKIP_PX = 80


@dataclass(slots=True)
class VerticalOverlapMatch:
    """
    Describes overlap between two vertically adjacent capture frames.

    Attributes:
        overlap_rows: Estimated shared row count.
        difference_score: Average row-difference score for the matched overlap.
        new_content_rows: Estimated newly visible rows in the lower frame.
    """

    overlap_rows: int
    difference_score: float
    new_content_rows: int


def _content_column_range(width: int) -> tuple[int, int, int]:
    """
    Returns sampled column bounds excluding a typical right-side scrollbar.

    Args:
        width: Frame width in pixels.

    Returns:
        tuple[int, int, int]: Start column, end column exclusive, sample step.
    """

    content_width = max(24, width - _SCROLLBAR_EXCLUDE_WIDTH)
    step = 1 if content_width <= 240 else _OVERLAP_SAMPLE_STEP
    return 0, content_width, step


def _content_row_bounds(height: int) -> tuple[int, int]:
    """
    Returns row bounds that skip browser chrome and edge artifacts.

    Args:
        height: Frame height in pixels.

    Returns:
        tuple[int, int]: Start row inclusive and end row exclusive.
    """

    if height <= 0:
        return 0, 0
    if height < 200:
        row_start = max(0, int(height * 0.08))
        row_end = max(row_start + 1, height - max(2, int(height * 0.04)))
        return row_start, row_end
    top_skip = max(_MIN_CONTENT_TOP_SKIP_PX, int(height * _CONTENT_TOP_SKIP_RATIO))
    bottom_skip = max(8, int(height * _CONTENT_BOTTOM_SKIP_RATIO))
    row_start = min(height - 1, top_skip)
    row_end = max(row_start + 1, height - bottom_skip)
    return row_start, row_end


def _pixmap_to_gray_rows(
    pixmap: QPixmap,
    *,
    row_start: int = 0,
    row_end: int | None = None,
) -> list[list[int]]:
    """
    Converts one pixmap region into grayscale row brightness values.

    Args:
        pixmap: Source pixmap.
        row_start: First row to include.
        row_end: Last row exclusive; uses full height when omitted.

    Returns:
        list[list[int]]: Row-wise grayscale values.
    """

    image = pixmap.toImage().convertToFormat(QImage.Format.Format_Grayscale8)
    width = image.width()
    height = image.height()
    if width <= 0 or height <= 0:
        return []

    x_start, x_end, step = _content_column_range(width)
    start_row = max(0, row_start)
    end_row = height if row_end is None else min(height, row_end)
    rows: list[list[int]] = []
    for row_index in range(start_row, end_row):
        row_values = [
            image.pixelColor(column_index, row_index).red()
            for column_index in range(x_start, x_end, step)
        ]
        rows.append(row_values)
    return rows


def _average_frame_difference(
    previous_frame: QPixmap,
    current_frame: QPixmap,
    *,
    content_region_only: bool = False,
) -> float:
    """
    Estimates the average per-channel pixel difference between two frames.

    Args:
        previous_frame: Previous captured frame.
        current_frame: Current captured frame.
        content_region_only: When True, ignores browser chrome at the top.

    Returns:
        float: Normalized difference in the range ``0.0`` to ``1.0``.
    """

    previous_image = previous_frame.toImage().convertToFormat(QImage.Format.Format_Grayscale8)
    current_image = current_frame.toImage().convertToFormat(QImage.Format.Format_Grayscale8)
    width = min(previous_image.width(), current_image.width())
    height = min(previous_image.height(), current_image.height())
    if width <= 0 or height <= 0:
        return 1.0

    row_start = 0
    row_end = height
    if content_region_only:
        row_start, row_end = _content_row_bounds(height)
        if row_end <= row_start:
            row_start, row_end = 0, height

    x_start, x_end, x_step = _content_column_range(width)
    sample_step = max(1, min(width, row_end - row_start) // 120)
    total = 0.0
    count = 0
    for row_index in range(row_start, row_end, sample_step):
        for column_index in range(x_start, x_end, x_step):
            total += abs(
                previous_image.pixelColor(column_index, row_index).red()
                - current_image.pixelColor(column_index, row_index).red()
            )
            count += 1
    if count == 0:
        return 1.0
    return total / (count * 255.0)


def _row_difference(left_row: list[int], right_row: list[int]) -> float:
    """
    Computes the average absolute difference between two rows.

    Args:
        left_row: First row values.
        right_row: Second row values.

    Returns:
        float: Average difference.
    """

    if not left_row or not right_row or len(left_row) != len(right_row):
        return float("inf")
    total = sum(abs(left - right) for left, right in zip(left_row, right_row, strict=True))
    return total / len(left_row)


def _rows_block_difference(top_block: list[list[int]], bottom_block: list[list[int]]) -> float:
    """
    Computes the average row difference between two row blocks.

    Args:
        top_block: Upper row block.
        bottom_block: Lower row block.

    Returns:
        float: Average difference score.
    """

    if not top_block or not bottom_block or len(top_block) != len(bottom_block):
        return float("inf")
    total = 0.0
    for top_row, bottom_row in zip(top_block, bottom_block, strict=True):
        total += _row_difference(top_row, bottom_row)
    return total / len(top_block)


def find_vertical_overlap_from_rows(top_rows: list[list[int]], bottom_rows: list[list[int]]) -> int:
    """
    Estimates overlapping row count from precomputed grayscale row data.

    Args:
        top_rows: Upper frame rows.
        bottom_rows: Lower frame rows.

    Returns:
        int: Estimated overlapping row count.
    """

    return measure_vertical_overlap_from_rows(top_rows, bottom_rows).overlap_rows


def measure_vertical_overlap_from_rows(
    top_rows: list[list[int]],
    bottom_rows: list[list[int]],
) -> VerticalOverlapMatch:
    """
    Estimates overlap metrics from precomputed grayscale row data.

    Args:
        top_rows: Upper frame rows.
        bottom_rows: Lower frame rows.

    Returns:
        VerticalOverlapMatch: Overlap estimation with confidence score.
    """

    if not top_rows or not bottom_rows:
        return VerticalOverlapMatch(0, float("inf"), 0)

    frame_height = len(bottom_rows)
    max_overlap = min(len(top_rows), frame_height, max(240, int(frame_height * 0.96)))
    min_overlap = 8
    best_overlap = min_overlap
    best_score = float("inf")

    coarse_step = max(1, max_overlap // 100)
    for overlap in range(min_overlap, max_overlap + 1, coarse_step):
        score = _rows_block_difference(top_rows[-overlap:], bottom_rows[:overlap])
        if score < best_score or (score == best_score and overlap > best_overlap):
            best_score = score
            best_overlap = overlap

    refine_start = max(min_overlap, best_overlap - max(8, coarse_step * 2))
    refine_end = min(max_overlap, best_overlap + max(8, coarse_step * 2))
    for overlap in range(refine_start, refine_end + 1):
        score = _rows_block_difference(top_rows[-overlap:], bottom_rows[:overlap])
        if score < best_score or (score == best_score and overlap > best_overlap):
            best_score = score
            best_overlap = overlap

    if best_score > _MAX_OVERLAP_SCORE:
        return VerticalOverlapMatch(0, best_score, frame_height)

    max_reasonable_overlap = max(8, int(frame_height * 0.96))
    if best_overlap > max_reasonable_overlap and best_score > 8.0:
        return VerticalOverlapMatch(0, best_score, frame_height)

    return VerticalOverlapMatch(
        best_overlap,
        best_score,
        max(0, frame_height - best_overlap),
    )


def measure_vertical_overlap_lenient(top_pixmap: QPixmap, bottom_pixmap: QPixmap) -> VerticalOverlapMatch:
    """
    Estimates overlap metrics while keeping the best match even for noisy web content.

    Args:
        top_pixmap: Upper screenshot segment.
        bottom_pixmap: Lower screenshot segment.

    Returns:
        VerticalOverlapMatch: Best-effort overlap estimation for scroll-end detection.
    """

    top_rows = _pixmap_to_gray_rows(top_pixmap)
    bottom_rows = _pixmap_to_gray_rows(bottom_pixmap)
    if not top_rows or not bottom_rows:
        return VerticalOverlapMatch(0, float("inf"), 0)

    frame_height = len(bottom_rows)
    max_overlap = min(len(top_rows), frame_height, max(240, int(frame_height * 0.96)))
    min_overlap = 8
    best_overlap = min_overlap
    best_score = float("inf")

    coarse_step = max(1, max_overlap // 100)
    for overlap in range(min_overlap, max_overlap + 1, coarse_step):
        score = _rows_block_difference(top_rows[-overlap:], bottom_rows[:overlap])
        if score < best_score or (score == best_score and overlap > best_overlap):
            best_score = score
            best_overlap = overlap

    refine_start = max(min_overlap, best_overlap - max(8, coarse_step * 2))
    refine_end = min(max_overlap, best_overlap + max(8, coarse_step * 2))
    for overlap in range(refine_start, refine_end + 1):
        score = _rows_block_difference(top_rows[-overlap:], bottom_rows[:overlap])
        if score < best_score or (score == best_score and overlap > best_overlap):
            best_score = score
            best_overlap = overlap

    min_useful_overlap = max(8, int(frame_height * _LENIENT_MIN_OVERLAP_RATIO))
    if best_overlap >= min_useful_overlap:
        return VerticalOverlapMatch(
            best_overlap,
            best_score,
            max(0, frame_height - best_overlap),
        )

    if best_score > _MAX_OVERLAP_SCORE:
        return VerticalOverlapMatch(0, best_score, frame_height)

    return VerticalOverlapMatch(
        best_overlap,
        best_score,
        max(0, frame_height - best_overlap),
    )


def measure_vertical_overlap(top_pixmap: QPixmap, bottom_pixmap: QPixmap) -> VerticalOverlapMatch:
    """
    Estimates overlap metrics between two vertically stacked captures.

    Args:
        top_pixmap: Upper screenshot segment.
        bottom_pixmap: Lower screenshot segment.

    Returns:
        VerticalOverlapMatch: Overlap estimation with confidence score.
    """

    return measure_vertical_overlap_from_rows(
        _pixmap_to_gray_rows(top_pixmap),
        _pixmap_to_gray_rows(bottom_pixmap),
    )


def find_vertical_overlap_rows(top_pixmap: QPixmap, bottom_pixmap: QPixmap) -> int:
    """
    Estimates overlapping row count between two vertically stacked captures.

    Args:
        top_pixmap: Upper screenshot segment.
        bottom_pixmap: Lower screenshot segment.

    Returns:
        int: Estimated overlapping row count.
    """

    return measure_vertical_overlap(top_pixmap, bottom_pixmap).overlap_rows


def estimate_scroll_progress_rows(previous_frame: QPixmap, current_frame: QPixmap) -> int:
    """
    Estimates how many new rows became visible between two consecutive captures.

    Args:
        previous_frame: Previous captured frame.
        current_frame: Current captured frame.

    Returns:
        int: Estimated newly scrolled row count.
    """

    if previous_frame.isNull() or current_frame.isNull():
        return current_frame.height()
    if previous_frame.size() != current_frame.size():
        return current_frame.height()
    if previous_frame.toImage() == current_frame.toImage():
        return 0

    row_start, row_end = _content_row_bounds(current_frame.height())
    top_rows = _pixmap_to_gray_rows(previous_frame, row_start=row_start, row_end=row_end)
    bottom_rows = _pixmap_to_gray_rows(current_frame, row_start=row_start, row_end=row_end)
    match = measure_vertical_overlap_from_rows(top_rows, bottom_rows)
    if match.overlap_rows == 0 and match.new_content_rows >= len(bottom_rows):
        lenient_match = measure_vertical_overlap_lenient(previous_frame, current_frame)
        content_height = max(1, row_end - row_start)
        return lenient_match.new_content_rows if lenient_match.overlap_rows > 0 else content_height
    return match.new_content_rows


def _resolve_overlap_match(previous_frame: QPixmap, current_frame: QPixmap) -> VerticalOverlapMatch:
    """
    Resolves overlap metrics, falling back to lenient matching for noisy frames.

    Args:
        previous_frame: Previous captured frame.
        current_frame: Current captured frame.

    Returns:
        VerticalOverlapMatch: Best overlap estimation for progress decisions.
    """

    match = measure_vertical_overlap(previous_frame, current_frame)
    frame_height = max(current_frame.height(), 1)
    if match.overlap_rows == 0 and match.new_content_rows >= int(frame_height * 0.75):
        lenient_match = measure_vertical_overlap_lenient(previous_frame, current_frame)
        if lenient_match.overlap_rows > 0:
            return lenient_match
    return match


def frame_has_meaningful_new_content(
    previous_frame: QPixmap,
    current_frame: QPixmap,
) -> bool:
    """
    Indicates whether the lower frame adds enough new content to keep scrolling.

    Args:
        previous_frame: Previous captured frame.
        current_frame: Current captured frame.

    Returns:
        bool: True when the lower frame should still be captured.
    """

    if previous_frame.isNull() or current_frame.isNull():
        return True
    if previous_frame.size() != current_frame.size():
        return True
    if previous_frame.toImage() == current_frame.toImage():
        return False

    match = _resolve_overlap_match(previous_frame, current_frame)
    return match.new_content_rows > _STOP_NEW_CONTENT_ROWS


def is_scroll_position_unchanged(
    previous_frame: QPixmap,
    current_frame: QPixmap,
) -> bool:
    """
    Indicates whether two consecutive captures show the same scroll position.

    Uses tolerant overlap matching so animated/noisy web pages still stop at the bottom.

    Args:
        previous_frame: Previous captured frame.
        current_frame: Current captured frame.

    Returns:
        bool: True when scrolling no longer changes the visible page region.
    """

    if previous_frame.isNull() or current_frame.isNull():
        return False
    if previous_frame.size() != current_frame.size():
        return False
    if previous_frame.toImage() == current_frame.toImage():
        return True

    if _average_frame_difference(
        previous_frame,
        current_frame,
        content_region_only=True,
    ) <= _STATIONARY_PIXEL_DIFF_RATIO:
        return True

    progress_rows = estimate_scroll_progress_rows(previous_frame, current_frame)
    if progress_rows <= _STOP_NEW_CONTENT_ROWS:
        return True

    row_start, row_end = _content_row_bounds(current_frame.height())
    top_rows = _pixmap_to_gray_rows(previous_frame, row_start=row_start, row_end=row_end)
    bottom_rows = _pixmap_to_gray_rows(current_frame, row_start=row_start, row_end=row_end)
    if not top_rows or not bottom_rows:
        return False

    match = measure_vertical_overlap_from_rows(top_rows, bottom_rows)
    if match.overlap_rows == 0 and match.new_content_rows >= len(bottom_rows):
        match = measure_vertical_overlap_lenient(previous_frame, current_frame)

    content_height = max(1, len(bottom_rows))
    overlap_ratio = match.overlap_rows / content_height
    new_rows = max(0, content_height - match.overlap_rows)
    if overlap_ratio >= 0.985:
        return True
    if overlap_ratio >= _STATIONARY_OVERLAP_RATIO and new_rows <= _STATIONARY_MAX_NEW_ROWS:
        return True
    return new_rows <= _STOP_NEW_CONTENT_ROWS and overlap_ratio >= 0.85


def dedupe_scroll_frames(frames: list[QPixmap]) -> list[QPixmap]:
    """
    Removes trailing near-duplicate frames before stitching.

    Args:
        frames: Captured frames from top to bottom.

    Returns:
        list[QPixmap]: Frames without stationary duplicates at the end.
    """

    valid_frames = [frame for frame in frames if not frame.isNull()]
    if len(valid_frames) <= 1:
        return valid_frames

    deduped = [valid_frames[0]]
    for frame in valid_frames[1:]:
        if frame_has_meaningful_new_content(deduped[-1], frame):
            deduped.append(frame)
    return deduped


def _clamp_overlap(overlap: int, frame_height: int) -> int:
    """
    Clamps overlap to a safe range for one frame height.

    Args:
        overlap: Raw overlap row count.
        frame_height: Lower frame height.

    Returns:
        int: Clamped overlap row count.
    """

    if frame_height <= 1:
        return 0
    return max(0, min(overlap, frame_height - 1))


def _resolve_stitch_overlap(
    match: VerticalOverlapMatch,
    frame_height: int,
    overlap_history: list[int],
    lenient_match: VerticalOverlapMatch | None = None,
) -> int:
    """
    Resolves the overlap row count used while stitching one lower frame.

    Args:
        match: Overlap measurement against the previous frame.
        frame_height: Lower frame height in pixels.
        overlap_history: Overlap values used for earlier frame pairs.
        lenient_match: Optional tolerant overlap measurement for noisy frames.

    Returns:
        int: Overlap rows to use for stitching.
    """

    if match.difference_score <= _MAX_OVERLAP_SCORE and match.overlap_rows > 0:
        return _clamp_overlap(match.overlap_rows, frame_height)

    if (
        lenient_match is not None
        and lenient_match.overlap_rows > 0
        and lenient_match.difference_score <= _MAX_OVERLAP_SCORE * 2.5
    ):
        return _clamp_overlap(lenient_match.overlap_rows, frame_height)

    if overlap_history:
        median_overlap = sorted(overlap_history)[len(overlap_history) // 2]
        return _clamp_overlap(median_overlap, frame_height)

    estimated_overlap = max(8, int(frame_height * 0.82))
    return _clamp_overlap(estimated_overlap, frame_height)


def _append_vertical_frame(combined: QPixmap, frame: QPixmap, overlap: int) -> QPixmap:
    """
    Appends one lower frame onto an existing combined capture.

    Args:
        combined: Current stitched image.
        frame: Next lower frame.
        overlap: Shared row count between the two frames.

    Returns:
        QPixmap: Updated stitched image.
    """

    combined_image = combined.toImage()
    frame_image = frame.toImage()
    combined_height = combined_image.height()
    frame_height = frame_image.height()
    width = min(combined_image.width(), frame_image.width())
    overlap = _clamp_overlap(overlap, frame_height)
    append_height = max(0, frame_height - overlap)
    output_height = combined_height + append_height
    output = QImage(width, output_height, QImage.Format.Format_ARGB32)
    output.fill(Qt.GlobalColor.transparent)
    painter = QPainter(output)
    painter.drawImage(0, 0, combined_image)
    painter.drawImage(0, combined_height, frame_image, 0, overlap, width, append_height)
    painter.end()
    return QPixmap.fromImage(output)


def stitch_vertical_pixmaps(frames: list[QPixmap]) -> QPixmap:
    """
    Stitches multiple vertically scrolling frames into one pixmap.

    Args:
        frames: Capture frames from top to bottom.

    Returns:
        QPixmap: Combined pixmap.
    """

    valid_frames = dedupe_scroll_frames(frames)
    if not valid_frames:
        return QPixmap()
    if len(valid_frames) == 1:
        return valid_frames[0]

    combined = valid_frames[0]
    overlap_history: list[int] = []
    for frame_index in range(1, len(valid_frames)):
        previous_frame = valid_frames[frame_index - 1]
        frame = valid_frames[frame_index]
        match = measure_vertical_overlap(previous_frame, frame)
        lenient_match = measure_vertical_overlap_lenient(previous_frame, frame)
        overlap = _resolve_stitch_overlap(match, frame.height(), overlap_history, lenient_match)
        overlap_history.append(overlap)
        combined = _append_vertical_frame(combined, frame, overlap)
    return combined


def pixmap_to_png_bytes(pixmap: QPixmap) -> bytes:
    """
    Encodes one pixmap as PNG bytes.

    Args:
        pixmap: Source pixmap.

    Returns:
        bytes: PNG encoded image bytes.
    """

    byte_array = QByteArray()
    buffer = QBuffer(byte_array)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    return bytes(byte_array)
