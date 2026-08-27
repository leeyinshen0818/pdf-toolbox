from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QGridLayout, QLayout, QSizePolicy, QStyle


class ResponsiveMode(str, Enum):
    COMPACT = "compact"
    MEDIUM = "medium"
    WIDE = "wide"


WIDE_BREAKPOINT = 1300
MEDIUM_BREAKPOINT = 900


def responsive_mode_for_width(width: int) -> ResponsiveMode:
    if width >= WIDE_BREAKPOINT:
        return ResponsiveMode.WIDE
    if width >= MEDIUM_BREAKPOINT:
        return ResponsiveMode.MEDIUM
    return ResponsiveMode.COMPACT


def clear_grid_layout(layout: QGridLayout) -> None:
    while layout.count():
        layout.takeAt(0)
    for index in range(4):
        layout.setColumnStretch(index, 0)
        layout.setRowStretch(index, 0)


class FlowLayout(QLayout):
    def __init__(self, parent=None, margin: int = 0, spacing: int = 8) -> None:
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def __del__(self) -> None:
        while self.count():
            self.takeAt(0)

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _smart_spacing(self, pixel_metric: QStyle.PixelMetric) -> int:
        parent = self.parent()
        if parent is None:
            return self.spacing()
        if parent.isWidgetType():
            return parent.style().pixelMetric(pixel_metric, None, parent)
        return parent.spacing()

    def _do_layout(self, rect: QRect, *, test_only: bool) -> int:
        margins = self.contentsMargins()
        effective_rect = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x = effective_rect.x()
        y = effective_rect.y()
        line_height = 0

        for item in self._items:
            widget = item.widget()
            space_x = self.spacing() if self.spacing() >= 0 else self._smart_spacing(QStyle.PM_LayoutHorizontalSpacing)
            space_y = self.spacing() if self.spacing() >= 0 else self._smart_spacing(QStyle.PM_LayoutVerticalSpacing)
            next_x = x + item.sizeHint().width() + space_x

            if next_x - space_x > effective_rect.right() and line_height > 0:
                x = effective_rect.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0

            if not test_only and widget is not None:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = next_x
            line_height = max(line_height, item.sizeHint().height())

        return y + line_height - rect.y() + margins.bottom()


def allow_horizontal_shrink(widget) -> None:
    widget.setMinimumWidth(0)
    widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

