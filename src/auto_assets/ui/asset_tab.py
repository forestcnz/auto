"""素材管理视图：侧栏工程列表 + 工具栏 + 截图墙 + 状态栏 + 框选覆盖层调度。

作为 auto 主窗口顶部 tab「素材管理」的内容（由 ui/main_window.py 承载）。
"""
from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSize, QTimer, Qt
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QGuiApplication,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QListView,
    QMenu,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QStyle,
    QStyledItemDelegate,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from auto_assets.models import Project, Shot
from auto_assets.services.capture import grab_region, logical_to_physical_rect
from auto_assets.services.project import ProjectService
from auto_assets.services import storage
from auto_assets.ui.gallery import ShotGallery
from auto_assets.ui.overlay import CaptureOverlay

SIDEBAR_W = 236


ACCENT = "#374151"  # 石墨灰


class ProjectDelegate(QStyledItemDelegate):
    """工程列表委托：方块选中高亮 + 状态圆点 + mono 计数徽标。

    选中效果明确：实心石墨底 + 白字加粗 + 左侧强调条 + 白圈描边圆点。
    """

    PAD = 8

    def __init__(self, view):
        super().__init__(view)
        self._view = view

    def sizeHint(self, option, index) -> QSize:
        w = self._view.viewport().width() - self.PAD * 2
        return QSize(max(120, w), 36)

    def paint(self, p: QPainter, option, index) -> None:
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(self.PAD, 2, -self.PAD, -2)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        if selected:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(ACCENT))
            p.drawRoundedRect(rect, 3, 3)
            p.setBrush(QColor("#9ca3af"))  # 左侧强调条
            p.drawRect(rect.x(), rect.y(), 3, rect.height())
        elif hovered:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#e6eaef"))
            p.drawRoundedRect(rect, 3, 3)

        # 状态圆点（选中时白圈描边保证可见）
        color = QColor(index.data(Qt.ItemDataRole.UserRole + 1) or ACCENT)
        cx, cy = rect.x() + 13, rect.center().y()
        p.setPen(QPen(QColor("#ffffff") if selected else QColor("#c7cdd5"), 2))
        p.setBrush(color)
        p.drawEllipse(QPoint(cx, int(cy)), 5, 5)

        # 名称（选中加粗白字，超长省略）
        f = p.font()
        f.setBold(selected)
        p.setFont(f)
        p.setPen(QColor("#ffffff") if selected else QColor("#1f2937"))
        name_rect = rect.adjusted(26, 0, -44, 0)
        fm = p.fontMetrics()
        name = fm.elidedText(
            index.data(Qt.ItemDataRole.DisplayRole) or "",
            Qt.TextElideMode.ElideRight,
            max(20, name_rect.width()),
        )
        p.drawText(
            name_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            name,
        )

        # 截图计数（mono 右对齐徽标）
        count = index.data(Qt.ItemDataRole.UserRole + 2)
        if count is not None:
            p.setPen(QColor("#d1d5db") if selected else QColor("#9aa1ab"))
            f = p.font()
            f.setFamily("Consolas")
            f.setPointSize(8)
            p.setFont(f)
            p.drawText(
                rect.adjusted(0, 0, -8, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                f"▸{count}",
            )
        p.restore()


class AssetManagerView(QWidget):
    """素材管理模块视图（auto 顶部第一个 tab）。"""

    def __init__(self, svc: ProjectService | None = None):
        super().__init__()

        self._svc = svc or ProjectService()
        self._project: Project | None = None
        self._overlays: list[CaptureOverlay] = []
        self._capturing = False

        self._build_ui()
        self._build_shortcuts()
        self._restore_last_project()

    # ================= UI 装配 =================

    def _build_ui(self) -> None:
        root = QHBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- 侧栏：工程列表 ----
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(SIDEBAR_W)
        sv = QVBoxLayout(sidebar)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.setSpacing(0)

        cap = QLabel("工  程")
        cap.setObjectName("SidebarCap")
        cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cap.setContentsMargins(0, 12, 0, 8)
        sv.addWidget(cap)

        self.btn_new_proj = QPushButton("＋ 新增工程")
        self.btn_new_proj.setObjectName("BtnNewProject")
        self.btn_new_proj.clicked.connect(self._new_project)
        wrap = QHBoxLayout()
        wrap.setContentsMargins(12, 0, 12, 10)
        wrap.addWidget(self.btn_new_proj)
        sv.addLayout(wrap)

        self.proj_list = QListWidget()
        self.proj_list.setObjectName("ProjList")
        self.proj_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.proj_list.setItemDelegate(ProjectDelegate(self.proj_list))
        self.proj_list.setMouseTracking(True)
        self.proj_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.proj_list.setResizeMode(QListView.ResizeMode.Adjust)
        self.proj_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.proj_list.customContextMenuRequested.connect(self._on_proj_ctx_menu)
        self.proj_list.currentRowChanged.connect(self._on_proj_row_changed)
        sv.addWidget(self.proj_list, 1)

        root.addWidget(sidebar)

        # ---- 右侧工作区 ----
        work = QWidget()
        work.setObjectName("WorkArea")
        wv = QVBoxLayout(work)
        wv.setContentsMargins(0, 0, 0, 0)
        wv.setSpacing(0)

        # 截图墙（先创建，供工具栏搜索框接线）
        self._gallery = ShotGallery()
        self._gallery.saveRequested.connect(self._save_shot)
        self._gallery.renamed.connect(self._rename_shot)
        self._gallery.copyRequested.connect(self._copy_shot)
        self._gallery.deleteRequested.connect(self._delete_shot)
        self._gallery.openRequested.connect(self._open_shot)

        # 工具栏
        bar = QHBoxLayout()
        bar.setContentsMargins(12, 8, 12, 8)
        bar.setSpacing(8)
        self.btn_capture = QPushButton("▣ 开始截图")
        self.btn_capture.setObjectName("BtnCapture")
        self.btn_capture.setToolTip("F1")
        self.btn_capture.clicked.connect(self.start_capture)
        bar.addWidget(self.btn_capture)

        self.btn_export = QToolButton(text="⇩ 导出全部")
        self.btn_export.setObjectName("ToolBtn")
        self.btn_export.clicked.connect(self._export_all)
        bar.addWidget(self.btn_export)

        self.btn_open_dir = QToolButton(text="📂 打开目录")
        self.btn_open_dir.setObjectName("ToolBtn")
        self.btn_open_dir.clicked.connect(self._open_dir)
        bar.addWidget(self.btn_open_dir)

        bar.addStretch(1)

        self.search = QLineEdit(placeholderText="⌕ 按名称搜索截图…")
        self.search.setObjectName("SearchBox")
        self.search.setFixedWidth(210)
        self.search.textChanged.connect(self._gallery.filter)
        bar.addWidget(self.search)

        wv.addLayout(bar)

        # 截图墙 + 空状态
        wv.addWidget(self._gallery, 1)

        self.empty_lbl = QLabel("尚无工程\n\n点击左侧「＋ 新增工程」开始")
        self.empty_lbl.setObjectName("EmptyState")
        self.empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wv.addWidget(self.empty_lbl, 1)

        root.addWidget(work, 1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addLayout(root, 1)

        # 状态栏（视图内底部）
        self._status = QStatusBar()
        outer.addWidget(self._status)
        self._status.showMessage("就绪 · 等待框选")
        self._update_ui_state()

    def _build_shortcuts(self) -> None:
        QShortcut(QKeySequence(Qt.Key.Key_F1), self, self.start_capture)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self._cancel_capture)
        QShortcut(QKeySequence("Ctrl+N"), self, self._new_project)
        QShortcut(QKeySequence("Ctrl+E"), self, self._export_all)

    def _restore_last_project(self) -> None:
        """仅恢复工程列表，不自动加载任何工程（用户点击后再打开）。"""
        self._reload_proj_list()
        self._set_project(None)  # 归一化空状态文案（区分“无工程”与“未选择”）

    # ================= 工程管理 =================

    def _reload_proj_list(self) -> None:
        import json

        self.proj_list.blockSignals(True)
        self.proj_list.clear()
        for r in list(self._svc.config.recent):
            path = Path(r.path)
            if not path.exists():
                self._svc.drop_recent(path)
                continue
            count = 0
            try:
                meta = json.loads((path / "project.json").read_text("utf-8"))
                name = str(meta.get("name") or path.name)
                count = len(meta.get("shots") or [])
            except Exception:
                name = path.name
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, r.path)
            item.setData(Qt.ItemDataRole.UserRole + 1, r.color)
            item.setData(Qt.ItemDataRole.UserRole + 2, count)
            self.proj_list.addItem(item)
            item.setData(Qt.ItemDataRole.UserRole, r.path)
            self.proj_list.addItem(item)
        self.proj_list.blockSignals(False)
        if self._project is None:
            self._set_project(None)  # 同步空状态文案（区分“无工程”与“未选择”）
        self._update_ui_state()

    def _on_proj_row_changed(self, row: int) -> None:
        if row < 0:
            self._set_project(None)
            return
        path = Path(self.proj_list.item(row).data(Qt.ItemDataRole.UserRole))
        try:
            project = self._svc.load_project(path)
        except Exception as e:
            QMessageBox.warning(self, "打开失败", f"无法读取工程:\n{e}")
            self._svc.drop_recent(path)
            self._reload_proj_list()
            return
        self._svc.touch_recent(path)
        self.proj_list.item(row).setSelected(True)  # 确保选中态（委托依赖 State_Selected）
        self._set_project(project)

    def _on_proj_ctx_menu(self, pos) -> None:
        """工程右键菜单：重命名 / 打开目录 / 删除（与项目编辑侧一致）。"""
        item = self.proj_list.itemAt(pos)
        if item is None:
            return
        path = Path(item.data(Qt.ItemDataRole.UserRole))
        row = self.proj_list.row(item)
        path = Path(item.data(Qt.ItemDataRole.UserRole))
        row = self.proj_list.row(item)
        menu = QMenu(self)
        act_rename = menu.addAction("✎ 重命名工程")
        act_open = menu.addAction("📂 打开工程目录")
        menu.addSeparator()
        act_del = menu.addAction("✕ 删除工程")
        act = menu.exec(self.proj_list.viewport().mapToGlobal(pos))
        if act == act_rename:
            self._rename_project(row, path)
        elif act == act_open:
            self._open_dir_at(path)
        elif act == act_del:
            self._delete_project(path)

    def _open_dir_at(self, path: Path) -> None:
        QDesktopServices.openUrl(path.as_uri())

    def _rename_project(self, row: int, path: Path) -> None:
        old = self.proj_list.item(row).text()
        name, ok = QInputDialog.getText(self, "重命名工程", "工程名称：", text=old)
        if not ok or not name.strip() or name.strip() == old:
            return
        try:
            project = self._svc.load_project(path)
        except Exception as e:
            QMessageBox.warning(self, "重命名失败", f"无法读取工程元数据：\n{e}")
            return
        self._svc.rename_project(project, name.strip())
        if self._project is not None and self._project.path == path:
            self._project.meta.name = name.strip()
            self._update_ui_state()
        self._reload_proj_list()
        self._status.showMessage(f"已重命名为「{name.strip()}」", 3000)

    def _delete_project(self, path: Path) -> None:
        try:
            n = len(self._svc.load_project(path).meta.shots)
        except Exception:
            n = 0
        ret = QMessageBox.warning(
            self,
            "删除工程",
            f"确定删除该工程？\n\n{path}\n\n含 {n} 张截图，删除后不可恢复！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        if self._project is not None and self._project.path == path:
            self._set_project(None)
        try:
            self._svc.delete_project(path)
        except OSError as e:
            QMessageBox.warning(self, "删除失败", f"无法删除目录：\n{e}")
            return
        self._reload_proj_list()
        self._status.showMessage(f"已删除工程 → {path.name}", 3000)

    def _new_project(self) -> None:
        if not self.isVisible():
            return
        name, ok = QInputDialog.getText(self, "新增工程", "工程名称：")
        if not ok or not name.strip():
            return
        try:
            project = self._svc.create_project(name)
        except FileExistsError as e:
            QMessageBox.warning(self, "创建失败", str(e))
            return
        self._reload_proj_list()
        # 定位到新工程
        for i in range(self.proj_list.count()):
            if self.proj_list.item(i).data(Qt.ItemDataRole.UserRole) == str(project.path):
                self.proj_list.setCurrentRow(i)
                break
        self._status.showMessage(f'已创建工程「{project.name}」→ {project.path}', 4000)

    def _set_project(self, project: Project | None) -> None:
        self._project = project
        if project is None:
            self._gallery.clear()
            if self.proj_list.count() == 0:
                self.empty_lbl.setText("尚无工程\n\n点击左侧「＋ 新增工程」开始")
            else:
                self.empty_lbl.setText("未选择工程\n\n在左侧列表点击一个工程")
            self.empty_lbl.show()
            self._gallery.hide()
        else:
            pixmaps = {}
            for shot in project.meta.shots:
                tp = project.thumbs_dir / f"{shot.id}.png"
                if tp.exists():
                    pixmaps[shot.id] = QPixmap(str(tp))
            self._gallery.load_project(project, pixmaps)
            self.empty_lbl.hide()
            self._gallery.show()
        self._update_ui_state()

    def _update_ui_state(self) -> None:
        has = self._project is not None
        self.btn_capture.setEnabled(has)
        self.btn_export.setEnabled(has)
        self.btn_open_dir.setEnabled(has)
        n = self._gallery.count_shots()
        if has:
            self._status.showMessage(
                f"工程: {self._project.name} · 截图: {n} 张 · {self._project.path}"
            )

    # ================= 框选截图 =================

    def start_capture(self) -> None:
        if not self.isVisible() or self._project is None or self._capturing:
            return
        self._capturing = True
        self._ensure_overlays()
        for ov in self._overlays:
            ov.show()

    def _ensure_overlays(self) -> None:
        if self._overlays:
            return

        for screen in QGuiApplication.screens():
            ov = CaptureOverlay(screen)
            ov.regionCaptured.connect(self._on_region_captured)
            ov.cancelled.connect(self._cancel_capture)
            self._overlays.append(ov)

    def _hide_overlays(self) -> None:
        for ov in self._overlays:
            ov.hide()

    def _close_overlays(self) -> None:
        self._hide_overlays()
        for ov in self._overlays:
            ov.deleteLater()
        self._overlays.clear()

    def _cancel_capture(self) -> None:
        self._capturing = False
        self._close_overlays()
        self._status.showMessage("已取消框选", 3000)

    def _on_region_captured(self, overlay: CaptureOverlay, rect) -> None:
        """左键松开：先隐藏遮罩再抓屏（避免遮罩入图），完成后自动退出覆盖层。"""
        if self._project is None:
            return
        screen = overlay.screen()
        self._hide_overlays()
        QTimer.singleShot(90, lambda: self._do_capture(screen, QRect(rect)))

    def _do_capture(self, screen, rect) -> None:
        try:
            physical = logical_to_physical_rect(screen, rect)
            img = grab_region(physical)
        except Exception as e:
            QMessageBox.critical(self, "捕获失败", str(e))
            self._capturing = False
            self._close_overlays()
            return

        shot, pixmap = storage.stage_capture(self._project, img)
        self._project.meta.shots.insert(0, shot)
        self._svc.save_meta(self._project)
        self._gallery.add_shot(shot, pixmap, at_top=True)
        self._update_ui_state()
        self._status.showMessage(
            f"已捕获 {shot.width}×{shot.height} · 在卡片上右键保存 / 重命名", 4000
        )
        # 单次捕获：完成即退出覆盖层（再次 F1 重新框选）
        self._capturing = False
        self._close_overlays()

    # ================= 卡片动作 =================

    def _save_shot(self, shot_id: str) -> None:
        shot = self._find_shot(shot_id)
        if shot is None:
            return
        storage.save_shot(self._project, shot)
        self._svc.save_meta(self._project)
        self._gallery.refresh_shot(shot)
        self._status.showMessage(
            f"已保存 → {self._project.path / shot.file}", 4000
        )

    def _rename_shot(self, shot_id: str, new_name: str) -> None:
        shot = self._find_shot(shot_id)
        if shot is None:
            return
        storage.rename_shot(self._project, shot, new_name)
        self._svc.save_meta(self._project)
        self._gallery.refresh_shot(shot)
        self._status.showMessage(f"已重命名为「{shot.name}」", 3000)

    def _copy_shot(self, shot_id: str) -> None:
        from PySide6.QtGui import QGuiApplication

        shot = self._find_shot(shot_id)
        if shot is None:
            return
        pm = storage.load_pixmap(self._project, shot)
        if not pm.isNull():
            QGuiApplication.clipboard().setImage(pm.toImage())
            self._status.showMessage("已复制到剪贴板", 3000)

    def _delete_shot(self, shot_id: str) -> None:
        shot = self._find_shot(shot_id)
        if shot is None:
            return
        ret = QMessageBox.question(
            self, "删除截图", f"确定删除「{shot.name}」？此操作不可撤销。"
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        storage.delete_shot(self._project, shot)
        self._project.meta.shots = [s for s in self._project.meta.shots if s.id != shot.id]
        self._svc.save_meta(self._project)
        self._gallery.remove_shot(shot_id)
        self._update_ui_state()
        self._status.showMessage("已删除", 3000)

    def _open_shot(self, shot_id: str) -> None:
        shot = self._find_shot(shot_id)
        if shot is None:
            return
        path = storage.resolve_file(self._project, shot)
        QDesktopServices.openUrl(path.as_uri())

    def _find_shot(self, shot_id: str) -> Shot | None:
        if self._project is None:
            return None
        for s in self._project.meta.shots:
            if s.id == shot_id:
                return s
        return None

    # ================= 工具栏动作 =================

    def _export_all(self) -> None:
        if not self.isVisible() or self._project is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出全部截图", f"{self._project.name}.zip", "Zip (*.zip)"
        )
        if not path:
            return
        n = storage.export_zip(self._project, Path(path))
        self._status.showMessage(f"已导出 {n} 张 → {path}", 4000)

    def _open_dir(self) -> None:
        if self._project is None:
            return
        self._open_dir_at(self._project.path)

    def shutdown(self) -> None:
        """宿主窗口关闭时调用：释放覆盖层并记录最近工程。"""
        self._close_overlays()
        if self._project is not None:
            self._svc.touch_recent(self._project.path)
