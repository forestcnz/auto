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
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
INPUT_KEYBOARD = 1

# 虚拟键码表：脚本 auto.key()/auto.hotkey() 支持的按键名
_KEY_NAMES = {
    "esc": 0x1B, "escape": 0x1B, "tab": 0x09, "enter": 0x0D, "return": 0x0D,
    "space": 0x20, "backspace": 0x08, "delete": 0x2E, "del": 0x2E,
    "insert": 0x2D, "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "ctrl": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B,
    "capslock": 0x14, "printscreen": 0x2C,
}
KEY_MAP = {
    **_KEY_NAMES,
    **{chr(c): c for c in range(ord("A"), ord("Z") + 1)},
    **{str(d): ord(str(d)) for d in range(10)},
    **{f"f{i}": 0x6F + i for i in range(1, 13)},  # F1=0x70 … F12=0x7B
}


def _vk(name: str) -> int:
    """按键名 → Windows 虚拟键码。单字符一律按字母/符号处理。"""
    k = str(name).strip().lower()
    if k in KEY_MAP:
        return KEY_MAP[k]
    if len(k) == 1:
        return ord(k.upper())
    raise ValueError(f"未知按键: {name}")


def press_key(key: str) -> None:
    """单击一个键（keybd_event，物理键码，仅 Windows）。"""
    vk = _vk(key)
    user32 = ctypes.windll.user32
    user32.keybd_event(vk, 0, 0, 0)
    time.sleep(0.02)
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.05)


def press_hotkey(*keys: str) -> None:
    """组合键：按住所有键 → 逆序松开，如 press_hotkey("ctrl", "s")。"""
    user32 = ctypes.windll.user32
    vks = [_vk(k) for k in keys]
    if not vks:
        return
    for vk in vks:
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.02)
    for vk in reversed(vks):
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.02)
    time.sleep(0.05)


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT), ("pad", ctypes.c_ubyte * 40)]

    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_ulong), ("u", _U)]


def _send_unicode_scan(scan: int, up: bool) -> None:
    """SendInput 注入一个 UTF-16 码元（KEYEVENTF_UNICODE，绕过输入法）。"""
    flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0)
    ki = _KEYBDINPUT(0, scan, flags, 0, 0)
    inp = _INPUT(INPUT_KEYBOARD)
    inp.ki = ki
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))


def type_text(text: str) -> None:
    """注入文本（支持中文）：按 UTF-16 码元逐个 SendInput，不走输入法。"""
    data = text.encode("utf-16-le")
    for i in range(0, len(data), 2):
        scan = data[i] | (data[i + 1] << 8)
        _send_unicode_scan(scan, up=False)
        _send_unicode_scan(scan, up=True)
        time.sleep(0.01)
    time.sleep(0.05)


class ScriptAbort(Exception):
    """脚本调用 auto.abort() 主动终止流程（视为正常结束，非出错）。"""


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

    def __init__(self, path: Path, data: AutoProject, grab_fn=None, click_fn=None,
                 key_fn=None, hotkey_fn=None, text_fn=None):
        super().__init__()
        self.path = Path(path)
        self.data = data
        self.status = "排队中"
        self.detail = ""
        self.last_score: float | None = None
        self.round_current = 0  # 当前轮次（loop 项目，UI 进度条读取）
        self.round_total = data.times if data.type == "loop" else 0  # 0 = 非循环
        self.started_at: float | None = None  # time.monotonic() 启动时刻
        self.finished_at: float | None = None  # 结束时刻（运行中为 None）
        self._stop = False
        self._grab = grab_fn or grab_screen
        self._click = click_fn or click_at
        self._key = key_fn or press_key
        self._hotkey = hotkey_fn or press_hotkey
        self._text = text_fn or type_text
        # 脚本模式：构造 auto 桥接对象（局部导入避免循环依赖）
        self.api = None
        if data.script:
            from auto_assets.services.scripting import ScriptAPI

            self.api = ScriptAPI(
                self.path,
                grab=self._grab, click=self._click,
                key=self._key, hotkey=self._hotkey, text=self._text,
                log=self._script_log, stop_flag=lambda: self._stop,
            )

    def _script_log(self, msg: str) -> None:
        self.detail = msg
        self.updated.emit()

    # ---- 控制 ----

    def stop(self) -> None:
        self._stop = True

    # ---- 执行 ----

    def run(self) -> None:  # noqa: C901
        try:
            self.status = "运行中"
            self.started_at = time.monotonic()
            self._run_steps()
            if self._stop:
                self.status = "已停止"
            else:
                self.status = "已完成"
        except ScriptAbort as e:  # 脚本主动终止 → 正常完成
            self.status = "已完成"
            self.detail = f"脚本主动终止: {e}" if str(e) else "脚本主动终止"
        except Exception as e:  # noqa: BLE001
            self.status = "出错"
            self.detail = str(e)
        self.finished_at = time.monotonic()
        self.updated.emit()

    def _run_steps(self) -> None:
        d = self.data
        total_rounds = d.times if d.type == "loop" else 1
        rnd = 0
        while rnd < total_rounds and not self._stop:
            rnd += 1
            self.round_current = rnd  # 供 UI 进度条轮询
            round_txt = f"第 {rnd}/{total_rounds} 轮" if d.type == "loop" else "单次执行"
            if self.api is not None:
                # ---- 脚本模式：忽略 steps，每轮调用一次 main(auto) ----
                self.api.round = rnd
                self.detail = round_txt
                self.updated.emit()
                from auto_assets.services.scripting import run_script  # 局部导入避免循环依赖

                run_script(self.path, d.script, self.api)
            else:
                # ---- 步骤模式 ----
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
