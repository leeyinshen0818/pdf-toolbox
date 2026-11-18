"""Sizes of text-bearing widgets, derived from font metrics plus token padding.

These need a QGuiApplication, so they are functions (evaluated when widgets are built),
not module-level constants.
"""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QSize

from pdf_toolbox.ui import tokens as T


# Plain layout constants (logical px); not text-bearing.
ROW_THUMBNAIL = 58  # thumbnail box in Image->PDF and HEIC rows
ROW_THUMBNAIL_IMAGE = 54  # pixmap drawn inside that box
CARD_WIDTH = 190
CARD_THUMBNAIL = QSize(136, 176)
PAGE_THUMBNAIL_ICON = QSize(140, 180)
PAGE_THUMBNAIL_IMAGE = QSize(122, 158)
PAGE_THUMBNAIL_ITEM_WIDTH = 184


@lru_cache(maxsize=None)
def file_row_height() -> int:
    """Image->PDF / HEIC list row: thumbnail beside a file name and a caption line."""
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


@lru_cache(maxsize=None)
def organizer_card_size() -> QSize:
    """Organizer page card: header (title + delete button), thumbnail, three caption lines."""
    header = max(T.line_height(T.TYPE_SECTION_TITLE), T.MIN_TARGET)
    captions = 3 * caption_label_height()
    spacing = 4 * T.SPACE_4  # between header, thumbnail and the three caption lines
    margins = 2 * T.SPACE_8
    border = 2 * 2  # selected border (1.5px) rounded up on each side
    height = header + CARD_THUMBNAIL.height() + captions + spacing + margins + border
    return QSize(CARD_WIDTH, height)


@lru_cache(maxsize=None)
def page_thumbnail_item_size() -> QSize:
    """PDF->Image page tile: icon above two body-text lines (file name, page number)."""
    text = 2 * T.line_height(T.TYPE_BODY)
    height = PAGE_THUMBNAIL_ICON.height() + T.SPACE_4 + text + 2 * T.SPACE_8
    return QSize(PAGE_THUMBNAIL_ITEM_WIDTH, height)
