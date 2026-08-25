APP_STYLE = """
QMainWindow, QWidget#Root {
    background: #f6f7f9;
    color: #1f2328;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}

QFrame#Sidebar {
    background: #ffffff;
    border-right: 1px solid #e2e6ec;
}

QLabel#SidebarTitle {
    color: #1f2328;
    font-size: 17px;
    font-weight: 700;
}

QPushButton#NavButton {
    border: 1px solid transparent;
    border-radius: 6px;
    color: #2f3742;
    padding: 9px 10px;
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
    padding: 7px 11px;
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

QListWidget#ImageList {
    border: 1px solid #dfe4ea;
    border-radius: 8px;
    background: #ffffff;
    outline: 0;
}

QListWidget#ImageList::item {
    border: none;
    padding: 4px;
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

QFrame#SettingsPanel {
    min-width: 350px;
}

QLabel#PanelHeading {
    color: #1f2328;
    font-size: 14px;
    font-weight: 700;
}

QLabel#FieldLabel {
    color: #4f5b67;
    font-size: 12px;
    font-weight: 600;
}

QComboBox {
    background: #ffffff;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    color: #24292f;
    min-height: 34px;
    padding: 4px 10px;
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
    min-height: 28px;
    color: #24292f;
    padding: 5px 8px;
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

QPushButton#IconButton {
    background: transparent;
    border: 1px solid transparent;
    padding: 4px;
}

QPushButton#IconButton:hover:enabled {
    background: #f0f4f9;
    border-color: #d8e0ea;
}

QPushButton#PresetButton {
    text-align: center;
    color: #24292f;
    min-height: 34px;
    padding: 8px 8px;
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

QLabel#ImageDimensions,
QLabel#SubtleText,
QLabel#StatusText {
    color: #66707c;
}
"""
