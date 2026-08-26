from __future__ import annotations

from PySide6.QtCore import Qt
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

from pdf_toolbox.ui.image_to_pdf_page import ImageToPdfPage
from pdf_toolbox.ui.pdf_to_image_page import PdfToImagePage
from pdf_toolbox.ui.styles import APP_STYLE


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PDF Toolbox")
        self.resize(1040, 720)

        root = QWidget()
        root.setObjectName("Root")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        sidebar = self._build_sidebar()
        self.stack = QStackedWidget()
        self.stack.addWidget(ImageToPdfPage())
        self.stack.addWidget(PdfToImagePage())
        self.stack.addWidget(self._placeholder_page("PDF Organizer", "Reserved for Phase 3."))

        layout.addWidget(sidebar)
        layout.addWidget(self.stack, 1)

        self.setCentralWidget(root)
        self.setStyleSheet(APP_STYLE)

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(190)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 20, 16, 20)
        layout.setSpacing(10)

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
        organizer.setEnabled(False)

        layout.addWidget(title)
        layout.addSpacing(12)
        layout.addWidget(image_to_pdf)
        layout.addWidget(pdf_to_image)
        layout.addWidget(organizer)
        layout.addStretch(1)

        return sidebar

    def _placeholder_page(self, title: str, subtitle: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignCenter)

        heading = QLabel(title)
        heading.setAlignment(Qt.AlignCenter)
        heading.setStyleSheet("font-size: 24px; font-weight: 700; color: #374151;")

        text = QLabel(subtitle)
        text.setAlignment(Qt.AlignCenter)
        text.setStyleSheet("font-size: 14px; color: #6b7280;")

        layout.addWidget(heading)
        layout.addWidget(text)
        return page
