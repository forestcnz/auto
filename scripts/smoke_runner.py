"""运行引擎冒烟测试（离屏，注入 grab/click，不碰真实鼠标键盘）。"""
import tempfile
import time
from pathlib import Path

import numpy as np
from PySide6.QtGui import QGuiApplication

_app = QGuiApplication([])

from auto_assets.models import AutoProject, AutoStep
from auto_assets.services.runner import TaskWorker, find_template, imwrite_unicode

tmp = Path(tempfile.mkdtemp())

# 屏幕图像：300x200 灰底 + 一块有纹理的 60x40 特征块 @ (20,10)
screen = np.full((200, 300, 3), 200, dtype=np.uint8)
patch = np.zeros((40, 60, 3), dtype=np.uint8)
patch[..., 0] = np.linspace(0, 255, 60, dtype=np.uint8)[None, :]
patch[..., 1] = np.linspace(20, 230, 40, dtype=np.uint8)[:, None]
patch[..., 2] = 130
screen[10:50, 20:80] = patch
tpl = screen[10:50, 20:80].copy()

# 1. find_template
score, loc, size = find_template(screen, tpl)
print("1. match ->", round(score, 3), loc, size)
assert score > 0.99 and loc == (20, 10) and size == (60, 40)

# 2. 单步任务：命中并点击模板中心
proj_dir = tmp / "任务A"
(proj_dir / "templates").mkdir(parents=True)
imwrite_unicode(proj_dir / "templates" / "t.png", tpl)
tpl_rel = "templates/t.png"

clicks: list[tuple[int, int]] = []
data = AutoProject(
    name="任务A", type="any", times=1,
    steps=[AutoStep(template=tpl_rel, action="click", score=0.8, strategy="skip")],
)
worker = TaskWorker(proj_dir, data,
                    grab_fn=lambda: (screen.copy(), (0, 0)),
                    click_fn=lambda x, y, c=1: clicks.append((x, y, c)))
worker.start()
worker.wait(8000)
print("2. worker ->", worker.status, "| detail:", worker.detail, "| clicks:", clicks)
assert worker.status == "已完成"
assert clicks == [(20 + 30, 10 + 20, 1)], clicks  # 单击：模板中心

# 2b. 双击：count=2
data2b = AutoProject(
    name="任务A2", type="any", times=1,
    steps=[AutoStep(template=tpl_rel, action="double_click", score=0.8, strategy="skip")],
)
clicks_d: list[tuple[int, int, int]] = []
worker2b = TaskWorker(proj_dir, data2b,
                      grab_fn=lambda: (screen.copy(), (0, 0)),
                      click_fn=lambda x, y, c=1: clicks_d.append((x, y, c)))
worker2b.start()
worker2b.wait(8000)
print("2b. 双击 ->", worker2b.status, "| clicks:", clicks_d)
assert clicks_d == [(50, 30, 2)], clicks_d

# 3. loop + exit 策略：阈值不可能达到 → 第一步触发 exit 终止
data2 = AutoProject(
    name="任务B", type="loop", times=999,
    steps=[AutoStep(template=tpl_rel, action="click", score=1.5, strategy="exit")],
)
clicks2: list[tuple[int, int]] = []
worker2 = TaskWorker(proj_dir, data2,
                     grab_fn=lambda: (screen.copy(), (0, 0)),
                     click_fn=lambda x, y, c=1: clicks2.append((x, y, c)))
worker2.start()
worker2.wait(8000)
print("3. exit ->", worker2.status, "| detail:", worker2.detail, "| clicks:", len(clicks2))
assert worker2.status == "已完成" and not clicks2  # 未命中不点击

# 4. 手动停止：loop + skip 策略 + times 巨大 → stop 后很快结束
data3 = AutoProject(
    name="任务C", type="loop", times=999999,
    steps=[AutoStep(template=tpl_rel, action="click", score=0.8, strategy="skip")],
)
worker3 = TaskWorker(proj_dir, data3,
                     grab_fn=lambda: (screen.copy(), (0, 0)),
                     click_fn=lambda x, y, c=1: clicks2.append((x, y, c)))
worker3.start()
t0 = time.time()
QTimer = None  # 占位，stop 由主线程稍后调用
import threading


def _stop_later():
    time.sleep(0.6)
    worker3.stop()


threading.Thread(target=_stop_later, daemon=True).start()
worker3.wait(15000)
print("4. stop ->", worker3.status, f"| 耗时 {time.time() - t0:.1f}s")
assert worker3.status == "已停止"

# 5. 模板缺失
data4 = AutoProject(name="任务D", type="any", times=1,
                    steps=[AutoStep(template="templates/不存在.png")])
worker4 = TaskWorker(proj_dir, data4,
                     grab_fn=lambda: (screen.copy(), (0, 0)),
                     click_fn=lambda x, y, c=1: None)
worker4.start()
worker4.wait(8000)
print("5. 缺模板 ->", worker4.status, "| detail:", worker4.detail)
assert worker4.status == "已完成"

print("ALL OK")
