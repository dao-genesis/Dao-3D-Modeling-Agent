#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""道直连器 · 烟雾测 · 对活体 SW 验证核心 API."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from typing import Dict
from 道_直连_底层 import Dao, MemidTable, MATE, ALIGN, SEL, SURF, DOC, _safe


def main():
    print("═══ 道直连器 · 烟雾测 ═══")
    dao = Dao().connect()

    # 1. 统计
    print(f"\n[1] tlb 载入: {dao.mt.loaded}")
    st = dao.mt.stats()
    print(f"    接口 {st['interfaces']} · 方法 {st['methods_total']}"
          f" · 属性 {st['properties_total']} · 枚举 {st['enums']}")

    # 2. 基本 API 调用 · mate count
    print(f"\n[2] mate 相关 API:")
    mt = dao.mt
    for n in mt.list_methods("IAssemblyDoc"):
        if "mate" in n.lower():
            print(f"    method: {n}")
    for n in mt.list_properties("IAssemblyDoc"):
        if "mate" in n.lower():
            print(f"    prop:   {n}")

    # 3. 直接 memid 调用 (全局搜索 FirstFeature)
    print(f"\n[3] 全局搜 FirstFeature memid:")
    found = mt.find_anywhere("FirstFeature")
    print(f"    find_anywhere('FirstFeature') = {found}")

    # 4. DaoDispatch 路径 · 通过继承链调 FirstFeature
    print(f"\n[4] DaoDispatch 经全局搜: dao.asm.FirstFeature()")
    try:
        feat = dao.asm.FirstFeature()
        print(f"    FirstFeature: {feat} iface={feat.iface if feat else 'None'}")
        if feat:
            tn = feat.GetTypeName2()
            print(f"    GetTypeName2 = {tn}")
    except Exception as e:
        print(f"    error: {e}")

    # 5. 组件摘要
    print(f"\n[5] 组件摘要:")
    try:
        cmap = dao.build_comp_map()
        print(f"    组件数: {len(cmap)}")
        for name in list(cmap.keys())[:10]:
            fixed = dao.comp.is_fixed(name)
            supp = dao.comp.is_suppressed(name)
            print(f"      {name}  fixed={fixed} supp={supp}")
    except Exception as e:
        print(f"    error: {e}")

    # 6. Transform 读
    print(f"\n[6] Transform 读:")
    for name in ("main_shaft-1", "rotor_disc-1", "hammer_pin-1"):
        try:
            xf = dao.transform.get(name)
            org = dao.transform.origin_mm(name)
            if xf:
                print(f"    {name}: origin_mm={org}")
            else:
                print(f"    {name}: N/A")
        except Exception as e:
            print(f"    {name}: {e}")

    # 7. face 扫描
    print(f"\n[7] face 扫描 (hammer_pin-1):")
    try:
        scan = dao.face.scan("hammer_pin-1")
        if scan.get("ok"):
            for fi in scan["faces"][:10]:
                if fi.get("type") == "cylinder":
                    print(f"    cyl: R={fi.get('radius_mm')}mm "
                          f"O={fi.get('origin_mm')} "
                          f"axis={fi.get('axis')}")
                else:
                    print(f"    {fi.get('type')}")
    except Exception as e:
        print(f"    error: {e}")

    # 8. mate 列表
    print(f"\n[8] 当前 mate 列表 (前 10):")
    try:
        mates = dao.mate.list_all(verbose=True)
        for m in mates[:10]:
            print(f"    {m.get('name')}: type={m.get('type')} "
                  f"tn={m.get('type_name')} "
                  f"err={m.get('error_status')}")
        print(f"    共 {len(mates)} 个 mate")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"    error: {e}")

    # 9. 遍历特征树 · 统计 type names (全)
    print(f"\n[9] 特征树全统计:")
    try:
        feat = dao.asm.FirstFeature()
        type_count: Dict[str, int] = {}
        specials = []
        n = 0
        while feat and n < 10000:
            n += 1
            tn = _safe(lambda f=feat: str(f.GetTypeName2()), "?")
            type_count[tn] = type_count.get(tn, 0) + 1
            if tn not in ("Reference", "FavoriteFolder", "HistoryFolder",
                           "SelectionSetFolder", "SensorFolder", "DocsFolder",
                           "DetailCabinet", "InkMarkupFolder", "EnvFolder",
                           "CommentsFolder", "EqnFolder", "RefPlane",
                           "OriginProfileFeature", "?"):
                nm = _safe(lambda f=feat: str(f.Name.cast('IFeature')()
                                              if hasattr(f, 'cast') else ""), "?")
                specials.append(f"    {tn:30s}  name={nm}")
            try:
                feat = feat.GetNextFeature()
            except Exception:
                break
        print(f"    total features: {n}")
        for tn, ct in sorted(type_count.items(), key=lambda x: -x[1]):
            print(f"    {tn:30s}  x{ct}")
        if specials:
            print("    非常规特征:")
            for s in specials:
                print(s)
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"    error: {e}")

    print(f"\n═══ 道直连 · 活体验毕 ═══")


if __name__ == "__main__":
    main()
