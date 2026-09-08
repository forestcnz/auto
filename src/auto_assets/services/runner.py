"""任务运行引擎：截屏 → OpenCV 模板匹配 → 达到阈值自动点击。

- 每个运行中的项目一个 TaskWorker(QThread)
- grab_screen(): mss 抓整个虚拟屏幕（物理像素），返回 (BGR ndarray, 屏幕原点)
- find_template(): TM_CCOEFF_NORMED 匹配，返回 (score, 左上角坐标, 模板尺寸)
- click_at(): ctypes 移动光标并左键单击（物理像素坐标）
- 失败策略：skip 跳过本步 / loop 循环重试本步 / exit 终止流程
"""
from __future__ import annotations

import ctypes
import time
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal

from auto_assets.models import AutoProject

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


def grab_screen() -> tuple[np.ndarray, tuple[int, int]] | None:
    """抓取整个虚拟屏幕，返回 (BGR 图像, 屏幕原点(物理像素))。"""
    import mss

    with mss.mss() as sct:
        mon = sct.monitors[0]  # 整个虚拟屏幕（多显示器合并）
        # mss 9+ 返回 dict，旧版返回 namedtuple——统一兼容
        get = (lambda k: mon[k]) if isinstance(mon, dict) else (lambda k: getattr(mon, k))
        origin = (int(get("left")), int(get("top")))
        raw = sct.grab(mon)
    arr = np.frombuffer(raw.bgra, dtype=np.uint8).reshape(raw.height, raw.width, 4)
    return arr[:, :, :3].copy(), origin


def imread_unicode(path: Path) -> np.ndarray | None:
    """cv2.imread 的 unicode 安全版（Windows 下 cv2 不支持非 ASCII 路径）。"""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    return cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)


def imwrite_unicode(path: Path, img: np.ndarray) -> bool:
    ok, buf = cv2.imencode(Path(path).suffix, img)
    if ok:
        Path(path).write_bytes(buf.tobytes())
    return bool(ok)


def find_template(screen_bgr: np.ndarray, tpl_bgr: np.ndarray | None):
    """模板匹配。返回 (score, 匹配左上角(x,y), 模板(w,h))；不可匹配返回 (None, None, None)。"""
    if tpl_bgr is None or screen_bgr is None:
        return None, None, None
    th, tw = tpl_bgr.shape[:2]
    sh, sw = screen_bgr.shape[:2]
    if th > sh or tw > sw:
        return None, None, None
    res = cv2.matchTemplate(screen_bgr, tpl_bgr, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    return float(max_val), (int(max_loc[0]), int(max_loc[1])), (tw, th)


def click_at(x: int, y: int, count: int = 1) -> None:
    """移动光标到物理像素 (x, y) 并左键点击 count 次（count=2 为双击）。"""
    user32 = ctypes.windll.user32
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.03)
    for _ in range(max(1, count)):
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.03)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(0.05)


class TaskWorker(QThread):
    """单个自动化项目的执行线程。"""

    updated = Signal()          # 状态/详情变化（UI 轮询读取属性）

    def __init__(self, path: Path, data: AutoProject, grab_fn=None, click_fn=None):
        super().__init__()
        self.path = Path(path)
        self.data = data
        self.status = "排队中"
        self.detail = ""
        self.last_score: float | None = None
        self._stop = False
        self._grab = grab_fn or grab_screen
        self._click = click_fn or click_at

    # ---- 控制 ----

    def stop(self) -> None:
        self._stop = True

    # ---- 执行 ----

    def run(self) -> None:  # noqa: C901
        try:
            self.status = "运行中"
            self._run_steps()
            if self._stop:
                self.status = "已停止"
            else:
                self.status = "已完成"
        except Exception as e:  # noqa: BLE001
            self.status = "出错"
            self.detail = str(e)
        self.updated.emit()

    def _run_steps(self) -> None:
        d = self.data
        total_rounds = d.times if d.type == "loop" else 1
        rnd = 0
        while rnd < total_rounds and not self._stop:
            rnd += 1
            round_txt = f"第 {rnd}/{total_rounds} 轮" if d.type == "loop" else "单次执行"
            for i, step in enumerate(d.steps):
                if self._stop:
                    return
                if not self._exec_step(step, i, round_txt, len(d.steps)):
                    if step.strategy == "exit":
                        self.detail = f"{round_txt} · 步骤 {i + 1} 匹配失败，触发 exit 终止"
                        return
                    return  # stop
            if d.type == "loop" and not self._stop:
                self.detail = f"第 {rnd}/{total_rounds} 轮完成"
                self.updated.emit()
                time.sleep(0.3)

    def _exec_step(self, step, idx: int, round_txt: str, total: int) -> bool:
        """执行单步。返回 False = 流程终止（exit 或手动停止）。"""
        tpl_path = self.path / step.template
        tpl = imread_unicode(tpl_path) if tpl_path.exists() else None
        if tpl is None:
            self.detail = f"{round_txt} · 步骤 {idx + 1}/{total} 模板缺失 → 跳过"
            self.updated.emit()
            return step.strategy != "exit"

        while not self._stop:
            grabbed = self._grab()
            if grabbed is None:
                time.sleep(0.5)
                continue
            screen, origin = grabbed
            score, loc, size = find_template(screen, tpl)
            self.last_score = score
            if score is not None and score >= step.score and loc is not None:
                cx = origin[0] + loc[0] + size[0] // 2
                cy = origin[1] + loc[1] + size[1] // 2
                act_txt = "双击" if step.action == "double_click" else "单击"
                count = 2 if step.action == "double_click" else 1
                self.detail = f"{round_txt} · 步骤 {idx + 1}/{total} 命中 {score:.2f} → {act_txt} ({cx},{cy})"
                self.updated.emit()
                self._click(cx, cy, count)
                time.sleep(0.3)
                return True
            if step.strategy == "skip":
                self.detail = f"{round_txt} · 步骤 {idx + 1}/{total} 未达阈值({score:.2f}) → 跳过"
                self.updated.emit()
                return True
            if step.strategy == "exit":
                self.updated.emit()
                return False
            # loop 策略：循环重试本步
            self.detail = f"{round_txt} · 步骤 {idx + 1}/{total} 未达阈值({score:.2f}) → 循环重试"
            self.updated.emit()
            time.sleep(0.5)
        return False
