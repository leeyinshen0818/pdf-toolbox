"""Borderless inline status message with a semantic icon and colour."""
from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from pdf_toolbox.ui import icons
from pdf_toolbox.ui.tokens import DANGER_TEXT, ICON_INLINE, SPACE_8, SUCCESS_TEXT, TEXT_SECONDARY, WARNING_TEXT


class StatusKind(str, Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


_ICON_FOR_KIND = {
    StatusKind.INFO: ("info", TEXT_SECONDARY),
    StatusKind.SUCCESS: ("circle-check", SUCCESS_TEXT),
    StatusKind.WARNING: ("triangle-alert", WARNING_TEXT),
    StatusKind.ERROR: ("circle-x", DANGER_TEXT),
}


class StatusLine(QWidget):
    """Status message shown under each page.

    `setText()` / `text()` mirror QLabel so plain informational messages need no special call;
    `show_success()`, `show_warning()` and `show_error()` switch the icon and colour.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("StatusLine")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_8)

        self._icon = QLabel()
        self._icon.setObjectName("StatusIcon")
        self._icon.setFixedSize(ICON_INLINE, ICON_INLINE)
        self._label = QLabel("")
        self._label.setObjectName("StatusText")
        self._label.setWordWrap(True)
        self._label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        layout.addWidget(self._icon, 0, Qt.AlignTop)
        layout.addWidget(self._label, 1)
        self._kind = StatusKind.INFO
        self.set_message("", StatusKind.INFO)

    # QLabel-compatible API -------------------------------------------------
    def setText(self, text: str) -> None:  # noqa: N802 - mirrors QLabel
        self.set_message(text, StatusKind.INFO)

    def text(self) -> str:
        return self._label.text()

    # Semantic messages -----------------------------------------------------
    def show_success(self, text: str) -> None:
        self.set_message(text, StatusKind.SUCCESS)

    def show_warning(self, text: str) -> None:
        self.set_message(text, StatusKind.WARNING)

    def show_error(self, text: str) -> None:
        self.set_message(text, StatusKind.ERROR)

    @property
    def kind(self) -> StatusKind:
        return self._kind

    def set_message(self, text: str, kind: StatusKind = StatusKind.INFO) -> None:
        self._kind = StatusKind(kind)
        self._label.setText(text)
        self._label.setProperty("kind", self._kind.value)
        self._label.style().unpolish(self._label)
        self._label.style().polish(self._label)
        if text:
            name, colour = _ICON_FOR_KIND[self._kind]
            icon = icons.icon(name, colour, ICON_INLINE)
            self._icon.setPixmap(icon.pixmap(QSize(ICON_INLINE, ICON_INLINE), self.devicePixelRatioF()))
            self._icon.setVisible(True)
        else:
            self._icon.clear()
            self._icon.setVisible(False)
