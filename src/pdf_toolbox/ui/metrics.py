"""Sizes of text-bearing widgets, derived from font metrics plus token padding.

These need a QGuiApplication, so they are functions (evaluated when widgets are built),
not module-level constants.
"""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QSize

from pdf_toolbox.core.organizer_preferences import ThumbnailSize
from pdf_toolbox.ui import tokens as T


# Plain layout constants (logical px); not text-bearing.
ROW_THUMBNAIL = 58  # thumbnail box in Image->PDF and Convert to JPG rows
ROW_THUMBNAIL_IMAGE = 54  # pixmap drawn inside that box
# Organizer page thumbnails (logical px), one box per thumbnail size; roughly A4 proportions.
ORGANIZER_THUMBNAIL_BOXES = {
    ThumbnailSize.SMALL: QSize(104, 136),
    ThumbnailSize.MEDIUM: QSize(144, 188),
    ThumbnailSize.LARGE: QSize(200, 262),
}
CARD_THUMBNAIL = ORGANIZER_THUMBNAIL_BOXES[ThumbnailSize.MEDIUM]
ORGANIZER_CARD_GAP = T.SPACE_12  # at least this much space between cards
ORGANIZER_CARD_PADDING = T.SPACE_8
PAGE_THUMBNAIL_ICON = QSize(140, 180)
PAGE_THUMBNAIL_IMAGE = QSize(122, 158)
PAGE_THUMBNAIL_ITEM_WIDTH = 184


@lru_cache(maxsize=None)
def file_row_height() -> int:
    """Image->PDF / Convert to JPG list row: thumbnail beside a file name and a caption line."""
    text = T.line_height(T.TYPE_BODY_STRONG) + T.SPACE_4 + T.line_height(T.TYPE_CAPTION)
    return max(ROW_THUMBNAIL, text, T.MIN_TARGET) + 2 * T.SPACE_8


def file_row_size_hint() -> QSize:
    return QSize(300, file_row_height())


@lru_cache(maxsize=None)
def order_number_width() -> int:
    return T.text_width(T.TYPE_FIELD_LABEL, "000") + T.SPACE_8


@lru_cache(maxsize=None)
def caption_label_height() -> int:
    return T.line_height(T.TYPE_CAPTION)


def organizer_thumbnail_box(size: ThumbnailSize = ThumbnailSize.MEDIUM) -> QSize:
    return ORGANIZER_THUMBNAIL_BOXES[ThumbnailSize(size)]


@lru_cache(maxsize=None)
def organizer_card_size(size: ThumbnailSize = ThumbnailSize.MEDIUM) -> QSize:
    """Organizer page card: thumbnail on top, then "Page N" (body strong) and one caption line."""
    box = organizer_thumbnail_box(size)
    border = 2 * 2  # selected border (1.5px) rounded up on each side
    text = T.line_height(T.TYPE_BODY_STRONG) + T.SPACE_4 + caption_label_height()
    width = box.width() + 2 * ORGANIZER_CARD_PADDING + border
    height = 2 * ORGANIZER_CARD_PADDING + box.height() + T.SPACE_8 + text + border
    return QSize(width, height)


@lru_cache(maxsize=None)
def page_thumbnail_item_size() -> QSize:
    """PDF->Image page tile: icon above two body-text lines (file name, page number)."""
    text = 2 * T.line_height(T.TYPE_BODY)
    height = PAGE_THUMBNAIL_ICON.height() + T.SPACE_4 + text + 2 * T.SPACE_8
    return QSize(PAGE_THUMBNAIL_ITEM_WIDTH, height)
