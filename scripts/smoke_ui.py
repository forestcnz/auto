"""覆盖层构建 + mss 真实抓屏验证 + 清理测试污染的 config。"""
import tempfile
from pathlib import Path

from PySide6.QtWidgets import QApplication

app = QApplication([])

# 1. 覆盖层可构建/可显示（offscreen）
from auto_assets.ui.overlay import CaptureOverlay
from PySide6.QtGui import QGuiApplication

scr = QGuiApplication.primaryScreen()
ov = CaptureOverlay(scr)
ov.show()
print("1. overlay OK:", scr.name(), scr.geometry(), "dpr=", scr.devicePixelRatio())

# 2. 逻辑→物理换算
from PySide6.QtCore import QRect
from auto_assets.services.capture import grab_region, logical_to_physical_rect

local = QRect(50, 40, 200, 100)
phys = logical_to_physical_rect(scr, local)
img = grab_region(phys)
print("2. grab OK:", img.size, "physical rect:", phys.x(), phys.y(), phys.width(), phys.height())

# 3. 清理 config 中指向 temp 的污染条目
from auto_assets.services.project import ProjectService

svc = ProjectService()
temp_root = str(Path(tempfile.gettempdir()))
before = len(svc.config.recent)
svc.config.recent = [r for r in svc.config.recent if not r.path.startswith(temp_root)]
svc.config.last = "" if svc.config.last.startswith(temp_root) else svc.config.last
svc.save_config()
print(f"3. config cleaned: {before} -> {len(svc.config.recent)} entries")
print("ALL OK")
