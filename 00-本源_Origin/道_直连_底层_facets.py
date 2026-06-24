#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
道_直连_底层_facets.py — 域便捷 · 皆 memid 直调 · 不引入语义层

与 道_直连_底层.py 配对. 本文件提供五大域便捷:
  · _MateFacet        配合建造 (face-direct, 无射线)
  · _TransformFacet   组件变换矩阵 get/set (Transform2 · PUTREF)
  · _SelectFacet      选择 (SelectByID2 / Select4 / 清选)
  · _FaceFacet        B-Rep 面扫描 (cylinder/plane · 装配上下文)
  · _CompFacet        组件 fix/unfix/suppress/resolve

所有操作皆通过 Dao.mt (MemidTable) 的 memid 直调, 无动态分派/gencache 污染.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from 道_直连_底层 import (
    Dao, DaoDispatch, DaoError, MemidTable,
    MATE, ALIGN, SEL, SURF, DOC, SUPP,
    _nothing, _byref_int, _safearray_r8, _ole_of, _safe, _dyn,
)


# ════════════════════════════════════════════════════════════════════════
# _MateFacet — 配合 · face-direct · 无射线
# ════════════════════════════════════════════════════════════════════════
class _MateFacet:
    """AddMate5 包装 · 双 face 句柄直调 (依赖 face.Select4)."""

    def __init__(self, dao: Dao):
        self.dao = dao

    def _add(self, face_a, face_b, mate_type: int,
             align: int = ALIGN.CLOSEST,
             flip: bool = False,
             distance_m: float = 0.0,
             distance_abs_min_m: float = 0.0,
             distance_abs_max_m: float = 0.0,
             gear_ratio_num: float = 0.0,
             gear_ratio_den: float = 0.0,
             for_positioning: bool = False) -> Dict[str, Any]:
        if self.dao.asm is None:
            return {"ok": False, "error": "not_assembly"}
        asm = self.dao.asm

        asm.ClearSelection2(True)  # type: ignore
        try:
            r1 = face_a.Select4(False, _nothing())
            r2 = face_b.Select4(True, _nothing())
        except Exception as e:
            return {"ok": False, "error": f"Select4: {e}"}
        if not r1 or not r2:
            asm.ClearSelection2(True)  # type: ignore
            return {"ok": False, "error": "Select4 returned false"}

        err = _byref_int()
        try:
            mate = asm.AddMate5(  # type: ignore
                mate_type, align, flip,
                float(distance_m),
                float(distance_abs_min_m),
                float(distance_abs_max_m),
                float(gear_ratio_num), float(gear_ratio_den),
                0.0, 0.0, 0.0,
                False, for_positioning, 0, err,
            )
        except Exception as e:
            asm.ClearSelection2(True)  # type: ignore
            return {"ok": False, "error": f"AddMate5: {e}"}

        err_v = _safe(lambda: err.value, -1)
        asm.ClearSelection2(True)  # type: ignore
        if mate is None:
            return {"ok": False, "error": f"AddMate5=None err={err_v}"}

        mate_d = (mate if isinstance(mate, DaoDispatch)
                  else DaoDispatch(_ole_of(mate), "IMate2",
                                    self.dao.mt, self.dao))
        name = _safe(lambda: str(mate_d.cast("IFeature").Name()))
        return {"ok": True, "name": name, "err": err_v, "mate": mate_d}

    def concentric(self, face_a, face_b, align: int = ALIGN.ANTI,
                   unfix_comp: Optional[str] = None) -> Dict[str, Any]:
        with _TempUnfix(self.dao, unfix_comp):
            return self._add(face_a, face_b, MATE.CONCENTRIC, align)

    def coincident(self, face_a, face_b, align: int = ALIGN.ANTI,
                   unfix_comp: Optional[str] = None) -> Dict[str, Any]:
        with _TempUnfix(self.dao, unfix_comp):
            return self._add(face_a, face_b, MATE.COINCIDENT, align)

    def distance(self, face_a, face_b, distance_mm: float,
                 align: int = ALIGN.ALIGNED,
                 unfix_comp: Optional[str] = None) -> Dict[str, Any]:
        d = distance_mm / 1000.0
        with _TempUnfix(self.dao, unfix_comp):
            return self._add(face_a, face_b, MATE.DISTANCE, align,
                             distance_m=d,
                             distance_abs_min_m=d,
                             distance_abs_max_m=d)

    def parallel(self, face_a, face_b, align: int = ALIGN.ANTI,
                 unfix_comp: Optional[str] = None) -> Dict[str, Any]:
        with _TempUnfix(self.dao, unfix_comp):
            return self._add(face_a, face_b, MATE.PARALLEL, align)

    def perpendicular(self, face_a, face_b, align: int = ALIGN.CLOSEST,
                      unfix_comp: Optional[str] = None) -> Dict[str, Any]:
        with _TempUnfix(self.dao, unfix_comp):
            return self._add(face_a, face_b, MATE.PERPENDICULAR, align)

    def tangent(self, face_a, face_b, align: int = ALIGN.CLOSEST,
                unfix_comp: Optional[str] = None) -> Dict[str, Any]:
        with _TempUnfix(self.dao, unfix_comp):
            return self._add(face_a, face_b, MATE.TANGENT, align)

    def angle(self, face_a, face_b, angle_deg: float,
              align: int = ALIGN.CLOSEST,
              unfix_comp: Optional[str] = None) -> Dict[str, Any]:
        a = math.radians(angle_deg)
        with _TempUnfix(self.dao, unfix_comp):
            return self._add(face_a, face_b, MATE.ANGLE, align,
                             distance_m=a,
                             distance_abs_min_m=a,
                             distance_abs_max_m=a)

    # SW 2023+ mate feature type names (prefix "Mate" + 具体类型)
    _MATE_TYPE_NAMES = {
        "Mate", "MateCoincident", "MateConcentric", "MatePerpendicular",
        "MateParallel", "MateTangent", "MateDistance", "MateAngle",
        "MateSymmetric", "MateWidth", "MateGear", "MateLock",
        "MateCam", "MateRackPinion", "MateScrew", "MateHinge",
        "MateSlot", "MatePath", "MateProfileCenter", "MateLinearCoupler",
        "MateUniversalJoint", "MateLimitDistance", "MateLimitAngle",
    }

    def list_all(self, verbose: bool = False) -> List[Dict[str, Any]]:
        """列举当前装配所有 mate · 返 [{name, type_name, type, error_status}].

        策略: 遍历特征树 · 遇 MateGroup 进子特征 · 遇任何 Mate* 提取 IMate2.
        SW 2023+ 用具体 mate 类型名 (MateConcentric 等), 非通用 "Mate".
        """
        if self.dao.asm is None:
            return []
        out: List[Dict[str, Any]] = []
        feat = self.dao.asm.FirstFeature()  # type: ignore
        n = 0
        while feat and n < 10000:
            n += 1
            # 强制 cast 为 IFeature · 避免 IDispatch 歧义
            f = feat.cast("IFeature") if hasattr(feat, "cast") else feat
            tn = _safe(lambda fx=f: str(fx.GetTypeName2()), "")
            # MateGroup 或直接散 Mate* 特征
            if tn == "MateGroup" or tn in self._MATE_TYPE_NAMES:
                if verbose:
                    print(f"  [list_all] enter walk at n={n} tn={tn}")
                before = len(out)
                self._walk_mate_tree(f, out, depth=0, verbose=verbose)
                if verbose:
                    print(f"  [list_all] walk added {len(out)-before} mates")
            try:
                feat = feat.GetNextFeature()  # type: ignore
            except Exception:
                break
        return out

    def _walk_mate_tree(self, feat, out: List[Dict[str, Any]],
                        depth: int = 0, verbose: bool = False):
        """递归遍历特征 · 收集 Mate* 子特征."""
        tn = _safe(lambda fx=feat: str(fx.GetTypeName2()), "")
        if verbose:
            print(f"    {'  '*depth}walk tn={tn}")
        if tn in self._MATE_TYPE_NAMES:
            # Step A: GetSpecificFeature2
            try:
                mate_feat_raw = feat.GetSpecificFeature2()  # type: ignore
            except Exception as e:
                if verbose:
                    print(f"    {'  '*depth}  GSF2 err: {e}")
                return
            if not mate_feat_raw:
                return
            # Step B: cast to IMate2
            try:
                md = (mate_feat_raw.cast("IMate2")
                      if isinstance(mate_feat_raw, DaoDispatch)
                      else DaoDispatch(_ole_of(mate_feat_raw), "IMate2",
                                        self.dao.mt, self.dao))
            except Exception as e:
                if verbose:
                    print(f"    {'  '*depth}  cast err: {e}")
                return
            # Step C: extract Type
            try:
                mtype = md.Type  # type: ignore
                if callable(mtype):
                    mtype = mtype()
            except Exception as e:
                if verbose:
                    print(f"    {'  '*depth}  Type err: {e}")
                mtype = -1
            # Step D: Name + error via IFeature.GetErrorCode2(IsWarning*)
            # (IMate2.ErrorStatus 有 DISP_E_PARAMNOTOPTIONAL 问题;
            #  IFeature.GetErrorCode2 才是真路 · 0=OK / 51=over-def ...)
            f_feat = (feat.cast("IFeature") if hasattr(feat, "cast") else feat)
            err = -1
            is_warn = None
            try:
                import pythoncom, win32com.client
                w = win32com.client.VARIANT(
                    pythoncom.VT_BYREF | pythoncom.VT_BOOL, False)
                ec = _safe(
                    lambda fx=f_feat, ww=w: int(fx.GetErrorCode2(ww)), -1)
                err = ec
                is_warn = _safe(lambda ww=w: bool(ww.value), None)
            except Exception:
                pass
            # Step E: Name
            try:
                name_v = f_feat.Name  # type: ignore
                if callable(name_v):
                    name_v = name_v()
            except Exception as e:
                if verbose:
                    print(f"    {'  '*depth}  Name err: {e}")
                name_v = None
            # Step F: extract component names via IMate2.MateEntity(i)
            comp_names: List[str] = []
            for ei in range(2):
                try:
                    me = md.MateEntity(ei)  # type: ignore
                    if me:
                        rc = me.ReferenceComponent  # type: ignore
                        if callable(rc):
                            rc = rc()
                        if rc:
                            rc2 = (rc.cast("IComponent2")
                                   if isinstance(rc, DaoDispatch)
                                   else DaoDispatch(_ole_of(rc), "IComponent2",
                                                     self.dao.mt, self.dao))
                            cn = _safe(lambda c=rc2: str(c.Name2))  # type: ignore
                            if callable(cn):
                                cn = _safe(lambda c=cn: str(c()))
                            if cn:
                                comp_names.append(cn)
                except Exception:
                    pass
            out.append({
                "name": str(name_v) if name_v is not None else "?",
                "type_name": tn,
                "type": (int(mtype) if isinstance(mtype, (int, float)) else -1),
                "error_status": (int(err) if isinstance(err, (int, float)) else -1),
                "is_warning": is_warn,
                "components": comp_names,
            })
            if verbose:
                print(f"    {'  '*depth}  → added name={name_v} type={mtype} err={err}")
            return
        # MateGroup 或嵌套 · 递归子特征
        try:
            sub = feat.GetFirstSubFeature()  # type: ignore
        except Exception as e:
            if verbose:
                print(f"    {'  '*depth}  GetFirstSub err: {e}")
            return
        safety = 0
        while sub and safety < 500:
            safety += 1
            f_sub = sub.cast("IFeature") if hasattr(sub, "cast") else sub
            self._walk_mate_tree(f_sub, out, depth + 1, verbose)
            try:
                sub = sub.GetNextSubFeature()  # type: ignore
            except Exception:
                break

    def count_ok(self) -> int:
        return sum(1 for m in self.list_all()
                   if m.get("error_status") in (0, None, -1))

    def delete_by_name(self, mate_name: str) -> Dict[str, Any]:
        """按名删 mate · SelectByID2("MATE") + DeleteSelection2.

        mate_name 为 mate feature name (如 '同心26').
        """
        if self.dao.doc is None:
            return {"ok": False, "error": "no_doc"}
        ext = self.dao.doc.Extension  # type: ignore
        if callable(ext):
            ext = ext()
        try:
            self.dao.doc.ClearSelection2(True)  # type: ignore
            ok_sel = ext.SelectByID2(
                mate_name, "MATE", 0.0, 0.0, 0.0, False, 0, _nothing(), 0)
            if not ok_sel:
                return {"ok": False, "error": f"select failed: {mate_name}"}
            # DeleteSelection2(swDelete_Absorbed | swDelete_Children = 18)
            ok_del = ext.DeleteSelection2(18)
            self.dao.doc.ClearSelection2(True)  # type: ignore
            return {"ok": bool(ok_del), "name": mate_name}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def delete_many(self, mate_names: List[str]) -> Dict[str, Any]:
        """批删 mate · 累选 SelectByID2(append=True) 一次 DeleteSelection2."""
        if self.dao.doc is None:
            return {"ok": False, "error": "no_doc", "deleted": 0}
        ext = self.dao.doc.Extension  # type: ignore
        if callable(ext):
            ext = ext()
        self.dao.doc.ClearSelection2(True)  # type: ignore
        selected: List[str] = []
        try:
            for i, nm in enumerate(mate_names):
                append = i > 0
                ok_s = _safe(lambda n=nm, a=append: bool(
                    ext.SelectByID2(n, "MATE", 0.0, 0.0, 0.0,
                                     a, 0, _nothing(), 0)), False)
                if ok_s:
                    selected.append(nm)
            if not selected:
                return {"ok": True, "deleted": 0, "skipped": mate_names}
            ok_del = ext.DeleteSelection2(18)
            self.dao.doc.ClearSelection2(True)  # type: ignore
            return {"ok": bool(ok_del), "deleted": len(selected),
                    "names": selected,
                    "skipped": [n for n in mate_names if n not in selected]}
        except Exception as e:
            self.dao.doc.ClearSelection2(True)  # type: ignore
            return {"ok": False, "error": str(e), "deleted": 0}


# Context manager for temporary unfix
class _TempUnfix:
    def __init__(self, dao: Dao, comp_name: Optional[str]):
        self.dao = dao
        self.name = comp_name
        self._was_fixed: Optional[bool] = None

    def __enter__(self):
        if not self.name:
            return self
        try:
            cmap = self.dao.build_comp_map()
            comp = cmap.get(self.name)
            if comp is None:
                return self
            self._was_fixed = _safe(lambda: bool(comp.IsFixed()), False)
            if self._was_fixed:
                self.dao.comp.unfix(self.name)
        except Exception:
            pass
        return self

    def __exit__(self, *exc):
        if not self.name or not self._was_fixed:
            return False
        try:
            self.dao.comp.fix(self.name)
        except Exception:
            pass
        return False


# ════════════════════════════════════════════════════════════════════════
# _TransformFacet — Transform2 get / set · PUTREF 核心
# ════════════════════════════════════════════════════════════════════════
class _TransformFacet:
    """IComponent2.Transform2 · 强设 + 读取.

    Transform2 是 IMathTransform (4x4 仿射矩阵, 单位 m).
    SW API 只给 1D 16-float 数组 (col-major: R[0..8] + T[9..11] + scale/pad[12..15]).
    """

    def __init__(self, dao: Dao):
        self.dao = dao

    def get(self, comp_name: str) -> Optional[List[float]]:
        """读组件 Transform2 · 返 16-float (col-major 9 rot + 3 trans + 4 pad).
        单位: rotation 无单位, translation 米.
        """
        cmap = self.dao.build_comp_map()
        comp = cmap.get(comp_name)
        if comp is None:
            return None
        try:
            # Transform2 是 property (GET 无参 · 由 DaoDispatch 自动 invoke),
            # 直接属性访问即取值 (返 IMathTransform DaoDispatch).
            xf = comp.Transform2  # type: ignore
            if xf is None:
                return None
            # ArrayData 同为 property · 返 SAFEARRAY(double, 16)
            arr = xf.ArrayData  # type: ignore
            # 兼容: 若 tlb 登记为 method, 可 callable
            if callable(arr):
                arr = arr()
            if arr and len(arr) >= 12:
                return [float(x) for x in arr]
        except Exception as e:
            print(f"  transform.get({comp_name}): {e}")
        return None

    def origin_mm(self, comp_name: str) -> Optional[Tuple[float, float, float]]:
        a = self.get(comp_name)
        if a is None or len(a) < 12:
            return None
        return (a[9] * 1000.0, a[10] * 1000.0, a[11] * 1000.0)

    def set(self, comp_name: str,
            pos_mm: Tuple[float, float, float],
            rot: Optional[Tuple[float, ...]] = None,
            scale: float = 1.0) -> bool:
        """强设组件 Transform2.

        rot = 9-float col-major 旋转矩阵. None → 单位矩阵.
        pos_mm = (x, y, z) 世界位置 mm.

        绕过 SW AddComponent5 的 bbox-center bug.
        """
        cmap = self.dao.build_comp_map()
        comp = cmap.get(comp_name)
        if comp is None:
            return False
        if rot is None:
            rot = (1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0)
        rot = [float(v) for v in rot][:9]
        if len(rot) < 9:
            rot += [0.0] * (9 - len(rot))
        tx, ty, tz = [v / 1000.0 for v in pos_mm]
        arr = rot + [tx, ty, tz, float(scale), 0.0, 0.0, 0.0]
        try:
            v = _safearray_r8(arr)
            math = self.dao.math
            if math is None:
                return False
            nxf = math.CreateTransform(v)  # type: ignore
            if nxf is None:
                return False
            # PUTREF Transform2
            mid = self.dao.mt.memid("IComponent2", "Transform2")
            if mid is None:
                return False
            import pythoncom
            raw_c = _ole_of(comp)
            raw_x = _ole_of(nxf)
            raw_c.Invoke(mid, 0, pythoncom.DISPATCH_PROPERTYPUTREF,
                         False, raw_x)
            return True
        except Exception as e:
            print(f"  transform.set({comp_name}): {e}")
            return False

    def identity(self, comp_name: str) -> bool:
        """重置为单位矩阵 @ 原点."""
        return self.set(comp_name, (0, 0, 0), None)


# ════════════════════════════════════════════════════════════════════════
# _SelectFacet — SelectByID2 + Select4 + 清选
# ════════════════════════════════════════════════════════════════════════
class _SelectFacet:
    """选择便捷 · 透过 IModelDocExtension."""

    def __init__(self, dao: Dao):
        self.dao = dao

    def clear(self):
        if self.dao.doc:
            self.dao.doc.ClearSelection2(True)  # type: ignore

    def by_id(self, name: str, sel_type: str,
              append: bool = False,
              mark: int = 0) -> bool:
        """SelectByID2(Name, Type, X=0, Y=0, Z=0, Append, Mark,
                       Callout=Nothing, SelectOption=0)."""
        if self.dao.ext is None:
            return False
        try:
            ok = self.dao.ext.SelectByID2(  # type: ignore
                str(name), str(sel_type),
                0.0, 0.0, 0.0,
                bool(append), int(mark), _nothing(), 0)
            return bool(ok)
        except Exception as e:
            print(f"  select.by_id({name}@{sel_type}): {e}")
            return False

    def component(self, comp_name: str, append: bool = False,
                  mark: int = 0) -> bool:
        """选组件 · 自动拼 {name}@{asm_title}."""
        if self.dao.asm is None:
            return False
        title = _safe(
            lambda: str(self.dao.asm.GetTitle()).replace(".SLDASM", ""),  # type: ignore
            "")
        return self.by_id(f"{comp_name}@{title}", "COMPONENT", append, mark)

    def plane(self, name: str, append: bool = False,
              mark: int = 0) -> bool:
        return self.by_id(name, "DATUMPLANE", append, mark)

    def face_on_comp(self, face, append: bool = False) -> bool:
        """face.Select4 · append 追加."""
        try:
            return bool(face.Select4(append, _nothing()))
        except Exception:
            return False

    def count(self) -> int:
        if self.dao.sel is None:
            return 0
        try:
            return int(self.dao.sel.GetSelectedObjectCount2(-1))  # type: ignore
        except Exception:
            return 0


# ════════════════════════════════════════════════════════════════════════
# _FaceFacet — B-Rep 面扫描 (装配上下文 face 句柄)
# ════════════════════════════════════════════════════════════════════════
class _FaceFacet:
    """扫描组件 B-Rep · cylinder/plane 分类 · 返 face 句柄.

    face 句柄可用 face.Select4 直选, 绕射线墙.
    """

    def __init__(self, dao: Dao):
        self.dao = dao

    def _comp_body_asm(self, comp):
        """装配上下文 body (face 可 Select4 正常)."""
        for getter in ("GetBody", "GetBody2"):
            try:
                b = getattr(comp, getter)
                if callable(b):
                    b = b()
                if b:
                    return b
            except Exception:
                continue
        try:
            bb = comp.GetBodies2(0, False)  # type: ignore
            if bb and len(bb) > 0:
                return _dyn(bb[0])
        except Exception:
            pass
        return None

    def scan(self, comp_name: str) -> Dict[str, Any]:
        """扫单组件 · 返 {body, faces: [{face, type, radius_mm, origin_mm, axis}]}."""
        cmap = self.dao.build_comp_map()
        comp = cmap.get(comp_name)
        if comp is None:
            return {"ok": False, "error": "comp_not_found"}

        body = self._comp_body_asm(comp)
        if body is None:
            return {"ok": False, "error": "no_body"}

        xform = self.dao.transform.get(comp_name)
        try:
            faces = body.GetFaces  # type: ignore
            if callable(faces):
                faces = faces()
        except Exception as e:
            return {"ok": False, "error": f"GetFaces: {e}"}

        result = []
        for f_com in (faces or []):
            fi = self._classify(f_com, xform)
            if fi:
                result.append(fi)
        return {"ok": True, "faces": result, "n": len(result)}

    def _classify(self, f_com, xform: Optional[List[float]]) -> Optional[Dict[str, Any]]:
        """分类单面 · 提 cylinder params."""
        # 确保 face 句柄可用 Select4 · raw PyIDispatch 需 _dyn 包装
        if not isinstance(f_com, DaoDispatch):
            try:
                f_com = _dyn(f_com)
            except Exception:
                pass
        fi: Dict[str, Any] = {"face": f_com}
        try:
            ident = int(f_com.chain(["GetSurface", "Identity"])
                        if isinstance(f_com, DaoDispatch)
                        else self._chain_surf_identity(f_com))
            fi["type"] = SURF.NAME.get(ident, f"unknown_{ident}")
        except Exception:
            # Fallback: dynamic
            try:
                surf = _dyn(f_com.GetSurface)
                ident = int(surf.Identity if callable(surf.Identity) is False
                            else surf.Identity())
                fi["type"] = SURF.NAME.get(ident, f"unknown_{ident}")
            except Exception:
                fi["type"] = "unknown"

        if fi["type"] == "cylinder":
            cp = self._cylinder_params(f_com)
            if cp:
                # cp = (root.x, root.y, root.z, axis.x, axis.y, axis.z, R) 米
                if xform:
                    wr = _xf_pt(xform, cp[0:3])
                    wa = _xf_vec(xform, cp[3:6])
                else:
                    wr = list(cp[0:3])
                    wa = list(cp[3:6])
                fi["radius_mm"] = round(cp[6] * 1000, 3)
                fi["origin_mm"] = (round(wr[0] * 1000, 3),
                                   round(wr[1] * 1000, 3),
                                   round(wr[2] * 1000, 3))
                fi["axis"] = (round(wa[0], 6),
                              round(wa[1], 6),
                              round(wa[2], 6))
        elif fi["type"] == "plane":
            pp = self._plane_params(f_com)
            if pp:
                # SW PlaneParams = (normal.x, normal.y, normal.z, root.x, root.y, root.z) 米
                if xform:
                    wn = _xf_vec(xform, pp[0:3])
                    wr = _xf_pt(xform, pp[3:6])
                else:
                    wn = list(pp[0:3])
                    wr = list(pp[3:6])
                fi["origin_mm"] = (round(wr[0] * 1000, 3),
                                   round(wr[1] * 1000, 3),
                                   round(wr[2] * 1000, 3))
                fi["normal"] = (round(wn[0], 6),
                                round(wn[1], 6),
                                round(wn[2], 6))
        return fi

    def _chain_surf_identity(self, f_com):
        import pythoncom
        ole = _ole_of(f_com)
        mt = self.dao.mt
        mid_surf = mt.memid("IFace2", "GetSurface")
        surf = ole.Invoke(
            mid_surf, 0,
            pythoncom.DISPATCH_METHOD | pythoncom.DISPATCH_PROPERTYGET,
            True)
        mid_id = mt.memid("ISurface", "Identity")
        return _ole_of(surf).Invoke(
            mid_id, 0,
            pythoncom.DISPATCH_METHOD | pythoncom.DISPATCH_PROPERTYGET,
            True)

    def _plane_params(self, f_com) -> Optional[Tuple[float, ...]]:
        """ISurface.PlaneParams · 6-tuple: (root.xyz, normal.xyz)."""
        import pythoncom
        try:
            ole = _ole_of(f_com)
            mt = self.dao.mt
            mid_surf = mt.memid("IFace2", "GetSurface")
            surf = ole.Invoke(
                mid_surf, 0,
                pythoncom.DISPATCH_METHOD | pythoncom.DISPATCH_PROPERTYGET,
                True)
            mid_pp = mt.memid("ISurface", "PlaneParams")
            pp = _ole_of(surf).Invoke(
                mid_pp, 0,
                pythoncom.DISPATCH_METHOD | pythoncom.DISPATCH_PROPERTYGET,
                True)
            if pp and len(pp) >= 6:
                return tuple(float(x) for x in pp)
        except Exception:
            pass
        # Fallback
        try:
            surf = _dyn(f_com.GetSurface)
            pp = surf.PlaneParams
            if callable(pp):
                pp = pp()
            if pp and len(pp) >= 6:
                return tuple(float(x) for x in pp)
        except Exception:
            pass
        return None

    def _cylinder_params(self, f_com) -> Optional[Tuple[float, ...]]:
        """ISurface.CylinderParams · 7-tuple: (root.xyz, axis.xyz, R)."""
        import pythoncom
        try:
            ole = _ole_of(f_com)
            mt = self.dao.mt
            mid_surf = mt.memid("IFace2", "GetSurface")
            surf = ole.Invoke(
                mid_surf, 0,
                pythoncom.DISPATCH_METHOD | pythoncom.DISPATCH_PROPERTYGET,
                True)
            mid_cp = mt.memid("ISurface", "CylinderParams")
            cp = _ole_of(surf).Invoke(
                mid_cp, 0,
                pythoncom.DISPATCH_METHOD | pythoncom.DISPATCH_PROPERTYGET,
                True)
            if cp and len(cp) >= 7:
                return tuple(float(x) for x in cp)
        except Exception:
            pass
        # Fallback
        try:
            surf = _dyn(f_com.GetSurface)
            cp = surf.CylinderParams
            if callable(cp):
                cp = cp()
            if cp and len(cp) >= 7:
                return tuple(float(x) for x in cp)
        except Exception:
            pass
        return None

    def find_cylinder(self, comp_name: str,
                      radius_mm: Optional[float] = None,
                      axis: Optional[Tuple[float, float, float]] = None,
                      through_point_mm: Optional[Tuple[float, float, float]] = None,
                      tol_mm: float = 1.0,
                      tol_axis: float = 0.05) -> Optional[Any]:
        """按几何挑圆柱面 · 返 face 句柄 (供 Select4/mate).

        当 radius_mm 严格匹配失败时, 自动放宽到最近半径的圆柱面.
        """
        scan = self.scan(comp_name)
        if not scan.get("ok"):
            return None
        cyls = [fi for fi in scan["faces"] if fi.get("type") == "cylinder"]
        if not cyls:
            return None
        # 严格匹配
        for fi in cyls:
            if not self._cyl_match(fi, radius_mm, axis, through_point_mm,
                                   tol_mm, tol_axis):
                continue
            return fi["face"]
        # 放宽: 忽略半径, 仅看轴向/穿过点
        if radius_mm is not None:
            for fi in cyls:
                if not self._cyl_match(fi, None, axis, through_point_mm,
                                       tol_mm, tol_axis):
                    continue
                return fi["face"]
        # 最后兜底: 返最大半径圆柱面
        best = max(cyls, key=lambda f: f.get("radius_mm", 0))
        return best["face"]

    def _cyl_match(self, fi, radius_mm, axis, through_point_mm,
                   tol_mm, tol_axis) -> bool:
        if radius_mm is not None:
            r = fi.get("radius_mm")
            if r is None or abs(r - radius_mm) > tol_mm:
                return False
        if axis is not None:
            a = fi.get("axis")
            if a is None:
                return False
            dot = sum(a[i] * axis[i] for i in range(3))
            if abs(abs(dot) - 1.0) > tol_axis:
                return False
        if through_point_mm is not None:
            o = fi.get("origin_mm")
            a = fi.get("axis")
            if o is None or a is None:
                return False
            d = _point_axis_dist_mm(through_point_mm, o, a)
            if d > tol_mm:
                return False
        return True

    def find_plane(self, comp_name: str,
                   normal: Optional[Tuple[float, float, float]] = None,
                   tol_axis: float = 0.05) -> Optional[Any]:
        """按法向挑平面."""
        scan = self.scan(comp_name)
        if not scan.get("ok"):
            return None
        planes = [fi for fi in scan["faces"] if fi.get("type") == "plane"]
        if not planes:
            return None
        if normal is None:
            return planes[0]["face"]
        # 按法向匹配 · 找与指定法向最接近的平面 (允许反向)
        best_face, best_dot = None, -1.0
        for fi in planes:
            n = fi.get("normal")
            if n is None:
                continue
            dot = abs(sum(n[i] * normal[i] for i in range(3)))
            if dot > best_dot:
                best_dot = dot
                best_face = fi["face"]
        if best_face is not None and best_dot > (1.0 - tol_axis):
            return best_face
        # 无法严格匹配法向 · 返第一个平面
        return planes[0]["face"]


def _xf_pt(xform: List[float], p: Tuple[float, ...]) -> List[float]:
    """应用 16-float xform 到 point (col-major 9 rot + 3 trans)."""
    r = xform[:9]
    t = xform[9:12]
    return [
        r[0] * p[0] + r[3] * p[1] + r[6] * p[2] + t[0],
        r[1] * p[0] + r[4] * p[1] + r[7] * p[2] + t[1],
        r[2] * p[0] + r[5] * p[1] + r[8] * p[2] + t[2],
    ]


def _xf_vec(xform: List[float], v: Tuple[float, ...]) -> List[float]:
    """应用 rotation only 到向量."""
    r = xform[:9]
    return [
        r[0] * v[0] + r[3] * v[1] + r[6] * v[2],
        r[1] * v[0] + r[4] * v[1] + r[7] * v[2],
        r[2] * v[0] + r[5] * v[1] + r[8] * v[2],
    ]


def _point_axis_dist_mm(p_mm: Tuple[float, float, float],
                         a_mm: Tuple[float, float, float],
                         axis: Tuple[float, float, float]) -> float:
    """点 p 到 (a, axis) 轴线的距离 (mm)."""
    # vec ap
    apx, apy, apz = p_mm[0] - a_mm[0], p_mm[1] - a_mm[1], p_mm[2] - a_mm[2]
    # cross(ap, axis)
    cx = apy * axis[2] - apz * axis[1]
    cy = apz * axis[0] - apx * axis[2]
    cz = apx * axis[1] - apy * axis[0]
    # |cross| / |axis|
    amag = math.sqrt(axis[0] ** 2 + axis[1] ** 2 + axis[2] ** 2)
    if amag < 1e-12:
        return float("inf")
    cmag = math.sqrt(cx * cx + cy * cy + cz * cz)
    return cmag / amag


# ════════════════════════════════════════════════════════════════════════
# _CompFacet — 组件 fix/unfix/suppress/resolve
# ════════════════════════════════════════════════════════════════════════
class _CompFacet:
    """组件便捷 · fix/unfix/suppress/resolve/get."""

    def __init__(self, dao: Dao):
        self.dao = dao

    def __getitem__(self, name: str) -> Optional[DaoDispatch]:
        return self.dao.build_comp_map().get(name)

    def __contains__(self, name: str) -> bool:
        return name in self.dao.build_comp_map()

    def __iter__(self):
        return iter(self.dao.build_comp_map().keys())

    def names(self) -> List[str]:
        return list(self.dao.build_comp_map().keys())

    def _call_or_val(self, obj, name: str):
        """属性/方法统一取值 · 兼容 (无论 DaoDispatch 返值还是闭包)."""
        if obj is None:
            return None
        try:
            v = getattr(obj, name)
        except Exception:
            return None
        if callable(v):
            try:
                return v()
            except Exception:
                return None
        return v

    def is_fixed(self, name: str) -> Optional[bool]:
        comp = self[name]
        if comp is None:
            return None
        v = self._call_or_val(comp, "IsFixed")
        return bool(v) if v is not None else None

    def is_suppressed(self, name: str) -> Optional[bool]:
        comp = self[name]
        if comp is None:
            return None
        s = self._call_or_val(comp, "GetSuppression")
        if s is None:
            return None
        return int(s) == SUPP.SUPPRESSED

    def fix(self, name: str) -> bool:
        return self._set_fix(name, True)

    def unfix(self, name: str) -> bool:
        return self._set_fix(name, False)

    def _set_fix(self, name: str, fixed: bool) -> bool:
        if self.dao.asm is None:
            return False
        comp = self[name]
        if comp is None:
            return False
        cur = _safe(lambda: bool(comp.IsFixed()), None)  # type: ignore
        if cur == fixed:
            return True
        if not self.dao.select.component(name):
            return False
        try:
            if fixed:
                self.dao.asm.FixComponent()  # type: ignore
            else:
                self.dao.asm.UnfixComponent()  # type: ignore
            self.dao.select.clear()
            return True
        except Exception:
            self.dao.select.clear()
            return False

    def suppress(self, name: str) -> bool:
        return self._set_suppression(name, SUPP.SUPPRESSED)

    def resolve(self, name: str) -> bool:
        return self._set_suppression(name, SUPP.RESOLVED)

    def _set_suppression(self, name: str, state: int) -> bool:
        comp = self[name]
        if comp is None:
            return False
        try:
            return bool(comp.SetSuppression2(state))  # type: ignore
        except Exception:
            return False

    def suppressed_names(self) -> List[str]:
        return [n for n in self.names() if self.is_suppressed(n)]

    def resolved_names(self) -> List[str]:
        return [n for n in self.names() if self.is_suppressed(n) is False]

    def fixed_names(self) -> List[str]:
        return [n for n in self.names() if self.is_fixed(n)]

    def constrained_status(self, name: str) -> Optional[int]:
        """swComponentConstrainedStatus_e: 0=free 1=fully 2=over 3=fixed."""
        comp = self[name]
        if comp is None:
            return None
        return _safe(lambda: int(comp.GetConstrainedStatus()), None)  # type: ignore

    def _asm_title(self) -> str:
        """取当前装配标题 (用于 suppressed 组件 select 的 @asm 后缀)."""
        try:
            t = self.dao.doc.GetTitle()  # type: ignore
            if callable(t):
                t = t()
            t = str(t or "")
            # 去扩展名 (如 .SLDASM)
            dot = t.rfind(".")
            return t[:dot] if dot > 0 else t
        except Exception:
            return ""

    def _select_name_for(self, name: str) -> str:
        """构 SelectByID2 用名 · suppressed 需 `name@asm_title`."""
        comp = self[name]
        if comp is not None and self.is_suppressed(name):
            asm = self._asm_title()
            return f"{name}@{asm}" if asm else name
        return name

    def delete(self, name: str) -> Dict[str, Any]:
        """永删组件 (含 suppressed) · SelectByID2("COMPONENT") + DeleteSelection2."""
        if self.dao.doc is None:
            return {"ok": False, "error": "no_doc"}
        ext = self.dao.doc.Extension  # type: ignore
        if callable(ext):
            ext = ext()
        try:
            self.dao.doc.ClearSelection2(True)  # type: ignore
            full_name = self._select_name_for(name)
            ok_sel = ext.SelectByID2(
                full_name, "COMPONENT", 0.0, 0.0, 0.0,
                False, 0, _nothing(), 0)
            if not ok_sel:
                return {"ok": False,
                        "error": f"select failed: {full_name}"}
            ok_del = ext.DeleteSelection2(18)
            self.dao.doc.ClearSelection2(True)  # type: ignore
            # 失效组件缓存 · 删后立即反映
            self.dao._comp_map_cache = None  # type: ignore
            return {"ok": bool(ok_del), "name": name,
                    "select_name": full_name}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def delete_many(self, names: List[str]) -> Dict[str, Any]:
        """批删组件 (含 suppressed) · 累选一次删."""
        if self.dao.doc is None:
            return {"ok": False, "error": "no_doc", "deleted": 0}
        ext = self.dao.doc.Extension  # type: ignore
        if callable(ext):
            ext = ext()
        self.dao.doc.ClearSelection2(True)  # type: ignore
        selected: List[str] = []
        try:
            for i, nm in enumerate(names):
                full_nm = self._select_name_for(nm)
                append = i > 0
                ok_s = _safe(lambda n=full_nm, a=append: bool(
                    ext.SelectByID2(n, "COMPONENT", 0.0, 0.0, 0.0,
                                     a, 0, _nothing(), 0)), False)
                if ok_s:
                    selected.append(nm)
            if not selected:
                return {"ok": True, "deleted": 0, "skipped": names}
            ok_del = ext.DeleteSelection2(18)
            self.dao.doc.ClearSelection2(True)  # type: ignore
            # 失效组件缓存 · 删后立即反映
            self.dao._comp_map_cache = None  # type: ignore
            return {"ok": bool(ok_del), "deleted": len(selected),
                    "names": selected,
                    "skipped": [n for n in names if n not in selected]}
        except Exception as e:
            self.dao.doc.ClearSelection2(True)  # type: ignore
            return {"ok": False, "error": str(e), "deleted": 0}
