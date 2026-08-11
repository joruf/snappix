"""
Point handling for freehand strokes: thinning while drawing, smoothing on top.

Deliberately free of Qt types so the geometry can be tested on its own. Callers
convert to and from ``QPointF``; everything here works on plain ``(x, y)`` pairs.

Smoothing is applied to a *copy* of the recorded points and never replaces them.
The raw stroke stays in the annotation payload, so the smoothing slider can be
moved back and forth -- also after saving and reopening -- without the stroke
degrading a little more each time.
"""

from __future__ import annotations

from collections.abc import Sequence

Point = tuple[float, float]

SMOOTHING_MIN = 0.0
SMOOTHING_MAX = 1.0
SMOOTHING_DEFAULT = 0.35

# Chaikin passes at full slider travel. Corner cutting doubles the point count
# each pass, and beyond two the curve barely changes.
MAX_SMOOTHING_PASSES = 2

# Widest averaging window at full slider travel, in points. Corner cutting alone
# rounds corners but leaves the shake amplitude of an unsteady hand intact; the
# averaging pass is what actually removes the wobble.
MAX_AVERAGE_WINDOW = 15

# Points closer than this to their predecessor are dropped while recording.
# A mouse drag reports far more positions than a stroke needs; without thinning
# a single sweep stores thousands of near-identical points.
FREEHAND_MIN_POINT_DISTANCE = 2.0


def clamp_smoothing(value: float) -> float:
    """
    Clamps a smoothing amount into the supported range.

    Args:
        value: Requested amount.

    Returns:
        float: Amount between ``SMOOTHING_MIN`` and ``SMOOTHING_MAX``.
    """

    try:
        amount = float(value)
    except (TypeError, ValueError):
        return SMOOTHING_DEFAULT
    if amount != amount:  # NaN
        return SMOOTHING_DEFAULT
    return max(SMOOTHING_MIN, min(SMOOTHING_MAX, amount))


def should_append_point(
    points: Sequence[Point],
    candidate: Point,
    *,
    min_distance: float = FREEHAND_MIN_POINT_DISTANCE,
) -> bool:
    """
    Reports whether a freshly sampled position is far enough to be recorded.

    Args:
        points: Points recorded so far.
        candidate: Newly sampled position.
        min_distance: Smallest accepted gap to the previous point.

    Returns:
        bool: True when the point should be appended.
    """

    if not points:
        return True
    last_x, last_y = points[-1]
    dx = float(candidate[0]) - float(last_x)
    dy = float(candidate[1]) - float(last_y)
    return (dx * dx) + (dy * dy) >= (float(min_distance) ** 2)


def thin_points(
    points: Sequence[Point],
    *,
    min_distance: float = FREEHAND_MIN_POINT_DISTANCE,
) -> list[Point]:
    """
    Drops points that sit closer together than one step.

    The final point is always kept, so the stroke still ends where the pointer
    was released even when that last move was a short one.

    Args:
        points: Recorded points in drawing order.
        min_distance: Smallest accepted gap between consecutive points.

    Returns:
        list[Point]: Thinned points in drawing order.
    """

    source = [(float(x), float(y)) for x, y in points]
    if len(source) <= 2:
        return source

    kept: list[Point] = [source[0]]
    for point in source[1:]:
        if should_append_point(kept, point, min_distance=min_distance):
            kept.append(point)

    if kept[-1] != source[-1]:
        kept.append(source[-1])
    return kept


def smoothing_passes(amount: float) -> int:
    """
    Maps a slider amount onto the number of Chaikin passes.

    Args:
        amount: Smoothing amount between 0 and 1.

    Returns:
        int: Pass count between 0 and ``MAX_SMOOTHING_PASSES``.
    """

    resolved = clamp_smoothing(amount)
    if resolved <= 0.0:
        return 0
    return max(1, round(resolved * MAX_SMOOTHING_PASSES))


def average_window(amount: float) -> int:
    """
    Maps a slider amount onto the averaging window width.

    Args:
        amount: Smoothing amount between 0 and 1.

    Returns:
        int: Odd window width; 1 means no averaging.
    """

    resolved = clamp_smoothing(amount)
    if resolved <= 0.0:
        return 1
    half = max(1, round(resolved * (MAX_AVERAGE_WINDOW - 1) / 2))
    return (half * 2) + 1


def _moving_average(points: list[Point], window: int) -> list[Point]:
    """
    Averages each point with its neighbours inside one window.

    First and last point are carried over untouched so the stroke keeps its
    start and end; the window shrinks near the ends instead of reaching past
    them, which would pull the stroke inwards.

    Args:
        points: Points in drawing order.
        window: Odd window width; 1 returns the input.

    Returns:
        list[Point]: Averaged points.
    """

    if window <= 1 or len(points) < 3:
        return list(points)

    half = window // 2
    last = len(points) - 1
    averaged: list[Point] = [points[0]]
    for index in range(1, last):
        reach = min(half, index, last - index)
        start = index - reach
        end = index + reach + 1
        chunk = points[start:end]
        count = float(len(chunk))
        averaged.append(
            (
                sum(point[0] for point in chunk) / count,
                sum(point[1] for point in chunk) / count,
            )
        )
    averaged.append(points[last])
    return averaged


def _chaikin_pass(points: list[Point]) -> list[Point]:
    """
    Runs one Chaikin corner-cutting pass over an open path.

    Each inner segment is replaced by two points at one quarter and three
    quarters of its length, which rounds every corner. First and last point are
    carried over untouched so the stroke keeps its start and end.

    Args:
        points: Points in drawing order.

    Returns:
        list[Point]: Points after one pass.
    """

    if len(points) < 3:
        return list(points)

    cut: list[Point] = [points[0]]
    for index in range(len(points) - 1):
        start_x, start_y = points[index]
        end_x, end_y = points[index + 1]
        cut.append((start_x * 0.75 + end_x * 0.25, start_y * 0.75 + end_y * 0.25))
        cut.append((start_x * 0.25 + end_x * 0.75, start_y * 0.25 + end_y * 0.75))
    cut.append(points[-1])
    return cut


def smooth_points(points: Sequence[Point], amount: float) -> list[Point]:
    """
    Returns a smoothed copy of one freehand stroke.

    Args:
        points: Recorded points in drawing order.
        amount: Smoothing amount between 0 and 1. Zero returns the input.

    Returns:
        list[Point]: Smoothed points; endpoints match the input.
    """

    source = [(float(x), float(y)) for x, y in points]
    passes = smoothing_passes(amount)
    if passes <= 0 or len(source) < 3:
        return source

    # Average first to take the shake out, then cut corners for roundness.
    smoothed = _moving_average(source, average_window(amount))
    for _ in range(passes):
        smoothed = _chaikin_pass(smoothed)
    return smoothed


def path_length(points: Sequence[Point]) -> float:
    """
    Returns the summed segment length of a point run.

    Used by tests to show that smoothing shortens the path -- the measurable
    effect of cutting corners.

    Args:
        points: Points in drawing order.

    Returns:
        float: Total length.
    """

    total = 0.0
    for index in range(len(points) - 1):
        start_x, start_y = points[index]
        end_x, end_y = points[index + 1]
        total += (((end_x - start_x) ** 2) + ((end_y - start_y) ** 2)) ** 0.5
    return total
