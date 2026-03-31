from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from spinelab.ui.theme import RAW_PALETTE


@lru_cache(maxsize=32)
def _cached_renderer(path_str: str) -> QSvgRenderer:
    return QSvgRenderer(path_str)


def svg_renderer(path: Path) -> QSvgRenderer | None:
    renderer = _cached_renderer(str(path))
    if renderer.isValid():
        return renderer
    return None


@lru_cache(maxsize=32)
def _cached_svg_text(path_str: str) -> str:
    return Path(path_str).read_text(encoding="utf-8")


def _renderer_for_svg_source(svg_source: str) -> QSvgRenderer | None:
    renderer = QSvgRenderer()
    if renderer.load(QByteArray(svg_source.encode("utf-8"))):
        return renderer
    return None


def build_svg_pixmap(
    path: Path,
    size: QSize,
    *,
    device_pixel_ratio: float = 1.0,
    tint: str | None = None,
) -> QPixmap:
    logical_width = max(1, int(round(size.width())))
    logical_height = max(1, int(round(size.height())))

    if tint is None:
        renderer = svg_renderer(path)
    else:
        svg_source = _cached_svg_text(str(path))
        tinted_source = svg_source.replace(
            f"var(--fill-0, {RAW_PALETTE.svg_asset_default})",
            tint,
        )
        tinted_source = tinted_source.replace(
            f"var(--stroke-0, {RAW_PALETTE.svg_asset_default})",
            tint,
        )
        if tinted_source == svg_source:
            tinted_source = svg_source.replace(RAW_PALETTE.svg_asset_default, tint)
        renderer = _renderer_for_svg_source(tinted_source)
    if renderer is None:
        return QPixmap()

    pixel_width = max(1, int(round(logical_width * device_pixel_ratio)))
    pixel_height = max(1, int(round(logical_height * device_pixel_ratio)))

    pixmap = QPixmap(pixel_width, pixel_height)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(painter, QRectF(0.0, 0.0, float(pixel_width), float(pixel_height)))
    painter.end()

    pixmap.setDevicePixelRatio(device_pixel_ratio)
    return pixmap


def build_svg_icon(
    path: Path,
    size: QSize,
    *,
    device_pixel_ratio: float = 1.0,
    tint: str | None = None,
) -> QIcon:
    return QIcon(
        build_svg_pixmap(
            path,
            size,
            device_pixel_ratio=device_pixel_ratio,
            tint=tint,
        )
    )


def centered_square_rect(
    frame_width: int,
    frame_height: int,
    square_side: int,
    *,
    vertical_bias: float = 0.0,
) -> QRect:
    side = max(1, int(round(square_side)))
    x = int(round((frame_width - side) / 2))
    y = int(round((frame_height - side) / 2 + vertical_bias))
    return QRect(x, y, side, side)
