from __future__ import annotations

from enum import Enum
from io import BytesIO

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter
from pytablericons import TablerIcons, OutlineIcon, FilledIcon

ICON_SIZE = 16

class Color(Enum):
    BLUE = '#005f73'
    GREEN = '#0a9396'
    RED = '#ae2012'
    ORANGE = '#ca6702'

from PIL import Image, ImageDraw

def get_colored_icon(shape, color):
    img = Image.new("RGBA", (16, 16), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    if shape == "circle":
        draw.ellipse([2, 2, 14, 14], fill=color)
    elif shape == "rect":
        draw.rectangle([2, 2, 14, 14], fill=color)
    elif shape == "triangle":
        draw.polygon([(8, 2), (2, 14), (14, 14)], fill=color)
    elif shape == "check":
        draw.line([3, 8, 7, 12, 14, 4], fill=color, width=2)
    elif shape == "cross":
        draw.line([4, 4, 12, 12], fill=color, width=2)
        draw.line([4, 12, 12, 4], fill=color, width=2)
    return img

class Icon(Enum):
    START = get_colored_icon("circle", Color.GREEN.value)
    STOP = get_colored_icon("rect", Color.RED.value)
    CHECK = get_colored_icon("check", Color.GREEN.value)
    X = get_colored_icon("cross", Color.RED.value)
    FILE_CHECK = get_colored_icon("check", Color.BLUE.value)
    REFRESH = get_colored_icon("circle", Color.BLUE.value)
    FILE_X = get_colored_icon("cross", Color.ORANGE.value)
    TRASH = get_colored_icon("rect", Color.ORANGE.value)
    ALERT_TRIANGLE = get_colored_icon("triangle", Color.ORANGE.value)
    INFO_SQUARE_ROUNDED = get_colored_icon("rect", Color.BLUE.value)

    def get_icon(self: Icon) -> QIcon:
        try:
            return self._cached_icon
        except AttributeError:
            pass
        buffer = BytesIO()
        self.value.save(buffer, format='PNG')
        buffer.seek(0)
        pixmap = QPixmap()
        pixmap.loadFromData(buffer.read())
        icon = QIcon(pixmap)
        self._cached_icon = icon  # type: ignore[attr-defined]
        return icon

_combined_cache: dict[tuple, QIcon] = {}

def combine_icons(icon1, icon2, size=ICON_SIZE):
    key = (id(icon1), id(icon2), size)
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
