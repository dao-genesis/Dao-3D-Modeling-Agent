#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""spring_in_housing.py — 弹簧-缸套子装配 (高阶建模实战) · 万法归一 60 门

一条 live FreeCAD 内核, 锻造一套压缩弹簧装入缸套的子装配 (2 零件):
  · 缸套 Housing: pad 圆 + pocket 镗孔 → 沿 Z 的薄壁管 (OD56 / ID44, 长60)
  · 弹簧 Spring : 圆截面沿螺旋线扫掠 → 压缩螺旋弹簧 (中径30, 线径6, 5圈)

闭式/几何校验:
  1 缸套壁体积 V = pi(ro^2-ri^2) h 精确
  2 弹簧圈数 turns = height/pitch = 5 精确; 线材体积 = A * 圈数*sqrt((2piR)^2+p^2)
  3 同轴装入: 弹簧外径 36 < 缸套内径 44 → 干涉 0 (间隙装配)

运行:  python 60-实战_Projects/spring_in_housing.py
"""
import math
import os
import sys
from pathlib import Path

_DAO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "_paths.py").is_file())
sys.path.insert(0, str(_DAO_ROOT))
import _paths  # noqa: E402,F401

from cad_agent import new_session  # noqa: E402

OD, ID, HLEN = 28.0, 22.0, 60.0      # 缸套外/内半径, 长
R_COIL, WIRE, PITCH, SLEN = 15.0, 3.0, 10.0, 50.0  # 弹簧中径半径, 线半径, 螺距, 长


def main():
    s = new_session("spring_housing")
    print("FreeCAD", s.registry.kernel.freecad_version)

    # --- 缸套 (Z 轴薄壁管) ----------------------------------------------
    assert s.act("param.body", {"name": "Housing"}).ok
    assert s.act("param.pad", {"body": "Housing", "feature": "Tube",
                               "profile": {"circle": OD}, "length": HLEN}).ok
    pk = s.act("param.pocket", {"body": "Housing", "feature": "Bore",
                                "profile": {"circle": ID}, "through": True})
    assert pk.ok, pk.error
    closed_wall = math.pi * (OD ** 2 - ID ** 2) * HLEN
    err = abs(pk.data["volume"] / closed_wall - 1.0)
    print("housing wall V=%.1f  closed=%.1f  err=%.2f%%" % (pk.data["volume"], closed_wall, err * 100))
    assert err < 0.01, (pk.data["volume"], closed_wall)

    # --- 弹簧 (螺旋扫掠) ------------------------------------------------
    assert s.act("param.body", {"name": "Spring"}).ok
    sp = s.act("param.sweep", {"body": "Spring", "feature": "Coil", "profile": {"circle": WIRE},
               "path": {"helix": {"radius": R_COIL, "pitch": PITCH, "height": SLEN}}})
    assert sp.ok, sp.error
    assert abs(sp.data["turns"] - SLEN / PITCH) < 1e-6, sp.data["turns"]
    wlen = (SLEN / PITCH) * math.sqrt((2 * math.pi * R_COIL) ** 2 + PITCH ** 2)
    serr = abs(sp.data["volume"] / (math.pi * WIRE ** 2 * wlen) - 1.0)
    print("spring turns=%.1f  V=%.1f  closed=%.1f  err=%.2f%%"
          % (sp.data["turns"], sp.data["volume"], math.pi * WIRE ** 2 * wlen, serr * 100))
    assert serr < 0.04, sp.data["volume"]

    # --- 同轴装入 (间隙装配, 干涉 0) ------------------------------------
    assert s.act("asm.create", {"name": "SpringSet"}).ok
    assert s.act("asm.add", {"assembly": "SpringSet", "body": "Housing", "name": "housing",
                             "fixed": True}).ok
    assert s.act("asm.add", {"assembly": "SpringSet", "body": "Spring", "name": "spring"}).ok
    assert s.act("asm.place", {"name": "spring", "pos": [0, 0, 5]}).ok
    clashes = {tuple(sorted((c["a"], c["b"]))): c["overlap_volume"]
               for c in s.act("asm.interference", {"assembly": "SpringSet"}).data["clashes"]}
    seat = clashes.get(("housing", "spring"), 0.0)
    print("spring-in-bore overlap = %.2f mm^3 (OD %.0f < ID %.0f clearance)"
          % (seat, 2 * (R_COIL + WIRE), 2 * ID))
    assert seat < 1.0, ("spring should clear the bore", seat)

    bom = s.act("asm.bom", {"assembly": "SpringSet", "density": 0.00785})
    print("BOM: %d parts  mass=%.1f g" % (bom.data["component_count"], bom.data["total_mass"]))
    assert bom.data["component_count"] == 2, bom.data

    if "view.render" in s.tools():
        out = str(_paths.ROOT / "output" / "fem_demo" / "spring_in_housing.png")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        rr = s.act("view.render", {"assembly": "SpringSet", "view": "iso", "path": out})
        if rr.ok:
            print("render -> %s (%d bytes)" % (out, rr.data["bytes"]))

    print("SPRING IN HOUSING OK", s.summary())
    s.registry.kernel.shutdown()


if __name__ == "__main__":
    main()
