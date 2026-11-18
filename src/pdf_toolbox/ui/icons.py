"""Tinted, HiDPI-safe icons from the bundled Lucide SVGs (assets/icons, ISC licence)."""
from __future__ import annotations

import hashlib
import logging
import tempfile
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from pdf_toolbox.build_metadata import APP_VERSION
from pdf_toolbox.resources import icon_asset_path


logger = logging.getLogger(__name__)

# Device pixel ratios rendered up front so the icon stays crisp at 100-300% Windows scaling.
_DEVICE_PIXEL_RATIOS = (1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0)


@lru_cache(maxsize=None)
def _svg_source(name: str) -> str:
    return icon_asset_path(name).read_text(encoding="utf-8")


def tinted_svg(name: str, colour: str) -> bytes:
    """The Lucide SVG with currentColor replaced by a concrete colour."""
    return _svg_source(name).replace("currentColor", colour).encode("utf-8")


def _render(svg: bytes, size: int, ratio: float) -> QPixmap:
    device_size = max(1, round(size * ratio))
    pixmap = QPixmap(device_size, device_size)
    pixmap.fill(Qt.transparent)
    renderer = QSvgRenderer(QByteArray(svg))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter, QRectF(0, 0, device_size, device_size))
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


@lru_cache(maxsize=None)
def icon(name: str, colour: str, size: int, checked_colour: str | None = None) -> QIcon:
    """QIcon for a Lucide SVG tinted to `colour` at `size` logical px.

    `checked_colour` tints the On state, used by checkable buttons such as the sidebar items.
    Rendered with QtSvg directly, so it does not depend on the SVG icon-engine plugin.
    """
    result = QIcon()
    states = [(QIcon.Off, colour)]
    if checked_colour is not None:
        states.append((QIcon.On, checked_colour))
    for state, tint in states:
        svg = tinted_svg(name, tint)
        for ratio in _DEVICE_PIXEL_RATIOS:
            result.addPixmap(_render(svg, size, ratio), QIcon.Normal, state)
    return result


def icon_size(size: int) -> QSize:
    return QSize(size, size)


@lru_cache(maxsize=None)
def stylesheet_svg_path(name: str, colour: str) -> str:
    """File path of a tinted SVG for use in QSS `image: url(...)` (QSS cannot recolour SVGs).

    Written once per name/colour to a version-specific folder in the system temp directory.
    Returns a forward-slash path as QSS expects.
    """
    svg = tinted_svg(name, colour)
    digest = hashlib.sha1(svg).hexdigest()[:10]
    folder = Path(tempfile.gettempdir()) / f"pdf-toolbox-icons-{APP_VERSION}"
    target = folder / f"{name}-{digest}.svg"
    try:
        if not target.exists():
            folder.mkdir(parents=True, exist_ok=True)
            target.write_bytes(svg)
    except OSError:
        logger.warning("Could not write tinted icon %s", target, exc_info=True)
        return icon_asset_path(name).as_posix()
    return target.as_posix()
