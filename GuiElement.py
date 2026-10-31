"""Icons of the GUI: Tabler SVG icons (from the pytablericons package) rendered with QtSvg."""
from __future__ import annotations

import os
from enum import Enum

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

ICON_SIZE = 16


class Color(Enum):
    BLUE = '#2b7bb9'
    GREEN = '#16a34a'
    RED = '#dc2626'
    ORANGE = '#d97706'
    GREY = '#8a8a8a'


def _svg_path(name: str):
    try:
        import pytablericons
    except ImportError:
        return None
    path = os.path.join(os.path.dirname(pytablericons.__file__), 'icons', 'outline', name + '.svg')
    return path if os.path.isfile(path) else None


def _render(svg_name: str, color: str, size: int) -> QPixmap:
    from PySide6.QtSvg import QSvgRenderer
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    path = _svg_path(svg_name)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    if path:
        with open(path, 'rt', encoding='utf-8') as f:
            svg = f.read().replace('currentColor', color).replace('stroke-width="2"', 'stroke-width="2.2"')
        QSvgRenderer(QByteArray(svg.encode('utf-8'))).render(painter, QRectF(0, 0, size, size))
    else:
        # fallback when the icon package is missing: a simple dot
        painter.setPen(QPen(QColor(color), 2))
        painter.setBrush(QColor(color))
        painter.drawEllipse(3, 3, size - 6, size - 6)
    painter.end()
    return pixmap


def make_icon(svg_name: str, color: str = '#d0d8e0', size: int = 20) -> QIcon:
    """Any Tabler icon in any color (toolbars of the sync editor)."""
    return QIcon(_render(svg_name, color, size))


class Icon(Enum):
    START = ('player-play', Color.GREEN)
    STOP = ('player-stop', Color.RED)
    PLAY = ('player-play', Color.GREEN)
    PAUSE = ('player-pause', Color.ORANGE)
    CHECK = ('check', Color.GREEN)
    X = ('x', Color.RED)
    FILE_CHECK = ('database', Color.BLUE)          # converted file cached
    REFRESH = ('refresh', Color.BLUE)
    FILE_X = ('eraser', Color.ORANGE)
    TRASH = ('trash', Color.GREY)
    ALERT_TRIANGLE = ('alert-triangle', Color.ORANGE)
    INFO_SQUARE_ROUNDED = ('info-circle', Color.BLUE)
    SYNC = ('clock', Color.BLUE)
    SYNC_WARNING = ('clock-exclamation', Color.ORANGE)
    FOLDER = ('folder-open', Color.BLUE)
    STATUS_OK = ('circle-check', Color.GREEN)
    STATUS_ERROR = ('circle-x', Color.RED)
    STATUS_SKIPPED = ('alert-triangle', Color.ORANGE)
    STATUS_RUNNING = ('loader-2', Color.BLUE)
    STATUS_PENDING = ('circle-dashed', Color.GREY)
    STATUS_CACHED = ('circle-check', Color.BLUE)
    CONVERT_SELECTED = ('playlist-add', Color.GREEN)

    def get_icon(self, size: int = ICON_SIZE) -> QIcon:
        cache = Icon.__dict__.get('_icon_cache')
        if cache is None:
            cache = {}
            setattr(Icon, '_icon_cache', cache)
        key = (self.name, size)
        if key not in cache:
            svg_name, color = self.value
            cache[key] = QIcon(_render(svg_name, color.value, size * 2))  # 2x for sharp scaling
        return cache[key]


_combined_cache: dict[tuple, QIcon] = {}


def combine_icons(icon1, icon2, size=ICON_SIZE):
    key = (icon1.cacheKey(), icon2.cacheKey(), size)
    cached = _combined_cache.get(key)
    if cached is not None:
        return cached
    pixmap = QPixmap(size * 2, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    icon1.paint(painter, 0, 0, size, size)
    icon2.paint(painter, size, 0, size, size)
    painter.end()
    icon = QIcon(pixmap)
    _combined_cache[key] = icon
    return icon
