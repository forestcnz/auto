"""应用装配：QApplication、HiDPI、工业风浅色主题 QSS（安全绿强调）。"""
from __future__ import annotations

import sys

QSS = """
* { font-family: "Microsoft YaHei", "Noto Sans SC", sans-serif; font-size: 13px; color: #1f2937; }

QMainWindow, #WorkArea, #PlaceholderView { background: #eef0f3; }
#Sidebar { background: #f7f8fa; border-right: 1px solid #d5dae1; }

#SidebarCap { color: #6b7280; letter-spacing: 6px; font-size: 11px; font-weight: 600; }
#SidebarTips { color: #8a919c; font-size: 11px; border-top: 1px solid #e2e5ea; }

#BtnNewProject {
  background: #374151; color: #ffffff; font-weight: 700;
  border: 1px solid #1f2937; border-radius: 3px; padding: 8px 12px;
}
#BtnNewProject:hover { background: #1f2937; }
#BtnNewProject:pressed { background: #111827; }

#ProjList { background: transparent; border: none; outline: none; padding: 4px 8px; }

#BtnCapture {
  background: #374151; color: #ffffff; font-weight: 600;
  border: 1px solid #1f2937; border-radius: 3px; padding: 7px 16px;
}
#BtnCapture:hover { background: #1f2937; }
#BtnCapture:disabled { color: #9aa1ab; border-color: #d5dae1; background: #e5e8ec; }

QToolButton#ToolBtn {
  background: #ffffff; border: 1px solid #c9ced6; border-radius: 3px;
  padding: 6px 12px; color: #3f4753;
}
QToolButton#ToolBtn:hover { border-color: #374151; color: #374151; background: #f3f4f6; }
QToolButton#ToolBtn:disabled { color: #b3b9c2; border-color: #dfe3e8; background: #f2f4f6; }

#SearchBox {
  background: #ffffff; border: 1px solid #c9ced6; border-radius: 3px;
  padding: 6px 11px; color: #1f2937; selection-background-color: #374151;
}
#SearchBox:focus { border-color: #374151; }

#ShotGallery { background: #eef0f3; border: none; outline: none; }
#EmptyState { color: #9aa1ab; font-size: 14px; background: #eef0f3; }

#ShotCard { background: #ffffff; border: 1px solid #d5dae1; border-radius: 3px; }
#ShotCard:hover { border-color: #8a94a3; }
#ShotName { font-weight: 600; font-size: 12.5px; }
#ShotMeta { color: #6b7280; font-family: Consolas, monospace; font-size: 10.5px; }

#TopBar { background: #ffffff; border-bottom: 1px solid #d5dae1; }
#BrandName { font-size: 15px; font-weight: 800; color: #111827; letter-spacing: 2px; }
QTabBar { background: transparent; }
QTabBar::tab {
  background: transparent; color: #5f6672; padding: 5px 16px; margin: 0;
  border: none; border-bottom: 2px solid transparent; border-radius: 0;
}
QTabBar::tab:hover { color: #111827; }
QTabBar::tab:selected { color: #111827; border-bottom: 2px solid #374151; font-weight: 700; }
#PlaceholderView { background: #eef0f3; }
#PlaceholderTitle { color: #9aa1ab; font-size: 20px; font-weight: 700; letter-spacing: 4px; }
#PlaceholderSub { color: #b8bec7; font-size: 12px; padding-top: 8px; font-family: Consolas, monospace; }

#EditStatus { color: #6b7280; font-family: Consolas, monospace; font-size: 11px; }
QTableWidget { background: #ffffff; border: 1px solid #d5dae1; gridline-color: #e9edf2; }
QHeaderView::section {
  background: #f7f8fa; border: none; border-right: 1px solid #e2e5ea; border-bottom: 1px solid #d5dae1;
  padding: 6px 8px; color: #5f6672; font-weight: 600;
}
QTableCornerButton::section { background: #f7f8fa; border: none; }
QComboBox, QDoubleSpinBox, QSpinBox {
  background: #ffffff; border: 1px solid #c9ced6; border-radius: 3px; padding: 4px 8px;
}
QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus { border-color: #374151; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView {
  background: #ffffff; border: 1px solid #c9ced6;
  selection-background-color: #374151; selection-color: #ffffff;
}

/* 微调框上下按钮：显式定义子控件，否则 stylesheet 模式下箭头不可点 */
QSpinBox::up-button, QDoubleSpinBox::up-button {
  subcontrol-origin: border; subcontrol-position: top right;
  width: 18px; border: none; border-left: 1px solid #d5dae1;
  border-bottom: 1px solid #d5dae1; background: #f0f2f5;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
  subcontrol-origin: border; subcontrol-position: bottom right;
  width: 18px; border: none; border-left: 1px solid #d5dae1; background: #f0f2f5;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover { background: #dfe3e8; }
QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,
QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed { background: #c9ced6; }

QStatusBar { background: #ffffff; border-top: 1px solid #d5dae1; color: #6b7280;
  font-family: Consolas, monospace; font-size: 11px; }
QStatusBar::item { border: none; }

QMenu { background: #ffffff; border: 1px solid #c9ced6; border-radius: 3px; padding: 4px; }
QMenu::item { padding: 7px 22px 7px 12px; color: #1f2937; }
QMenu::item:selected { background: #374151; color: #ffffff; }
QMenu::separator { height: 1px; background: #e2e5ea; margin: 3px 6px; }

QInputDialog QLineEdit, QMessageBox { background: #ffffff; }
QLineEdit { background: #ffffff; border: 1px solid #c9ced6; border-radius: 3px;
  padding: 5px 8px; color: #1f2937; selection-background-color: #374151; }
QMessageBox QLabel { color: #1f2937; }
QMessageBox QPushButton { background: #ffffff; border: 1px solid #c9ced6;
  border-radius: 3px; padding: 6px 18px; min-width: 60px; }
QMessageBox QPushButton:hover { border-color: #374151; color: #374151; }

QScrollBar:vertical { background: transparent; width: 9px; margin: 0; }
QScrollBar::handle:vertical { background: #c2c9d2; border-radius: 0; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #9aa5b1; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: transparent; height: 9px; }
QScrollBar::handle:horizontal { background: #c2c9d2; border-radius: 0; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
"""


def main() -> int:
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    from auto_assets.ui.logo import app_icon
    from auto_assets.ui.main_window import MainWindow

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("Auto")
    app.setApplicationDisplayName("Auto")
    app.setWindowIcon(app_icon())
    app.setStyleSheet(QSS)

    win = MainWindow()
    win.show()
    return app.exec()


from PySide6.QtCore import Qt  # noqa: E402  (QSS 之上仅用到枚举)

if __name__ == "__main__":
    raise SystemExit(main())
