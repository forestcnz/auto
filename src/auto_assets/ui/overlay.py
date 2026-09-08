"""全屏框选覆盖层：每块屏幕一个实例。

交互（DESIGN.md §5.2）：
- 进入：屏幕变暗，光标十字，中央提示
- 左键按下拖动：蓝色选区框 + 实时 W×H 角标，选区外更暗（挖孔效果）
- 左键松开：≥12×12 捕获并发出 regionCaptured（单次捕获，主窗口收到后自动关闭覆盖层）；过小视为误触取消
- Esc：取消并退出（cancelled）
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

MIN_SIZE = 12  # px，小于此视为误触取消

ACCENT = QColor("#374151")
MASK = QColor(8, 10, 13, 210)


class CaptureOverlay(QWidget):
    regionCaptured = Signal(object, QRect)  # (overlay, 屏幕局部逻辑坐标 QRect)
    cancelled = Signal()

    def __init__(self, screen):
        super().__init__(
            None,
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool,
        )
        self.setScreen(screen)
        self.setGeometry(screen.geometry())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._origin: QPoint | None = None
        self._current: QPoint | None = None
        self._dragging = False

    # ---------- 交互 ----------

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._origin = e.position().toPoint()
            self._current = self._origin
            self.update()

    def mouseMoveEvent(self, e) -> None:
        if self._dragging:
            self._current = e.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() != Qt.MouseButton.LeftButton or not self._dragging:
            return
        self._dragging = False
        rect = QRect(self._origin, self._current).normalized()
        self._origin = self._current = None
        self.update()
        if rect.width() >= MIN_SIZE and rect.height() >= MIN_SIZE:
            self.regionCaptured.emit(self, rect)
        else:
            self.cancelled.emit()  # 误触：视为取消并退出覆盖层

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()

    # ---------- 绘制 ----------

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        full = self.rect()

        sel = self._selection_rect()
        if sel is not None:
            # 遮罩挖孔：奇偶填充 → 选区提亮
            path = QPainterPath()
            path.setFillRule(Qt.FillRule.OddEvenFill)
            path.addRect(full)
            path.addRect(sel)
            p.fillPath(path, MASK)
            p.setPen(QPen(ACCENT, 1))
            p.drawRect(sel)
            self._draw_dim_label(p, sel)
        else:
            p.fillRect(full, MASK)
            self._draw_hint(p, full)

    def _selection_rect(self) -> QRect | None:
        if self._dragging and self._origin is not None:
            return QRect(self._origin, self._current).normalized()
        return None

    def _draw_dim_label(self, p: QPainter, sel: QRect) -> None:
        dpr = self.screen().devicePixelRatio()
        text = f"{round(sel.width() * dpr)} × {round(sel.height() * dpr)}"
        f = QFont("Consolas", 10)
        p.setFont(f)
        fm = p.fontMetrics()
        pad = 6
        w = fm.horizontalAdvance(text) + pad * 2
        h = fm.height() + 4
        label_y = sel.y() - h - 6 if sel.y() - h - 6 > 0 else sel.y() + 6
        p.fillRect(QRect(sel.x(), label_y, w, h), QColor(12, 14, 17, 235))
        p.setPen(QPen(ACCENT, 1))
        p.drawRect(QRect(sel.x(), label_y, w, h))
        p.setPen(ACCENT)
        p.drawText(QRect(sel.x(), label_y, w, h), Qt.AlignmentFlag.AlignCenter, text)

    def _draw_hint(self, p: QPainter, full: QRect) -> None:
        p.setPen(QColor("#d8dde4"))
        f = QFont("Microsoft YaHei", 12)
        f.setBold(True)
        p.setFont(f)
        fm = p.fontMetrics()
        cx, cy = full.center().x(), full.center().y()
        p.drawText(cx - fm.horizontalAdvance("按住左键拖动，框选屏幕区域") // 2,
                   cy - 14, "按住左键拖动，框选屏幕区域")
        p.setPen(QColor("#7d8590"))
        p.setFont(QFont("Microsoft YaHei", 9))
        fm2 = p.fontMetrics()
        tip = "松开左键生成截图 → 右键保存 / 重命名    Esc 取消"
        p.drawText(cx - fm2.horizontalAdvance(tip) // 2, cy + 12, tip)

