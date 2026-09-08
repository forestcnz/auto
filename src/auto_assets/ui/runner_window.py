"""运行监控小窗：显示运行中的任务，双击停止；关闭窗口返回主界面。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
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
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(2)
        self.title_lbl = QLabel(name)
        self.title_lbl.setStyleSheet("font-weight:700; color:#1f2937;")
        self.state_lbl = QLabel("")
        self.state_lbl.setStyleSheet("font-family:Consolas,monospace; font-size:11px;")
        lay.addWidget(self.title_lbl)
        lay.addWidget(self.state_lbl)

    def update_state(self, status: str, detail: str, score: float | None) -> None:
        color = STATUS_COLORS.get(status, "#8a919c")
        score_txt = f" · score {score:.2f}" if score is not None else ""
        self.state_lbl.setText(f'<span style="color:{color};font-weight:700">● {status}</span>'
                               f'{score_txt} {detail}')
        self.state_lbl.setTextFormat(Qt.TextFormat.RichText)


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

        hint = QLabel("双击任务可停止 · 关闭窗口返回主界面")
        hint.setObjectName("RunnerHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(hint)

        btn_back = QPushButton("返回主界面")
        btn_back.setObjectName("BtnCapture")
        btn_back.clicked.connect(self.close)
        lay.addWidget(btn_back)

    # ---- 任务管理 ----

    def add_task(self, path: Path, data: AutoProject) -> bool:
        key = str(path)
        if key in self._workers and self._workers[key].isRunning():
            return False
        worker = TaskWorker(path, data.model_copy(deep=True))
        row = TaskRow(data.name)
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
            pair[1].update_state(worker.status, worker.detail, worker.last_score)

    def _on_finished(self, worker: TaskWorker) -> None:
        self._refresh(worker)
        self._workers.pop(str(worker.path), None)

    def _on_double_clicked(self, item: QListWidgetItem) -> None:
        for key, (it, _row) in self._rows.items():
            if it is item:
                worker = self._workers.get(key)
                if worker and worker.isRunning():
                    worker.stop()
                    worker.status = "停止中"
                    worker.detail = "等待当前步骤结束…"
                    self._refresh(worker)
                return

    # ---- 关闭 ----

    def closeEvent(self, e) -> None:
        for worker in self._workers.values():
            if worker.isRunning():
                worker.stop()
        for worker in self._workers.values():
            worker.wait(3000)
        self.closed.emit()
        super().closeEvent(e)
