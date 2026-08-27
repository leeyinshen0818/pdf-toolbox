from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    copy_metadata,
)


EXCLUDES = [
    "IPython",
    "jedi",
    "jsonschema",
    "matplotlib",
    "nbformat",
    "notebook",
    "numpy",
    "pandas",
    "parso",
    "pytest",
    "scipy",
    "tkinter",
    "unittest",
    "zmq",
]


def import_app_metadata(root: Path):
    src = root / "src"
    sys.path.insert(0, str(src))
    from pdf_toolbox.build_metadata import APP_ICON_RELATIVE_PATH, APP_NAME, APP_VERSION

    return APP_ICON_RELATIVE_PATH, APP_NAME, APP_VERSION


def collect_runtime_assets(root: Path, icon_relative_path: tuple[str, ...]):
    icon_path = root.joinpath(*icon_relative_path)
    datas = [(str(icon_path), str(Path(*icon_relative_path).parent))]
    binaries = []
    hiddenimports = ["pymupdf"]

    for package_name in ("pillow_heif",):
        datas += collect_data_files(package_name)
        binaries += collect_dynamic_libs(package_name)
        hiddenimports += collect_submodules(package_name)

    for distribution_name in ("Pillow", "PyMuPDF", "PySide6", "pillow-heif"):
        datas += copy_metadata(distribution_name)

    return datas, binaries, hiddenimports


def write_windows_version_file(root: Path, app_name: str, app_version: str) -> str:
    file_version = _version_tuple(app_version)
    version_file = root / "build" / "windows_version_info.txt"
    version_file.parent.mkdir(parents=True, exist_ok=True)
    version_file.write_text(
        f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={file_version},
    prodvers={file_version},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904b0',
        [
          StringStruct('FileDescription', '{app_name}'),
          StringStruct('FileVersion', '{app_version}'),
          StringStruct('InternalName', '{app_name}'),
          StringStruct('OriginalFilename', '{app_name}.exe'),
          StringStruct('ProductName', '{app_name}'),
          StringStruct('ProductVersion', '{app_version}')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""",
        encoding="utf-8",
    )
    return str(version_file)


def _version_tuple(version: str) -> tuple[int, int, int, int]:
    parts = [int(part) for part in version.split(".")]
    return tuple((parts + [0, 0, 0, 0])[:4])

