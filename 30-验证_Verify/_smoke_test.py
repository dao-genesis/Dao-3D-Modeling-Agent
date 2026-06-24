#!/usr/bin/env python3
"""万法归一 · 五层闭环 · 综合冒烟验证"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import _paths

print('ROOT:', _paths.ROOT)
print('Layers registered:')
for k in ('ORIGIN','REVERSE','FORGE','VERIFY','TEMPLATES','DEMO','PROJECTS','WORLD','LOGS'):
    p = getattr(_paths, k)
    print(f'  {k:10s} -> {p.name}  exists={p.exists()}')

print()
print('=== 00-本源 imports ===')
from dao_kernel import DaoKernel as K
from dao_audit import full_audit, heal_shape
from dao_reverse import DaoReverse
from dao_forge import DaoForge
from dao_engine import DaoEngine
print('  OK: dao_kernel, dao_audit, dao_reverse, dao_forge, dao_engine')

print()
print('=== 10-反笙 imports ===')
from fc_reverse import FCReverse
from fc_show import FCShow
from fc_model_builder import FCModelBuilder
from freecad_connection import FreeCADConnection
from freecad_bridge import FreeCADBridge
from freecad_gui_launcher import FreeCADGUILauncher
print('  OK: fc_reverse, fc_show, fc_model_builder, freecad_connection/bridge/gui_launcher')

print()
print('=== 20-万法 imports ===')
from forge_v3 import detect_tools
from model_hub import scan_projects
from design_intent_compiler import DesignIntentCompiler
from parametric_codegen import ParametricCodegen
from geometric_preflight import preflight
print('  OK: forge_v3, model_hub, design_intent_compiler, parametric_codegen, geometric_preflight')

print()
print('=== 30-验证 syntax check ===')
vdir = _paths.VERIFY
files = sorted(vdir.glob('*.py'))
for f in files:
    src = f.read_text(encoding='utf-8')
    try:
        compile(src, str(f), 'exec')
    except SyntaxError as e:
        print(f'  FAIL {f.name}: {e}')
        sys.exit(1)
print(f'  OK: {len(files)} verify scripts compile')

print()
print('=== 路径一致性 (关键文件) ===')
import dao_forge, dao_engine, fc_reverse, fc_model_builder, model_hub, freecad_gui_launcher
checks = [
    ('dao_forge.BACKEND_SCRIPT',  dao_forge.BACKEND_SCRIPT,     '10-反笙_FreeCAD', 'freecad_backend.py'),
    ('dao_forge.OUTPUT_DIR',      dao_forge.OUTPUT_DIR,         '60-实战_Projects', 'fc_output'),
    ('fc_reverse.CACHE_DIR',      fc_reverse.CACHE_DIR,         '70-天下_World',    '.resource_cache'),
    ('fc_model_builder.OUTPUT',   fc_model_builder.OUTPUT_DIR,  '60-实战_Projects', 'fc_output'),
    ('model_hub.PROJECTS_DIR',    model_hub.PROJECTS_DIR,       None,               '60-实战_Projects'),
    ('model_hub.DEMO_DIR',        model_hub.DEMO_DIR,           None,               '50-演示_Demo'),
    ('freecad_gui_launcher.OUT',  freecad_gui_launcher.OUTPUT_DIR, '60-实战_Projects', 'fc_output'),
]
all_ok = True
for name, p, expect_parent, expect_name in checks:
    ok = p.name == expect_name
    if expect_parent:
        ok = ok and (p.parent.name == expect_parent)
    status = '✓' if ok else '✗'
    print(f'  [{status}] {name:32s} = {p}')
    if not ok:
        all_ok = False

print()
if all_ok:
    print('=== 万法归一 · 五层全通 ✓ ===')
else:
    print('=== 检测到路径不一致 ✗ ===')
    sys.exit(1)
