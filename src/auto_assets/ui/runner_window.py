"""运行监控小窗：显示运行中的任务（轮次进度条 + 耗时），单任务停止/全部停止；关闭窗口返回主界面。"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from auto_assets.models import AutoProject
from auto_assets.services.runner import TaskWorker

STATUS_COLORS = {
    "运行中": "#374151",
    "排队中": "#8a919c",
    "已完成": "#8a919c",
    "已停止": "#dc2626",
    "停止中": "#dc2626",
    "出错": "#dc2626",
}


class TaskRow(QWidget):
    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self._stop_cb = None  # 由 RunnerWindow 注入的停止回调

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(8)

        # 左侧：标题 + 状态 + 轮次进度条（loop 任务可见）
        left = QVBoxLayout()
        left.setSpacing(2)
        self.title_lbl = QLabel(name)
        self.title_lbl.setStyleSheet("font-weight:700; color:#1f2937;")
        self.state_lbl = QLabel("")
        self.state_lbl.setStyleSheet("font-family:Consolas,monospace; font-size:11px;")
        left.addWidget(self.title_lbl)
        left.addWidget(self.state_lbl)

        self.progress = QProgressBar()
        self.progress.setObjectName("TaskProgress")
        self.progress.setVisible(False)
        self.progress.setFixedHeight(14)
        left.addWidget(self.progress)

        lay.addLayout(left, 1)

        # 右侧：单任务停止按钮
        self.btn_stop = QPushButton("■ 停止")
        self.btn_stop.setObjectName("ToolBtn")
        self.btn_stop.setToolTip("停止该任务（等待当前步骤结束）")
        self.btn_stop.clicked.connect(self._on_stop)
        lay.addWidget(self.btn_stop)

    def set_stop_cb(self, cb) -> None:
        self._stop_cb = cb

    def _on_stop(self) -> None:
        if self._stop_cb:
            self._stop_cb()

    def update_state(self, status: str, detail: str, score: float | None,
                     round_cur: int = 0, round_total: int = 0) -> None:
        color = STATUS_COLORS.get(status, "#8a919c")
        score_txt = f" · score {score:.2f}" if score is not None else ""
        self.state_lbl.setText(f'<span style="color:{color};font-weight:700">● {status}</span>'
                               f'{score_txt} {detail}')
        self.state_lbl.setTextFormat(Qt.TextFormat.RichText)

        # 停止按钮状态
        if status == "停止中":
            self.btn_stop.setText("停止中…")
            self.btn_stop.setEnabled(False)
        else:
            self.btn_stop.setText("■ 停止")
            self.btn_stop.setEnabled(status in ("运行中", "排队中"))

        # loop 任务显示轮次进度条（round_total=0 为 any 类型，隐藏）
        if round_total > 1:
            self.progress.setVisible(True)
            self.progress.setRange(0, round_total)
            self.progress.setValue(min(max(round_cur, 0), round_total))
            self.progress.setFormat(f"%v / %m 轮")
        else:
            self.progress.setVisible(False)


class RunnerWindow(QWidget):
    """运行监控窗口（主窗口隐藏后显示）。"""

    closed = Signal()  # 窗口关闭（已停止全部任务），主窗口应恢复显示

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Auto · 运行监控")
        self.resize(420, 320)
        self.setObjectName("RunnerWindow")

        self._workers: dict[str, TaskWorker] = {}
        self._rows: dict[str, tuple[QListWidgetItem, TaskRow]] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        cap = QLabel("运行中的任务")
        cap.setObjectName("SidebarCap")
        lay.addWidget(cap)

        self.list = QListWidget()
        self.list.setObjectName("TaskList")
        self.list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.list.itemDoubleClicked.connect(self._on_double_clicked)
        lay.addWidget(self.list, 1)

        hint = QLabel("停止：点任务右侧「■ 停止」或双击任务行 · 关闭窗口返回主界面")
        hint.setObjectName("RunnerHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(hint)

        btns = QHBoxLayout()
        self.btn_stop_all = QPushButton("■ 全部停止")
        self.btn_stop_all.setObjectName("ToolBtn")
        self.btn_stop_all.setToolTip("停止所有运行中的任务")
        self.btn_stop_all.clicked.connect(self._stop_all)
        btns.addWidget(self.btn_stop_all)
        btns.addStretch(1)
        btn_back = QPushButton("返回主界面")
        btn_back.setObjectName("BtnCapture")
        btn_back.clicked.connect(self.close)
        btns.addWidget(btn_back)
        lay.addLayout(btns)

        # 1s 定时器轮询刷新状态/耗时/进度（TaskWorker 属性由工作线程更新）
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

    # ---- 任务管理 ----

    def add_task(self, path: Path, data: AutoProject) -> bool:
        key = str(path)
        if key in self._workers and self._workers[key].isRunning():
            return False
        worker = TaskWorker(path, data.model_copy(deep=True))
        row = TaskRow(data.name)
        row.set_stop_cb(lambda w=worker: self._request_stop(w))
        item = QListWidgetItem(self.list)
        item.setSizeHint(row.sizeHint())
        self.list.setItemWidget(item, row)
        self._rows[key] = (item, row)
        self._workers[key] = worker
        worker.updated.connect(lambda w=worker: self._refresh(w))
        worker.finished.connect(lambda w=worker: self._on_finished(w))
        worker.start()
        return True

    def _refresh(self, worker: TaskWorker) -> None:
        pair = self._rows.get(str(worker.path))
        if pair:
            # 耗时：运行中实时累计，结束后冻结
            elapsed = ""
            if worker.started_at is not None:
                end = worker.finished_at or time.monotonic()
                elapsed = f" · 耗时 {end - worker.started_at:.0f}s"
            pair[1].update_state(
                worker.status, f"{worker.detail}{elapsed}", worker.last_score,
                worker.round_current, worker.round_total,
            )

    def _on_finished(self, worker: TaskWorker) -> None:
        self._refresh(worker)
        self._workers.pop(str(worker.path), None)

    def _request_stop(self, worker: TaskWorker | None) -> None:
        if worker and worker.isRunning():
            worker.stop()
            worker.status = "停止中"
            worker.detail = "等待当前步骤结束…"
            self._refresh(worker)

    def _stop_all(self) -> None:
        for worker in self._workers.values():
            self._request_stop(worker)

    def _poll(self) -> None:
        for worker in self._workers.values():
            if worker.isRunning():
                self._refresh(worker)

    def _on_double_clicked(self, item: QListWidgetItem) -> None:
        for key, (it, _row) in self._rows.items():
            if it is item:
                self._request_stop(self._workers.get(key))
                return

    # ---- 关闭 ----

    def closeEvent(self, e) -> None:
        self._timer.stop()
        for worker in self._workers.values():
            if worker.isRunning():
                worker.stop()
        for worker in self._workers.values():
            worker.wait(3000)
        self.closed.emit()
        super().closeEvent(e)
