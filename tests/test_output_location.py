from __future__ import annotations

import os
from pathlib import Path

from pdf_toolbox.core.output_location import open_output_location


def test_open_output_location_reveals_file_on_windows(tmp_path: Path) -> None:
    output = tmp_path / "result.pdf"
    output.write_bytes(b"%PDF")
    calls: list[list[str]] = []

    result = open_output_location(
        output,
        reveal=True,
        launcher=lambda args: calls.append(list(args)),
        platform_name="win32",
    )

    assert result.success
    assert calls == [["explorer.exe", f"/select,{output}"]]


def test_open_output_location_opens_folder_once(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    result = open_output_location(
        tmp_path,
        launcher=lambda args: calls.append(list(args)),
        platform_name="win32",
    )

    assert result.success
    assert calls == [["explorer.exe", str(tmp_path)]]


def test_open_output_location_missing_path_fails_without_launching(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    result = open_output_location(
        tmp_path / "missing",
        launcher=lambda args: calls.append(list(args)),
        platform_name="win32",
    )

    assert not result.success
    assert calls == []


def test_open_output_location_launcher_failure_is_nonfatal(tmp_path: Path) -> None:
    def fail(_args):
        raise OSError("launcher unavailable")

    result = open_output_location(tmp_path, launcher=fail, platform_name="win32")

    assert not result.success
    assert result.message == "launcher unavailable"


def test_open_output_location_uses_platform_folder_command(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    platform_name = "darwin" if os.name != "nt" else "linux"

    result = open_output_location(
        tmp_path,
        launcher=lambda args: calls.append(list(args)),
        platform_name=platform_name,
    )

    assert result.success
    expected_command = "open" if platform_name == "darwin" else "xdg-open"
    assert calls == [[expected_command, str(tmp_path)]]
