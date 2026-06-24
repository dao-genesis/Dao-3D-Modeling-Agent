#!/usr/bin/env python3
"""SolidWorks COM 直连探针 · 道法自然"""
import sys, os, json, time
from pathlib import Path
from datetime import datetime

HERE = Path(__file__).parent.resolve()
OUT  = HERE / "sw_api"
OUT.mkdir(exist_ok=True)
LOG  = OUT / "sw_probe_log.json"

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")

# ── Phase 0: COM 连接 ────────────────────────────────────────
log("Phase 0 · COM 直连 SolidWorks ...")
try:
    import win32com.client
    sw = win32com.client.Dispatch("SldWorks.Application")
except Exception as e:
    log(f"FAIL · COM Dispatch 失败: {e}")
    log("请确保: (1) SolidWorks 已打开 (2) 本脚本在同一桌面会话运行")
    sys.exit(1)

rev = sw.RevisionNumber
vis = sw.Visible
log(f"OK · SolidWorks {rev}  Visible={vis}")

# ── Phase 1: 当前文档 ────────────────────────────────────────
doc = sw.ActiveDoc
if doc:
    log(f"ActiveDoc: {doc.GetTitle()}  Type={doc.GetType()}")
else:
    log("ActiveDoc: None (无活动文档)")

# ── Phase 2: 打开总装配 ──────────────────────────────────────
ASM_PATH = str(HERE / "交付包_最终" / "锤式破碎机_总装配.SLDASM")
log(f"Phase 2 · 打开装配: {ASM_PATH}")

if doc and doc.GetPathName().replace("/", "\\").lower() == ASM_PATH.lower():
    log("装配已打开, 跳过重新加载")
    asm = doc
else:
    # swDocASSEMBLY = 2
    arg_err = win32com.client.VARIANT(win32com.client.pythoncom.VT_BYREF | win32com.client.pythoncom.VT_I4, 0)
    warn_err = win32com.client.VARIANT(win32com.client.pythoncom.VT_BYREF | win32com.client.pythoncom.VT_I4, 0)
    asm = sw.OpenDoc6(ASM_PATH, 2, 1, "", arg_err, warn_err)  # swOpenDocOptions_Silent=1
    if asm is None:
        log(f"FAIL · 无法打开装配  err={arg_err.value}  warn={warn_err.value}")
        sys.exit(2)
    log(f"OK · 装配已打开: {asm.GetTitle()}")

# ── Phase 3: 零件清单 ────────────────────────────────────────
log("Phase 3 · 遍历零件 ...")
components = []
try:
    # GetComponents(TopLevelOnly)
    comps = asm.GetComponents(False)
    if comps:
        for c in comps:
            name = c.Name2
            path = c.GetPathName()
            suppressed = c.IsSuppressed()
            visible = c.Visible
            components.append({
                "name": name,
                "path": path,
                "suppressed": suppressed,
                "visible": visible,
            })
            status = "SUPP" if suppressed else ("VIS" if visible == 1 else "HID")
            log(f"  [{status}] {name}")
    log(f"共 {len(components)} 个组件")
except Exception as e:
    log(f"WARN · 遍历组件失败: {e}")

# ── Phase 4: 包围盒 ──────────────────────────────────────────
log("Phase 4 · 装配包围盒 ...")
try:
    bbox = asm.GetBox(True)  # visible only
    if bbox:
        bmin = [bbox[0]*1000, bbox[1]*1000, bbox[2]*1000]
        bmax = [bbox[3]*1000, bbox[4]*1000, bbox[5]*1000]
        sz = [round(bmax[i]-bmin[i], 1) for i in range(3)]
        log(f"bbox mm: min={[round(v,1) for v in bmin]} max={[round(v,1) for v in bmax]}")
        log(f"size mm: {sz}")
except Exception as e:
    log(f"WARN · 包围盒失败: {e}")

# ── Phase 5: 多视图截图 ──────────────────────────────────────
log("Phase 5 · 多视图截图 ...")
VIEWS = {
    "front":  (1, 0, 0, 0, 1, 0, 0, 0, 1),  # *Front
    "back":   (-1,0, 0, 0, 1, 0, 0, 0,-1),
    "right":  (0, 0,-1, 0, 1, 0, 1, 0, 0),
    "top":    (1, 0, 0, 0, 0,-1, 0, 1, 0),
    "iso":    None,  # use named view
}
SNAP_DIR = HERE / "交付包_最终" / "渲染图"
SNAP_DIR.mkdir(exist_ok=True)

model_view = asm.ActiveView
if model_view is None:
    log("WARN · 无法获取 ActiveView")
else:
    # 等轴测
    asm.ShowNamedView2("*Isometric", -1)
    asm.ViewZoomtofit2()
    time.sleep(0.5)
    fp = str(SNAP_DIR / "sw_isometric.png")
    ok = asm.SaveBMP(fp, 1920, 1080)
    log(f"  iso: {'OK' if ok else 'FAIL'} → {fp}")

    # 标准视图
    named_views = {"front": "*Front", "back": "*Back", "right": "*Right", "top": "*Top", "bottom": "*Bottom"}
    for vname, sw_name in named_views.items():
        asm.ShowNamedView2(sw_name, -1)
        asm.ViewZoomtofit2()
        time.sleep(0.3)
        fp = str(SNAP_DIR / f"sw_{vname}.png")
        ok = asm.SaveBMP(fp, 1920, 1080)
        log(f"  {vname}: {'OK' if ok else 'FAIL'} → {fp}")

# ── Phase 6: 导出 STEP ───────────────────────────────────────
log("Phase 6 · 导出 STEP AP214 ...")
step_path = str(HERE / "交付包_最终" / "锤式破碎机_总装配.STEP")
try:
    errors = win32com.client.VARIANT(win32com.client.pythoncom.VT_BYREF | win32com.client.pythoncom.VT_I4, 0)
    warnings = win32com.client.VARIANT(win32com.client.pythoncom.VT_BYREF | win32com.client.pythoncom.VT_I4, 0)
    ok = asm.Extension.SaveAs3(step_path, 0, 0, None, errors, warnings)
    if ok:
        sz = Path(step_path).stat().st_size
        log(f"OK · STEP 已导出 ({sz//1024}KB)")
    else:
        log(f"WARN · STEP 导出失败 err={errors.value}")
except Exception as e:
    log(f"WARN · STEP 导出异常: {e}")

# ── Phase 7: 导出 STL ────────────────────────────────────────
log("Phase 7 · 导出 STL ...")
stl_path = str(HERE / "交付包_最终" / "锤式破碎机_总装配.STL")
try:
    ok = asm.SaveAs2(stl_path, 0, True, False)
    if ok:
        sz = Path(stl_path).stat().st_size
        log(f"OK · STL 已导出 ({sz//1024}KB)")
    else:
        log(f"WARN · STL 导出返回 False")
except Exception as e:
    log(f"WARN · STL 导出异常: {e}")

# ── 写出探针日志 ──────────────────────────────────────────────
result = {
    "timestamp": datetime.now().isoformat(),
    "sw_revision": rev,
    "assembly": ASM_PATH,
    "components_count": len(components),
    "components": components,
}
LOG.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
log(f"探针日志: {LOG}")
log("道法自然 · SolidWorks 直连完成 ✓")
