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

    # Smallest pinch change worth acting on. Touchpads report a stream of tiny
    # scale factors; rescaling on every one of them costs a full repaint and
    # makes the picture shimmer without moving.
    PINCH_DEAD_ZONE = 0.002

    def enable_pinch_zoom(self) -> None:
        """
        Starts listening for two-finger pinch gestures.

        Returns:
            None
        """

        from PySide6.QtCore import Qt

        self.grabGesture(Qt.GestureType.PinchGesture)

    def handle_zoom_event(self, event) -> bool:
        """
        Zooms in response to a pinch, whichever way the system reports it.

        Two-finger zoom arrives differently depending on the platform and the
        input driver: as a pinch gesture from a touchscreen, or as a native
        zoom gesture from a touchpad. Both are handled here so the canvases
        only have to forward the event.

        Args:
            event: Event to inspect.

        Returns:
            bool: True when the event was a zoom and has been handled.
        """

        from PySide6.QtCore import QEvent, Qt

        event_type = event.type()
        if event_type == QEvent.Type.NativeGesture:
            if event.gestureType() != Qt.NativeGestureType.ZoomNativeGesture:
                return False
            return self._apply_pinch_scale(1.0 + float(event.value()))
        if event_type == QEvent.Type.Gesture:
            pinch = event.gesture(Qt.GestureType.PinchGesture)
            if pinch is None:
                return False
            self._apply_pinch_scale(float(pinch.scaleFactor()))
            return True
        return False

    def _apply_pinch_scale(self, scale_factor: float) -> bool:
        """
        Applies one pinch step.

        Args:
            scale_factor: Reported scale factor; 1.0 means unchanged.

        Returns:
            bool: True when the gesture was consumed.
        """

        if scale_factor <= 0.0:
            return True
        if abs(scale_factor - 1.0) < self.PINCH_DEAD_ZONE:
            return True
        self._apply_zoom(scale_factor)
        return True

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
