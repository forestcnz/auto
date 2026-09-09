"""Python 脚本模式冒烟测试（离屏，注入 grab/click/key/hotkey/text，不碰真实鼠标键盘）。"""
import tempfile
from pathlib import Path

import numpy as np
from PySide6.QtGui import QGuiApplication

_app = QGuiApplication([])

from auto_assets.models import AutoProject
from auto_assets.services.automation import AutomationService
from auto_assets.services.project import ProjectService
from auto_assets.services.runner import TaskWorker, imwrite_unicode

tmp = Path(tempfile.mkdtemp())
cfg = ProjectService()
auto = AutomationService(cfg, root=str(tmp))

# 屏幕图像：300x200 灰底 + 一块有纹理的 60x40 特征块 @ (20,10)（与 smoke_runner 一致）
screen = np.full((200, 300, 3), 200, dtype=np.uint8)
patch = np.zeros((40, 60, 3), dtype=np.uint8)
patch[..., 0] = np.linspace(0, 255, 60, dtype=np.uint8)[None, :]
patch[..., 1] = np.linspace(20, 230, 40, dtype=np.uint8)[:, None]
patch[..., 2] = 130
screen[10:50, 20:80] = patch
tpl = screen[10:50, 20:80].copy()

h = auto.create_project("脚本项目", "loop", 3)
(h.path / "templates").mkdir(parents=True, exist_ok=True)
imwrite_unicode(h.path / "templates" / "按钮.png", tpl)


def grab():
    return (screen.copy(), (0, 0))


# 1. 脚本 CRUD：重名追加 _1 / 非法路径拒绝 / 删除后清理空目录
rel1 = auto.create_script(h.path, "main")
rel2 = auto.create_script(h.path, "main")
assert rel1 == "scripts/main.py" and rel2 == "scripts/main_1.py", (rel1, rel2)
assert auto.list_scripts(h.path) == ["scripts/main.py", "scripts/main_1.py"]
try:
    auto.save_script(h.path, "../逃逸.py", "x = 1")
    raise SystemExit("非法路径未被拒绝")
except ValueError:
    print("1. CRUD -> 重名 _1 / 非法路径拒绝 OK")
auto.delete_script(h.path, rel2)
auto.delete_script(h.path, rel1)
assert auto.list_scripts(h.path) == [] and not (h.path / "scripts").exists()

# 2. 脚本模式：find_click 命中 + 键盘注入 + round 轮次 + 提前 return
rel = auto.create_script(h.path, "main")
SRC_MAIN = '''
def main(auto):
    auto.log("round " + str(auto.round))
    ok = auto.find_click("按钮.png")
    if not ok:
        auto.abort("没找到按钮")
    auto.key("enter")
    auto.hotkey("ctrl", "s")
    auto.text("第" + str(auto.round) + "次")
'''
auto.save_script(h.path, rel, SRC_MAIN)
h.data.script = rel
auto.save_project(h)

clicks: list[tuple[int, int, int]] = []
keys: list[str] = []
hotkeys: list[tuple[str, ...]] = []
texts: list[str] = []
worker = TaskWorker(
    h.path, h.data.model_copy(deep=True), grab_fn=grab,
    click_fn=lambda x, y, c=1: clicks.append((x, y, c)),
    key_fn=lambda k: keys.append(k),
    hotkey_fn=lambda *ks: hotkeys.append(ks),
    text_fn=lambda s: texts.append(s),
)
worker.start()
worker.wait(20000)
print("2. 脚本运行 ->", worker.status, "| detail:", worker.detail)
assert worker.status == "已完成", worker.detail
assert clicks == [(50, 30, 1)] * 3, clicks          # 单击模板中心 × 3 轮
assert keys == ["enter"] * 3, keys
assert hotkeys == [("ctrl", "s")] * 3, hotkeys
assert texts == ["第1次", "第2次", "第3次"], texts   # round 从 1 递增
assert worker.round_total == 3

# 3. wait 超时 + abort 携带原因（score 不可能达到 → 未命中）
SRC_WAIT = '''
def main(auto):
    ok = auto.wait("按钮.png", timeout=1.0, score=1.5)
    auto.abort("wait=" + str(ok))
'''
auto.save_script(h.path, rel, SRC_WAIT)
w2 = TaskWorker(h.path, h.data.model_copy(deep=True), grab_fn=grab,
                click_fn=lambda x, y, c=1: None)
w2.start()
w2.wait(20000)
print("3. wait 超时 ->", w2.status, "| detail:", w2.detail)
assert w2.status == "已完成" and "wait=False" in w2.detail

# 4. screen_size / pixel（灰底取色）
SRC_INFO = '''
def main(auto):
    w, hh = auto.screen_size()
    auto.abort("size=" + str(w) + "x" + str(hh) + " pixel=" + str(auto.pixel(200, 100)))
'''
auto.save_script(h.path, rel, SRC_INFO)
w3 = TaskWorker(h.path, h.data.model_copy(deep=True), grab_fn=grab,
                click_fn=lambda x, y, c=1: None)
w3.start()
w3.wait(20000)
print("4. 屏幕/取色 ->", w3.status, "| detail:", w3.detail)
assert w3.status == "已完成"
assert "size=300x200" in w3.detail and "(200, 200, 200)" in w3.detail

# 5. 错误处理：语法错误 / 缺 main / 模板不存在 → 出错
for name, src, frag in [
    ("语法错误", "def main(auto):(", "main.py"),  # 编译错误信息含脚本文件名
    ("缺 main", "x = 1\n", "main(auto)"),
    ("模板缺失", 'def main(auto):\n    auto.find("不存在.png")\n', "模板不存在"),
]:
    auto.save_script(h.path, rel, src)
    w = TaskWorker(h.path, h.data.model_copy(deep=True), grab_fn=grab,
                   click_fn=lambda x, y, c=1: None)
    w.start()
    w.wait(20000)
    print(f"5. {name} ->", w.status, "| detail:", w.detail[:60])
    assert w.status == "出错" and frag in w.detail, (name, w.status, w.detail)

# 清理 config 中的临时条目
_sys_tmp = str(Path(tempfile.gettempdir()))
cfg.config.auto_recent = [p for p in cfg.config.auto_recent if not p.startswith(_sys_tmp)]
cfg.save_config()
print("ALL OK")
