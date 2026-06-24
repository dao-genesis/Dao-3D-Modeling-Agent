#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
道_庖丁解牛.py — 目无全牛 · 以神遇而不以目视 · 依乎天理
═══════════════════════════════════════════════════════════════════════

    "庖丁为文惠君解牛，手之所触，肩之所倚，足之所履，膝之所踦，
     砉然向然，奏刀騞然，莫不中音。"

    "臣之所好者道也，进乎技矣。始臣之解牛之时，所见无非牛者。
     三年之后，未尝见全牛也。方今之时，臣以神遇而不以目视，
     官知止而神欲行。依乎天理，批大郤，导大窾，因其固然。"

SolidWorks COM 对象模型 · 终极解构
══════════════════════════════════
不依赖 TypeLib 注册, 不依赖 .tlb 文件.
从活体 COM 对象出发, 以 ITypeInfo 递归反射一切可达接口.

六路并行:
  路零 · 活体递归反射 — 从 ISldWorks 出发, 每个方法返回类型递归发现新接口
  路壹 · EXE 内嵌 TypeLib — pythoncom.LoadTypeLib(SLDWORKS.exe)
  路贰 · 注册表全扫 — HKLM\TypeLib 下所有 SolidWorks 相关
  路叁 · 安装目录文件扫描 — *.tlb *.olb *.dll *.exe 全部尝试加载
  路肆 · PE 资源段 — 读 SLDWORKS.exe 的 RT_TYPELIB 资源
  路伍 · ProgID → CLSID → TypeLib GUID 链式追踪

输出:
  _庖丁解牛_report.json  — 完整对象模型 (接口/方法/属性/参数/返回类型/继承)
  _庖丁解牛_graph.json   — 接口引用关系图 (A.Method() → returns B)
  _庖丁解牛_log.txt      — 全过程日志

用法:
  python 道_庖丁解牛.py                # 全部六路
  python 道_庖丁解牛.py live           # 仅活体递归反射
  python 道_庖丁解牛.py typelib        # 仅 TypeLib 合并
  python 道_庖丁解牛.py graph          # 仅接口关系图
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ── 路径引导 ──────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_DAO_ROOT = next(
    (p for p in Path(__file__).resolve().parents if (p / "_paths.py").is_file()),
    _HERE.parent,
)
for _d in (_DAO_ROOT, _HERE):
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

__version__ = "2.0.0"  # 融合版 · 与逆向万法共享解析引擎

__all__ = [
    "LiveReflector", "run_deep_deconstruction", "_save_results",
    "_resolve_typedesc", "_HREF_NAME_CACHE", "_VT_NAMES",
    "_scan_registry_typelibs", "_find_sw_install_dir",
    "_try_load_typelib", "_scan_directory_for_typelibs",
]

# ── 日志 ──────────────────────────────────────────────────────────────
_LOG: List[str] = []


def _log(msg: str):
    print(msg)
    _LOG.append(msg)


# ── COM 工具 ──────────────────────────────────────────────────────────
def _dyn(obj):
    """包装为纯动态 IDispatch."""
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


# ════════════════════════════════════════════════════════════════════════
# TYPEDESC 解析 — 从 ITypeInfo 的 TYPEDESC 结构提取类型名
# ════════════════════════════════════════════════════════════════════════

# pythoncom VT 常量 → 人类可读名
_VT_NAMES = {
    0: "VT_EMPTY", 2: "short", 3: "long", 4: "float", 5: "double",
    6: "CY", 7: "DATE", 8: "BSTR", 9: "IDispatch*", 10: "SCODE",
    11: "bool", 12: "VARIANT", 13: "IUnknown*", 16: "i1", 17: "ui1",
    18: "ui2", 19: "ui4", 20: "i8", 21: "ui8", 22: "int", 23: "uint",
    24: "void", 25: "HRESULT", 26: "PTR", 27: "SAFEARRAY", 28: "CARRAY",
    29: "USERDEFINED", 36: "RECORD",
}


# href → name 全局缓存 (跨 TypeLib 积累)
_HREF_NAME_CACHE: Dict[int, str] = {}


def _resolve_typedesc(ti, td) -> str:
    """递归解析 TYPEDESC 为人类可读类型字符串.

    pythoncom 的 fd.rettype / fd.args[i] 返回 ELEMDESC 格式:
      (typedesc, paramdesc_flags, default_value)
    其中 typedesc 可以是:
      - int (简单 VT, 如 24=void, 9=IDispatch*)
      - (vt, sub) 嵌套 (如 (26, (29, href)) = PTR→USERDEFINED)
    本函数递归解析 typedesc 部分.
    """
    if td is None:
        return "?"
    try:
        if isinstance(td, int):
            return _VT_NAMES.get(td, f"vt_{td}")
        if isinstance(td, tuple):
            # 检测 ELEMDESC 3-tuple: (typedesc, flags, default)
            # 特征: len==3, td[1] 是 int (flags), td[2] 是 None 或默认值
            if (len(td) == 3
                    and isinstance(td[1], int)
                    and (td[2] is None or isinstance(td[2], (int, float, str)))):
                # td[0] 是实际 typedesc
                return _resolve_typedesc(ti, td[0])
            vt = td[0] if len(td) > 0 else 0
            if isinstance(vt, tuple):
                # 嵌套 ELEMDESC — 直接递归内层
                return _resolve_typedesc(ti, vt)
            if vt == 26 and len(td) > 1:  # VT_PTR → dereference
                inner = _resolve_typedesc(ti, td[1])
                if inner.startswith("vt_"):
                    return inner  # 不重复加 *
                return f"{inner}*"
            if vt == 29 and len(td) > 1:  # VT_USERDEFINED → resolve href
                href = td[1]
                # 先查缓存
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
                inner = _resolve_typedesc(ti, td[1])
                return f"SAFEARRAY({inner})"
            if vt == 28 and len(td) > 1:  # VT_CARRAY
                inner = _resolve_typedesc(ti, td[1])
                return f"{inner}[]"
            if vt == 36 and len(td) > 1:  # VT_RECORD
                try:
                    ref_ti = ti.GetRefTypeInfo(td[1])
                    return ref_ti.GetDocumentation(-1)[0]
                except Exception:
                    pass
            return _VT_NAMES.get(vt, f"vt_{vt}")
        return str(td)
    except Exception:
        return f"?({td})"


# ════════════════════════════════════════════════════════════════════════
# 路零 · 活体递归反射 — 从 IDispatch.GetTypeInfo(0) 深入
# ════════════════════════════════════════════════════════════════════════

class LiveReflector:
    """从活体 COM 对象递归反射接口, 追踪方法返回类型发现新接口."""

    def __init__(self):
        self.interfaces: Dict[str, Dict[str, Any]] = {}
        self.graph_edges: List[Dict[str, str]] = []  # {from, method, to}
        self._visited_iids: Set[str] = set()
        self._pending_typeinfos: List[Tuple[str, Any]] = []  # (label, ITypeInfo)
        self._discovered_refs: Dict[str, str] = {}  # href_name → source

    def reflect_object(self, obj, label: str = "root", depth: int = 0,
                       max_depth: int = 3):
        """从 COM 对象提取 ITypeInfo 并递归反射."""
        if depth > max_depth:
            return
        if obj is None:
            return
        try:
            oleobj = obj._oleobj_
            ti = oleobj.GetTypeInfo(0)
        except Exception:
            return
        self._reflect_typeinfo(ti, label, depth, max_depth)

    def _reflect_typeinfo(self, ti, label: str, depth: int, max_depth: int):
        """从 ITypeInfo 提取完整接口定义."""
        try:
            ta = ti.GetTypeAttr()
        except Exception:
            return

        iid = str(ta.iid)
        if iid in self._visited_iids:
            return
        self._visited_iids.add(iid)

        try:
            name = ti.GetDocumentation(-1)[0]
        except Exception:
            name = label

        _log(f"{'  ' * depth}● {name} (IID={iid}, {ta.cFuncs}F {ta.cVars}V)")

        iface = {
            "name": name,
            "iid": iid,
            "label": label,
            "kind": ta.typekind,  # 3=INTERFACE, 4=DISPATCH
            "methods": {},
            "properties": {},
            "vars": {},
            "n_funcs": ta.cFuncs,
            "n_vars": ta.cVars,
            "n_impl": ta.cImplTypes,
            "inherited_from": [],
            "discovered_refs": [],
        }

        # ─── 继承链 ──────────────────────────────────────────────
        for impl_idx in range(ta.cImplTypes):
            try:
                href = ti.GetRefTypeOfImplType(impl_idx)
                ref_ti = ti.GetRefTypeInfo(href)
                ref_name = ref_ti.GetDocumentation(-1)[0]
                iface["inherited_from"].append(ref_name)
                # 递归反射父接口
                self._reflect_typeinfo(ref_ti, f"{name}→{ref_name}",
                                       depth + 1, max_depth)
            except Exception:
                continue

        # ─── 方法 & 属性 ─────────────────────────────────────────
        for j in range(ta.cFuncs):
            try:
                fd = ti.GetFuncDesc(j)
                fname = ti.GetNames(fd.memid)[0]
                all_names = ti.GetNames(fd.memid)
                param_names = list(all_names[1:]) if len(all_names) > 1 else []

                # 返回类型
                ret_type = "void"
                try:
                    ret_td = fd.rettype
                    ret_type = _resolve_typedesc(ti, ret_td)
                except Exception:
                    pass

                # 参数类型
                param_types = []
                try:
                    for pi in range(len(fd.args)):
                        arg_td = fd.args[pi]
                        # arg_td 是 (typedesc, paramdesc_flags) 或直接 typedesc
                        if isinstance(arg_td, tuple) and len(arg_td) >= 1:
                            pt = _resolve_typedesc(ti, arg_td[0] if isinstance(arg_td[0], (tuple, int)) else arg_td)
                        else:
                            pt = _resolve_typedesc(ti, arg_td)
                        param_types.append(pt)
                except Exception:
                    pass

                # 构建参数列表
                params = []
                for pi in range(max(len(param_names), len(param_types))):
                    pn = param_names[pi] if pi < len(param_names) else f"p{pi}"
                    pt = param_types[pi] if pi < len(param_types) else "?"
                    params.append({"name": pn, "type": pt})

                invkind = fd.invkind
                entry = {
                    "memid": fd.memid,
                    "params": params,
                    "return_type": ret_type,
                    "invkind": invkind,
                }

                if invkind == 1:  # INVOKE_FUNC
                    iface["methods"][fname] = entry
                    # 追踪返回类型 → 发现新接口
                    _SKIP_TYPES = frozenset({
                        "void", "bool", "short", "long", "float", "double",
                        "BSTR", "VARIANT", "HRESULT", "?", "int", "uint",
                        "DATE", "CY", "IDispatch*", "IUnknown*",
                        "IDispatch", "IUnknown", "SCODE",
                    })
                    if ret_type not in _SKIP_TYPES:
                        clean_ret = ret_type.rstrip("*")
                        if (clean_ret
                                and clean_ret not in self._discovered_refs
                                and not clean_ret.startswith("href:")
                                and not clean_ret.startswith("vt_")):
                            self._discovered_refs[clean_ret] = f"{name}.{fname}()"
                            iface["discovered_refs"].append(clean_ret)
                            self.graph_edges.append({
                                "from": name, "method": fname, "to": clean_ret
                            })
                elif invkind in (2, 4, 8):  # PROPERTYGET/PUT/PUTREF
                    pk = {2: "get", 4: "put", 8: "putref"}.get(invkind, "?")
                    if fname not in iface["properties"]:
                        iface["properties"][fname] = {"accessors": {}}
                    iface["properties"][fname]["accessors"][pk] = entry
                    # 属性 getter 返回类型也追踪
                    if pk == "get" and ret_type not in _SKIP_TYPES:
                        clean_ret = ret_type.rstrip("*")
                        if (clean_ret
                                and clean_ret not in self._discovered_refs
                                and not clean_ret.startswith("href:")
                                and not clean_ret.startswith("vt_")
                                and not clean_ret.startswith("?(")):
                            self._discovered_refs[clean_ret] = f"{name}.{fname}"
                            iface["discovered_refs"].append(clean_ret)
                            self.graph_edges.append({
                                "from": name, "via_prop": fname, "to": clean_ret
                            })
            except Exception:
                continue

        # ─── 变量 (枚举值等) ──────────────────────────────────────
        for j in range(ta.cVars):
            try:
                vd = ti.GetVarDesc(j)
                vname = ti.GetNames(vd.memid)[0]
                iface["vars"][vname] = vd.value
            except Exception:
                continue

        self.interfaces[name] = iface

    @staticmethod
    def _warm_href_cache(tlib):
        """预热 href→name 缓存: 枚举 TypeLib 所有类型, 对每个 ITypeInfo
        尝试获取其 hRefType 并映射到名称. 这样后续 _resolve_typedesc 中
        遇到跨 TypeLib 的 USERDEFINED 引用时也能解析."""
        count = tlib.GetTypeInfoCount()
        for i in range(count):
            try:
                ti = tlib.GetTypeInfo(i)
                name = tlib.GetDocumentation(i)[0]
                ta = ti.GetTypeAttr()
                # 对每个实现的接口, 缓存其 href→name
                for impl_idx in range(ta.cImplTypes):
                    try:
                        href = ti.GetRefTypeOfImplType(impl_idx)
                        if href not in _HREF_NAME_CACHE:
                            ref_ti = ti.GetRefTypeInfo(href)
                            ref_name = ref_ti.GetDocumentation(-1)[0]
                            _HREF_NAME_CACHE[href] = ref_name
                    except Exception:
                        continue
                # 对每个函数的返回类型和参数, 预解析 USERDEFINED
                for j in range(ta.cFuncs):
                    try:
                        fd = ti.GetFuncDesc(j)
                        for td in [fd.rettype] + list(fd.args or []):
                            LiveReflector._cache_td_hrefs(ti, td)
                    except Exception:
                        continue
            except Exception:
                continue

    @staticmethod
    def _cache_td_hrefs(ti, td):
        """递归扫描 TYPEDESC, 缓存所有 USERDEFINED href."""
        if td is None or isinstance(td, int):
            return
        if not isinstance(td, tuple):
            return
        # 解包 ELEMDESC 3-tuple
        if (len(td) == 3
                and isinstance(td[1], int)
                and (td[2] is None or isinstance(td[2], (int, float, str)))):
            td = td[0]
            if not isinstance(td, tuple):
                return
        if len(td) < 2:
            return
        vt = td[0]
        if isinstance(vt, tuple):
            LiveReflector._cache_td_hrefs(ti, vt)
            return
        if vt == 29:  # VT_USERDEFINED
            href = td[1]
            if href not in _HREF_NAME_CACHE:
                try:
                    ref_ti = ti.GetRefTypeInfo(href)
                    ref_name = ref_ti.GetDocumentation(-1)[0]
                    _HREF_NAME_CACHE[href] = ref_name
                except Exception:
                    pass
        elif vt in (26, 27):  # VT_PTR, VT_SAFEARRAY
            LiveReflector._cache_td_hrefs(ti, td[1])

    def reflect_from_typelib(self, tlib, max_depth: int = 3):
        """从 ITypeLib 枚举所有类型, 递归反射."""
        count = tlib.GetTypeInfoCount()
        _log(f"  TypeLib: {tlib.GetDocumentation(-1)[0]} ({count} types)")
        # 先预热 href 缓存
        self._warm_href_cache(tlib)
        for i in range(count):
            try:
                kind = tlib.GetTypeInfoType(i)
                ti = tlib.GetTypeInfo(i)
                name = tlib.GetDocumentation(i)[0]
                if kind in (3, 4):  # INTERFACE / DISPATCH
                    self._reflect_typeinfo(ti, f"tlib[{i}]", 0, max_depth)
                elif kind == 0:  # ENUM
                    self._reflect_enum(ti, name)
                elif kind == 5:  # COCLASS
                    self._reflect_coclass(ti, tlib, i, name, max_depth)
            except Exception:
                continue

    def _reflect_enum(self, ti, name: str):
        """枚举类型."""
        try:
            ta = ti.GetTypeAttr()
            vals = {}
            for j in range(ta.cVars):
                vd = ti.GetVarDesc(j)
                vname = ti.GetNames(vd.memid)[0]
                vals[vname] = vd.value
            self.interfaces[name] = {
                "name": name, "kind": 0, "is_enum": True,
                "values": vals, "count": len(vals),
            }
        except Exception:
            pass

    def _reflect_coclass(self, ti, tlib, tlib_idx: int, name: str,
                         max_depth: int):
        """CoClass — 提取实现的接口."""
        try:
            ta = ti.GetTypeAttr()
            impl_ifaces = []
            for impl_idx in range(ta.cImplTypes):
                try:
                    href = ti.GetRefTypeOfImplType(impl_idx)
                    ref_ti = ti.GetRefTypeInfo(href)
                    ref_name = ref_ti.GetDocumentation(-1)[0]
                    impl_ifaces.append(ref_name)
                    self._reflect_typeinfo(ref_ti, f"CoClass({name})",
                                           1, max_depth)
                except Exception:
                    continue
            self.interfaces[f"CoClass_{name}"] = {
                "name": name, "kind": 5, "is_coclass": True,
                "implements": impl_ifaces,
            }
        except Exception:
            pass

    def summary(self) -> Dict[str, Any]:
        n_iface = sum(1 for v in self.interfaces.values()
                      if v.get("kind") in (3, 4))
        n_enum = sum(1 for v in self.interfaces.values()
                     if v.get("is_enum"))
        n_coclass = sum(1 for v in self.interfaces.values()
                        if v.get("is_coclass"))
        n_methods = sum(
            len(v.get("methods", {})) for v in self.interfaces.values()
        )
        n_props = sum(
            len(v.get("properties", {})) for v in self.interfaces.values()
        )
        return {
            "interfaces": n_iface,
            "enums": n_enum,
            "coclasses": n_coclass,
            "total_methods": n_methods,
            "total_properties": n_props,
            "graph_edges": len(self.graph_edges),
            "discovered_refs": len(self._discovered_refs),
        }


# ════════════════════════════════════════════════════════════════════════
# 路壹 · EXE/DLL 内嵌 TypeLib
# ════════════════════════════════════════════════════════════════════════

def _try_load_typelib(path: str) -> Optional[Any]:
    """尝试从文件加载 TypeLib."""
    import pythoncom
    try:
        tlib = pythoncom.LoadTypeLib(path)
        return tlib
    except Exception:
        pass
    # 尝试带索引 (有些 EXE 内嵌多个 TypeLib)
    for idx in range(1, 10):
        try:
            tlib = pythoncom.LoadTypeLib(f"{path}\\{idx}")
            return tlib
        except Exception:
            continue
    return None


# ════════════════════════════════════════════════════════════════════════
# 路贰 · 注册表全扫
# ════════════════════════════════════════════════════════════════════════

def _scan_registry_typelibs() -> List[Dict[str, str]]:
    """扫描 HKLM\\SOFTWARE\\Classes\\TypeLib 下所有 SolidWorks 相关."""
    results = []
    try:
        import winreg
        key_path = r"SOFTWARE\Classes\TypeLib"
        hk = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
        i = 0
        while True:
            try:
                guid = winreg.EnumKey(hk, i)
                i += 1
                try:
                    sk = winreg.OpenKey(hk, guid)
                    j = 0
                    while True:
                        try:
                            ver = winreg.EnumKey(sk, j)
                            j += 1
                            vk = winreg.OpenKey(sk, ver)
                            desc, _ = winreg.QueryValueEx(vk, "")
                            if desc and any(kw in desc.lower() for kw in
                                            ("solidworks", "sldworks", "swconst",
                                             "cosmos", "dimxpert", "swutilities",
                                             "swrouting", "swpublished",
                                             "cmotion", "swfeedback",
                                             "designchecker", "macrobuilder")):
                                # 尝试获取 TypeLib 文件路径
                                tlb_path = None
                                for lcid in ("0", "409"):
                                    for platform in ("win32", "win64"):
                                        try:
                                            pk = winreg.OpenKey(
                                                vk, f"{lcid}\\{platform}")
                                            p, _ = winreg.QueryValueEx(pk, "")
                                            if p:
                                                tlb_path = p
                                            winreg.CloseKey(pk)
                                            if tlb_path:
                                                break
                                        except OSError:
                                            continue
                                    if tlb_path:
                                        break
                                results.append({
                                    "guid": guid, "ver": ver,
                                    "desc": desc, "path": tlb_path,
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
    except Exception as ex:
        _log(f"  注册表扫描异常: {ex}")
    return results


# ════════════════════════════════════════════════════════════════════════
# 路叁 · 安装目录文件扫描
# ════════════════════════════════════════════════════════════════════════

def _find_sw_install_dir() -> Optional[str]:
    """多路寻找 SW 安装目录."""
    # 从 dao_solidworks 获取
    try:
        import dao_solidworks as _sw
        info = _sw.sw_info()
        if info.installdir and Path(info.installdir).exists():
            return info.installdir
        if info.exe:
            d = str(Path(info.exe).parent)
            if Path(d).exists():
                return d
    except Exception:
        pass
    # 硬编码常见路径
    for p in [
        r"D:\Program Files\SOLIDWORKS Corp23\SOLIDWORKS",
        r"D:\Program Files\SOLIDWORKS Corp22\SOLIDWORKS",
        r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS",
    ]:
        if Path(p).exists():
            return p
    return None


def _scan_directory_for_typelibs(sw_dir: str) -> List[Dict[str, Any]]:
    """扫描 SW 安装目录下所有可能含 TypeLib 的文件."""
    import glob
    results = []
    for ext in ("*.tlb", "*.olb"):
        for f in glob.glob(os.path.join(sw_dir, "**", ext), recursive=True):
            results.append({"path": f, "type": ext})
    # 也尝试主 EXE 和关键 DLL
    for name in ("SLDWORKS.exe", "sldappu.dll", "swshellutils.dll",
                 "api\\sldworks.tlb", "sldworks.tlb"):
        p = os.path.join(sw_dir, name)
        if os.path.exists(p) and p not in [r["path"] for r in results]:
            results.append({"path": p, "type": "exe/dll"})
    return results


# ════════════════════════════════════════════════════════════════════════
# 路肆 · PE RT_TYPELIB 资源提取 (纯 Python, 无外部依赖)
# ════════════════════════════════════════════════════════════════════════

def _pe_find_typelib_resources(exe_path: str) -> List[Dict[str, Any]]:
    """读 PE 文件, 找 RT_TYPELIB 资源段 (type=8)."""
    import struct
    results = []
    try:
        with open(exe_path, "rb") as f:
            # DOS header
            f.seek(0x3C)
            pe_offset = struct.unpack("<I", f.read(4))[0]
            f.seek(pe_offset)
            sig = f.read(4)
            if sig != b"PE\x00\x00":
                return results

            # COFF header
            machine = struct.unpack("<H", f.read(2))[0]
            n_sections = struct.unpack("<H", f.read(2))[0]
            f.read(12)  # skip timestamp, symtab ptr, n_syms
            opt_hdr_size = struct.unpack("<H", f.read(2))[0]
            f.read(2)  # characteristics

            # Optional header — find resource directory RVA
            opt_start = f.tell()
            magic = struct.unpack("<H", f.read(2))[0]
            is_pe32plus = (magic == 0x20B)

            if is_pe32plus:
                f.seek(opt_start + 112)  # data dirs start at offset 112 for PE32+
            else:
                f.seek(opt_start + 96)   # data dirs start at offset 96 for PE32

            # Data directory [2] = Resource Table
            f.read(16)  # skip export and import
            res_rva = struct.unpack("<I", f.read(4))[0]
            res_size = struct.unpack("<I", f.read(4))[0]

            if res_rva == 0:
                _log(f"  PE: 无资源段")
                return results

            # Find .rsrc section
            f.seek(opt_start + opt_hdr_size)
            rsrc_file_offset = 0
            rsrc_rva = 0
            for _ in range(n_sections):
                sec_name = f.read(8).rstrip(b'\x00').decode('ascii', errors='replace')
                vsize = struct.unpack("<I", f.read(4))[0]
                vrva = struct.unpack("<I", f.read(4))[0]
                raw_size = struct.unpack("<I", f.read(4))[0]
                raw_ptr = struct.unpack("<I", f.read(4))[0]
                f.read(16)  # skip relocs, linenums, etc.
                if sec_name == ".rsrc":
                    rsrc_file_offset = raw_ptr
                    rsrc_rva = vrva
                    break

            if rsrc_file_offset == 0:
                _log(f"  PE: .rsrc 段未找到")
                return results

            results.append({
                "rsrc_offset": rsrc_file_offset,
                "rsrc_rva": rsrc_rva,
                "res_dir_rva": res_rva,
                "found": True,
            })
            _log(f"  PE: .rsrc @ offset=0x{rsrc_file_offset:X}, "
                 f"RVA=0x{rsrc_rva:X}")

    except Exception as ex:
        _log(f"  PE 解析异常: {ex}")
    return results


# ════════════════════════════════════════════════════════════════════════
# 路伍 · ProgID → CLSID → TypeLib GUID 链式追踪
# ════════════════════════════════════════════════════════════════════════

def _chase_progid_to_typelib(progid: str) -> Dict[str, Any]:
    """从 ProgID 追踪到 TypeLib GUID."""
    result = {"progid": progid}
    try:
        import winreg
        # ProgID → CLSID
        try:
            k = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f"{progid}\\CLSID")
            clsid, _ = winreg.QueryValueEx(k, "")
            result["clsid"] = clsid
            winreg.CloseKey(k)
        except OSError:
            return result

        # CLSID → TypeLib
        try:
            k = winreg.OpenKey(
                winreg.HKEY_CLASSES_ROOT, f"CLSID\\{clsid}\\TypeLib")
            tl_guid, _ = winreg.QueryValueEx(k, "")
            result["typelib_guid"] = tl_guid
            winreg.CloseKey(k)
        except OSError:
            pass

        # CLSID → InProcServer32 / LocalServer32
        for server_key in ("InprocServer32", "LocalServer32"):
            try:
                k = winreg.OpenKey(
                    winreg.HKEY_CLASSES_ROOT, f"CLSID\\{clsid}\\{server_key}")
                path, _ = winreg.QueryValueEx(k, "")
                result[server_key.lower()] = path
                winreg.CloseKey(k)
            except OSError:
                continue

        # CLSID → Version
        try:
            k = winreg.OpenKey(
                winreg.HKEY_CLASSES_ROOT, f"CLSID\\{clsid}\\Version")
            ver, _ = winreg.QueryValueEx(k, "")
            result["version"] = ver
            winreg.CloseKey(k)
        except OSError:
            pass

    except Exception as ex:
        result["error"] = str(ex)
    return result


# ════════════════════════════════════════════════════════════════════════
# 活体对象递归遍历 — 从 app 出发获取所有可达子对象
# ════════════════════════════════════════════════════════════════════════

def _probe_live_objects(app) -> Dict[str, Any]:
    """从 SW app 对象获取所有关键子对象, 每个都做 ITypeInfo 反射."""
    import win32com.client.dynamic as _d

    objects = {"ISldWorks": app}

    # 获取活动文档
    doc = None
    try:
        doc = _d.Dispatch(app.ActiveDoc._oleobj_)
        objects["IModelDoc2"] = doc
    except Exception:
        pass

    if doc:
        # 从文档获取各种管理器
        for prop_name, iface_name in [
            ("Extension", "IModelDocExtension"),
            ("SelectionManager", "ISelectionMgr"),
            ("FeatureManager", "IFeatureManager"),
            ("SketchManager", "ISketchManager"),
            ("ConfigurationManager", "IConfigurationManager"),
            ("EquationMgr", "IEquationMgr"),
        ]:
            try:
                sub = getattr(doc, prop_name)
                if sub is not None:
                    if hasattr(sub, '_oleobj_'):
                        sub = _d.Dispatch(sub._oleobj_)
                    objects[iface_name] = sub
            except Exception:
                continue

        # 第一个特征
        try:
            feat = doc.FirstFeature
            if feat:
                if hasattr(feat, '_oleobj_'):
                    feat = _d.Dispatch(feat._oleobj_)
                objects["IFeature"] = feat
        except Exception:
            pass

        # 第一个组件 (装配体)
        try:
            comps = doc.GetComponents(True)
            if comps and len(comps) > 0:
                c = _d.Dispatch(comps[0]._oleobj_)
                objects["IComponent2"] = c
                # 组件的 ModelDoc
                try:
                    mdoc = c.GetModelDoc2
                    if mdoc and hasattr(mdoc, '_oleobj_'):
                        mdoc = _d.Dispatch(mdoc._oleobj_)
                        objects["IModelDoc2_part"] = mdoc
                        # Body
                        try:
                            bodies = mdoc.GetBodies2(0, False)
                            if bodies and len(bodies) > 0:
                                body = _d.Dispatch(bodies[0]._oleobj_)
                                objects["IBody2"] = body
                                # Faces
                                try:
                                    faces = body.GetFaces()
                                    if faces and len(faces) > 0:
                                        face = _d.Dispatch(faces[0]._oleobj_)
                                        objects["IFace2"] = face
                                        # Surface
                                        try:
                                            surf = face.GetSurface()
                                            if surf and hasattr(surf, '_oleobj_'):
                                                surf = _d.Dispatch(surf._oleobj_)
                                                objects["ISurface"] = surf
                                        except Exception:
                                            pass
                                        # Edges from face
                                        try:
                                            edges = face.GetEdges()
                                            if edges and len(edges) > 0:
                                                edge = _d.Dispatch(edges[0]._oleobj_)
                                                objects["IEdge"] = edge
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception:
            pass

        # 配合 (从 MateGroup 特征)
        try:
            feat = doc.FirstFeature
            if hasattr(feat, '_oleobj_'):
                feat = _d.Dispatch(feat._oleobj_)
            while feat:
                ft = str(getattr(feat, 'GetTypeName2', ''))
                if ft == "MateGroup":
                    sub = feat.GetFirstSubFeature()
                    if sub:
                        if hasattr(sub, '_oleobj_'):
                            sub = _d.Dispatch(sub._oleobj_)
                        mate2 = sub.GetSpecificFeature2
                        if mate2 and hasattr(mate2, '_oleobj_'):
                            mate2 = _d.Dispatch(mate2._oleobj_)
                            objects["IMate2"] = mate2
                    break
                feat = feat.GetNextFeature()
                if feat and hasattr(feat, '_oleobj_'):
                    feat = _d.Dispatch(feat._oleobj_)
        except Exception:
            pass

    # MathUtility
    try:
        mu = app.GetMathUtility()
        if mu and hasattr(mu, '_oleobj_'):
            mu = _d.Dispatch(mu._oleobj_)
            objects["IMathUtility"] = mu
    except Exception:
        try:
            mu = app.IGetMathUtility
            if mu and hasattr(mu, '_oleobj_'):
                mu = _d.Dispatch(mu._oleobj_)
                objects["IMathUtility"] = mu
        except Exception:
            pass

    return objects


# ════════════════════════════════════════════════════════════════════════
# 主编排 — 六路并行, 合而为一
# ════════════════════════════════════════════════════════════════════════

def run_deep_deconstruction(mode: str = "all") -> Dict[str, Any]:
    """执行深度解构."""
    _log("道 · 庖丁解牛 — 目无全牛 · 以神遇而不以目视")
    _log("═" * 60)
    _log(f"模式: {mode}")
    _log(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    _log("")

    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mode": mode,
        "version": __version__,
    }

    reflector = LiveReflector()
    do_live = mode in ("all", "live", "graph")
    do_typelib = mode in ("all", "typelib")

    # ═══ TypeLib 先行 (路壹/贰/叁) → 预热 _HREF_NAME_CACHE ═══
    # 这样后续活体反射的 VT_USERDEFINED 引用都能解析成接口名

    # ─── 路壹 · EXE 内嵌 TypeLib ─────────────────────────────────
    if do_typelib or mode == "all":
        _log("\n═══ 路壹 · EXE 内嵌 TypeLib ═══")
        sw_dir = _find_sw_install_dir()
        if sw_dir:
            exe_path = os.path.join(sw_dir, "SLDWORKS.exe")
            _log(f"  SW dir: {sw_dir}")
            _log(f"  EXE: {exe_path}")
            tlib = _try_load_typelib(exe_path)
            if tlib:
                _log(f"  成功! 加载 EXE TypeLib")
                reflector.reflect_from_typelib(tlib, max_depth=3)
                s = reflector.summary()
                _log(f"  路壹后: {s['interfaces']} 接口 (+{s['enums']} 枚举)")
            else:
                _log(f"  EXE TypeLib 加载失败 — SW 可能未内嵌")
        else:
            _log(f"  SW 安装目录未找到")

    # ─── 路贰 · 注册表全扫 ───────────────────────────────────────
    if do_typelib or mode == "all":
        _log("\n═══ 路贰 · 注册表全扫 ═══")
        reg_libs = _scan_registry_typelibs()
        _log(f"  找到 {len(reg_libs)} 个 SolidWorks TypeLib")
        report["registry_typelibs"] = reg_libs

        for lib in reg_libs:
            try:
                import pythoncom
                guid = lib["guid"]
                ver_str = lib["ver"]
                parts = ver_str.split(".")
                major = int(parts[0], 16) if parts else 0
                minor = int(parts[1], 16) if len(parts) > 1 else 0
                tlib = pythoncom.LoadRegTypeLib(guid, major, minor, 0)
                name = tlib.GetDocumentation(-1)[0]
                n_types = tlib.GetTypeInfoCount()
                _log(f"    {name}: {n_types} types")
                reflector.reflect_from_typelib(tlib, max_depth=2)
            except Exception:
                _log(f"    {lib['desc']}: 加载失败")
                continue

        s = reflector.summary()
        _log(f"  路贰后: {s['interfaces']} 接口, {s['enums']} 枚举")

    # ─── 路叁 · 安装目录文件扫描 ─────────────────────────────────
    if do_typelib or mode == "all":
        _log("\n═══ 路叁 · 安装目录文件扫描 ═══")
        sw_dir = _find_sw_install_dir()
        if sw_dir:
            files = _scan_directory_for_typelibs(sw_dir)
            _log(f"  找到 {len(files)} 个候选文件")
            loaded = 0
            for fi in files:
                tlib = _try_load_typelib(fi["path"])
                if tlib:
                    try:
                        name = tlib.GetDocumentation(-1)[0]
                        cnt = tlib.GetTypeInfoCount()
                        _log(f"    ✓ {os.path.basename(fi['path'])}: "
                             f"{name} ({cnt} types)")
                        reflector.reflect_from_typelib(tlib, max_depth=2)
                        loaded += 1
                    except Exception:
                        pass
            _log(f"  成功加载 {loaded}/{len(files)} 个文件")
        else:
            _log(f"  SW 安装目录未找到")

    # ─── 路零 · 活体递归反射 (在 TypeLib 缓存预热后) ─────────────
    if do_live:
        _log("\n═══ 路零 · 活体递归反射 ═══")
        _log(f"  href 缓存已有 {len(_HREF_NAME_CACHE)} 条映射")
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()

            app = win32com.client.GetActiveObject("SldWorks.Application")
            app = _dyn(app)
            rev = "?"
            try:
                rev = str(app.RevisionNumber)
            except Exception:
                pass
            _log(f"  SW rev={rev}")

            _log("  收集活体对象...")
            live_objects = _probe_live_objects(app)
            _log(f"  发现 {len(live_objects)} 个活体对象: "
                 f"{', '.join(live_objects.keys())}")

            _log("  递归反射...")
            for label, obj in live_objects.items():
                try:
                    reflector.reflect_object(obj, label=label, max_depth=4)
                except Exception as ex:
                    _log(f"  {label} 反射失败: {ex}")

            s = reflector.summary()
            _log(f"\n  路零结果: {s['interfaces']} 接口, "
                 f"{s['total_methods']} 方法, "
                 f"{s['total_properties']} 属性, "
                 f"{s['graph_edges']} 引用边")

            report["live_reflection"] = s
            report["live_objects"] = list(live_objects.keys())

        except Exception as ex:
            _log(f"  路零失败: {ex}")
            traceback.print_exc()
            report["live_error"] = str(ex)

    # ─── 路肆 · PE 资源段 ────────────────────────────────────────
    if mode == "all":
        _log("\n═══ 路肆 · PE 资源段 ═══")
        sw_dir = _find_sw_install_dir()
        if sw_dir:
            exe_path = os.path.join(sw_dir, "SLDWORKS.exe")
            if os.path.exists(exe_path):
                pe_info = _pe_find_typelib_resources(exe_path)
                report["pe_resources"] = pe_info
            else:
                _log(f"  SLDWORKS.exe 不存在")
        else:
            _log(f"  SW 安装目录未找到")

    # ─── 路伍 · ProgID 链式追踪 ──────────────────────────────────
    if mode == "all":
        _log("\n═══ 路伍 · ProgID → CLSID → TypeLib 链式追踪 ═══")
        progids = [
            "SldWorks.Application",
            "SldWorks.Application.31",
            "SldWorks.Application.32",
            "SldWorks.Document",
            "SldWorks.Document.31",
            "SldWorks.Document.32",
            "SwDocumentMgr.SwDocumentMgr",
            "EModelView.EModelViewControl",
            "SldDrawingDoc",
            "SldWorks.PartDoc",
            "SldWorks.AssemblyDoc",
        ]
        chains = {}
        for pid in progids:
            chain = _chase_progid_to_typelib(pid)
            if chain.get("clsid"):
                _log(f"  {pid} → CLSID={chain['clsid']}"
                     + (f" → TypeLib={chain.get('typelib_guid', '?')}"
                        if chain.get('typelib_guid') else ""))
                chains[pid] = chain

                # 尝试通过 TypeLib GUID 加载
                if chain.get("typelib_guid"):
                    try:
                        import pythoncom
                        tlib = pythoncom.LoadRegTypeLib(
                            chain["typelib_guid"], 0, 0, 0)
                        name = tlib.GetDocumentation(-1)[0]
                        cnt = tlib.GetTypeInfoCount()
                        _log(f"    → TypeLib: {name} ({cnt} types)")
                        reflector.reflect_from_typelib(tlib, max_depth=2)
                    except Exception:
                        pass
            else:
                _log(f"  {pid} → 未注册")
        report["progid_chains"] = chains

    # ─── 汇总 ────────────────────────────────────────────────────
    _log("\n" + "═" * 60)
    _log("═══ 汇总 · 目无全牛 ═══")

    s = reflector.summary()
    report["final_summary"] = s
    _log(f"  接口:   {s['interfaces']}")
    _log(f"  枚举:   {s['enums']}")
    _log(f"  CoClass: {s['coclasses']}")
    _log(f"  方法总计: {s['total_methods']}")
    _log(f"  属性总计: {s['total_properties']}")
    _log(f"  引用边:   {s['graph_edges']}")

    # ─── 关键接口详情 ────────────────────────────────────────────
    key_ifaces = [
        "ISldWorks", "IModelDoc2", "IAssemblyDoc", "IPartDoc",
        "IDrawingDoc", "IComponent2", "IMate2", "IFeature",
        "IBody2", "IFace2", "IEdge", "ISurface",
        "IModelDocExtension", "ISelectionMgr", "IMathUtility",
        "ISketchManager", "IFeatureManager", "IEquationMgr",
        "IConfigurationManager", "IConfiguration",
        "IDimensionTolerance", "IDisplayDimension",
        "IMathTransform", "IMathVector", "IMathPoint",
    ]
    _log("\n═══ 关键接口 ═══")
    key_details = {}
    for ki in key_ifaces:
        if ki in reflector.interfaces:
            iface = reflector.interfaces[ki]
            methods = iface.get("methods", {})
            props = iface.get("properties", {})
            inherited = iface.get("inherited_from", [])
            _log(f"  {ki}: {len(methods)}M {len(props)}P"
                 + (f" ← {', '.join(inherited)}" if inherited else ""))
            key_details[ki] = {
                "methods": len(methods),
                "properties": len(props),
                "inherited": inherited,
                "method_names": sorted(methods.keys()),
                "property_names": sorted(props.keys()),
            }
    report["key_interfaces"] = key_details

    # ─── 接口关系图 ──────────────────────────────────────────────
    report["interface_graph"] = reflector.graph_edges

    # ─── 完整接口数据 ────────────────────────────────────────────
    report["all_interfaces"] = {}
    for name, iface in reflector.interfaces.items():
        # 序列化, 但跳过大枚举的 values 节省空间
        entry = dict(iface)
        if entry.get("is_enum") and entry.get("values"):
            entry["value_count"] = len(entry["values"])
            if len(entry["values"]) > 100:
                entry["values_sample"] = dict(
                    list(entry["values"].items())[:20])
                del entry["values"]
        report["all_interfaces"][name] = entry

    return report


def _save_results(report: Dict):
    """保存所有结果."""
    cwd = Path.cwd()

    # 主报告
    json_path = cwd / "_庖丁解牛_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    _log(f"\n报告: {json_path}")

    # 接口关系图 (单独输出, 方便可视化)
    graph_path = cwd / "_庖丁解牛_graph.json"
    graph = {
        "edges": report.get("interface_graph", []),
        "nodes": list(report.get("all_interfaces", {}).keys()),
    }
    with open(graph_path, "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, indent=2, default=str)
    _log(f"关系图: {graph_path}")

    # 日志
    log_path = cwd / "_庖丁解牛_log.txt"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(_LOG))
    _log(f"日志: {log_path}")


# ════════════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════════════

def main():
    import argparse
    ap = argparse.ArgumentParser(
        description="道 · 庖丁解牛 — SolidWorks COM 终极解构"
    )
    ap.add_argument("mode", nargs="?", default="all",
                    choices=["all", "live", "typelib", "graph"],
                    help="解构模式 (默认: all)")
    args = ap.parse_args()

    report = run_deep_deconstruction(args.mode)
    _save_results(report)

    s = report.get("final_summary", {})
    _log(f"\n{'═' * 60}")
    _log(f"庖丁解牛 · 完 · {s.get('interfaces', 0)} 接口 "
         f"{s.get('total_methods', 0)} 方法 "
         f"{s.get('total_properties', 0)} 属性")


if __name__ == "__main__":
    main()
