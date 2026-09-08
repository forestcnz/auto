"""服务层端到端冒烟测试（不依赖显示器）。QPixmap 需先建 QGuiApplication。"""
import tempfile
from pathlib import Path

from PySide6.QtGui import QGuiApplication

_app = QGuiApplication([])  # offscreen 下仅用于满足 QPixmap 前置条件

from PIL import Image

from auto_assets.services import storage
from auto_assets.services.project import ProjectService

tmp = Path(tempfile.mkdtemp())
svc = ProjectService()
p = svc.create_project("测试工程A", tmp)
print("1. create ->", p.path.exists(), (p.path / "shots").exists())

# 模拟捕获
img = Image.new("RGB", (640, 400), (30, 40, 60))
shot, pm = storage.stage_capture(p, img)
p.meta.shots.insert(0, shot)
print("2. stage ->", shot.name, "seq=", shot.seq, "saved=", shot.saved, "pixmap=", not pm.isNull())

# 保存
storage.save_shot(p, shot)
svc.save_meta(p)
f = p.path / shot.file
print("3. save ->", f.exists(), shot.file)

# 重命名
storage.rename_shot(p, shot, "登录页_正常态")
svc.save_meta(p)
print("4. rename ->", (p.path / shot.file).exists(), shot.file, shot.name)

# 第二张 + 删除
img2 = Image.new("RGB", (300, 200), (90, 20, 20))
s2, _ = storage.stage_capture(p, img2)
p.meta.shots.insert(0, s2)
storage.save_shot(p, s2)
svc.save_meta(p)
storage.delete_shot(p, s2)
p.meta.shots = [s for s in p.meta.shots if s.id != s2.id]
svc.save_meta(p)
print("5. delete ->", len(p.meta.shots), "shot left")

# 导出
zp = tmp / "out.zip"
n = storage.export_zip(p, zp)
print("6. export ->", zp.exists(), n, "file(s)")

# 重载
p2 = svc.load_project(p.path)
print("7. reload ->", p2.name, len(p2.meta.shots), p2.meta.shots[0].name)

# 配置
print("8. config recent ->", [r.path for r in svc.config.recent])

# 清理：移除指向临时目录的污染条目（不影响真实工程）
import tempfile as _tf
_tmp_root = str(Path(_tf.gettempdir()))
svc.config.recent = [r for r in svc.config.recent if not r.path.startswith(_tmp_root)]
svc.save_config()
print("cleaned, recent ->", [r.path for r in svc.config.recent])
print("ALL OK")
