#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
道_本源_逆向万法.py — 反者道之动 · 大曰逝逝曰远远曰反 · 万物复归于始
═══════════════════════════════════════════════════════════════════════

从SolidWorks反向出发推演万法。复用一切而非重构。守正而非创新。道法自然。

    "反者道之动，弱者道之用。天下万物生于有，有生于无。"

Layer: L12 · 逆向万法 (Reverse All Methods)
依赖: dao_solidworks (L0-L9), dao_sw_live (L11)

核心能力:
  ① 类型库逆向 — ITypeLib 枚举一切接口、方法、属性、参数签名
  ② 活体深探  — 活动文档完整状态快照 (特征树/组件/配合/B-Rep/变换/属性)
  ③ 装配操控  — 基于 SelectByRay 精确面选 + AddMate5 多路回退
  ④ B-Rep几何  — 装配上下文面枚举 (绕 ISurface 动态分派限制 · 用启发式分类)
  ⑤ 万法映射  — 输出完整 JSON 能力报告

用法:
    # 作为模块:
    from 道_本源_逆向万法 import SWReverse
    rev = SWReverse()
    rev.connect()
    report = rev.full_probe()

    # CLI:
    python 道_本源_逆向万法.py probe      # 完整逆向探测
    python 道_本源_逆向万法.py typelib     # 类型库枚举
    python 道_本源_逆向万法.py components  # 组件状态
    python 道_本源_逆向万法.py mates       # 配合详情
    python 道_本源_逆向万法.py brep        # B-Rep 几何
    python 道_本源_逆向万法.py api-map     # API 能力映射
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import traceback
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

# ── 路径引导 ──────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_DAO_ROOT = next(
    (p for p in Path(__file__).resolve().parents if (p / "_paths.py").is_file()),
    _HERE.parent,
)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

__version__ = "2.2.0"  # 内固其本 + MateForge (face-direct Mate, 无射线)
__all__ = [
    "SWReverse", "TypeLibInfo", "MemidRegistry", "DocSnapshot",
    "ComponentInfo", "MateInfo", "FaceInfo", "BRepScan",
    "CylinderFace", "PlaneFace", "CompGeometry",
]

# ── 日志 ──────────────────────────────────────────────────────────────
_LOG: List[str] = []


def _log(msg: str):
    print(msg)
    _LOG.append(msg)


# ════════════════════════════════════════════════════════════════════════
# COM 工具 (复用 dao_solidworks 的模式)
# ════════════════════════════════════════════════════════════════════════
def _dyn(obj):
    """包装为纯动态 IDispatch, 绕 gencache 污染."""
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


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def _nothing():
    import win32com.client
    import pythoncom
    return win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)


def _byref_int(val=0):
    import win32com.client
    import pythoncom
    return win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, val)


# ════════════════════════════════════════════════════════════════════════
# TYPEDESC 解析 — 庖丁解牛融合 · 类型名解析能力
# ════════════════════════════════════════════════════════════════════════
# "庖丁为文惠君解牛 … 依乎天理, 批大郤, 导大窾, 因其固然."
# 从 道_庖丁解牛 继承 TYPEDESC 解析, 令 MemidRegistry 知晓返回类型,
# 使 invoke_chain 能自动推断中间接口 — 道法自然, 无为而无不为.
try:
    from 道_庖丁解牛 import (
        _resolve_typedesc, _VT_NAMES, _HREF_NAME_CACHE,
        _scan_registry_typelibs,
    )
except ImportError:
    _scan_registry_typelibs = None
    _VT_NAMES = {
        0: "VT_EMPTY", 2: "short", 3: "long", 4: "float", 5: "double",
        6: "CY", 7: "DATE", 8: "BSTR", 9: "IDispatch*", 10: "SCODE",
        11: "bool", 12: "VARIANT", 13: "IUnknown*", 16: "i1", 17: "ui1",
        18: "ui2", 19: "ui4", 20: "i8", 21: "ui8", 22: "int", 23: "uint",
        24: "void", 25: "HRESULT", 26: "PTR", 27: "SAFEARRAY", 28: "CARRAY",
        29: "USERDEFINED", 36: "RECORD",
    }
    _HREF_NAME_CACHE: Dict[int, str] = {}

    def _resolve_typedesc(ti, td) -> str:
        """递归解析 TYPEDESC 为人类可读类型字符串 (内联回退版)."""
        if td is None:
            return "?"
        try:
            if isinstance(td, int):
                return _VT_NAMES.get(td, f"vt_{td}")
            if isinstance(td, tuple):
                if (len(td) == 3 and isinstance(td[1], int)
                        and (td[2] is None
                             or isinstance(td[2], (int, float, str)))):
                    return _resolve_typedesc(ti, td[0])
                vt = td[0] if len(td) > 0 else 0
                if isinstance(vt, tuple):
                    return _resolve_typedesc(ti, vt)
                if vt == 26 and len(td) > 1:  # VT_PTR
                    inner = _resolve_typedesc(ti, td[1])
                    return inner if inner.startswith("vt_") else f"{inner}*"
                if vt == 29 and len(td) > 1:  # VT_USERDEFINED
                    href = td[1]
                    if href in _HREF_NAME_CACHE:
                        return _HREF_NAME_CACHE[href]
                    try:
                        ref_ti = ti.GetRefTypeInfo(href)
                        ref_name = ref_ti.GetDocumentation(-1)[0]
                        _HREF_NAME_CACHE[href] = ref_name
                        return ref_name
                    except Exception:
                        return f"href:{href}"
                if vt == 27 and len(td) > 1:  # VT_SAFEARRAY
                    return f"SAFEARRAY({_resolve_typedesc(ti, td[1])})"
                return _VT_NAMES.get(vt, f"vt_{vt}")
            return str(td)
        except Exception:
            return f"?({td})"


def _warm_href_cache_from_tlib(tlib):
    """预热 href→name 全局缓存 · 庖丁解牛之法.

    遍历所有类型的 impltype 引用, 填充 _HREF_NAME_CACHE,
    使 _resolve_typedesc 遇到 VT_USERDEFINED 时能直接查缓存.
    """
    count = tlib.GetTypeInfoCount()
    for i in range(count):
        try:
            ti = tlib.GetTypeInfo(i)
            ta = ti.GetTypeAttr()
            for impl_idx in range(ta.cImplTypes):
                try:
                    href = ti.GetRefTypeOfImplType(impl_idx)
                    if href not in _HREF_NAME_CACHE:
                        ref_ti = ti.GetRefTypeInfo(href)
                        _HREF_NAME_CACHE[href] = ref_ti.GetDocumentation(-1)[0]
                except Exception:
                    continue
        except Exception:
            continue


# ════════════════════════════════════════════════════════════════════════
# ⓪ MemidRegistry — 庖丁之刀 · memid 直接 Invoke
# ════════════════════════════════════════════════════════════════════════
# SolidWorks COM 对象多数不暴露 ITypeInfo, IDispatch 名称解析不完整,
# 但 sldworks.tlb (1001 types) 包含所有接口的完整 memid.
# 直接用 memid 通过 oleobj.Invoke() 调用, 绕过一切限制.
# "道冲，而用之或不盈。渊兮，似万物之宗。"

class MemidRegistry:
    """从 sldworks.tlb 加载 memid → 直接 Invoke 一切方法."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._loaded = False
        return cls._instance

    def __init__(self):
        if not self._loaded:
            self._ifaces: Dict[str, Dict[str, int]] = {}
            self._props: Dict[str, Dict[str, int]] = {}
            self._ret_types: Dict[str, Dict[str, str]] = {}  # iface→{method→返回类型}
            self._tlb_path: Optional[str] = None
            self._tlb_name: str = ""
            self._tlb_count: int = 0

    def load(self, sw_exe: Optional[str] = None) -> bool:
        """加载 sldworks.tlb, 构建 memid 表."""
        if self._loaded:
            return True
        import pythoncom
        # 定位 sldworks.tlb
        tlb_path = None
        if sw_exe:
            d = os.path.dirname(sw_exe)
            p = os.path.join(d, "sldworks.tlb")
            if os.path.exists(p):
                tlb_path = p
        if not tlb_path:
            for candidate in [
                r"D:\Program Files\SOLIDWORKS Corp23\SOLIDWORKS\sldworks.tlb",
                r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb",
                r"D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb",
            ]:
                if os.path.exists(candidate):
                    tlb_path = candidate
                    break
        if not tlb_path:
            # 注册表搜索
            try:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                     r"SOFTWARE\SolidWorks\SOLIDWORKS")
                path, _ = winreg.QueryValueEx(key, "SolidWorksExePath")
                winreg.CloseKey(key)
                p = os.path.join(os.path.dirname(path), "sldworks.tlb")
                if os.path.exists(p):
                    tlb_path = p
            except Exception:
                pass
        if not tlb_path:
            _log("  MemidRegistry: sldworks.tlb 未找到")
            return False

        try:
            tlib = pythoncom.LoadTypeLib(tlb_path)
            self._tlb_path = tlb_path
            self._tlb_name = tlib.GetDocumentation(-1)[0]
            self._tlb_count = tlib.GetTypeInfoCount()

            # 预热 href→name 缓存 (庖丁解牛之法)
            _warm_href_cache_from_tlib(tlib)

            for i in range(self._tlb_count):
                try:
                    k = tlib.GetTypeInfoType(i)
                    if k not in (3, 4):  # interface / dispatch only
                        continue
                    tn = tlib.GetDocumentation(i)[0]
                    ti = tlib.GetTypeInfo(i)
                    ta = ti.GetTypeAttr()
                    methods = {}
                    props = {}
                    ret_types = {}
                    for j in range(ta.cFuncs):
                        try:
                            fd = ti.GetFuncDesc(j)
                            fname = ti.GetNames(fd.memid)[0]
                            if fd.invkind == 1:
                                methods[fname] = fd.memid
                                try:
                                    ret_types[fname] = _resolve_typedesc(
                                        ti, fd.rettype)
                                except Exception:
                                    pass
                            elif fd.invkind in (2, 4):
                                props[fname] = fd.memid
                                if fd.invkind == 2:  # PROPERTYGET
                                    try:
                                        ret_types[fname] = _resolve_typedesc(
                                            ti, fd.rettype)
                                    except Exception:
                                        pass
                        except Exception:
                            continue
                    self._ifaces[tn] = methods
                    self._props[tn] = props
                    if ret_types:
                        self._ret_types[tn] = ret_types
                except Exception:
                    continue

            self._loaded = True
            _log(f"  MemidRegistry: {self._tlb_name} ({self._tlb_count} types, "
                 f"{len(self._ifaces)} interfaces)")
            return True
        except Exception as e:
            _log(f"  MemidRegistry: 加载失败 {e}")
            return False

    @property
    def loaded(self) -> bool:
        return self._loaded

    def memid(self, iface: str, method: str) -> Optional[int]:
        """查 memid. 先查方法表, 再查属性表."""
        m = self._ifaces.get(iface, {}).get(method)
        if m is not None:
            return m
        return self._props.get(iface, {}).get(method)

    def invoke(self, oleobj, iface: str, method: str, *args):
        """通过 memid 调用方法/读属性. 庖丁之刀."""
        import pythoncom
        mid = self.memid(iface, method)
        if mid is None:
            raise AttributeError(f"{iface}.{method} memid not found")
        return oleobj.Invoke(
            mid, 0,
            pythoncom.DISPATCH_METHOD | pythoncom.DISPATCH_PROPERTYGET,
            True, *args
        )

    def invoke_obj(self, com_obj, iface: str, method: str, *args):
        """对已包装的 COM 对象调用. 自动取 _oleobj_."""
        raw = com_obj._oleobj_ if hasattr(com_obj, "_oleobj_") else com_obj
        result = self.invoke(raw, iface, method, *args)
        if result is not None and hasattr(result, "QueryInterface"):
            return _dyn(result)
        return result

    def list_methods(self, iface: str) -> List[str]:
        return list(self._ifaces.get(iface, {}).keys())

    def list_properties(self, iface: str) -> List[str]:
        return list(self._props.get(iface, {}).keys())

    def list_interfaces(self) -> List[str]:
        return list(self._ifaces.keys())

    def return_type(self, iface: str, method: str) -> Optional[str]:
        """查询方法/属性的返回类型 (庖丁解牛融合)."""
        return self._ret_types.get(iface, {}).get(method)

    def resolve_return_iface(self, iface: str, method: str) -> Optional[str]:
        """推断方法返回的接口名. 返回 None 若为基础类型."""
        rt = self.return_type(iface, method)
        if not rt:
            return None
        clean = rt.rstrip("*")
        return clean if clean in self._ifaces else None

    def invoke_chain(self, oleobj, iface: str, method_chain: List[str]):
        """链式调用 · 自动推断中间接口 · 庖丁之刀流转.

        例: invoke_chain(face_ole, "IFace2", ["GetSurface", "Identity"])
        等价: IFace2.GetSurface() → 推断 ISurface → ISurface.Identity()
        "善行无辙迹, 善言无瑕谪, 善数不用筹策."
        """
        import pythoncom
        current = oleobj
        current_iface = iface
        for method in method_chain:
            mid = self.memid(current_iface, method)
            if mid is None:
                raise AttributeError(
                    f"{current_iface}.{method} memid not found")
            result = current.Invoke(
                mid, 0,
                pythoncom.DISPATCH_METHOD | pythoncom.DISPATCH_PROPERTYGET,
                True)
            # 推断下一个接口 (有即用 · 无即止)
            next_iface = self.resolve_return_iface(current_iface, method)
            if next_iface:
                current_iface = next_iface
            current = result
        return current

    def stats(self) -> Dict[str, Any]:
        return {
            "tlb_path": self._tlb_path,
            "tlb_name": self._tlb_name,
            "total_types": self._tlb_count,
            "interfaces_loaded": len(self._ifaces),
            "typed_interfaces": len(self._ret_types),
            "href_cache_size": len(_HREF_NAME_CACHE),
            "top_interfaces": {
                k: len(v) for k, v in sorted(
                    self._ifaces.items(),
                    key=lambda x: -len(x[1])
                )[:20]
            },
        }


# ════════════════════════════════════════════════════════════════════════
# ① 类型库逆向 — ITypeLib 枚举所有接口
# ════════════════════════════════════════════════════════════════════════
class TypeLibInfo:
    """SolidWorks 类型库逆向. 通过 COM ITypeLib 枚举一切接口."""

    def __init__(self):
        self.interfaces: Dict[str, Dict[str, Any]] = {}
        self.enums: Dict[str, Dict[str, int]] = {}
        self.coclasses: List[str] = []

    def probe(self, progid: str = "SldWorks.Application") -> Dict[str, Any]:
        """从 ProgID 加载类型库并枚举所有接口."""
        import pythoncom
        _log("═══ 类型库逆向 · ITypeLib ═══")

        result = {"interfaces": {}, "enums": {}, "coclasses": [], "error": None}

        try:
            # 路 1: 从活体 COM 对象拿 ITypeInfo → ITypeLib
            try:
                import win32com.client
                app = win32com.client.GetActiveObject(progid)
                disp = app._oleobj_
                type_info = disp.GetTypeInfo(0)
                type_lib, idx = type_info.GetContainingTypeLib()
                _log(f"  TypeLib: {type_lib.GetDocumentation(-1)[0]}")
                _log(f"  TypeLib count: {type_lib.GetTypeInfoCount()}")
                result = self._enumerate_typelib(type_lib)
                self._store(result)
                return result
            except Exception as e1:
                _log(f"  路1 (活体 ITypeInfo) 失败: {e1}")

            # 路 2: 注册表扫描 → LoadRegTypeLib → 合并所有 SW TypeLib
            merged = {"interfaces": {}, "enums": {}, "coclasses": [],
                      "sources": [], "via": "merged"}
            try:
                reg_info = self._probe_from_registry()
                sw_libs = reg_info.get("sw_typelibs", [])
                for lib_info in sw_libs:
                    try:
                        guid = lib_info["guid"]
                        ver_str = lib_info["ver"]
                        parts = ver_str.split(".")
                        major = int(parts[0], 16) if parts else 0
                        minor = int(parts[1], 16) if len(parts) > 1 else 0
                        tlib = pythoncom.LoadRegTypeLib(guid, major, minor, 0)
                        name = tlib.GetDocumentation(-1)[0]
                        n_types = tlib.GetTypeInfoCount()
                        _log(f"  路2 扫描: {name} ({n_types} types)")
                        r = self._enumerate_typelib(tlib)
                        ni = len(r.get("interfaces", {}))
                        ne = len(r.get("enums", {}))
                        if ni > 0 or ne > 0:
                            merged["interfaces"].update(r.get("interfaces", {}))
                            merged["enums"].update(r.get("enums", {}))
                            merged["coclasses"].extend(r.get("coclasses", []))
                            merged["sources"].append(
                                {"name": name, "guid": guid,
                                 "interfaces": ni, "enums": ne})
                    except Exception:
                        continue
            except Exception as e2:
                _log(f"  路2 (LoadRegTypeLib) 失败: {e2}")

            # 路 3: 从 SW 安装目录找 sldworks.tlb (主 API)
            try:
                import dao_solidworks as _sw
                info = _sw.sw_info()
                if info.installdir:
                    import glob
                    tlb_files = glob.glob(
                        os.path.join(info.installdir, "**", "*.tlb"),
                        recursive=True
                    )
                    for tlb_path in tlb_files:
                        try:
                            tlib = pythoncom.LoadTypeLib(tlb_path)
                            name = tlib.GetDocumentation(-1)[0]
                            n_types = tlib.GetTypeInfoCount()
                            _log(f"  路3 扫描: {name} ({n_types} types) [{tlb_path}]")
                            r = self._enumerate_typelib(tlib)
                            ni = len(r.get("interfaces", {}))
                            ne = len(r.get("enums", {}))
                            if ni > 0 or ne > 0:
                                merged["interfaces"].update(r.get("interfaces", {}))
                                merged["enums"].update(r.get("enums", {}))
                                merged["coclasses"].extend(r.get("coclasses", []))
                                merged["sources"].append(
                                    {"name": name, "file": tlb_path,
                                     "interfaces": ni, "enums": ne})
                        except Exception:
                            continue
            except Exception as e3:
                _log(f"  路3 (文件扫描) 失败: {e3}")

            # 合并结果
            if merged["interfaces"] or merged["enums"]:
                result = merged
                _log(f"  合并: {len(merged['interfaces'])} interfaces, "
                     f"{len(merged['enums'])} enums, "
                     f"from {len(merged['sources'])} sources")
                self._store(result)
                return result

        except Exception as ex:
            result["error"] = str(ex)
            _log(f"  TypeLib 枚举失败: {ex}")

        self._store(result)
        return result

    def _store(self, result: Dict[str, Any]):
        self.interfaces = result.get("interfaces", {})
        self.enums = result.get("enums", {})
        self.coclasses = result.get("coclasses", [])

    def _enumerate_typelib(self, tlib) -> Dict[str, Any]:
        """枚举类型库中的所有类型.

        融合庖丁解牛的解析引擎:
          · 预热 _HREF_NAME_CACHE → 跨 TypeLib 引用可解析
          · _resolve_typedesc → 方法返回类型 + 参数类型完整解析
          · 继承链提取 → 接口关系图可构建
        "依乎天理, 批大郤, 导大窾, 因其固然。"
        """
        import pythoncom
        result = {"interfaces": {}, "enums": {}, "coclasses": []}
        count = tlib.GetTypeInfoCount()
        _log(f"  枚举 {count} 个类型定义...")

        # ── 预热 href 缓存 ──
        _warm_href_cache_from_tlib(tlib)

        for i in range(count):
            try:
                kind = tlib.GetTypeInfoType(i)
                name = tlib.GetDocumentation(i)[0]
            except Exception:
                continue

            # TKIND_ENUM = 0, TKIND_RECORD = 1, TKIND_MODULE = 2,
            # TKIND_INTERFACE = 3, TKIND_DISPATCH = 4, TKIND_COCLASS = 5
            if kind == 0:  # ENUM
                try:
                    ti = tlib.GetTypeInfo(i)
                    ta = ti.GetTypeAttr()
                    enum_vals = {}
                    for j in range(ta.cVars):
                        vd = ti.GetVarDesc(j)
                        vname = ti.GetNames(vd.memid)[0]
                        enum_vals[vname] = vd.value
                    result["enums"][name] = enum_vals
                except Exception:
                    pass

            elif kind in (3, 4):  # INTERFACE / DISPATCH
                try:
                    ti = tlib.GetTypeInfo(i)
                    ta = ti.GetTypeAttr()
                    iface = {"methods": {}, "properties": {}, "kind": kind,
                             "inherited_from": []}

                    # ── 继承链 ──
                    for impl_idx in range(ta.cImplTypes):
                        try:
                            href = ti.GetRefTypeOfImplType(impl_idx)
                            ref_ti = ti.GetRefTypeInfo(href)
                            ref_name = ref_ti.GetDocumentation(-1)[0]
                            iface["inherited_from"].append(ref_name)
                            _HREF_NAME_CACHE[href] = ref_name
                        except Exception:
                            continue

                    # ── 方法 & 属性 ──
                    for j in range(ta.cFuncs):
                        try:
                            fd = ti.GetFuncDesc(j)
                            fname = ti.GetNames(fd.memid)[0]
                            all_names = ti.GetNames(fd.memid)
                            param_names = list(all_names[1:]) if len(all_names) > 1 else []
                            invkind = fd.invkind

                            # 返回类型解析
                            ret_type = "void"
                            try:
                                ret_type = _resolve_typedesc(ti, fd.rettype)
                            except Exception:
                                pass

                            # 参数类型解析
                            param_types = []
                            if fd.args:
                                for pi in range(len(fd.args)):
                                    try:
                                        arg_td = fd.args[pi]
                                        if isinstance(arg_td, tuple) and len(arg_td) >= 1:
                                            pt = _resolve_typedesc(ti, arg_td[0] if isinstance(arg_td[0], (tuple, int)) else arg_td)
                                        else:
                                            pt = _resolve_typedesc(ti, arg_td)
                                        param_types.append(pt)
                                    except Exception:
                                        param_types.append("?")

                            # 构建带类型的参数列表
                            params_full = []
                            for pi in range(max(len(param_names), len(param_types))):
                                pn = param_names[pi] if pi < len(param_names) else f"p{pi}"
                                pt = param_types[pi] if pi < len(param_types) else None
                                entry = {"name": pn}
                                if pt:
                                    entry["type"] = pt
                                params_full.append(entry)

                            # INVOKE_FUNC=1, INVOKE_PROPERTYGET=2,
                            # INVOKE_PROPERTYPUT=4, INVOKE_PROPERTYPUTREF=8
                            if invkind == 1:
                                method_entry = {
                                    "params": [p["name"] for p in params_full],
                                    "n_params": len(param_names),
                                    "memid": fd.memid,
                                }
                                if ret_type != "void":
                                    method_entry["return_type"] = ret_type
                                if param_types:
                                    method_entry["param_types"] = param_types
                                iface["methods"][fname] = method_entry
                            elif invkind in (2, 4, 8):
                                prop_kind = {2: "get", 4: "put", 8: "putref"
                                             }.get(invkind, "?")
                                if fname not in iface["properties"]:
                                    iface["properties"][fname] = {}
                                prop_entry = {
                                    "params": [p["name"] for p in params_full],
                                    "memid": fd.memid,
                                }
                                if prop_kind == "get" and ret_type != "void":
                                    prop_entry["type"] = ret_type
                                iface["properties"][fname][prop_kind] = prop_entry
                        except Exception:
                            continue

                    result["interfaces"][name] = iface
                except Exception:
                    pass

            elif kind == 5:  # COCLASS
                result["coclasses"].append(name)

        _log(f"  接口: {len(result['interfaces'])}")
        _log(f"  枚举: {len(result['enums'])}")
        _log(f"  CoClass: {len(result['coclasses'])}")
        return result

    def _probe_from_registry(self) -> Dict[str, Any]:
        """从注册表扫描 SolidWorks TypeLib.

        融合庖丁解牛的全量关键字: solidworks/sldworks/swconst/cosmos/
        dimxpert/swutilities/swrouting/swpublished/cmotion/swfeedback/
        designchecker/macrobuilder — 覆盖全部卫星 TypeLib.
        """
        _log("  回退: 注册表扫描 TypeLib")
        result = {"interfaces": {}, "enums": {}, "coclasses": [], "via": "registry"}

        # 优先使用庖丁解牛的全量扫描
        if _scan_registry_typelibs is not None:
            try:
                libs = _scan_registry_typelibs()
                result["sw_typelibs"] = libs
                _log(f"  找到 {len(libs)} 个 SolidWorks TypeLib (庖丁解牛引擎)")
                for lib in libs[:8]:
                    _log(f"    {lib['desc']} ({lib['guid']} v{lib['ver']})")
                return result
            except Exception:
                pass

        # 回退: 本地扫描 (扩展关键字集)
        _SW_KEYWORDS = frozenset({
            "solidworks", "sldworks", "swconst", "cosmos", "dimxpert",
            "swutilities", "swrouting", "swpublished", "cmotion",
            "swfeedback", "designchecker", "macrobuilder",
        })
        try:
            import winreg
            key_path = r"SOFTWARE\Classes\TypeLib"
            hk = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
            i = 0
            sw_libs = []
            while True:
                try:
                    sub = winreg.EnumKey(hk, i)
                    i += 1
                    try:
                        sk = winreg.OpenKey(hk, sub)
                        j = 0
                        while True:
                            try:
                                ver = winreg.EnumKey(sk, j)
                                j += 1
                                vk = winreg.OpenKey(sk, ver)
                                desc, _ = winreg.QueryValueEx(vk, "")
                                if desc and any(kw in desc.lower()
                                                for kw in _SW_KEYWORDS):
                                    sw_libs.append({
                                        "guid": sub, "ver": ver,
                                        "desc": desc
                                    })
                                winreg.CloseKey(vk)
                            except OSError:
                                break
                        winreg.CloseKey(sk)
                    except OSError:
                        pass
                except OSError:
                    break
            winreg.CloseKey(hk)
            result["sw_typelibs"] = sw_libs
            _log(f"  找到 {len(sw_libs)} 个 SolidWorks TypeLib")
            for lib in sw_libs[:8]:
                _log(f"    {lib['desc']} ({lib['guid']} v{lib['ver']})")
        except Exception as ex:
            result["error"] = str(ex)
        return result

    def lookup_method(self, interface: str, method: str) -> Optional[Dict]:
        """查找某接口的某方法 — 返回参数签名."""
        iface = self.interfaces.get(interface, {})
        return (iface.get("methods", {}).get(method)
                or iface.get("properties", {}).get(method))

    def is_property(self, interface: str, name: str) -> bool:
        """判断某名称是属性还是方法."""
        iface = self.interfaces.get(interface, {})
        return name in iface.get("properties", {})

    def is_method(self, interface: str, name: str) -> bool:
        iface = self.interfaces.get(interface, {})
        return name in iface.get("methods", {})


# ════════════════════════════════════════════════════════════════════════
# ② 活体深探 — 文档完整状态快照
# ════════════════════════════════════════════════════════════════════════
class ComponentInfo:
    """组件完整信息."""
    def __init__(self):
        self.name: str = ""
        self.path: str = ""
        self.fixed: Optional[bool] = None
        self.suppressed: Optional[bool] = None
        self.visible: Optional[int] = None
        self.transform: Optional[List[float]] = None
        self.suppression_state: int = -1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name, "path": self.path,
            "fixed": self.fixed, "suppressed": self.suppressed,
            "visible": self.visible, "transform": self.transform,
            "suppression_state": self.suppression_state,
        }


class MateInfo:
    """配合完整信息."""
    def __init__(self):
        self.name: str = ""
        self.type_name: str = ""
        self.mate_type: int = -1
        self.alignment: int = -1
        self.error_status: Optional[int] = None
        self.entity_comps: List[str] = []
        self.suppressed: Optional[bool] = None

    TYPE_MAP = {
        0: "Coincident", 1: "Concentric", 2: "Perpendicular",
        3: "Parallel", 4: "Tangent", 5: "Distance", 6: "Angle",
        7: "Unknown7", 8: "Symmetric", 9: "CamFollower", 10: "Lock",
        11: "Gear", 12: "Rack", 13: "Screw", 14: "LinearCoupler",
        15: "Width", 16: "PathMate", 17: "UniversalJoint",
    }
    ALIGN_MAP = {0: "Aligned", 1: "Anti-Aligned", 2: "Closest"}
    ERROR_MAP = {0: "OK", 1: "OverDefined", 2: "Inconsistent", 3: "Redundant"}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type_name": self.type_name,
            "type_desc": self.TYPE_MAP.get(self.mate_type, f"?({self.mate_type})"),
            "alignment": self.ALIGN_MAP.get(self.alignment, "?"),
            "error": self.ERROR_MAP.get(self.error_status, f"err={self.error_status}"),
            "entities": self.entity_comps,
            "suppressed": self.suppressed,
        }


class FaceInfo:
    """面的几何信息 (绕 ISurface 动态分派限制)."""
    def __init__(self):
        self.index: int = 0
        self.surface_type: str = "unknown"
        self.area_m2: Optional[float] = None
        self.radius_mm: Optional[float] = None
        self.normal: Optional[List[float]] = None
        self.uv_bounds: Optional[List[float]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {"index": self.index, "type": self.surface_type}
        if self.area_m2 is not None:
            d["area_m2"] = self.area_m2
        if self.radius_mm is not None:
            d["radius_mm"] = self.radius_mm
            d["diameter_mm"] = round(self.radius_mm * 2, 2)
        if self.normal is not None:
            d["normal"] = self.normal
        return d


class BRepScan:
    """组件 B-Rep 扫描结果."""
    def __init__(self, comp_name: str):
        self.comp_name = comp_name
        self.n_faces: int = 0
        self.n_edges: int = 0
        self.n_cylinders: int = 0
        self.n_planes: int = 0
        self.faces: List[FaceInfo] = []
        self.body_source: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "comp": self.comp_name,
            "n_faces": self.n_faces,
            "n_edges": self.n_edges,
            "n_cylinders": self.n_cylinders,
            "n_planes": self.n_planes,
            "body_source": self.body_source,
            "faces": [f.to_dict() for f in self.faces],
        }


class CylinderFace:
    """装配上下文圆柱面 · 含 face COM 句柄 + 世界几何.

    用于 MateForge: 由 SWReverse.scan_comp_geometry() 产生,
    face 可直接传入 AddMate5 / Select4, 无需 SelectByRay.
    "以神遇而不以目视, 官知止而神欲行."
    """
    def __init__(self, face_com, idx: int, radius_mm: float,
                 axis_world: Tuple[float, float, float],
                 origin_world_mm: Tuple[float, float, float],
                 area_m2: float):
        self.face = face_com   # IFace2 COM (from comp.GetBody → GetFaces)
        self.idx = idx
        self.radius_mm = radius_mm
        self.axis_world = axis_world   # 单位向量 · 世界系
        self.origin_world_mm = origin_world_mm   # 轴线上任一点 · mm
        self.area_m2 = area_m2

    def to_dict(self) -> Dict[str, Any]:
        return {
            "idx": self.idx, "radius_mm": self.radius_mm,
            "axis_world": self.axis_world,
            "origin_world_mm": self.origin_world_mm,
            "area_m2": self.area_m2,
        }


class PlaneFace:
    """装配上下文平面 · 含 face COM 句柄 + 世界法线."""
    def __init__(self, face_com, idx: int,
                 normal_world: Tuple[float, float, float],
                 point_world_mm: Tuple[float, float, float],
                 area_m2: float):
        self.face = face_com
        self.idx = idx
        self.normal_world = normal_world
        self.point_world_mm = point_world_mm
        self.area_m2 = area_m2

    def to_dict(self) -> Dict[str, Any]:
        return {
            "idx": self.idx,
            "normal_world": self.normal_world,
            "point_world_mm": self.point_world_mm,
            "area_m2": self.area_m2,
        }


class CompGeometry:
    """组件几何索引: {"cylinders": [CylinderFace], "planes": [PlaneFace]}."""
    def __init__(self, comp_name: str):
        self.comp_name: str = comp_name
        self.cylinders: List[CylinderFace] = []
        self.planes: List[PlaneFace] = []
        self.body_src: str = "?"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "comp": self.comp_name,
            "body_src": self.body_src,
            "cylinders": [c.to_dict() for c in self.cylinders],
            "planes": [p.to_dict() for p in self.planes],
        }

    # ─── 查询工具 ──
    def find_cylinder(self, radius_mm: Optional[float] = None,
                      axis: Optional[Tuple[float, float, float]] = None,
                      through_point_mm: Optional[Tuple[float, float, float]] = None,
                      r_tol: float = 0.5,
                      prefer: str = "largest_area") -> Optional[CylinderFace]:
        """按几何特征挑选圆柱面.

        · radius_mm: 目标半径 (±r_tol mm)
        · axis: 世界轴 (允许反向匹配)
        · through_point_mm: 轴线须穿过此点 (垂直距离 < 1 mm)
        · prefer: "largest_area" 或 "smallest_area"
        """
        cands = list(self.cylinders)
        if radius_mm is not None:
            cands = [c for c in cands if abs(c.radius_mm - radius_mm) <= r_tol]
        if axis is not None:
            a0 = axis
            def _col(c):
                d = sum(x*y for x, y in zip(c.axis_world, a0))
                return abs(abs(d) - 1.0) < 0.05
            cands = [c for c in cands if _col(c)]
        if through_point_mm is not None:
            def _on(c):
                o = c.origin_world_mm; ax = c.axis_world
                d = [p-o[i] for i, p in enumerate(through_point_mm)]
                proj = sum(di*ai for di, ai in zip(d, ax))
                perp = [di - proj*ai for di, ai in zip(d, ax)]
                return math.sqrt(sum(x*x for x in perp)) < 1.0
            cands = [c for c in cands if _on(c)]
        if not cands:
            return None
        if prefer == "smallest_area":
            return min(cands, key=lambda c: c.area_m2)
        return max(cands, key=lambda c: c.area_m2)


class DocSnapshot:
    """文档完整状态快照."""
    def __init__(self):
        self.doc_name: str = ""
        self.doc_path: str = ""
        self.doc_type: int = 0
        self.features: List[Dict[str, Any]] = []
        self.components: List[ComponentInfo] = []
        self.mates: List[MateInfo] = []
        self.brep_scans: List[BRepScan] = []
        self.ref_planes: List[str] = []
        self.properties: Dict[str, Any] = {}
        self.equations: List[Dict[str, Any]] = []
        self.configurations: List[str] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document": {
                "name": self.doc_name,
                "path": self.doc_path,
                "type": self.doc_type,
                "type_desc": {0: "none", 1: "part", 2: "assembly", 3: "drawing"}
                    .get(self.doc_type, f"?({self.doc_type})"),
            },
            "features": self.features,
            "components": [c.to_dict() for c in self.components],
            "mates": [m.to_dict() for m in self.mates],
            "brep_scans": [b.to_dict() for b in self.brep_scans],
            "ref_planes": self.ref_planes,
            "properties": self.properties,
            "equations": self.equations,
            "configurations": self.configurations,
            "summary": {
                "n_features": len(self.features),
                "n_components": len(self.components),
                "n_fixed": sum(1 for c in self.components if c.fixed),
                "n_free": sum(1 for c in self.components
                             if not c.fixed and not c.suppressed),
                "n_mates": len(self.mates),
                "n_mates_ok": sum(1 for m in self.mates
                                 if m.error_status in (0, None)),
                "n_brep_faces": sum(b.n_faces for b in self.brep_scans),
                "n_cylinders": sum(b.n_cylinders for b in self.brep_scans),
            },
        }


# ════════════════════════════════════════════════════════════════════════
# ③ SWReverse — 万法归宗总纲
# ════════════════════════════════════════════════════════════════════════
class SWReverse:
    """SolidWorks 逆向万法总纲.

    从 SW 反向出发，发现一切、操控一切。
    复用 dao_solidworks + dao_sw_live，守正不创新。
    """

    def __init__(self):
        self._app = None
        self._asm = None
        self._ext = None
        self._sel = None
        self._comp_map: Dict[str, Any] = {}
        self._typelib = TypeLibInfo()
        self._mreg = MemidRegistry()  # 庖丁之刀
        self._snapshot: Optional[DocSnapshot] = None
        # 复用已有桥接
        self._bridge = None
        self._live = None

    # ─── 连接 ──────────────────────────────────────────────────────────
    def connect(self) -> Dict[str, Any]:
        """连接到运行中的 SolidWorks, 复用 dao_solidworks 桥接."""
        _log("═══ 连接 SolidWorks ═══")
        try:
            import win32com.client
            self._app = _dyn(win32com.client.GetActiveObject("SldWorks.Application"))
            rev = _safe(lambda: str(self._app.RevisionNumber), "?")
            _log(f"  SW rev={rev}")
        except Exception as e:
            _log(f"  GetActiveObject 失败: {e}")
            # 回退: 通过 dao_solidworks 桥接
            try:
                import dao_solidworks as _sw
                self._bridge = _sw.SolidWorksBridge()
                self._bridge.connect(prefer_active=True)
                self._app = _dyn(self._bridge._app)
                rev = _safe(lambda: str(self._app.RevisionNumber), "?")
                _log(f"  SW rev={rev} (via bridge)")
            except Exception as e2:
                _log(f"  bridge 连接也失败: {e2}")
                return {"ok": False, "error": str(e2)}

        # 获取活动文档
        self._asm = _safe(lambda: _dyn(self._app.ActiveDoc))
        if not self._asm:
            # 遍历打开的文档
            doc = _safe(lambda: _dyn(self._app.GetFirstDocument))
            while doc:
                try:
                    if int(doc.GetType) == 2:  # Assembly
                        self._asm = doc
                        break
                except Exception:
                    pass
                doc = _safe(lambda: _dyn(doc.GetNext))

        if not self._asm:
            _log("  无活动文档")
            return {"ok": False, "error": "no_active_doc"}

        self._ext = _safe(lambda: _dyn(self._asm.Extension))
        self._sel = _safe(lambda: _dyn(self._asm.SelectionManager))
        asm_name = _safe(lambda: str(self._asm.GetTitle), "?")
        asm_path = _safe(lambda: str(self._asm.GetPathName), "?")
        doc_type = _safe(lambda: int(self._asm.GetType), 0)
        _log(f"  文档: {asm_name}")
        _log(f"  路径: {asm_path}")
        _log(f"  类型: {doc_type}")

        # 加载 MemidRegistry (庖丁之刀)
        try:
            import dao_solidworks as _sw
            info = _sw.sw_info()
            self._mreg.load(sw_exe=info.exe)
        except Exception:
            self._mreg.load()

        # 构建组件映射
        self._build_comp_map()

        return {"ok": True, "name": asm_name, "path": asm_path,
                "type": doc_type, "n_components": len(self._comp_map)}

    def _build_comp_map(self):
        """构建组件名→COM对象映射."""
        self._comp_map = {}
        raw = _safe(lambda: self._asm.GetComponents(True))
        if raw:
            for c in raw:
                c = _dyn(c)
                if c:
                    name = _safe(lambda: str(c.Name2))
                    if name:
                        self._comp_map[name] = c

    # ─── ① 类型库逆向 ────────────────────────────────────────────────
    def probe_typelib(self) -> Dict[str, Any]:
        """逆向 SolidWorks 类型库."""
        return self._typelib.probe()

    # ─── ② 活体深探 ──────────────────────────────────────────────────
    def probe_features(self) -> List[Dict[str, Any]]:
        """遍历完整特征树."""
        _log("═══ 特征树 · 完整遍历 ═══")
        features = []
        feat = _safe(lambda: _dyn(self._asm.FirstFeature))
        while feat:
            fn = _safe(lambda: str(feat.Name), "?")
            ft = _safe(lambda: str(feat.GetTypeName2), "?")
            sup = _safe(lambda: bool(feat.IsSuppressed), None)
            rec = {"name": fn, "type": ft, "suppressed": sup, "sub": []}

            _log(f"  {fn} [{ft}]{'  (抑制)' if sup else ''}")

            # 子特征
            sub = _safe(lambda: _dyn(feat.GetFirstSubFeature))
            while sub:
                sn = _safe(lambda: str(sub.Name), "?")
                st = _safe(lambda: str(sub.GetTypeName2), "?")
                ss = _safe(lambda: bool(sub.IsSuppressed), None)
                sub_rec = {"name": sn, "type": st, "suppressed": ss}

                # 配合特征提取详细信息
                if "Mate" in st:
                    sub_rec["mate_detail"] = self._extract_mate_detail(sub)

                rec["sub"].append(sub_rec)
                _log(f"    {sn} [{st}]{'  (抑制)' if ss else ''}")

                sub = _safe(lambda: _dyn(sub.GetNextSubFeature))

            features.append(rec)
            feat = _safe(lambda: _dyn(feat.GetNextFeature))

        _log(f"  顶层特征: {len(features)}")
        _log(f"  子特征: {sum(len(f['sub']) for f in features)}")
        return features

    def _extract_mate_detail(self, feat) -> Dict[str, Any]:
        """从配合特征提取详细信息 (IMate2)."""
        detail = {}
        try:
            mate2 = _dyn(feat.GetSpecificFeature2)
            if mate2:
                detail["mate_type"] = _safe(lambda: int(mate2.Type), -1)
                detail["alignment"] = _safe(lambda: int(mate2.Alignment), -1)
                detail["error_status"] = _safe(lambda: int(mate2.ErrorStatus), None)
                detail["max_var"] = _safe(lambda: float(mate2.MaxVariance), None)
                detail["min_var"] = _safe(lambda: float(mate2.MinVariance), None)

                # 配合实体组件
                for i in range(3):
                    try:
                        ent = _dyn(mate2.MateEntity(i))
                        if ent:
                            comp = _safe(lambda: _dyn(ent.ReferenceComponent))
                            detail[f"entity{i}_comp"] = (
                                _safe(lambda: str(comp.Name2), "?") if comp else "?"
                            )
                            detail[f"entity{i}_type"] = _safe(
                                lambda: int(ent.ReferenceType2), -1
                            )
                    except Exception:
                        break
        except Exception as ex:
            detail["error"] = str(ex)[:200]
        return detail

    def probe_components(self) -> List[ComponentInfo]:
        """深探所有组件状态."""
        _log("═══ 组件 · 完整状态 ═══")
        comps = []
        raw = _safe(lambda: self._asm.GetComponents(True))
        if not raw:
            _log("  GetComponents 返回 None")
            return comps

        for i, c_raw in enumerate(raw):
            c = _dyn(c_raw)
            if not c:
                continue
            info = ComponentInfo()
            info.name = _safe(lambda: str(c.Name2), f"comp_{i}")
            info.path = _safe(lambda: str(c.GetPathName), "")
            info.fixed = _safe(lambda: bool(c.IsFixed), None)
            info.suppressed = _safe(lambda: bool(c.IsSuppressed), None)
            info.visible = _safe(lambda: int(c.Visible), None)
            info.suppression_state = _safe(lambda: int(c.GetSuppression), -1)

            # 变换矩阵
            try:
                xform = c.Transform2
                if xform:
                    arr = _safe(lambda: list(xform.ArrayData))
                    if arr:
                        info.transform = [round(float(v), 6) for v in arr]
            except Exception:
                pass

            status = "(固定)" if info.fixed else "(-)"
            sup = " [抑制]" if info.suppressed else ""
            vis = " [隐藏]" if info.visible == 0 else ""
            _log(f"  {status} {info.name}{sup}{vis}")

            comps.append(info)
            self._comp_map[info.name] = c

        _log(f"  共 {len(comps)} 个组件")
        return comps

    def probe_mates(self, features: Optional[List[Dict]] = None) -> List[MateInfo]:
        """深探所有配合详情."""
        _log("═══ 配合 · 详细分析 ═══")
        if features is None:
            features = self.probe_features()

        mates = []
        for feat in features:
            for sub in feat.get("sub", []):
                if "Mate" not in sub.get("type", ""):
                    continue
                mi = MateInfo()
                mi.name = sub["name"]
                mi.type_name = sub["type"]
                mi.suppressed = sub.get("suppressed")

                detail = sub.get("mate_detail", {})
                mi.mate_type = detail.get("mate_type", -1)
                mi.alignment = detail.get("alignment", -1)
                mi.error_status = detail.get("error_status")

                for j in range(3):
                    ec = detail.get(f"entity{j}_comp")
                    if ec and ec != "?":
                        mi.entity_comps.append(ec)

                e0 = mi.entity_comps[0] if len(mi.entity_comps) > 0 else "?"
                e1 = mi.entity_comps[1] if len(mi.entity_comps) > 1 else "?"
                td = mi.to_dict()
                err_flag = f"  ⚠ {td['error']}" if mi.error_status not in (0, None) else ""
                _log(f"  {mi.name}: {td['type_desc']} [{td['alignment']}] "
                     f"{e0} ↔ {e1}{err_flag}")

                mates.append(mi)

        _log(f"  共 {len(mates)} 个配合")
        type_counts = Counter(m.to_dict()["type_desc"] for m in mates)
        for t, c in type_counts.most_common():
            _log(f"    {t}: {c}")

        return mates

    # ─── ④ B-Rep 几何 (绕 ISurface 限制) ────────────────────────────
    def probe_brep(self, comp_names: Optional[List[str]] = None) -> List[BRepScan]:
        """扫描组件 B-Rep 几何.

        关键发现 (来自前序对话):
          - ISurface.IsCylinder() 在动态分派下不可用 ("找不到成员")
          - face.GetArea 是属性 (非方法)
          - face.Normal 返回数组
          - face.GetUVBounds 返回数组
          - 需要启发式方法: Normal 长度 + UVBounds 判断面类型
        """
        _log("═══ B-Rep 几何扫描 ═══")
        scans = []

        if comp_names is None:
            # 只扫描每种零件的第一个实例
            seen_stems = set()
            comp_names = []
            for name in self._comp_map:
                stem = name.rsplit("-", 1)[0]
                if stem not in seen_stems:
                    seen_stems.add(stem)
                    comp_names.append(name)

        for comp_name in comp_names:
            comp = self._comp_map.get(comp_name)
            if not comp:
                continue
            scan = self._scan_comp_brep(comp, comp_name)
            scans.append(scan)

        return scans

    def _scan_comp_brep(self, comp, comp_name: str) -> BRepScan:
        """扫描单个组件的 B-Rep."""
        scan = BRepScan(comp_name)

        # 获取 body — 多路回退
        body = None
        faces_raw = None

        # 路 1: GetModelDoc2 → GetBodies2
        try:
            mdoc = _dyn(comp.GetModelDoc2)
            if mdoc:
                bodies = _safe(lambda: mdoc.GetBodies2(0, False))
                if bodies and len(bodies) > 0:
                    body = _dyn(bodies[0])
                    scan.body_source = "GetModelDoc2"
        except Exception:
            pass

        # 路 2: GetBody (装配上下文)
        if body is None:
            try:
                body = _dyn(comp.GetBody)
                if body:
                    scan.body_source = "GetBody"
            except Exception:
                pass

        # 路 3: GetBodies2 on component
        if body is None:
            try:
                bodies = comp.GetBodies2(0, False)
                if bodies and len(bodies) > 0:
                    body = _dyn(bodies[0])
                    scan.body_source = "GetBodies2"
            except Exception:
                pass

        if body is None:
            _log(f"  {comp_name}: 无法获取 body")
            return scan

        # 枚举面
        try:
            faces_raw = body.GetFaces()
        except Exception:
            try:
                faces_raw = body.GetFaces
            except Exception:
                pass

        if not faces_raw:
            _log(f"  {comp_name}: 无面")
            return scan

        scan.n_faces = len(faces_raw)

        # 枚举边
        try:
            edges = body.GetEdges()
            if edges:
                scan.n_edges = len(edges)
        except Exception:
            pass

        # 分类每个面
        for idx, f_raw in enumerate(faces_raw):
            f = _dyn(f_raw)
            if not f:
                continue

            fi = FaceInfo()
            fi.index = idx

            # 面积 (属性,非方法)
            try:
                a = f.GetArea
                if callable(a):
                    a = a()
                fi.area_m2 = float(a)
            except Exception:
                pass

            # 法线 (平面有固定法线, 曲面为 None)
            try:
                n = f.Normal
                if n and len(n) >= 3:
                    fi.normal = [round(float(n[0]), 6),
                                 round(float(n[1]), 6),
                                 round(float(n[2]), 6)]
            except Exception:
                pass

            # UV 范围
            try:
                uv = f.GetUVBounds
                if callable(uv):
                    uv = uv()
                if uv and len(uv) >= 4:
                    fi.uv_bounds = [float(uv[i]) for i in range(4)]
            except Exception:
                pass

            # 面类型 — 多路探测 (ISurface + 启发式)
            fi.surface_type, fi.radius_mm = self._classify_face_deep(f, fi)

            if fi.surface_type == "cylinder" and fi.radius_mm and fi.radius_mm > 0:
                scan.n_cylinders += 1
            elif fi.surface_type == "plane":
                scan.n_planes += 1

            scan.faces.append(fi)

        cyl_summary = ", ".join(
            f"Ø{f.radius_mm*2:.1f}" for f in scan.faces
            if f.radius_mm and f.radius_mm > 0
        )
        _log(f"  {comp_name}: {scan.body_source} "
             f"faces={scan.n_faces} cyl={scan.n_cylinders} plane={scan.n_planes}"
             + (f" [{cyl_summary}]" if cyl_summary else ""))

        return scan

    def _classify_face_deep(self, face_com, fi: FaceInfo) -> Tuple[str, Optional[float]]:
        """多路面类型分类 + 圆柱半径提取.

        路 0: MemidRegistry (庖丁之刀 · 最准最快)
              IFace2.GetSurface(memid=3) → ISurface.Identity(memid=9)
        路 1-3: 动态分派回退 (多数情况下会失败)
        路 4: face.Normal + UV 启发式 (终极回退)

        swSurfaceType_e:
          PLANE=4001, CYLINDER=4002, CONE=4003, SPHERE=4004,
          TORUS=4005, BSURF=4006, BLEND=4007, OFFSET=4008, EXTRU=4009
        """
        SURF_TYPE_MAP = {
            4001: "plane", 4002: "cylinder", 4003: "cone",
            4004: "sphere", 4005: "torus", 4006: "bspline",
            4007: "blend", 4008: "offset", 4009: "extrusion",
        }
        radius_mm = None

        # ─── 路 0: MemidRegistry · 庖丁之刀 · 链式调用 ───
        if self._mreg.loaded:
            try:
                oleobj = face_com._oleobj_ if hasattr(face_com, "_oleobj_") else face_com
                # 链式: IFace2.GetSurface() → 自动推断 ISurface → .Identity()
                identity = int(self._mreg.invoke_chain(
                    oleobj, "IFace2", ["GetSurface", "Identity"]))
                stype = SURF_TYPE_MAP.get(identity)
                if stype:
                    if stype == "cylinder":
                        surf_raw = self._mreg.invoke_chain(
                            oleobj, "IFace2", ["GetSurface"])
                        radius_mm = self._extract_cylinder_radius_memid(surf_raw)
                    return (stype, radius_mm)
            except Exception:
                pass  # 跌入旧路

        # ─── 路 1-3: 动态分派回退 ───
        surf = None
        for getter in ("GetSurface", "IGetSurface"):
            try:
                fn = getattr(face_com, getter, None)
                if fn:
                    s = fn() if callable(fn) else fn
                    if s:
                        surf = _dyn(s)
                        break
            except Exception:
                continue

        if surf is not None:
            try:
                identity = surf.Identity
                if callable(identity):
                    identity = identity()
                stype = SURF_TYPE_MAP.get(int(identity))
                if stype:
                    if stype == "cylinder":
                        radius_mm = self._extract_cylinder_radius(surf)
                    return (stype, radius_mm)
            except Exception:
                pass

        # ─── 路 4: 启发式回退 ───
        return self._classify_face_heuristic(fi)

    def _extract_cylinder_radius_memid(self, surf_oleobj) -> Optional[float]:
        """从 ISurface oleobj 通过 invoke_chain 提取圆柱半径 (mm)."""
        try:
            cp = self._mreg.invoke_chain(
                surf_oleobj, "ISurface", ["CylinderParams"])
            if cp and len(cp) >= 7:
                return round(float(cp[6]) * 1000, 2)
        except Exception:
            pass
        return None

    def _extract_cylinder_radius(self, surf) -> Optional[float]:
        """从 ISurface 提取圆柱半径 (mm) — 动态分派路径."""
        for attr in ("CylinderParams", "GetCylinderParams"):
            try:
                cp = getattr(surf, attr)
                if callable(cp):
                    cp = cp()
                if cp and len(cp) >= 7:
                    return round(float(cp[6]) * 1000, 2)
            except Exception:
                continue
        return None

    def _classify_face_heuristic(self, fi: FaceInfo) -> Tuple[str, Optional[float]]:
        """启发式面分类 (当 ISurface 不可用时的回退).

        关键发现 (实测):
          - 平面: Normal = 单位向量 (e.g. (1,0,0))
          - 曲面: Normal = 零向量 (0,0,0) (不是 None!)
          → Normal 非零且单位长度 → 平面
          → Normal 零向量 或 None → 非平面 → 检查 UV
        """
        radius_mm = None

        if fi.normal is not None:
            nmag = math.sqrt(sum(n * n for n in fi.normal))
            if abs(nmag - 1.0) < 0.01:
                return ("plane", None)
            # nmag ≈ 0 → 曲面 (SW 返回零向量) → 不返回, 跌入 UV 检查

        # Normal 为 None 或零向量 → 非平面 → 检查 UV
        if fi.uv_bounds:
            u_range = abs(fi.uv_bounds[1] - fi.uv_bounds[0])
            v_range = abs(fi.uv_bounds[3] - fi.uv_bounds[2])

            # 全圆柱: 一维 ≈ 2π
            if abs(u_range - 2 * math.pi) < 0.3:
                if fi.area_m2 and v_range > 1e-9:
                    radius_mm = round((fi.area_m2 / (u_range * v_range)) * 1000, 2)
                return ("cylinder", radius_mm)
            if abs(v_range - 2 * math.pi) < 0.3:
                if fi.area_m2 and u_range > 1e-9:
                    radius_mm = round((fi.area_m2 / (u_range * v_range)) * 1000, 2)
                return ("cylinder", radius_mm)

            # 部分圆柱 (半圆等)
            for rng in (u_range, v_range):
                if abs(rng - math.pi) < 0.2:
                    return ("cylinder", None)

        # Normal 为 None, UV 也不像圆柱 → 其他曲面
        if fi.normal is None:
            return ("other_curved", None)

        return ("other", None)

    # ─── ③ 装配操控 ──────────────────────────────────────────────────
    def select_by_ray(self, x: float, y: float, z: float,
                      dx: float, dy: float, dz: float,
                      radius: float = 0.001,
                      sel_type: int = 2,  # FACE
                      append: bool = False) -> Dict[str, Any]:
        """通过射线选择面. 坐标单位: 米. 返回选中的组件和面信息."""
        if not append:
            self._asm.ClearSelection2(True)
        try:
            ok = self._ext.SelectByRay(
                float(x), float(y), float(z),
                float(dx), float(dy), float(dz),
                float(radius), int(sel_type),
                bool(append), 0, 0
            )
            cnt = int(self._sel.GetSelectedObjectCount2(-1))
            comp_name = None
            if cnt > 0:
                comp = _safe(lambda: _dyn(self._sel.GetSelectedObjectsComponent4(1, -1)))
                comp_name = _safe(lambda: str(comp.Name2)) if comp else None

            return {"ok": bool(ok), "count": cnt, "comp": comp_name}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def add_mate_concentric(self, comp1: str, comp2: str,
                            ray1: Tuple[float, ...],
                            ray2: Tuple[float, ...],
                            unfix_comp: Optional[str] = None) -> Dict[str, Any]:
        """添加同心配合. ray = (x, y, z, dx, dy, dz) 单位米.

        策略:
          1. 可选: 解固 unfix_comp
          2. SelectByRay 选第一面 (验证命中 comp1)
          3. SelectByRay 追加选第二面 (验证命中 comp2)
          4. AddMate5 创建同心配合
          5. 可选: 重新固定 unfix_comp
        """
        _log(f"  ── 配合: {comp1} ↔ {comp2} (同心) ──")
        result = {"comp1": comp1, "comp2": comp2, "type": "concentric"}

        # 解固
        if unfix_comp:
            self._set_fixed(unfix_comp, False)

        try:
            # 选面1
            self._asm.ClearSelection2(True)
            r1 = self.select_by_ray(*ray1[:6])
            _log(f"    射线1 ok={r1['ok']} hit={r1.get('comp')} (期望 {comp1})")
            if not r1["ok"] or r1.get("comp") != comp1:
                result["error"] = f"射线1 命中 {r1.get('comp')} (期望 {comp1})"
                if unfix_comp:
                    self._set_fixed(unfix_comp, True)
                return result

            # 选面2 (追加)
            r2 = self.select_by_ray(*ray2[:6], append=True)
            _log(f"    射线2 ok={r2['ok']} hit={r2.get('comp')} (期望 {comp2})")
            cnt = int(self._sel.GetSelectedObjectCount2(-1))
            if not r2["ok"] or r2.get("comp") != comp2 or cnt < 2:
                result["error"] = f"射线2 命中 {r2.get('comp')} (期望 {comp2}), cnt={cnt}"
                if unfix_comp:
                    self._set_fixed(unfix_comp, True)
                return result

            # AddMate5: type=1 (Concentric), align=0, flip=False
            err_status = _byref_int()
            try:
                mate = self._asm.AddMate5(
                    1, 0, False,   # Concentric, Aligned, no flip
                    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                    False, False, 0, err_status
                )
                err_val = _safe(lambda: err_status.value, -1)
                if mate:
                    _log(f"    AddMate5: 成功 ✓ err={err_val}")
                    result["ok"] = True
                    result["error_code"] = err_val
                else:
                    _log(f"    AddMate5: 返回 None, err={err_val}")
                    result["error"] = f"AddMate5=None, err={err_val}"
            except Exception as e:
                _log(f"    AddMate5 异常: {e}")
                result["error"] = str(e)

        finally:
            self._asm.ClearSelection2(True)
            if unfix_comp:
                self._set_fixed(unfix_comp, True)

        return result

    def add_mate_coincident(self, comp1: str, comp2: str,
                            ray1: Tuple[float, ...],
                            ray2: Tuple[float, ...],
                            unfix_comp: Optional[str] = None) -> Dict[str, Any]:
        """添加重合配合."""
        _log(f"  ── 配合: {comp1} ↔ {comp2} (重合) ──")
        result = {"comp1": comp1, "comp2": comp2, "type": "coincident"}

        if unfix_comp:
            self._set_fixed(unfix_comp, False)

        try:
            self._asm.ClearSelection2(True)
            r1 = self.select_by_ray(*ray1[:6])
            if not r1["ok"] or r1.get("comp") != comp1:
                result["error"] = f"射线1 命中 {r1.get('comp')} (期望 {comp1})"
                return result

            r2 = self.select_by_ray(*ray2[:6], append=True)
            cnt = int(self._sel.GetSelectedObjectCount2(-1))
            if not r2["ok"] or r2.get("comp") != comp2 or cnt < 2:
                result["error"] = f"射线2 命中 {r2.get('comp')} (期望 {comp2})"
                return result

            err_status = _byref_int()
            try:
                mate = self._asm.AddMate5(
                    0, 0, False,   # Coincident, Aligned, no flip
                    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                    False, False, 0, err_status
                )
                err_val = _safe(lambda: err_status.value, -1)
                if mate:
                    _log(f"    AddMate5: 成功 ✓")
                    result["ok"] = True
                else:
                    result["error"] = f"AddMate5=None, err={err_val}"
            except Exception as e:
                result["error"] = str(e)
        finally:
            self._asm.ClearSelection2(True)
            if unfix_comp:
                self._set_fixed(unfix_comp, True)

        return result

    def add_mate_distance(self, comp1: str, comp2: str,
                          distance_m: float,
                          ray1: Tuple[float, ...],
                          ray2: Tuple[float, ...],
                          unfix_comp: Optional[str] = None) -> Dict[str, Any]:
        """添加距离配合."""
        _log(f"  ── 配合: {comp1} ↔ {comp2} (距离={distance_m*1000:.1f}mm) ──")
        result = {"comp1": comp1, "comp2": comp2, "type": "distance"}

        if unfix_comp:
            self._set_fixed(unfix_comp, False)

        try:
            self._asm.ClearSelection2(True)
            r1 = self.select_by_ray(*ray1[:6])
            if not r1["ok"] or r1.get("comp") != comp1:
                result["error"] = f"射线1 命中 {r1.get('comp')}"
                return result

            r2 = self.select_by_ray(*ray2[:6], append=True)
            cnt = int(self._sel.GetSelectedObjectCount2(-1))
            if not r2["ok"] or r2.get("comp") != comp2 or cnt < 2:
                result["error"] = f"射线2 命中 {r2.get('comp')}"
                return result

            err_status = _byref_int()
            try:
                mate = self._asm.AddMate5(
                    5, 0, False,   # Distance, Aligned, no flip
                    float(distance_m), float(distance_m), float(distance_m),
                    0.0, 0.0, 0.0, 0.0, 0.0,
                    False, False, 0, err_status
                )
                if mate:
                    result["ok"] = True
                else:
                    result["error"] = f"AddMate5=None, err={_safe(lambda: err_status.value, -1)}"
            except Exception as e:
                result["error"] = str(e)
        finally:
            self._asm.ClearSelection2(True)
            if unfix_comp:
                self._set_fixed(unfix_comp, True)

        return result

    def _set_fixed(self, comp_name: str, fixed: bool):
        """固定/解固组件."""
        comp = self._comp_map.get(comp_name)
        if not comp:
            return
        is_fixed = _safe(lambda: bool(comp.IsFixed), None)
        if is_fixed == fixed:
            return
        try:
            comp.Select2(False, 0)
            if fixed:
                self._asm.FixComponent()
            else:
                self._asm.UnfixComponent()
            self._asm.ClearSelection2(True)
            action = "固定" if fixed else "解固"
            _log(f"    {action}: {comp_name}")
        except Exception as e:
            _log(f"    固定/解固 {comp_name} 失败: {e}")

    # ═══════════════════════════════════════════════════════════════════
    # ⑨ MateForge · Face-Direct 配合建造 (无射线 · 以神遇而不以目视)
    # ═══════════════════════════════════════════════════════════════════
    # SelectByRay 受装配墙阻挡限制, 常错选. 此处以 IComponent2.GetBody →
    # IBody2.GetFaces → IFace2.GetSurface.CylinderParams 直取几何, face
    # COM 句柄通过 IEntity.Select4 可直选, 绕开射线. 精准如庖丁之刀.
    # "依乎天理, 批大郤, 导大窾, 因其固然."
    # swMateType_e / swMateAlign_e
    MATE_COINCIDENT = 0
    MATE_CONCENTRIC = 1
    MATE_PERPENDICULAR = 2
    MATE_PARALLEL = 3
    MATE_TANGENT = 4
    MATE_DISTANCE = 5
    MATE_ANGLE = 6
    MATE_LOCK = 11
    MATE_GEAR = 13
    ALIGN_SAME = 0
    ALIGN_ANTI = 1
    ALIGN_CLOSEST = 2

    def _comp_body_asm(self, comp):
        """装配上下文 body · face 可 Select4.

        路 1: comp.GetBody (装配级, IFace2.Select4 可用)
        路 2: comp.GetBodies2(0, False)
        路 3: comp.GetModelDoc2.GetBodies2(0, False) (部件级, 仅读不可选)
        """
        # 路 1
        try:
            b = _dyn(comp.GetBody)
            if b:
                return b, "GetBody"
        except Exception:
            pass
        # 路 2
        try:
            bb = _safe(lambda: comp.GetBodies2(0, False))
            if bb and len(bb) > 0:
                return _dyn(bb[0]), "comp.GetBodies2"
        except Exception:
            pass
        # 路 3
        try:
            md = _dyn(comp.GetModelDoc2)
            if md:
                bb = _safe(lambda: md.GetBodies2(0, False))
                if bb and len(bb) > 0:
                    return _dyn(bb[0]), "ModelDoc2"
        except Exception:
            pass
        return None, None

    def _comp_xf_array(self, comp) -> Optional[List[float]]:
        """取 Transform2 ArrayData (12 floats: 9 rot col-major + 3 trans)."""
        try:
            xf = _dyn(comp.Transform2)
            arr = xf.ArrayData
            if callable(arr):
                arr = arr()
            return list(arr)
        except Exception:
            return None

    @staticmethod
    def _xf_apply(arr: List[float], p: Sequence[float]) -> Tuple[float, float, float]:
        """世界坐标 = R @ p + t, R 列主序."""
        r, t = arr[:9], arr[9:12]
        x, y, z = p
        return (r[0]*x+r[3]*y+r[6]*z+t[0],
                r[1]*x+r[4]*y+r[7]*z+t[1],
                r[2]*x+r[5]*y+r[8]*z+t[2])

    @staticmethod
    def _xf_apply_dir(arr: List[float],
                       d: Sequence[float]) -> Tuple[float, float, float]:
        """方向量变换 (仅 R, 无 t)."""
        r = arr[:9]
        x, y, z = d
        return (r[0]*x+r[3]*y+r[6]*z,
                r[1]*x+r[4]*y+r[7]*z,
                r[2]*x+r[5]*y+r[8]*z)

    @staticmethod
    def _norm(v: Sequence[float]) -> Tuple[float, float, float]:
        m = math.sqrt(sum(c*c for c in v))
        if m < 1e-12:
            return tuple(v)  # type: ignore
        return tuple(c/m for c in v)  # type: ignore

    def scan_comp_geometry(self, comp_name: str) -> CompGeometry:
        """扫描组件的圆柱面 + 平面, 返回含 face COM 句柄的 CompGeometry.

        用于 MateForge · 与 probe_brep() 的纯统计扫描不同:
        此法保留 face COM 对象以供 AddMate5 直接使用, 避免 SelectByRay 的墙阻.
        """
        geom = CompGeometry(comp_name)
        comp = self._comp_map.get(comp_name)
        if not comp:
            return geom
        body, src = self._comp_body_asm(comp)
        if not body:
            return geom
        geom.body_src = src or "?"
        faces = _safe(lambda: body.GetFaces())
        if not faces:
            return geom
        arr = self._comp_xf_array(comp)
        if arr is None:
            return geom
        for i, fr in enumerate(faces):
            f = _dyn(fr)
            if not f:
                continue
            area = _safe(lambda: float(f.GetArea), 0.0)
            try:
                surf = _dyn(f.GetSurface)
                if not surf:
                    continue
                ident = _safe(lambda: int(surf.Identity), 0)
            except Exception:
                continue
            if ident == 4002:  # CYLINDER
                cp = _safe(lambda: surf.CylinderParams)
                if not cp or len(cp) < 7:
                    continue
                o_l = (float(cp[0]), float(cp[1]), float(cp[2]))
                a_l = (float(cp[3]), float(cp[4]), float(cp[5]))
                r_m = float(cp[6])
                o_w = self._xf_apply(arr, o_l)
                a_w = self._norm(self._xf_apply_dir(arr, a_l))
                geom.cylinders.append(CylinderFace(
                    face_com=f, idx=i, radius_mm=round(r_m*1000, 2),
                    axis_world=tuple(round(v, 4) for v in a_w),
                    origin_world_mm=tuple(round(v*1000, 1) for v in o_w),
                    area_m2=round(area, 6),
                ))
            elif ident == 4001:  # PLANE
                n = _safe(lambda: tuple(f.Normal))
                if not n:
                    continue
                n_w = self._norm(self._xf_apply_dir(arr, n))
                try:
                    bb = _safe(lambda: f.GetBox)
                    if bb and not callable(bb):
                        cx = (bb[0]+bb[3])/2; cy = (bb[1]+bb[4])/2
                        cz = (bb[2]+bb[5])/2
                        p_w = self._xf_apply(arr, (cx, cy, cz))
                    else:
                        p_w = self._xf_apply(arr, (0, 0, 0))
                except Exception:
                    p_w = self._xf_apply(arr, (0, 0, 0))
                geom.planes.append(PlaneFace(
                    face_com=f, idx=i,
                    normal_world=tuple(round(v, 4) for v in n_w),
                    point_world_mm=tuple(round(v*1000, 1) for v in p_w),
                    area_m2=round(area, 6),
                ))
        return geom

    def _select_face_direct(self, face_com, append: bool = False,
                            mark: int = 0) -> bool:
        """IEntity.Select4 直选 · 无射线. face 须来自 GetBody (装配上下文)."""
        try:
            sd = _safe(lambda: _dyn(self._ext.CreateSelectData))
            ok = face_com.Select4(append, sd)
            return bool(ok)
        except Exception:
            try:
                ok = face_com.Select4(append, _nothing())
                return bool(ok)
            except Exception as e:
                _log(f"    Select4 失败: {e}")
                return False

    def add_mate_faces(self, face1, face2, mate_type: int,
                       align: int = 0, flip: bool = False,
                       distance_m: float = 0.0,
                       angle_rad: float = 0.0,
                       unfix_comp: Optional[str] = None,
                       second_unfix: Optional[str] = None
                       ) -> Dict[str, Any]:
        """以两 face COM 直建 Mate · 不走射线.

        参数:
          · face1, face2: CylinderFace.face / PlaneFace.face
          · mate_type: self.MATE_CONCENTRIC / COINCIDENT / DISTANCE / PARALLEL / ...
          · align: 0=Same, 1=Anti, 2=Closest
          · flip: AddMate5 flip 参数
          · distance_m / angle_rad: Distance/Angle mate 用
          · unfix_comp: 建 Mate 前解固此件 (Fixed 件不接受 Mate)
          · second_unfix: 同上, 第二件可选
        """
        result: Dict[str, Any] = {"type": mate_type, "align": align}
        if unfix_comp:
            self._set_fixed(unfix_comp, False)
        if second_unfix:
            self._set_fixed(second_unfix, False)
        try:
            self._asm.ClearSelection2(True)
            r1 = self._select_face_direct(face1, False, 0)
            cnt1 = int(self._sel.GetSelectedObjectCount2(-1))
            if not r1 or cnt1 < 1:
                result["error"] = f"face1_select_fail cnt={cnt1}"
                return result
            r2 = self._select_face_direct(face2, True, 0)
            cnt2 = int(self._sel.GetSelectedObjectCount2(-1))
            if not r2 or cnt2 < 2:
                result["error"] = f"face2_select_fail cnt={cnt2}"
                return result
            err = _byref_int()
            mate = self._asm.AddMate5(
                mate_type, align, bool(flip),
                float(distance_m), float(distance_m), float(distance_m),
                float(angle_rad), float(angle_rad), float(angle_rad),
                0.0, 0.0,
                False, False, 0, err
            )
            err_val = _safe(lambda: err.value, -1)
            if mate:
                m = _dyn(mate)
                result["ok"] = True
                result["name"] = _safe(lambda: str(m.Name), "?")
                result["err"] = err_val
            else:
                result["error"] = f"addmate_none err={err_val}"
        except Exception as e:
            result["error"] = str(e)
        finally:
            self._asm.ClearSelection2(True)
        return result

    # ─── MateForge 语义外壳 (便于调用) ──
    def add_concentric(self, face1, face2, align: int = 1, flip: bool = False,
                       unfix_comp: Optional[str] = None,
                       second_unfix: Optional[str] = None) -> Dict[str, Any]:
        """同心 mate · CylinderFace.face 对 CylinderFace.face."""
        return self.add_mate_faces(face1, face2, self.MATE_CONCENTRIC,
                                   align=align, flip=flip,
                                   unfix_comp=unfix_comp,
                                   second_unfix=second_unfix)

    def add_coincident(self, face1, face2, align: int = 0,
                       flip: bool = False,
                       unfix_comp: Optional[str] = None,
                       second_unfix: Optional[str] = None) -> Dict[str, Any]:
        """重合 mate · PlaneFace.face 对 PlaneFace.face."""
        return self.add_mate_faces(face1, face2, self.MATE_COINCIDENT,
                                   align=align, flip=flip,
                                   unfix_comp=unfix_comp,
                                   second_unfix=second_unfix)

    def add_distance_faces(self, face1, face2, distance_mm: float,
                           align: int = 0, flip: bool = False,
                           unfix_comp: Optional[str] = None,
                           second_unfix: Optional[str] = None) -> Dict[str, Any]:
        """距离 mate (平面 / 平面). distance_mm 必须 > 0."""
        return self.add_mate_faces(face1, face2, self.MATE_DISTANCE,
                                   align=align, flip=flip,
                                   distance_m=distance_mm/1000.0,
                                   unfix_comp=unfix_comp,
                                   second_unfix=second_unfix)

    def add_parallel_faces(self, face1, face2, align: int = 0,
                           flip: bool = False,
                           unfix_comp: Optional[str] = None,
                           second_unfix: Optional[str] = None) -> Dict[str, Any]:
        """平行 mate (面 / 面 / 边 / 轴 均可)."""
        return self.add_mate_faces(face1, face2, self.MATE_PARALLEL,
                                   align=align, flip=flip,
                                   unfix_comp=unfix_comp,
                                   second_unfix=second_unfix)

    def mate_exists(self, comp1_name: str, comp2_name: str,
                    mate_type: Optional[int] = None) -> bool:
        """检查两件是否已有 mate (可选限定类型)."""
        try:
            feats = self.probe_features()
            mates = self.probe_mates(feats)
        except Exception:
            return False
        for m in mates:
            s = set(m.entity_comps[:2] if len(m.entity_comps) >= 2
                    else m.entity_comps)
            if comp1_name in s and comp2_name in s:
                if mate_type is None or m.mate_type == mate_type:
                    return True
        return False

    def force_set_transform(self, comp_name: str,
                             pos_mm: Tuple[float, float, float],
                             rot_col9: Optional[Sequence[float]] = None) -> bool:
        """复写组件 Transform2 · 列主序 9 rot + 3 trans.

        用于复位漂移件 (例: Concentric mate 允许轴向移动, 零件会被 solver
        挪到某稳定位置; 此法把它强制搬回地真坐标, 再 Fix 锁定).
        """
        comp = self._comp_map.get(comp_name)
        if not comp:
            return False
        if rot_col9 is None:
            rot = [1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0]
        else:
            rot = [float(v) for v in rot_col9][:9]
            if len(rot) < 9:
                rot = rot + [0.0] * (9 - len(rot))
        tx, ty, tz = pos_mm[0]/1000.0, pos_mm[1]/1000.0, pos_mm[2]/1000.0
        arr = rot + [tx, ty, tz, 1.0, 0.0, 0.0, 0.0]
        try:
            import pythoncom as _pyc
            from win32com.client import VARIANT as _VARIANT
            mu = self._mreg.invoke_obj(self._app, "ISldWorks",
                                       "GetMathUtility")
            v = _VARIANT(_pyc.VT_ARRAY | _pyc.VT_R8, arr)
            nxf = self._mreg.invoke_obj(mu, "IMathUtility",
                                        "CreateTransform", v)
            mid = self._mreg.memid("IComponent2", "Transform2")
            raw_c = comp._oleobj_ if hasattr(comp, "_oleobj_") else comp
            raw_x = nxf._oleobj_ if hasattr(nxf, "_oleobj_") else nxf
            raw_c.Invoke(mid, 0, _pyc.DISPATCH_PROPERTYPUTREF, False, raw_x)
            return True
        except Exception as e:
            _log(f"    force_set_transform {comp_name}: {e}")
            return False

    def fix_component(self, name: str):
        self._set_fixed(name, True)

    def unfix_component(self, name: str):
        self._set_fixed(name, False)

    # ─── 选择工具 ────────────────────────────────────────────────────
    def select_component(self, name: str, mark: int = 0) -> bool:
        """通过名称选择组件."""
        asm_title = _safe(
            lambda: str(self._asm.GetTitle).replace(".SLDASM", ""), ""
        )
        self._asm.ClearSelection2(True)
        ok = self._ext.SelectByID2(
            f"{name}@{asm_title}", "COMPONENT",
            0.0, 0.0, 0.0, False, mark, _nothing(), 0
        )
        return bool(ok)

    def select_plane(self, name: str, append: bool = False, mark: int = 0) -> bool:
        """选择基准面."""
        ok = self._ext.SelectByID2(
            name, "DATUMPLANE",
            0.0, 0.0, 0.0, append, mark, _nothing(), 0
        )
        return bool(ok)

    # ─── 文档操作 ────────────────────────────────────────────────────
    def rebuild(self, force: bool = True) -> bool:
        try:
            if force:
                return bool(self._asm.ForceRebuild3(False))
            else:
                return bool(self._asm.EditRebuild3)
        except Exception:
            return False

    def save(self) -> Dict[str, Any]:
        """保存装配体."""
        try:
            import pythoncom
            import win32com.client
            errs = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            warns = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            ok = self._asm.Save3(1, errs, warns)
            return {"ok": bool(ok),
                    "errors": _safe(lambda: errs.value, -1),
                    "warnings": _safe(lambda: warns.value, -1)}
        except Exception as e:
            try:
                self._asm.Save2(True, 0, 0)
                return {"ok": True, "via": "Save2"}
            except Exception as e2:
                return {"ok": False, "error": str(e2)}

    # ─── 探测参考几何 ────────────────────────────────────────────────
    def probe_ref_planes(self) -> List[str]:
        """枚举所有基准面名称."""
        _log("═══ 基准面 ═══")
        planes = []
        feat = _safe(lambda: _dyn(self._asm.FirstFeature))
        while feat:
            ft = _safe(lambda: str(feat.GetTypeName2), "")
            fn = _safe(lambda: str(feat.Name), "")
            if ft == "RefPlane":
                planes.append(fn)
                _log(f"  {fn}")
            feat = _safe(lambda: _dyn(feat.GetNextFeature))
        return planes

    # ─── 探测属性和方程 ──────────────────────────────────────────────
    def probe_properties(self) -> Dict[str, Any]:
        """读取文档自定义属性."""
        props = {}
        try:
            mgr = self._asm.Extension.CustomPropertyManager("")
            names = _safe(lambda: list(mgr.GetNames() or []), [])
            for n in names:
                try:
                    v, _ = mgr.Get4(str(n), False)
                    props[str(n)] = v
                except Exception:
                    props[str(n)] = None
        except Exception:
            pass
        return props

    def probe_equations(self) -> List[Dict[str, Any]]:
        """读取方程."""
        eqs = []
        try:
            em = self._asm.GetEquationMgr()
            if not em:
                em = self._asm.EquationMgr
            n = int(em.GetCount())
            for i in range(n):
                eq = _safe(lambda: em.Equation[i], "?")
                val = _safe(lambda: float(em.Value[i]), None)
                eqs.append({"index": i, "equation": eq, "value": val})
        except Exception:
            pass
        return eqs

    def probe_configurations(self) -> List[str]:
        """读取配置列表."""
        try:
            names = self._asm.GetConfigurationNames()
            if names:
                return [str(n) for n in names]
        except Exception:
            pass
        return []

    # ─── ⑤ 万法映射 · API 能力探测 ──────────────────────────────────
    def probe_api_capabilities(self) -> Dict[str, Any]:
        """探测当前文档可用的 API 方法."""
        _log("═══ API 能力探测 ═══")
        CANDIDATES = {
            "IModelDoc2": [
                "GetTitle", "GetPathName", "GetType", "Extension",
                "SelectionManager", "FirstFeature", "FeatureManager",
                "GetComponentCount", "GetComponents", "EditRebuild3",
                "ForceRebuild3", "Save3", "Save2", "ClearSelection2",
                "GetConfigurationNames", "ConfigurationManager",
            ],
            "IAssemblyDoc": [
                "AddMate5", "AddMate3", "AddSmartMate",
                "FixComponent", "UnfixComponent",
                "HideComponent", "ShowComponent",
                "AddComponent5", "AddComponent4",
                "InterferenceDetectionManager",
                "GetMateCount",
            ],
            "IExtension": [
                "SelectByID2", "SelectByRay", "SaveAs", "SaveAs2",
                "CustomPropertyManager", "CreateSelectData",
            ],
            "ISelectionMgr": [
                "GetSelectedObjectCount2", "GetSelectedObject6",
                "GetSelectedObjectsComponent4", "GetSelectedObjectType3",
            ],
        }
        results = {}
        targets = {
            "IModelDoc2": self._asm,
            "IAssemblyDoc": self._asm,
            "IExtension": self._ext,
            "ISelectionMgr": self._sel,
        }
        for iface, methods in CANDIDATES.items():
            obj = targets.get(iface)
            if not obj:
                continue
            available = {}
            for m in methods:
                try:
                    val = getattr(obj, m)
                    available[m] = "method" if callable(val) else "property"
                except Exception:
                    available[m] = "unavailable"
            results[iface] = available
            avail_count = sum(1 for v in available.values() if v != "unavailable")
            _log(f"  {iface}: {avail_count}/{len(methods)} 可用")

        return results

    # ─── 综合探测 ────────────────────────────────────────────────────
    def full_probe(self) -> Dict[str, Any]:
        """完整逆向探测 · 输出万法报告."""
        _log("道_本源_逆向万法 — 反者道之动 · 万物复归于始")
        _log("=" * 60)

        report = {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}

        # 连接
        conn = self.connect()
        report["connection"] = conn
        if not conn.get("ok"):
            return report

        # 特征树
        features = self.probe_features()
        report["features"] = features

        # 组件
        components = self.probe_components()
        report["components"] = [c.to_dict() for c in components]

        # 配合
        mates = self.probe_mates(features)
        report["mates"] = [m.to_dict() for m in mates]

        # B-Rep
        brep_scans = self.probe_brep()
        report["brep"] = [b.to_dict() for b in brep_scans]

        # 基准面
        ref_planes = self.probe_ref_planes()
        report["ref_planes"] = ref_planes

        # 属性
        report["properties"] = self.probe_properties()

        # 方程
        report["equations"] = self.probe_equations()

        # 配置
        report["configurations"] = self.probe_configurations()

        # API 能力
        report["api"] = self.probe_api_capabilities()

        # 类型库 (可选 — 可能耗时)
        try:
            tl = self.probe_typelib()
            report["typelib_summary"] = {
                "interfaces": len(tl.get("interfaces", {})),
                "enums": len(tl.get("enums", {})),
                "coclasses": len(tl.get("coclasses", [])),
            }
            # 只保存关键接口的方法列表 (避免报告过大)
            key_ifaces = [
                "ISldWorks", "IModelDoc2", "IAssemblyDoc", "IPartDoc",
                "IDrawingDoc", "IComponent2", "IMate2", "IFeature",
                "IBody2", "IFace2", "IEdge", "ISurface",
                "IModelDocExtension", "ISelectionMgr", "IMathUtility",
                "ISketchManager", "IFeatureManager", "IEquationMgr",
            ]
            report["typelib_key_interfaces"] = {}
            for ki in key_ifaces:
                if ki in tl.get("interfaces", {}):
                    iface = tl["interfaces"][ki]
                    report["typelib_key_interfaces"][ki] = {
                        "n_methods": len(iface.get("methods", {})),
                        "n_properties": len(iface.get("properties", {})),
                        "methods": list(iface.get("methods", {}).keys())[:50],
                        "properties": list(iface.get("properties", {}).keys())[:50],
                    }
        except Exception as ex:
            report["typelib_error"] = str(ex)

        # 摘要
        n_fixed = sum(1 for c in components if c.fixed)
        n_free = sum(1 for c in components if not c.fixed and not c.suppressed)
        n_mates_ok = sum(1 for m in mates if m.error_status in (0, None))
        # MemidRegistry 统计
        if self._mreg.loaded:
            report["memid_registry"] = self._mreg.stats()

        report["summary"] = {
            "components": len(components),
            "fixed": n_fixed,
            "free": n_free,
            "mates": len(mates),
            "mates_ok": n_mates_ok,
            "mates_error": len(mates) - n_mates_ok,
            "brep_faces": sum(b.n_faces for b in brep_scans),
            "brep_cylinders": sum(b.n_cylinders for b in brep_scans),
            "ref_planes": len(ref_planes),
            "memid_interfaces": len(self._mreg.list_interfaces()) if self._mreg.loaded else 0,
        }

        _log("")
        _log("═══ 摘要 ═══")
        s = report["summary"]
        _log(f"  组件: {s['components']} (固定={s['fixed']}, 自由={s['free']})")
        _log(f"  配合: {s['mates']} (正常={s['mates_ok']}, 错误={s['mates_error']})")
        _log(f"  B-Rep: {s['brep_faces']} 面, {s['brep_cylinders']} 圆柱面")
        _log(f"  基准面: {s['ref_planes']}")
        if self._mreg.loaded:
            _log(f"  庖丁之刀: {s['memid_interfaces']} interfaces (sldworks.tlb)")

        return report

    # ═══════════════════════════════════════════════════════════════════
    # ⑧ 组件变换矩阵 — via MemidRegistry
    # ═══════════════════════════════════════════════════════════════════
    def probe_transforms(self) -> Dict[str, Any]:
        """提取所有组件的装配上下文变换矩阵 (4x4)."""
        _log("═══ 组件变换矩阵 ═══")
        transforms = {}
        for name, comp in self._comp_map.items():
            xform = self._get_transform(comp)
            if xform:
                transforms[name] = xform
                origin = [round(xform[9] * 1000, 2),
                          round(xform[10] * 1000, 2),
                          round(xform[11] * 1000, 2)]
                _log(f"  {name}: origin=({origin[0]}, {origin[1]}, {origin[2]}) mm")
        _log(f"  共 {len(transforms)} 个变换")
        return transforms

    def _get_transform(self, comp) -> Optional[List[float]]:
        """提取组件 Transform2 → 16 元素数组 (3x3 rotation + translation + scale)."""
        # 路 0: memid
        if self._mreg.loaded:
            try:
                oleobj = comp._oleobj_ if hasattr(comp, "_oleobj_") else comp
                import pythoncom
                mid = self._mreg.memid("IComponent2", "Transform2")
                if mid is not None:
                    xf_raw = oleobj.Invoke(
                        mid, 0,
                        pythoncom.DISPATCH_METHOD | pythoncom.DISPATCH_PROPERTYGET,
                        True
                    )
                    if xf_raw is not None:
                        arr_mid = self._mreg.memid("IMathTransform", "ArrayData")
                        if arr_mid is not None:
                            arr = xf_raw.Invoke(
                                arr_mid, 0,
                                pythoncom.DISPATCH_METHOD | pythoncom.DISPATCH_PROPERTYGET,
                                True
                            )
                            if arr and len(arr) >= 12:
                                return [float(x) for x in arr]
            except Exception:
                pass
        # 回退: 动态分派
        try:
            xf = _dyn(comp.Transform2)
            if xf:
                arr = xf.ArrayData
                if callable(arr):
                    arr = arr()
                if arr and len(arr) >= 12:
                    return [float(x) for x in arr]
        except Exception:
            pass
        return None

    # ═══════════════════════════════════════════════════════════════════
    # ⑨ 完整拓扑 — Edge/Vertex via MemidRegistry
    # ═══════════════════════════════════════════════════════════════════
    def probe_topology(self, comp_names: Optional[List[str]] = None) -> Dict[str, Any]:
        """提取 B-Rep 完整拓扑: face→edge→vertex + 边曲线类型."""
        _log("═══ 拓扑分析 ═══")
        if comp_names is None:
            seen = set()
            comp_names = []
            for name in self._comp_map:
                stem = name.rsplit("-", 1)[0]
                if stem not in seen:
                    seen.add(stem)
                    comp_names.append(name)

        result = {}
        for name in comp_names:
            comp = self._comp_map.get(name)
            if not comp:
                continue
            topo = self._extract_topology(comp, name)
            if topo:
                result[name] = topo
                _log(f"  {name}: {topo['n_faces']}F {topo['n_edges']}E {topo['n_vertices']}V")

        return result

    def _extract_topology(self, comp, name: str) -> Optional[Dict]:
        """单组件拓扑提取."""
        try:
            mdoc = _dyn(comp.GetModelDoc2)
            if not mdoc:
                return None
            bodies = _safe(lambda: mdoc.GetBodies2(0, False))
            if not bodies:
                return None
            body = _dyn(bodies[0])

            n_faces = _safe(lambda: int(body.GetFaceCount()), 0)
            n_edges = _safe(lambda: int(body.GetEdgeCount()), 0)
            n_verts = _safe(lambda: int(body.GetVertexCount()), 0)

            # 边类型统计 via memid
            edge_types = Counter()
            if self._mreg.loaded:
                import pythoncom
                edges_raw = _safe(lambda: body.GetEdges())
                if edges_raw:
                    for e_raw in edges_raw:
                        try:
                            eole = e_raw._oleobj_ if hasattr(e_raw, "_oleobj_") else e_raw
                            # IEdge.GetCurve → ICurve.Identity
                            gc_mid = self._mreg.memid("IEdge", "GetCurve")
                            if gc_mid:
                                crv = eole.Invoke(
                                    gc_mid, 0,
                                    pythoncom.DISPATCH_METHOD | pythoncom.DISPATCH_PROPERTYGET,
                                    True
                                )
                                if crv:
                                    id_mid = self._mreg.memid("ICurve", "Identity")
                                    if id_mid:
                                        cid = int(crv.Invoke(
                                            id_mid, 0,
                                            pythoncom.DISPATCH_METHOD | pythoncom.DISPATCH_PROPERTYGET,
                                            True
                                        ))
                                        CURVE_MAP = {
                                            3001: "line", 3002: "circle", 3003: "ellipse",
                                            3004: "intersection", 3005: "bcurve",
                                            3006: "spcurve", 3007: "constparam",
                                            3008: "trimmed",
                                        }
                                        edge_types[CURVE_MAP.get(cid, f"unknown_{cid}")] += 1
                        except Exception:
                            continue

            return {
                "n_faces": n_faces,
                "n_edges": n_edges,
                "n_vertices": n_verts,
                "edge_types": dict(edge_types),
            }
        except Exception:
            return None

    # ═══════════════════════════════════════════════════════════════════
    # ⑩ 健康检查 — DOF + 配合错误 + 干涉
    # ═══════════════════════════════════════════════════════════════════
    def health_check(self, mates: Optional[List[MateInfo]] = None,
                     components: Optional[List[ComponentInfo]] = None) -> Dict[str, Any]:
        """装配体健康诊断: DOF 分析, 配合错误, 冗余固定."""
        _log("═══ 健康检查 ═══")
        issues = []

        if components is None:
            components = self.probe_components()
        if mates is None:
            features = self.probe_features()
            mates = self.probe_mates(features)

        # 1. 欠约束组件 (非固定, 非抑制)
        free_comps = [c for c in components
                      if not c.fixed and not c.suppressed]
        mated_comps = set()
        for m in mates:
            for ec in m.entity_comps:
                mated_comps.add(ec)

        for c in free_comps:
            if c.name not in mated_comps:
                issues.append({
                    "type": "underconstrained",
                    "severity": "critical",
                    "component": c.name,
                    "msg": f"自由组件 {c.name} 无任何配合",
                })
            else:
                # 计算配合数
                n_mates = sum(1 for m in mates
                              if c.name in m.entity_comps)
                if n_mates < 3:
                    issues.append({
                        "type": "underconstrained",
                        "severity": "warning",
                        "component": c.name,
                        "msg": f"自由组件 {c.name} 仅 {n_mates} 个配合 (可能欠约束)",
                    })

        # 2. 配合错误
        for m in mates:
            if m.error_status not in (0, None):
                issues.append({
                    "type": "mate_error",
                    "severity": "critical",
                    "mate": m.name,
                    "error_code": m.error_status,
                    "msg": f"配合 {m.name} 错误 (code={m.error_status})",
                })

        # 3. 过度固定 (所有组件都被固定, 配合无意义)
        n_fixed = sum(1 for c in components if c.fixed)
        n_total = len(components)
        if n_total > 1 and n_fixed == n_total:
            issues.append({
                "type": "overconstrained",
                "severity": "info",
                "msg": f"所有 {n_total} 个组件均被固定, 配合可能冗余",
            })

        # 4. 重复配合检测
        mate_pairs = Counter()
        for m in mates:
            pair = tuple(sorted(m.entity_comps[:2]))
            mate_pairs[pair] += 1
        for pair, count in mate_pairs.items():
            if count > 3:
                issues.append({
                    "type": "redundant_mates",
                    "severity": "warning",
                    "components": list(pair),
                    "count": count,
                    "msg": f"{pair[0]} ↔ {pair[1]} 有 {count} 个配合 (可能冗余)",
                })

        # 输出
        for issue in issues:
            icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(
                issue["severity"], "⚪")
            _log(f"  {icon} [{issue['type']}] {issue['msg']}")

        if not issues:
            _log("  ✅ 无问题")

        return {
            "n_issues": len(issues),
            "critical": sum(1 for i in issues if i["severity"] == "critical"),
            "warning": sum(1 for i in issues if i["severity"] == "warning"),
            "issues": issues,
        }

    # ═══════════════════════════════════════════════════════════════════
    # ⑪ 全链路闭环循环 — 周行而不殆
    # ═══════════════════════════════════════════════════════════════════
    def full_cycle(self, auto_fix: bool = False) -> Dict[str, Any]:
        """完整闭环: 探→析→为→验→报 · 我无为你无不为.

        探 (probe):  全链路状态快照
        析 (analyze): 健康诊断 + DOF 分析
        为 (act):     auto_fix=True 时自动修复 (固定欠约束组件)
        验 (verify):  Rebuild + 二次探测验证
        报 (report):  输出完整闭环报告 (含 delta)
        """
        _log("道_本源_逆向万法 — 反者道之动 · 周行而不殆")
        _log("═" * 60)
        _log("═══ 闭环循环 · 探→析→为→验→报 ═══")
        cycle = {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}

        # ── 探 ──
        _log("\n┌─ 探 (Probe) ─────────────────────────────────────")
        conn = self.connect()
        cycle["connection"] = conn
        if not conn.get("ok"):
            return cycle

        features = self.probe_features()
        components = self.probe_components()
        mates = self.probe_mates(features)
        brep = self.probe_brep()
        transforms = self.probe_transforms()
        topology = self.probe_topology()

        cycle["probe"] = {
            "features": features,
            "components": [c.to_dict() for c in components],
            "mates": [m.to_dict() for m in mates],
            "brep": [b.to_dict() for b in brep],
            "transforms": {k: v[:3] + ["..."] for k, v in transforms.items()},
            "topology": topology,
        }

        # ── 析 ──
        _log("\n├─ 析 (Analyze) ──────────────────────────────────")
        health = self.health_check(mates, components)
        cycle["health"] = health

        # ── 为 ──
        actions_taken = []
        fixable = health["critical"] + health["warning"]
        if auto_fix and fixable > 0:
            _log("\n├─ 为 (Act · 自动修复) ───────────────────────────")
            for issue in health["issues"]:
                if issue["type"] == "underconstrained":
                    comp_name = issue["component"]
                    _log(f"  → 固定欠约束组件: {comp_name} [{issue['severity']}]")
                    self._set_fixed(comp_name, True)
                    actions_taken.append({
                        "action": "fix_component",
                        "component": comp_name,
                        "reason": issue["msg"],
                    })
            # Rebuild
            if actions_taken:
                _log("  → 重建模型...")
                self.rebuild(force=True)
        else:
            _log("\n├─ 为 (Act · 无为) ──────────────────────────────")
            if fixable == 0:
                _log("  无需操作")
            else:
                _log(f"  {fixable} 个问题待手动修复 (auto_fix=False)")

        cycle["actions"] = actions_taken

        # ── 验 ──
        _log("\n├─ 验 (Verify) ──────────────────────────────────")
        if actions_taken:
            self._build_comp_map()
            components2 = self.probe_components()
            features2 = self.probe_features()
            mates2 = self.probe_mates(features2)
            health2 = self.health_check(mates2, components2)
            cycle["verify"] = {
                "health_after": health2,
                "issues_resolved": health["n_issues"] - health2["n_issues"],
            }
            _log(f"  修复前: {health['n_issues']} 问题")
            _log(f"  修复后: {health2['n_issues']} 问题")
            _log(f"  已解决: {health['n_issues'] - health2['n_issues']}")
        else:
            cycle["verify"] = {"skipped": True}
            _log("  跳过 (无操作)")

        # ── 报 ──
        _log("\n└─ 报 (Report) ──────────────────────────────────")

        # MemidRegistry 全景
        if self._mreg.loaded:
            cycle["memid_registry"] = self._mreg.stats()

        n_fixed = sum(1 for c in components if c.fixed)
        n_free = sum(1 for c in components if not c.fixed and not c.suppressed)
        cycle["summary"] = {
            "components": len(components),
            "fixed": n_fixed,
            "free": n_free,
            "mates": len(mates),
            "mates_ok": sum(1 for m in mates if m.error_status in (0, None)),
            "brep_faces": sum(b.n_faces for b in brep),
            "brep_cylinders": sum(b.n_cylinders for b in brep),
            "topology_edges": sum(t.get("n_edges", 0) for t in topology.values()),
            "topology_vertices": sum(t.get("n_vertices", 0) for t in topology.values()),
            "health_issues": health["n_issues"],
            "actions_taken": len(actions_taken),
            "memid_interfaces": len(self._mreg.list_interfaces()) if self._mreg.loaded else 0,
        }

        s = cycle["summary"]
        _log(f"  组件: {s['components']} (固定={s['fixed']}, 自由={s['free']})")
        _log(f"  配合: {s['mates']} (正常={s['mates_ok']})")
        _log(f"  B-Rep: {s['brep_faces']} 面, {s['brep_cylinders']} 圆柱面")
        _log(f"  拓扑: {s['topology_edges']} 边, {s['topology_vertices']} 顶点")
        _log(f"  健康: {s['health_issues']} 问题, {s['actions_taken']} 操作")
        if self._mreg.loaded:
            _log(f"  庖丁之刀: {s['memid_interfaces']} interfaces")
        _log("")
        _log("闭环完成 · 周行而不殆")

        return cycle


# ════════════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════════════
def _save_report(report: Dict, name: str = "_逆向万法"):
    """保存报告到调用目录."""
    cwd = Path.cwd()
    json_path = cwd / f"{name}_report.json"
    log_path = cwd / f"{name}_log.txt"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(_LOG))
    _log(f"\n报告: {json_path}")
    _log(f"日志: {log_path}")


def main():
    import argparse
    ap = argparse.ArgumentParser(
        description="道_本源_逆向万法 — 反者道之动 · SolidWorks 逆向万法"
    )
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("probe", help="完整逆向探测")
    sub.add_parser("typelib", help="类型库枚举")
    sub.add_parser("components", help="组件状态")
    sub.add_parser("mates", help="配合详情")
    sub.add_parser("brep", help="B-Rep 几何")
    sub.add_parser("api-map", help="API 能力映射")
    sub.add_parser("features", help="特征树")
    sub.add_parser("cycle", help="闭环循环 · 探→析→为→验→报 (只读)")
    sub.add_parser("cycle-fix", help="闭环循环 + 自动修复")
    sub.add_parser("transforms", help="组件变换矩阵")
    sub.add_parser("topology", help="B-Rep 拓扑分析")
    sub.add_parser("health", help="装配体健康检查")
    sub.add_parser("deep", help="庖丁解牛 · 终极解构 (六路并行)")
    sub.add_parser("memid", help="MemidRegistry 统计")

    args = ap.parse_args()
    cmd = args.cmd or "probe"

    rev = SWReverse()

    if cmd == "probe":
        report = rev.full_probe()
        _save_report(report)

    elif cmd == "typelib":
        conn = rev.connect()
        if conn.get("ok"):
            tl = rev.probe_typelib()
            _save_report({"typelib": tl}, "_逆向_typelib")

    elif cmd == "components":
        conn = rev.connect()
        if conn.get("ok"):
            comps = rev.probe_components()
            _save_report(
                {"components": [c.to_dict() for c in comps]},
                "_逆向_components"
            )

    elif cmd == "mates":
        conn = rev.connect()
        if conn.get("ok"):
            features = rev.probe_features()
            mates = rev.probe_mates(features)
            _save_report(
                {"mates": [m.to_dict() for m in mates]},
                "_逆向_mates"
            )

    elif cmd == "brep":
        conn = rev.connect()
        if conn.get("ok"):
            rev.probe_components()  # build comp_map
            scans = rev.probe_brep()
            _save_report(
                {"brep": [s.to_dict() for s in scans]},
                "_逆向_brep"
            )

    elif cmd == "api-map":
        conn = rev.connect()
        if conn.get("ok"):
            api = rev.probe_api_capabilities()
            _save_report({"api": api}, "_逆向_api")

    elif cmd == "features":
        conn = rev.connect()
        if conn.get("ok"):
            features = rev.probe_features()
            _save_report({"features": features}, "_逆向_features")

    elif cmd == "cycle":
        report = rev.full_cycle(auto_fix=False)
        _save_report(report, "_逆向_cycle")

    elif cmd == "cycle-fix":
        report = rev.full_cycle(auto_fix=True)
        _save_report(report, "_逆向_cycle")

    elif cmd == "transforms":
        conn = rev.connect()
        if conn.get("ok"):
            rev.probe_components()
            xf = rev.probe_transforms()
            _save_report({"transforms": xf}, "_逆向_transforms")

    elif cmd == "topology":
        conn = rev.connect()
        if conn.get("ok"):
            rev.probe_components()
            topo = rev.probe_topology()
            _save_report({"topology": topo}, "_逆向_topology")

    elif cmd == "health":
        conn = rev.connect()
        if conn.get("ok"):
            health = rev.health_check()
            _save_report({"health": health}, "_逆向_health")

    elif cmd == "deep":
        from 道_庖丁解牛 import run_deep_deconstruction, _save_results
        report = run_deep_deconstruction("all")
        _save_results(report)

    elif cmd == "memid":
        mreg = MemidRegistry()
        try:
            import dao_solidworks as _sw
            info = _sw.sw_info()
            mreg.load(sw_exe=info.exe)
        except Exception:
            mreg.load()
        if mreg.loaded:
            stats = mreg.stats()
            _log(f"MemidRegistry: {stats['tlb_name']}")
            _log(f"  总类型: {stats['total_types']}")
            _log(f"  接口: {stats['interfaces_loaded']}")
            _log("  Top 接口 (按方法数):")
            for k, v in stats["top_interfaces"].items():
                _log(f"    {k}: {v} 方法")
            _save_report({"memid_stats": stats}, "_逆向_memid")
        else:
            _log("MemidRegistry 加载失败")


if __name__ == "__main__":
    main()
