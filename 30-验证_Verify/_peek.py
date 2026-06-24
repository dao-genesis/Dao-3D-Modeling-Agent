import json
from pathlib import Path

d = json.loads(Path(r"e:\道\道生一\一生二\3D建模Agent\30-验证_Verify\_sw_e2e_omega.json").read_text(encoding="utf-8"))
KEY = ("3.bbox", "3.feature_tree", "3.feature.chamfer", "4.list_components",
       "3.mass_properties", "4.add_component_base", "4.add_component_shaft",
       "4.new_assembly", "1.new_part_A", "3.feature.extrude",
       "3.feature.extrude_flange", "3.feature.fillet")
for s in d["steps"]:
    if s["step"] in KEY:
        k = s["step"]
        print(f"\n=== {k} ===  ok={s.get('ok')}")
        for kk, vv in s.items():
            if kk in ("step", "t0", "t1"):
                continue
            if isinstance(vv, (list, dict)):
                sv = json.dumps(vv, ensure_ascii=False)[:2000]
            else:
                sv = str(vv)[:2000]
            print(f"  {kk}: {sv}")
print(f"\n总评: {d['summary']}")
