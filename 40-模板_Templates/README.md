# ModelForge 黄金模板库 — Engine Golden Templates

> 每种引擎的最佳实践范例，融合世界万法之成果。
> Agent在步骤3(建模)时，根据引擎选择决策树匹配对应模板。

## 目录

| 模板 | 引擎 | 用途 | 来源 |
|------|------|------|------|
| `cq_bracket.py` | CadQuery | 参数化安装支架(圆角/沉头孔/STEP) | CadQuery官方+AI-CAD论文最佳实践 |
| `cq_enclosure.py` | CadQuery | 参数化电子外壳(壳体/卡扣/通风孔) | Text-to-CadQuery范式 |
| `b3d_phone_stand.py` | build123d | 参数化手机支架(可调角度) | build123d官方范例+社区 |
| `b3d_pipe_fitting.py` | build123d | 管件接头(Loft/Sweep) | build123d BREP能力展示 |
| `scad_gear.scad` | OpenSCAD | 参数化齿轮(BOSL2渐开线) | BOSL2库+OpenSCAD社区 |
| `fc_motor_mount.json` | FreeCAD | 电机安装座(Sketch→Pad→Pocket) | FreeCAD PartDesign最佳实践 |

## 使用方式

Agent直接读取模板，理解结构，然后根据用户需求修改参数生成新模型。
模板不是直接输出给用户的 — 它们是Agent的参考蓝图。

```bash
# CadQuery模板 → 直接执行
python forge_v3.py cq "$(cat templates/cq_bracket.py)" output/bracket.stl

# build123d模板 → 直接执行
python forge_v3.py b3d "$(cat templates/b3d_phone_stand.py)" output/stand.stl

# OpenSCAD模板 → 渲染
python forge_v3.py scad templates/scad_gear.scad output/gear.stl

# FreeCAD模板 → 操作序列
python forge_v3.py fc_ops templates/fc_motor_mount.json
```
