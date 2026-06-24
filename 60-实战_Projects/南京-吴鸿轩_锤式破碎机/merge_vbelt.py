#!/usr/bin/env python3
"""
将V带STL合并进完整装配体 - 纯Python struct (无外部依赖)
道法自然 · 万法归宗

★ 反者道之动 (2026-04-18): STL 三角级读/写 hoist 到
  00-本源_Origin/dao_mesh.py · read_stl_triangles + write_stl_binary.
"""
import sys
from pathlib import Path

# ═══ 万法归一 · 路径引导 ══════════════════════════════════════════
_HERE = Path(__file__).resolve().parent
_DAO_ROOT = next((p for p in Path(__file__).resolve().parents
                  if (p / '_paths.py').is_file()), _HERE)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
import _paths as _dao_paths  # noqa: F401
from dao_mesh import read_stl_triangles, write_stl_binary as _write_stl
# ═══════════════════════════════════════════════════════════════

OUT = _HERE / "output_cq"

def write_stl(path, triangles):
    """兼容原 API: path + triangles → 二进制 STL. 本源: dao_mesh.write_stl_binary."""
    return _write_stl(path, triangles)

asm_src  = OUT / "assembly_complete.stl"
belt_src = OUT / "vbelt_all.stl"
dst      = OUT / "assembly_complete_v4.stl"

if not asm_src.exists():
    print(f"❌ {asm_src} not found"); raise SystemExit(1)
if not belt_src.exists():
    print(f"❌ {belt_src} not found"); raise SystemExit(1)

print(f"读取装配体 {asm_src.name}...")
asm_tris  = read_stl_triangles(str(asm_src))
print(f"  {len(asm_tris)} triangles")

print(f"读取V带    {belt_src.name}...")
belt_tris = read_stl_triangles(str(belt_src))
print(f"  {len(belt_tris)} triangles")

all_tris = asm_tris + belt_tris
write_stl(str(dst), all_tris)
sz = dst.stat().st_size
print(f"\n[OK] STL: {dst.name}  {len(all_tris)} triangles  {sz//1024}KB")

# GLB导出 (需要trimesh)
glb_dst = OUT / "assembly_complete_v4.glb"
try:
    import trimesh
    mesh = trimesh.load(str(dst), force="mesh")
    mesh.export(str(glb_dst))
    sz_glb = glb_dst.stat().st_size
    print(f"[OK] GLB: {glb_dst.name}  {sz_glb//1024}KB")
except ImportError:
    print("[WARN] trimesh not installed, skip GLB (pip install trimesh)")
except Exception as e:
    print(f"[WARN] GLB export failed: {e}")

print("[DONE] complete assembly with V-belts")
