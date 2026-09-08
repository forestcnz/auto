"""截图墙（ShotGallery）：卡片列表 + 行内重命名 + 右键菜单。

卡片为“暂存/已保存”二态（DESIGN.md §4.3 / §5.3）：
- ○ 未保存（未保存，红）：右键保存后变 ● 已保存（绿）
- 右键菜单：保存 / 重命名 / 复制 / 删除
- 双击：系统看图器打开
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QContextMenuEvent, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QVBoxLayout,
    QWidget,
)

from auto_assets.models import Project, Shot

ACCENT = "#374151"
RED = "#dc2626"
GREEN = "#4b5563"


def _status_text(shot: Shot) -> str:
    if shot.saved:
        return f'<span style="color:{GREEN}">● 已保存</span>'
    return f'<span style="color:{RED}">○ 未保存</span>'


class ShotCard(QWidget):
    """单张截图卡片。"""

    saveRequested = Signal(str)      # shot_id
    renamed = Signal(str, str)       # shot_id, new_name
    copyRequested = Signal(str)      # shot_id
    deleteRequested = Signal(str)    # shot_id
    openRequested = Signal(str)      # shot_id

    def __init__(self, shot: Shot, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.setObjectName("ShotCard")
        self.shot = shot
        self._thumb = pixmap
        self._renaming = False
        # 点选卡片后快捷键生效（F2 / Del / Ctrl+S）
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        for keys, cb in (
            ("F2", self.start_rename),
            ("Del", lambda: self.deleteRequested.emit(self.shot.id)),
            ("Ctrl+S", lambda: self.saveRequested.emit(self.shot.id)),
        ):
            sc = QShortcut(QKeySequence(keys), self)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(cb)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 8)
        lay.setSpacing(5)

        self.thumb_lbl = QLabel()
        self.thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_lbl.setFixedHeight(122)
        self.thumb_lbl.setPixmap(
            pixmap.scaled(
                224, 122,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        lay.addWidget(self.thumb_lbl)

        self.name_lbl = QLabel(shot.name)
        self.name_lbl.setObjectName("ShotName")
        self.name_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        lay.addWidget(self.name_lbl)

        meta_txt = (
            f'{shot.width}×{shot.height} · '
            f'{shot.created_at.strftime("%H:%M:%S")} · {_status_text(shot)}'
        )
        self.meta_lbl = QLabel(meta_txt)
        self.meta_lbl.setObjectName("ShotMeta")
        lay.addWidget(self.meta_lbl)

    # ---------- 状态刷新 ----------

    def refresh(self, shot: Shot) -> None:
        self.shot = shot
        self.name_lbl.setText(shot.name)
        self.meta_lbl.setText(
            f'{shot.width}×{shot.height} · '
            f'{shot.created_at.strftime("%H:%M:%S")} · {_status_text(shot)}'
        )

    # ---------- 行内重命名 ----------

    def start_rename(self) -> None:
        if self._renaming:
            return
        self._renaming = True
        editor = QLineEdit(self.shot.name, self)
        editor.selectAll()
        editor.setStyleSheet(
            "QLineEdit{background:#ffffff;border:1px solid %s;border-radius:4px;"
            "padding:2px 6px;font-size:12.5px;color:#1f2937}" % ACCENT
        )
        self.name_lbl.hide()
        self.layout().insertWidget(1, editor)
        editor.setFixedWidth(self.name_lbl.width())
        editor.setFocus()

        def finish(save: bool) -> None:
            if not self._renaming:
                return
            self._renaming = False
            text = editor.text().strip()
            editor.blockSignals(True)
            editor.deleteLater()
            self.name_lbl.show()
            if save and text and text != self.shot.name:
                self.renamed.emit(self.shot.id, text)

        editor.returnPressed.connect(lambda: finish(True))
        editor.editingFinished.connect(lambda: finish(True))

        orig_key = editor.keyPressEvent

        def key_press(e) -> None:  # noqa: ANN001
            if e.key() == Qt.Key.Key_Escape:
                editor.blockSignals(True)
                finish(False)
                return
            orig_key(e)

        editor.keyPressEvent = key_press  # type: ignore[method-assign]

    # ---------- 事件 ----------

    def mouseDoubleClickEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.openRequested.emit(self.shot.id)

    def contextMenuEvent(self, e: QContextMenuEvent) -> None:
        menu = QMenu(self)
        act_save = QAction("💾 保存截图", menu)
        act_save.triggered.connect(lambda: self.saveRequested.emit(self.shot.id))
        act_save.setEnabled(not self.shot.saved)

        act_rename = QAction("✎ 重命名", menu)
        act_rename.triggered.connect(self.start_rename)

        act_copy = QAction("⧉ 复制到剪贴板", menu)
        act_copy.triggered.connect(lambda: self.copyRequested.emit(self.shot.id))

        act_del = QAction("✕ 删除", menu)
        act_del.triggered.connect(lambda: self.deleteRequested.emit(self.shot.id))

        for a in (act_save, act_rename, act_copy):
            menu.addAction(a)
        menu.addSeparator()
        menu.addAction(act_del)
        menu.exec(e.globalPos())


class ShotGallery(QListWidget):
    """截图墙。维护 shot_id → (item, card) 映射。"""

    saveRequested = Signal(str)
    renamed = Signal(str, str)
    copyRequested = Signal(str)
    deleteRequested = Signal(str)
    openRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ShotGallery")
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Static)
        self.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.setSpacing(14)
        self.setUniformItemSizes(True)
        self._index: dict[str, tuple[QListWidgetItem, ShotCard]] = {}

    # ---------- 增删改查 ----------

    def add_shot(self, shot: Shot, pixmap: QPixmap, at_top: bool = True) -> None:
        item = QListWidgetItem(self)
        item.setSizeHint(QSize(240, 214))
        card = ShotCard(shot, pixmap)
        card.setFixedSize(240, 208)
        card.saveRequested.connect(self.saveRequested)
        card.renamed.connect(self.renamed)
        card.copyRequested.connect(self.copyRequested)
        card.deleteRequested.connect(self.deleteRequested)
        card.openRequested.connect(self.openRequested)
        self.setItemWidget(item, card)
        self._index[shot.id] = (item, card)
        if at_top:
            self.insertItem(0, item)
        else:
            self.addItem(item)

    def refresh_shot(self, shot: Shot) -> None:
        pair = self._index.get(shot.id)
        if pair:
            pair[1].refresh(shot)

    def remove_shot(self, shot_id: str) -> None:
        pair = self._index.pop(shot_id, None)
        if pair:
            row = self.row(pair[0])
            self.takeItem(row)

    def load_project(self, project: Project, pixmaps: dict[str, QPixmap]) -> None:
        """切换工程：重建全部卡片（最新的在前）。"""
        self.clear()
        self._index.clear()
        for shot in reversed(project.meta.shots):
            pm = pixmaps.get(shot.id) or QPixmap()
            self.add_shot(shot, pm, at_top=False)

    def filter(self, text: str) -> None:
        text = text.strip().lower()
        for item, card in self._index.values():
            item.setHidden(bool(text) and text not in card.shot.name.lower())

    def count_shots(self) -> int:
        return len(self._index)
