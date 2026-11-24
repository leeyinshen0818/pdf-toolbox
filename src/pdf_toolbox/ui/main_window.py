from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtCore import QElapsedTimer, QEventLoop, QSize, QThread
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
from pdf_toolbox.ui.image_to_jpg_page import ConvertToJpgPage
from pdf_toolbox.ui.image_to_pdf_page import ImageToPdfPage
from pdf_toolbox.ui.pdf_organizer_page import PdfOrganizerPage
from pdf_toolbox.ui.pdf_to_image_page import PdfToImagePage
from pdf_toolbox.ui.threads import live_thread_count
from pdf_toolbox.ui.components.drop_area import local_paths
from pdf_toolbox.ui.components.page import ToolPage
from pdf_toolbox.ui.styles import build_app_style
from pdf_toolbox.ui import icons
from pdf_toolbox.ui.tokens import ICON_SIDEBAR, PRIMARY, SPACE_8, SPACE_12, SPACE_16, TEXT_SECONDARY


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


class CurrentPageStack(QStackedWidget):
    """Stacked widget sized by the visible page only, so the tallest page never sets the window minimum."""

    def __init__(self) -> None:
        super().__init__()
        self.currentChanged.connect(lambda _index: self.updateGeometry())

    def sizeHint(self) -> QSize:
        current = self.currentWidget()
        return current.sizeHint() if current is not None else super().sizeHint()

    def minimumSizeHint(self) -> QSize:
        current = self.currentWidget()
        return current.minimumSizeHint() if current is not None else super().minimumSizeHint()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        icon_path = app_icon_path()
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(1040, 720)
        self.setMinimumSize(960, 640)

        root = QWidget()
        root.setObjectName("Root")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        sidebar = self._build_sidebar()
        self.stack = CurrentPageStack()
        self.image_to_pdf_page = ImageToPdfPage()
        self.pdf_to_image_page = PdfToImagePage()
        self.pdf_organizer_page = PdfOrganizerPage()
        self.convert_to_jpg_page = ConvertToJpgPage()
        self.stack.addWidget(self.image_to_pdf_page)
        self.stack.addWidget(self.pdf_to_image_page)
        self.stack.addWidget(self.pdf_organizer_page)
        self.stack.addWidget(self.convert_to_jpg_page)
        self._closing = False

        layout.addWidget(sidebar)
        layout.addWidget(self.stack, 1)

        self.setCentralWidget(root)
        self.setStyleSheet(build_app_style())
        # Files dropped anywhere in the window go to the current page (same as its drop area).
        self.setAcceptDrops(True)

    def _pages(self) -> tuple:
        return (self.image_to_pdf_page, self.pdf_to_image_page, self.pdf_organizer_page, self.convert_to_jpg_page)

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

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        paths = local_paths(event.mimeData()) if event.mimeData().hasUrls() else []
        if not paths:
            super().dropEvent(event)
            return
        event.acceptProposedAction()
        page = self.stack.currentWidget()
        if isinstance(page, ToolPage) and not page.is_job_running():
            page.add_dropped_files(paths)

    def _finish_background_work(self) -> bool:
        """Return True when no worker thread is left running and the window may close.

        Every job (both exports, both conversions, thumbnail rendering) is cancelled and stops
        after its current page or image; nothing is ever abandoned mid-write, so each job's own
        temp-file cleanup always runs.
        """
        pages = self._pages()
        for page in pages:
            page.stop_background_work()
        # live_thread_count covers worker threads a page has already let go of (e.g. after a clear).
        idle = lambda: not any(page.has_background_work() for page in pages) and live_thread_count() == 0  # noqa: E731
        if wait_until(idle, CANCEL_WAIT_TIMEOUT_MS):
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
        sidebar.setMinimumWidth(190)
        sidebar.setMaximumWidth(230)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(SPACE_16, SPACE_16, SPACE_16, SPACE_16)
        layout.setSpacing(SPACE_8)

        title = QLabel("PDF Toolbox")
        title.setObjectName("SidebarTitle")
        button_group = QButtonGroup(sidebar)
        button_group.setExclusive(True)

        nav_items = [
            ("Image → PDF", "file-image"),
            ("PDF → Image", "images"),
            ("PDF Organizer", "layout-grid"),
            ("Convert to JPG", "image"),
        ]
        nav_buttons: list[QPushButton] = []
        for index, (label, icon_name) in enumerate(nav_items):
            button = QPushButton(label)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setIcon(icons.icon(icon_name, TEXT_SECONDARY, ICON_SIDEBAR, checked_colour=PRIMARY))
            button.setIconSize(icons.icon_size(ICON_SIDEBAR))
            button.clicked.connect(lambda _checked=False, index=index: self.stack.setCurrentIndex(index))
            button_group.addButton(button)
            nav_buttons.append(button)
        nav_buttons[0].setChecked(True)

        layout.addWidget(title)
        layout.addSpacing(SPACE_12)
        for button in nav_buttons:
            layout.addWidget(button)
        layout.addStretch(1)

        return sidebar
