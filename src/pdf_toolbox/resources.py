from __future__ import annotations

import os
import sys
from pathlib import Path

from pdf_toolbox.build_metadata import APP_ICON_RELATIVE_PATH, APP_NAME


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def bundle_root() -> Path:
    packaged_root = getattr(sys, "_MEIPASS", None)
    if packaged_root:
        return Path(packaged_root)
    return project_root()


def resource_path(*parts: str) -> Path:
    return bundle_root().joinpath(*parts)


def app_icon_path() -> Path:
    return resource_path(*APP_ICON_RELATIVE_PATH)


def user_data_dir() -> Path:
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / APP_NAME
        return Path.home() / "AppData" / "Local" / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg_data_home) if xdg_data_home else Path.home() / ".local" / "share"
    return base / "pdf-toolbox"

