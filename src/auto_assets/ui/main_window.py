"""主窗口外壳：顶部品牌 logo + tab（素材管理 / 项目编辑）+ 视图栈。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from auto_assets.services.project import ProjectService
from auto_assets.ui.asset_tab import AssetManagerView
from auto_assets.ui.edit_tab import ProjectEditView
from auto_assets.ui.logo import logo_pixmap
from auto_assets.ui.runner_window import RunnerWindow


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Auto")
        self.resize(1180, 720)
        self.setMinimumSize(960, 600)

        self._svc = ProjectService()

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- 顶部栏：logo + 品牌 + tab ----
        header = QFrame()
        header.setObjectName("TopBar")
        header.setFixedHeight(46)
        h = QHBoxLayout(header)
        h.setContentsMargins(14, 0, 14, 0)
        h.setSpacing(10)

        logo_lbl = QLabel()
        logo_lbl.setPixmap(logo_pixmap(28))
        h.addWidget(logo_lbl)

        brand = QLabel("Auto")
        brand.setObjectName("BrandName")
        h.addWidget(brand)
        h.addSpacing(8)

        self._tabs = QTabBar()
        self._tabs.setDrawBase(False)
        self._tabs.setExpanding(False)
        self._tabs.setUsesScrollButtons(False)
        self._tabs.addTab("素材管理")
        self._tabs.addTab("项目编辑")
        h.addWidget(self._tabs)
        h.addStretch(1)
        root.addWidget(header)

        # ---- 视图栈 ----
        self._stack = QStackedWidget()
        self._assets = AssetManagerView(self._svc)
        self._stack.addWidget(self._assets)              # index 0: 素材管理
        self._edit_view = ProjectEditView(self._svc)     # index 1: 项目编辑
        self._stack.addWidget(self._edit_view)
        root.addWidget(self._stack, 1)

        self.setCentralWidget(central)
        self._tabs.currentChanged.connect(self._stack.setCurrentIndex)

        # ---- 运行监控 ----
        self._runner: RunnerWindow | None = None
        self._edit_view.runRequested.connect(self._run_project)

    def _run_project(self, path_str: str) -> None:
        """隐藏主窗口，打开运行监控小窗。"""
        path = Path(path_str)
        try:
            from auto_assets.services.automation import AutomationService

            handle = AutomationService(self._svc).load_project(path)
        except Exception as e:
            QMessageBox.warning(self, "运行失败", f"无法读取项目：\n{e}")
            return
        if self._runner is None:
            self._runner = RunnerWindow()
            self._runner.closed.connect(self._on_runner_closed)
        self.hide()
        self._runner.add_task(handle.path, handle.data)
        self._runner.show()
        self._runner.raise_()
        self._runner.activateWindow()

    def _on_runner_closed(self) -> None:
        self.show()
        self.activateWindow()

    def closeEvent(self, e) -> None:
        self._assets.shutdown()
        super().closeEvent(e)
