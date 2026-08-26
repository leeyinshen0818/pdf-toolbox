from __future__ import annotations

import sys

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication

from pdf_toolbox.ui.main_window import MainWindow


def ensure_window_starts_maximized(window: MainWindow, app: QApplication) -> None:
    screen = window.screen() or app.primaryScreen()
    if screen is not None:
        window.setGeometry(screen.availableGeometry())
    window.setWindowState(window.windowState() | Qt.WindowMaximized)
    window.showMaximized()
    QTimer.singleShot(0, window.showMaximized)
    QTimer.singleShot(100, window.showMaximized)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("PDF Toolbox")
    app.setOrganizationName("PDF Toolbox")

    window = MainWindow()
    ensure_window_starts_maximized(window, app)

    return app.exec()
