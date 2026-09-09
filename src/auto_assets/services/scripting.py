"""Python 脚本模式运行时：向脚本注入 auto 桥接对象并执行 main(auto)。

脚本约定：
- 位置：{自动化项目}/scripts/xxx.py
- 入口：必须定义 main(auto)，每轮被调用一次（type=loop 时按 times 循环）
- 顶层代码只执行一次（适合放 import / 常量）；本轮提前结束用 return

auto 对象 API（模板按 templates/ 下文件名引用）：
- find(name, score=0.85)         → 命中返回 (score, cx, cy) 绝对物理像素中心点，未命中 None
- find_click(name, score, double) → 找到即点击，返回是否命中
- wait(name, timeout=10, score)   → 循环找图直到命中/超时，返回是否命中
- click(x, y) / double_click(x, y)
- key("enter") / hotkey("ctrl", "s") / text("中文输入")
- sleep(seconds)                  → 分片睡眠，随时响应停止
- log(msg)                        → 写入运行监控窗状态行
- pixel(x, y) → (r, g, b) / screen_size() → (w, h)
- round                           → 当前轮次（从 1 开始）
- abort(reason)                   → 主动终止流程（状态为「已完成」）
- stop_requested()                → 用户是否请求了停止

安全说明：脚本与主程序同信任级（本机个人工具），不做硬沙箱；
仅注入 auto 桥接对象，其余为脚本自己的 import。
"""
from __future__ import annotations

import time
from pathlib import Path

from auto_assets.services.runner import (
    ScriptAbort,
    find_template,
    imread_unicode,
)

DEFAULT_SCORE = 0.85  # 与 AutoStep.score 默认值一致

# 生成脚本骨架（create_script 写入）
SCRIPT_TEMPLATE = '''# -*- coding: utf-8 -*-
"""自动化脚本：运行时每轮调用一次 main(auto)。

常用 API（详见 auto.log 提示或项目文档）：
  auto.find("按钮.png")            # 找图 → (score, x, y) 或 None
  auto.find_click("按钮.png")      # 找到即点击
  auto.wait("弹窗.png", timeout=5) # 等待出现
  auto.click(x, y) / auto.key("enter") / auto.hotkey("ctrl", "s") / auto.text("文本")
  auto.log("进度信息")             # 显示到运行监控窗
  auto.abort("原因")               # 主动终止
"""


def main(auto):
    auto.log("脚本开始运行")
    # TODO: 在这里编写自动化逻辑
'''


def _load_template(proj_dir: Path, name: str):
    """按文件名读 templates/ 下的模板图（拒绝 .. 路径穿越）。"""
    if ".." in Path(name).parts:
        raise ValueError(f"非法模板名: {name}")
    path = Path(proj_dir) / "templates" / name
    return imread_unicode(path) if path.exists() else None


class ScriptAPI:
    """脚本可用的 auto 桥接对象。底层能力由 TaskWorker 注入（离屏测试可替换）。"""

    def __init__(self, proj_dir: Path, *, grab, click, key, hotkey, text, log, stop_flag):
        self.proj_dir = Path(proj_dir)
        self.round = 0  # 当前轮次，TaskWorker 每轮更新
        self._grab = grab          # () -> (screen_bgr, origin) | None
        self._click = click        # (x, y, count) -> None
        self._key_fn = key         # (name) -> None
        self._hotkey_fn = hotkey   # (*names) -> None
        self._text_fn = text       # (s) -> None
        self._log_fn = log         # (msg) -> None
        self._stop_flag = stop_flag  # () -> bool

    # ---------- 找图 ----------

    def find(self, name: str, score: float | None = None):
        """找图。命中返回 (score, cx, cy) 绝对物理像素中心点；未命中返回 None。"""
        threshold = DEFAULT_SCORE if score is None else score
        grabbed = self._grab()
        if grabbed is None:
            return None
        screen, origin = grabbed
        tpl = _load_template(self.proj_dir, name)
        if tpl is None:
            raise FileNotFoundError(f"模板不存在: templates/{name}")
        s, loc, size = find_template(screen, tpl)
        if s is None or s < threshold or loc is None:
            return None
        cx = origin[0] + loc[0] + size[0] // 2
        cy = origin[1] + loc[1] + size[1] // 2
        return (round(s, 4), int(cx), int(cy))

    def find_click(self, name: str, score: float | None = None, double: bool = False) -> bool:
        """找到即点击（默认单击）。返回是否命中。"""
        hit = self.find(name, score)
        if hit is None:
            return False
        self._click(hit[1], hit[2], 2 if double else 1)
        return True

    def wait(self, name: str, timeout: float = 10.0, score: float | None = None,
             interval: float = 0.5) -> bool:
        """循环找图直到命中或超时。返回是否命中。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._stop_flag():
                return False
            if self.find(name, score) is not None:
                return True
            time.sleep(min(interval, max(0.0, deadline - time.monotonic())))
        return False

    # ---------- 鼠标 / 键盘 ----------

    def click(self, x: int, y: int) -> None:
        self._click(int(x), int(y), 1)

    def double_click(self, x: int, y: int) -> None:
        self._click(int(x), int(y), 2)

    def key(self, name: str) -> None:
        self._key_fn(name)

    def hotkey(self, *names: str) -> None:
        self._hotkey_fn(*names)

    def text(self, s: str) -> None:
        self._text_fn(s)

    # ---------- 屏幕 / 流程 ----------

    def screen_size(self) -> tuple[int, int]:
        """当前屏幕（虚拟屏）宽高，物理像素。"""
        grabbed = self._grab()
        if grabbed is None:
            return (0, 0)
        screen, _origin = grabbed
        return (int(screen.shape[1]), int(screen.shape[0]))

    def pixel(self, x: int, y: int) -> tuple[int, int, int]:
        """取屏幕上一点的颜色，返回 (r, g, b)。坐标为绝对物理像素。"""
        grabbed = self._grab()
        if grabbed is None:
            return (0, 0, 0)
        screen, origin = grabbed
        px, py = int(x) - origin[0], int(y) - origin[1]
        b, g, r = screen[py, px][:3]
        return (int(r), int(g), int(b))

    def sleep(self, seconds: float) -> None:
        """分片睡眠，随时响应用户停止。"""
        end = time.monotonic() + seconds
        while True:
            remain = end - time.monotonic()
            if remain <= 0 or self._stop_flag():
                return
            time.sleep(min(0.1, remain))

    def log(self, msg: str) -> None:
        self._log_fn(str(msg))

    def stop_requested(self) -> bool:
        return bool(self._stop_flag())

    def abort(self, reason: str = "") -> None:
        raise ScriptAbort(reason)


def run_script(proj_dir: Path, rel_path: str, api: ScriptAPI) -> None:
    """加载并执行脚本：exec 一次（顶层代码），然后调用 main(auto) 一次。

    轮次循环由调用方（TaskWorker）负责。
    """
    path = Path(proj_dir) / rel_path
    if not path.exists():
        raise FileNotFoundError(f"脚本文件不存在: {rel_path}")
    if ".." in Path(rel_path).parts:
        raise ValueError(f"非法脚本路径: {rel_path}")
    code = compile(path.read_text("utf-8"), str(path), "exec")
    ns: dict = {"__name__": "__auto_script__", "__file__": str(path), "auto": api}
    exec(code, ns)
    main = ns.get("main")
    if not callable(main):
        raise AttributeError("脚本缺少入口函数 main(auto)")
    main(api)
