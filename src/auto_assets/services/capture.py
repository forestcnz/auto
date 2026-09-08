"""捕获引擎：mss 抓取指定屏幕区域（物理像素），返回 PIL Image。"""
from __future__ import annotations

from PIL import Image
from PySide6.QtCore import QRect


def logical_to_physical_rect(screen, local_rect: QRect) -> QRect:
    """把某屏幕上的局部逻辑坐标 QRect 换算成桌面物理像素 QRect。

    screen: QScreen；local_rect 相对该屏幕左上角（逻辑坐标）。
    """
    dpr = screen.devicePixelRatio()
    geo = screen.geometry()  # 逻辑坐标（全局虚拟桌面）
    x = round((geo.x() + local_rect.x()) * dpr)
    y = round((geo.y() + local_rect.y()) * dpr)
    w = round(local_rect.width() * dpr)
    h = round(local_rect.height() * dpr)
    return QRect(x, y, w, h)


def grab_region(physical_rect: QRect) -> Image.Image:
    """按物理像素抓屏。mss 坐标系即桌面物理像素。"""
    import mss

    with mss.mss() as sct:
        raw = sct.grab(
            {
                "left": physical_rect.x(),
                "top": physical_rect.y(),
                "width": physical_rect.width(),
                "height": physical_rect.height(),
            }
        )
        return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
