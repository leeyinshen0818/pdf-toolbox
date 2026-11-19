"""PDF Organizer choices remembered between launches (thumbnail size)."""
from __future__ import annotations

from enum import Enum

from pdf_toolbox.core.stored_enums import enum_or_default


class ThumbnailSize(str, Enum):
    SMALL = "Small"
    MEDIUM = "Medium"
    LARGE = "Large"


THUMBNAIL_SIZE_KEY = "pdf_organizer/thumbnail_size"
DEFAULT_THUMBNAIL_SIZE = ThumbnailSize.MEDIUM

# Render resolution per size: roughly twice the on-screen height of an A4 page at each size,
# so thumbnails stay sharp on 200% displays without rendering far more pixels than shown.
THUMBNAIL_DPI = {
    ThumbnailSize.SMALL: 36,
    ThumbnailSize.MEDIUM: 54,
    ThumbnailSize.LARGE: 72,
}


def thumbnail_size_to_value(size: ThumbnailSize) -> str:
    return ThumbnailSize(size).name


def thumbnail_size_from_value(raw: object) -> ThumbnailSize:
    return enum_or_default(ThumbnailSize, raw, DEFAULT_THUMBNAIL_SIZE)
