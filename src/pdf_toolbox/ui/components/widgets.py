"""Small shared widgets and helpers: elided labels, enum combos, labelled fields,
page-thumbnail placeholders and the default output folder."""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QSize, QStandardPaths, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QComboBox, QLabel, QSizePolicy, QStyledItemDelegate, QVBoxLayout, QWidget

from pdf_toolbox.core.pdf_to_image import JpgQuality
from pdf_toolbox.ui.tokens import BORDER, CARD_BG, CONTROL_HEIGHT, PAGE_BG, SHADOW_RGBA, SPACE_4, TEXT_SECONDARY


# Plain-language JPG quality labels (best first); the underlying JpgQuality values are unchanged.
JPG_QUALITY_CHOICES = (
    (JpgQuality.MAXIMUM, "Best quality"),
    (JpgQuality.HIGH, "Balanced"),
    (JpgQuality.STANDARD, "Smaller file"),
)


class ElidedLabel(QLabel):
    """Single-line label that elides in the middle and shows the full text as a tooltip."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.full_text = text
        self.setToolTip(text)
        self.setText(text)

    def set_full_text(self, text: str) -> None:
        self.full_text = text
        self.setToolTip(text)
        self._refresh_text()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh_text()

    def _refresh_text(self) -> None:
        available_width = max(24, self.width())
        self.setText(self.fontMetrics().elidedText(self.full_text, Qt.ElideMiddle, available_width))


def enum_combo(
    enum_type: type[Enum],
    *,
    min_contents_length: int | None = None,
    popup_min_width: int = 300,
    choices: Sequence[tuple[Enum, str]] | None = None,
) -> QComboBox:
    """Combo listing an Enum's values (data is always the value).

    The shown text is the value, unless `choices` gives (member, label) pairs, which also set
    the order; use it for plain-language labels without changing the underlying values.
    """
    combo = QComboBox()
    combo.setMinimumHeight(CONTROL_HEIGHT)
    combo.setMinimumWidth(260)
    combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    if min_contents_length is not None:
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(min_contents_length)
    for item, label in choices if choices is not None else [(item, item.value) for item in enum_type]:
        combo.addItem(label, item.value)
    # The default combo delegate ignores item stylesheets; this one honours the 36px rows.
    combo.setItemDelegate(QStyledItemDelegate(combo))
    combo.view().setObjectName("ComboPopup")
    combo.view().setMinimumWidth(popup_min_width)
    return combo


def labeled_control(label: str, control: QWidget) -> QVBoxLayout:
    layout = QVBoxLayout()
    layout.setSpacing(SPACE_4)
    text = QLabel(label)
    text.setObjectName("FieldLabel")
    layout.addWidget(text)
    layout.addWidget(control)
    return layout


def thumbnail_placeholder(text: str, size: QSize) -> QPixmap:
    """Blank page drawing with a caption, shown while a page thumbnail loads or when it fails."""
    canvas = QPixmap(size)
    canvas.fill(QColor(CARD_BG))
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.fillRect(canvas.rect(), QColor(PAGE_BG))
    page_rect = canvas.rect().adjusted(12, 10, -12, -10)
    painter.fillRect(page_rect.adjusted(3, 3, 3, 3), QColor(*SHADOW_RGBA))
    painter.fillRect(page_rect, QColor(CARD_BG))
    painter.setPen(QPen(QColor(BORDER), 1))
    painter.drawRect(page_rect)
    painter.setPen(QColor(TEXT_SECONDARY))
    painter.drawText(page_rect, Qt.AlignCenter, text)
    painter.end()
    return canvas


def default_output_folder() -> Path:
    """The user's Pictures folder, or their home folder if Pictures is unavailable."""
    pictures = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)
    if pictures:
        path = Path(pictures)
        if path.exists():
            return path
    return Path.home()
