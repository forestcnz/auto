"""自动化项目服务（项目编辑 tab）。

目录即项目：{auto_root}/{项目名}/
├── project.json   # AutoProject schema（name/type/times/steps）
└── templates/     # 从素材工程复制过来的模板图
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from auto_assets.models import AutoProject
from auto_assets.paths import DEFAULT_AUTO_ROOT
from auto_assets.services.storage import _unique_file, sanitize


@dataclass
class AutoProjectHandle:
    path: Path
    data: AutoProject


class AutomationService:
    def __init__(self, config_svc, root: str | None = None):
        """config_svc: ProjectService（共享 AppConfig）；root 覆盖默认目录（测试用）。"""
        self._cfg = config_svc
        self._root_override = root

    @property
    def root(self) -> Path:
        return Path(self._root_override or DEFAULT_AUTO_ROOT)

    # ---------- CRUD ----------

    def list_projects(self) -> list[AutoProjectHandle]:
        """合并：根目录扫描 + auto_recent 已知路径（去重），解析失败的跳过。"""
        candidates: dict[str, Path] = {}
        if self.root.exists():
            for pj in self.root.glob("*/project.json"):
                candidates[str(pj.parent)] = pj.parent
        for p in self._cfg.config.auto_recent:
            pp = Path(p)
            if (pp / "project.json").exists():
                candidates.setdefault(p, pp)
        out: list[AutoProjectHandle] = []
        for path in sorted(candidates.values()):
            try:
                data = AutoProject.model_validate_json(
                    (path / "project.json").read_text("utf-8")
                )
            except Exception:
                continue
            out.append(AutoProjectHandle(path, data))
        return out

    def create_project(self, name: str, type_: str = "any", times: int = 1000) -> AutoProjectHandle:
        """创建项目：统一在 config/auto_projects/ 下。"""
        safe_name = sanitize(name.strip())
        root = self.root / safe_name
        if root.exists():
            raise FileExistsError(f"目录已存在: {root}")
        (root / "templates").mkdir(parents=True)
        handle = AutoProjectHandle(
            root, AutoProject(name=safe_name, type=type_, times=times)
        )
        self.save_project(handle)
        self._remember(root)
        return handle

    def _remember(self, path: Path) -> None:
        key = str(path)
        if key not in self._cfg.config.auto_recent:
            self._cfg.config.auto_recent.insert(0, key)
            self._cfg.save_config()

    def drop_recent(self, path: Path) -> None:
        key = str(path)
        self._cfg.config.auto_recent = [
            p for p in self._cfg.config.auto_recent if p != key
        ]
        self._cfg.save_config()

    def load_project(self, path: Path) -> AutoProjectHandle:
        path = Path(path)
        data = AutoProject.model_validate_json((path / "project.json").read_text("utf-8"))
        return AutoProjectHandle(path, data)

    def save_project(self, handle: AutoProjectHandle) -> None:
        handle.path.mkdir(parents=True, exist_ok=True)
        (handle.path / "project.json").write_text(
            handle.data.model_dump_json(indent=2), "utf-8"
        )

    def rename_project(self, handle: AutoProjectHandle, new_name: str) -> Path:
        """重命名：目录与 meta.name 同步更新（名称做文件名安全化）。"""
        new = sanitize(new_name)
        if new == handle.data.name:
            return handle.path
        new_path = handle.path.parent / new
        if new_path.exists():
            raise FileExistsError(f"目录已存在: {new_path}")
        handle.path.rename(new_path)
        handle.path = new_path
        handle.data.name = new
        self.save_project(handle)
        return new_path

    def delete_project(self, path: Path) -> None:
        shutil.rmtree(path)
        self.drop_recent(path)

    # ---------- 模板 ----------

    def import_template(self, auto_dir: Path, source_png: Path) -> str:
        """把素材工程里的截图复制一份到自动化项目 templates/，返回相对路径。"""
        tdir = auto_dir / "templates"
        tdir.mkdir(parents=True, exist_ok=True)
        target = _unique_file(tdir, Path(source_png).name)
        shutil.copy2(source_png, target)
        return f"templates/{target.name}".replace("\\", "/")
