"""工程服务：创建 / 加载 / 元数据读写 / 重命名 / 删除 / 最近工程配置。"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from auto_assets.models import Project, ProjectMeta

CONFIG_DIR = Path.home() / "AppData" / "Roaming" / "auto_assets"
CONFIG_FILE = CONFIG_DIR / "config.json"

PROJECT_COLORS = ["#374151", "#6b7280", "#1f2937", "#9ca3af", "#0d9488"]


@dataclass
class RecentEntry:
    path: str
    color: str = PROJECT_COLORS[0]


@dataclass
class AppConfig:
    last: str = ""
    recent: list[RecentEntry] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            {
                "last": self.last,
                "recent": [{"path": r.path, "color": r.color} for r in self.recent],
            },
            ensure_ascii=False,
            indent=2,
        )

    @staticmethod
    def from_json(text: str) -> "AppConfig":
        data = json.loads(text)
        return AppConfig(
            last=data.get("last", ""),
            recent=[RecentEntry(**r) for r in data.get("recent", [])],
        )


class ProjectService:
    """工程 CRUD 与应用配置持久化。"""

    def __init__(self) -> None:
        self.config = self._load_config()

    # ---------- config ----------

    def _load_config(self) -> AppConfig:
        try:
            cfg = AppConfig.from_json(CONFIG_FILE.read_text("utf-8"))
        except Exception:
            return AppConfig()
        # 旧版本配色迁移（如蓝色 → 当前调色板）
        for i, r in enumerate(cfg.recent):
            if r.color not in PROJECT_COLORS:
                r.color = PROJECT_COLORS[i % len(PROJECT_COLORS)]
        return cfg

    def save_config(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(self.config.to_json(), "utf-8")

    def touch_recent(self, path: Path) -> None:
        """把工程移到最近列表首位（保留已有配色，新工程按序取色）。"""
        key = str(path)
        existing = next((r for r in self.config.recent if r.path == key), None)
        color = (
            existing.color
            if existing
            else PROJECT_COLORS[len(self.config.recent) % len(PROJECT_COLORS)]
        )
        self.config.recent = [r for r in self.config.recent if r.path != key]
        self.config.recent.insert(0, RecentEntry(path=key, color=color))
        self.config.last = key
        self.save_config()

    def drop_recent(self, path: Path) -> None:
        key = str(path)
        self.config.recent = [r for r in self.config.recent if r.path != key]
        if self.config.last == key:
            self.config.last = ""
        self.save_config()

    # ---------- project ----------

    def create_project(self, name: str, parent_dir: Path) -> Project:
        """新增工程：目录即工程（shots/ + thumbs/ + project.json）。"""
        parent = Path(parent_dir).expanduser()
        root = parent / name.strip()
        if root.exists():
            raise FileExistsError(f"目录已存在: {root}")
        (root / "shots").mkdir(parents=True)
        (root / "thumbs").mkdir()
        project = Project(root, ProjectMeta(name=name.strip()))
        self.save_meta(project)
        self.touch_recent(root)
        return project

    def load_project(self, path: Path) -> Project:
        path = Path(path)
        meta = ProjectMeta.model_validate_json((path / "project.json").read_text("utf-8"))
        project = Project(path, meta)
        # 文件即真相：显示名与磁盘文件名严格同步（用户在资源管理器里改名后应用内也跟随）
        for shot in project.meta.shots:
            if shot.saved and shot.file:
                stem = Path(shot.file).stem
                if shot.name != stem:
                    shot.name = stem
        return project

    def rename_project(self, project: Project, new_name: str) -> None:
        """重命名工程：更新元数据显示名（目录名作为稳定标识不变）。"""
        project.meta.name = new_name.strip()
        self.save_meta(project)
        self.touch_recent(project.path)

    def delete_project(self, path: Path) -> None:
        """删除工程：删除整个目录（shots/thumbs/project.json）并移出最近列表。"""
        shutil.rmtree(path)
        self.drop_recent(path)

    def save_meta(self, project: Project) -> None:
        project.meta_file.write_text(project.meta.model_dump_json(indent=2), "utf-8")
