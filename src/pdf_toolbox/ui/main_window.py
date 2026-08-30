from __future__ import annotations

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from pdf_toolbox.build_metadata import APP_NAME
from pdf_toolbox.resources import app_icon_path
from pdf_toolbox.ui.heic_to_jpg_page import HeicToJpgPage
from pdf_toolbox.ui.image_to_pdf_page import ImageToPdfPage
from pdf_toolbox.ui.pdf_organizer_page import PdfOrganizerPage
from pdf_toolbox.ui.pdf_to_image_page import PdfToImagePage
from pdf_toolbox.ui.scale import scaled, ui_scale
from pdf_toolbox.ui.styles import build_app_style


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        icon_path = app_icon_path()
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(scaled(1040), scaled(720))
        self.setMinimumSize(scaled(960), scaled(640))

        root = QWidget()
        root.setObjectName("Root")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        sidebar = self._build_sidebar()
        self.stack = QStackedWidget()
        self.stack.addWidget(ImageToPdfPage())
        self.stack.addWidget(PdfToImagePage())
        self.stack.addWidget(PdfOrganizerPage())
        self.stack.addWidget(HeicToJpgPage())

        layout.addWidget(sidebar)
        layout.addWidget(self.stack, 1)

        self.setCentralWidget(root)
        self.setStyleSheet(build_app_style(ui_scale()))

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setMinimumWidth(scaled(190))
        sidebar.setMaximumWidth(scaled(230))
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(scaled(16), scaled(20), scaled(16), scaled(20))
        layout.setSpacing(scaled(10))

        title = QLabel("PDF Toolbox")
        title.setObjectName("SidebarTitle")
        button_group = QButtonGroup(sidebar)
        button_group.setExclusive(True)

        image_to_pdf = QPushButton("Image -> PDF")
        image_to_pdf.setObjectName("NavButton")
        image_to_pdf.setCheckable(True)
        image_to_pdf.setChecked(True)
        image_to_pdf.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        button_group.addButton(image_to_pdf)

        pdf_to_image = QPushButton("PDF -> Image")
        pdf_to_image.setObjectName("NavButton")
        pdf_to_image.setCheckable(True)
        pdf_to_image.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        button_group.addButton(pdf_to_image)

        organizer = QPushButton("PDF Organizer")
        organizer.setObjectName("NavButton")
        organizer.setCheckable(True)
        organizer.clicked.connect(lambda: self.stack.setCurrentIndex(2))
        button_group.addButton(organizer)

        heic_to_jpg = QPushButton("HEIC -> JPG")
        heic_to_jpg.setObjectName("NavButton")
        heic_to_jpg.setCheckable(True)
        heic_to_jpg.clicked.connect(lambda: self.stack.setCurrentIndex(3))
        button_group.addButton(heic_to_jpg)

        layout.addWidget(title)
        layout.addSpacing(scaled(12))
        layout.addWidget(image_to_pdf)
        layout.addWidget(pdf_to_image)
        layout.addWidget(organizer)
        layout.addWidget(heic_to_jpg)
        layout.addStretch(1)

        return sidebar
