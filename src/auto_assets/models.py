"""数据模型：Shot / ProjectMeta（与 DESIGN.md §4 对应）。"""
from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field


def new_id() -> str:
    return uuid.uuid4().hex[:8]


class Shot(BaseModel):
    """单张截图。saved=False 为“未保存”（暂存临时目录），True 为“已保存”（已入工程）。"""

    id: str = Field(default_factory=new_id)
    file: str = ""  # 相对工程根目录的路径；未保存时为空（文件在 %TEMP%/auto_assets/）
    name: str
    seq: int
    width: int = 0
    height: int = 0
    monitor: int = 0
    saved: bool = False
    created_at: datetime = Field(default_factory=datetime.now)


class ProjectMeta(BaseModel):
    """project.json 的结构。"""

    schema_version: int = 1
    name: str
    created_at: datetime = Field(default_factory=datetime.now)
    next_seq: int = 1
    shots: list[Shot] = Field(default_factory=list)


class Project:
    """运行时工程对象：磁盘路径 + 元数据。"""

    def __init__(self, path: Path, meta: ProjectMeta):
        self.path = Path(path)
        self.meta = meta

    @property
    def name(self) -> str:
        return self.meta.name

    @property
    def shots_dir(self) -> Path:
        return self.path / "shots"

    @property
    def thumbs_dir(self) -> Path:
        return self.path / "thumbs"

    @property
    def meta_file(self) -> Path:
        return self.path / "project.json"
