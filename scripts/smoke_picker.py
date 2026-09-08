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

# 还原真实 config（移除本次测试的临时条目）
cfg_file = Path.home() / "AppData" / "Roaming" / "auto_assets" / "config.json"
data = json.loads(cfg_file.read_text("utf-8"))
tmp_root = str(Path(tempfile.gettempdir()))
data["recent"] = [r for r in data.get("recent", []) if not r["path"].startswith(tmp_root)]
data["auto_recent"] = [p for p in data.get("auto_recent", []) if not p.startswith(tmp_root)]
cfg_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
print("4. config 已还原, recent:", len(data["recent"]))
print("ALL OK")
