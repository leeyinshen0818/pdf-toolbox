"""File drop target and the shared empty state shown inside it."""
from __future__ import annotations

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from pdf_toolbox.ui.tokens import SPACE_8, SPACE_12


def set_drop_active(widget: QWidget, active: bool) -> None:
    """Toggle the `dropActive` highlight (styled in styles.py)."""
    widget.setProperty("dropActive", active)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def local_paths(mime: QMimeData) -> list[str]:
    return [url.toLocalFile() for url in mime.urls() if url.isLocalFile()]


class EmptyState(QWidget):
    """Headline, one-line hint and a single primary button."""

    action_requested = Signal()

    def __init__(self, headline: str, hint: str, button_text: str) -> None:
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

        layout.addWidget(self.headline)
        layout.addWidget(self.hint)
        layout.addSpacing(SPACE_12 - SPACE_8)
        layout.addWidget(self.button, alignment=Qt.AlignCenter)


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


def empty_drop_area(headline: str, hint: str, button_text: str) -> tuple[DropArea, EmptyState]:
    state = EmptyState(headline, hint, button_text)
    return DropArea(state), state
