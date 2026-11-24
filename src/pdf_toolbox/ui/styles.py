"""Application stylesheet, generated entirely from ui/tokens.py."""
from __future__ import annotations

from pdf_toolbox.ui import tokens as T
from pdf_toolbox.ui.icons import stylesheet_svg_path


def _font(style: T.TextStyle) -> str:
    return f"font-size: {style.size}px; font-weight: {style.weight};"


def _px(value: float) -> str:
    return f"{value:g}px"


def build_app_style() -> str:
    border = 1
    ring = T.FOCUS_RING_WIDTH
    selected_border = _px(T.SELECTED_BORDER_WIDTH)
    # Buttons/inputs keep a constant outer height: min-height covers the content box, so the
    # border width is subtracted, and the focus state trades 1px of padding for the wider ring.
    control_min = T.CONTROL_HEIGHT - 2 * border
    control_min_focus = T.CONTROL_HEIGHT - 2 * ring
    pad_x = T.SPACE_16
    pad_x_focus = pad_x - (ring - border)
    input_pad_x = T.SPACE_12
    input_pad_x_focus = input_pad_x - (ring - border)
    chevron_down = stylesheet_svg_path("chevron-down", T.TEXT_SECONDARY)
    chevron_up = stylesheet_svg_path("chevron-up", T.TEXT_SECONDARY)
    chevron_disabled = stylesheet_svg_path("chevron-down", T.DISABLED_TEXT)

    return f"""
/* ---------- base ---------- */
QMainWindow, QWidget#Root {{
    background: {T.PAGE_BG};
    color: {T.TEXT};
    font-family: {T.FONT_FAMILY_CSS};
    {_font(T.TYPE_BODY)}
}}

QLabel {{
    color: {T.TEXT};
}}

QLabel#PageTitle {{
    color: {T.TEXT};
    {_font(T.TYPE_PAGE_TITLE)}
}}

QLabel#PanelHeading,
QLabel#DropTitle {{
    color: {T.TEXT};
    {_font(T.TYPE_SECTION_TITLE)}
    background: transparent;
    border: none;
}}

QLabel#FieldLabel {{
    color: {T.TEXT_SECONDARY};
    {_font(T.TYPE_FIELD_LABEL)}
}}

QLabel#SubtleText,
QLabel#StatusText {{
    color: {T.TEXT_SECONDARY};
    {_font(T.TYPE_BODY)}
    background: transparent;
    border: none;
}}

QLabel#CardTitle {{
    color: {T.TEXT};
    {_font(T.TYPE_SECTION_TITLE)}
}}

QLabel#EmptyCaption {{
    color: {T.TEXT_SECONDARY};
    {_font(T.TYPE_CAPTION)}
    background: transparent;
    border: none;
}}

QLabel#CardMeta,
QLabel#ImageDimensions {{
    color: {T.TEXT_SECONDARY};
    {_font(T.TYPE_CAPTION)}
}}

QLabel#ImageName,
QLabel#EditingLabel {{
    color: {T.TEXT};
    {_font(T.TYPE_BODY_STRONG)}
}}

QLabel#FieldHint {{
    color: {T.TEXT_SECONDARY};
    {_font(T.TYPE_CAPTION)}
}}

QLabel#ImageOrderNumber {{
    color: {T.TEXT_SECONDARY};
    {_font(T.TYPE_FIELD_LABEL)}
}}

QLabel#RowThumbnail {{
    background: {T.PAGE_BG};
    border: {border}px solid {T.HAIRLINE};
    border-radius: {T.RADIUS_CONTROL}px;
}}

/* ---------- sidebar ---------- */
QFrame#Sidebar {{
    background: {T.CARD_BG};
    border-right: {border}px solid {T.HAIRLINE};
}}

QLabel#SidebarTitle {{
    color: {T.TEXT};
    {_font(T.TYPE_SECTION_TITLE)}
}}

QPushButton#NavButton {{
    background: transparent;
    color: {T.TEXT};
    {_font(T.TYPE_BUTTON)}
    text-align: left;
    border: {border}px solid transparent;
    border-radius: {T.RADIUS_CONTROL}px;
    min-height: {T.SIDEBAR_ITEM_HEIGHT - 2 * border}px;
    padding: 0px {T.SPACE_12}px;
}}

QPushButton#NavButton:hover {{
    background: {T.PAGE_BG};
}}

QPushButton#NavButton:checked {{
    background: {T.PRIMARY_TINT};
    color: {T.PRIMARY};
    font-weight: 600;
}}

QPushButton#NavButton:focus {{
    border: {ring}px solid {T.PRIMARY};
    min-height: {T.SIDEBAR_ITEM_HEIGHT - 2 * ring}px;
    padding: 0px {T.SPACE_12 - (ring - border)}px;
}}

/* ---------- buttons ---------- */
QPushButton {{
    background: {T.CARD_BG};
    color: {T.TEXT};
    {_font(T.TYPE_BUTTON)}
    border: {border}px solid {T.BORDER};
    border-radius: {T.RADIUS_CONTROL}px;
    min-height: {control_min}px;
    padding: 0px {pad_x}px;
}}

QPushButton:hover {{
    background: {T.PAGE_BG};
    border-color: {T.TEXT_SECONDARY};
}}

QPushButton:pressed {{
    background: {T.HAIRLINE};
}}

QPushButton:focus {{
    border: {ring}px solid {T.PRIMARY};
    min-height: {control_min_focus}px;
    padding: 0px {pad_x_focus}px;
}}

QPushButton:disabled {{
    background: {T.DISABLED_BG};
    color: {T.DISABLED_TEXT};
    border-color: {T.DISABLED_BG};
}}

QPushButton#PrimaryButton {{
    background: {T.PRIMARY};
    color: {T.ON_PRIMARY};
    border-color: {T.PRIMARY};
}}

QPushButton#PrimaryButton:hover {{
    background: {T.PRIMARY_HOVER};
    border-color: {T.PRIMARY_HOVER};
}}

QPushButton#PrimaryButton:pressed {{
    background: {T.PRIMARY_PRESSED};
    border-color: {T.PRIMARY_PRESSED};
}}

QPushButton#PrimaryButton:focus {{
    border-color: {T.PRIMARY_PRESSED};
}}

QPushButton#PrimaryButton:disabled {{
    background: {T.DISABLED_BG};
    color: {T.DISABLED_TEXT};
    border-color: {T.DISABLED_BG};
}}

QPushButton#SecondaryActionButton {{
    background: {T.CARD_BG};
    color: {T.TEXT};
}}

QPushButton#PresetButton:checked {{
    background: {T.PRIMARY_TINT};
    color: {T.PRIMARY};
    border: {selected_border} solid {T.PRIMARY};
    font-weight: 700;
}}

QPushButton#PresetButton:checked:focus {{
    border: {ring}px solid {T.PRIMARY};
}}

QPushButton#IconButton {{
    background: transparent;
    border: {border}px solid transparent;
    min-height: {T.MIN_TARGET - 2 * border}px;
    min-width: {T.MIN_TARGET - 2 * border}px;
    padding: 0px;
}}

QPushButton#IconButton:hover {{
    background: {T.DANGER_BG};
    border-color: {T.DANGER_BG};
}}

QPushButton#IconButton:focus {{
    border: {ring}px solid {T.PRIMARY};
    min-height: {T.MIN_TARGET - 2 * ring}px;
    min-width: {T.MIN_TARGET - 2 * ring}px;
}}

/* ---------- inputs ---------- */
QLineEdit {{
    background: {T.CARD_BG};
    color: {T.TEXT};
    {_font(T.TYPE_BODY)}
    border: {border}px solid {T.BORDER};
    border-radius: {T.RADIUS_CONTROL}px;
    min-height: {control_min}px;
    padding: 0px {input_pad_x}px;
    selection-background-color: {T.PRIMARY_TINT};
    selection-color: {T.TEXT};
}}

QLineEdit:focus {{
    border: {ring}px solid {T.PRIMARY};
    min-height: {control_min_focus}px;
    padding: 0px {input_pad_x_focus}px;
}}

QLineEdit:read-only {{
    background: {T.PAGE_BG};
}}

QLineEdit:disabled {{
    background: {T.DISABLED_BG};
    color: {T.DISABLED_TEXT};
    border-color: {T.DISABLED_BG};
}}

/* ---------- combo boxes ---------- */
QComboBox {{
    background: {T.CARD_BG};
    color: {T.TEXT};
    {_font(T.TYPE_BODY)}
    border: {border}px solid {T.BORDER};
    border-radius: {T.RADIUS_CONTROL}px;
    min-height: {control_min}px;
    padding: 0px {T.SPACE_32 + T.SPACE_4}px 0px {input_pad_x}px;
}}

QComboBox:hover {{
    border-color: {T.TEXT_SECONDARY};
}}

QComboBox:focus,
QComboBox:on {{
    border: {ring}px solid {T.PRIMARY};
    min-height: {control_min_focus}px;
    padding: 0px {T.SPACE_32 + T.SPACE_4 - (ring - border)}px 0px {input_pad_x_focus}px;
}}

QComboBox:disabled {{
    background: {T.DISABLED_BG};
    color: {T.DISABLED_TEXT};
    border-color: {T.DISABLED_BG};
}}

QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: {T.SPACE_32}px;
    border: none;
    background: transparent;
}}

QComboBox::down-arrow {{
    image: url("{chevron_down}");
    width: {T.ICON_INLINE}px;
    height: {T.ICON_INLINE}px;
}}

QComboBox::down-arrow:on {{
    image: url("{chevron_up}");
}}

QComboBox::down-arrow:disabled {{
    image: url("{chevron_disabled}");
}}

QComboBox QAbstractItemView,
QListView#ComboPopup {{
    background: {T.CARD_BG};
    color: {T.TEXT};
    border: {border}px solid {T.BORDER};
    border-radius: {T.RADIUS_CONTROL}px;
    padding: {T.SPACE_4}px;
    outline: 0px;
    selection-background-color: {T.PRIMARY_TINT};
    selection-color: {T.TEXT};
}}

QComboBox QAbstractItemView::item,
QListView#ComboPopup::item {{
    min-height: {T.COMBO_ITEM_HEIGHT}px;
    padding: 0px {T.SPACE_12}px;
    border-radius: {T.RADIUS_CONTROL - 2}px;
    color: {T.TEXT};
    background: transparent;
}}

QComboBox QAbstractItemView::item:hover,
QListView#ComboPopup::item:hover,
QComboBox QAbstractItemView::item:selected,
QListView#ComboPopup::item:selected {{
    background: {T.PRIMARY_TINT};
    color: {T.TEXT};
}}

/* ---------- lists and selection ---------- */
QListWidget#ImageList,
QListWidget#OrganizerPageGrid {{
    background: {T.CARD_BG};
    border: {border}px solid {T.HAIRLINE};
    border-radius: {T.RADIUS_CARD}px;
    outline: 0px;
    padding: {T.SPACE_8}px;
    color: {T.TEXT};
}}

QListWidget#ImageList:focus,
QListWidget#OrganizerPageGrid:focus {{
    border-color: {T.PRIMARY};
}}

QListWidget#ImageList::item {{
    border: {selected_border} solid transparent;
    border-radius: {T.RADIUS_CONTROL}px;
    color: {T.TEXT};
}}

QListWidget#ImageList::item:hover:!selected {{
    background: {T.PAGE_BG};
}}

QListWidget#ImageList::item:selected {{
    background: {T.PRIMARY_TINT};
    border: {selected_border} solid {T.PRIMARY};
    color: {T.TEXT};
}}

/* Organizer grid cells are wider than their cards; the card itself shows hover and selection. */
QListWidget#OrganizerPageGrid::item,
QListWidget#OrganizerPageGrid::item:hover,
QListWidget#OrganizerPageGrid::item:selected {{
    background: transparent;
    border: none;
    color: {T.TEXT};
}}

QListWidget#ImageList[dropActive="true"],
QListWidget#OrganizerPageGrid[dropActive="true"],
QFrame#DropArea[dropActive="true"] {{
    background: {T.PRIMARY_TINT};
    border-color: {T.PRIMARY};
}}

QWidget#ImageRow {{
    background: transparent;
}}

QFrame#OrganizerPageCard {{
    background: {T.CARD_BG};
    border: {selected_border} solid {T.HAIRLINE};
    border-radius: {T.RADIUS_CARD}px;
}}

QFrame#OrganizerPageCard[selected="true"] {{
    background: {T.PRIMARY_TINT};
    border: {selected_border} solid {T.PRIMARY};
}}

QLabel#OrganizerCardTitle {{
    color: {T.TEXT};
    {_font(T.TYPE_BODY_STRONG)}
    background: transparent;
}}

QLabel#OrganizerCardThumbnail {{
    background: transparent;
}}

/* Trash button floating over the thumbnail; only shown on hover or selection. */
QPushButton#CardDeleteButton {{
    background: {T.CARD_BG};
    border: {border}px solid {T.BORDER};
    border-radius: {T.RADIUS_CONTROL}px;
    min-height: {T.MIN_TARGET - 2 * border}px;
    min-width: {T.MIN_TARGET - 2 * border}px;
    padding: 0px;
}}

QPushButton#CardDeleteButton:hover {{
    background: {T.DANGER_BG};
    border-color: {T.DANGER_TEXT};
}}

QPushButton#CardDeleteButton:focus {{
    border: {ring}px solid {T.PRIMARY};
    min-height: {T.MIN_TARGET - 2 * ring}px;
    min-width: {T.MIN_TARGET - 2 * ring}px;
}}

/* Clear: available but visually quiet next to the editing tools. */
QPushButton#QuietButton {{
    background: transparent;
    border-color: transparent;
    color: {T.TEXT_SECONDARY};
}}

QPushButton#QuietButton:hover {{
    background: {T.PAGE_BG};
    border-color: {T.BORDER};
    color: {T.TEXT};
}}

QPushButton#QuietButton:disabled {{
    background: transparent;
    border-color: transparent;
    color: {T.DISABLED_TEXT};
}}

/* ---------- thumbnail size slider ---------- */
QSlider#SizeSlider {{
    background: transparent;
    min-height: 24px;
}}

QSlider#SizeSlider::groove:horizontal {{
    height: 6px;
    margin: 0px;
    background: {T.HAIRLINE};
    border: none;
    border-radius: 3px;
}}

/* Qt paints sub-page/add-page at the slider's full height, so the 6px groove alone is the track. */
QSlider#SizeSlider::sub-page:horizontal,
QSlider#SizeSlider::add-page:horizontal {{
    background: transparent;
    border: none;
}}

QSlider#SizeSlider::handle:horizontal {{
    background: {T.CARD_BG};
    border: {ring}px solid {T.PRIMARY};
    width: 16px;
    height: 16px;
    margin: -7px 0px;
    border-radius: 10px;
}}

QSlider#SizeSlider::handle:horizontal:hover {{
    background: {T.PRIMARY_TINT};
}}

QSlider#SizeSlider::handle:horizontal:focus {{
    background: {T.PRIMARY_TINT};
    border-color: {T.PRIMARY_PRESSED};
}}

QSlider#SizeSlider::handle:horizontal:disabled {{
    border-color: {T.BORDER};
}}

QPushButton#SizeStepButton {{
    background: transparent;
    border: {border}px solid transparent;
    color: {T.TEXT_SECONDARY};
    {_font(T.TYPE_CAPTION)}
    min-height: {T.line_height(T.TYPE_CAPTION) + T.SPACE_4}px;
    padding: 0px {T.SPACE_4}px;
}}

QPushButton#SizeStepButton:hover {{
    color: {T.TEXT};
    background: {T.PAGE_BG};
}}

QPushButton#SizeStepButton:checked {{
    color: {T.PRIMARY};
    font-weight: 700;
}}

/* ---------- panels ---------- */
QFrame#DropArea {{
    background: {T.CARD_BG};
    border: {border}px dashed {T.BORDER};
    border-radius: {T.RADIUS_CARD}px;
}}

QFrame#SettingsPanel,
QWidget#PreviewWidget {{
    background: {T.CARD_BG};
    border: {border}px solid {T.HAIRLINE};
    border-radius: {T.RADIUS_CARD}px;
}}

QFrame#CorrectionsPanel {{
    background: transparent;
    border: none;
}}

QScrollArea#SettingsScroll {{
    background: transparent;
    border: none;
}}

QScrollArea#SettingsScroll > QWidget > QWidget,
QWidget#SettingsBody,
QWidget#JobFooter,
QWidget#EmptyState,
QWidget#EmptyStateGroup,
QWidget#FormatBadges {{
    background: transparent;
}}

/* pinned footer of the settings card: a hairline separates it from the scrolling body */
QWidget#SettingsFooter {{
    background: transparent;
    border-top: {border}px solid {T.HAIRLINE};
}}

/* ---------- status line (borderless, semantic colour) ---------- */
QWidget#StatusLine,
QLabel#StatusIcon {{
    background: transparent;
    border: none;
}}

QLabel#StatusText[kind="success"] {{
    color: {T.SUCCESS_TEXT};
}}

QLabel#StatusText[kind="warning"] {{
    color: {T.WARNING_TEXT};
}}

QLabel#StatusText[kind="error"] {{
    color: {T.DANGER_TEXT};
    font-weight: 600;
}}

QFrame#Divider {{
    color: {T.HAIRLINE};
    background: {T.HAIRLINE};
}}

/* ---------- progress ---------- */
QProgressBar {{
    background: {T.HAIRLINE};
    border: none;
    border-radius: {T.PROGRESS_HEIGHT // 2}px;
    min-height: {T.PROGRESS_HEIGHT}px;
    max-height: {T.PROGRESS_HEIGHT}px;
}}

QProgressBar::chunk {{
    background: {T.PRIMARY};
    border-radius: {T.PROGRESS_HEIGHT // 2}px;
}}

/* ---------- tooltips ---------- */
QToolTip {{
    background: {T.TEXT};
    color: {T.CARD_BG};
    border: none;
    padding: {T.SPACE_8}px {T.SPACE_12}px;
    {_font(T.TYPE_BODY)}
}}

/* ---------- scrollbars ---------- */
QScrollBar:vertical {{
    background: transparent;
    width: {T.SCROLLBAR_WIDTH}px;
    margin: {T.SPACE_4}px 0px;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: {T.SCROLLBAR_WIDTH}px;
    margin: 0px {T.SPACE_4}px;
}}

QScrollBar::handle:vertical {{
    background: {T.BORDER};
    border-radius: {T.SCROLLBAR_WIDTH // 2}px;
    min-height: {T.SPACE_32}px;
}}

QScrollBar::handle:horizontal {{
    background: {T.BORDER};
    border-radius: {T.SCROLLBAR_WIDTH // 2}px;
    min-width: {T.SPACE_32}px;
}}

QScrollBar::handle:vertical:hover,
QScrollBar::handle:horizontal:hover,
QScrollBar::handle:vertical:pressed,
QScrollBar::handle:horizontal:pressed {{
    background: {T.TEXT_SECONDARY};
}}

QScrollBar::add-line,
QScrollBar::sub-line {{
    width: 0px;
    height: 0px;
    border: none;
    background: none;
}}

QScrollBar::add-page,
QScrollBar::sub-page {{
    background: none;
}}
"""
