from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from pdf_toolbox.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("PDF Toolbox")
    app.setOrganizationName("PDF Toolbox")

    window = MainWindow()
    window.show()

    return app.exec()
