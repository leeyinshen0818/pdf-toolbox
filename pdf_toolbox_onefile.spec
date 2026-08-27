# -*- mode: python ; coding: utf-8 -*-

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(SPECPATH)
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from packaging_support.pyinstaller_config import (
    EXCLUDES,
    collect_runtime_assets,
    import_app_metadata,
    write_windows_version_file,
)


APP_ICON_RELATIVE_PATH, APP_NAME, APP_VERSION = import_app_metadata(ROOT)
icon_path = ROOT.joinpath(*APP_ICON_RELATIVE_PATH)
datas, binaries, hiddenimports = collect_runtime_assets(ROOT, APP_ICON_RELATIVE_PATH)

a = Analysis(
    ["run.py"],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_path),
    version=write_windows_version_file(ROOT, APP_NAME, APP_VERSION),
)
