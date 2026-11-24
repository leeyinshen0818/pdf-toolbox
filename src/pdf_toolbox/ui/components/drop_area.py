"""File drop target and the shared empty state shown inside it."""
from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QMimeData, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from pdf_toolbox.ui.tokens import ON_PRIMARY, RADIUS_CARD, SPACE_8, SPACE_12, SPACE_16, TYPE_BADGE, qfont


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
    """A solid rounded tile with a large white format name. Information only, never interactive."""

    def __init__(self, label: str, colour: str) -> None:
        super().__init__()
        self.setObjectName("FormatBadge")
        self.label = label
        self._colour = QColor(colour)
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
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._colour)
        painter.drawRoundedRect(self.rect(), RADIUS_CARD, RADIUS_CARD)
        painter.setPen(QColor(ON_PRIMARY))
        painter.setFont(self._font)
        painter.drawText(self.rect(), Qt.AlignCenter, self.label)


class FormatBadges(QWidget):
    """Equal-size badges in one centred row, stacked instead when the row would not fit the width.

    The badges are placed directly rather than by a layout: Qt asks a widget's own layout, not
    the widget, for height-for-width, and the height here depends on the row/stack choice.
    """

    def __init__(self, badges: Sequence[tuple[str, str]]) -> None:
        super().__init__()
        self.setObjectName("FormatBadges")
        self.badges = [FormatBadge(label, colour) for label, colour in badges]
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

    Optionally, between the hint and the button: one colour badge per accepted format and a
    small note under them. These are information only, and are hidden (note first) when the
    drop area is too short to show them without clipping.
    """

    action_requested = Signal()

    def __init__(
        self,
        headline: str,
        hint: str,
        button_text: str,
        format_badges: Sequence[tuple[str, str]] | None = None,
        format_note: str | None = None,
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
        self.hint = QLabel(hint)
        self.hint.setObjectName("SubtleText")
        self.hint.setAlignment(Qt.AlignCenter)
        self.hint.setWordWrap(True)
        self.button = QPushButton(button_text)
        self.button.setObjectName("PrimaryButton")
        self.button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.button.clicked.connect(self.action_requested.emit)

        self.format_badges: FormatBadges | None = None
        self.format_note: QLabel | None = None
        if format_badges:
            self.format_badges = FormatBadges(format_badges)
            # Use the full width, so the badges choose between a row and a stack on the real
            # available width; labels centre their own text and the button keeps its centring.
            layout.setAlignment(Qt.AlignVCenter)
        if format_note:
            self.format_note = QLabel(format_note)
            self.format_note.setObjectName("FormatNote")
            self.format_note.setAlignment(Qt.AlignCenter)
            self.format_note.setWordWrap(True)

        layout.addWidget(self.headline)
        layout.addWidget(self.hint)
        if self.format_badges is not None:
            layout.addWidget(self.format_badges)
        if self.format_note is not None:
            layout.addWidget(self.format_note)
        layout.addSpacing(SPACE_12 - SPACE_8)
        layout.addWidget(self.button, alignment=Qt.AlignCenter)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_format_details()

    def _fit_format_details(self) -> None:
        """Show the format badges and note only while everything fits at the current size."""
        if self.format_badges is None and self.format_note is None:
            return
        margins = self.layout().contentsMargins()
        width = max(1, self.width() - margins.left() - margins.right())
        available = self.height() - margins.top() - margins.bottom()
        show_badges = (
            self.format_badges is not None and self.content_height(width, badges=True, note=False) <= available
        )
        show_note = (
            self.format_note is not None
            and (show_badges or self.format_badges is None)
            and self.content_height(width, badges=show_badges, note=True) <= available
        )
        if self.format_badges is not None:
            self.format_badges.setVisible(show_badges)
        if self.format_note is not None:
            self.format_note.setVisible(show_note)

    def content_height(self, width: int, *, badges: bool, note: bool) -> int:
        """Column height at this width with the optional parts shown or not, as the layout stacks it."""
        widgets: list[QWidget] = [self.headline, self.hint]
        if badges and self.format_badges is not None:
            widgets.append(self.format_badges)
        if note and self.format_note is not None:
            widgets.append(self.format_note)
        widgets.append(self.button)
        heights = [
            widget.heightForWidth(width) if widget.hasHeightForWidth() else widget.sizeHint().height()
            for widget in widgets
        ]
        # One gap between each pair of widgets, plus the fixed spacer above the button (no gap of its own).
        return sum(heights) + self.layout().spacing() * (len(widgets) - 1) + (SPACE_12 - SPACE_8)


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
    hint: str,
    button_text: str,
    format_badges: Sequence[tuple[str, str]] | None = None,
    format_note: str | None = None,
) -> tuple[DropArea, EmptyState]:
    state = EmptyState(headline, hint, button_text, format_badges, format_note)
    return DropArea(state), state
