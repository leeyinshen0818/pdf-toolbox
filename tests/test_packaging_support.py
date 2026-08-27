from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

import pdf_toolbox
from pdf_toolbox import resources
from pdf_toolbox.app import configure_qt_application
from pdf_toolbox.build_metadata import (
    APP_ICON_RELATIVE_PATH,
    APP_NAME,
    APP_ORGANIZATION,
    APP_VERSION,
)
from pdf_toolbox.logging_config import configure_logging, log_file_path


def test_version_is_centralized() -> None:
    assert APP_VERSION == "1.0.0"
    assert pdf_toolbox.__version__ == APP_VERSION


def test_development_resource_path_resolves_icon() -> None:
    icon_path = resources.app_icon_path()

    assert icon_path == resources.project_root().joinpath(*APP_ICON_RELATIVE_PATH)
    assert icon_path.suffix.lower() == ".ico"


def test_packaged_resource_path_uses_pyinstaller_meipass(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(resources.sys, "_MEIPASS", str(tmp_path), raising=False)

    assert resources.resource_path("icon", "app.ico") == tmp_path / "icon" / "app.ico"


def test_user_data_dir_uses_windows_local_app_data(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(resources.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert resources.user_data_dir() == tmp_path / APP_NAME


def test_logging_uses_user_writable_app_data(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(resources.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    path = configure_logging()

    assert path == log_file_path()
    assert path.parent.exists()
    assert APP_NAME in str(path)


def test_qsettings_application_metadata_is_configured() -> None:
    app = QApplication.instance() or QApplication([])

    configure_qt_application(app)

    assert QCoreApplication.applicationName() == APP_NAME
    assert QCoreApplication.organizationName() == APP_ORGANIZATION
    assert QCoreApplication.applicationVersion() == APP_VERSION
