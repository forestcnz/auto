"""项目编辑视图（auto 顶部第二个 tab）。

自动化项目 schema（用户定义，project.json 严格一致）：
{
  "name": "项目名称",
  "type": "any|loop",
  "times": 1000,                     # type=loop 时生效
  "steps": [{
      "template": "templates/xx.png",  # 从素材工程复制过来
      "action": "click",
      "score": 0.85,
      "strategy": "skip|exit"
  }]
}
"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QRegularExpression, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QKeySequence,
    QPixmap,
    QShortcut,
    QTextCharFormat,
    QSyntaxHighlighter,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QListView,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from auto_assets.models import AutoProject, AutoStep, Shot
from auto_assets.services.automation import AutomationService, AutoProjectHandle
from auto_assets.services.project import ProjectService
from auto_assets.services.runner import TaskWorker
from auto_assets.services import storage
from auto_assets.ui.asset_tab import ProjectDelegate

TYPE_LABELS = [("any", "any · 任意"), ("loop", "loop · 整体循环×次数")]
ACTION_LABELS = [("click", "click · 单击"), ("double_click", "double_click · 双击")]

def _strategy_labels(type_: str) -> list[tuple[str, str]]:
    """策略三选：skip 跳过 / loop 重试 / exit 退出。

    注意：策略里的 loop（步骤级循环重试）与项目类型的 loop（整体循环次数）是两回事。
    exit 语义随类型变化：loop 项目里是退出循环，any 项目里是终止流程。
    """
    if type_ == "loop":
        return [
            ("skip", "skip · 跳过本步"),
            ("loop", "loop · 循环重试本步"),
            ("exit", "exit · 退出循环"),
        ]
    return [
        ("skip", "skip · 跳过本步"),
        ("loop", "loop · 循环重试本步"),
        ("exit", "exit · 终止流程"),
    ]


def _combo(labels: list[tuple[str, str]], value: str) -> QComboBox:
    combo = QComboBox()
    for data, text in labels:
        combo.addItem(text, data)
    idx = combo.findData(value)
    combo.setCurrentIndex(max(0, idx))
    return combo


class _PyHighlighter(QSyntaxHighlighter):
    """极简 Python 语法高亮：关键字 / 字符串 / 注释（无第三方依赖，多行字符串不处理）。"""

    def __init__(self, doc):
        super().__init__(doc)
        kw = ("and|as|assert|async|await|break|class|continue|def|del|elif|else|except|"
              "finally|for|from|global|if|import|in|is|lambda|None|nonlocal|not|or|pass|"
              "raise|return|True|False|try|while|with|yield")
        fmt_kw = QTextCharFormat()
        fmt_kw.setForeground(QColor("#374151"))
        fmt_kw.setFontWeight(QFont.Weight.Bold)
        fmt_str = QTextCharFormat()
        fmt_str.setForeground(QColor("#0d9488"))
        fmt_cmt = QTextCharFormat()
        fmt_cmt.setForeground(QColor("#9aa1ab"))
        fmt_cmt.setFontItalic(True)
        # 顺序应用：字符串覆盖关键字、注释最后覆盖（简单近似）
        self._rules = [
            (QRegularExpression(rf"\b(?:{kw})\b"), fmt_kw),
            (QRegularExpression(r"'[^'\n]*'|\"[^\"\n]*\""), fmt_str),
            (QRegularExpression(r"#[^\n]*"), fmt_cmt),
        ]

    def highlightBlock(self, text: str) -> None:
        for rx, fmt in self._rules:
            it = rx.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)


class ScriptEditorDialog(QDialog):
    """Python 脚本编辑器：语法高亮 + Ctrl+S 保存 + 非阻塞试运行（真实执行一轮）。"""

    def __init__(self, auto_svc: AutomationService, auto_dir: Path, rel: str, parent=None):
        super().__init__(parent)
        self._auto = auto_svc
        self._dir = Path(auto_dir)
        self._rel = rel
        self._worker: TaskWorker | None = None
        self.setWindowTitle(f"编辑脚本 · {rel}")
        self.resize(760, 560)

        lay = QVBoxLayout(self)
        self.edit = QPlainTextEdit()
        self.edit.setFont(QFont("Consolas", 10))
        self.edit.setPlainText(self._auto.read_script(self._dir, self._rel))
        self._saved_text = self.edit.toPlainText()  # 关闭时判断未保存改动
        self._hl = _PyHighlighter(self.edit.document())
        lay.addWidget(self.edit, 1)

        self._status = QLabel("")
        self._status.setObjectName("EditStatus")
        self._status.setWordWrap(True)
        lay.addWidget(self._status)

        btns = QHBoxLayout()
        self.btn_run = QPushButton("▶ 试运行")
        self.btn_run.setObjectName("BtnCapture")
        self.btn_run.setToolTip("先保存，然后真实执行一轮：将截屏，且可能点击鼠标 / 输入按键")
        self.btn_run.clicked.connect(self._dry_run)
        btns.addWidget(self.btn_run)
        btns.addStretch(1)
        btn_save = QPushButton("保存")
        btn_save.setObjectName("ToolBtn")
        btn_save.clicked.connect(self._save)
        btns.addWidget(btn_save)
        btn_close = QPushButton("关闭")
        btn_close.setObjectName("ToolBtn")
        btn_close.clicked.connect(self.close)
        btns.addWidget(btn_close)
        lay.addLayout(btns)

        QShortcut(QKeySequence.StandardKey.Save, self, self._save)

    # ---- 保存 ----

    def _save(self) -> bool:
        try:
            self._auto.save_script(self._dir, self._rel, self.edit.toPlainText())
        except OSError as e:
            QMessageBox.warning(self, "保存失败", str(e))
            return False
        self._saved_text = self.edit.toPlainText()
        self._status.setText(f"已保存 {self._rel} · {time.strftime('%H:%M:%S')}")
        return True

    # ---- 试运行 ----

    def _dry_run(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(self, "提示", "试运行进行中，请稍候")
            return
        ret = QMessageBox.warning(
            self, "试运行",
            "将真实截屏，且可能点击鼠标 / 输入按键。\n\n确定执行一轮？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        if not self._save():  # 先落盘，运行引擎从磁盘读脚本
            return
        data = AutoProject(name="试运行", type="any", times=1, script=self._rel)
        self._worker = TaskWorker(self._dir, data)
        self._worker.updated.connect(self._on_run_update)
        self._worker.finished.connect(self._on_run_done)
        self._worker.start()
        self.btn_run.setEnabled(False)
        self._status.setText("试运行中…")

    def _on_run_update(self) -> None:
        if self._worker is not None:
            self._status.setText(f"[{self._worker.status}] {self._worker.detail}")

    def _on_run_done(self) -> None:
        if self._worker is not None:
            self._status.setText(f"试运行结束 · [{self._worker.status}] {self._worker.detail}")
        self.btn_run.setEnabled(True)

    # ---- 关闭 ----

    def closeEvent(self, e) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(3000)
        if self.edit.toPlainText() != self._saved_text:
            ret = QMessageBox.question(
                self, "未保存", "脚本已修改但未保存，保存并关闭？",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if ret == QMessageBox.StandardButton.Save:
                if not self._save():
                    e.ignore()
                    return
            elif ret != QMessageBox.StandardButton.Discard:
                e.ignore()
                return
        super().closeEvent(e)


class TemplatePicker(QDialog):
    """从素材工程选择模板：选中后由调用方复制到自动化项目。"""

    def __init__(self, svc: ProjectService, parent=None):
        super().__init__(parent)
        self.setWindowTitle("从素材工程选择模板")
        self.resize(640, 440)
        self.result_source: Path | None = None
        self._svc = svc

        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("素材工程:"))
        self.proj_combo = QComboBox()
        for r in svc.config.recent:
            p = Path(r.path)
            if not p.exists():
                continue
            try:
                display = svc.load_project(p).name  # 只显示工程名称
            except Exception:
                display = p.name
            self.proj_combo.addItem(display, r.path)
        top.addWidget(self.proj_combo, 1)
        lay.addLayout(top)

        self.gallery = QListWidget()
        self.gallery.setViewMode(QListWidget.ViewMode.IconMode)
        self.gallery.setIconSize(QSize(96, 54))
        self.gallery.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.gallery.setMinimumHeight(280)
        lay.addWidget(self.gallery, 1)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        self.proj_combo.currentIndexChanged.connect(self._load_shots)
        if self.proj_combo.count():
            self._load_shots()

    def _load_shots(self) -> None:
        self.gallery.clear()
        path = Path(self.proj_combo.currentData() or "")
        if not path.exists():
            return
        try:
            project = self._svc.load_project(path)
        except Exception as e:
            QMessageBox.warning(self, "读取失败", str(e))
            return
        for shot in reversed(project.meta.shots):
            tp = project.thumbs_dir / f"{shot.id}.png"
            pm = QPixmap(str(tp)) if tp.exists() else QPixmap()
            item = QListWidgetItem(pm, shot.name)
            item.setData(Qt.ItemDataRole.UserRole, shot.id)
            item.setData(
                Qt.ItemDataRole.UserRole + 1,
                str(storage.resolve_file(project, shot)),
            )
            self.gallery.addItem(item)

    def _accept(self) -> None:
        item = self.gallery.currentItem()
        if item is None:
            QMessageBox.information(self, "提示", "请先选择一张模板截图")
            return
        self.result_source = Path(item.data(Qt.ItemDataRole.UserRole + 1))
        self.accept()


class ProjectEditView(QWidget):
    """项目编辑：自动化项目列表 + 步骤编辑器。"""

    runRequested = Signal(str)  # 项目路径，请求运行

    def __init__(self, svc: ProjectService, root: str | None = None):
        super().__init__()
        self._svc = svc
        self._auto = AutomationService(svc, root)
        self._handle: AutoProjectHandle | None = None
        self._loading = False

        self._build_ui()
        self._reload_list()
        self._set_project(None)

    # ================= UI =================

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- 侧栏 ----
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(236)
        sv = QVBoxLayout(sidebar)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.setSpacing(0)

        cap = QLabel("自动化项目")
        cap.setObjectName("SidebarCap")
        cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cap.setContentsMargins(0, 12, 0, 8)
        sv.addWidget(cap)

        self.btn_new = QPushButton("＋ 新建项目")
        self.btn_new.setObjectName("BtnNewProject")
        self.btn_new.clicked.connect(self._new_project)
        wrap = QHBoxLayout()
        wrap.setContentsMargins(12, 0, 12, 10)
        wrap.addWidget(self.btn_new)
        sv.addLayout(wrap)

        self.proj_list = QListWidget()
        self.proj_list.setObjectName("ProjList")
        self.proj_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.proj_list.setItemDelegate(ProjectDelegate(self.proj_list))
        self.proj_list.setMouseTracking(True)
        self.proj_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.proj_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.proj_list.setResizeMode(QListView.ResizeMode.Adjust)
        self.proj_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.proj_list.customContextMenuRequested.connect(self._on_proj_ctx_menu)
        self.proj_list.currentRowChanged.connect(self._on_row_changed)
        sv.addWidget(self.proj_list, 1)

        root.addWidget(sidebar)

        # ---- 编辑区 ----
        editor = QWidget()
        editor.setObjectName("WorkArea")
        ev = QVBoxLayout(editor)
        ev.setContentsMargins(16, 12, 16, 10)
        ev.setSpacing(10)

        form = QHBoxLayout()
        form.setSpacing(8)
        form.addWidget(QLabel("项目名称:"))
        self.name_edit = QLineEdit()
        self.name_edit.setMinimumWidth(160)
        self.name_edit.editingFinished.connect(self._on_name_changed)
        form.addWidget(self.name_edit)
        form.addWidget(QLabel("类型:"))
        self.type_combo = _combo(TYPE_LABELS, "any")
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        form.addWidget(self.type_combo)
        form.addWidget(QLabel("循环次数:"))
        self.times_spin = QSpinBox()
        self.times_spin.setRange(1, 100_000_000)
        self.times_spin.setValue(1000)
        self.times_spin.valueChanged.connect(self._on_times_changed)
        form.addWidget(self.times_spin)
        form.addStretch(1)
        self.btn_run = QPushButton("▶ 运行")
        self.btn_run.setObjectName("BtnCapture")
        self.btn_run.setToolTip("隐藏主窗口，打开运行监控；双击任务可停止")
        self.btn_run.clicked.connect(self._run_project)
        form.addWidget(self.btn_run)
        ev.addLayout(form)

        # ---- 脚本行：选择 Python 脚本后为脚本模式（运行时忽略步骤） ----
        srow = QHBoxLayout()
        srow.setSpacing(8)
        srow.addWidget(QLabel("脚本:"))
        self.script_combo = QComboBox()
        self.script_combo.setToolTip(
            "选择 Python 脚本（scripts/xx.py）后为脚本模式：运行时忽略下方步骤列表"
        )
        self.script_combo.currentIndexChanged.connect(self._on_script_changed)
        srow.addWidget(self.script_combo, 1)
        self.btn_edit_script = QPushButton("✎ 编辑")
        self.btn_edit_script.setObjectName("ToolBtn")
        self.btn_edit_script.setToolTip("打开脚本编辑器（语法高亮 / Ctrl+S 保存 / 试运行）")
        self.btn_edit_script.clicked.connect(self._edit_script)
        srow.addWidget(self.btn_edit_script)
        self.btn_new_script = QPushButton("＋ 新建")
        self.btn_new_script.setObjectName("ToolBtn")
        self.btn_new_script.setToolTip("新建脚本并启用脚本模式")
        self.btn_new_script.clicked.connect(self._new_script)
        srow.addWidget(self.btn_new_script)
        self.btn_del_script = QPushButton("✕ 删除")
        self.btn_del_script.setObjectName("ToolBtn")
        self.btn_del_script.setToolTip("删除选中的脚本文件")
        self.btn_del_script.clicked.connect(self._delete_script)
        srow.addWidget(self.btn_del_script)
        ev.addLayout(srow)

        head = QHBoxLayout()
        title = QLabel("步骤 Steps")
        title.setObjectName("SidebarCap")
        head.addWidget(title)
        head.addStretch(1)
        self.btn_add_step = QPushButton("＋ 添加步骤")
        self.btn_add_step.setObjectName("ToolBtn")
        self.btn_add_step.clicked.connect(self._add_step)
        head.addWidget(self.btn_add_step)
        ev.addLayout(head)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["#", "模板", "动作", "阈值 score", "失败策略", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setColumnWidth(0, 36)
        self.table.setColumnWidth(1, 240)
        self.table.setColumnWidth(2, 130)
        self.table.setColumnWidth(3, 120)
        self.table.setColumnWidth(4, 150)
        self.table.setColumnWidth(5, 110)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setStyleSheet("QTableWidget::item{padding:4px;}")
        # 行右键菜单（放大预览 / 替换模板 / 复制 / 上移 / 下移 / 删除）
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_step_ctx_menu)
        # 点击模板列放大预览
        self.table.cellClicked.connect(self._on_cell_clicked)
        ev.addWidget(self.table, 1)

        self.empty_lbl = QLabel("未选择项目\n\n点击左侧「＋ 新建项目」开始")
        self.empty_lbl.setObjectName("EmptyState")
        self.empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ev.addWidget(self.empty_lbl, 1)

        self._status = QLabel("")
        self._status.setObjectName("EditStatus")
        ev.addWidget(self._status)

        root.addWidget(editor, 1)
        self._editor_widgets = [
            self.name_edit, self.type_combo, self.times_spin,
            self.btn_add_step, self.table,
            self.script_combo, self.btn_edit_script, self.btn_new_script, self.btn_del_script,
        ]

    # ================= 项目切换 =================

    def _reload_list(self) -> None:
        self.proj_list.blockSignals(True)
        self.proj_list.clear()
        for h in self._auto.list_projects():
            item = QListWidgetItem(h.data.name)  # 只显示名称
            item.setData(Qt.ItemDataRole.UserRole, str(h.path))
            item.setData(Qt.ItemDataRole.UserRole + 2, len(h.data.steps))  # 徽标：步骤数
            self.proj_list.addItem(item)
        self.proj_list.blockSignals(False)
        self._sync_selection()

    def _sync_selection(self) -> None:
        """列表重建后，恢复当前打开项目的选中态。"""
        if self._handle is None:
            return
        key = str(self._handle.path)
        for i in range(self.proj_list.count()):
            if self.proj_list.item(i).data(Qt.ItemDataRole.UserRole) == key:
                self.proj_list.blockSignals(True)
                self.proj_list.setCurrentRow(i)
                self.proj_list.blockSignals(False)
                self.proj_list.item(i).setSelected(True)
                return

    def _on_row_changed(self, row: int) -> None:
        if row < 0:
            self._set_project(None)
            return
        path = Path(self.proj_list.item(row).data(Qt.ItemDataRole.UserRole))
        try:
            self._set_project(self._auto.load_project(path))
        except Exception as e:
            QMessageBox.warning(self, "打开失败", f"无法读取项目:\n{e}")
            self._set_project(None)

    def _set_project(self, handle: AutoProjectHandle | None) -> None:
        self._handle = handle
        has = handle is not None
        for w in self._editor_widgets:
            w.setVisible(has)
        self.empty_lbl.setVisible(not has)
        if not has:
            if self.proj_list.count() == 0:
                self.empty_lbl.setText("尚无自动化项目\n\n点击左侧「＋ 新建项目」开始")
            else:
                self.empty_lbl.setText("未选择项目\n\n在左侧列表点击一个项目")
            return
        self._loading = True
        d = handle.data
        self.name_edit.setText(d.name)
        self.type_combo.setCurrentIndex(max(0, self.type_combo.findData(d.type)))
        self.times_spin.setValue(max(1, d.times))
        self.times_spin.setEnabled(d.type == "loop")
        self._reload_scripts()
        self._rebuild_table()
        self._loading = False
        script_hint = f" · 脚本模式 {d.script}" if d.script else ""
        self._status.setText(f"已打开 {handle.path}{script_hint}")

    # ================= 脚本 =================

    def _reload_scripts(self) -> None:
        """刷新脚本下拉（首项 = 无脚本/步骤模式），并同步当前选择。"""
        self.script_combo.blockSignals(True)
        self.script_combo.clear()
        self.script_combo.addItem("（无 · 步骤模式）", "")
        if self._handle is not None:
            for rel in self._auto.list_scripts(self._handle.path):
                self.script_combo.addItem(rel, rel)
            idx = self.script_combo.findData(self._handle.data.script or "")
            self.script_combo.setCurrentIndex(max(0, idx))
        self.script_combo.blockSignals(False)
        self._update_script_buttons()

    def _update_script_buttons(self) -> None:
        has_file = bool(self.script_combo.currentData())
        self.btn_edit_script.setEnabled(has_file)
        self.btn_del_script.setEnabled(has_file)
        self.btn_new_script.setEnabled(self._handle is not None)

    def _on_script_changed(self) -> None:
        self._update_script_buttons()
        if self._loading or self._handle is None:
            return
        val = self.script_combo.currentData() or ""
        if val == (self._handle.data.script or ""):
            return
        self._handle.data.script = val
        self._save_and_refresh("已切换为脚本模式" if val else "已切换为步骤模式")

    def _new_script(self) -> None:
        if self._handle is None:
            return
        name, ok = QInputDialog.getText(self, "新建脚本", "脚本名称（不含 .py）：")
        if not ok or not name.strip():
            return
        try:
            rel = self._auto.create_script(self._handle.path, name)
        except OSError as e:
            QMessageBox.warning(self, "创建失败", str(e))
            return
        self._handle.data.script = rel  # 新建即启用脚本模式
        self._save_and_refresh(f"已新建脚本 {rel} · 已自动保存")
        self._reload_scripts()
        self._edit_script()

    def _edit_script(self) -> None:
        if self._handle is None:
            return
        rel = self.script_combo.currentData() or ""
        if not rel:
            return
        dlg = ScriptEditorDialog(self._auto, self._handle.path, rel, self)
        dlg.exec()

    def _delete_script(self) -> None:
        if self._handle is None:
            return
        rel = self.script_combo.currentData() or ""
        if not rel:
            return
        ret = QMessageBox.warning(
            self, "删除脚本", f"确定删除脚本？\n\n{rel}\n\n删除后不可恢复！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        try:
            self._auto.delete_script(self._handle.path, rel)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "删除失败", str(e))
            return
        if self._handle.data.script == rel:
            self._handle.data.script = ""
            self._save_and_refresh("脚本已删除 · 已自动保存")
        self._reload_scripts()
        self._status.setText(f"已删除脚本 {rel}")

    # ================= 表格 =================

    def _rebuild_table(self) -> None:
        self.table.setRowCount(0)
        if self._handle is None:
            return
        for i, step in enumerate(self._handle.data.steps):
            self.table.insertRow(i)
            self._fill_row(i, step)
        if self._handle.data.steps:
            self.table.setRowHeight(0, 60)

    def _fill_row(self, row: int, step: AutoStep) -> None:
        idx = QTableWidgetItem(str(row + 1))
        idx.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, 0, idx)

        # 模板：缩略图 + 文件名（点击放大预览，右键更多操作）
        tpl_path = self._handle.path / step.template if step.template else None
        pm = QPixmap(str(tpl_path)) if tpl_path and tpl_path.exists() else QPixmap()
        item = QTableWidgetItem(Path(step.template).name if step.template else "(未设置)")
        if not pm.isNull():
            item.setIcon(pm.scaled(
                96, 48,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        item.setData(Qt.ItemDataRole.UserRole, step.template)
        item.setToolTip(f"{step.template}\n点击放大预览 · 右键更多操作")
        self.table.setItem(row, 1, item)

        act = _combo(ACTION_LABELS, step.action)
        act.currentIndexChanged.connect(lambda _i, r=row: self._on_action_changed(r))
        self.table.setCellWidget(row, 2, act)

        score = QDoubleSpinBox()
        score.setRange(0.05, 1.0)
        score.setSingleStep(0.01)
        score.setValue(step.score)
        score.setDecimals(2)
        score.setAlignment(Qt.AlignmentFlag.AlignCenter)
        score.setKeyboardTracking(False)  # 避免输入过程中频繁写盘
        score.setToolTip("匹配阈值 0.05 ~ 1.00，默认 0.85")
        score.valueChanged.connect(lambda _v, r=row: self._on_score_changed(r))
        self.table.setCellWidget(row, 3, score)

        strat = _combo(_strategy_labels(self._handle.data.type), step.strategy)
        strat.currentIndexChanged.connect(lambda _i, r=row: self._on_strategy_changed(r))
        self.table.setCellWidget(row, 4, strat)

        # 末列操作组：↑ 上移 / ↓ 下移 / ✕ 删除
        ops = QWidget()
        ops_lay = QHBoxLayout(ops)
        ops_lay.setContentsMargins(0, 0, 0, 0)
        ops_lay.setSpacing(2)
        btn_up = QPushButton("↑")
        btn_up.setToolTip("上移此步骤")
        btn_up.clicked.connect(lambda _c=False, r=row: self._move_step(r, -1))
        btn_down = QPushButton("↓")
        btn_down.setToolTip("下移此步骤")
        btn_down.clicked.connect(lambda _c=False, r=row: self._move_step(r, 1))
        btn_del = QPushButton("✕")
        btn_del.setToolTip("删除此步骤")
        btn_del.clicked.connect(lambda _c=False, r=row: self._remove_step(r))
        for b in (btn_up, btn_down, btn_del):
            b.setFixedWidth(30)
            ops_lay.addWidget(b)
        self.table.setCellWidget(row, 5, ops)
        self.table.setRowHeight(row, 60)

    def _steps_mutated(self, msg: str) -> None:
        if self._loading or self._handle is None:
            return
        self._auto.save_project(self._handle)
        self._status.setText(f"{msg} · 已自动保存")

    def _on_action_changed(self, row: int) -> None:
        if self._handle is None or row >= len(self._handle.data.steps):
            return
        combo = self.table.cellWidget(row, 2)
        self._handle.data.steps[row].action = combo.currentData()
        self._steps_mutated("动作已更新")

    def _on_score_changed(self, row: int) -> None:
        if self._handle is None or row >= len(self._handle.data.steps):
            return
        spin = self.table.cellWidget(row, 3)
        self._handle.data.steps[row].score = round(spin.value(), 2)
        self._steps_mutated("阈值已更新")

    def _on_strategy_changed(self, row: int) -> None:
        if self._handle is None or row >= len(self._handle.data.steps):
            return
        combo = self.table.cellWidget(row, 4)
        self._handle.data.steps[row].strategy = combo.currentData()
        self._steps_mutated("失败策略已更新")

    def _remove_step(self, row: int) -> None:
        if self._handle is None or row >= len(self._handle.data.steps):
            return
        del self._handle.data.steps[row]
        self._rebuild_table()
        self._steps_mutated("步骤已删除")

    # ================= 步骤操作：排序 / 复制 / 替换模板 / 放大预览 =================

    def _move_step(self, row: int, delta: int) -> None:
        """上移（delta=-1）/ 下移（delta=+1）步骤，越界为静默 no-op。"""
        if self._handle is None or self._loading:
            return
        steps = self._handle.data.steps
        new_row = row + delta
        if row < 0 or row >= len(steps) or new_row < 0 or new_row >= len(steps):
            return
        steps[row], steps[new_row] = steps[new_row], steps[row]
        self._rebuild_table()
        self._steps_mutated(f"步骤已{'上移' if delta < 0 else '下移'}")

    def _copy_step(self, row: int) -> None:
        """复制步骤：在原步骤后插入副本（template 文件共享，不重复拷贝）。"""
        if self._handle is None or row < 0 or row >= len(self._handle.data.steps):
            return
        src = self._handle.data.steps[row]
        self._handle.data.steps.insert(row + 1, src.model_copy(deep=True))
        self._rebuild_table()
        self._steps_mutated(f"已复制步骤 {row + 1}")

    def _replace_template(self, row: int) -> None:
        """替换模板：重新选图复制进 templates/（重名自动加 _1），旧文件保留（可能被其他步骤引用）。"""
        if self._handle is None or row < 0 or row >= len(self._handle.data.steps):
            return
        dlg = TemplatePicker(self._svc, self)
        if dlg.exec() != QDialog.DialogCode.Accepted or dlg.result_source is None:
            return
        if not dlg.result_source.exists():
            QMessageBox.warning(self, "模板不可用", "源截图文件不存在（可能是未保存的素材）")
            return
        rel = self._auto.import_template(self._handle.path, dlg.result_source)
        self._handle.data.steps[row].template = rel
        self._rebuild_table()
        self._steps_mutated(f"步骤 {row + 1} 已替换模板（复制自 {dlg.result_source.name}）")

    def _preview_template(self, row: int) -> None:
        """放大预览模板：原始尺寸自适应大图 + 文件信息。"""
        if self._handle is None or row < 0 or row >= len(self._handle.data.steps):
            return
        rel = self._handle.data.steps[row].template
        path = self._handle.path / rel if rel else None
        if not path or not path.exists():
            QMessageBox.warning(self, "预览失败", f"模板文件不存在：\n{rel}")
            return
        pm = QPixmap(str(path))
        if pm.isNull():
            QMessageBox.warning(self, "预览失败", f"无法读取模板图像：\n{rel}")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"模板预览 · {Path(rel).name}")
        lay = QVBoxLayout(dlg)
        lbl = QLabel()
        lbl.setPixmap(pm.scaled(
            800, 560,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl)
        info = QLabel(f"{pm.width()} × {pm.height()} px · {rel}")
        info.setObjectName("EditStatus")
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(info)
        dlg.exec()

    def _on_cell_clicked(self, row: int, col: int) -> None:
        if col == 1:
            self._preview_template(row)

    def _on_step_ctx_menu(self, pos) -> None:
        """步骤行右键菜单：预览 / 替换模板 / 复制 / 上移 / 下移 / 删除。"""
        row = self.table.rowAt(pos.y())
        if row < 0 or self._handle is None or row >= len(self._handle.data.steps):
            return
        menu = QMenu(self)
        act_preview = menu.addAction("🔍 放大预览")
        act_replace = menu.addAction("🔄 替换模板")
        act_copy = menu.addAction("⧉ 复制步骤")
        menu.addSeparator()
        act_up = menu.addAction("↑ 上移")
        act_down = menu.addAction("↓ 下移")
        menu.addSeparator()
        act_del = menu.addAction("✕ 删除步骤")
        act = menu.exec(self.table.viewport().mapToGlobal(pos))
        if act == act_preview:
            self._preview_template(row)
        elif act == act_replace:
            self._replace_template(row)
        elif act == act_copy:
            self._copy_step(row)
        elif act == act_up:
            self._move_step(row, -1)
        elif act == act_down:
            self._move_step(row, 1)
        elif act == act_del:
            self._remove_step(row)

    # ================= 字段编辑 =================

    def _on_name_changed(self) -> None:
        if self._loading or self._handle is None:
            return
        new = self.name_edit.text().strip()
        if not new or new == self._handle.data.name:
            return
        old_path = self._handle.path
        try:
            new_path = self._auto.rename_project(self._handle, new)
        except FileExistsError as e:
            QMessageBox.warning(self, "重命名失败", str(e))
            self.name_edit.setText(self._handle.data.name)
            return
        except OSError as e:
            QMessageBox.warning(self, "重命名失败", str(e))
            return
        self._handle.path = new_path
        self._reload_list()
        self._status.setText(f"已重命名为「{self._handle.data.name}」")

    def _on_type_changed(self) -> None:
        if self._loading or self._handle is None:
            return
        self._handle.data.type = self.type_combo.currentData()
        self.times_spin.setEnabled(self._handle.data.type == "loop")
        self._save_and_refresh("类型已更新")
        self._rebuild_table()  # 刷新失败策略文案（exit 语义随类型变化）

    def _on_times_changed(self) -> None:
        if self._loading or self._handle is None:
            return
        self._handle.data.times = self.times_spin.value()
        self._save_and_refresh("循环次数已更新")

    def _save_and_refresh(self, msg: str) -> None:
        self._auto.save_project(self._handle)
        self._reload_list()
        self._status.setText(f"{msg} · 已自动保存")

    # ================= 运行 =================

    def _run_project(self) -> None:
        if self._handle is None:
            return
        self.runRequested.emit(str(self._handle.path))

    # ================= 动作 =================

    # ================= 右键菜单：重命名 / 打开目录 / 删除 =================

    def _on_proj_ctx_menu(self, pos) -> None:
        item = self.proj_list.itemAt(pos)
        if item is None:
            return
        path = Path(item.data(Qt.ItemDataRole.UserRole))
        menu = QMenu(self)
        act_rename = menu.addAction("✎ 重命名项目")
        act_open = menu.addAction("📂 打开项目目录")
        menu.addSeparator()
        act_del = menu.addAction("✕ 删除项目")
        act = menu.exec(self.proj_list.viewport().mapToGlobal(pos))
        if act == act_rename:
            self._rename_project_dialog(path)
        elif act == act_open:
            self._open_dir_at(path)
        elif act == act_del:
            self._confirm_delete(path)

    def _rename_project_dialog(self, path: Path) -> None:
        try:
            handle = self._auto.load_project(path)
        except Exception as e:
            QMessageBox.warning(self, "重命名失败", f"无法读取项目：\n{e}")
            return
        old = handle.data.name
        name, ok = QInputDialog.getText(self, "重命名项目", "项目名称：", text=old)
        if not ok or not name.strip() or name.strip() == old:
            return
        was_open = self._handle is not None and self._handle.path == path
        try:
            new_path = self._auto.rename_project(handle, name)
        except FileExistsError as e:
            QMessageBox.warning(self, "重命名失败", str(e))
            return
        except OSError as e:
            QMessageBox.warning(self, "重命名失败", str(e))
            return
        if was_open:
            self._handle.path = new_path
            self._handle.data.name = handle.data.name
            self.name_edit.setText(handle.data.name)
            self._auto.save_project(self._handle)
        self._reload_list()
        self._status.setText(f"已重命名为「{handle.data.name}」")

    def _confirm_delete(self, path: Path) -> None:
        ret = QMessageBox.warning(
            self, "删除项目",
            f"确定删除自动化项目？\n\n{path}\n\n含 templates 模板与配置，删除后不可恢复！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        was_open = self._handle is not None and self._handle.path == path
        if was_open:
            self._set_project(None)
        try:
            self._auto.delete_project(path)
        except OSError as e:
            QMessageBox.warning(self, "删除失败", str(e))
            return
        self._reload_list()
        self._status.setText(f"已删除项目 → {path.name}")

    def _new_project(self) -> None:
        name, ok = QInputDialog.getText(self, "新建自动化项目", "项目名称：")
        if not ok or not name.strip():
            return
        type_, ok2 = QInputDialog.getItem(
            self, "项目类型", "类型：", [t for _, t in TYPE_LABELS], 0, False
        )
        if not ok2:
            return
        type_val = TYPE_LABELS[[t for _, t in TYPE_LABELS].index(type_)][0]
        times = 1000
        if type_val == "loop":
            times, ok3 = QInputDialog.getInt(self, "循环次数", "次数：", 1000, 1, 100_000_000)
            if not ok3:
                return
        try:
            handle = self._auto.create_project(name, type_val, times)
        except FileExistsError as e:
            QMessageBox.warning(self, "创建失败", str(e))
            return
        self._reload_list()
        for i in range(self.proj_list.count()):
            if self.proj_list.item(i).data(Qt.ItemDataRole.UserRole) == str(handle.path):
                self.proj_list.setCurrentRow(i)
                break
        self._status.setText(f"已创建项目「{handle.data.name}」")

    def _add_step(self) -> None:
        if self._handle is None:
            return
        dlg = TemplatePicker(self._svc, self)
        if dlg.exec() != QDialog.DialogCode.Accepted or dlg.result_source is None:
            return
        if not dlg.result_source.exists():
            QMessageBox.warning(self, "模板不可用", "源截图文件不存在（可能是未保存的素材）")
            return
        rel = self._auto.import_template(self._handle.path, dlg.result_source)
        self._handle.data.steps.append(
            AutoStep(template=rel, action="click", score=0.85, strategy="skip")
        )
        self._rebuild_table()
        self._steps_mutated(f"已添加步骤（复制自 {dlg.result_source.name}）")

    def _open_dir_at(self, path: Path) -> None:
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(path.as_uri())
