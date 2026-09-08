"""Auto 品牌 logo：自动车（激光雷达 + 信号弧）矢量图标。

单一数据源：本文件内嵌 SVG（与 resources/logo.svg 保持一致），
渲染为任意尺寸 QPixmap / 窗口 QIcon。
"""
from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap

SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <circle cx="35" cy="15" r="1.9" fill="#4b5563"/>
  <path d="M 31 11.5 A 5.5 5.5 0 0 1 39 11.5" stroke="#4b5563" stroke-width="2.4" fill="none" stroke-linecap="round"/>
  <path d="M 27.5 11.5 A 9.5 9.5 0 0 1 42.5 11.5" stroke="#4b5563" stroke-width="2" fill="none" stroke-linecap="round" opacity="0.4"/>
  <rect x="32.8" y="18.4" width="4.4" height="2.6" rx="1.3" fill="#4b5563"/>
  <path d="M 21.5 32 L 26.5 22.5 Q 27.6 20.5 30 20.5 L 40 20.5 Q 42.6 20.5 44 22.7 L 48.5 32 Z" fill="#4b5563"/>
  <rect x="7.5" y="32" width="50" height="13.5" rx="4.5" fill="#4b5563"/>
  <path d="M 25 30.5 L 28.6 23.2 Q 29 22.5 29.8 22.5 L 31.5 22.5 L 31.5 30.5 Z" fill="#e5e7eb"/>
  <path d="M 34.5 30.5 L 34.5 22.5 L 39.5 22.5 Q 40.6 22.5 41.2 23.4 L 44.6 30.5 Z" fill="#e5e7eb"/>
  <rect x="52.6" y="34.6" width="3.6" height="3.2" rx="1.6" fill="#9ca3af"/>
  <circle cx="19" cy="45.5" r="5.5" fill="#1f2937"/>
  <circle cx="19" cy="45.5" r="2.1" fill="#f3f4f6"/>
  <circle cx="47" cy="45.5" r="5.5" fill="#1f2937"/>
  <circle cx="47" cy="45.5" r="2.1" fill="#f3f4f6"/>
  <path d="M 16 53.5 H 48" stroke="#d1d5db" stroke-width="2.5" stroke-linecap="round"/>
</svg>
"""

try:
    from PySide6.QtSvg import QSvgRenderer

    _HAS_SVG = True
except ImportError:  # 环境缺失 QtSvg 时降级为透明占位
    _HAS_SVG = False


def logo_pixmap(size: int) -> QPixmap:
    """渲染指定边长的正方形 logo（透明底）。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    if not _HAS_SVG:
        return pm
    renderer = QSvgRenderer(QByteArray(SVG.encode("utf-8")))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p)
    p.end()
    return pm


def app_icon() -> QIcon:
    """多尺寸窗口图标（任务栏 / 标题栏）。"""
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(logo_pixmap(s))
    return icon
