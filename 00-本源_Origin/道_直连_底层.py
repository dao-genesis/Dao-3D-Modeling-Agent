#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
道_直连_底层.py — 道直连器 · 无为而无不为 · v1.0

"反者道之动, 弱者道之用. 圣人执古之道, 以御今之有."

从 Python 直达 SolidWorks 底层 · 无中间层 · 唯官方 sldworks.tlb 为源.

  Python → memid Invoke → sldworks.tlb (1001 types · 505 interfaces · 官方)
                                 ↓
                         SldWorks.Application (COM)

已淘汰的中间层:
  ✗ dao_sw_live Builders (140 KB)
  ✗ dao_sw_omni wrapper (65 KB)
  ✗ dao_sw_bridge re-exporter (3 KB)
  ✗ _com_prop/_com_call/_dyn_wrap property-vs-method 补丁

核心:
  ① MemidTable   — 全境 memid 表 (sldworks.tlb + 辅助 tlb)
  ② DaoDispatch  — 包裹 oleobj+iface, __getattr__ 自动 memid Invoke, 链式自动推断
  ③ Dao          — 单例 · 连接 · 绑 sw/doc/asm/ext/sel/fm/sm/math
  ④ 域便捷       — mate/transform/select/face/comp (皆 memid 直调)

用法:
    from 道_直连_底层 import Dao
    dao = Dao().connect()
    print(dao.summary())
    # 任意 SW API 直达:
    n = dao.asm.GetMateCount()
    # 域便捷:
    dao.transform.set("hammer-1", (207, 220, -20), rot=(0,0,-1, 0,1,0, 1,0,0))
    dao.mate.concentric(face_a, face_b, align=1, unfix_comp="hammer-1")
"""
from __future__ import annotations

import math
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

_HERE = Path(__file__).resolve().parent
_DAO_ROOT = next(
    (p for p in Path(__file__).resolve().parents if (p / "_paths.py").is_file()),
    _HERE.parent,
)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

__version__ = "1.0.0"
__all__ = [
    "Dao", "DaoDispatch", "DaoError", "MemidTable",
    "MATE", "ALIGN", "SEL", "SURF", "DOC", "SUPP",
]


# ════════════════════════════════════════════════════════════════════════
# 常量 (对应 SW 官方 swconst.h)
# ════════════════════════════════════════════════════════════════════════
class MATE:
    COINCIDENT = 0
    CONCENTRIC = 1
    PERPENDICULAR = 2
    PARALLEL = 3
    TANGENT = 4
    DISTANCE = 5
    ANGLE = 6
    SYMMETRIC = 11
    WIDTH = 17
    GEAR = 13
    LOCK = 11
    BY_NAME = {"coincident": 0, "concentric": 1, "perpendicular": 2,
               "parallel": 3, "tangent": 4, "distance": 5, "angle": 6,
               "symmetric": 11, "width": 17, "gear": 13}


class ALIGN:
    ALIGNED = 0
    ANTI = 1
    CLOSEST = 2
    SAME = 0  # alias


class SEL:
    NOTHING = 0
    EDGE = 1
    FACE = 2
    VERTEX = 3
    BODY = 4
    FEATURE = 5
    SKETCH = 9
    SKETCHSEG = 10
    SKETCHPOINT = 11
    DATUMPLANE = 19
    DATUMAXIS = 20
    COMPONENT = 20
    REFPOINT = 23
    MATE = 32


class SURF:
    PLANE = 4001
    CYLINDER = 4002
    CONE = 4003
    SPHERE = 4004
    TORUS = 4005
    BSURF = 4006
    BLEND = 4007
    OFFSET = 4008
    EXTRUSION = 4009
    NAME = {4001: "plane", 4002: "cylinder", 4003: "cone",
            4004: "sphere", 4005: "torus", 4006: "bspline",
            4007: "blend", 4008: "offset", 4009: "extrusion"}


class DOC:
    NONE = 0
    PART = 1
    ASSEMBLY = 2
    DRAWING = 3
    NAME = {0: "none", 1: "part", 2: "assembly", 3: "drawing"}


class SUPP:
    SUPPRESSED = 0
    LIGHTWEIGHT = 1
    RESOLVED = 2


class DaoError(RuntimeError):
    pass


# ════════════════════════════════════════════════════════════════════════
# COM 原语
# ════════════════════════════════════════════════════════════════════════
def _dyn(obj):
    if obj is None:
        return None
    try:
        import win32com.client.dynamic as _d
        return _d.Dispatch(obj._oleobj_)
    except Exception:
        try:
            import win32com.client
            return win32com.client.Dispatch(obj)
        except Exception:
            return obj


def _nothing():
    import pythoncom, win32com.client
    return win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)


def _byref_int(val=0):
    import pythoncom, win32com.client
    return win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, val)


def _safearray_r8(arr):
    import pythoncom, win32com.client
    return win32com.client.VARIANT(
        pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(x) for x in arr])


def _ole_of(obj):
    if hasattr(obj, "_ole"):        # DaoDispatch
        return obj._ole
    if hasattr(obj, "_oleobj_"):    # pywin32 CDispatch
        return obj._oleobj_
    return obj


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


_VT_NAMES = {
    0: "VT_EMPTY", 2: "short", 3: "long", 4: "float", 5: "double",
    6: "CY", 7: "DATE", 8: "BSTR", 9: "IDispatch*", 10: "SCODE",
    11: "bool", 12: "VARIANT", 13: "IUnknown*", 16: "i1", 17: "ui1",
    18: "ui2", 19: "ui4", 20: "i8", 21: "ui8", 22: "int", 23: "uint",
    24: "void", 25: "HRESULT", 26: "PTR", 27: "SAFEARRAY", 28: "CARRAY",
    29: "USERDEFINED", 36: "RECORD",
}


# ════════════════════════════════════════════════════════════════════════
# ① MemidTable — 从 sldworks.tlb 载入 memid + 返回类型 + 参数签名
# ════════════════════════════════════════════════════════════════════════
class MemidTable:
    """sldworks.tlb 全境 memid 表 · 单例."""

    _instance: Optional["MemidTable"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_once()
        return cls._instance

    def _init_once(self):
        self._methods: Dict[str, Dict[str, int]] = {}
        self._props: Dict[str, Dict[str, int]] = {}
        self._ret_types: Dict[str, Dict[str, str]] = {}
        self._params: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        # 分 invkind 跟踪参数 (property GET/PUT 不同 · method 不同)
        self._getter_params: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        self._method_params: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        self._has_getter: Dict[str, set] = {}  # iface → 含 invkind=2 的 name set
        self._enums: Dict[str, Dict[str, int]] = {}
        self._href_cache: Dict[int, str] = {}
        self._inherits: Dict[str, List[str]] = {}  # iface → [父接口...]
        self._tlb_paths: List[str] = []
        self._loaded: bool = False

    def load(self, sw_exe: Optional[str] = None,
             also_aux_tlbs: bool = True) -> bool:
        if self._loaded:
            return True
        import pythoncom

        tlb_path = self._locate_main_tlb(sw_exe)
        if not tlb_path:
            return False

        try:
            tlib = pythoncom.LoadTypeLib(tlb_path)
            self._warm_href(tlib)
            self._ingest(tlib)
            self._tlb_paths.append(tlb_path)

            if also_aux_tlbs:
                sw_dir = os.path.dirname(tlb_path)
                for fn in os.listdir(sw_dir):
                    if fn.endswith(".tlb") and fn.lower() != "sldworks.tlb":
                        p = os.path.join(sw_dir, fn)
                        try:
                            t = pythoncom.LoadTypeLib(p)
                            self._warm_href(t)
                            self._ingest(t)
                            self._tlb_paths.append(p)
                        except Exception:
                            continue

            self._loaded = True
            return True
        except Exception as e:
            print(f"[MemidTable] 载入失败: {e}", file=sys.stderr)
            return False

    def _locate_main_tlb(self, sw_exe: Optional[str]) -> Optional[str]:
        if sw_exe:
            p = os.path.join(os.path.dirname(sw_exe), "sldworks.tlb")
            if os.path.exists(p):
                return p
        for c in [
            r"D:\Program Files\SOLIDWORKS Corp23\SOLIDWORKS\sldworks.tlb",
            r"D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb",
            r"C:\Program Files\SOLIDWORKS Corp23\SOLIDWORKS\sldworks.tlb",
            r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb",
            r"C:\Program Files\SOLIDWORKS\SOLIDWORKS\sldworks.tlb",
        ]:
            if os.path.exists(c):
                return c
        try:
            import winreg
            for hk in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    k = winreg.OpenKey(hk, r"SOFTWARE\SolidWorks\SOLIDWORKS")
                    v, _ = winreg.QueryValueEx(k, "SolidWorksExePath")
                    winreg.CloseKey(k)
                    p = os.path.join(os.path.dirname(v), "sldworks.tlb")
                    if os.path.exists(p):
                        return p
                except OSError:
                    continue
        except Exception:
            pass
        return None

    def _warm_href(self, tlib):
        n = tlib.GetTypeInfoCount()
        for i in range(n):
            try:
                ti = tlib.GetTypeInfo(i)
                ta = ti.GetTypeAttr()
                for idx in range(ta.cImplTypes):
                    try:
                        href = ti.GetRefTypeOfImplType(idx)
                        if href not in self._href_cache:
                            ref = ti.GetRefTypeInfo(href)
                            self._href_cache[href] = ref.GetDocumentation(-1)[0]
                    except Exception:
                        continue
            except Exception:
                continue

    def _resolve_td(self, ti, td) -> str:
        if td is None:
            return "?"
        try:
            if isinstance(td, int):
                return _VT_NAMES.get(td, f"vt_{td}")
            if isinstance(td, tuple):
                if (len(td) == 3 and isinstance(td[1], int)
                        and (td[2] is None
                             or isinstance(td[2], (int, float, str)))):
                    return self._resolve_td(ti, td[0])
                vt = td[0] if len(td) > 0 else 0
                if isinstance(vt, tuple):
                    return self._resolve_td(ti, vt)
                if vt == 26 and len(td) > 1:
                    inner = self._resolve_td(ti, td[1])
                    return inner if inner.startswith("vt_") else f"{inner}*"
                if vt == 29 and len(td) > 1:
                    href = td[1]
                    if href in self._href_cache:
                        return self._href_cache[href]
                    try:
                        ref = ti.GetRefTypeInfo(href)
                        name = ref.GetDocumentation(-1)[0]
                        self._href_cache[href] = name
                        return name
                    except Exception:
                        return f"href:{href}"
                if vt == 27 and len(td) > 1:
                    return f"SAFEARRAY({self._resolve_td(ti, td[1])})"
                return _VT_NAMES.get(vt, f"vt_{vt}")
            return str(td)
        except Exception:
            return "?"

    def _ingest(self, tlib):
        n = tlib.GetTypeInfoCount()
        for i in range(n):
            try:
                k = tlib.GetTypeInfoType(i)
                name = tlib.GetDocumentation(i)[0]
            except Exception:
                continue
            if k == 0:  # ENUM
                try:
                    ti = tlib.GetTypeInfo(i)
                    ta = ti.GetTypeAttr()
                    vals = {}
                    for j in range(ta.cVars):
                        vd = ti.GetVarDesc(j)
                        vn = ti.GetNames(vd.memid)[0]
                        vals[vn] = vd.value
                    if vals:
                        self._enums[name] = vals
                except Exception:
                    continue
            elif k in (3, 4):  # INTERFACE / DISPATCH
                try:
                    ti = tlib.GetTypeInfo(i)
                    ta = ti.GetTypeAttr()
                    methods: Dict[str, int] = {}
                    props: Dict[str, int] = {}
                    rt: Dict[str, str] = {}
                    pm: Dict[str, List[Dict[str, Any]]] = {}
                    getter_pm: Dict[str, List[Dict[str, Any]]] = {}
                    method_pm: Dict[str, List[Dict[str, Any]]] = {}
                    has_get: set = set()
                    # ── 继承链 ──
                    parents: List[str] = []
                    for impl_idx in range(ta.cImplTypes):
                        try:
                            href = ti.GetRefTypeOfImplType(impl_idx)
                            ref = ti.GetRefTypeInfo(href)
                            pname = ref.GetDocumentation(-1)[0]
                            if pname and pname != name:
                                parents.append(pname)
                                self._href_cache[href] = pname
                        except Exception:
                            continue
                    if parents:
                        self._inherits.setdefault(name, [])
                        for p in parents:
                            if p not in self._inherits[name]:
                                self._inherits[name].append(p)
                    for j in range(ta.cFuncs):
                        try:
                            fd = ti.GetFuncDesc(j)
                            fname = ti.GetNames(fd.memid)[0]
                            all_names = ti.GetNames(fd.memid)
                            p_names = (list(all_names[1:])
                                       if len(all_names) > 1 else [])
                            invk = fd.invkind
                            if invk == 1:
                                methods[fname] = fd.memid
                            elif invk in (2, 4):
                                props[fname] = fd.memid
                                if invk == 2:
                                    has_get.add(fname)
                            # 返回类型 (对 GET/method 记录; PUT 的 rettype 通常 void)
                            if invk != 4:
                                try:
                                    resolved_rt = self._resolve_td(ti, fd.rettype)
                                    if resolved_rt and resolved_rt != "void":
                                        rt[fname] = resolved_rt
                                except Exception:
                                    pass
                            # params
                            p_list: List[Dict[str, Any]] = []
                            try:
                                eds = fd.args if hasattr(fd, "args") else []
                            except Exception:
                                eds = []
                            for pi, ed in enumerate(eds or []):
                                pn = (p_names[pi] if pi < len(p_names)
                                      else f"arg{pi}")
                                try:
                                    pt = self._resolve_td(
                                        ti, ed[0] if isinstance(ed, tuple) else ed)
                                except Exception:
                                    pt = "?"
                                p_list.append({"name": pn, "type": pt})
                            # 分类存
                            if invk == 2:
                                getter_pm[fname] = p_list  # 可能为 []
                            elif invk == 1:
                                method_pm[fname] = p_list
                            # 合并到 legacy _params (保留兼容)
                            if p_list and fname not in pm:
                                pm[fname] = p_list
                            elif p_list and invk == 2:
                                # GET 优先 (更准)
                                pm[fname] = p_list
                        except Exception:
                            continue
                    if methods:
                        self._methods.setdefault(name, {}).update(methods)
                    if props:
                        self._props.setdefault(name, {}).update(props)
                    if rt:
                        self._ret_types.setdefault(name, {}).update(rt)
                    if pm:
                        self._params.setdefault(name, {}).update(pm)
                    if getter_pm:
                        self._getter_params.setdefault(name, {}).update(getter_pm)
                    if method_pm:
                        self._method_params.setdefault(name, {}).update(method_pm)
                    if has_get:
                        self._has_getter.setdefault(name, set()).update(has_get)
                except Exception:
                    continue

    @property
    def loaded(self) -> bool:
        return self._loaded

    def _iface_chain(self, iface: str, _seen: Optional[set] = None) -> List[str]:
        """当前接口 + 所有祖先接口 (深度优先 · 去环)."""
        if _seen is None:
            _seen = set()
        if iface in _seen:
            return []
        _seen.add(iface)
        chain = [iface]
        for p in self._inherits.get(iface, []):
            chain.extend(self._iface_chain(p, _seen))
        return chain

    def memid(self, iface: str, name: str) -> Optional[int]:
        """查 memid · 先当前接口+继承链, 再全局搜 (SW dispinterface 扁平)."""
        for c in self._iface_chain(iface):
            m = self._methods.get(c, {}).get(name)
            if m is not None:
                return m
            m = self._props.get(c, {}).get(name)
            if m is not None:
                return m
        # 全局搜 · SW tlb 里 IAssemblyDoc/IPartDoc 不显式继承 IModelDoc2,
        # 但活体对象 (IDispatch) 支持所有父接口的 memid.
        found = self.find_anywhere(name)
        if found:
            return found[1]
        return None

    def which_iface(self, iface: str, name: str) -> Optional[str]:
        """定位 · method 实际定义在哪个 (父) 接口 · 若不在链内再全局搜."""
        for c in self._iface_chain(iface):
            if (name in self._methods.get(c, {})
                    or name in self._props.get(c, {})):
                return c
        found = self.find_anywhere(name)
        return found[0] if found else None

    def find_anywhere(self, name: str) -> Optional[Tuple[str, int]]:
        """全局搜: 返第一个 (iface, memid) 匹配.

        SW COM dispinterface 是扁平的 (每个接口独立存所有方法), 但
        活体对象通过 IDispatch 实现, 跨接口 memid 唯一且可互通.
        优先返有返回类型记录的接口 (类型推断更准确).
        """
        # 偏好有返回类型记录的接口 (通常是 "原生" 接口, 如 IModelDoc2
        # 而非 IDrawingDoc 这种 stub)
        candidates_with_ret: List[Tuple[str, int]] = []
        candidates_bare: List[Tuple[str, int]] = []
        for iface, methods in self._methods.items():
            if name in methods:
                mid = methods[name]
                if self._ret_types.get(iface, {}).get(name):
                    candidates_with_ret.append((iface, mid))
                else:
                    candidates_bare.append((iface, mid))
        for iface, props in self._props.items():
            if name in props:
                mid = props[name]
                if self._ret_types.get(iface, {}).get(name):
                    candidates_with_ret.append((iface, mid))
                else:
                    candidates_bare.append((iface, mid))
        if candidates_with_ret:
            # 偏好 IModelDoc2 > IModelDoc > 其他
            candidates_with_ret.sort(key=lambda x: (
                0 if x[0] == "IModelDoc2" else
                1 if x[0] == "IModelDoc" else
                2 if x[0].startswith("ISldWorks") else
                3))
            return candidates_with_ret[0]
        if candidates_bare:
            return candidates_bare[0]
        return None

    def ret_type(self, iface: str, name: str) -> Optional[str]:
        """沿继承链 + 全局搜返回类型."""
        for c in self._iface_chain(iface):
            rt = self._ret_types.get(c, {}).get(name)
            if rt is not None:
                return rt
        # 全局搜 (用定位到的原生接口的返回类型)
        w = self.which_iface(iface, name)
        if w and w != iface:
            return self._ret_types.get(w, {}).get(name)
        return None

    def params_of(self, iface: str, name: str) -> List[Dict[str, Any]]:
        for c in self._iface_chain(iface):
            p = self._params.get(c, {}).get(name)
            if p is not None:
                return p
        w = self.which_iface(iface, name)
        if w and w != iface:
            return self._params.get(w, {}).get(name, [])
        return []

    def is_prop_only(self, iface: str, name: str) -> bool:
        """是否仅属性 (invkind 2/4, 无方法同名 entry)."""
        for c in self._iface_chain(iface):
            if name in self._methods.get(c, {}):
                return False
            if name in self._props.get(c, {}):
                return True
        # 全局搜
        w = self.which_iface(iface, name)
        if w and w != iface:
            if name in self._methods.get(w, {}):
                return False
            if name in self._props.get(w, {}):
                return True
        return False

    def is_getter(self, iface: str, name: str) -> bool:
        """有无 PROPERTYGET (invkind=2) 形式 · 用于决定是否立即 Invoke."""
        for c in self._iface_chain(iface):
            if name in self._has_getter.get(c, set()):
                return True
        w = self.which_iface(iface, name)
        if w and w != iface and name in self._has_getter.get(w, set()):
            return True
        return False

    def getter_params(self, iface: str, name: str) -> List[Dict[str, Any]]:
        """专门查 PROPERTYGET 形式的参数 (通常为空)."""
        for c in self._iface_chain(iface):
            p = self._getter_params.get(c, {}).get(name)
            if p is not None:
                return p
        w = self.which_iface(iface, name)
        if w and w != iface:
            return self._getter_params.get(w, {}).get(name, [])
        return []

    def method_params(self, iface: str, name: str) -> List[Dict[str, Any]]:
        """专门查 method (invkind=1) 形式的参数."""
        for c in self._iface_chain(iface):
            p = self._method_params.get(c, {}).get(name)
            if p is not None:
                return p
        w = self.which_iface(iface, name)
        if w and w != iface:
            return self._method_params.get(w, {}).get(name, [])
        return []

    def resolve_iface(self, iface: str, name: str) -> Optional[str]:
        rt = self.ret_type(iface, name)
        if not rt:
            return None
        clean = rt.rstrip("*")
        if clean in self._methods or clean in self._props:
            return clean
        return None

    def enum(self, name: str) -> Optional[Dict[str, int]]:
        return self._enums.get(name)

    def list_interfaces(self) -> List[str]:
        ifs = set(self._methods.keys()) | set(self._props.keys())
        return sorted(ifs)

    def list_methods(self, iface: str) -> List[str]:
        return sorted(self._methods.get(iface, {}).keys())

    def list_properties(self, iface: str) -> List[str]:
        return sorted(self._props.get(iface, {}).keys())

    def signature(self, iface: str, name: str) -> str:
        rt = self.ret_type(iface, name) or "?"
        params = self._params.get(iface, {}).get(name, [])
        ps = ", ".join(f"{p['name']}: {p['type']}" for p in params)
        return f"{rt} {iface}::{name}({ps})"

    def invoke(self, oleobj, iface: str, name: str, *args):
        import pythoncom
        mid = self.memid(iface, name)
        if mid is None:
            raise DaoError(f"memid not found: {iface}.{name}")
        return oleobj.Invoke(
            mid, 0,
            pythoncom.DISPATCH_METHOD | pythoncom.DISPATCH_PROPERTYGET,
            True, *args)

    def putref(self, oleobj, iface: str, name: str, ref_obj):
        import pythoncom
        mid = self.memid(iface, name)
        if mid is None:
            raise DaoError(f"memid not found: {iface}.{name}")
        raw = _ole_of(ref_obj)
        oleobj.Invoke(mid, 0, pythoncom.DISPATCH_PROPERTYPUTREF, False, raw)

    def stats(self) -> Dict[str, Any]:
        return {
            "loaded": self._loaded,
            "tlb_paths": self._tlb_paths,
            "interfaces": len(self.list_interfaces()),
            "methods_total": sum(len(v) for v in self._methods.values()),
            "properties_total": sum(len(v) for v in self._props.values()),
            "enums": len(self._enums),
            "href_cache": len(self._href_cache),
            "inherits_edges": sum(len(v) for v in self._inherits.values()),
        }


# ════════════════════════════════════════════════════════════════════════
# ② DaoDispatch — 包裹 oleobj+iface, __getattr__ 自动 memid Invoke
# ════════════════════════════════════════════════════════════════════════
class DaoDispatch:
    """任意 COM 对象的道直连代理.

    使用:
        asm = DaoDispatch(asm_oleobj, "IAssemblyDoc", mt)
        n = asm.GetMateCount()              # 延迟调用: 返回 int
        feat = asm.FirstFeature()           # 返回 DaoDispatch(IFeature)
        name = feat.Name()                  # 链式直达 str

    规则:
      1. 属性 (仅在 _props, 无参数) → 立即 Invoke 返标量
      2. 方法或有参属性 → 返可调用闭包, 调用时 Invoke
      3. 结果若 IDispatch 且返回类型是接口 → 包 DaoDispatch
    """

    __slots__ = ("_ole", "_iface", "_mt", "_dao")

    def __init__(self, com_obj, iface: str, mt: MemidTable,
                 dao: Optional["Dao"] = None):
        self._ole = _ole_of(com_obj) if com_obj is not None else None
        self._iface = iface
        self._mt = mt
        self._dao = dao

    def __repr__(self):
        return f"<DaoDispatch {self._iface} @ 0x{id(self._ole):x}>"

    def __bool__(self):
        return self._ole is not None

    def __eq__(self, other):
        return isinstance(other, DaoDispatch) and self._ole is other._ole

    def __hash__(self):
        return id(self._ole) if self._ole else 0

    @property
    def ole(self):
        return self._ole

    @property
    def iface(self) -> str:
        return self._iface

    def _wrap(self, result, method_name: str):
        if result is None:
            return None
        if not (hasattr(result, "Invoke") or hasattr(result, "QueryInterface")):
            return result
        nxt = self._mt.resolve_iface(self._iface, method_name)
        if nxt:
            return DaoDispatch(result, nxt, self._mt, self._dao)
        # 无推断 → 保持 raw (不 _dyn 包装 · 避免 pywin32 dynamic dispatch 污染)
        # 包成 DaoDispatch("IDispatch") · 用户可 .cast() 到具体接口
        return DaoDispatch(result, "IDispatch", self._mt, self._dao)

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        if self._ole is None:
            raise DaoError(f"{self._iface}.{name}: wrapped oleobj is None")
        mt = self._mt
        mid = mt.memid(self._iface, name)
        if mid is None:
            raise AttributeError(
                f"{self._iface}.{name}: memid not found in tlb "
                f"(including global search)")

        has_get = mt.is_getter(self._iface, name)
        getter_args = mt.getter_params(self._iface, name)
        method_args = mt.method_params(self._iface, name)
        which = mt.which_iface(self._iface, name) or self._iface
        is_method = name in mt._methods.get(which, {})

        import pythoncom
        # 标志位: method / property 分别用不同 flag (SW COM 对 PROPERTYGET 组合方法严格)
        if is_method and not has_get:
            flags = pythoncom.DISPATCH_METHOD
        elif has_get and not is_method:
            flags = pythoncom.DISPATCH_PROPERTYGET
        else:  # 两种都可 · 留 OR
            flags = pythoncom.DISPATCH_METHOD | pythoncom.DISPATCH_PROPERTYGET

        # 属性 GET 无参数 → 立即取值
        if has_get and not getter_args and not is_method:
            result = self._ole.Invoke(mid, 0, flags, True)
            return self._wrap(result, name)

        # 返回闭包 (method / indexed property / property w/ args)
        def _invoker(*args):
            result = self._ole.Invoke(mid, 0, flags, True, *args)
            return self._wrap(result, name)
        _invoker.__name__ = f"{self._iface}::{name}"
        return _invoker

    def set_ref(self, name: str, ref_obj):
        """PUTREF · 引用属性赋值 (例 IComponent2.Transform2)."""
        self._mt.putref(self._ole, self._iface, name, ref_obj)

    def chain(self, methods: List[str]):
        """invoke_chain 式调用."""
        import pythoncom
        current = self._ole
        cur_iface = self._iface
        for m in methods:
            mid = self._mt.memid(cur_iface, m)
            if mid is None:
                raise DaoError(f"chain: {cur_iface}.{m} not found")
            result = current.Invoke(
                mid, 0,
                pythoncom.DISPATCH_METHOD | pythoncom.DISPATCH_PROPERTYGET,
                True)
            nxt = self._mt.resolve_iface(cur_iface, m)
            if nxt and result is not None:
                current = _ole_of(result)
                cur_iface = nxt
            else:
                return result
        return DaoDispatch(current, cur_iface, self._mt, self._dao)

    def cast(self, iface: str) -> "DaoDispatch":
        return DaoDispatch(self._ole, iface, self._mt, self._dao)


# ════════════════════════════════════════════════════════════════════════
# ③ Dao — 单例 · 连接 · 绑定
# ════════════════════════════════════════════════════════════════════════
class Dao:
    _instance: Optional["Dao"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_once()
        return cls._instance

    def _init_once(self):
        self.mt = MemidTable()
        self._sw_raw = None
        self._doc_raw = None
        self.sw: Optional[DaoDispatch] = None
        self.doc: Optional[DaoDispatch] = None
        self.asm: Optional[DaoDispatch] = None
        self.part: Optional[DaoDispatch] = None
        self.drw: Optional[DaoDispatch] = None
        self.ext: Optional[DaoDispatch] = None
        self.sel: Optional[DaoDispatch] = None
        self.fm: Optional[DaoDispatch] = None
        self.sm: Optional[DaoDispatch] = None
        self.math: Optional[DaoDispatch] = None
        self._connected = False
        self._comp_map_cache: Optional[Dict[str, DaoDispatch]] = None
        # facets lazy
        self._facets: Dict[str, Any] = {}

    def connect(self, progid: str = "SldWorks.Application") -> "Dao":
        import pythoncom, win32com.client
        pythoncom.CoInitialize()
        try:
            app = win32com.client.GetActiveObject(progid)
        except Exception as e:
            raise DaoError(f"无活体 SW ({progid}): {e}. "
                           f"可试 connect_or_launch() 启动并连接.")
        return self._bind(app)

    def connect_or_launch(self, progid: str = "SldWorks.Application",
                          visible: bool = True,
                          timeout_s: float = 120.0) -> "Dao":
        import pythoncom, win32com.client
        pythoncom.CoInitialize()
        try:
            app = win32com.client.GetActiveObject(progid)
            return self._bind(app)
        except Exception:
            pass
        sw_exe = self._find_sw_exe()
        if not sw_exe:
            raise DaoError("SW exe 未找到")
        import subprocess
        subprocess.Popen([sw_exe], shell=False)
        deadline = time.time() + timeout_s
        last_err: Optional[Exception] = None
        while time.time() < deadline:
            try:
                app = win32com.client.GetActiveObject(progid)
                self._bind(app)
                if visible and self.sw:
                    try:
                        self.sw.Visible = True  # type: ignore
                    except Exception:
                        pass
                return self
            except Exception as e:
                last_err = e
                time.sleep(2.0)
        raise DaoError(f"SW 启动超时: {last_err}")

    def _find_sw_exe(self) -> Optional[str]:
        for p in [
            r"D:\Program Files\SOLIDWORKS Corp23\SOLIDWORKS\SLDWORKS.exe",
            r"D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\SLDWORKS.exe",
            r"C:\Program Files\SOLIDWORKS Corp23\SOLIDWORKS\SLDWORKS.exe",
            r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\SLDWORKS.exe",
        ]:
            if os.path.exists(p):
                return p
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                               r"SOFTWARE\SolidWorks\SOLIDWORKS")
            v, _ = winreg.QueryValueEx(k, "SolidWorksExePath")
            winreg.CloseKey(k)
            if os.path.exists(v):
                return v
        except Exception:
            pass
        return None

    def _bind(self, app) -> "Dao":
        if not self.mt.loaded:
            self.mt.load()
        if not self.mt.loaded:
            raise DaoError("sldworks.tlb 载入失败 · SW 未安装?")
        self._sw_raw = _ole_of(app)
        self.sw = DaoDispatch(self._sw_raw, "ISldWorks", self.mt, self)

        try:
            doc = self.sw.ActiveDoc  # type: ignore
        except Exception:
            doc = None
        if doc:
            self._bind_doc(doc)
        self._connected = True
        return self

    def _bind_doc(self, doc):
        if isinstance(doc, DaoDispatch):
            self._doc_raw = doc.ole
            self.doc = doc
        else:
            self._doc_raw = _ole_of(doc)
            self.doc = DaoDispatch(self._doc_raw, "IModelDoc2", self.mt, self)
        try:
            dtype = int(self.doc.GetType())  # type: ignore
        except Exception:
            dtype = None
        self.asm = self.part = self.drw = None
        if dtype == DOC.ASSEMBLY:
            self.asm = DaoDispatch(self._doc_raw, "IAssemblyDoc", self.mt, self)
        elif dtype == DOC.PART:
            self.part = DaoDispatch(self._doc_raw, "IPartDoc", self.mt, self)
        elif dtype == DOC.DRAWING:
            self.drw = DaoDispatch(self._doc_raw, "IDrawingDoc", self.mt, self)

        self.ext = _safe(lambda: self.doc.Extension)  # type: ignore
        self.sel = _safe(lambda: self.doc.SelectionManager)  # type: ignore
        self.fm = _safe(lambda: self.doc.FeatureManager)  # type: ignore
        self.sm = _safe(lambda: self.doc.SketchManager)  # type: ignore
        self.math = _safe(lambda: self.sw.GetMathUtility())  # type: ignore
        self._comp_map_cache = None

    def rebind_active(self) -> "Dao":
        if not self._connected:
            raise DaoError("未连接")
        try:
            doc = self.sw.ActiveDoc  # type: ignore
        except Exception:
            doc = None
        if doc:
            self._bind_doc(doc)
        return self

    @property
    def connected(self) -> bool:
        return self._connected

    def build_comp_map(self, force: bool = False) -> Dict[str, DaoDispatch]:
        """{comp_name: DaoDispatch(IComponent2)} · 缓存."""
        if self._comp_map_cache is not None and not force:
            return self._comp_map_cache
        if self.asm is None:
            raise DaoError("当前非装配")
        mapping: Dict[str, DaoDispatch] = {}
        feat_raw = self.asm.FirstFeature()  # type: ignore
        n = 0
        while feat_raw and n < 5000:
            n += 1
            # 强制 cast 为 IFeature · FirstFeature 返 IDispatch*
            feat = (feat_raw.cast("IFeature")
                    if isinstance(feat_raw, DaoDispatch) else feat_raw)
            try:
                tn = feat.GetTypeName2()
            except Exception:
                tn = ""
            if tn == "Reference":
                try:
                    comp_raw = feat.GetSpecificFeature2()
                    if comp_raw:
                        comp = (comp_raw.cast("IComponent2")
                                if isinstance(comp_raw, DaoDispatch)
                                else DaoDispatch(_ole_of(comp_raw),
                                                 "IComponent2", self.mt, self))
                        # Name2 是 IComponent2 的 property (完整路径 name)
                        name = _safe(lambda: str(comp.Name2))  # type: ignore
                        if callable(name):
                            name = _safe(lambda: str(name()))
                        if name:
                            mapping[name] = comp
                except Exception:
                    pass
            try:
                feat_raw = feat_raw.GetNextFeature()  # type: ignore
            except Exception:
                break
        self._comp_map_cache = mapping
        return mapping

    # facets (lazy import avoids circular)
    @property
    def mate(self):
        if "mate" not in self._facets:
            self._facets["mate"] = _MateFacet(self)
        return self._facets["mate"]

    @property
    def transform(self):
        if "transform" not in self._facets:
            self._facets["transform"] = _TransformFacet(self)
        return self._facets["transform"]

    @property
    def select(self):
        if "select" not in self._facets:
            self._facets["select"] = _SelectFacet(self)
        return self._facets["select"]

    @property
    def face(self):
        if "face" not in self._facets:
            self._facets["face"] = _FaceFacet(self)
        return self._facets["face"]

    @property
    def comp(self):
        if "comp" not in self._facets:
            self._facets["comp"] = _CompFacet(self)
        return self._facets["comp"]

    def rebuild(self, force: bool = False) -> bool:
        if self.asm is not None:
            try:
                if force:
                    return bool(self.asm.ForceRebuild3(False))  # type: ignore
                return bool(self.asm.EditRebuild3())  # type: ignore
            except Exception:
                return False
        try:
            return bool(self.doc.EditRebuild3())  # type: ignore
        except Exception:
            return False

    def save(self) -> Dict[str, Any]:
        if self.doc is None:
            return {"ok": False, "error": "no_doc"}
        errs = _byref_int()
        warns = _byref_int()
        try:
            ok = self.doc.Save3(1, errs, warns)  # type: ignore
            return {"ok": bool(ok),
                    "errors": _safe(lambda: errs.value, -1),
                    "warnings": _safe(lambda: warns.value, -1)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def summary(self) -> Dict[str, Any]:
        s: Dict[str, Any] = {
            "connected": self._connected,
            "sw_revision": (_safe(lambda: str(self.sw.RevisionNumber()))
                            if self.sw else None),
            "tlb_stats": self.mt.stats(),
        }
        if self.doc is not None:
            s["doc_title"] = _safe(lambda: str(self.doc.GetTitle()))  # type: ignore
            s["doc_path"] = _safe(lambda: str(self.doc.GetPathName()))  # type: ignore
            s["doc_type"] = DOC.NAME.get(
                _safe(lambda: int(self.doc.GetType()), 0), "?")  # type: ignore
        if self.asm is not None:
            s["component_count"] = _safe(
                lambda: int(self.asm.GetComponentCount(False)), -1)  # type: ignore
            s["mate_count"] = _safe(lambda: len(self.mate.list_all()), -1)
        return s


# ════════════════════════════════════════════════════════════════════════
# ④ 域便捷 · _MateFacet / _TransformFacet / _SelectFacet / _FaceFacet / _CompFacet
#   (实现在 道_直连_底层_facets.py · 本文件 _lazy 导入以保持清洁)
# ════════════════════════════════════════════════════════════════════════
try:
    from 道_直连_底层_facets import (
        _MateFacet, _TransformFacet, _SelectFacet,
        _FaceFacet, _CompFacet,
    )
except Exception:
    # 占位 · 使 Dao 可 import 不崩 (facets 未到时域便捷失效, 核心仍用)
    class _StubFacet:
        def __init__(self, dao):
            self.dao = dao

        def __getattr__(self, name):
            raise DaoError(
                f"facets 未加载: {name} · "
                f"确认 道_直连_底层_facets.py 存在")

    _MateFacet = _TransformFacet = _SelectFacet = _FaceFacet = _CompFacet = _StubFacet


# ════════════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════════════
def _cli():
    import argparse
    ap = argparse.ArgumentParser(
        description="道直连器 · 无中间层 · 直达 SolidWorks 底层")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("connect", help="连接 + 打印摘要")
    sub.add_parser("probe", help="探活当前文档")
    sub.add_parser("interfaces", help="列接口 (memid 表)")
    p_call = sub.add_parser("call", help="任意调用")
    p_call.add_argument("iface")
    p_call.add_argument("method")
    p_call.add_argument("args", nargs="*")
    p_sig = sub.add_parser("sig", help="查方法签名")
    p_sig.add_argument("iface")
    p_sig.add_argument("method", nargs="?")
    args = ap.parse_args()

    if not args.cmd:
        ap.print_help()
        return 0

    if args.cmd == "interfaces":
        mt = MemidTable()
        mt.load()
        print(f"tlb paths: {mt._tlb_paths}")
        print(f"总接口: {len(mt.list_interfaces())}")
        print(f"top 20 by method count:")
        tops = sorted(mt._methods.items(), key=lambda x: -len(x[1]))[:20]
        for nm, ms in tops:
            print(f"  {nm:30s}  methods={len(ms):4d}  props={len(mt._props.get(nm,{})):3d}")
        return 0

    if args.cmd == "sig":
        mt = MemidTable()
        mt.load()
        if args.method:
            print(mt.signature(args.iface, args.method))
        else:
            for m in mt.list_methods(args.iface):
                print(mt.signature(args.iface, m))
        return 0

    dao = Dao().connect()
    if args.cmd == "connect":
        import json
        print(json.dumps(dao.summary(), ensure_ascii=False, indent=2,
                         default=str))
    elif args.cmd == "probe":
        import json
        s = dao.summary()
        if dao.asm:
            try:
                cmap = dao.build_comp_map()
                s["components"] = list(cmap.keys())[:30]
                s["n_components"] = len(cmap)
            except Exception as e:
                s["comp_error"] = str(e)
        print(json.dumps(s, ensure_ascii=False, indent=2, default=str))
    elif args.cmd == "call":
        # 需要一个 oleobj · 取活文档或 sw
        target_map = {
            "ISldWorks": dao.sw, "IModelDoc2": dao.doc,
            "IAssemblyDoc": dao.asm, "IPartDoc": dao.part,
            "IDrawingDoc": dao.drw, "IModelDocExtension": dao.ext,
            "ISelectionMgr": dao.sel, "IFeatureManager": dao.fm,
            "ISketchManager": dao.sm, "IMathUtility": dao.math,
        }
        obj = target_map.get(args.iface)
        if obj is None:
            print(f"未知接口 target: {args.iface}")
            return 1
        fn = getattr(obj, args.method)
        coerced = []
        for a in args.args:
            if a.lower() in ("true", "false"):
                coerced.append(a.lower() == "true")
            else:
                try:
                    coerced.append(int(a))
                except ValueError:
                    try:
                        coerced.append(float(a))
                    except ValueError:
                        coerced.append(a)
        result = fn(*coerced) if callable(fn) else fn
        print(result)
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
