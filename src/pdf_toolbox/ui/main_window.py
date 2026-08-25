from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PDF Toolbox")
        self.resize(1040, 720)

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        sidebar = self._build_sidebar()
        self.stack = QStackedWidget()
        self.stack.addWidget(ImageToPdfPage())
        self.stack.addWidget(self._placeholder_page("PDF -> Image", "Reserved for Phase 2."))
        self.stack.addWidget(self._placeholder_page("PDF Organizer", "Reserved for Phase 3."))

        layout.addWidget(sidebar)
        layout.addWidget(self.stack, 1)

        self.setCentralWidget(root)

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(190)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 20, 16, 20)
        layout.setSpacing(10)

        title = QLabel("PDF Toolbox")
        title.setObjectName("SidebarTitle")

        image_to_pdf = QPushButton("Image -> PDF")
        image_to_pdf.setCheckable(True)
        image_to_pdf.setChecked(True)
        image_to_pdf.clicked.connect(lambda: self.stack.setCurrentIndex(0))

        pdf_to_image = QPushButton("PDF -> Image")
        pdf_to_image.setEnabled(False)

        organizer = QPushButton("PDF Organizer")
        organizer.setEnabled(False)

        layout.addWidget(title)
        layout.addSpacing(12)
        layout.addWidget(image_to_pdf)
        layout.addWidget(pdf_to_image)
        layout.addWidget(organizer)
        layout.addStretch(1)

        sidebar.setStyleSheet(
            """
            QFrame#Sidebar {
                background: #f3f4f6;
                border-right: 1px solid #d8dee7;
            }
            QLabel#SidebarTitle {
                color: #1f2937;
                font-size: 18px;
                font-weight: 700;
            }
            QPushButton {
                border: 1px solid #d0d7e2;
                border-radius: 6px;
                color: #1f2937;
                padding: 10px 12px;
                text-align: left;
                background: #ffffff;
            }
            QPushButton:checked {
                background: #0f766e;
                border-color: #0f766e;
                color: #ffffff;
                font-weight: 600;
            }
            QPushButton:disabled {
                color: #8b95a5;
                background: #eef1f5;
            }
            """
        )

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
