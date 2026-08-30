from __future__ import annotations

from PySide6.QtCore import QSize


REFERENCE_WORK_AREA = QSize(1920, 1080)
MIN_UI_SCALE = 0.68
MAX_UI_SCALE = 1.0
_ui_scale = 1.0


def calculate_ui_scale(available_size: QSize) -> float:
    if available_size.width() <= 0 or available_size.height() <= 0:
        return 1.0
    scale = min(
        available_size.width() / REFERENCE_WORK_AREA.width(),
        available_size.height() / REFERENCE_WORK_AREA.height(),
    )
    return max(MIN_UI_SCALE, min(MAX_UI_SCALE, scale))


def set_ui_scale(scale: float) -> None:
    global _ui_scale
    _ui_scale = max(MIN_UI_SCALE, min(MAX_UI_SCALE, scale))


def ui_scale() -> float:
    return _ui_scale


def scaled(value: int | float, *, minimum: int = 1) -> int:
    return max(minimum, round(float(value) * _ui_scale))


def scaled_size(width: int, height: int, *, minimum: int = 1) -> QSize:
    return QSize(scaled(width, minimum=minimum), scaled(height, minimum=minimum))

