from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QSettings


@pytest.fixture(autouse=True)
def isolated_qsettings(tmp_path_factory: pytest.TempPathFactory):
    """Keep every test away from the user's real saved settings (Windows registry)."""
    folder: Path = tmp_path_factory.mktemp("qsettings")
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(folder))
    QCoreApplication.setOrganizationName("pdf-toolbox-tests")
    QCoreApplication.setApplicationName("pdf-toolbox-tests")
    QSettings().clear()
    yield
    QSettings().clear()
