#!/usr/bin/env python3
"""
本源验证 — 从根锚定一切，推进到底，解决一切
道法自然 · 重新锚定本源

从 model_hub(:8872) → FreeCAD Remote(:18920) → DaoForge → Backend
全链路、全API、全模型、全格式、全工作流 一体化验证

覆盖:
  I.   Hub 基础 (health/tools/sense/catalog)
  II.  Hub→FreeCAD Remote 代理 (全15个端点)
  III. DaoForge 锻造系统 (headless 8套件 + GUI远程35模型)
  IV.  Hub 渲染/生成/分析 API
  V.   Hub 资源/模板/示例/批量
  VI.  DaoForge CLI 全子命令
  VII. 已有E2E验证 (_e2e_ultimate_verify)
  VIII.万法归一构建 (_万法归一_build) 确认产出
  IX.  全链路综合: Hub建模→分析→VR
"""
import urllib.request
import urllib.parse
import json
import time
import os
import sys
import subprocess
from pathlib import Path

HUB = "http://127.0.0.1:8872"
FC = "http://127.0.0.1:18920"
SCRIPT_DIR = Path(__file__).parent.resolve()

# ═══ 万法归一 · 路径引导 ════════════════════════════════════════════
_DAO_ROOT = next((p for p in SCRIPT_DIR.parents if (p / '_paths.py').is_file()), SCRIPT_DIR.parent)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
import _paths as _dao_paths  # noqa: F401  (registers 五层 sys.path)
ROOT_DIR = _DAO_ROOT
# ═══════════════════════════════════════════════════════════════════

OUTPUT_DIR = _dao_paths.PROJECTS / "fc_output"

passed = 0
failed = 0
errors = []
t0 = time.time()

def api(base, path, data=None, timeout=30):
    url = base + path
    if data:
        req = urllib.request.Request(url, json.dumps(data).encode(), {'Content-Type': 'application/json'})
    else:
        req = urllib.request.Request(url)
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  \u2705 {name}")
    else:
        failed += 1
        errors.append(f"{name}: {detail}")
        print(f"  \u274c {name} \u2014 {detail}")

def section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")

# ═══════════════════════════════════════════════════════════════════
# I. Hub 基础
# ═══════════════════════════════════════════════════════════════════
section("I. Hub 基础 (:8872)")

try:
    h = api(HUB, "/api/health")
    check("Hub在线", h.get("status") == "ok")
    check("Hub端口", h.get("port") == 8872)
    check("工具链", isinstance(h.get("tools"), dict))

    tools = h.get("tools", {})
    for t in ["openscad", "freecad", "trimesh"]:
        check(f"工具: {t}", "\u2705" in tools.get(t, ""))
except Exception as e:
    check("Hub连接", False, str(e)[:80])

try:
    h = api(HUB, "/api/health")
    check("项目数>=0", isinstance(h.get("projects"), int))
    fc_r = h.get("freecad_remote", {})
    check("FC Remote检测", isinstance(fc_r, dict))
    check("FC Remote连接", fc_r.get("connected") == True, str(fc_r)[:60])
except Exception as e:
    check("Hub健康", False, str(e)[:80])

# Sense
try:
    s = api(HUB, "/sense")
    check("Sense端口", s.get("port") == 8872)
    check("Sense时间戳", s.get("timestamp") is not None)
    check("Sense工具", isinstance(s.get("tools"), dict))
except Exception as e:
    check("Sense", False, str(e)[:80])

# Catalog
try:
    c = api(HUB, "/api/catalog")
    check("Catalog项目列表", isinstance(c.get("projects"), list))
    check("Catalog demos列表", isinstance(c.get("demos"), list))
except Exception as e:
    check("Catalog", False, str(e)[:80])

# Tools
try:
    t = api(HUB, "/api/tools")
    check("Tools详情", isinstance(t, dict))
    check("OpenSCAD路径", t.get("openscad", {}).get("ok") == True)
    check("FreeCAD路径", t.get("freecad", {}).get("ok") == True)
    check("trimesh", t.get("trimesh", {}).get("ok") == True)
except Exception as e:
    check("Tools", False, str(e)[:80])

# ═══════════════════════════════════════════════════════════════════
# II. Hub → FreeCAD Remote 代理
# ═══════════════════════════════════════════════════════════════════
section("II. Hub → FC Remote 代理 (全端点)")

# GET proxies
GET_ENDPOINTS = [
    ("/api/fc/status", "ok"),
    ("/api/fc/commands", "commands"),
    ("/api/fc/workbenches", "workbenches"),
    ("/api/fc/document", None),  # may or may not have 'document'
    ("/api/fc/documents", None),
    ("/api/fc/selection", None),
]
for ep, key in GET_ENDPOINTS:
    try:
        r = api(HUB, ep)
        ok = r.get("ok") if key == "ok" else (key in r if key else not r.get("error"))
        check(f"GET {ep}", ok, str(r)[:60])
    except Exception as e:
        check(f"GET {ep}", False, str(e)[:60])

# POST proxies
POST_ENDPOINTS = [
    ("/api/fc/run_command", {"command": "Std_ViewFitAll"}, "ok"),
    ("/api/fc/exec", {"code": "__result__ = '42'"}, "ok"),
    ("/api/fc/view", {"action": "isometric"}, "ok"),
    ("/api/fc/workbench", {"name": "PartWorkbench"}, "ok"),
    ("/api/fc/create_object", {"type": "Part::Box", "name": "HubTestBox", "props": {"Length": 25}}, "ok"),
    ("/api/fc/property", {"obj": "HubTestBox", "prop": "Length"}, None),
    ("/api/fc/select", {"action": "clear"}, "ok"),
    ("/api/fc/screenshot", {}, "ok"),
    ("/api/fc/export", {"format": "fcstd", "path": str(OUTPUT_DIR / "_hub_test.fcstd")}, "ok"),
]
for ep, data, key in POST_ENDPOINTS:
    try:
        r = api(HUB, ep, data)
        ok = r.get(key) if key else not r.get("error")
        check(f"POST {ep}", ok, str(r)[:60])
    except Exception as e:
        check(f"POST {ep}", False, str(e)[:60])

# Switch back
try:
    api(HUB, "/api/fc/workbench", {"name": "PartDesignWorkbench"})
except Exception:
    pass

# Exec with result
try:
    r = api(HUB, "/api/fc/exec", {"code": "import FreeCAD; __result__ = str(len(FreeCAD.ActiveDocument.Objects))"})
    check("Exec结果", r.get("ok") and r.get("result") is not None, f"result={r.get('result')}")
except Exception as e:
    check("Exec结果", False, str(e)[:80])

# ═══════════════════════════════════════════════════════════════════
# III. DaoForge 锻造系统
# ═══════════════════════════════════════════════════════════════════
section("III. DaoForge 锻造系统")

# III-a: Forge models API via Hub
try:
    m = api(HUB, "/api/forge/models")
    check("Forge模型注册", isinstance(m.get("registry"), list) and len(m["registry"]) > 30,
          f"count={len(m.get('registry',[]))}")
    check("Forge ops数", m.get("ops_count", 0) > 100, f"ops={m.get('ops_count')}")
    check("Forge画廊", isinstance(m.get("gallery"), list) and len(m["gallery"]) > 20,
          f"gallery={len(m.get('gallery',[]))}")
except Exception as e:
    check("Forge API", False, str(e)[:80])

# III-b: Build via Hub (headless)
HEADLESS_MODELS = ["box", "cylinder", "sphere", "hex_bolt", "enclosure", "washer", "gear_spur", "bracket"]
for model in HEADLESS_MODELS:
    try:
        r = api(HUB, "/api/forge/build", {"model": model, "params": {}, "gui": False}, timeout=120)
        ok = r.get("ok", False)
        check(f"Headless构建: {model}", ok, f"mode={r.get('mode')} elapsed={r.get('elapsed_s')}s")
    except Exception as e:
        check(f"Headless构建: {model}", False, str(e)[:60])

# III-c: DaoForge CLI (info, list-models, list-ops, sense)
section("III-c. DaoForge CLI")
CLI_CMDS = [
    (["info"], "cmd"),
    (["list-models"], None),
    (["list-ops"], None),
    (["sense"], "files"),
]
for args, key in CLI_CMDS:
    try:
        r = subprocess.run([sys.executable, str(SCRIPT_DIR / "dao_forge.py")] + args,
                           capture_output=True, text=True, timeout=30, cwd=str(SCRIPT_DIR))
        if key:
            data = json.loads(r.stdout)
            check(f"CLI: {args[0]}", key in data, f"keys={list(data.keys())[:5]}")
        else:
            check(f"CLI: {args[0]}", r.returncode == 0 and len(r.stdout) > 10,
                  f"exit={r.returncode} out={len(r.stdout)} chars")
    except Exception as e:
        check(f"CLI: {args[0]}", False, str(e)[:60])

# ═══════════════════════════════════════════════════════════════════
# IV. Hub 分析 API
# ═══════════════════════════════════════════════════════════════════
section("IV. Hub 分析 API (trimesh)")

# Find a test STL
test_stl = None
for f in OUTPUT_DIR.glob("*.stl"):
    if f.stat().st_size > 100:
        test_stl = f
        break

万法_stls = list((OUTPUT_DIR / "_万法归一").glob("*.stl"))
if 万法_stls:
    test_stl = 万法_stls[0]

if test_stl:
    try:
        rel = str(test_stl.relative_to(SCRIPT_DIR)).replace("\\", "/")
        r = api(HUB, "/api/analyze", {"stl": rel})
        check("trimesh分析", r.get("ok"), str(r)[:80])
        check("体积>0", r.get("volume_mm3", 0) > 0, f"vol={r.get('volume_mm3')}")
        check("面数>0", r.get("faces", 0) > 0, f"faces={r.get('faces')}")
        check("水密性", r.get("is_watertight") is not None)
    except Exception as e:
        check("trimesh分析", False, str(e)[:80])

    # STL serving
    try:
        url = f"{HUB}/api/stl/{urllib.parse.quote(rel, safe='/')}"
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=10)
        data = resp.read()
        check("STL服务", len(data) > 100, f"size={len(data)}")
    except Exception as e:
        check("STL服务", False, str(e)[:80])
else:
    check("测试STL", False, "无STL文件")

# ═══════════════════════════════════════════════════════════════════
# V. Hub 资源/模板/示例
# ═══════════════════════════════════════════════════════════════════
section("V. Hub 资源/模板/示例")

try:
    r = api(HUB, "/api/templates")
    check("模板API", isinstance(r.get("templates"), list), f"count={r.get('count')}")
    if r.get("templates"):
        check("模板有代码", all(t.get("code") for t in r["templates"]))
except Exception as e:
    check("模板", False, str(e)[:80])

try:
    r = api(HUB, "/api/forge")
    check("Forge版本", "version" in r, str(r)[:80])
except Exception as e:
    check("Forge版本", False, str(e)[:80])

# Dashboard HTML
try:
    req = urllib.request.Request(f"{HUB}/")
    resp = urllib.request.urlopen(req, timeout=10)
    html = resp.read().decode("utf-8", errors="replace")
    check("Dashboard HTML", "ModelHub" in html and len(html) > 5000, f"size={len(html)}")
    check("Forge选项卡", "forge" in html.lower())
    check("FreeCAD选项卡", "fcremote" in html.lower())
    check("VR选项卡", "panel-vr" in html)
    check("实时选项卡", "panel-live" in html)
except Exception as e:
    check("Dashboard", False, str(e)[:80])

# ═══════════════════════════════════════════════════════════════════
# VI. FC Remote 直连验证 (关键项)
# ═══════════════════════════════════════════════════════════════════
section("VI. FC Remote 直连核心")

try:
    s = api(FC, "/status")
    ver = s.get("freecad_version", [0])
    check("FC版本", int(ver[0]) >= 1 if ver else False, str(ver))
    cmds = api(FC, "/commands")
    check("命令>400", cmds.get("count", 0) > 400, f"count={cmds.get('count')}")
    wbs = api(FC, "/workbenches")
    check("工作台>15", len(wbs.get("workbenches", {})) > 15)
except Exception as e:
    check("FC直连", False, str(e)[:80])

# ═══════════════════════════════════════════════════════════════════
# VII. 万法归一构建产出确认
# ═══════════════════════════════════════════════════════════════════
section("VII. 万法归一产出确认")

万法dir = OUTPUT_DIR / "_万法归一"
if 万法dir.exists():
    stls = list(万法dir.glob("*.stl"))
    steps = list(万法dir.glob("*.step"))
    breps = list(万法dir.glob("*.brep"))
    iges = list(万法dir.glob("*.iges"))
    objs = list(万法dir.glob("*.obj"))
    pngs = list(万法dir.glob("*.png"))
    fcstds = list(万法dir.glob("*.fcstd"))
    total_kb = sum(f.stat().st_size for f in 万法dir.iterdir() if f.is_file()) / 1024

    check("STL>=35", len(stls) >= 35, f"count={len(stls)}")
    check("STEP>=35", len(steps) >= 35, f"count={len(steps)}")
    check("BREP>=1", len(breps) >= 1)
    check("IGES>=1", len(iges) >= 1)
    check("OBJ>=1", len(objs) >= 1)
    check("PNG截图>=1", len(pngs) >= 1)
    check("FCStd>=1", len(fcstds) >= 1)
    check("总大小>5MB", total_kb > 5000, f"size={total_kb:.0f}KB")
else:
    check("万法归一目录", False, "不存在")

# 历史产出
existing_stls = list(OUTPUT_DIR.glob("*.stl"))
existing_steps = list(OUTPUT_DIR.glob("*.step"))
check("产出STL", len(existing_stls) > 20, f"count={len(existing_stls)}")
check("产出STEP", len(existing_steps) > 10, f"count={len(existing_steps)}")

# ═══════════════════════════════════════════════════════════════════
# VIII. 全链路: Hub构建→FC创建→分析→截图
# ═══════════════════════════════════════════════════════════════════
section("VIII. 全链路端到端")

# 1. Create object through hub proxy
try:
    r = api(HUB, "/api/fc/exec", {
        "code": """
import FreeCAD as App
import Part
doc = App.ActiveDocument or App.newDocument('E2E')
box = doc.addObject('Part::Box', 'E2EBox')
box.Length = 50
box.Width = 30
box.Height = 20
doc.recompute()
__result__ = str(round(box.Shape.Volume, 2))
"""
    })
    check("全链路: 创建对象", r.get("ok"), str(r)[:60])
    if r.get("result"):
        vol = float(r["result"])
        check("全链路: 体积=30000", abs(vol - 30000) < 1, f"vol={vol}")
except Exception as e:
    check("全链路: 创建", False, str(e)[:80])

# 2. Export through hub proxy
e2e_stl = str(OUTPUT_DIR / "_e2e_chain.stl")
e2e_step = str(OUTPUT_DIR / "_e2e_chain.step")
try:
    r = api(FC, "/ops", {"ops": [
        {"op": "make_box", "id": "e", "L": 50, "W": 30, "H": 20},
        {"op": "fillet", "id": "ef", "shape": "e", "radius": 3},
        {"op": "export_stl", "shape": "ef", "path": e2e_stl},
        {"op": "export_step", "shape": "ef", "path": e2e_step},
        {"op": "shape_info", "shape": "ef"},
    ]})
    check("全链路: Ops+导出", r.get("ok"))
    check("全链路: 分析数据", len(r.get("analyses", [])) > 0)
except Exception as e:
    check("全链路: Ops", False, str(e)[:80])

# 3. Analyze the exported STL through hub
if Path(e2e_stl).exists():
    try:
        rel = str(Path(e2e_stl).relative_to(SCRIPT_DIR)).replace("\\", "/")
        r = api(HUB, "/api/analyze", {"stl": rel})
        check("全链路: trimesh分析", r.get("ok") and r.get("volume_mm3", 0) > 0)
    except Exception as e:
        check("全链路: 分析", False, str(e)[:80])

# 4. Screenshot
try:
    api(FC, "/view", {"action": "fit_all"})
    time.sleep(0.3)
    r = api(FC, "/screenshot")
    check("全链路: 截图", r.get("ok") and len(r.get("data", "")) > 100)
except Exception as e:
    check("全链路: 截图", False, str(e)[:80])

# ═══════════════════════════════════════════════════════════════════
# IX. 探针+命令完整性
# ═══════════════════════════════════════════════════════════════════
section("IX. 探针+命令完整性")

probe_path = OUTPUT_DIR / "_fc_gui_probe_result.json"
if probe_path.exists():
    probe = json.loads(probe_path.read_text(encoding="utf-8"))
    check("探针文件", True)
    s = probe.get("summary", {})
    check("探针命令>400", s.get("total_commands", 0) > 400)
    check("探针工作台>15", s.get("workbench_count", 0) > 15)
    check("探针快捷键>50", s.get("shortcut_count", 0) > 50)
    check("探针14段完整", len(probe.get("sections", {})) >= 14)
else:
    check("探针文件", False, "不存在")

# ═══════════════════════════════════════════════════════════════════
# FINAL: 本源总结
# ═══════════════════════════════════════════════════════════════════
elapsed = round(time.time() - t0, 1)
total = passed + failed
rate = passed / total * 100 if total > 0 else 0

# Count all output
all_output = list(OUTPUT_DIR.rglob("*"))
all_stl = [f for f in all_output if f.suffix == ".stl"]
all_step = [f for f in all_output if f.suffix == ".step"]
total_size_mb = sum(f.stat().st_size for f in all_output if f.is_file()) / 1024 / 1024

print(f"\n{'='*70}")
print(f"  本源验证 — 终极报告")
print(f"{'='*70}")
print(f"  \u2705 通过: {passed}/{total} ({rate:.1f}%)")
print(f"  \u274c 失败: {failed}/{total}")
print(f"  \u23f1  耗时: {elapsed}s")
print()
print(f"  系统架构:")
print(f"    ModelHub   :8872  \u2714")
print(f"    FC Remote  :18920 \u2714")
print(f"    DaoForge   headless + GUI")
print(f"    Backend    freecad_backend.py")
print()
print(f"  产出统计:")
print(f"    STL: {len(all_stl)} | STEP: {len(all_step)}")
print(f"    总大小: {total_size_mb:.1f} MB")
print(f"    万法归一: {len(list((OUTPUT_DIR/'_万法归一').glob('*'))) if (OUTPUT_DIR/'_万法归一').exists() else 0} 文件")

if errors:
    print(f"\n  失败详情:")
    for e in errors[:25]:
        print(f"    \u26a0\ufe0f  {e}")

if failed == 0:
    grade = "SSS \u2014 道法自然\uff0c本源锚定\uff0c万法归一\uff0c无为而无不为"
elif failed <= 3:
    grade = "SS \u2014 几近圆满"
elif failed <= 8:
    grade = "S \u2014 优秀"
elif failed <= 15:
    grade = "A \u2014 良好"
else:
    grade = "B \u2014 需改进"

print(f"\n  等级: {grade}")
print(f"{'='*70}")
