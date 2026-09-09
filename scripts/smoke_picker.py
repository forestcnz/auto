"""TemplatePicker 显示名称验证 + 策略文案按类型 + config 还原。"""
import json
import tempfile
from pathlib import Path

from PIL import Image
from PySide6.QtWidgets import QApplication

from auto_assets.services.project import ProjectService
from auto_assets.services.automation import AutomationService
from auto_assets.services import storage
from auto_assets.models import AutoStep
from auto_assets.ui.edit_tab import ProjectEditView, TemplatePicker

app = QApplication([])
tmp = Path(tempfile.mkdtemp())
svc = ProjectService()
h = svc.create_project("界面素材库", tmp)
shot_img = tmp / "界面素材库" / "shots" / "按钮.png"
shot_img.parent.mkdir(parents=True, exist_ok=True)
Image.new("RGB", (120, 60), (80, 80, 80)).save(shot_img)

pk = TemplatePicker(svc)
labels = [pk.proj_combo.itemText(i) for i in range(pk.proj_combo.count())]
print("1. picker 下拉显示:", labels)
for t in labels:
    assert ":" not in t and "\\" not in t and "/" not in t, f"路径泄漏: {t}"
print("   无路径泄漏 ✓  userData:", pk.proj_combo.currentData())

auto = AutomationService(svc, root=str(tmp))
ha = auto.create_project("any项目", "any", 1000)
ha.data.steps.append(AutoStep(template=auto.import_template(ha.path, shot_img)))
auto.save_project(ha)
v = ProjectEditView(svc, root=str(tmp))
v.show()
v.proj_list.setCurrentRow(0)
app.processEvents()
strat = v.table.cellWidget(0, 4)
print("2. any  策略项:", [strat.itemText(i) for i in range(strat.count())])
v.type_combo.setCurrentIndex(1)
app.processEvents()
strat = v.table.cellWidget(0, 4)
print("3. loop 策略项:", [strat.itemText(i) for i in range(strat.count())])
print("   times enabled:", v.times_spin.isEnabled())

# 步骤复制 / 上下移动 + 自动保存持久化
h0 = v._handle
assert h0 is not None and len(h0.data.steps) == 1
rel2 = auto.import_template(h0.path, shot_img)  # 同图再导一份 → 不同文件名
h0.data.steps.append(AutoStep(template=rel2, action="click", score=0.9, strategy="exit"))
h0.data.steps.append(AutoStep(template=rel2, action="double_click", score=0.8, strategy="skip"))
auto.save_project(h0)
assert [s.score for s in h0.data.steps] == [0.85, 0.9, 0.8]
v._copy_step(0)  # 复制首步 → 插入到其后
assert [s.score for s in h0.data.steps] == [0.85, 0.85, 0.9, 0.8]
v._move_step(0, -1)  # 越界 no-op
assert [s.score for s in h0.data.steps] == [0.85, 0.85, 0.9, 0.8]
v._move_step(2, -1)  # 第三步上移一位
assert [s.score for s in h0.data.steps] == [0.85, 0.9, 0.85, 0.8]
v._move_step(3, 1)  # 末步下移 no-op
assert [s.score for s in h0.data.steps] == [0.85, 0.9, 0.85, 0.8]
h_reload = auto.load_project(h0.path)  # 重载验证自动保存已落盘
assert [s.score for s in h_reload.data.steps] == [0.85, 0.9, 0.85, 0.8]
assert [s.action for s in h_reload.data.steps] == ["click", "click", "click", "double_click"]
print("5. 步骤复制/移动 + 持久化 OK:", len(h_reload.data.steps), "steps")

# 还原真实 config（移除本次测试的临时条目）
cfg_file = Path.home() / "AppData" / "Roaming" / "auto_assets" / "config.json"
data = json.loads(cfg_file.read_text("utf-8"))
tmp_root = str(Path(tempfile.gettempdir()))
data["recent"] = [r for r in data.get("recent", []) if not r["path"].startswith(tmp_root)]
data["auto_recent"] = [p for p in data.get("auto_recent", []) if not p.startswith(tmp_root)]
cfg_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
print("4. config 已还原, recent:", len(data["recent"]))
print("ALL OK")
