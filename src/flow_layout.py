"""
Flow layout that wraps widgets from left to right and top to bottom.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QLayoutItem, QSizePolicy, QStyle, QWidget


class FlowLayout(QLayout):
    """
    Arranges child widgets in rows that wrap when horizontal space runs out.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        margin: int = 0,
        horizontal_spacing: int = -1,
        vertical_spacing: int = -1,
    ) -> None:
        """
        Initializes one flow layout.

        Args:
            parent: Optional parent widget.
            margin: Content margin on all sides in pixels.
            horizontal_spacing: Horizontal gap between items, or -1 for style default.
            vertical_spacing: Vertical gap between rows, or -1 for style default.
        """

        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._horizontal_spacing = horizontal_spacing
        self._vertical_spacing = vertical_spacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item: QLayoutItem) -> None:
        """
        Adds one layout item.

        Args:
            item: Item to append.

        Returns:
            None
        """

        self._items.append(item)

    def count(self) -> int:
        """
        Returns the number of managed items.

        Returns:
            int: Item count.
        """

        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:
        """
        Returns one item by index.

        Args:
            index: Item index.

        Returns:
            QLayoutItem | None: Item or None when out of range.
        """

        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> QLayoutItem | None:
        """
        Removes and returns one item by index.

        Args:
            index: Item index.

        Returns:
            QLayoutItem | None: Removed item or None when out of range.
        """

        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientation:
        """
        Returns supported expansion directions.

        Returns:
            Qt.Orientation: Empty because the layout does not expand children.
        """

        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        """
        Indicates that height depends on the assigned width.

        Returns:
            bool: Always True.
        """

        return True

    def heightForWidth(self, width: int) -> int:
        """
        Computes the required height for one target width.

        Args:
            width: Available layout width.

        Returns:
            int: Required height in pixels.
        """

        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:
        """
        Positions all items inside the target rectangle.

        Args:
            rect: Assigned layout rectangle.

        Returns:
            None
        """

        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        """
        Returns the preferred layout size.

        Returns:
            QSize: Preferred size.
        """

        return self.minimumSize()

    def minimumSize(self) -> QSize:
        """
        Returns the minimum layout size across all items.

        Returns:
            QSize: Minimum size.
        """

        size = QSize(0, 0)
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def horizontalSpacing(self) -> int:
        """
        Returns the effective horizontal spacing between items.

        Returns:
            int: Horizontal spacing in pixels.
        """

        if self._horizontal_spacing >= 0:
            return self._horizontal_spacing
        return self._smart_spacing(QStyle.PixelMetric.PM_LayoutHorizontalSpacing)

    def verticalSpacing(self) -> int:
        """
        Returns the effective vertical spacing between rows.

        Returns:
            int: Vertical spacing in pixels.
        """

        if self._vertical_spacing >= 0:
            return self._vertical_spacing
        return self._smart_spacing(QStyle.PixelMetric.PM_LayoutVerticalSpacing)

    def clear(self) -> None:
        """
        Removes all layout items while keeping their widgets parented.

        Returns:
            None
        """

        while self.count() > 0:
            item = self.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None and self.parentWidget() is not None:
                widget.setParent(self.parentWidget())

    def set_widgets(self, widgets: list[QWidget]) -> None:
        """
        Replaces all managed widgets in the provided order.

        Args:
            widgets: Widgets to display using flow placement.

        Returns:
            None
        """

        self.clear()
        for widget in widgets:
            self.addWidget(widget)

    def _smart_spacing(self, pixel_metric: QStyle.PixelMetric) -> int:
        """
        Resolves spacing from the parent widget style.

        Args:
            pixel_metric: Qt style pixel metric.

        Returns:
            int: Spacing in pixels.
        """

        parent = self.parentWidget()
        if parent is None:
            return 4
        return parent.style().pixelMetric(pixel_metric, None, parent)

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        """
        Lays out or measures items inside one rectangle.

        Args:
            rect: Target rectangle.
            test_only: When True, only compute height without moving widgets.

        Returns:
            int: Used height in pixels.
        """

        margins = self.contentsMargins()
        effective_rect = rect.adjusted(
            margins.left(),
            margins.top(),
            -margins.right(),
            -margins.bottom(),
        )
        x_pos = effective_rect.x()
        y_pos = effective_rect.y()
        row_height = 0
        used_height = 0
        horizontal_spacing = self.horizontalSpacing()
        vertical_spacing = self.verticalSpacing()

        for item in self._items:
            widget = item.widget()
            if widget is not None:
                policy = widget.sizePolicy()
                horizontal_policy = policy.horizontalPolicy()
                if horizontal_policy in {
                    QSizePolicy.Policy.Expanding,
                    QSizePolicy.Policy.MinimumExpanding,
                }:
                    continue
                widget.adjustSize()

            item_size = item.sizeHint()
            if widget is not None:
                item_size = item_size.expandedTo(widget.minimumSizeHint())

            item_width = item_size.width()
            if (
                row_height > 0
                and x_pos + item_width > effective_rect.right() + 1
            ):
                x_pos = effective_rect.x()
                y_pos += row_height + vertical_spacing
                row_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x_pos, y_pos), item_size))

            x_pos += item_width + horizontal_spacing
            row_height = max(row_height, item_size.height())
            used_height = max(used_height, y_pos + row_height - effective_rect.y())

        used_height += margins.top() + margins.bottom()
        return used_height


def widget_layout_area(widget: QWidget) -> int:
    """
    Returns the layout area used to sort toolbar containers.

    Args:
        widget: Widget whose size hint area is measured.

    Returns:
        int: Width multiplied by height, at least 1.
    """

    widget.adjustSize()
    size = widget.sizeHint()
    if widget.minimumWidth() > 0 and widget.minimumWidth() == widget.maximumWidth():
        width = widget.minimumWidth()
    else:
        width = max(size.width(), widget.minimumWidth())
    if widget.minimumHeight() > 0 and widget.minimumHeight() == widget.maximumHeight():
        height = widget.minimumHeight()
    else:
        height = max(size.height(), widget.minimumHeight())
    return max(1, width * height)


def sort_widgets_by_area_descending(widgets: list[QWidget]) -> list[QWidget]:
    """
    Sorts widgets by descending layout area for Tetris-like toolbar packing.

    Args:
        widgets: Widgets to sort.

    Returns:
        list[QWidget]: New list ordered from largest to smallest area.
    """

    return sorted(widgets, key=widget_layout_area, reverse=True)


class FlowLayoutWidget(QWidget):
    """
    Host widget that reflows FlowLayout children when its width changes.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        horizontal_spacing: int = 6,
        vertical_spacing: int = 3,
        margin: int = 0,
    ) -> None:
        """
        Initializes one auto-reflowing flow container.

        Args:
            parent: Optional parent widget.
            horizontal_spacing: Horizontal gap between items in pixels.
            vertical_spacing: Vertical gap between rows in pixels.
            margin: Content margin on all sides in pixels.
        """

        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self._flow_layout = FlowLayout(
            self,
            margin=margin,
            horizontal_spacing=horizontal_spacing,
            vertical_spacing=vertical_spacing,
        )

    @property
    def flow_layout(self) -> FlowLayout:
        """
        Returns the managed flow layout instance.

        Returns:
            FlowLayout: Active flow layout.
        """

        return self._flow_layout

    def set_flow_widgets(self, widgets: list[QWidget]) -> None:
        """
        Replaces all managed widgets and reflows immediately.

        Args:
            widgets: Widgets to place using float-style wrapping.

        Returns:
            None
        """

        self._flow_layout.set_widgets(widgets)
        self.update_flow_geometry()

    def hasHeightForWidth(self) -> bool:
        """
        Indicates that height depends on the assigned width.

        Returns:
            bool: Always True.
        """

        return True

    def heightForWidth(self, width: int) -> int:
        """
        Computes the required height for one target width.

        Args:
            width: Available container width.

        Returns:
            int: Required height in pixels.
        """

        effective_width = max(width, 1)
        return self._flow_layout.heightForWidth(effective_width)

    def sizeHint(self) -> QSize:
        """
        Returns the preferred size for the current or fallback width.

        Returns:
            QSize: Preferred size.
        """

        width = self.width() if self.width() > 0 else 320
        return QSize(width, self.heightForWidth(width))

    def minimumSizeHint(self) -> QSize:
        """
        Returns the minimum size hint for the flow container.

        Returns:
            QSize: Minimum size hint.
        """

        return QSize(0, self._flow_layout.minimumSize().height())

    def resizeEvent(self, event) -> None:
        """
        Reflows wrapped items when the container width changes.

        Args:
            event: Qt resize event.

        Returns:
            None
        """

        super().resizeEvent(event)
        self.update_flow_geometry()

    def update_flow_geometry(self) -> None:
        """
        Recomputes wrapped geometry for the current container width.

        Returns:
            None
        """

        width = self.width()
        if width <= 0:
            return

        height = self._flow_layout.heightForWidth(width)
        self.setMinimumHeight(height)
        self.setMaximumHeight(16777215)
        self._flow_layout.invalidate()
        self._flow_layout.setGeometry(QRect(0, 0, width, height))
        self.updateGeometry()
