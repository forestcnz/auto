# Auto 素材管理 · 设计文档

> **auto 项目**的两个顶部模块：①「素材管理」（本文档，工程化框选截图采集）②「项目编辑」（占位）。
> 素材管理模块：按工程管理屏幕截图，左键拖动框选截图，右键保存 / 重命名，可循环多次采集。

---

## 1. 产品概述

### 1.1 定位

面向文档编写、Bug 复现、竞品走查等**批量、成组**截图场景的轻量 PC 工具。核心心智：

```
工程 (Project)  →  一组相关截图 (Shot)  →  一个磁盘目录 + 元数据
```

### 1.2 核心用户流（用户需求 → 设计映射）

| 需求 | 设计 |
|---|---|
| 新增一个工程 | 侧栏「＋ 新增工程」→ 命名 → 自动创建工作目录与元数据文件 |
| 左键按住拖动，框选截图 | `F1` 或按钮进入全屏暗幕覆盖层 → 按住左键拖出选区（实时显示 W×H）→ 松开即捕获 |
| 右键保存 / 重命名 | 截图卡片右键 → 上下文菜单：保存 / 重命名 / 复制 / 删除；重命名支持 `F2` 与双击 |
| 可重复多次 | 单次捕获模式（v1.1 变更）：松开即出图并自动退出覆盖层，按 `F1` 再次框选；原始连拍常驻方案已按需求移除 |

### 1.3 设计原则

1. **键盘可全程驱动**：`F1` 截图、`F2` 重命名、`Del` 删除、`Esc` 取消、`Ctrl+S` 保存。
2. **工业风浅色主题**：白/钢灰底、直角小圆角边框、石墨灰（#374151）强调、Consolas 数据字体；品牌 logo 为灰色自动车（激光雷达 + 信号弧，见 `src/auto_assets/resources/logo.svg`）。
3. **启动不自动加载**：仅恢复工程列表，点击具体工程后才打开其内容；空状态区分「尚无工程」与「未选择工程」。
3. **零打断**：捕获不弹窗、不抢焦点切换；所有反馈走状态栏 + toast。

### 1.4 信息架构（auto 项目内定位）

```
Auto 主窗口
├── 顶栏：logo + 品牌 + QTabBar
├── Tab 1「素材管理」 ← 截图采集（本文档主体）
└── Tab 2「项目编辑」 ← 图步骤自动化项目（见 §9）
```

---

## 2. 技术选型

| 项 | 选型 | 理由 |
|---|---|---|
| 运行时/包管理 | **uv** (Python ≥3.11) | 用户要求；启动快、锁文件可复现 |
| GUI 框架 | **PySide6** (Qt6) | 原生窗口/托盘/全局热键生态成熟，QGraphicsView 适合做选区覆盖层 |
| 屏幕捕获 | **mss** | 多显示器支持好、逐显示器采集快 |
| 图像处理 | **Pillow** | PNG 压缩、缩略图、剪贴板位图编码 |
| 剪贴板 | Qt `QClipboard` + Pillow | 文本/图像双向 |
| 配置 | `pydantic-settings` + TOML | 全局配置类型安全 |
| 元数据 | 项目目录内 `project.json` | 目录即工程，可直接拷贝分享 |
| 打包 | `uv build` + PyInstaller（可选） | 交付单 exe |

```toml
# pyproject.toml（节选）
[project]
name = "auto_assets"
requires-python = ">=3.11"
dependencies = ["pyside6>=6.7", "mss>=9", "pillow>=10", "pydantic-settings>=2"]
```

---

## 3. 总体架构

```
┌────────────────────────────────────────────────┐
│                    auto_assets/                    │
│  ┌──────────┐   signals    ┌────────────────┐  │
│  │ MainWindow│◄───────────►│ ProjectService │  │
│  │ (PySide6) │             │ (工程/元数据)    │  │
│  └────┬─────┘             └───────┬────────┘  │
│       │                           │           │
│  ┌────▼──────────┐         ┌──────▼────────┐  │
│  │ CaptureOverlay │────────►│ CaptureEngine │  │
│  │ (全屏选区覆盖层) │  region │ (mss+Pillow)  │  │
│  └───────────────┘         └──────┬────────┘  │
│                                   │           │
│  ┌────────────┐  ┌────────────────▼─────────┐ │
│  │ ShotGallery │  │ StorageService            │ │
│  │ (截图墙视图) │  │ (落盘/缩略图/剪贴板/导出)    │ │
│  └────────────┘  └──────────────────────────┘ │
└────────────────────────────────────────────────┘
```

- **UI 线程**：窗口、覆盖层、列表交互。
- **捕获**：`mss` 单帧 <50ms，主线程直接执行；编码落盘走 `QThreadPool`，避免大图卡 UI。

### 3.1 目录结构

```
auto_assets/
├── pyproject.toml
├── DESIGN.md
├── design/ui-mockup.html
└── src/auto_assets/
    ├── __main__.py          # 入口
    ├── app.py               # QApplication 装配、全局热键
    ├── models.py            # Project / Shot 数据类（pydantic）
    ├── services/
    │   ├── project.py       # 工程 CRUD、project.json 读写
    │   ├── capture.py       # mss 捕获、DPI 缩放换算
    │   └── storage.py       # 落盘、缩略图、导出 zip
    ├── ui/
    │   ├── main_window.py   # 主窗口：侧栏+工具栏+画廊+状态栏
    │   ├── overlay.py       # 全屏覆盖层：左键拖动框选
    │   ├── gallery.py       # 截图卡片墙（QListWidget IconMode）
    │   ├── context_menu.py  # 右键菜单
    │   └── rename.py        # 行内重命名编辑器
    └── resources/
```

---

## 4. 数据模型

### 4.1 工程目录（磁盘即真相）

```
<exe>/config/projects/manual_v2/  ← 工程根目录（示例，位置可自选）
├── project.json               ← 工程元数据
├── shots/                     ← 截图文件
│   ├── 登录页_正常态.png
│   └── 002_表单校验.png
└── thumbs/                    ← 320px 缩略图缓存
```

### 4.2 `project.json`

```json
{
  "schema": 1,
  "name": "用户手册截图 v2",
  "created_at": "2025-01-15T10:30:00+08:00",
  "next_seq": 4,
  "shots": [
    {
      "id": "f81d4fae",
      "file": "登录页_正常态.png",
      "name": "登录页_正常态",
      "seq": 1,
      "width": 1280, "height": 720,
      "monitor": 0,
      "saved": true,
      "created_at": "2025-01-15T10:31:22+08:00"
    }
  ]
}
```

### 4.3 内存模型（`models.py`，pydantic）

```python
class Shot(BaseModel):
    id: str; file: str; name: str; seq: int
    width: int; height: int; monitor: int = 0
    saved: bool = False            # 未保存 = 未保存
    created_at: datetime

class Project(BaseModel):
    name: str; path: Path; next_seq: int = 1
    shots: list[Shot] = []
```

**状态机**：`Shot.saved` 仅两种状态。捕获 → `saved=False`（未保存，文件暂存 `exe 同级 `config/tmp/``）；右键保存 → 移入 `shots/` 并写元数据 → `saved=True`（已保存）。删除未保存态直接丢弃临时文件。

### 4.4 全局配置 `config/config.json`（exe 同级，开发态为仓库根 config/）

```toml
[general]
auto_root = "config/auto_projects"
autosave = false        # true 时捕获即落盘，跳过右键保存

[naming]
template = "{name}"              # 文件名 = 显示名（严格一致，冲突自动加 _1）
default_name = "截图_{seq:03d}"

[hotkey]
capture = "F1"          # 全局热键（任意界面外框选）
```

---

## 5. 交互规格（核心）

### 5.1 新增工程

1. 侧栏「＋ 新增工程」→ 模态对话框：工程名、父目录（默认 exe 同级 `config/projects/`，可自选）、命名模板。
2. 创建：`mkdir -p {dir}/{shots,thumbs}` + 写入 `project.json`。
3. 成功后自动切换为当前工程；重名/非法路径行内报错。
4. **重命名工程**：列表项右键 → 更新 `meta.name`（目录名作为稳定标识不变）；最近列表颜色保留。
5. **删除工程**：列表项右键 → 确认对话框（含路径与截图数）→ `rmtree` 整目录 + 移出最近列表；若为当前工程则先清空画廊。

### 5.2 框选截图（左键按住拖动）

**覆盖层（CaptureOverlay）** —— 每块显示器一个全屏无边框 `QWidget`（`WindowStaysOnTopHint` + `WA_TranslucentBackground`）：

| 阶段 | 行为 |
|---|---|
| 进入 | 屏幕变暗（半透明黑遮罩 + `Esc` 提示条），光标 `CrossCursor`；可先拖动微调 |
| **左键按下** | 记录锚点 `(x0,y0)`，开始绘制选区矩形：深灰 1px 边框 + 8% 填充，遮罩挖孔提亮选区 |
| 拖动中 | 实时刷新矩形与尺寸角标 `W × H`；吸附：接近窗口边缘 8px 磁吸（可选，v2） |
| **左键松开** | 选区 ≥12×12px → 捕获；过小 → 视为误触取消 |

**捕获流水线（CaptureEngine）**：

```
mouseRelease → geometry(QScreen 归一化, 处理 DPI scale)
  → mss.grab(monitor=per-screen region)          # 拾图前先隐藏遮罩层
  → PIL.Image.frombytes("BGRA"→"RGB")
  → 缩略图 320px → thumbs/seq.png
  → 内存态 Shot{saved=False} → 画廊头部插入新卡片
```

**单次捕获（v1.1 变更）**：捕获成功后覆盖层自动退出，需要下一张再次按 `F1`；早期“覆盖层常驻连拍”已按用户要求移除。未保存卡片在画廊中标记为“○ 未保存”，可多次截图后统一右键保存。

### 5.3 右键菜单（保存 / 重命名）

画廊卡片 `contextMenuEvent`：

| 菜单项 | 快捷键 | 行为 |
|---|---|---|
| 💾 保存截图 | `Ctrl+S` | 临时文件 → `shots/{template}.png`，写 `project.json`，状态 ● 已保存 |
| ✎ 重命名 | `F2` | 卡片名称行内编辑器（QLineEdit 预选中默认名）；Enter 确认 / Esc 还原；同步改磁盘文件名 |
| ⧉ 复制到剪贴板 | `Ctrl+C` | 位图入剪贴板（不改状态） |
| ✕ 删除 | `Del` | 确认对话框 → 删文件+缩略图+元数据记录 |

规则：
- 多选（Ctrl/Shift 点选）时菜单批量作用于所选集。
- 未保存卡片执行"复制/导出"时自动先落临时盘。
- 工作目录冲突（同名文件）自动追加 `_1`、`_2`。

### 5.4 截图墙（ShotGallery）

- `QListWidget(IconMode)`：卡片 = 缩略图 + 名称 + `尺寸 · 时间` + 状态点。
- 双击卡片 = 用系统看图器打开原图；拖出卡片 = 以拖拽协议 `image/png` 拖入其他应用。
- 顶部搜索框按名称过滤；工具栏「导出全部」打 zip。

### 5.5 快捷键总表

| 键 | 作用域 | 动作 |
|---|---|---|
| `F1` | 全局（热键注册） | 进入框选 |
| 左键拖动 | 覆盖层 | 框选 |
| `Esc` | 覆盖层/编辑器 | 取消 |
| `Ctrl+S` / `F2` / `Del` | 画廊 | 保存 / 重命名 / 删除 |
| `Ctrl+N` | 主窗口 | 新增工程 |
| `Ctrl+E` | 主窗口 | 导出全部 |

---

## 6. 关键技术点

1. **多显示器 & DPI**：mss 的 monitor 坐标是物理像素；Qt 逻辑坐标需乘 `devicePixelRatio`。覆盖层按 `QScreen.geometry()` 每屏一个实例，跨屏拖选按鼠标当前屏裁剪。
2. **遮罩不留影**：截图前对覆盖层 `hide()` → `mss.grab()` → `show()`；或使用 `QWidget.grabWindow` 备选。延迟一帧（`QTimer.singleShot(80ms)`）确保合成器刷新。
3. **性能**：编码与缩略图在 `QThreadPool`；画廊模型仅在编码完成后接收信号刷新。
4. **崩溃安全**：未保存的临时文件在启动时扫描 `exe 同级 `config/tmp/``，提供"恢复上次会话"。
5. **i18n**：界面文案统一走 `tr()`，先出中文。

---

## 7. 里程碑

| 阶段 | 内容 | 验收 |
|---|---|---|
| M1 | 工程 CRUD + 画廊视图 + 元数据 | 新增/切换/删除工程，卡片列表正确 |
| M2 | 覆盖层框选 + 捕获 + 暂存态卡片 | 连续 10 次单次捕获不卡顿、坐标含 DPI 正确 |
| M3 | 右键保存/重命名/删除 + 快捷键 | 重命名同步磁盘；保存后状态点变绿 |
| M4 | 全局热键、剪贴板、导出 zip、托盘 | 常驻后台 `F1` 随时可截 |
| M5 | 打包 exe + 恢复会话 + 设置页 | 单文件可分发 |

---

## 8. 非目标（v1 不做）

- 标注/马赛克/箭头编辑（留给 v2 的编辑器面板）
- 录屏、滚动长截图
- 云同步（工程目录即数据，用户可自行网盘同步）

---

## 9. 项目编辑模块（Tab 2）

图步骤自动化项目编辑器。目录即项目：`{auto_root}/{项目名}/project.json + templates/`（auto_root 默认 exe 同级 `config/auto_projects/`，创建时可自选并记忆；`auto_recent` 记录根目录外的历史项目）。

### 9.1 数据 schema（用户定义，pydantic 校验）

```json
{
  "name": "项目名称",
  "type": "any | loop",
  "times": 1000,
  "steps": [
    {"template": "templates/xx.png",  "type": "any" 之下的 action 含义见下表| loop | exit"}
  ]
}
```

失败策略三选（策略里的 `loop` 与项目类型 `loop` 是两个概念——前者是步骤级循环重试，后者是整体流程循环次数）：

| 值 | loop 项目 | any 项目 |
|---|---|---|
| `skip` | 跳过本步，继续执行后续步骤 | 同左 |
| `loop` | 循环重试本步，直到匹配成功 | 同左 |
| `exit` | 退出循环 | 终止流程 |

### 9.2 交互

- 步骤表格：模板（缩略图 + 文件名）/ 动作（click 单击 / double_click 双击）/ score（双精度微调框）/ 失败策略，所有改动**自动保存**
- 模板来源：从素材工程缩略图列表选取 → `import_template()` **复制一份**到 `templates/`（重名自动加 `_1`），素材原件不动
- **重命名 / 删除**：列表项**右键菜单**（未打开也可操作）——与素材管理侧统一为「✎ 重命名 / 📂 打开目录 / ✕ 删除」；重命名同步目录名 + meta.name（非法字符安全化、冲突检测）；删除带确认，若为当前打开项目先清空编辑器

### 9.3 关键类

- `models.AutoStep / AutoProject`：schema 模型
- `services/automation.py AutomationService`：CRUD + 模板复制
- `ui/edit_tab.py ProjectEditView / TemplatePicker`：编辑器与选取对话框

---

- 标注/马赛克/箭头编辑（留给 v2 的编辑器面板）
- 录屏、滚动长截图
- 云同步（工程目录即数据，用户可自行网盘同步）
