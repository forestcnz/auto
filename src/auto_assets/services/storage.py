"""存储服务：暂存暂存 / 保存已保存 / 重命名 / 删除 / 缩略图 / 导出。"""
from __future__ import annotations

import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from PIL import Image
from PySide6.QtGui import QPixmap

from auto_assets.models import Project, Shot

THUMB_W = 320

_name_cache: Path | None = None


def temp_dir() -> Path:
    """未保存截图的暂存目录 %TEMP%/auto_assets/。"""
    global _name_cache
    if _name_cache is None:
        _name_cache = Path(tempfile.gettempdir()) / "auto_assets"
        _name_cache.mkdir(parents=True, exist_ok=True)
    return _name_cache


def sanitize(name: str) -> str:
    """文件名安全化：去掉 Windows 非法字符。"""
    cleaned = re.sub(r'[\\/:*?"<>|\r\n]', "_", name.strip())
    return cleaned[:80] or "shot"


def _unique_file(directory: Path, filename: str) -> Path:
    """同名自动追加 _1 / _2 …"""
    target = directory / filename
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    i = 1
    while (directory / f"{stem}_{i}{suffix}").exists():
        i += 1
    return directory / f"{stem}_{i}{suffix}"


def _thumb_path(project: Project, shot: Shot) -> Path:
    return project.thumbs_dir / f"{shot.id}.png"


def stage_capture(project: Project, img: Image.Image, monitor: int = 0) -> tuple[Shot, QPixmap]:
    """捕获后的“暂存”阶段：暂存临时 PNG + 生成缩略图，返回未保存 Shot。"""
    shot = Shot(name="", seq=project.meta.next_seq, monitor=monitor)
    shot.width, shot.height = img.size
    shot.name = f"截图_{shot.seq:03d}"

    tmp = temp_dir() / f"{shot.id}.png"
    img.save(tmp, "PNG")

    project.thumbs_dir.mkdir(parents=True, exist_ok=True)
    thumb = img.copy()
    thumb.thumbnail((THUMB_W, 10000))
    thumb.save(_thumb_path(project, shot), "PNG")

    project.meta.next_seq += 1
    return shot, QPixmap(str(_thumb_path(project, shot)))


def resolve_file(project: Project, shot: Shot) -> Path:
    return temp_dir() / f"{shot.id}.png" if not shot.saved else project.path / shot.file


def save_shot(project: Project, shot: Shot, name: str | None = None) -> None:
    """右键保存：暂存文件 → shots/{显示名}.png，文件名与显示名严格一致。"""
    if shot.saved:
        return
    if name and name.strip():
        shot.name = name.strip()
    project.shots_dir.mkdir(parents=True, exist_ok=True)
    target = _unique_file(project.shots_dir, f"{sanitize(shot.name)}.png")

    src = temp_dir() / f"{shot.id}.png"
    shutil.move(str(src), target)
    shot.file = str(target.relative_to(project.path)).replace("\\", "/")
    shot.name = target.stem  # 冲突自动加 _1 后同步显示名，保证 文件名 = 显示名
    shot.saved = True
    project.meta.next_seq = max(project.meta.next_seq, shot.seq + 1)


def rename_shot(project: Project, shot: Shot, new_name: str) -> None:
    """重命名：已保存的同步改磁盘文件名（文件名 = 显示名）。"""
    new_name = new_name.strip()
    if not new_name or new_name == shot.name:
        return
    if shot.saved:
        old_path = resolve_file(project, shot)
        target = _unique_file(project.shots_dir, f"{sanitize(new_name)}.png")
        old_path.rename(target)
        shot.file = str(target.relative_to(project.path)).replace("\\", "/")
        shot.name = target.stem
    else:
        shot.name = new_name  # 未保存：仅改显示名，落盘时按此命名


def delete_shot(project: Project, shot: Shot) -> None:
    """删除：文件 + 缩略图 + 元数据记录由调用方移除。"""
    try:
        resolve_file(project, shot).unlink(missing_ok=True)
    except OSError:
        pass
    _thumb_path(project, shot).unlink(missing_ok=True)


def load_pixmap(project: Project, shot: Shot) -> QPixmap:
    """读取原图（剪贴板/打开用）。"""
    return QPixmap(str(resolve_file(project, shot)))


def export_zip(project: Project, zip_path: Path) -> int:
    """导出全部已保存截图为 zip，返回张数。"""
    files = sorted(p for p in project.shots_dir.glob("*.png"))
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f"shots/{f.name}")
    return len(files)
