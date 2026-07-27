"""
Shared multiplicative/absolute zoom behavior for the image and video canvases.
"""

from __future__ import annotations


class ZoomableCanvasMixin:
    """
    Provides zoom_in/zoom_out/set_zoom_factor for a QGraphicsView-based canvas.

    Host classes must provide a numeric ``self._zoom_factor`` attribute, a
    ``zoom_changed`` Qt signal taking one float, and the usual QGraphicsView
    ``scale()`` method. Override ``_on_zoom_applied()`` for extra bookkeeping
    that should run after every zoom change (``reset_zoom`` is intentionally
    not included here since the two canvases fit different rects to the
    viewport and is left to each host class).
    """

    ZOOM_MIN = 0.1
    ZOOM_MAX = 8.0
    ZOOM_STEP = 1.06

    def zoom_in(self) -> None:
        """
        Zooms into the canvas.

        Returns:
            None
        """

        self._apply_zoom(self.ZOOM_STEP)

    def zoom_out(self) -> None:
        """
        Zooms out of the canvas.

        Returns:
            None
        """

        self._apply_zoom(1.0 / self.ZOOM_STEP)

    def set_zoom_factor(self, target_zoom: float) -> None:
        """
        Sets zoom to an absolute factor value.

        Args:
            target_zoom: Target zoom factor (1.0 = 100%).

        Returns:
            None
        """

        bounded_zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, target_zoom))
        if abs(bounded_zoom - self._zoom_factor) < 0.0001:
            return
        scale_factor = bounded_zoom / self._zoom_factor
        self.scale(scale_factor, scale_factor)
        self._zoom_factor = bounded_zoom
        self.zoom_changed.emit(self._zoom_factor)
        self._on_zoom_applied()

    def _apply_zoom(self, factor: float) -> None:
        """
        Applies a multiplicative zoom factor, clamped to ZOOM_MIN/ZOOM_MAX.

        Args:
            factor: Scale factor.

        Returns:
            None
        """

        new_zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, self._zoom_factor * factor))
        if abs(new_zoom - self._zoom_factor) < 0.0001:
            return
        scale_factor = new_zoom / self._zoom_factor
        self.scale(scale_factor, scale_factor)
        self._zoom_factor = new_zoom
        self.zoom_changed.emit(self._zoom_factor)
        self._on_zoom_applied()

    def _on_zoom_applied(self) -> None:
        """
        Runs extra bookkeeping after a zoom change; no-op unless overridden.

        Returns:
            None
        """

        return
