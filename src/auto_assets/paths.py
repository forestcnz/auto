"""数据路径：统一放在 exe 同级 config/ 下。

- 打包后（PyInstaller onefile）：exe 所在目录/config/
- 开发态（uv run）：仓库根目录/config/

用户创建工程/项目时仍可自选任意位置；此处只决定"默认位置"与应用配置、
未保存截图暂存目录的落点。
"""
from __future__ import annotations

import sys
from pathlib import Path


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False):  # PyInstaller 打包
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]  # src/auto_assets/paths.py → 仓库根


BASE_DIR = app_base_dir()
CONFIG_DIR = BASE_DIR / "config"
TMP_DIR = CONFIG_DIR / "tmp"  # 未保存截图暂存
DEFAULT_PROJECTS_DIR = CONFIG_DIR / "projects"  # 素材工程默认父目录
DEFAULT_AUTO_ROOT = CONFIG_DIR / "auto_projects"  # 自动化项目默认根目录
