from __future__ import annotations

import ctypes
import logging
import sys
from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from pdf_toolbox.build_metadata import APP_NAME, APP_ORGANIZATION, APP_VERSION
from pdf_toolbox.core.heic_to_jpg import register_heic_support
from pdf_toolbox.logging_config import configure_logging
from pdf_toolbox.resources import app_icon_path

if TYPE_CHECKING:
    from pdf_toolbox.ui.main_window import MainWindow


logger = logging.getLogger(__name__)


def ensure_window_starts_maximized(window: "MainWindow", app: QApplication) -> None:
    screen = window.screen() or app.primaryScreen()
    if screen is not None:
        window.setGeometry(screen.availableGeometry())
    window.setWindowState(window.windowState() | Qt.WindowMaximized)
    window.showMaximized()
    QTimer.singleShot(0, window.showMaximized)
    QTimer.singleShot(100, window.showMaximized)


def configure_qt_application(app: QApplication) -> None:
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName(APP_ORGANIZATION)
    app.setApplicationVersion(APP_VERSION)

    icon_path = app_icon_path()
    if icon_path.exists():
        icon = QIcon(str(icon_path))
        app.setWindowIcon(icon)
    else:
        logger.warning("Application icon not found: %s", icon_path)


def _show_startup_error(message: str) -> None:
    app = QApplication.instance()
    if app is not None:
        QMessageBox.critical(None, APP_NAME, message)
        return
    if sys.platform.startswith("win"):
        ctypes.windll.user32.MessageBoxW(None, message, APP_NAME, 0x10)
        return
    print(message, file=sys.stderr)


def main() -> int:
    log_path = configure_logging()
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        register_heic_support()
        app = QApplication(sys.argv)
        configure_qt_application(app)

        from pdf_toolbox.ui.main_window import MainWindow

        window = MainWindow()
        ensure_window_starts_maximized(window, app)

        return app.exec()
    except Exception as exc:
        logger.exception("Startup failed")
        _show_startup_error(
            "PDF Toolbox could not start.\n\n"
            f"{exc}\n\n"
            f"Technical details were written to:\n{log_path}"
        )
        return 1
