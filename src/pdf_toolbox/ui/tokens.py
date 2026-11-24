"""Design tokens: the single source for colours, type, spacing, radii and control sizes.

All sizes are logical pixels. Qt's own high-DPI scaling turns them into device pixels,
so nothing here is multiplied by a custom factor.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache


# ---------------------------------------------------------------- colours (palette A)
PRIMARY = "#2563EB"
PRIMARY_HOVER = "#1D4ED8"
PRIMARY_PRESSED = "#1E40AF"
ON_PRIMARY = "#FFFFFF"
PRIMARY_TINT = "#E8F0FE"  # selected rows, selected navigation

PAGE_BG = "#F6F8FB"
CARD_BG = "#FFFFFF"
TEXT = "#1F2937"
TEXT_SECONDARY = "#5B6472"
BORDER = "#CBD2DC"
HAIRLINE = "#E3E7EE"
DISABLED_BG = "#EEF0F3"
DISABLED_TEXT = "#5B6472"

SUCCESS_BG = "#E7F6EC"
SUCCESS_TEXT = "#166534"
WARNING_BG = "#FEF3E2"
WARNING_TEXT = "#8A4B08"
DANGER_BG = "#FDECEC"
DANGER_TEXT = "#B91C1C"

SHADOW_RGBA = (0, 0, 0, 14)  # soft drop shadow under page thumbnails


@dataclass(frozen=True)
class BadgeColours:
    text: str
    fill: str
    border: str  # a slightly darker tint of the fill


# Format badges (Convert to JPG empty state): text-on-fill contrast >= 4.5:1
# (HEIC 5.85, WebP 6.38, PNG 6.66).
BADGE_HEIC = BadgeColours(text=PRIMARY_HOVER, fill=PRIMARY_TINT, border="#BFD2FB")
BADGE_WEBP = BadgeColours(text=SUCCESS_TEXT, fill=SUCCESS_BG, border="#BEE3C9")
BADGE_PNG = BadgeColours(text="#9A3412", fill=WARNING_BG, border="#F6D3A8")



# ---------------------------------------------------------------- type
FONT_FAMILY_NAME = "Segoe UI"
FONT_FAMILY_CSS = '"Segoe UI", Arial, sans-serif'
MIN_TEXT_PX = 12


@dataclass(frozen=True)
class TextStyle:
    size: int  # logical px
    weight: int  # CSS weight


TYPE_PAGE_TITLE = TextStyle(24, 600)
TYPE_SECTION_TITLE = TextStyle(16, 600)
TYPE_BODY = TextStyle(14, 400)
TYPE_BODY_STRONG = TextStyle(14, 600)  # body size, emphasised (file names)
TYPE_FIELD_LABEL = TextStyle(13, 500)
TYPE_CAPTION = TextStyle(12, 400)
TYPE_BUTTON = TextStyle(14, 500)
TYPE_BADGE = TextStyle(28, 700)  # large format name on a coloured badge


# ---------------------------------------------------------------- spacing, radius, sizes
SPACE_4 = 4
SPACE_8 = 8
SPACE_12 = 12
SPACE_16 = 16
SPACE_24 = 24
SPACE_32 = 32

RADIUS_CONTROL = 8
RADIUS_CARD = 12

CONTROL_HEIGHT = 40  # buttons, inputs, combos
SIDEBAR_ITEM_HEIGHT = 44
MIN_TARGET = 36  # smallest clickable target
FOCUS_RING_WIDTH = 2
SELECTED_BORDER_WIDTH = 1.5
COMBO_ITEM_HEIGHT = 36
SCROLLBAR_WIDTH = 10
PROGRESS_HEIGHT = 10

ICON_SIDEBAR = 20
ICON_INLINE = 16  # chevrons
ICON_DELETE = 18


# ---------------------------------------------------------------- font metrics helpers
def qfont(style: TextStyle):
    """QFont matching a text style (requires a QGuiApplication)."""
    from PySide6.QtGui import QFont

    font = QFont(FONT_FAMILY_NAME)
    font.setPixelSize(style.size)
    font.setWeight(QFont.Weight(style.weight))
    return font


@lru_cache(maxsize=None)
def line_height(style: TextStyle) -> int:
    """Height of one text line in this style, from font metrics (requires a QGuiApplication)."""
    from PySide6.QtGui import QFontMetrics

    return QFontMetrics(qfont(style)).height()


@lru_cache(maxsize=None)
def text_width(style: TextStyle, text: str) -> int:
    from PySide6.QtGui import QFontMetrics

    return QFontMetrics(qfont(style)).horizontalAdvance(text)


# ---------------------------------------------------------------- contrast
def relative_luminance(hex_colour: str) -> float:
    value = hex_colour.lstrip("#")
    channels = [int(value[index : index + 2], 16) / 255 for index in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(foreground: str, background: str) -> float:
    lighter, darker = sorted((relative_luminance(foreground), relative_luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)
