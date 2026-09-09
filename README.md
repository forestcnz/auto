# Auto 素材管理

按工程管理的 PC 框选截图工具 + 图步骤自动化项目编辑，作为 **auto** 项目的两个顶部 tab：①「素材管理」②「项目编辑」。界面为**工业风浅色主题**：钢灰底色、直角边框、石墨灰（#374151）强调、Consolas 数据字体；启动后不自动打开工程，需在左侧列表点击选择。设计文档见 `DESIGN.md`。

品牌 logo：`src/auto_assets/resources/logo.svg`（自动车 + 激光雷达信号，蓝色主题）。

## 快速开始

```bash
uv sync          # 安装依赖（Python 3.12）
uv run auto_assets   # 启动
```

开发模式运行：`uv run python -m auto_assets`

冒烟测试（无需显示器）：

```bash
QT_QPA_PLATFORM=offscreen uv run python -u scripts/smoke_test.py
QT_QPA_PLATFORM=offscreen uv run python -u scripts/smoke_ui.py
```

## 使用方法

### Tab 1 素材管理

1. **新增工程**：侧栏「＋ 新增工程」→ 命名 → 选择父目录（默认 exe 同级 `config/projects/`，可自选），自动创建
   `shots/`、`thumbs/`、`project.json`
   - **重命名 / 删除**：在侧栏**右键工程** → 重命名（改显示名，目录标识不变）/ 删除（确认后整目录删除，不可恢复）
   - 启动后不自动打开工程，点击列表项加载；圆点颜色稳定不漂移
2. **框选截图**：`F1` 或工具栏「▣ 开始截图」→ **按住左键拖动**出选区 → 松开捕获，覆盖层自动退出（单次模式）
   → 需要再截时再按 `F1` 重新框选
3. **保存 / 重命名**：在截图卡片上**点击右键** → 保存 / 重命名 / 复制 / 删除
   - 未保存卡片为红色「○ 未保存」，保存后变灰色「● 已保存」
   - **文件名 = 显示名**：保存/重命名后磁盘文件与卡片显示严格一致；重名自动追加 `_1`；在资源管理器手动改名后，重新打开工程时应用内显示会跟随磁盘文件名
   - 点选卡片后：`F2` 重命名、`Del` 删除、`Ctrl+S` 保存
4. **导出**：工具栏「⇩ 导出全部」打包 zip；「📂 打开目录」直达工程文件夹

## 目录结构

```
src/auto_assets/
├── app.py               # 入口 + 暗房主题 QSS
├── models.py            # Shot / ProjectMeta（pydantic）
├── services/
│   ├── project.py       # 工程 CRUD、最近工程配置
│   ├── capture.py       # mss 抓屏、逻辑→物理坐标换算
│   └── storage.py       # 暂存暂存 / 已保存保存 / 重命名 / 导出
└── ui/
    ├── main_window.py   # 主窗口外壳：logo + 顶部 tab（素材管理 / 项目编辑）
    ├── asset_tab.py     # 素材管理视图（侧栏 + 工具栏 + 截图墙）
    ├── logo.py          # Auto 自动车 logo（SVG 矢量渲染）
    ├── overlay.py       # 全屏框选覆盖层（挖孔遮罩 + 实时尺寸）
    └── gallery.py       # 截图墙卡片 + 右键菜单 + 行内重命名
```

### Tab 2 项目编辑

1. **新建项目**：侧栏「＋ 新建项目」→ 名称 → 类型（any 任意 / loop 循环）→ 循环次数（loop 时）
2. **添加步骤**：「＋ 添加步骤」→ 从素材工程缩略图列表选一张 → **自动复制**到项目的 `templates/` 目录
3. **步骤编辑**：动作（click 单击 / double_click 双击）、阈值 score（默认 0.85）、失败策略（skip 跳过 / loop 循环重试 / exit 退出）直接在表格内修改，**改动自动保存**；末列 `↑` `↓` `✕` 排序/删除，行右键菜单支持 放大预览 / 替换模板 / 复制步骤，点击模板列放大查看原图
4. **运行**：「▶ 运行」隐藏主窗口打开运行监控小窗：loop 项目显示轮次进度条与实时耗时，每个任务可「■ 停止」（或双击任务行），也可「■ 全部停止」
5. **脚本模式**：表单「脚本」行选择 `scripts/xx.py`（「＋ 新建」自动生成骨架）→ 运行时忽略步骤列表，每轮调用一次脚本里的 `main(auto)`；「✎ 编辑」打开内嵌编辑器（语法高亮 / `Ctrl+S` 保存 / `▶ 试运行` 真实执行一轮）
   - 脚本 `auto` API：`find(name, score)` / `find_click(...)` / `wait(name, timeout)` 找图；`click` / `double_click` / `key` / `hotkey("ctrl","s")` / `text("中文")` 输入；`sleep` / `log` / `pixel` 取色 / `screen_size` / `round` 轮次 / `abort("原因")` 主动终止
6. `project.json` 与用户定义 schema 严格一致：

```json
{
  "name": "项目名称",
  "type": "any",
  "times": 1000,
  "steps": [
    {"template": "templates/xx.png", "action": "click", "score": 0.85, "strategy": "skip"}
  ],
  "script": ""
}
```



| 键 | 作用 |
|---|---|
| `F1` | 开始框选 |
| 左键拖动 | 框选（松开即捕获，单次模式） |
| `Esc` | 取消框选 / 取消重命名 |
| `Ctrl+N` | 新增工程 |
| `Ctrl+E` | 导出全部 |
| `Ctrl+S` / `F2` / `Del` | 保存 / 重命名 / 删除（卡片点选后） |

## 数据

- 工程即目录：`{工程}/project.json` + `shots/` + `thumbs/`，可直接拷贝分享
- 所有应用数据统一在 **exe 同级 `config/`** 下：`config.json`（配置/最近列表）、`tmp/`（未保存截图暂存）、`projects/`（素材工程默认位置）、`auto_projects/`（自动化项目默认位置）
