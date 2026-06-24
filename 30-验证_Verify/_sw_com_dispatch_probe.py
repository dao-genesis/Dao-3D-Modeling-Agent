#!/usr/bin/env python3
"""探针: 4 种 COM 获取方式下 NewDocument 的可用性"""
import sys, os, glob
import pythoncom
import win32com.client as wc
import win32com.client.dynamic as dyn

pythoncom.CoInitialize()

# 4 种方式获取 COM 对象
targets = {}

try:
    targets["Dispatch"] = wc.Dispatch("SldWorks.Application")
except Exception as e:
    print(f"Dispatch FAIL: {e}")

try:
    targets["dynamic"] = dyn.Dispatch("SldWorks.Application")
except Exception as e:
    print(f"dynamic FAIL: {e}")

try:
    targets["GetActive"] = wc.GetActiveObject("SldWorks.Application.31")
except Exception as e:
    print(f"GetActive FAIL: {e}")

if "GetActive" in targets:
    try:
        targets["dyn_oleobj"] = dyn.Dispatch(targets["GetActive"]._oleobj_)
    except Exception as e:
        print(f"dyn_oleobj FAIL: {e}")

# 探测
for label, app in targets.items():
    print(f"\n{'='*60}")
    print(f"  {label}: {type(app).__name__} (module={type(app).__module__})")
    print(f"{'='*60}")
    has = hasattr(app, "NewDocument")
    print(f"  hasattr(NewDocument): {has}")
    try:
        nd = app.NewDocument
        print(f"  .NewDocument = {nd!r} (type={type(nd).__name__})")
    except Exception as e:
        print(f"  .NewDocument ERR: {type(e).__name__}: {e}")

    # RevisionNumber
    try:
        rev = app.RevisionNumber
        print(f"  .RevisionNumber = {rev!r}")
    except Exception as e:
        print(f"  .RevisionNumber ERR: {type(e).__name__}: {e}")

# 找模板
sw_dir = r"D:\Program Files\SOLIDWORKS Corp23\SOLIDWORKS"
tpls = glob.glob(os.path.join(sw_dir, "lang", "chinese-simplified", "Tutorial", "*.prtdot"))
if not tpls:
    tpls = glob.glob(os.path.join(sw_dir, "**", "*.prtdot"), recursive=True)
tpl = tpls[0] if tpls else ""
print(f"\nTemplate: {tpl} (exists={os.path.isfile(tpl)})")

# 实际调用
print(f"\n{'='*60}")
print("  实际调用 NewDocument")
print(f"{'='*60}")
for label, app in targets.items():
    try:
        doc = app.NewDocument(tpl, 0, 0, 0)
        dt = type(doc).__name__ if doc else "None"
        print(f"  {label}.NewDocument => type={dt}, is_none={doc is None}")
        # 关掉
        if doc:
            try:
                app.CloseDoc(doc.GetTitle())
            except Exception:
                pass
    except Exception as e:
        print(f"  {label}.NewDocument ERR: {type(e).__name__}: {e}")

print("\nDone.")
