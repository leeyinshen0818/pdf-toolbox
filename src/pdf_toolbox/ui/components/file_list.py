"""One-row-per-file list used by the HEIC → JPG and PDF → Image pages.

Each row: thumbnail, file name (elided, full path in the tooltip), one detail line and a trash
button. Rows can be created with a placeholder thumbnail and filled in later.
"""
from __future__ import annotations

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QPushButton, QVBoxLayout, QWidget

from pdf_toolbox.ui import icons
from pdf_toolbox.ui.components.drop_area import local_paths, set_drop_active
from pdf_toolbox.ui.components.widgets import ElidedLabel
from pdf_toolbox.ui.metrics import ROW_THUMBNAIL, ROW_THUMBNAIL_IMAGE
from pdf_toolbox.ui.tokens import ICON_DELETE, MIN_TARGET, SPACE_4, SPACE_8, TEXT_SECONDARY

PLACEHOLDER_ICON = 24


class FileListWidget(QListWidget):
    """Card-styled list of file rows that also accepts dropped files."""

    files_dropped = Signal(list)

    def __init__(self, selection_mode: QListWidget.SelectionMode = QListWidget.SingleSelection) -> None:
        super().__init__()
        self.setObjectName("ImageList")
        self.setAcceptDrops(True)
        self.setSelectionMode(selection_mode)
        self.setSpacing(SPACE_4)
        self.setUniformItemSizes(True)

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


class FileRowWidget(QWidget):
    """A file row; `delete_requested` carries the row's key."""

    delete_requested = Signal(str)

    def __init__(
        self,
        key: str,
        title: str,
        detail: str,
        thumbnail: QPixmap,
        *,
        tooltip: str | None = None,
        delete_tooltip: str = "Remove file",
    ) -> None:
        super().__init__()
        self.setObjectName("ImageRow")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.key = key

        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE_8, SPACE_4, SPACE_8, SPACE_4)
        layout.setSpacing(SPACE_8)

        self.thumbnail_label = QLabel()
        self.thumbnail_label.setObjectName("RowThumbnail")
        self.thumbnail_label.setFixedSize(ROW_THUMBNAIL, ROW_THUMBNAIL)
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setPixmap(thumbnail)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(SPACE_4)
        self.title_label = ElidedLabel(title)
        self.title_label.setObjectName("ImageName")
        self.title_label.setToolTip(tooltip or title)
        self.detail_label = QLabel(detail)
        self.detail_label.setObjectName("ImageDimensions")
        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.detail_label)

        self.delete_button = QPushButton()
        self.delete_button.setObjectName("IconButton")
        self.delete_button.setToolTip(delete_tooltip)
        self.delete_button.setFixedSize(MIN_TARGET, MIN_TARGET)
        self.delete_button.setIcon(icons.icon("trash-2", TEXT_SECONDARY, ICON_DELETE))
        self.delete_button.setIconSize(icons.icon_size(ICON_DELETE))
        self.delete_button.clicked.connect(lambda: self.delete_requested.emit(self.key))

        layout.addWidget(self.thumbnail_label)
        layout.addLayout(text_layout, 1)
        layout.addWidget(self.delete_button, alignment=Qt.AlignVCenter)

    def set_thumbnail(self, pixmap: QPixmap) -> None:
        self.thumbnail_label.setPixmap(pixmap)

    def set_detail(self, text: str) -> None:
        self.detail_label.setText(text)


def row_placeholder(icon_name: str, colour: str = TEXT_SECONDARY) -> QPixmap:
    """Row-thumbnail-sized pixmap with a small centred icon (loading or failed state)."""
    canvas = QPixmap(ROW_THUMBNAIL_IMAGE, ROW_THUMBNAIL_IMAGE)
    canvas.fill(Qt.transparent)
    painter = QPainter(canvas)
    offset = (ROW_THUMBNAIL_IMAGE - PLACEHOLDER_ICON) // 2
    icons.icon(icon_name, colour, PLACEHOLDER_ICON).paint(
        painter, QRect(offset, offset, PLACEHOLDER_ICON, PLACEHOLDER_ICON)
    )
    painter.end()
    return canvas


def row_thumbnail(source: QPixmap) -> QPixmap:
    return source.scaled(ROW_THUMBNAIL_IMAGE, ROW_THUMBNAIL_IMAGE, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def file_size_text(size_bytes: int) -> str:
    megabytes = size_bytes / (1024 * 1024)
    return f"{megabytes:.1f} MB" if megabytes >= 0.1 else "under 0.1 MB"
