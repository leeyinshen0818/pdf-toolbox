"""File drop target and the shared empty state shown inside it."""
from __future__ import annotations

from collections.abc import Sequence
from html import escape

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from pdf_toolbox.ui.tokens import SPACE_4, SPACE_8, SPACE_12, TEXT, TYPE_FIELD_LABEL


def set_drop_active(widget: QWidget, active: bool) -> None:
    """Toggle the `dropActive` highlight (styled in styles.py)."""
    widget.setProperty("dropActive", active)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def local_paths(mime: QMimeData) -> list[str]:
    return [url.toLocalFile() for url in mime.urls() if url.isLocalFile()]


class EmptyState(QWidget):
    """Headline, one-line hint and a single primary button.

    Optionally, between the hint and the button: one plain-text line per accepted format
    ("HEIC  iPhone photos") and a small note under them. These are information only, and are
    hidden (note first) when the drop area is too short to show them without clipping.
    """

    action_requested = Signal()

    def __init__(
        self,
        headline: str,
        hint: str,
        button_text: str,
        format_rows: Sequence[tuple[str, str]] | None = None,
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

        self.format_rows: QWidget | None = None
        self.format_note: QLabel | None = None
        if format_rows:
            self.format_rows = QWidget()
            self.format_rows.setObjectName("FormatRows")
            rows_layout = QVBoxLayout(self.format_rows)
            rows_layout.setContentsMargins(0, SPACE_4, 0, 0)
            rows_layout.setSpacing(SPACE_4)
            for label, caption in format_rows:
                rows_layout.addWidget(_format_row_label(label, caption))
            # Use the full width so the longer captions wrap as little as possible; each label
            # centres its own text, and the button keeps its own centring.
            layout.setAlignment(Qt.AlignVCenter)
        if format_note:
            self.format_note = QLabel(format_note)
            self.format_note.setObjectName("FormatNote")
            self.format_note.setAlignment(Qt.AlignCenter)
            self.format_note.setWordWrap(True)

        layout.addWidget(self.headline)
        layout.addWidget(self.hint)
        if self.format_rows is not None:
            layout.addWidget(self.format_rows)
        if self.format_note is not None:
            layout.addWidget(self.format_note)
        layout.addSpacing(SPACE_12 - SPACE_8)
        layout.addWidget(self.button, alignment=Qt.AlignCenter)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_format_details()

    def _fit_format_details(self) -> None:
        """Show the format rows and note only while everything fits at the current size."""
        if self.format_rows is None and self.format_note is None:
            return
        margins = self.layout().contentsMargins()
        width = max(1, self.width() - margins.left() - margins.right())
        available = self.height() - margins.top() - margins.bottom()
        show_rows = self.format_rows is not None and self._content_height(width, rows=True, note=False) <= available
        show_note = (
            self.format_note is not None
            and (show_rows or self.format_rows is None)
            and self._content_height(width, rows=show_rows, note=True) <= available
        )
        if self.format_rows is not None:
            self.format_rows.setVisible(show_rows)
        if self.format_note is not None:
            self.format_note.setVisible(show_note)

    def _content_height(self, width: int, *, rows: bool, note: bool) -> int:
        widgets: list[QWidget] = [self.headline, self.hint]
        if rows and self.format_rows is not None:
            widgets.append(self.format_rows)
        if note and self.format_note is not None:
            widgets.append(self.format_note)
        widgets.append(self.button)
        heights = [
            widget.heightForWidth(width) if widget.hasHeightForWidth() else widget.sizeHint().height()
            for widget in widgets
        ]
        spacing = self.layout().spacing()
        return sum(heights) + spacing * len(widgets) + (SPACE_12 - SPACE_8)


def _format_row_label(label: str, caption: str) -> QLabel:
    """One centred line: the format name, emphasised, then a plain-language caption."""
    name_style = f"color: {TEXT}; font-size: {TYPE_FIELD_LABEL.size}px; font-weight: {TYPE_FIELD_LABEL.weight};"
    row = QLabel(f'<span style="{name_style}">{escape(label)}</span>&nbsp;&nbsp;{escape(caption)}')
    row.setObjectName("FormatRow")
    row.setTextFormat(Qt.RichText)
    row.setAlignment(Qt.AlignCenter)
    row.setWordWrap(True)
    row.setTextInteractionFlags(Qt.NoTextInteraction)
    return row


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
    format_rows: Sequence[tuple[str, str]] | None = None,
    format_note: str | None = None,
) -> tuple[DropArea, EmptyState]:
    state = EmptyState(headline, hint, button_text, format_rows, format_note)
    return DropArea(state), state
