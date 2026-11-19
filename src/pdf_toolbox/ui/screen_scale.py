"""Screen-relative UI scale, applied through QT_SCALE_FACTOR before QApplication exists.

The design tokens were tuned on a 1536 px wide logical desktop (1920x1080 at 125%).
On smaller logical desktops (for example 1920x1080 at 150% = 1280 px) the same
tokens take up a larger share of the screen, so the whole UI is scaled down a
little to keep the same density. The scale never goes above 1.0, never below
0.85, and never below 1 / os_scale (so the UI is never drawn smaller than it
would be at 100% Windows scaling).
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
from ctypes import wintypes


logger = logging.getLogger(__name__)

REFERENCE_LOGICAL_WIDTH = 1536
MIN_AUTO_SCALE = 0.85
OVERRIDE_ENV_VAR = "PDF_TOOLBOX_UI_SCALE"
OVERRIDE_MIN = 0.5
OVERRIDE_MAX = 1.5
QT_SCALE_ENV_VAR = "QT_SCALE_FACTOR"


def compute_ui_scale(logical_width: float, os_scale: float) -> float:
    """Return the UI scale for a primary screen of the given logical width and OS scale."""
    return min(1.0, max(logical_width / REFERENCE_LOGICAL_WIDTH, MIN_AUTO_SCALE, 1.0 / os_scale))


def parse_scale_override(value: str | None) -> float | None:
    """Parse PDF_TOOLBOX_UI_SCALE; return None when unset or invalid, else clamp to 0.5-1.5."""
    if value is None or not value.strip():
        return None
    try:
        scale = float(value)
    except ValueError:
        logger.warning("Ignoring invalid %s=%r", OVERRIDE_ENV_VAR, value)
        return None
    if scale != scale:  # NaN
        logger.warning("Ignoring invalid %s=%r", OVERRIDE_ENV_VAR, value)
        return None
    return min(OVERRIDE_MAX, max(OVERRIDE_MIN, scale))


class _DEVMODEW(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", wintypes.WCHAR * 32),
        ("dmSpecVersion", wintypes.WORD),
        ("dmDriverVersion", wintypes.WORD),
        ("dmSize", wintypes.WORD),
        ("dmDriverExtra", wintypes.WORD),
        ("dmFields", wintypes.DWORD),
        ("dmPositionX", wintypes.LONG),
        ("dmPositionY", wintypes.LONG),
        ("dmDisplayOrientation", wintypes.DWORD),
        ("dmDisplayFixedOutput", wintypes.DWORD),
        ("dmColor", ctypes.c_short),
        ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short),
        ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short),
        ("dmFormName", wintypes.WCHAR * 32),
        ("dmLogPixels", wintypes.WORD),
        ("dmBitsPerPel", wintypes.DWORD),
        ("dmPelsWidth", wintypes.DWORD),
        ("dmPelsHeight", wintypes.DWORD),
        ("dmDisplayFlags", wintypes.DWORD),
        ("dmDisplayFrequency", wintypes.DWORD),
        ("dmICMMethod", wintypes.DWORD),
        ("dmICMIntent", wintypes.DWORD),
        ("dmMediaType", wintypes.DWORD),
        ("dmDitherType", wintypes.DWORD),
        ("dmReserved1", wintypes.DWORD),
        ("dmReserved2", wintypes.DWORD),
        ("dmPanningWidth", wintypes.DWORD),
        ("dmPanningHeight", wintypes.DWORD),
    ]


_ENUM_CURRENT_SETTINGS = -1
_MONITOR_DEFAULTTOPRIMARY = 1
_MDT_EFFECTIVE_DPI = 0
_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4


def detect_primary_screen() -> tuple[int, float]:
    """Return (physical_width, os_scale) of the primary screen on Windows.

    Uses only user32/shcore, so it works before QApplication is created. The
    calling thread is switched to per-monitor DPI awareness for the query and
    restored afterwards; the process-wide awareness Qt sets later is untouched.
    Raises on any failure.
    """
    if not sys.platform.startswith("win"):
        raise OSError("screen detection is only implemented for Windows")

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    shcore = ctypes.WinDLL("shcore", use_last_error=True)

    devmode = _DEVMODEW()
    devmode.dmSize = ctypes.sizeof(_DEVMODEW)
    user32.EnumDisplaySettingsW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(_DEVMODEW)]
    user32.EnumDisplaySettingsW.restype = wintypes.BOOL
    if not user32.EnumDisplaySettingsW(None, ctypes.c_uint32(_ENUM_CURRENT_SETTINGS).value, ctypes.byref(devmode)):
        raise ctypes.WinError(ctypes.get_last_error())
    physical_width = int(devmode.dmPelsWidth)
    if physical_width <= 0:
        raise OSError(f"invalid physical width {physical_width}")

    user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
    user32.MonitorFromPoint.restype = wintypes.HMONITOR
    shcore.GetDpiForMonitor.argtypes = [
        wintypes.HMONITOR,
        ctypes.c_int,
        ctypes.POINTER(wintypes.UINT),
        ctypes.POINTER(wintypes.UINT),
    ]
    shcore.GetDpiForMonitor.restype = ctypes.HRESULT

    previous = user32.SetThreadDpiAwarenessContext(_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
    try:
        monitor = user32.MonitorFromPoint(wintypes.POINT(0, 0), _MONITOR_DEFAULTTOPRIMARY)
        if not monitor:
            raise OSError("no primary monitor")
        dpi_x = wintypes.UINT()
        dpi_y = wintypes.UINT()
        shcore.GetDpiForMonitor(monitor, _MDT_EFFECTIVE_DPI, ctypes.byref(dpi_x), ctypes.byref(dpi_y))
    finally:
        if previous:
            user32.SetThreadDpiAwarenessContext(previous)

    if dpi_x.value <= 0:
        raise OSError(f"invalid DPI {dpi_x.value}")
    return physical_width, dpi_x.value / 96.0


def resolve_ui_scale() -> float:
    """Return the UI scale: env override, else auto-detected, else 1.0."""
    override = parse_scale_override(os.environ.get(OVERRIDE_ENV_VAR))
    if override is not None:
        logger.info("UI scale %.3f from %s", override, OVERRIDE_ENV_VAR)
        return override
    try:
        physical_width, os_scale = detect_primary_screen()
    except Exception as exc:
        logger.warning("Screen detection failed, using UI scale 1.0: %s", exc)
        return 1.0
    logical_width = physical_width / os_scale
    scale = compute_ui_scale(logical_width, os_scale)
    logger.info(
        "Primary screen %d px physical at %.0f%% (%.0f px logical): UI scale %.3f",
        physical_width,
        os_scale * 100,
        logical_width,
        scale,
    )
    return scale


def apply_ui_scale() -> float:
    """Resolve the UI scale and set QT_SCALE_FACTOR. Must run before QApplication exists.

    An existing QT_SCALE_FACTOR (set by the user or a test harness) is kept and
    multiplied by the UI scale.
    """
    scale = resolve_ui_scale()
    if scale == 1.0:
        return scale
    base = 1.0
    existing = os.environ.get(QT_SCALE_ENV_VAR)
    if existing:
        try:
            base = float(existing)
        except ValueError:
            logger.warning("Ignoring invalid %s=%r", QT_SCALE_ENV_VAR, existing)
    os.environ[QT_SCALE_ENV_VAR] = f"{base * scale:.4f}"
    return scale
