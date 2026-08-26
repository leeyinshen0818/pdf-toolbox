from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


Launcher = Callable[[Sequence[str]], object]


@dataclass(frozen=True)
class OpenLocationResult:
    success: bool
    message: str | None = None


def open_output_location(
    path: str | Path,
    *,
    reveal: bool = False,
    launcher: Launcher | None = None,
    platform_name: str | None = None,
) -> OpenLocationResult:
    target = Path(path)
    if not target.exists():
        return OpenLocationResult(False, "Output location no longer exists.")

    platform = platform_name or sys.platform
    launch = launcher or _default_launcher
    args = _open_args(target, reveal=reveal, platform_name=platform)

    try:
        launch(args)
    except OSError as exc:
        return OpenLocationResult(False, str(exc))

    return OpenLocationResult(True)


def _open_args(path: Path, *, reveal: bool, platform_name: str) -> list[str]:
    if platform_name.startswith("win"):
        if reveal and path.is_file():
            return ["explorer.exe", f"/select,{path}"]
        location = path if path.is_dir() else path.parent
        return ["explorer.exe", str(location)]

    if platform_name == "darwin":
        if reveal and path.is_file():
            return ["open", "-R", str(path)]
        location = path if path.is_dir() else path.parent
        return ["open", str(location)]

    location = path if path.is_dir() else path.parent
    return ["xdg-open", str(location)]


def _default_launcher(args: Sequence[str]) -> object:
    return subprocess.Popen(args)
