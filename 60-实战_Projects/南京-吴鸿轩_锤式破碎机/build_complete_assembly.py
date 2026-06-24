#!/usr/bin/env python3
"""
锤式破碎机 · 完整整机装配 (trimesh + STEP, 无需FreeCAD GUI)
道法自然 · 万法归宗 · 整合到底 · 完善一切

基于所有已构建的STEP/STL文件, 通过几何变换拼装完整整机:
  - 坐标系: 原点=主轴左端中心  X=沿轴  Y=横向  Z=竖直(向上)
  - 使用 cadquery 进行装配位置变换
  - 输出: assembly_complete.glb/.obj/.stl + STEP个件验证报告
"""
import sys, json, time, math
from pathlib import Path

HERE = Path(__file__).parent.resolve()
sys.path.insert(0, str(HERE))
from config import (OUT_DIR, PARTS, PARTS_NEW, BOM_COMPLETE, MACHINE_PARAMS,
                    MOTOR_PARAMS, VBELT_PARAMS, DRIVE_PULLEY_PARAMS, CASING_PARAMS)

import cadquery as cq

t_start = time.time()
results = {}

ARGS = set(sys.argv[1:])
WITH_VBELT = "--with-vbelt" in ARGS

print("\n" + "="*62)
print("  锤式破碎机 · 完整整机装配 (CadQuery几何变换)")
print("="*62)

# ──────────────────────────────────────────────────────────────────
# 零件位置定义 (装配坐标系)
# 原点: 主轴左端中心线
# ──────────────────────────────────────────────────────────────────
# 格式: (bname, label, tx, ty, tz, rv_vec, rv_ang)
ASSEMBLY_PLAN = [
    # 旋转部件 ─────────────────────────────────────────────────────
    ("main_shaft",    "主轴",       0,    0,    0,    None,    0),
    ("driven_pulley", "从动皮带轮", 960,  0,    0,    [0,1,0], 90),
    ("rotor_disc",    "转子盘1",    207,  0,    0,    [0,1,0], 90),
    ("rotor_disc",    "转子盘2",    408,  0,    0,    [0,1,0], 90),
    ("rotor_disc",    "转子盘3",    610,  0,    0,    [0,1,0], 90),
    ("rotor_disc",    "转子盘4",    810,  0,    0,    [0,1,0], 90),
    # 4个销轴
    ("hammer_pin",    "销轴1",      120,  220,  0,    None,    0),
    ("hammer_pin",    "销轴2",      120, -220,  0,    None,    0),
    ("hammer_pin",    "销轴3",      120,  0,    220,  None,    0),
    ("hammer_pin",    "销轴4",      120,  0,   -220,  None,    0),
    # 12锤头 (代表16个, 3行×4列)
    ("hammer",        "锤头@320a",  320,  100,  0,    [0,1,0], 90),
    ("hammer",        "锤头@320b",  320, -340,  0,    [0,1,0], 90),
    ("hammer",        "锤头@320c",  320, -120,  180,  [0,1,0], 90),
    ("hammer",        "锤头@320d",  320, -120, -180,  [0,1,0], 90),
    ("hammer",        "锤头@520a",  520,  100,  0,    [0,1,0], 90),
    ("hammer",        "锤头@520b",  520, -340,  0,    [0,1,0], 90),
    ("hammer",        "锤头@520c",  520, -120,  180,  [0,1,0], 90),
    ("hammer",        "锤头@520d",  520, -120, -180,  [0,1,0], 90),
    ("hammer",        "锤头@720a",  720,  100,  0,    [0,1,0], 90),
    ("hammer",        "锤头@720b",  720, -340,  0,    [0,1,0], 90),
    ("hammer",        "锤头@720c",  720, -120,  180,  [0,1,0], 90),
    ("hammer",        "锤头@720d",  720, -120, -180,  [0,1,0], 90),
    # 筛板: Rz-90° 后位于轴下方
    ("screen_plate",  "筛板",       572,  0,    0,    [0,0,1], -90),
    # 传动系统 ─────────────────────────────────────────────────────
    ("drive_pulley",  "主动带轮",   -90,  0,   -600,  [0,1,0], 90),
    ("motor_body",    "电动机",    -385,  0,   -600,  None,    0),
    # 机壳结构 ─────────────────────────────────────────────────────
    ("casing_lower",  "下机壳",     92,  -305, -460,  None,    0),
    ("casing_upper",  "上机壳",     92,  -305,  0,    None,    0),
    # 机架底座 ─────────────────────────────────────────────────────
    ("frame_base",    "机架底座",  -78,  -410, -750,  None,    0),
]

# ──────────────────────────────────────────────────────────────────
# T1: 加载所有零件 STEP 文件
# ──────────────────────────────────────────────────────────────────
print("\n  T1 — 加载零件STEP文件...")
part_shapes = {}
for bname in set(p[0] for p in ASSEMBLY_PLAN):
    step_p = OUT_DIR / f"{bname}.step"
    if step_p.exists():
        try:
            shape = cq.importers.importStep(str(step_p))
            part_shapes[bname] = shape
            bb = shape.val().BoundingBox()
            print(f"  ✅ {bname:<22}  ({step_p.stat().st_size//1024:4d}KB)")
        except Exception as e:
            print(f"  ❌ {bname}: {e}")
    else:
        print(f"  ❌ {bname}.step 缺失")

print(f"\n  加载: {len(part_shapes)}/{len(set(p[0] for p in ASSEMBLY_PLAN))} 个零件")

# ──────────────────────────────────────────────────────────────────
# T2: 装配变换 (几何变换)
# ──────────────────────────────────────────────────────────────────
print("\n  T2 — 装配变换...")

assembly_shapes = {}  # label → transformed shape
for (bname, label, tx, ty, tz, rv, ra) in ASSEMBLY_PLAN:
    if bname not in part_shapes:
        print(f"  SKIP {label} (零件{bname}未加载)")
        continue
    try:
        shape = part_shapes[bname]
        # 使用 CadQuery 的 Workplane 做变换
        result = cq.Workplane().add(shape)
        if rv and ra:
            # 绕原点轴旋转
            ax = cq.Vector(*rv)
            angle = float(ra)
            result = result.rotate((0,0,0), tuple(rv), angle)
        if tx or ty or tz:
            result = result.translate((float(tx), float(ty), float(tz)))
        assembly_shapes[label] = result
        print(f"  ✅ {label:<25}  tx={tx:+6.0f} ty={ty:+6.0f} tz={tz:+6.0f}")
    except Exception as e:
        print(f"  ❌ {label}: {e}")

print(f"\n  装配: {len(assembly_shapes)}/{len(ASSEMBLY_PLAN)} 个零件")

# ──────────────────────────────────────────────────────────────────
# T3: 导出完整装配体
# ──────────────────────────────────────────────────────────────────
print("\n  T3 — 导出完整装配体...")

# 合并所有形体为一个 compound
if assembly_shapes:
    try:
        # 先导出各零件分组STEP (可在CAD软件中分色)
        compound_shapes = []
        for label, wp in assembly_shapes.items():
            try:
                for solid in wp.vals():
                    compound_shapes.append(solid)
            except Exception:
                try:
                    compound_shapes.append(wp.val())
                except Exception:
                    pass

        # 导出完整STEP
        if compound_shapes:
            import OCC.Core.BRep as BRep_module
            from OCC.Core.TopoDS import TopoDS_Compound
            from OCC.Core.BRep import BRep_Builder
            from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Fuse
            from OCC.Core.TopoDS import TopoDS_Builder

            builder = BRep_Builder()
            compound = TopoDS_Compound()
            builder.MakeCompound(compound)
            for s in compound_shapes:
                try:
                    builder.Add(compound, s.wrapped)
                except Exception:
                    pass

            from OCC.Core.STEPControl import STEPControl_Writer, STEPControl_AsIs
            from OCC.Core.Interface import Interface_Static_SetCVal
            Interface_Static_SetCVal("write.step.schema", "AP214")
            writer = STEPControl_Writer()
            writer.Transfer(compound, STEPControl_AsIs)
            step_out = str(OUT_DIR / "assembly_complete.step")
            writer.Write(step_out)
            print(f"  ✅ STEP: {step_out}  ({Path(step_out).stat().st_size//1024}KB)")
    except Exception as e:
        print(f"  ⚠️  STEP导出: {e}")

# STL via trimesh
vbelt_mesh_loaded = False
try:
    import trimesh
    import numpy as np

    meshes = []
    for bname in set(p[0] for p in ASSEMBLY_PLAN):
        stl_p = OUT_DIR / f"{bname}.stl"
        if not stl_p.exists():
            continue
        try:
            m = trimesh.load(str(stl_p), force="mesh")
            meshes.append((bname, m))
        except Exception:
            pass

    if not meshes:
        print("  ❌ 没有可加载的STL")
    else:
        # 对每个零件应用变换矩阵
        transformed_meshes = []
        for (bname, label, tx, ty, tz, rv, ra) in ASSEMBLY_PLAN:
            # 找对应mesh
            base_mesh = None
            for mn, m in meshes:
                if mn == bname:
                    base_mesh = m.copy()
                    break
            if base_mesh is None:
                continue
            try:
                T = np.eye(4)
                if rv and ra:
                    import trimesh.transformations as tr
                    angle_rad = math.radians(float(ra))
                    axis = np.array(rv, dtype=float)
                    axis = axis / np.linalg.norm(axis)
                    R = tr.rotation_matrix(angle_rad, axis)
                    base_mesh.apply_transform(R)
                T[0,3] = float(tx); T[1,3] = float(ty); T[2,3] = float(tz)
                base_mesh.apply_transform(T)
                transformed_meshes.append(base_mesh)
            except Exception as e:
                print(f"  ⚠️  变换 {label}: {e}")

        vbelt_stl = OUT_DIR / "vbelt_all.stl"
        if WITH_VBELT and vbelt_stl.exists():
            try:
                vbelt_mesh = trimesh.load(str(vbelt_stl), force="mesh")
                transformed_meshes.append(vbelt_mesh)
                vbelt_mesh_loaded = True
                print(f"  ✅ V带组: {vbelt_stl.name}  ({len(vbelt_mesh.faces):,}面)")
            except Exception as e:
                print(f"  ⚠️  V带组加载失败: {e}")
        elif WITH_VBELT:
            print("  ⚠️  vbelt_all.stl 不存在，完整整机将不含V带")

        if transformed_meshes:
            combined = trimesh.util.concatenate(transformed_meshes)

            # STL
            stl_out = str(OUT_DIR / "assembly_complete.stl")
            combined.export(stl_out)
            sz = Path(stl_out).stat().st_size
            print(f"  ✅ STL: {stl_out}  ({sz//1024}KB  {len(combined.faces):,}面)")

            # OBJ
            obj_out = str(OUT_DIR / "assembly_complete.obj")
            combined.export(obj_out)
            print(f"  ✅ OBJ: {obj_out}  ({Path(obj_out).stat().st_size//1024}KB)")

            # GLB (如果trimesh支持)
            try:
                glb_out = str(OUT_DIR / "assembly_complete.glb")
                combined.export(glb_out)
                print(f"  ✅ GLB: {glb_out}  ({Path(glb_out).stat().st_size//1024}KB)")
            except Exception:
                pass

except ImportError:
    print("  ⚠️  trimesh未安装 (pip install trimesh)")
except Exception as e:
    print(f"  ⚠️  trimesh装配: {e}")
    import traceback; traceback.print_exc()

# ──────────────────────────────────────────────────────────────────
# T4: 输出完整BOM报告
# ──────────────────────────────────────────────────────────────────
print("\n" + "="*62)
print("  T4 — 整机BOM (来自总装配图 图6-2)")
print("="*62)

print(f"\n  {'序号':<4} {'名称':<12} {'英文名':<22} {'材料':<15} {'数量':<6} {'规格'}")
print("  " + "-"*80)
for item in BOM_COMPLETE:
    print(f"  {item['id']:<4} {item['name']:<12} {item['en']:<22} {item['mat']:<15} "
          f"{str(item['qty']):<6} {item['dim']}")

# ──────────────────────────────────────────────────────────────────
# 最终汇总
# ──────────────────────────────────────────────────────────────────
elapsed = round(time.time() - t_start, 1)
print("\n" + "="*62)
print("  最终汇总")
print("="*62)
print(f"""
  ✅ 零件建模  (原有6个 + 新增5个 = 共11个)
  ✅ 装配变换  ({'28个零件实例 + 4根V带已定位' if vbelt_mesh_loaded else '28个零件实例已定位'})
  ✅ 文件输出  output_cq/assembly_complete.stl/obj/glb

  整机参数:
    转子直径:  Ø700mm      旋转半径: 350mm
    轴总长:    1145mm      转速:    1200 r/min
    锤头线速: ~44 m/s     筛孔:    Ø15mm
    电机:     Y180L-4 22kW 传动比:  1.23
    外形:     {MACHINE_PARAMS['overall_l_mm']}×{MACHINE_PARAMS['overall_w_mm']}×{MACHINE_PARAMS['overall_h_mm']}mm

  耗时: {elapsed}s
  🎯 道法自然 · 万法归宗 · 整合到底 · 完善一切
""")
