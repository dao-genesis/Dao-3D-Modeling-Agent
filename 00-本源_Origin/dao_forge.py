#!/usr/bin/env python3
"""
道 · 锻造 — FreeCAD 动态持久化系统 v3.0

反者道之动。从逆向解构 FreeCAD 本源出发，由底层反推一切。
道生一，一生二，二生三，三生万物。

一个系统管理一切: 发现 → 执行 → 构建 → 持久化 → 感知 → 测试

用法:
  forge = DaoForge()
  forge.run([{"op":"make_box","id":"b","L":20,"W":10,"H":5}])
  forge.build("enclosure", {"L":60,"W":40,"H":30,"wall":2})
  forge.test()

CLI:
  python dao_forge.py info|run|build|gui|test|list-ops|list-models|history
"""
import json, os, shutil, subprocess, sys, tempfile, time, traceback, uuid, math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

__version__ = "3.0.0"
__all__ = ["DaoForge"]

SCRIPT_DIR = Path(__file__).parent.resolve()

# ═══ 万法归一 · 路径引导 ════════════════════════════════════════════
_DAO_ROOT = next((p for p in Path(__file__).resolve().parents
                  if (p / '_paths.py').is_file()), SCRIPT_DIR.parent)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
import _paths as _dao_paths  # noqa: F401  (registers 五层 sys.path)
ROOT_DIR = _DAO_ROOT
# ═══════════════════════════════════════════════════════════════════

BACKEND_SCRIPT = _dao_paths.REVERSE / "freecad_backend.py"       # 10-反笙_FreeCAD
MACRO_SCRIPT = _dao_paths.REVERSE / "freecad_gui_macro.py"       # 10-反笙_FreeCAD
OUTPUT_DIR = _dao_paths.PROJECTS / "fc_output"                    # 60-实战_Projects
HISTORY_FILE = OUTPUT_DIR / ".dao_history.json"
_NO_WINDOW = 0x08000000

_CMD_SEARCH = [
    r"D:\安装的软件\FreeCAD 1.0\bin\freecadcmd.exe",
    r"D:\安装的软件\FreeCAD 0.21\bin\FreeCADCmd.exe",
    r"C:\Program Files\FreeCAD 1.0\bin\freecadcmd.exe",
    r"C:\Program Files\FreeCAD\bin\FreeCADCmd.exe",
]
_GUI_SEARCH = [
    r"D:\安装的软件\FreeCAD 1.0\bin\freecad.exe",
    r"D:\安装的软件\FreeCAD 0.21\bin\FreeCAD.exe",
    r"C:\Program Files\FreeCAD 1.0\bin\freecad.exe",
    r"C:\Program Files\FreeCAD\bin\FreeCAD.exe",
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# OPS 注册表 — 从逆向解构 freecad_backend.py 得出
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OPS_REGISTRY = {
    "make_box":{"cat":"primitive","p":"L W H pos"},
    "make_cylinder":{"cat":"primitive","p":"R H pos dir angle"},
    "make_sphere":{"cat":"primitive","p":"R pos"},
    "make_cone":{"cat":"primitive","p":"R1 R2 H pos dir angle"},
    "make_torus":{"cat":"primitive","p":"R1 R2"},
    "make_wedge":{"cat":"primitive","p":"xmin..x2max (10 params)"},
    "make_tube":{"cat":"primitive","p":"R_outer R_inner H pos"},
    "make_prism":{"cat":"primitive","p":"n R H pos"},
    "make_ellipsoid":{"cat":"primitive","p":"rx ry rz pos"},
    "make_frustum":{"cat":"primitive","p":"R1 R2 H angle"},
    "make_pyramid":{"cat":"primitive","p":"n base_r H"},
    "make_stadium":{"cat":"primitive","p":"L R H"},
    "make_hollow_cylinder":{"cat":"primitive","p":"R_out R_in H"},
    "make_reg_polygon":{"cat":"primitive","p":"n R H"},
    "make_slot":{"cat":"primitive","p":"L W H pos"},
    "make_rounded_box":{"cat":"primitive","p":"L W H R pos"},
    "make_chamfer_box":{"cat":"primitive","p":"L W H chamfer"},
    "make_ellipse_extrude":{"cat":"primitive","p":"a b H"},
    "make_hex_bolt":{"cat":"engineering","p":"diameter length head_h head_w"},
    "make_hex_nut":{"cat":"engineering","p":"diameter thickness head_w"},
    "make_bracket":{"cat":"engineering","p":"W H D fillet"},
    "make_enclosure":{"cat":"engineering","p":"L W H wall open_top"},
    "make_gear_spur":{"cat":"engineering","p":"teeth module width hub_r"},
    "make_gear_rack":{"cat":"engineering","p":"module length width"},
    "make_thread":{"cat":"engineering","p":"diameter pitch length"},
    "make_spring":{"cat":"engineering","p":"R wire_r pitch turns"},
    "make_bearing_seat":{"cat":"engineering","p":"od bore width"},
    "make_i_beam":{"cat":"engineering","p":"W H tf tw L"},
    "make_channel":{"cat":"engineering","p":"W H tf tw L"},
    "make_l_profile":{"cat":"engineering","p":"W H t L"},
    "make_text_3d":{"cat":"engineering","p":"text size depth"},
    "make_polygon_wire":{"cat":"wire","p":"points closed"},
    "make_circle_wire":{"cat":"wire","p":"R center"},
    "make_bspline":{"cat":"wire","p":"points periodic"},
    "make_spiral":{"cat":"wire","p":"turns growth steps"},
    "make_helix":{"cat":"wire","p":"pitch height R angle"},
    "make_long_helix":{"cat":"wire","p":"pitch height R left_hand"},
    "make_polygon_3d":{"cat":"wire","p":"points closed"},
    "make_bezier_curve":{"cat":"wire","p":"points degree"},
    "make_catenary":{"cat":"wire","p":"span_half sag n_pts"},
    "make_torus_knot":{"cat":"wire","p":"p q R r wire_r steps"},
    "make_face":{"cat":"surface","p":"wire"},
    "make_filled_face":{"cat":"surface","p":"wire edges"},
    "make_bspline_surface":{"cat":"surface","p":"grid_pts"},
    "make_ruled":{"cat":"surface","p":"wire1 wire2"},
    "extrude":{"cat":"op","p":"shape direction"},
    "revolve":{"cat":"op","p":"shape axis_pos axis_dir angle"},
    "loft":{"cat":"op","p":"profiles solid ruled"},
    "pipe":{"cat":"op","p":"profile spine"},
    "make_loft_multi":{"cat":"op","p":"profiles ruled closed"},
    "make_pipe_3d":{"cat":"op","p":"path_pts R"},
    "make_swept_solid":{"cat":"op","p":"path r"},
    "make_taper_extrude":{"cat":"op","p":"points H taper"},
    "make_revolved_profile":{"cat":"op","p":"points angle"},
    "extrude_taper":{"cat":"op","p":"shape direction taper_angle"},
    "partdesign_pad":{"cat":"op","p":"face length symmetric taper"},
    "partdesign_pocket":{"cat":"op","p":"base profile depth"},
    "partdesign_fillet":{"cat":"op","p":"base radius"},
    "fuse":{"cat":"boolean","p":"base tool"},
    "cut":{"cat":"boolean","p":"base tool"},
    "common":{"cat":"boolean","p":"base tool"},
    "section":{"cat":"boolean","p":"base tool"},
    "occ_boolean":{"cat":"boolean","p":"base tools bool_op"},
    "boolean_split":{"cat":"boolean","p":"shape plane offset"},
    "fillet":{"cat":"modifier","p":"shape radius edges"},
    "chamfer":{"cat":"modifier","p":"shape size edges"},
    "offset3d":{"cat":"modifier","p":"shape offset"},
    "shell":{"cat":"modifier","p":"shape thickness face_indices"},
    "offset_2d":{"cat":"modifier","p":"shape offset join"},
    "occ_fillet":{"cat":"modifier","p":"shape radius edges"},
    "occ_thick_solid":{"cat":"modifier","p":"shape thickness faces"},
    "make_shell_from_solid":{"cat":"modifier","p":"shape thickness face_idx"},
    "section_curve":{"cat":"modifier","p":"shape z normal"},
    "make_cross_section":{"cat":"modifier","p":"shape axis height"},
    "project_shape":{"cat":"modifier","p":"shape normal origin"},
    "translate":{"cat":"transform","p":"shape vector"},
    "rotate":{"cat":"transform","p":"shape axis angle center"},
    "scale":{"cat":"transform","p":"shape factor"},
    "mirror":{"cat":"transform","p":"shape plane"},
    "make_scale":{"cat":"transform","p":"shape sx sy sz"},
    "compound":{"cat":"transform","p":"shapes"},
    "array_linear":{"cat":"array","p":"shape direction count spacing"},
    "array_polar":{"cat":"array","p":"shape center axis count angle"},
    "array_grid":{"cat":"array","p":"shape nx ny dx dy"},
    "array_path":{"cat":"array","p":"shape path count align"},
    "make_array_3d":{"cat":"array","p":"shape nx ny nz dx dy dz"},
    "export_stl":{"cat":"export","p":"shape path tolerance"},
    "export_step":{"cat":"export","p":"shape path"},
    "export_brep":{"cat":"export","p":"shape path"},
    "export_obj":{"cat":"export","p":"shape path"},
    "export_dxf":{"cat":"export","p":"shape path"},
    "export_svg":{"cat":"export","p":"shape path"},
    "export_iges":{"cat":"export","p":"shape path"},
    "export_fcstd":{"cat":"export","p":"shapes path"},
    "write_fcstd":{"cat":"export","p":"shapes_map path"},
    "import_step":{"cat":"import","p":"path"},
    "import_brep":{"cat":"import","p":"path"},
    "import_stl":{"cat":"import","p":"path"},
    "import_iges":{"cat":"import","p":"path"},
    "read_fcstd":{"cat":"import","p":"path"},
    "shape_info":{"cat":"analysis","p":"shape"},
    "check_shape":{"cat":"analysis","p":"shape"},
    "brep_string":{"cat":"analysis","p":"shape"},
    "mass_properties":{"cat":"analysis","p":"shape density"},
    "draft_angle":{"cat":"analysis","p":"shape direction min_angle"},
    "shape_analysis_3dprint":{"cat":"analysis","p":"shape min_wall_mm"},
    "measure_distance":{"cat":"analysis","p":"shape1 shape2"},
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 模型构建器辅助
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _exp_ops(sid, paths):
    ops = []
    for fmt, p in paths.items():
        if fmt in ("stl","step","brep","obj","iges","dxf","svg"):
            ops.append({"op":f"export_{fmt}","shape":sid,"path":p})
    return ops

def _mkpaths(label, fmts, odir):
    odir.mkdir(parents=True, exist_ok=True)
    return {f: str(odir/f"{label}.{f}") for f in fmts}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 模型构建函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _b_box(p,pt): return [{"op":"make_box","id":"result","L":float(p.get("L",20)),"W":float(p.get("W",15)),"H":float(p.get("H",10))}]+_exp_ops("result",pt)
def _b_rounded_box(p,pt): return [{"op":"make_rounded_box","id":"result","L":float(p.get("L",30)),"W":float(p.get("W",20)),"H":float(p.get("H",10)),"R":float(p.get("R",2))}]+_exp_ops("result",pt)
def _b_cylinder(p,pt): return [{"op":"make_cylinder","id":"result","R":float(p.get("R",10)),"H":float(p.get("H",20))}]+_exp_ops("result",pt)
def _b_sphere(p,pt): return [{"op":"make_sphere","id":"result","R":float(p.get("R",15))}]+_exp_ops("result",pt)
def _b_cone(p,pt): return [{"op":"make_cone","id":"result","R1":float(p.get("R1",15)),"R2":float(p.get("R2",5)),"H":float(p.get("H",20))}]+_exp_ops("result",pt)
def _b_torus(p,pt): return [{"op":"make_torus","id":"result","R1":float(p.get("R1",15)),"R2":float(p.get("R2",5))}]+_exp_ops("result",pt)
def _b_tube(p,pt): return [{"op":"make_tube","id":"result","R_outer":float(p.get("R_outer",10)),"R_inner":float(p.get("R_inner",8)),"H":float(p.get("H",20))}]+_exp_ops("result",pt)
def _b_hex_bolt(p,pt):
    d=float(p.get("diameter",8))
    return [{"op":"make_hex_bolt","id":"result","diameter":d,"length":float(p.get("length",30)),"head_h":float(p.get("head_h",d*0.7)),"head_w":float(p.get("head_w",d*1.8))}]+_exp_ops("result",pt)
def _b_hex_nut(p,pt):
    d=float(p.get("diameter",8))
    return [{"op":"make_hex_nut","id":"result","diameter":d,"thickness":float(p.get("thickness",d*0.8))}]+_exp_ops("result",pt)
def _b_bracket(p,pt): return [{"op":"make_bracket","id":"result","W":float(p.get("W",30)),"H":float(p.get("H",30)),"D":float(p.get("D",5)),"fillet":float(p.get("fillet",2))}]+_exp_ops("result",pt)
def _b_enclosure(p,pt): return [{"op":"make_enclosure","id":"result","L":float(p.get("L",50)),"W":float(p.get("W",40)),"H":float(p.get("H",30)),"wall":float(p.get("wall",2)),"open_top":p.get("open_top",True)}]+_exp_ops("result",pt)
def _b_gear_spur(p,pt): return [{"op":"make_gear_spur","id":"result","teeth":int(p.get("teeth",20)),"module":float(p.get("module",1.0)),"width":float(p.get("width",10)),"hub_r":float(p.get("hub_r",0))}]+_exp_ops("result",pt)
def _b_gear_rack(p,pt): return [{"op":"make_gear_rack","id":"result","module":float(p.get("module",1.0)),"length":float(p.get("length",60)),"width":float(p.get("width",10))}]+_exp_ops("result",pt)
def _b_bearing(p,pt): return [{"op":"make_bearing_seat","id":"result","od":float(p.get("od",40)),"bore":float(p.get("bore",17)),"width":float(p.get("width",12))}]+_exp_ops("result",pt)
def _b_spring(p,pt): return [{"op":"make_spring","id":"result","R":float(p.get("R",10)),"wire_r":float(p.get("wire_r",1.5)),"pitch":float(p.get("pitch",8)),"turns":float(p.get("turns",5))}]+_exp_ops("result",pt)
def _b_i_beam(p,pt): return [{"op":"make_i_beam","id":"result","W":float(p.get("W",20)),"H":float(p.get("H",30)),"tf":float(p.get("tf",3)),"tw":float(p.get("tw",2)),"L":float(p.get("L",50))}]+_exp_ops("result",pt)
def _b_channel(p,pt): return [{"op":"make_channel","id":"result","W":float(p.get("W",20)),"H":float(p.get("H",20)),"tf":float(p.get("tf",2.5)),"tw":float(p.get("tw",2)),"L":float(p.get("L",50))}]+_exp_ops("result",pt)
def _b_l_profile(p,pt): return [{"op":"make_l_profile","id":"result","W":float(p.get("W",20)),"H":float(p.get("H",20)),"t":float(p.get("t",2.5)),"L":float(p.get("L",50))}]+_exp_ops("result",pt)
def _b_thread(p,pt): return [{"op":"make_thread","id":"result","diameter":float(p.get("diameter",8)),"pitch":float(p.get("pitch",1.25)),"length":float(p.get("length",20))}]+_exp_ops("result",pt)
def _b_slot(p,pt): return [{"op":"make_slot","id":"result","L":float(p.get("L",20)),"W":float(p.get("W",8)),"H":float(p.get("H",5))}]+_exp_ops("result",pt)
def _b_chamfer_box(p,pt): return [{"op":"make_chamfer_box","id":"result","L":float(p.get("L",20)),"W":float(p.get("W",15)),"H":float(p.get("H",10)),"chamfer":float(p.get("chamfer",1.5))}]+_exp_ops("result",pt)
def _b_ellipsoid(p,pt): return [{"op":"make_ellipsoid","id":"result","rx":float(p.get("rx",15)),"ry":float(p.get("ry",10)),"rz":float(p.get("rz",8))}]+_exp_ops("result",pt)
def _b_stadium(p,pt): return [{"op":"make_stadium","id":"result","L":float(p.get("L",30)),"R":float(p.get("R",8)),"H":float(p.get("H",10))}]+_exp_ops("result",pt)
def _b_frustum(p,pt): return [{"op":"make_frustum","id":"result","R1":float(p.get("R1",15)),"R2":float(p.get("R2",8)),"H":float(p.get("H",20))}]+_exp_ops("result",pt)
def _b_pyramid(p,pt): return [{"op":"make_pyramid","id":"result","n":int(p.get("n",4)),"base_r":float(p.get("base_r",10)),"H":float(p.get("H",15))}]+_exp_ops("result",pt)
def _b_shaft(p,pt): return [{"op":"make_cylinder","id":"result","R":float(p.get("R",5)),"H":float(p.get("L",50))}]+_exp_ops("result",pt)
def _b_bushing(p,pt): return [{"op":"make_tube","id":"result","R_outer":float(p.get("R_out",8)),"R_inner":float(p.get("R_in",5)),"H":float(p.get("H",15))}]+_exp_ops("result",pt)
def _b_standoff(p,pt): return [{"op":"make_tube","id":"result","R_outer":float(p.get("od",6))/2,"R_inner":float(p.get("id",3))/2,"H":float(p.get("H",10))}]+_exp_ops("result",pt)
def _b_pipe(p,pt): return [{"op":"make_pipe_3d","id":"result","path_pts":p.get("path",[[0,0,0],[0,0,30],[10,0,50]]),"R":float(p.get("R",3))}]+_exp_ops("result",pt)

def _b_washer(p,pt):
    od,id_,t=float(p.get("od",16)),float(p.get("id",8.4)),float(p.get("thickness",1.6))
    return [{"op":"make_cylinder","id":"o","R":od/2,"H":t},{"op":"make_cylinder","id":"h","R":id_/2,"H":t},{"op":"cut","id":"result","base":"o","tool":"h"}]+_exp_ops("result",pt)

def _b_flange(p,pt):
    od,id_,t=float(p.get("od",60)),float(p.get("id",25)),float(p.get("thickness",8))
    br,nb,pcd=float(p.get("bolt_r",4)),int(p.get("n_bolts",6)),float(p.get("pcd",45))
    ops=[{"op":"make_cylinder","id":"disk","R":od/2,"H":t},{"op":"make_cylinder","id":"bore","R":id_/2,"H":t},{"op":"cut","id":"ring","base":"disk","tool":"bore"}]
    for i in range(nb):
        a=2*math.pi*i/nb; x,y=pcd/2*math.cos(a),pcd/2*math.sin(a)
        ops+=[{"op":"make_cylinder","id":f"bh{i}","R":br,"H":t,"pos":[x,y,0]},
              {"op":"cut","id":f"r{i}" if i<nb-1 else "result","base":f"r{i-1}" if i>0 else "ring","tool":f"bh{i}"}]
    return ops+_exp_ops("result",pt)

def _b_t_slot(p,pt):
    W,H,nw,nh,L=float(p.get("W",20)),float(p.get("H",10)),float(p.get("neck_w",8)),float(p.get("neck_h",5)),float(p.get("L",50))
    hh=H-nh
    return [{"op":"make_box","id":"hd","L":W,"W":L,"H":hh},{"op":"make_box","id":"nk","L":nw,"W":L,"H":nh,"pos":[(W-nw)/2,0,hh]},{"op":"fuse","id":"result","base":"hd","tool":"nk"}]+_exp_ops("result",pt)

def _b_motor_mount(p,pt):
    bl,bw,bh=float(p.get("base_l",40)),float(p.get("base_w",30)),float(p.get("base_h",5))
    md,mh=float(p.get("motor_d",25)),float(p.get("mount_h",15))
    cx,cy=bl/2,bw/2
    return [{"op":"make_box","id":"base","L":bl,"W":bw,"H":bh},
            {"op":"make_cylinder","id":"ring","R":md/2+3,"H":mh,"pos":[cx,cy,bh]},
            {"op":"make_cylinder","id":"bore","R":md/2,"H":mh,"pos":[cx,cy,bh]},
            {"op":"fuse","id":"f1","base":"base","tool":"ring"},
            {"op":"cut","id":"result","base":"f1","tool":"bore"}]+_exp_ops("result",pt)

def _b_knob(p,pt):
    R,H,gn,gr,br_=float(p.get("R",12)),float(p.get("H",8)),int(p.get("grip_n",8)),float(p.get("grip_r",2)),float(p.get("bore_r",3))
    ops=[{"op":"make_cylinder","id":"body","R":R,"H":H}]
    for i in range(gn):
        a=2*math.pi*i/gn; x,y=(R+gr*0.3)*math.cos(a),(R+gr*0.3)*math.sin(a)
        ops+=[{"op":"make_cylinder","id":f"g{i}","R":gr,"H":H,"pos":[x,y,0]},
              {"op":"cut","id":f"k{i}" if i<gn-1 else "knob","base":f"k{i-1}" if i>0 else "body","tool":f"g{i}"}]
    ops+=[{"op":"make_cylinder","id":"bh","R":br_,"H":H},{"op":"cut","id":"result","base":"knob","tool":"bh"}]
    return ops+_exp_ops("result",pt)

def _b_hinge(p,pt):
    L,W,t,pr=float(p.get("L",30)),float(p.get("W",15)),float(p.get("t",2)),float(p.get("pin_r",3))
    return [{"op":"make_box","id":"lf","L":L,"W":W,"H":t},
            {"op":"make_cylinder","id":"br","R":pr+t,"H":L,"pos":[0,W,t/2],"dir":[1,0,0]},
            {"op":"fuse","id":"hf","base":"lf","tool":"br"},
            {"op":"make_cylinder","id":"ph","R":pr,"H":L,"pos":[0,W,t/2],"dir":[1,0,0]},
            {"op":"cut","id":"result","base":"hf","tool":"ph"}]+_exp_ops("result",pt)

MODEL_REGISTRY = {
    "box":{"fn":_b_box,"d":"长方体","p":"L W H"},
    "rounded_box":{"fn":_b_rounded_box,"d":"圆角长方体","p":"L W H R"},
    "cylinder":{"fn":_b_cylinder,"d":"圆柱体","p":"R H"},
    "sphere":{"fn":_b_sphere,"d":"球体","p":"R"},
    "cone":{"fn":_b_cone,"d":"圆锥体","p":"R1 R2 H"},
    "torus":{"fn":_b_torus,"d":"圆环体","p":"R1 R2"},
    "tube":{"fn":_b_tube,"d":"管状体","p":"R_outer R_inner H"},
    "hex_bolt":{"fn":_b_hex_bolt,"d":"六角螺栓","p":"diameter length"},
    "hex_nut":{"fn":_b_hex_nut,"d":"六角螺母","p":"diameter thickness"},
    "washer":{"fn":_b_washer,"d":"垫圈","p":"od id thickness"},
    "bracket":{"fn":_b_bracket,"d":"L型支架","p":"W H D fillet"},
    "enclosure":{"fn":_b_enclosure,"d":"电子外壳","p":"L W H wall"},
    "gear_spur":{"fn":_b_gear_spur,"d":"直齿轮","p":"teeth module width"},
    "gear_rack":{"fn":_b_gear_rack,"d":"齿条","p":"module length width"},
    "bearing_seat":{"fn":_b_bearing,"d":"轴承座","p":"od bore width"},
    "spring":{"fn":_b_spring,"d":"弹簧","p":"R wire_r pitch turns"},
    "i_beam":{"fn":_b_i_beam,"d":"工字钢","p":"W H tf tw L"},
    "channel":{"fn":_b_channel,"d":"槽钢","p":"W H tf tw L"},
    "l_profile":{"fn":_b_l_profile,"d":"角钢","p":"W H t L"},
    "pipe":{"fn":_b_pipe,"d":"3D管道","p":"path R"},
    "flange":{"fn":_b_flange,"d":"法兰盘","p":"od id thickness n_bolts"},
    "t_slot":{"fn":_b_t_slot,"d":"T型槽","p":"W H neck_w neck_h L"},
    "motor_mount":{"fn":_b_motor_mount,"d":"电机座","p":"base_l base_w motor_d"},
    "standoff":{"fn":_b_standoff,"d":"铜柱","p":"od id H"},
    "shaft":{"fn":_b_shaft,"d":"轴","p":"R L"},
    "bushing":{"fn":_b_bushing,"d":"轴套","p":"R_out R_in H"},
    "knob":{"fn":_b_knob,"d":"旋钮","p":"R H grip_n bore_r"},
    "hinge":{"fn":_b_hinge,"d":"铰链","p":"L W t pin_r"},
    "frustum":{"fn":_b_frustum,"d":"截锥体","p":"R1 R2 H"},
    "pyramid":{"fn":_b_pyramid,"d":"棱锥","p":"n base_r H"},
    "thread":{"fn":_b_thread,"d":"螺纹","p":"diameter pitch length"},
    "slot":{"fn":_b_slot,"d":"腰形槽","p":"L W H"},
    "chamfer_box":{"fn":_b_chamfer_box,"d":"倒角盒","p":"L W H chamfer"},
    "ellipsoid":{"fn":_b_ellipsoid,"d":"椭球体","p":"rx ry rz"},
    "stadium":{"fn":_b_stadium,"d":"跑道形","p":"L R H"},
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 主系统类
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class DaoForge:
    """FreeCAD 动态持久化系统 — 道生一，一生二，二生三，三生万物。"""

    def __init__(self, output_dir=None):
        self.output_dir = Path(output_dir) if output_dir else OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cmd = self._find(_CMD_SEARCH, ["freecadcmd","FreeCADCmd"])
        self.gui_exe = self._find(_GUI_SEARCH, ["freecad","FreeCAD"])
        self._history = []
        self._load_history()

    @staticmethod
    def _find(paths, names):
        for p in paths:
            if Path(p).exists(): return p
        for n in names:
            f = shutil.which(n)
            if f: return f
        return None

    def available(self): return self.cmd and Path(self.cmd).exists()

    def info(self):
        return {"version":__version__,"cmd":self.cmd,"gui":self.gui_exe,
                "cmd_ok":self.available(),"gui_ok":bool(self.gui_exe and Path(self.gui_exe).exists()),
                "backend":str(BACKEND_SCRIPT),"backend_ok":BACKEND_SCRIPT.exists(),
                "output":str(self.output_dir),"history":len(self._history),
                "ops":len(OPS_REGISTRY),"models":len(MODEL_REGISTRY)}

    # ── 执行 ──────────────────────────────────────────────────────
    def run(self, ops, label="ops", timeout=300):
        if not self.available():
            return {"ok":False,"errors":["FreeCAD cmd not found"],"mode":"headless"}
        t0=time.time()
        td=Path(tempfile.gettempdir())/f"dao_{uuid.uuid4().hex[:8]}"
        td.mkdir(parents=True,exist_ok=True)
        try:
            shutil.copy2(str(BACKEND_SCRIPT),str(td/"freecad_backend.py"))
            cf=td/"cmd.json"; cf.write_text(json.dumps({"ops":ops},indent=2,ensure_ascii=True),encoding="utf-8")
            rf=td/"result.json"
            lf=td/"launcher.py"
            lf.write_text(f'import sys,json\nfrom pathlib import Path\nsys.path.insert(0,r"{td}")\n'
                f'from freecad_backend import run_ops\n'
                f'ops=json.loads(Path(r"{cf}").read_text(encoding="utf-8")).get("ops",[])\n'
                f'r=run_ops(ops)\nPath(r"{rf}").write_text(json.dumps(r,indent=2,ensure_ascii=False,default=str),encoding="utf-8")\n',
                encoding="utf-8")
            proc=subprocess.run([self.cmd,str(lf)],capture_output=True,text=True,timeout=timeout,
                creationflags=_NO_WINDOW if sys.platform=="win32" else 0)
            el=round(time.time()-t0,2)
            if rf.exists():
                result=json.loads(rf.read_text(encoding="utf-8"))
            else:
                result={"ok":False,"errors":[f"No result. exit={proc.returncode}",proc.stderr[-500:] if proc.stderr else ""]}
            result["mode"]="headless"; result["elapsed_s"]=el; result["label"]=label
            self._save(result); return result
        except subprocess.TimeoutExpired:
            return {"ok":False,"errors":[f"Timeout({timeout}s)"],"mode":"headless"}
        except Exception as e:
            return {"ok":False,"errors":[str(e)],"mode":"headless"}
        finally:
            shutil.rmtree(str(td),ignore_errors=True)

    def gui(self, ops, label="model", auto_close=False, wait=True, timeout=600, save_fcstd=True):
        if not self.gui_exe or not Path(self.gui_exe).exists():
            return {"ok":False,"errors":["FreeCAD GUI not found"],"mode":"gui"}
        if not MACRO_SCRIPT.exists():
            return {"ok":False,"errors":["GUI macro not found"],"mode":"gui"}
        t0=time.time()
        td=Path(tempfile.gettempdir())/f"fcg_{uuid.uuid4().hex[:8]}"
        td.mkdir(parents=True,exist_ok=True)
        try:
            shutil.copy2(str(MACRO_SCRIPT),str(td/"freecad_gui_macro.py"))
            if BACKEND_SCRIPT.exists(): shutil.copy2(str(BACKEND_SCRIPT),str(td/"freecad_backend.py"))
            sp=str(self.output_dir/f"{label}.FCStd") if save_fcstd else ""
            cf=td/"gui_cmd.json"
            cf.write_text(json.dumps({"ops":ops,"doc_name":label,"save_path":sp,"auto_close":auto_close},
                indent=2,ensure_ascii=True),encoding="utf-8")
            rf=td/"gui_result.json"
            env=os.environ.copy()
            env["FC_GUI_CMD_FILE"]=str(cf); env["FC_GUI_RESULT_FILE"]=str(rf)
            if sp: env["FC_GUI_SAVE_PATH"]=sp
            proc=subprocess.Popen([self.gui_exe,str(td/"freecad_gui_macro.py")],env=env,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            if wait:
                try: stdout,stderr=proc.communicate(timeout=timeout)
                except subprocess.TimeoutExpired: proc.kill(); return {"ok":False,"errors":["GUI timeout"],"mode":"gui"}
                el=round(time.time()-t0,2)
                result=json.loads(rf.read_text(encoding="utf-8")) if rf.exists() else {"ok":proc.returncode==0}
                result["mode"]="gui"; result["elapsed_s"]=el; result["label"]=label
                if sp and Path(sp).exists(): result["fcstd_path"]=sp
                self._save(result); return result
            else:
                return {"ok":True,"pid":proc.pid,"mode":"gui","blocking":False}
        except Exception as e:
            return {"ok":False,"errors":[str(e)],"mode":"gui"}

    # ── 构建 ──────────────────────────────────────────────────────
    def build(self, model_type, params=None, gui=False, formats=None, label=None):
        mt=model_type.lower().strip()
        reg=MODEL_REGISTRY.get(mt)
        if not reg:
            return {"ok":False,"errors":[f"Unknown model: '{mt}'","Available: "+", ".join(sorted(MODEL_REGISTRY))]}
        p=params or {}; fmts=formats or ["stl","step"]; lbl=label or mt
        paths=_mkpaths(lbl,fmts,self.output_dir)
        ops=reg["fn"](p,paths)
        result=self.gui(ops,label=lbl) if gui else self.run(ops,label=lbl)
        result["model_type"]=mt; result["params"]=p; result["output_files"]=paths
        return result

    # ── 持久化 ────────────────────────────────────────────────────
    def _load_history(self):
        try:
            if HISTORY_FILE.exists(): self._history=json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except: self._history=[]

    def _save(self, result):
        self._history.append({"id":uuid.uuid4().hex[:12],"ts":time.strftime("%Y-%m-%dT%H:%M:%S"),
            "ok":result.get("ok"),"mode":result.get("mode","?"),"label":result.get("label",""),
            "elapsed_s":result.get("elapsed_s",0),"shapes":len(result.get("shapes",{})),
            "exports":len(result.get("exports",[])),"errors":len(result.get("errors",[]))})
        self._history=self._history[-200:]
        try:
            HISTORY_FILE.parent.mkdir(parents=True,exist_ok=True)
            HISTORY_FILE.write_text(json.dumps(self._history,indent=2,ensure_ascii=False),encoding="utf-8")
        except: pass

    def history(self, n=20): return self._history[-n:]

    # ── 感知 ──────────────────────────────────────────────────────
    def sense(self):
        files=list(self.output_dir.glob("*"))
        return {"env":self.info(),"files":len(files),
            "stl":[f.name for f in files if f.suffix==".stl"],
            "step":[f.name for f in files if f.suffix==".step"],
            "last":self._history[-1] if self._history else None}

    # ── 列表 ──────────────────────────────────────────────────────
    def list_ops(self, cat=None):
        g={}
        for n,i in OPS_REGISTRY.items():
            c=i["cat"]
            if cat and c!=cat: continue
            g.setdefault(c,[]).append({"op":n,"p":i["p"]})
        return g

    def list_models(self):
        return [{"name":n,"desc":i["d"],"params":i["p"]} for n,i in sorted(MODEL_REGISTRY.items())]

    # ── 测试 ──────────────────────────────────────────────────────
    def test(self, scope="all", verbose=True):
        if not self.available(): return {"ok":False,"error":"FreeCAD unavailable"}
        suites={"env":self._t_env,"primitives":self._t_prims,"booleans":self._t_bool,
                "modifiers":self._t_mod,"transforms":self._t_xform,"exports":self._t_exp,
                "analysis":self._t_ana,"models":self._t_models}
        if scope!="all": suites={scope:suites[scope]}
        results={}; t0=time.time()
        for name,fn in suites.items():
            if verbose: print(f"  [{name}]...",end="",flush=True)
            try:
                r=fn(); results[name]=r
                p=sum(1 for v in r.values() if isinstance(v,dict) and v.get("ok"))
                if verbose: print(f" {p}/{len(r)} {'PASS' if p==len(r) else 'FAIL'}")
            except Exception as e:
                results[name]={"_error":str(e)}
                if verbose: print(f" ERROR: {e}")
        tt=sum(len(v) for v in results.values() if isinstance(v,dict))
        tp=sum(sum(1 for vv in v.values() if isinstance(vv,dict) and vv.get("ok")) for v in results.values() if isinstance(v,dict))
        el=round(time.time()-t0,2)
        if verbose: print(f"\n  === {tp}/{tt} passed in {el}s ===")
        return {"summary":{"total":tt,"passed":tp,"failed":tt-tp,"elapsed_s":el,"all_ok":tp==tt},"suites":results}

    def _tr(self, ops): return self.run(ops,label="_test",timeout=60)

    def _t_env(self):
        r=self._tr([{"op":"make_box","id":"b","L":10,"W":10,"H":10},{"op":"shape_info","shape":"b"}])
        return {"env":{"ok":r.get("ok",False)}}

    def _t_prims(self):
        ops=[{"op":"make_box","id":"box","L":20,"W":15,"H":10},
             {"op":"make_cylinder","id":"cyl","R":5,"H":20},
             {"op":"make_sphere","id":"sph","R":10},
             {"op":"make_cone","id":"cone","R1":10,"R2":5,"H":20},
             {"op":"make_torus","id":"tor","R1":10,"R2":3},
             {"op":"make_tube","id":"tube","R_outer":10,"R_inner":8,"H":20},
             {"op":"make_prism","id":"pri","n":6,"R":10,"H":20},
             {"op":"make_ellipsoid","id":"ell","rx":15,"ry":10,"rz":8},
             {"op":"make_frustum","id":"fru","R1":15,"R2":8,"H":20},
             {"op":"make_rounded_box","id":"rb","L":30,"W":20,"H":10,"R":2}]
        r=self._tr(ops); s=r.get("shapes",{})
        return {o["id"]:{"ok":o["id"] in s and s[o["id"]].get("type","")!="ERROR"} for o in ops}

    def _t_bool(self):
        ops=[{"op":"make_box","id":"a","L":20,"W":20,"H":20},
             {"op":"make_cylinder","id":"b","R":5,"H":30,"pos":[10,10,0]},
             {"op":"fuse","id":"fu","base":"a","tool":"b"},
             {"op":"cut","id":"cu","base":"a","tool":"b"},
             {"op":"common","id":"co","base":"a","tool":"b"}]
        r=self._tr(ops); s=r.get("shapes",{})
        return {"fuse":{"ok":"fu" in s and s.get("fu",{}).get("type","")!="ERROR"},"cut":{"ok":"cu" in s and s.get("cu",{}).get("type","")!="ERROR"},"common":{"ok":"co" in s and s.get("co",{}).get("type","")!="ERROR"}}

    def _t_mod(self):
        ops=[{"op":"make_box","id":"b","L":20,"W":15,"H":10},
             {"op":"fillet","id":"f","shape":"b","radius":2},
             {"op":"chamfer","id":"c","shape":"b","size":1.5},
             {"op":"shell","id":"s","shape":"b","thickness":-2,"face_indices":[0]}]
        r=self._tr(ops); s=r.get("shapes",{})
        return {"fillet":{"ok":"f" in s and s.get("f",{}).get("type","")!="ERROR"},"chamfer":{"ok":"c" in s and s.get("c",{}).get("type","")!="ERROR"},"shell":{"ok":"s" in s and s.get("s",{}).get("type","")!="ERROR"}}

    def _t_xform(self):
        ops=[{"op":"make_box","id":"b","L":10,"W":10,"H":10},
             {"op":"translate","id":"t","shape":"b","vector":[20,0,0]},
             {"op":"rotate","id":"r","shape":"b","axis":[0,0,1],"angle":45},
             {"op":"mirror","id":"m","shape":"b","plane":"YZ"},
             {"op":"make_scale","id":"sc","shape":"b","sx":2,"sy":1,"sz":1}]
        r=self._tr(ops); s=r.get("shapes",{})
        return {"translate":{"ok":"t" in s and s.get("t",{}).get("type","")!="ERROR"},"rotate":{"ok":"r" in s and s.get("r",{}).get("type","")!="ERROR"},"mirror":{"ok":"m" in s and s.get("m",{}).get("type","")!="ERROR"},"scale":{"ok":"sc" in s and s.get("sc",{}).get("type","")!="ERROR"}}

    def _t_exp(self):
        td=Path(tempfile.gettempdir())/f"dao_tx_{uuid.uuid4().hex[:6]}"; td.mkdir(exist_ok=True)
        ops=[{"op":"make_box","id":"b","L":15,"W":10,"H":8},
             {"op":"export_stl","shape":"b","path":str(td/"t.stl")},
             {"op":"export_step","shape":"b","path":str(td/"t.step")},
             {"op":"export_brep","shape":"b","path":str(td/"t.brep")}]
        r=self._tr(ops); ex=r.get("exports",[])
        shutil.rmtree(str(td),ignore_errors=True)
        res={}
        for e in ex: res[e.get("op","?")]={"ok":e.get("ok",False)}
        return res if res else {"export_stl":{"ok":False}}

    def _t_ana(self):
        ops=[{"op":"make_box","id":"b","L":20,"W":15,"H":10},
             {"op":"shape_info","id":"si","shape":"b"},
             {"op":"mass_properties","id":"mp","shape":"b","density":7.85},
             {"op":"shape_analysis_3dprint","id":"pa","shape":"b"}]
        r=self._tr(ops); a=r.get("analyses",[])
        return {"shape_info":{"ok":"si" in r.get("shapes",{}) or "b" in r.get("shapes",{})},
                "mass":{"ok":any(x.get("op")=="mass_properties" for x in a)},
                "3dprint":{"ok":any(x.get("op")=="shape_analysis_3dprint" for x in a)}}

    def _t_models(self):
        res={}
        for m in ["box","cylinder","hex_bolt","enclosure","washer","flange","gear_spur","i_beam"]:
            try:
                r=self.build(m,formats=["stl"])
                res[m]={"ok":r.get("ok",False),"shapes":len(r.get("shapes",{}))}
            except Exception as e: res[m]={"ok":False,"err":str(e)[:60]}
        return res

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _cli():
    import argparse
    ap=argparse.ArgumentParser(description="道·锻造 — FreeCAD 动态持久化系统 v"+__version__)
    sp=ap.add_subparsers(dest="cmd")
    sp.add_parser("info")
    pr=sp.add_parser("run"); pr.add_argument("ops_file")
    pg=sp.add_parser("gui"); pg.add_argument("ops_file"); pg.add_argument("--no-wait",action="store_true")
    pb=sp.add_parser("build"); pb.add_argument("model"); pb.add_argument("--params",default="{}")
    pb.add_argument("--gui",action="store_true"); pb.add_argument("--formats",default="stl,step")
    pt=sp.add_parser("test"); pt.add_argument("--scope",default="all")
    sp.add_parser("list-ops"); sp.add_parser("list-models"); sp.add_parser("history")
    sp.add_parser("sense")
    args=ap.parse_args()
    forge=DaoForge()
    if args.cmd=="info":
        print(json.dumps(forge.info(),indent=2,ensure_ascii=False))
    elif args.cmd=="run":
        ops=json.loads(Path(args.ops_file).read_text(encoding="utf-8"))
        if isinstance(ops,dict): ops=ops.get("ops",ops)
        print(json.dumps(forge.run(ops),indent=2,ensure_ascii=False,default=str))
    elif args.cmd=="gui":
        ops=json.loads(Path(args.ops_file).read_text(encoding="utf-8"))
        if isinstance(ops,dict): ops=ops.get("ops",ops)
        print(json.dumps(forge.gui(ops,wait=not args.no_wait),indent=2,ensure_ascii=False,default=str))
    elif args.cmd=="build":
        p=json.loads(args.params); fmts=args.formats.split(",")
        r=forge.build(args.model,params=p,gui=args.gui,formats=fmts)
        print(json.dumps(r,indent=2,ensure_ascii=False,default=str))
    elif args.cmd=="test":
        forge.test(scope=args.scope)
    elif args.cmd=="list-ops":
        for cat,ops in forge.list_ops().items():
            print(f"\n[{cat}]")
            for o in ops: print(f"  {o['op']:30s} {o['p']}")
    elif args.cmd=="list-models":
        for m in forge.list_models(): print(f"  {m['name']:20s} {m['desc']:10s}  params: {m['params']}")
    elif args.cmd=="history":
        for h in forge.history(): print(f"  {h['ts']} {h['label']:15s} {'OK' if h['ok'] else 'FAIL'} {h['elapsed_s']}s")
    elif args.cmd=="sense":
        print(json.dumps(forge.sense(),indent=2,ensure_ascii=False))
    else:
        ap.print_help()

if __name__=="__main__":
    _cli()
