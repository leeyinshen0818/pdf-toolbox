from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtCore import QElapsedTimer, QEventLoop, QThread
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
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


logger = logging.getLogger(__name__)
CANCEL_WAIT_TIMEOUT_MS = 15_000


def wait_until(predicate: Callable[[], bool], timeout_ms: int | None = None) -> bool:
    """Wait while keeping the event loop running.

    Workers signal their QThread to quit through queued connections to the GUI thread, so a
    blocking QThread.wait() here would deadlock; process events instead.
    """
    timer = QElapsedTimer()
    timer.start()
    while not predicate():
        if timeout_ms is not None and timer.elapsed() >= timeout_ms:
            return False
        QApplication.processEvents(QEventLoop.AllEvents, 50)
        QThread.msleep(10)
    return True


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
        self.image_to_pdf_page = ImageToPdfPage()
        self.pdf_to_image_page = PdfToImagePage()
        self.pdf_organizer_page = PdfOrganizerPage()
        self.heic_to_jpg_page = HeicToJpgPage()
        self.stack.addWidget(self.image_to_pdf_page)
        self.stack.addWidget(self.pdf_to_image_page)
        self.stack.addWidget(self.pdf_organizer_page)
        self.stack.addWidget(self.heic_to_jpg_page)
        self._closing = False

        layout.addWidget(sidebar)
        layout.addWidget(self.stack, 1)

        self.setCentralWidget(root)
        self.setStyleSheet(build_app_style(ui_scale()))

    def _pages(self) -> tuple:
        return (self.image_to_pdf_page, self.pdf_to_image_page, self.pdf_organizer_page, self.heic_to_jpg_page)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._closing:
            # A close request arrived while we are already waiting for jobs to stop.
            event.ignore()
            return
        self._closing = True
        try:
            if self._finish_background_work():
                event.accept()
            else:
                event.ignore()
        finally:
            self._closing = False

    def _finish_background_work(self) -> bool:
        """Return True when no worker thread is left running and the window may close.

        Exports (Image -> PDF, Organizer) cannot be cancelled: ask, then wait for them to finish.
        Conversions and thumbnail rendering are cancelled and stop after the current page/image.
        Threads are never abandoned, so each job's own temp-file cleanup always runs.
        """
        pages = self._pages()
        exporting = [page for page in pages if page.is_exporting()]
        if exporting:
            answer = QMessageBox.question(
                self,
                "Export in Progress",
                "A PDF export is still running.\n\nWait for it to finish and then close PDF Toolbox?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return False
            wait_until(lambda: not any(page.is_exporting() for page in exporting))

        for page in pages:
            page.stop_background_work()
        if wait_until(lambda: not any(page.has_background_work() for page in pages), CANCEL_WAIT_TIMEOUT_MS):
            return True

        logger.warning("Background work did not stop within %s ms; close was postponed.", CANCEL_WAIT_TIMEOUT_MS)
        QMessageBox.information(
            self,
            APP_NAME,
            "PDF Toolbox is still stopping a running job. Please try closing again in a moment.",
        )
        return False

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
