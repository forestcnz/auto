# AGENTS.md

Windows 桌面应用（PySide6）：①素材管理（框选截图）②项目编辑（OpenCV 模板匹配自动化）。uv 管理的 Python 3.12 项目，src 布局，包名 `auto_assets`。UI 文案、注释、文档一律中文。

## 常用命令

```bash
uv sync                  # 安装依赖（uv.lock 已提交，CI 用 uv sync --locked）
uv run auto_assets       # 启动 GUI（等价：uv run python -m auto_assets）
```

测试只有冒烟脚本（无 pytest / lint / typecheck 配置），必须离屏运行：

```powershell
$env:QT_QPA_PLATFORM='offscreen'; uv run python -u scripts/smoke_test.py    # 素材存储服务层
$env:QT_QPA_PLATFORM='offscreen'; uv run python -u scripts/smoke_ui.py      # 覆盖层 + 真实抓屏
$env:QT_QPA_PLATFORM='offscreen'; uv run python -u scripts/smoke_runner.py  # 运行引擎（注入 grab/click）
$env:QT_QPA_PLATFORM='offscreen'; uv run python -u scripts/smoke_edit.py    # 自动化项目服务
$env:QT_QPA_PLATFORM='offscreen'; uv run python -u scripts/smoke_picker.py  # 项目编辑 UI
$env:QT_QPA_PLATFORM='offscreen'; uv run python -u scripts/smoke_script.py  # Python 脚本模式（注入 grab/click/key）
```

- README 里的 `QT_QPA_PLATFORM=offscreen uv run ...` 是 POSIX 语法，Windows pwsh 下必须用 `$env:` 前缀。
- 改动哪个模块就跑对应脚本；服务层改动至少跑 `smoke_test.py`。

## 发布流程（注意）

推送到 `master` 即触发 `.github/workflows/release.yml`（windows-latest）：跑 smoke_test + smoke_ui → PyInstaller 打包 → 自动创建 GitHub Release `v{pyproject.toml 的 version}`（同名旧 release 先删再建）。**改 version 字段并推送 master 就会发版**，无需手动打 tag。

## 代码陷阱

- **Qt 离屏顺序**：使用 QPixmap 的模块（如 `services/storage.py`）必须先创建 `QGuiApplication`/`QApplication` 再导入/使用（见 `scripts/smoke_test.py` 开头）。
- **中文路径 + OpenCV**：Windows 下 `cv2.imread/imwrite` 不支持非 ASCII 路径，一律用 `services/runner.py` 的 `imread_unicode` / `imwrite_unicode`。
- **DPI 坐标系**：mss 用物理像素，Qt 用逻辑像素；换算只走 `services/capture.py` 的 `logical_to_physical_rect`。多屏时 mss 取 `monitors[0]`（合并虚拟屏）。
- **文件名 = 显示名**：素材保存/重命名后磁盘文件与卡片显示严格一致（`storage.py` 的 `sanitize` + `_unique_file`）；重载时以磁盘文件名反向同步显示名。
- **AutoProject schema 严格**：自动化 `project.json` 必须恰好是 `{name, type, times, steps, script}`（smoke_edit 有断言）；`script` 空 = 步骤模式，非空（`scripts/xx.py`）= Python 脚本模式（每轮调用 `main(auto)`，见 `services/scripting.py`）；action 只有 click/double_click，strategy 只有 skip/loop/exit。
- **TaskWorker**（`services/runner.py`，QThread）的 `grab_fn`/`click_fn`/`key_fn`/`hotkey_fn`/`text_fn` 可注入，离屏测试靠这个；不要把引擎改成直接操作真实鼠标键盘。真实点击/键盘走 ctypes user32，仅 Windows 可用。

## 数据目录（勿提交）

`config/` 已 gitignore，全是运行时数据：开发态在仓库根（`paths.py` 的 BASE_DIR），打包后 exe 同级；含 `config.json`、`tmp/`（未保存截图暂存）、`projects/`、`auto_projects/`。工程即目录：素材工程 = `{project.json, shots/, thumbs/}`，自动化项目 = `{project.json, templates/}`。smoke 脚本会往真实 config 写临时条目并在结尾自清理——脚本中途崩溃后需手动清掉 config.json 里的 temp 路径。

## 其他

- `DESIGN.md` 是设计文档（也是 pyproject 的 readme），部分技术选型描述已过时（实际配置是 `services/project.py` 的 json AppConfig，非 pydantic-settings/TOML）；README 的目录树缺 `paths.py`、`automation.py`、`runner.py`、`edit_tab.py`、`runner_window.py`——两者与代码冲突时以代码为准。
- 主题 QSS 集中在 `app.py` 顶部的 QSS 字符串（工业风浅色，石墨灰 #374151 强调），不要在 widget 上散落 setStyleSheet。
- 提交信息用中文 conventional 前缀（`feat:` / `chore:` / `docs:`），见 git log。
