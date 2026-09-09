"""自动化项目（项目编辑）服务层冒烟测试。"""
import json
import tempfile
from pathlib import Path

from PIL import Image
from PySide6.QtGui import QGuiApplication

_app = QGuiApplication([])

from auto_assets.services.automation import AutomationService
from auto_assets.services.project import ProjectService

tmp = Path(tempfile.mkdtemp())
cfg_svc = ProjectService()
auto = AutomationService(cfg_svc, root=str(tmp))

# 1. 创建（loop 类型）
h = auto.create_project("自动签到", "loop", 50)
print("1. create ->", (h.path / "project.json").exists(), (h.path / "templates").exists())
data = json.loads((h.path / "project.json").read_text("utf-8"))
assert set(data.keys()) == {"name", "type", "times", "steps", "script"}, data.keys()
print("   schema keys:", list(data.keys()), "| type:", data["type"], "| times:", data["times"])

# 2. 列表
items = auto.list_projects()
print("2. list ->", len(items), "项目:", items[0].data.name)

# 3. 导入模板（模拟从素材工程复制一张截图）
src = tmp / "素材.png"
Image.new("RGB", (200, 100), (60, 60, 60)).save(src)
rel = auto.import_template(h.path, src)
print("3. import ->", rel, "| 文件存在:", (h.path / rel).exists())

# 4. 写步骤 + 保存 + 重载
from auto_assets.models import AutoStep

h.data.steps.append(AutoStep(template=rel, action="click", score=0.85, strategy="skip"))
h.data.steps.append(AutoStep(template=rel, action="click", score=0.9, strategy="exit"))
auto.save_project(h)
h2 = auto.load_project(h.path)
print("4. reload ->", len(h2.data.steps), "steps |",
      [(s.template, s.score, s.strategy) for s in h2.data.steps])
assert h2.data.steps[1].strategy == "exit"

# 5. any 类型（times 不生效仍写出）
h3 = auto.create_project("单次任务", "any", 1000)
data3 = json.loads((h3.path / "project.json").read_text("utf-8"))
assert data3["type"] == "any" and isinstance(data3["times"], int)
print("5. any type OK:", data3["type"])

# 6. 删除
auto.delete_project(h3.path)
print("6. delete ->", not h3.path.exists(), "| 剩余:", len(auto.list_projects()))
# 清理 auto_recent 临时条目
import tempfile as _tf
_sys_tmp = str(Path(_tf.gettempdir()))
cfg_svc.config.auto_recent = [
    p for p in cfg_svc.config.auto_recent if not p.startswith(_sys_tmp)
]
cfg_svc.save_config()
print("ALL OK")
