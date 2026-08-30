from __future__ import annotations


def px(value: int | float, scale: float, *, minimum: int = 1) -> int:
    return max(minimum, round(float(value) * scale))


def build_app_style(scale: float = 1.0) -> str:
    style = """
QMainWindow, QWidget#Root {
    background: #f6f7f9;
    color: #1f2328;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: {px(13, scale, minimum=9)}px;
}

QFrame#Sidebar {
    background: #ffffff;
    border-right: 1px solid #e2e6ec;
}

QLabel#SidebarTitle {
    color: #1f2328;
    font-size: {px(17, scale, minimum=11)}px;
    font-weight: 700;
}

QPushButton#NavButton {
    border: 1px solid transparent;
    border-radius: 6px;
    color: #2f3742;
    padding: {px(9, scale)}px {px(10, scale)}px;
    text-align: left;
    background: transparent;
}

QPushButton#NavButton:checked {
    background: #eaf1fb;
    border-color: #d6e3f4;
    color: #163b66;
    font-weight: 600;
}

QPushButton#NavButton:disabled {
    color: #9aa3af;
    background: transparent;
}

QPushButton {
    border: 1px solid #d0d7de;
    border-radius: 6px;
    background: #ffffff;
    color: #24292f;
    min-height: {px(34, scale, minimum=24)}px;
    padding: {px(7, scale, minimum=4)}px {px(11, scale, minimum=7)}px;
}

QPushButton:hover:enabled {
    background: #f3f6fa;
    border-color: #b9c4d0;
}

QPushButton:pressed:enabled {
    background: #e8edf3;
}

QPushButton:disabled {
    color: #9aa3af;
    background: #f1f3f6;
    border-color: #dbe1e8;
}

QPushButton#PrimaryButton {
    background: #1f4f82;
    border-color: #1f4f82;
    color: #ffffff;
    font-weight: 600;
}

QPushButton#PrimaryButton:hover:enabled {
    background: #183f69;
}

QPushButton#SecondaryActionButton {
    background: #ffffff;
    border-color: #cfd7e2;
    color: #1f2328;
    font-weight: 500;
}

QPushButton#SecondaryActionButton:hover:enabled {
    background: #f3f6fa;
    border-color: #aebaca;
}

QListWidget#ImageList {
    border: 1px solid #dfe4ea;
    border-radius: 8px;
    background: #ffffff;
    outline: 0;
}

QListWidget#ImageList[dropActive="true"],
QListWidget#PageThumbnailList[dropActive="true"],
QListWidget#OrganizerPageGrid[dropActive="true"],
QFrame#DropArea[dropActive="true"] {
    background: #f7fbff;
    border-color: #8fb3df;
}

QListWidget#PageThumbnailList {
    border: 1px solid #dfe4ea;
    border-radius: 8px;
    background: #ffffff;
    outline: 0;
    padding: {px(8, scale, minimum=4)}px;
}

QListWidget#OrganizerPageGrid {
    border: 1px solid #dfe4ea;
    border-radius: 8px;
    background: #ffffff;
    outline: 0;
    padding: {px(10, scale, minimum=5)}px;
}

QListWidget#OrganizerPageGrid::item {
    border: 1px solid transparent;
    border-radius: 8px;
    padding: {px(4, scale, minimum=2)}px;
}

QListWidget#OrganizerPageGrid::item:selected {
    background: #edf4fd;
    border: 1px solid #8fb3df;
}

QFrame#OrganizerPageCard {
    background: #ffffff;
    border: 1px solid #dfe4ea;
    border-radius: 8px;
}

QFrame#OrganizerPageCard[selected="true"] {
    background: #edf4fd;
    border-color: #8fb3df;
}

QListWidget#PageThumbnailList::item {
    border: 1px solid transparent;
    border-radius: 8px;
    padding: {px(8, scale, minimum=4)}px;
    color: #374151;
}

QListWidget#PageThumbnailList::item:selected {
    background: #edf4fd;
    border: 1px solid #8fb3df;
    color: #163b66;
}

QListWidget#ImageList::item {
    border: none;
    padding: {px(4, scale, minimum=2)}px;
}

QListWidget#ImageList::item:selected {
    background: #edf4fd;
    border-radius: 6px;
}

QListWidget#ImageList::item:hover:!selected {
    background: #f6f8fa;
    border-radius: 6px;
}

QFrame#DropArea {
    border: 1px dashed #b9c3cf;
    border-radius: 8px;
    background: #ffffff;
}

QFrame#StatusBar {
    background: #ffffff;
    border: 1px solid #e0e5eb;
    border-radius: 6px;
}

QWidget#ImageRow {
    background: transparent;
    border-radius: 6px;
}

QFrame#SettingsPanel,
QWidget#PreviewWidget {
    background: #ffffff;
    border: 1px solid #dfe4ea;
    border-radius: 8px;
}

QScrollArea#SettingsScroll {
    background: transparent;
    border: none;
}

QScrollArea#SettingsScroll > QWidget > QWidget {
    background: transparent;
}

QLabel#PanelHeading {
    color: #1f2328;
    font-size: {px(14, scale, minimum=10)}px;
    font-weight: 700;
}

QLabel#CardTitle {
    color: #1f2328;
    font-size: {px(12, scale, minimum=9)}px;
    font-weight: 700;
}

QLabel#CardMeta {
    color: #66707c;
    font-size: {px(11, scale, minimum=8)}px;
}

QLabel#FieldLabel {
    color: #4f5b67;
    font-size: {px(12, scale, minimum=9)}px;
    font-weight: 600;
}

QComboBox {
    background: #ffffff;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    color: #24292f;
    min-height: {px(34, scale, minimum=24)}px;
    padding: {px(4, scale, minimum=2)}px {px(10, scale, minimum=6)}px;
}

QComboBox QAbstractItemView,
QListView#ComboPopup {
    background: #ffffff;
    color: #24292f;
    border: 1px solid #cfd7e2;
    selection-background-color: #edf4fd;
    selection-color: #163b66;
    outline: 0;
}

QComboBox QAbstractItemView::item,
QListView#ComboPopup::item {
    min-height: {px(28, scale, minimum=20)}px;
    color: #24292f;
    padding: {px(5, scale, minimum=3)}px {px(8, scale, minimum=5)}px;
    background: #ffffff;
}

QComboBox QAbstractItemView::item:selected,
QListView#ComboPopup::item:selected {
    background: #edf4fd;
    color: #163b66;
}

QComboBox:disabled {
    color: #596575;
    background: #f1f3f6;
}

QLineEdit {
    background: #ffffff;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    color: #24292f;
    min-height: {px(34, scale, minimum=24)}px;
    padding: {px(4, scale, minimum=2)}px {px(10, scale, minimum=6)}px;
}

QLineEdit:read-only {
    background: #f8fafc;
}

QProgressBar {
    background: #eef2f6;
    border: 1px solid #d8e0ea;
    border-radius: 6px;
    min-height: {px(10, scale, minimum=7)}px;
}

QProgressBar::chunk {
    background: #1f4f82;
    border-radius: 5px;
}

QPushButton#IconButton {
    background: transparent;
    border: 1px solid transparent;
    padding: {px(4, scale, minimum=2)}px;
}

QPushButton#IconButton:hover:enabled {
    background: #f0f4f9;
    border-color: #d8e0ea;
}

QPushButton#PresetButton {
    text-align: center;
    color: #24292f;
    min-height: {px(34, scale, minimum=24)}px;
    padding: {px(8, scale, minimum=4)}px {px(8, scale, minimum=4)}px;
    background: #ffffff;
}

QPushButton#PresetButton:checked {
    background: #eaf1fb;
    border-color: #8fb3df;
    color: #163b66;
    font-weight: 600;
}

QPushButton#PresetButton:disabled {
    color: #6f7a86;
    background: #f5f7fa;
}

QFrame#Divider {
    color: #e1e6ec;
    background: #e1e6ec;
}

QLabel#ImageName {
    color: #1f2328;
    font-weight: 600;
}

QLabel#ImageOrderNumber {
    color: #536170;
    font-size: {px(12, scale, minimum=9)}px;
    font-weight: 700;
}

QLabel#ImageDimensions,
QLabel#SubtleText,
QLabel#StatusText {
    color: #66707c;
}
"""
    replacements = {
        "{px(13, scale, minimum=9)}": px(13, scale, minimum=9),
        "{px(17, scale, minimum=11)}": px(17, scale, minimum=11),
        "{px(9, scale)}": px(9, scale),
        "{px(10, scale)}": px(10, scale),
        "{px(34, scale, minimum=24)}": px(34, scale, minimum=24),
        "{px(7, scale, minimum=4)}": px(7, scale, minimum=4),
        "{px(11, scale, minimum=7)}": px(11, scale, minimum=7),
        "{px(8, scale, minimum=4)}": px(8, scale, minimum=4),
        "{px(10, scale, minimum=5)}": px(10, scale, minimum=5),
        "{px(4, scale, minimum=2)}": px(4, scale, minimum=2),
        "{px(14, scale, minimum=10)}": px(14, scale, minimum=10),
        "{px(12, scale, minimum=9)}": px(12, scale, minimum=9),
        "{px(11, scale, minimum=8)}": px(11, scale, minimum=8),
        "{px(10, scale, minimum=6)}": px(10, scale, minimum=6),
        "{px(28, scale, minimum=20)}": px(28, scale, minimum=20),
        "{px(5, scale, minimum=3)}": px(5, scale, minimum=3),
        "{px(8, scale, minimum=5)}": px(8, scale, minimum=5),
        "{px(10, scale, minimum=7)}": px(10, scale, minimum=7),
    }
    for token, value in replacements.items():
        style = style.replace(token, str(value))
    return style


APP_STYLE = build_app_style()
