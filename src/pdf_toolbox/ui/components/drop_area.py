"""File drop target and the shared empty state shown inside it."""
from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QMimeData, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from pdf_toolbox.ui.tokens import (
    RADIUS_CARD,
    SPACE_8,
    SPACE_12,
    SPACE_16,
    SPACE_24,
    TYPE_BADGE,
    BadgeColours,
    qfont,
)


BADGE_PADDING_X = SPACE_16
BADGE_PADDING_Y = SPACE_12
BADGE_GAP = SPACE_8


def set_drop_active(widget: QWidget, active: bool) -> None:
    """Toggle the `dropActive` highlight (styled in styles.py)."""
    widget.setProperty("dropActive", active)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def local_paths(mime: QMimeData) -> list[str]:
    return [url.toLocalFile() for url in mime.urls() if url.isLocalFile()]


class FormatBadge(QWidget):
    """A soft tinted tile (pale fill, thin border) with a large format name in the vivid hue.

    Information only, never interactive.
    """

    def __init__(self, label: str, colours: BadgeColours) -> None:
        super().__init__()
        self.setObjectName("FormatBadge")
        self.label = label
        self._colours = colours
        # Kept apart from the widget font, which the app stylesheet's inherited font would override.
        self._font = qfont(TYPE_BADGE)
        self.setAccessibleName(label)
        self.setFocusPolicy(Qt.NoFocus)
        # Mouse and drag events pass straight through to the drop area underneath.
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def natural_size(self) -> QSize:
        """The label's size from font metrics, plus padding."""
        metrics = QFontMetrics(self._font)
        return QSize(
            metrics.horizontalAdvance(self.label) + 2 * BADGE_PADDING_X,
            metrics.height() + 2 * BADGE_PADDING_Y,
        )

    def sizeHint(self) -> QSize:
        return self.natural_size()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(self._colours.border), 1))
        painter.setBrush(QColor(self._colours.fill))
        # Inset by half the pen width so the 1px border sits crisply inside the tile.
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), RADIUS_CARD, RADIUS_CARD)
        painter.setPen(QColor(self._colours.text))
        painter.setFont(self._font)
        painter.drawText(self.rect(), Qt.AlignCenter, self.label)


class FormatBadges(QWidget):
    """Equal-size badges in one centred row, stacked instead when the row would not fit the width.

    The badges are placed directly rather than by a layout: Qt asks a widget's own layout, not
    the widget, for height-for-width, and the height here depends on the row/stack choice.
    """

    def __init__(self, badges: Sequence[tuple[str, BadgeColours]]) -> None:
        super().__init__()
        self.setObjectName("FormatBadges")
        self.badges = [FormatBadge(label, colours) for label, colours in badges]
        self.tile_size = QSize(0, 0)
        for badge in self.badges:
            self.tile_size = self.tile_size.expandedTo(badge.natural_size())
        self._stacked = False
        for badge in self.badges:
            badge.setParent(self)
            badge.setFixedSize(self.tile_size)
        policy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def row_width(self) -> int:
        count = len(self.badges)
        return count * self.tile_size.width() + (count - 1) * BADGE_GAP

    def stacks_at(self, width: int) -> bool:
        return width < self.row_width()

    def is_stacked(self) -> bool:
        return self._stacked

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        if self.stacks_at(width):
            count = len(self.badges)
            return count * self.tile_size.height() + (count - 1) * BADGE_GAP
        return self.tile_size.height()

    def sizeHint(self) -> QSize:
        return QSize(self.row_width(), self.tile_size.height())

    def minimumSizeHint(self) -> QSize:
        return QSize(self.tile_size.width(), self.heightForWidth(self.tile_size.width()))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        stacked = self.stacks_at(self.width())
        tile_width, tile_height = self.tile_size.width(), self.tile_size.height()
        if stacked:
            left = max(0, (self.width() - tile_width) // 2)
            for index, badge in enumerate(self.badges):
                badge.move(left, index * (tile_height + BADGE_GAP))
        else:
            left = (self.width() - self.row_width()) // 2
            for index, badge in enumerate(self.badges):
                badge.move(left + index * (tile_width + BADGE_GAP), 0)
        if stacked != self._stacked:
            self._stacked = stacked
            self.updateGeometry()  # the height for this width changed


class EmptyState(QWidget):
    """Headline, one-line hint and a single primary button.

    With the optional format badges and/or a caption under the button, the content is laid
    out in three clearly separated groups instead: headline (and hint, if any), the badges,
    then the button with its caption. The badges are information only and are hidden when
    the drop area is too short to show them without clipping.
    """

    action_requested = Signal()

    def __init__(
        self,
        headline: str,
        hint: str | None,
        button_text: str,
        format_badges: Sequence[tuple[str, BadgeColours]] | None = None,
        caption: str | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("EmptyState")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(SPACE_8)

        self.headline = QLabel(headline)
        self.headline.setObjectName("DropTitle")
        self.headline.setAlignment(Qt.AlignCenter)
        self.headline.setWordWrap(True)
        self.hint: QLabel | None = None
        if hint:
            self.hint = QLabel(hint)
            self.hint.setObjectName("SubtleText")
            self.hint.setAlignment(Qt.AlignCenter)
            self.hint.setWordWrap(True)
        self.button = QPushButton(button_text)
        self.button.setObjectName("PrimaryButton")
        self.button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.button.clicked.connect(self.action_requested.emit)

        self.format_badges = FormatBadges(format_badges) if format_badges else None
        self.caption: QLabel | None = None
        if caption:
            self.caption = QLabel(caption)
            self.caption.setObjectName("EmptyCaption")
            self.caption.setAlignment(Qt.AlignCenter)
            self.caption.setWordWrap(True)

        self._groups: list[QWidget] = []
        if self.format_badges is None and self.caption is None:
            # The plain empty state, unchanged: headline, hint, button.
            layout.addWidget(self.headline)
            if self.hint is not None:
                layout.addWidget(self.hint)
            layout.addSpacing(SPACE_12 - SPACE_8)
            layout.addWidget(self.button, alignment=Qt.AlignCenter)
            return

        # Grouped: full width (the badges choose row or stack on the real width) and a wide gap
        # between groups. A hidden group takes its gap with it.
        layout.setAlignment(Qt.AlignVCenter)
        layout.setSpacing(SPACE_24)
        self._groups.append(_group([self.headline, self.hint]))
        if self.format_badges is not None:
            self._groups.append(self.format_badges)
        self._groups.append(_group([self.button, self.caption], centre=self.button))
        for group in self._groups:
            layout.addWidget(group)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_format_badges()

    def _fit_format_badges(self) -> None:
        """Show the badges only while everything fits at the current size."""
        if self.format_badges is None:
            return
        margins = self.layout().contentsMargins()
        width = max(1, self.width() - margins.left() - margins.right())
        available = self.height() - margins.top() - margins.bottom()
        self.format_badges.setVisible(self.content_height(width, badges=True) <= available)

    def content_height(self, width: int, *, badges: bool) -> int:
        """Height of the grouped column at this width, with or without the badges."""
        groups = [group for group in self._groups if badges or group is not self.format_badges]
        heights = [
            group.heightForWidth(width) if group.hasHeightForWidth() else group.sizeHint().height()
            for group in groups
        ]
        return sum(heights) + self.layout().spacing() * (len(groups) - 1)


def _group(widgets: Sequence[QWidget | None], *, centre: QWidget | None = None) -> QWidget:
    """Stack widgets closely (SPACE_8 apart) as one unit of the grouped empty state."""
    group = QWidget()
    group.setObjectName("EmptyStateGroup")
    layout = QVBoxLayout(group)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(SPACE_8)
    for widget in widgets:
        if widget is None:
            continue
        if widget is centre:
            layout.addWidget(widget, alignment=Qt.AlignCenter)
        else:
            layout.addWidget(widget)
    return group


class DropArea(QFrame):
    """Dashed drop target; emits the local file paths dropped on it."""

    files_dropped = Signal(list)

    def __init__(self, content: QWidget | None = None) -> None:
        super().__init__()
        self.setObjectName("DropArea")
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        if content is not None:
            layout.addWidget(content)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            set_drop_active(self, True)
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        set_drop_active(self, False)
        if event.mimeData().hasUrls():
            self.files_dropped.emit(local_paths(event.mimeData()))
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    def dragLeaveEvent(self, event) -> None:
        set_drop_active(self, False)
        super().dragLeaveEvent(event)


def empty_drop_area(
    headline: str,
    hint: str | None,
    button_text: str,
    format_badges: Sequence[tuple[str, BadgeColours]] | None = None,
    caption: str | None = None,
) -> tuple[DropArea, EmptyState]:
    state = EmptyState(headline, hint, button_text, format_badges, caption)
    return DropArea(state), state
