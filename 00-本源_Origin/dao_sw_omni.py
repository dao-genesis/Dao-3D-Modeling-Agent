#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
dao_sw_omni.py — SolidWorks 万法归一 · op-stream 全链路
═══════════════════════════════════════════════════════════════════════════
对标 10-反笙_FreeCAD/freecad_connection.py · 把 FC 的 execute_ops JSON 协议
带到 SW 侧. 包住 dao_sw_live.SWLive · 对外暴露声明式装配/修改/导出 API.

设计原则
    · 水善利万物而不争 — 多路径自动降级 · 不抛异常 · 失败返 {ok:False, err:...}
    · ASCII 路径自动 stage (SW 对中文/含空格路径 COM 不稳)
    · MathUtility 走 `live.app_late` 绕 gencache 污染 (dao_sw_live.py:481-489)
    · 装配 `Transform2` 全路径封装 · 不重复造轮子
    · op-stream · 声明式意图 → 过程化执行 · 可序列化/重放/对账

支持操作 (v1.0)
    ─── 连接/文档 ───
    ensure_live           | 确保 SW 活体 (幂等)
    open                  | 打开文档 · 自动 ASCII stage
    close                 | 关闭 (不保存)
    close_all             | 关闭全部 (不保存)
    list_docs             | 列开文档
    activate              | 切换活动文档
    new_part / new_asm    | 新建
    ─── 装配 / 组件 ───
    list_components       | 列活动装配的所有组件 (含深遍历)
    add_component         | 添加零件 (多路径降级 · 见 AssemblyBuilder.add_component)
    set_transform         | 设组件位置/旋转 (BBox 中心 intent 或直接 R+t)
    remove_component      | 删除组件
    ─── 导入 / 导出 ───
    import_step_as_asm    | STEP → Assembly (swStepAsAssembly=64 · LoadFile4 · ASCII stage)
    save_as               | 保存 (.SLDASM/.SLDPRT/.step/.pdf/...) · 多路径
    export                | 等价 save_as
    ─── 视图 / 渲染 ───
    rebuild               | ForceRebuild3
    zoom_fit              | 自适应视图
    view                  | 切换标准视图 (iso/front/...)
    snap                  | 保存截图 (PNG)
    snap_views            | 批量 7 视图快照
    ─── 诊断 / 活体 ───
    bbox_world            | 活动组件世界 BBox
    probe_local_bbox      | 逐零件打开 · 读局部 BBox (GetPartBox)
    diag_assembly         | 装配诊断 (Transform2 + 世界 BBox 三源对账)
    mass_properties       | 质量属性

用法
    from dao_sw_omni import SWOmni
    omni = SWOmni()
    result = omni.execute_ops([
        {"op": "ensure_live"},
        {"op": "open", "path": "v8.SLDASM", "id": "asm"},
        {"op": "add_component", "path": "hammer.SLDPRT",
         "translation_mm": [225, 0, 310], "rot_axis": [1,0,0], "rot_deg": 90,
         "lbl": "锤头16"},
        {"op": "rebuild"},
        {"op": "save_as", "path": "v10.SLDASM"},
        {"op": "snap", "view": "iso", "out": "v10.png"},
    ])
    print(result["ok"], result["ops"])
"""
from __future__ import annotations

import json
import math
import os
import shutil
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

# ── 路径引导 ───────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# ── 依赖 (懒加载) ──────────────────────────────────────────────────────
try:
    import dao_sw_live as _live_mod  # noqa: F401
    import dao_solidworks as _sw_mod  # noqa: F401
except Exception as _e:  # noqa: BLE001
    print(f"[dao_sw_omni] warning: 无法加载 dao_sw_live/dao_solidworks: {_e}",
          file=sys.stderr)

__version__ = "1.0.0"
__all__ = [
    "SWOmni", "OmniResult", "OmniError",
    "ASCII_STAGE_DIR", "intent_to_rt",
]

# ── 全局常量 ───────────────────────────────────────────────────────────
ASCII_STAGE_DIR = Path(os.environ.get("DAO_SW_ASCII_STAGE",
                                       "E:/Temp/dao_sw_forge"))
ASCII_STAGE_DIR.mkdir(parents=True, exist_ok=True)

# SW 用户偏好 toggle
SW_STEP_AS_ASSEMBLY = 64      # swUserPreferenceToggle_e.swStepAsAssembly

# 文档类型
SW_DOC_PART = 1
SW_DOC_ASSEMBLY = 2
SW_DOC_DRAWING = 3

# 标准视图名 → swStandardViews_e
SW_VIEWS = {
    "front": 1, "back": 2, "left": 3, "right": 4,
    "top": 5, "bottom": 6,
    "iso": 7, "isometric": 7, "trimetric": 8, "dimetric": 9,
}


# ════════════════════════════════════════════════════════════════════════
# 数学工具 · intent → (R, t) 编译器
# ════════════════════════════════════════════════════════════════════════
def _rotation_matrix(axis: Optional[Sequence[float]],
                     angle_deg: float) -> Tuple[Tuple[float, float, float], ...]:
    """Rodrigues · 返 3×3 旋转矩阵 (row-major · R[row][col])."""
    if axis is None or not angle_deg:
        return ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    ax, ay, az = [float(v) for v in axis]
    L = math.sqrt(ax * ax + ay * ay + az * az)
    if L < 1e-12:
        return ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    ax, ay, az = ax / L, ay / L, az / L
    t = math.radians(float(angle_deg))
    c, s = math.cos(t), math.sin(t)
    u = 1.0 - c
    return (
        (c + ax * ax * u,       ax * ay * u - az * s, ax * az * u + ay * s),
        (ay * ax * u + az * s,  c + ay * ay * u,      ay * az * u - ax * s),
        (az * ax * u - ay * s,  az * ay * u + ax * s, c + az * az * u),
    )


def _rotate_vec(v: Sequence[float], axis: Optional[Sequence[float]],
                angle_deg: float) -> Tuple[float, float, float]:
    R = _rotation_matrix(axis, angle_deg)
    x, y, z = [float(c) for c in v]
    return (
        R[0][0] * x + R[0][1] * y + R[0][2] * z,
        R[1][0] * x + R[1][1] * y + R[1][2] * z,
        R[2][0] * x + R[2][1] * y + R[2][2] * z,
    )


def intent_to_rt(mode: str,
                 target: Sequence[float],
                 axis: Optional[Sequence[float]],
                 angle_deg: float,
                 local_bbox_center_mm: Optional[Sequence[float]] = None
                 ) -> Tuple[Tuple[Tuple[float, ...], ...], Tuple[float, float, float]]:
    """从声明式 intent 编译 (R, t).

    mode:
      "origin"    · target = 零件局部原点在世界的位置 (与 config.py:ASSEMBLY_POSITIONS 一致)
                    t = target · R = Rodrigues(axis, angle)
      "bbox_center" · target = 零件 BBox 中心在世界的位置
                      t = target - R · local_bbox_center
                      (需 local_bbox_center_mm, 由 probe_local_bbox 活体探测)

    返 (R, t_mm). t 单位 mm.
    """
    R = _rotation_matrix(axis, angle_deg)
    tx, ty, tz = [float(v) for v in target]
    if mode == "origin":
        return R, (tx, ty, tz)
    if mode == "bbox_center":
        if local_bbox_center_mm is None:
            raise ValueError("bbox_center intent 需 local_bbox_center_mm")
        lc = [float(v) for v in local_bbox_center_mm]
        rlc = _rotate_vec(lc, axis, angle_deg)
        return R, (tx - rlc[0], ty - rlc[1], tz - rlc[2])
    raise ValueError(f"未知 intent mode: {mode!r}; 须 'origin' 或 'bbox_center'")


# ════════════════════════════════════════════════════════════════════════
# 异常 / 结果容器
# ════════════════════════════════════════════════════════════════════════
class OmniError(Exception):
    pass


@dataclass
class OmniResult:
    ok: bool = True
    ops: List[Dict[str, Any]] = field(default_factory=list)
    objects: Dict[str, Any] = field(default_factory=dict)   # id → 资源 (doc/comp)
    errors: List[str] = field(default_factory=list)
    stage_dir: str = str(ASCII_STAGE_DIR)
    elapsed_s: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "ops": self.ops,
            "errors": self.errors,
            "stage_dir": self.stage_dir,
            "elapsed_s": round(self.elapsed_s, 3),
            "object_ids": list(self.objects.keys()),
        }


# ════════════════════════════════════════════════════════════════════════
# 核心: SWOmni
# ════════════════════════════════════════════════════════════════════════
class SWOmni:
    """SW 万法归一 op-stream 执行器.

    组合 SWLive (连接/新建/视图) + 底层 COM (Transform2/AddComponent5) + ASCII stage.

    不重建 dao_sw_live · 而是作为顶层 orchestrator 统一调度.

    属性:
      live            · SWLive 实例 (懒创建)
      app             · ISldWorks (bridge._app, 可能被 gencache 污染)
      app_late        · 干净 late-binding IDispatch (优先用)
      _math           · MathUtility 缓存 (从 app_late 获取)
      _objects        · id → 资源映射 (供 ops 间传递)
    """

    def __init__(self, *,
                 ascii_stage: Optional[Path] = None,
                 verbose: bool = False):
        self.verbose = verbose
        self.stage = Path(ascii_stage) if ascii_stage else ASCII_STAGE_DIR
        self.stage.mkdir(parents=True, exist_ok=True)
        self._live = None            # type: Optional[Any]
        self._math = None            # MathUtility (late-binding)
        self._objects: Dict[str, Any] = {}

    # ──────────────────────────────────────────────────────────────────
    # 连接
    # ──────────────────────────────────────────────────────────────────
    @property
    def live(self):
        """SWLive 实例 (懒创建, 不强制 ensure_live)."""
        if self._live is None:
            import dao_sw_live as _lm
            self._live = _lm.SWLive()
        return self._live

    @property
    def app(self):
        return self.live.app

    @property
    def app_late(self):
        """干净 late-binding · 绕 gencache 污染. MathUtility 必经此路."""
        return self.live.app_late

    def ensure_live(self, *, visible: bool = True,
                    dismiss_welcome: bool = False,
                    launch_timeout_s: float = 90.0) -> Dict[str, Any]:
        """确保 SW 活体 (幂等). 返 {ok, revision?, err?}."""
        try:
            rec = self.live.ensure_live(
                visible=visible,
                dismiss_welcome=dismiss_welcome,
                launch_timeout_s=launch_timeout_s,
            )
            return rec if isinstance(rec, dict) else {"ok": True}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "err": f"{type(e).__name__}: {e}"}

    # ──────────────────────────────────────────────────────────────────
    # MathUtility 健壮封装 (根治 · 走底层 Invoke + VT_ARRAY|VT_R8 绕 pywin32 bug)
    # ──────────────────────────────────────────────────────────────────
    # pywin32 late-binding 对 SW MathUtility.CreateVector/CreateTransform 失败:
    #   · CDispatch.__getattr__ 查成员时报 "找不到成员"
    #   · 直接传 list 参数会被误封为 VT_VARIANT → 数据错位 (首元素变 garbage)
    # 根治: 用 _oleobj_.Invoke(dispid, 0, 1, True, VARIANT(VT_ARRAY|VT_R8, arr))
    # 实测 (SW 2024 RevisionNumber=31.0.1):
    #   · dispid[CreateVector]    = 7
    #   · dispid[CreateTransform] = 1
    #   · dispid[CreatePoint]     = 5
    #   · dispid[ArrayData] on IMathVector/Transform = 3
    _MT_DISPID_CREATE_VECTOR    = 7
    _MT_DISPID_CREATE_TRANSFORM = 1
    _MT_DISPID_CREATE_POINT     = 5

    def math(self):
        """获取 MathUtility CDispatch · 缓存.

        返回的 mt 是 CDispatch 但其 .CreateVector/.CreateTransform 调用不通
        (见类注释). 仅用于取 `mt._oleobj_`, 真正的调用走 _math_create_*.
        """
        if self._math is not None:
            return self._math
        # 走 app.GetMathUtility prop (bridge._app · 非 late-binding)
        # 对话历史 _probe_math.py 验证仅此路径能拿到非 None CDispatch
        errors = []
        for src_name, src in (("app", self.app), ("app_late", self.app_late)):
            if src is None:
                continue
            try:
                mt = src.GetMathUtility  # prop 形式, 不加 ()
                if mt is None:
                    errors.append(f"{src_name}.GetMathUtility → None")
                    continue
                # 验证 · 能取 _oleobj_
                try:
                    _ = mt._oleobj_
                except Exception as e:
                    errors.append(f"{src_name}: no _oleobj_: {e}")
                    continue
                self._math = mt
                return mt
            except Exception as e:
                errors.append(f"{src_name}.GetMathUtility: {type(e).__name__}:{e}")
        raise OmniError(f"MathUtility 全路径失败: {errors}")

    def _math_invoke_safearray(self, dispid: int, arr: Sequence[float]):
        """底层调用 · 用 VARIANT(VT_ARRAY|VT_R8, arr) 绕 pywin32 list 误封.

        返 raw PyIDispatch (未包装). 取 ArrayData 必须再走 Invoke(3,...).
        """
        import pythoncom
        from win32com.client import VARIANT
        mt = self.math()
        flt_arr = [float(v) for v in arr]
        v_arg = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, flt_arr)
        # Invoke(dispid, lcid, wFlags=DISPATCH_METHOD, bResultWanted, *args)
        raw = mt._oleobj_.Invoke(dispid, 0, 1, True, v_arg)
        return raw

    def math_create_vector(self, arr: Sequence[float]):
        """创建 IMathVector. 返 CDispatch (可 .ArrayData)."""
        from win32com.client import Dispatch
        raw = self._math_invoke_safearray(self._MT_DISPID_CREATE_VECTOR, arr)
        return Dispatch(raw)

    def math_create_transform(self, arr16: Sequence[float]):
        """创建 IMathTransform · 16 元 ArrayData [R col0(3) + R col1(3) + R col2(3) + T(3) + 1 + S(3)].
        返 CDispatch.
        """
        from win32com.client import Dispatch
        raw = self._math_invoke_safearray(self._MT_DISPID_CREATE_TRANSFORM, arr16)
        return Dispatch(raw)

    def build_transform(self, R: Sequence[Sequence[float]],
                        t_mm: Sequence[float]):
        """用 MathUtility 构造 SW MathTransform (16 元).

        R: Rodrigues row-major 3×3. SW 约定 ArrayData[0..8] = 3 列 (按列存):
          col0 = (R[0][0], R[1][0], R[2][0])   → 零件 X 轴在世界中的方向
          col1 = (R[0][1], R[1][1], R[2][1])   → 零件 Y 轴
          col2 = (R[0][2], R[1][2], R[2][2])   → 零件 Z 轴
        T[9..11] = 平移 (m)
        ArrayData[12] = 1.0 (scale base)
        ArrayData[13..15] = (sx, sy, sz) = (1, 1, 1) 正常
        """
        col0 = [float(R[0][0]), float(R[1][0]), float(R[2][0])]
        col1 = [float(R[0][1]), float(R[1][1]), float(R[2][1])]
        col2 = [float(R[0][2]), float(R[1][2]), float(R[2][2])]
        tx = float(t_mm[0]) / 1000.0
        ty = float(t_mm[1]) / 1000.0
        tz = float(t_mm[2]) / 1000.0
        arr16 = (col0 + col1 + col2
                 + [tx, ty, tz]
                 + [1.0, 1.0, 1.0, 1.0])
        return self.math_create_transform(arr16)

    # ──────────────────────────────────────────────────────────────────
    # ASCII stage (SW 对中文/空格路径不稳)
    # ──────────────────────────────────────────────────────────────────
    def stage_file(self, src: Union[str, Path], *,
                   name: Optional[str] = None) -> Path:
        """把 src 复制到 ASCII stage (若 src 本就纯 ASCII 且 <260 字符则直接返原路径).
        name: 若给, 用此文件名; 否则用 src.name (仍可能含中文).
        """
        p = Path(src).resolve()
        if not p.exists():
            raise FileNotFoundError(f"stage_file: 源文件不存在 {p}")
        # 纯 ASCII + 短路径 → 原样
        s = str(p)
        if all(ord(c) < 128 for c in s) and len(s) < 250:
            return p
        target_name = name or p.name
        # 若名字仍非 ASCII · 用 ASCII 化
        if not all(ord(c) < 128 for c in target_name):
            target_name = _ascii_safe_name(target_name, p.suffix)
        dst = self.stage / target_name
        # 已存在且 mtime >= src.mtime → 复用
        if dst.exists() and dst.stat().st_mtime >= p.stat().st_mtime:
            return dst
        try:
            shutil.copy2(p, dst)
        except Exception:
            shutil.copy(p, dst)
        return dst

    # ──────────────────────────────────────────────────────────────────
    # op-stream 主引擎
    # ──────────────────────────────────────────────────────────────────
    def execute_ops(self, ops: List[Dict[str, Any]], *,
                    stop_on_error: bool = False,
                    ensure_live_first: bool = True) -> OmniResult:
        """执行 op 列表. 每 op 返 {ok, via?, ...}. 附加到 result.ops.

        ensure_live_first=True: 自动插入 ensure_live 为第 0 op.
        """
        result = OmniResult(ok=True, ops=[], errors=[])
        t0 = time.time()

        if ensure_live_first and not any(o.get("op") == "ensure_live" for o in ops):
            ops = [{"op": "ensure_live"}] + list(ops)

        for i, op_spec in enumerate(ops):
            op_name = str(op_spec.get("op", "")).strip()
            if not op_name:
                result.errors.append(f"op[{i}] 缺 'op' 字段")
                result.ok = False
                if stop_on_error:
                    break
                continue

            handler = self._get_handler(op_name)
            rec = {"op": op_name, "idx": i}
            if handler is None:
                rec.update({"ok": False, "err": f"未知 op: {op_name}"})
                result.errors.append(rec["err"])
                result.ok = False
                result.ops.append(rec)
                if stop_on_error:
                    break
                continue

            try:
                out = handler(op_spec) or {}
            except Exception as e:  # noqa: BLE001
                out = {"ok": False,
                       "err": f"{type(e).__name__}: {e}",
                       "trace": traceback.format_exc(limit=5)}
            rec.update(out)
            if not rec.get("ok"):
                result.ok = False
                result.errors.append(f"op[{i}] {op_name}: {rec.get('err', '?')}")
                if stop_on_error:
                    result.ops.append(rec)
                    break
            result.ops.append(rec)
            if self.verbose:
                _tag = "[OK]" if rec.get("ok") else "[ER]"
                print(f"  {_tag} op[{i}] {op_name:<20} "
                      f"{_abbrev(rec, 80)}")

        result.elapsed_s = time.time() - t0
        return result

    def _get_handler(self, op_name: str) -> Optional[Callable]:
        return getattr(self, f"op_{op_name}", None)

    # ──────────────────────────────────────────────────────────────────
    # ops · 连接/文档
    # ──────────────────────────────────────────────────────────────────
    def op_ensure_live(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        rec = self.ensure_live(
            visible=bool(spec.get("visible", True)),
            dismiss_welcome=bool(spec.get("dismiss_welcome", False)),
            launch_timeout_s=float(spec.get("launch_timeout_s", 90.0)),
        )
        return {"ok": rec.get("ok", True),
                "revision": rec.get("revision"),
                "err": rec.get("err")}

    def op_open(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """打开文档 · 自动 ASCII stage · 多路径.
        spec:
          path:   源路径 (必需)
          as_asm: bool  · 强制以 Assembly 打开 (STEP 专用)
          id:     str   · 存入 self._objects[id]
          readonly: bool
        """
        path = spec.get("path")
        if not path:
            return {"ok": False, "err": "缺 path"}
        try:
            staged = self.stage_file(path)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "err": f"stage_file: {e}"}

        ext = staged.suffix.lower()
        as_asm = bool(spec.get("as_asm", False))

        # STEP/IGES → import_step_as_asm
        if ext in (".step", ".stp", ".iges", ".igs") or as_asm:
            return self._do_import_step(staged, oid=spec.get("id"),
                                         as_asm=as_asm or ext in (".step", ".stp"))

        # 原生 SLDASM/SLDPRT/SLDDRW → OpenDoc6 多路径
        readonly = bool(spec.get("readonly", False))
        try:
            base = self.live._bridge.open(staged, readonly=readonly,
                                          silent=True)
            if base is None:
                return {"ok": False, "err": "bridge.open 返 None"}
            if spec.get("id"):
                self._objects[spec["id"]] = base
            return {"ok": True, "path": str(staged),
                    "title": base.title() if hasattr(base, "title") else None,
                    "doc_type": base.doc_type if hasattr(base, "doc_type") else None}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "err": f"bridge.open: {type(e).__name__}:{e}"}

    def op_close(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """关闭指定 title 或活动文档. unsaved 不保存."""
        title = spec.get("title")
        if not title:
            ad = self._active()
            if ad is None:
                return {"ok": False, "err": "无活动文档"}
            try:
                title = ad.GetTitle
            except Exception:
                return {"ok": False, "err": "无法获取活动文档 title"}
        try:
            self.app.CloseDoc(title)
            return {"ok": True, "title": title}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "err": f"CloseDoc: {e}"}

    def op_close_all(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # False = 不保存直接关闭 (True 在 SW 2024 中对含修改文档会弹存档对话框阻塞)
            self.app.CloseAllDocuments(False)
            time.sleep(0.5)
            return {"ok": True}
        except Exception as e:  # noqa: BLE001
            # 降级: 逐个 CloseDoc
            closed = 0
            try:
                docs = list(self.live.docs() or [])
                for d in docs:
                    try:
                        title = d.get("title", "")
                        if title:
                            self.app.CloseDoc(title)
                            closed += 1
                    except Exception:
                        pass
            except Exception:
                pass
            return {"ok": True, "via": "per_doc_fallback", "closed": closed,
                    "err_original": str(e)}

    def op_list_docs(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        try:
            docs = self.live.docs() or []
            return {"ok": True, "count": len(docs), "docs": docs}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "err": f"{e}"}

    def op_activate(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        title = spec.get("title", "")
        if not title:
            return {"ok": False, "err": "缺 title"}
        try:
            self.app.ActivateDoc(title)
            time.sleep(0.3)
            return {"ok": True, "title": title}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "err": f"ActivateDoc: {e}"}

    def op_new_asm(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        try:
            d = self.live.new_assembly()
            if spec.get("id"):
                self._objects[spec["id"]] = d
            return {"ok": True, "title": d.title() if d else None}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "err": f"{e}"}

    def op_new_part(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        try:
            d = self.live.new_part()
            if spec.get("id"):
                self._objects[spec["id"]] = d
            return {"ok": True, "title": d.title() if d else None}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "err": f"{e}"}

    # ──────────────────────────────────────────────────────────────────
    # ops · 装配 / 组件
    # ──────────────────────────────────────────────────────────────────
    def op_list_components(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """列当前活动装配的所有组件.
        返 components: [{name, bname, path, config, transform}]
        """
        ad = self._active_asm()
        if ad is None:
            return {"ok": False, "err": "非装配文档"}
        try:
            from win32com.client import dynamic
        except Exception:
            dynamic = None

        try:
            comps = ad.GetComponents(False) or []
        except Exception as e:
            return {"ok": False, "err": f"GetComponents: {e}"}

        out_comps = []
        for c in comps:
            cw = dynamic.Dispatch(c._oleobj_) if dynamic else c
            nm = _safe_name(cw)
            if not nm:
                continue
            bn = _extract_bname(nm)
            # Transform2 → array
            arr = None
            try:
                tx = cw.Transform2
                if tx is not None:
                    arr = list(tx.ArrayData)
            except Exception:
                pass
            # 位置 + 旋转 解析
            tx_mm = ty_mm = tz_mm = None
            if arr and len(arr) >= 12:
                tx_mm = round(arr[9] * 1000.0, 3)
                ty_mm = round(arr[10] * 1000.0, 3)
                tz_mm = round(arr[11] * 1000.0, 3)
            out_comps.append({
                "name": nm, "bname": bn,
                "tx_mm": tx_mm, "ty_mm": ty_mm, "tz_mm": tz_mm,
                "has_transform": arr is not None,
            })
        return {"ok": True, "count": len(out_comps), "components": out_comps}

    _warmed_parts: set = None  # type: ignore

    def op_add_component(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """添加零件到活动装配 · 委托 AssemblyBuilder.add_component (多路径).
        后续再 set_transform 定位/旋转.

        关键: SW AddComponent5 路径 5 (preload+activate) 对首次引入某 SLDPRT
        会产生 Transform2 setter 不通的 bug. 故 add 前先 warmup SLDPRT
        (open_readonly → close) 让后续 AddComponent5 走 path 1.

        spec:
          path:           SLDPRT 路径 (必需)
          translation_mm: [tx, ty, tz]  默认 [0,0,0]
          rot_axis, rot_deg:  旋转 (可选)
          intent_mode:    "origin" (默认) 或 "bbox_center"
          local_bbox_center_mm: [cx,cy,cz] (intent_mode=bbox_center 必需)
          lbl:            新组件的标签 (仅日志用)
          doc_id:         (可选) 之前 new_asm/open 时 id= 存的装配; 自动激活
          skip_warmup:    bool · 默认 False · 设 True 禁 warmup
        """
        if SWOmni._warmed_parts is None:
            SWOmni._warmed_parts = set()
        path = spec.get("path")
        if not path:
            return {"ok": False, "err": "缺 path"}
        try:
            staged = self.stage_file(path)
        except Exception as e:
            return {"ok": False, "err": f"stage_file: {e}"}

        # ── warmup (opt-in · default off): 首次引入某 SLDPRT · 预 open 再 close
        # 让后续 AddComponent5 走 path 1 · 避免 Transform2 setter 不通.
        # 实测 single-shot warmup 可能 race, 建议用 op_preload_parts 批量预热
        if spec.get("warmup", False):
            staged_key = str(staged).lower()
            if staged_key not in SWOmni._warmed_parts:
                try:
                    import pythoncom
                    from win32com.client import VARIANT
                    err_v = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                    warn_v = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                    wdoc = self.app.OpenDoc6(str(staged), 1, 0, "", err_v, warn_v)
                    time.sleep(0.3)
                    if wdoc is not None:
                        try:
                            self.app.CloseDoc(staged.name); time.sleep(0.15)
                        except Exception:
                            pass
                    SWOmni._warmed_parts.add(staged_key)
                except Exception:
                    pass

        # 若指定 doc_id · 先激活该装配 (add_component 多路径会切走 ActiveDoc)
        doc_id = spec.get("doc_id")
        if doc_id and doc_id in self._objects:
            stored = self._objects[doc_id]
            asm_title = None
            try:
                if hasattr(stored, "title"):
                    asm_title = stored.title()
                elif hasattr(stored, "GetTitle"):
                    asm_title = stored.GetTitle
            except Exception:
                pass
            if asm_title:
                try:
                    self.app.ActivateDoc3(asm_title, False, 0, 0)
                    time.sleep(0.15)
                except Exception:
                    try:
                        self.app.ActivateDoc(asm_title)
                        time.sleep(0.15)
                    except Exception:
                        pass

        # 找活动装配 + AssemblyBuilder
        asm_doc = self._active_live_asm()
        if asm_doc is None:
            # 最后一搏: 列出全部装配文档自动挑一个
            try:
                for d in self.live.docs():
                    t = d.get("title", "")
                    if t.upper().endswith(".SLDASM") or "装配" in t or "Assem" in t:
                        try:
                            self.app.ActivateDoc3(t, False, 0, 0)
                        except Exception:
                            self.app.ActivateDoc(t)
                        time.sleep(0.15)
                        break
            except Exception:
                pass
            asm_doc = self._active_live_asm()

        if asm_doc is None:
            return {"ok": False, "err": "无活动装配"}

        # 先用 translation 作为 AddComponent 的初始位置 (方便)
        tx_mm, ty_mm, tz_mm = [float(v) for v in spec.get("translation_mm",
                                                          [0.0, 0.0, 0.0])]
        rec = asm_doc.assembly.add_component(
            staged, x_mm=tx_mm, y_mm=ty_mm, z_mm=tz_mm,
            config=spec.get("config", ""))
        if not rec.get("ok"):
            return {"ok": False, "err": f"add_component: {rec.get('err')}",
                    "trace": (rec.get("trace") or [])[:3]}

        comp_name = rec.get("name") or rec.get("comp_name")
        # SW 新加的组件需时间初始化 Transform2 · 尤其首次 bname 引入 SLDPRT
        time.sleep(0.3)
        # 【根修】add_component 后 SW 会将 SLDPRT 切为活动文档 · 无论是否旋转都必须重新激活装配
        # 否则下一个 add_component 找不到活动装配 ("无活动装配" 在第4+非旋转件处爆发)
        if doc_id and doc_id in self._objects:
            try:
                stored = self._objects[doc_id]
                _at = stored.title() if hasattr(stored, "title") else None
                if _at:
                    try:
                        self.app.ActivateDoc3(_at, False, 0, 0)
                    except Exception:
                        try:
                            self.app.ActivateDoc(_at)
                        except Exception:
                            pass
                    time.sleep(0.15)
            except Exception:
                pass
        # 若要旋转 · 额外 set_transform
        axis = spec.get("rot_axis")
        deg = float(spec.get("rot_deg", 0) or 0)
        intent_mode = spec.get("intent_mode", "origin")
        local_bbox = spec.get("local_bbox_center_mm")
        if (axis and deg) or intent_mode == "bbox_center":
            # add_component 可能又切走 ActiveDoc · 先激活装配
            if doc_id and doc_id in self._objects:
                try:
                    stored = self._objects[doc_id]
                    t = stored.title() if hasattr(stored, "title") else None
                    if t:
                        try:
                            self.app.ActivateDoc3(t, False, 0, 0)
                        except Exception:
                            self.app.ActivateDoc(t)
                        time.sleep(0.1)
                except Exception:
                    pass
            # 重新编译 set_transform · 首次某 bname 刚载入时 Transform2 setter 常需 rebuild 才稳
            # 故此处失败不视为 op 失败 · 返 warn · 上游二轮 cleanup 会补设
            set_rec = self.op_set_transform({
                "component": comp_name,
                "translation_mm": [tx_mm, ty_mm, tz_mm],
                "rot_axis": axis,
                "rot_deg": deg,
                "intent_mode": intent_mode,
                "local_bbox_center_mm": local_bbox,
            })
            if set_rec.get("ok"):
                return {"ok": True, "component": comp_name,
                        "set_transform": set_rec}
            # 首次 add · Transform2 未稳 · 保留 warn · 不误报 fail
            return {"ok": True,
                    "component": comp_name,
                    "warn": "set_transform_deferred",
                    "set_transform": set_rec,
                    "translation_mm": [tx_mm, ty_mm, tz_mm]}
        return {"ok": True, "component": comp_name,
                "translation_mm": [tx_mm, ty_mm, tz_mm]}

    def op_set_transform(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """设置组件 Transform2.

        spec:
          component:         组件名 (Name2) 或 bname (模糊)
          translation_mm:    [tx, ty, tz]
          rot_axis, rot_deg: 旋转
          intent_mode:       "origin" | "bbox_center" (默认 origin)
          local_bbox_center_mm: bbox_center 模式必需
          max_retries:       失败重试次数 (默认 3 · 首次 add 的 SLDPRT 刚载入 · 延迟必要)
        """
        name = spec.get("component")
        if not name:
            return {"ok": False, "err": "缺 component"}
        t = spec.get("translation_mm", [0, 0, 0])
        axis = spec.get("rot_axis")
        deg = float(spec.get("rot_deg", 0) or 0)
        mode = spec.get("intent_mode", "origin")
        lbc = spec.get("local_bbox_center_mm")
        max_retries = int(spec.get("max_retries", 3))

        # 编译 intent → (R, t)
        try:
            R, t_mm = intent_to_rt(mode, t, axis, deg, lbc)
        except Exception as e:
            return {"ok": False, "err": f"intent_to_rt: {e}"}

        # 构造 Transform · SetTransform2 · 带重试 (SW 新 SLDPRT 加载需延迟)
        last_err = None
        for attempt in range(max_retries + 1):
            comp = self._find_component(name)
            if comp is None:
                last_err = f"找不到组件: {name} (attempt {attempt})"
                time.sleep(0.3 + 0.3 * attempt)
                continue
            try:
                tx_obj = self.build_transform(R, t_mm)
                comp.Transform2 = tx_obj
                return {"ok": True, "component": _safe_name(comp),
                        "translation_mm": list(t_mm),
                        "rot": {"axis": list(axis) if axis else None, "deg": deg},
                        "attempts": attempt + 1}
            except Exception as e:
                last_err = f"SetTransform2: {type(e).__name__}: {e}"
                time.sleep(0.3 + 0.3 * attempt)
        return {"ok": False, "err": last_err or "unknown",
                "attempts": max_retries + 1}

    def op_remove_component(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """删除组件 (按名字模糊)."""
        name = spec.get("component")
        if not name:
            return {"ok": False, "err": "缺 component"}
        ad = self._active_live_asm()
        if ad is None:
            return {"ok": False, "err": "非装配文档"}
        try:
            # 选组件
            ad.sel.clear()
            r = ad.sel.by_id(name, sel_type="component")
            if not r.get("ok"):
                return {"ok": False, "err": f"select: {r.get('err')}"}
            # Edit.Delete 或 IAssemblyDoc.DeleteSelections
            try:
                deleted = ad.raw.DeleteSelection(True)
            except Exception:
                deleted = False
            if not deleted:
                try:
                    deleted = ad.raw.EditDelete()
                except Exception:
                    pass
            return {"ok": bool(deleted), "component": name}
        except Exception as e:
            return {"ok": False, "err": f"{e}"}

    # ──────────────────────────────────────────────────────────────────
    # ops · 导入 / 导出 / 保存
    # ──────────────────────────────────────────────────────────────────
    def op_import_step_as_asm(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """STEP → Assembly · ASCII stage + swStepAsAssembly + LoadFile4/OpenDoc6 多路径."""
        path = spec.get("path")
        if not path:
            return {"ok": False, "err": "缺 path"}
        try:
            staged = self.stage_file(path)
        except Exception as e:
            return {"ok": False, "err": f"stage_file: {e}"}
        return self._do_import_step(staged, oid=spec.get("id"), as_asm=True)

    def _do_import_step(self, staged: Path, *, oid: Optional[str] = None,
                        as_asm: bool = True) -> Dict[str, Any]:
        import pythoncom
        from win32com.client import VARIANT

        # 设 swStepAsAssembly 偏好
        if as_asm:
            try:
                self.app.SetUserPreferenceToggle(SW_STEP_AS_ASSEMBLY, True)
            except Exception:
                pass

        doc = None
        method = None

        # 路 1: LoadFile4 + GetImportFileData
        try:
            import_data = self.app.GetImportFileData(str(staged))
            if import_data is not None:
                err_v = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                doc = self.app.LoadFile4(str(staged), "r", import_data, err_v)
                if doc is not None:
                    method = f"LoadFile4(err={err_v.value})"
        except Exception as e:
            pass

        # 路 2: OpenDoc6(dt=2 Assembly)
        if doc is None:
            try:
                err_v = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                warn_v = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                doc = self.app.OpenDoc6(str(staged),
                                         SW_DOC_ASSEMBLY if as_asm else SW_DOC_PART,
                                         1, "", err_v, warn_v)
                if doc is not None:
                    method = f"OpenDoc6(err={err_v.value}, warn={warn_v.value})"
            except Exception:
                pass

        # 路 3: OpenDoc6(dt=0 自选)
        if doc is None:
            try:
                err_v = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                warn_v = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                doc = self.app.OpenDoc6(str(staged), 0, 1, "", err_v, warn_v)
                if doc is not None:
                    method = f"OpenDoc6(dt=0)"
            except Exception:
                pass

        # 恢复偏好
        if as_asm:
            try:
                self.app.SetUserPreferenceToggle(SW_STEP_AS_ASSEMBLY, False)
            except Exception:
                pass

        if doc is None:
            return {"ok": False, "err": "STEP 导入全路径失败", "path": str(staged)}

        # 等 SW 完成
        time.sleep(3.0)
        ad = self._active()
        for _ in range(15):
            if ad is not None:
                break
            time.sleep(1.5)
            ad = self._active()
        if ad is None:
            return {"ok": False, "err": "ActiveDoc 未出现"}
        try:
            dt = ad.GetType if not callable(getattr(ad, "GetType", None)) else ad.GetType()
        except Exception:
            dt = -1

        if oid:
            self._objects[oid] = ad
        return {"ok": True, "path": str(staged),
                "doc_type": dt, "expect_assembly": as_asm,
                "via": method}

    def op_save_as(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """保存活动文档到 path. 自动 ASCII stage + 多路径 + 最终拷贝到目标.

        spec:
          path:        目标路径 (可含中文)
          copy_back:   bool · 默认 True · stage 成功后再拷贝到目标
        """
        path = spec.get("path")
        if not path:
            return {"ok": False, "err": "缺 path"}
        target = Path(path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)

        # 若目标路径是中文/空格 · stage 到 ASCII temp 先存, 再拷贝
        stage_name = _ascii_safe_name(target.name, target.suffix)
        staged = self.stage / stage_name

        # 若同名已存在 · 先删
        if staged.exists():
            try:
                staged.unlink()
            except Exception:
                pass

        ad = self._active()
        if ad is None:
            return {"ok": False, "err": "无活动文档"}

        # 路 1: SaveAs3 (warn 位会让 ret=False, 但文件可能已存)
        ok_ret = None
        err_path1 = None
        try:
            ok_ret = bool(ad.SaveAs3(str(staged), 0, 2))
            time.sleep(1.5)
        except Exception as e:
            err_path1 = f"SaveAs3: {type(e).__name__}: {e}"

        # 路 2: 若 staged 未出现 · 试 Extension.SaveAs
        if not staged.exists():
            try:
                import pythoncom
                from win32com.client import VARIANT
                err_v = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                warn_v = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                ok_ret2 = bool(ad.Extension.SaveAs(str(staged), 0, 2, None,
                                                    err_v, warn_v))
                time.sleep(1.5)
            except Exception as e:
                if err_path1 is None:
                    err_path1 = f"Extension.SaveAs: {type(e).__name__}: {e}"

        if not staged.exists():
            return {"ok": False, "err": f"保存到 stage 失败: {err_path1}",
                    "ret": ok_ret, "stage_path": str(staged)}

        # 拷贝到目标
        if bool(spec.get("copy_back", True)):
            try:
                shutil.copy2(staged, target)
            except Exception as e:
                return {"ok": False, "err": f"copy_back: {e}",
                        "stage_path": str(staged)}

        return {"ok": True, "path": str(target),
                "stage_path": str(staged),
                "size_B": target.stat().st_size if target.exists() else None,
                "ret": ok_ret}

    def op_export(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """别名 · 同 save_as. path 可 .step / .pdf / .stl / .png..."""
        return self.op_save_as(spec)

    # ──────────────────────────────────────────────────────────────────
    # ops · 视图 / 渲染
    # ──────────────────────────────────────────────────────────────────
    def op_rebuild(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        ad = self._active()
        if ad is None:
            return {"ok": False, "err": "无活动文档"}
        try:
            try:
                ad.ForceRebuild3(False)
            except Exception:
                ad.EditRebuild3()
            time.sleep(float(spec.get("wait_s", 1.5)))
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "err": f"{e}"}

    def op_zoom_fit(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        ad = self._active()
        if ad is None:
            return {"ok": False, "err": "无活动文档"}
        try:
            ad.ViewZoomtofit2()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "err": f"{e}"}

    def op_view(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        view = spec.get("view", "iso")
        try:
            rec = self.live.view(view)
            return rec if isinstance(rec, dict) else {"ok": True}
        except Exception as e:
            return {"ok": False, "err": f"{e}"}

    def op_snap(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """截图到 out.  若 view 指定 · 先切视图 + fit."""
        out = spec.get("out") or spec.get("path")
        if not out:
            return {"ok": False, "err": "缺 out"}
        try:
            rec = self.live.snap(out, view=spec.get("view"),
                                  fit=bool(spec.get("fit", True)))
            return rec if isinstance(rec, dict) else {"ok": True}
        except Exception as e:
            return {"ok": False, "err": f"{e}"}

    def op_snap_views(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """批量截图多视图.
        spec:
          out_dir:  输出目录
          prefix:   文件名前缀
          views:    视图列表 (默认 iso,front,back,left,right,top,bottom)
        """
        out_dir = Path(spec.get("out_dir", "."))
        out_dir.mkdir(parents=True, exist_ok=True)
        prefix = spec.get("prefix", "snap")
        views = spec.get("views") or list(SW_VIEWS.keys())[:7]
        results = {}
        ok_count = 0
        gdi_count = 0
        native_count = 0
        for v in views:
            out = out_dir / f"{prefix}_{v}.png"
            r = self.op_snap({"out": str(out), "view": v, "fit": True})
            results[v] = r
            if r.get("ok"):
                ok_count += 1
                via = r.get("via", "unknown")
                if via == "gdi_fallback":
                    gdi_count += 1
                elif via in ("sw_savebmp", "sw_saveas"):
                    native_count += 1
        rec = {"ok": ok_count == len(views),
               "pass": ok_count, "total": len(views),
               "native": native_count, "gdi_fallback": gdi_count,
               "views": results}
        if gdi_count > 0:
            rec["warn"] = f"snap_via_gdi_not_sw_viewport · {gdi_count}/{len(views)} frames"
        return rec

    # ──────────────────────────────────────────────────────────────────
    # ops · 诊断 / 活体
    # ──────────────────────────────────────────────────────────────────
    def op_bbox_world(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """读当前活动装配/零件的世界 BBox · 多路径降级.

        Assembly 优先: 遍历 IComponent2.GetBox(False,False) 累加 (最稳)
        Part 优先:     IPartDoc.GetPartBox(False) (modeled extents)
        通用回退:      IModelDoc2.GetBox · IModelDocExtension.GetBox
        """
        ad = self._active()
        if ad is None:
            return {"ok": False, "err": "无活动文档"}
        try:
            dt = ad.GetType if not callable(getattr(ad, "GetType", None)) else ad.GetType()
        except Exception:
            dt = -1
        trace: List[str] = []
        bx: Optional[Sequence[float]] = None

        # 路 1 (Assembly): 遍历 IComponent2.GetBox(False, False) · 世界 BBox 累加
        # 返 6 元 [xmin, ymin, zmin, xmax, ymax, zmax] 单位 m
        if dt == SW_DOC_ASSEMBLY or bx is None:
            try:
                from win32com.client import dynamic
            except Exception:
                dynamic = None
            try:
                asm = dynamic.Dispatch(ad._oleobj_) if dynamic else ad
                comps = asm.GetComponents(False) or []
                if comps:
                    lo = [float("inf")] * 3
                    hi = [float("-inf")] * 3
                    n_read = 0
                    for c in comps:
                        try:
                            cw = dynamic.Dispatch(c._oleobj_) if dynamic else c
                            cb = cw.GetBox(False, False)  # 世界坐标
                            if not cb or len(cb) < 6:
                                continue
                            lo[0] = min(lo[0], float(cb[0]))
                            lo[1] = min(lo[1], float(cb[1]))
                            lo[2] = min(lo[2], float(cb[2]))
                            hi[0] = max(hi[0], float(cb[3]))
                            hi[1] = max(hi[1], float(cb[4]))
                            hi[2] = max(hi[2], float(cb[5]))
                            n_read += 1
                        except Exception:
                            continue
                    if n_read > 0 and all(v != float("inf") for v in lo):
                        bx = [lo[0], lo[1], lo[2], hi[0], hi[1], hi[2]]
                        trace.append(f"Assembly.Components: ok n={n_read}/{len(comps)}")
            except Exception as e:
                trace.append(f"Assembly.Components: {type(e).__name__}:{e}")

        # 路 2 (Part): GetPartBox(False)
        if (not bx or len(bx) < 6) and dt == SW_DOC_PART:
            try:
                bx = ad.GetPartBox(False)
                if bx and len(bx) >= 6:
                    trace.append("GetPartBox: ok")
            except Exception as e:
                trace.append(f"GetPartBox: {type(e).__name__}:{e}")

        # 路 3 (通用): IModelDoc2.GetBox (property · 直取无括号)
        if not bx or len(bx) < 6:
            try:
                cand = ad.GetBox  # late-binding: SW 返 tuple/variant
                if not callable(cand):
                    bx = cand
                else:
                    bx = cand()
                if bx and len(bx) >= 6:
                    trace.append("ModelDoc.GetBox: ok")
            except Exception as e:
                trace.append(f"ModelDoc.GetBox: {type(e).__name__}:{e}")

        # 路 4 (Extension): IModelDocExtension.GetBox
        if not bx or len(bx) < 6:
            try:
                ex = ad.Extension
                cand = ex.GetBox
                if not callable(cand):
                    bx = cand
                else:
                    bx = ex.GetBox(0)  # nOptions=0 默认
                if bx and len(bx) >= 6:
                    trace.append("Extension.GetBox: ok")
            except Exception as e:
                trace.append(f"Extension.GetBox: {type(e).__name__}:{e}")

        if not bx or len(bx) < 6:
            return {"ok": False, "err": "GetBox 全路径失败", "trace": trace[:4]}
        try:
            vals = [float(v) * 1000 for v in list(bx)[:6]]
            xmin, ymin, zmin, xmax, ymax, zmax = vals
            return {"ok": True,
                    "xmin_mm": xmin, "ymin_mm": ymin, "zmin_mm": zmin,
                    "xmax_mm": xmax, "ymax_mm": ymax, "zmax_mm": zmax,
                    "cx_mm": (xmin + xmax) / 2, "cy_mm": (ymin + ymax) / 2,
                    "cz_mm": (zmin + zmax) / 2,
                    "w_mm": xmax - xmin, "h_mm": ymax - ymin, "d_mm": zmax - zmin,
                    "trace": trace[:4]}
        except Exception as e:
            return {"ok": False, "err": f"bbox parse: {e}", "raw": list(bx),
                    "trace": trace[:4]}

    def op_probe_local_bbox(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """逐零件打开 SLDPRT · GetPartBox · 收集局部 BBox.

        spec:
          parts:    {bname: sldprt_path}  或  [sldprt_path, ...]
          out:      (可选) JSON 输出路径
          close_each: bool 默认 False (不关, 后续复用)
        """
        parts = spec.get("parts")
        if not parts:
            return {"ok": False, "err": "缺 parts"}

        results = {}
        if isinstance(parts, list):
            parts_map = {Path(p).stem: p for p in parts}
        else:
            parts_map = parts

        for bn, path in parts_map.items():
            rec = {"sldprt": str(path)}
            try:
                staged = self.stage_file(path)
            except Exception as e:
                rec["err"] = f"stage: {e}"
                results[bn] = rec
                continue
            # 开
            open_rec = self.op_open({"path": str(staged), "readonly": True})
            if not open_rec.get("ok"):
                rec["err"] = f"open: {open_rec.get('err')}"
                results[bn] = rec
                continue
            time.sleep(0.5)
            # 量
            bb = self.op_bbox_world({})
            if bb.get("ok"):
                rec.update({k: v for k, v in bb.items() if k != "ok"})
            else:
                rec["err"] = f"bbox: {bb.get('err')}"
            results[bn] = rec

        # 输出
        if spec.get("out"):
            out = Path(spec["out"])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps({
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "parts": results,
            }, ensure_ascii=False, indent=2), encoding="utf-8")

        n_ok = sum(1 for r in results.values() if "cx_mm" in r)
        return {"ok": n_ok == len(parts_map),
                "count": n_ok, "total": len(parts_map),
                "parts": results}

    def op_diag_assembly(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """活体装配诊断 · 三源对账.
        spec:
          expected: {bname: expected_count}  BOM
          out:      (可选) JSON 输出路径
        """
        ad = self._active_asm()
        if ad is None:
            return {"ok": False, "err": "非装配文档"}

        lc = self.op_list_components({})
        if not lc.get("ok"):
            return {"ok": False, "err": f"list_components: {lc.get('err')}"}

        bname_count = {}
        for c in lc.get("components", []):
            bn = c.get("bname", "?")
            bname_count[bn] = bname_count.get(bn, 0) + 1

        # 整机 BBox
        bb = self.op_bbox_world({})
        expected = spec.get("expected", {})
        diag_bname = {}
        for bn, got in bname_count.items():
            exp = expected.get(bn)
            diag_bname[bn] = {"got": got, "expected": exp,
                              "ok": (exp is None or exp == got)}
        for bn, exp in expected.items():
            if bn not in diag_bname:
                diag_bname[bn] = {"got": 0, "expected": exp, "ok": False}

        all_ok = all(v["ok"] for v in diag_bname.values())
        out_rec = {
            "ok": all_ok and bb.get("ok", True),
            "component_count": lc.get("count"),
            "bname_count": bname_count,
            "bname_diag": diag_bname,
            "world_bbox": {k: v for k, v in bb.items() if k != "ok"} if bb.get("ok") else None,
        }
        if spec.get("out"):
            Path(spec["out"]).parent.mkdir(parents=True, exist_ok=True)
            Path(spec["out"]).write_text(
                json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"),
                            **out_rec,
                            "components": lc.get("components")},
                           ensure_ascii=False, indent=2),
                encoding="utf-8")
        return out_rec

    def op_mass_properties(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        ad = self._active_live_doc()
        if ad is None:
            return {"ok": False, "err": "无活动文档"}
        try:
            return ad.mass_properties()
        except Exception as e:
            return {"ok": False, "err": f"{e}"}

    # ──────────────────────────────────────────────────────────────────
    # 内部辅助
    # ──────────────────────────────────────────────────────────────────
    def _active(self):
        """获取活动文档 (raw COM)."""
        for src in (self.app_late, self.app):
            if src is None:
                continue
            try:
                ad = src.ActiveDoc
                if ad is not None:
                    return ad
            except Exception:
                pass
        return None

    def _active_asm(self):
        """获取活动装配 (raw) · 非装配返 None."""
        ad = self._active()
        if ad is None:
            return None
        try:
            dt = ad.GetType if not callable(getattr(ad, "GetType", None)) else ad.GetType()
        except Exception:
            return None
        if dt != SW_DOC_ASSEMBLY:
            return None
        try:
            from win32com.client import dynamic
            return dynamic.Dispatch(ad._oleobj_)
        except Exception:
            return ad

    def _active_live_doc(self):
        try:
            return self.live.active()
        except Exception:
            return None

    def _active_live_asm(self):
        d = self._active_live_doc()
        if d is None or not d.is_assembly:
            return None
        return d

    def _find_component(self, name_or_bname: str):
        """精确 Name2 → 模糊 bname 回退."""
        ad = self._active_asm()
        if ad is None:
            return None
        try:
            from win32com.client import dynamic
        except Exception:
            dynamic = None
        try:
            comps = ad.GetComponents(False) or []
        except Exception:
            return None
        # 精确
        for c in comps:
            cw = dynamic.Dispatch(c._oleobj_) if dynamic else c
            nm = _safe_name(cw)
            if nm == name_or_bname:
                return cw
        # bname 前缀
        for c in comps:
            cw = dynamic.Dispatch(c._oleobj_) if dynamic else c
            nm = _safe_name(cw)
            if nm and (_extract_bname(nm) == name_or_bname
                       or nm.startswith(name_or_bname)):
                return cw
        return None


# ════════════════════════════════════════════════════════════════════════
# 工具函数
# ════════════════════════════════════════════════════════════════════════
def _safe_name(comp) -> str:
    for attr in ("Name2", "Name"):
        try:
            v = getattr(comp, attr, None)
            if v is not None and not callable(v):
                return str(v)
        except Exception:
            pass
    return ""


def _extract_bname(name: str) -> str:
    """从 'hammer-1' 或 'hammer.step-1' 抽 'hammer'."""
    s = str(name).split("@")[0]
    if "-" in s:
        s = s.rsplit("-", 1)[0]
    for suf in (".step", ".stp", ".sldprt", ".SLDPRT", ".SLDPRT"):
        if s.lower().endswith(suf.lower()):
            return s[:-len(suf)]
    return s


def _ascii_safe_name(name: str, suffix: str = "") -> str:
    """生成一个 ASCII 安全的文件名. 若本身就 ASCII · 原样."""
    if all(ord(c) < 128 for c in name):
        return name
    import hashlib
    base = hashlib.md5(name.encode("utf-8")).hexdigest()[:12]
    return f"dao_{base}{suffix or ''}"


def _abbrev(d: Dict[str, Any], maxlen: int = 100) -> str:
    s = ", ".join(f"{k}={_v_abbrev(v)}" for k, v in d.items()
                  if k not in ("op", "idx", "trace"))
    if len(s) > maxlen:
        s = s[:maxlen-3] + "..."
    return s


def _v_abbrev(v) -> str:
    if isinstance(v, str) and len(v) > 40:
        return v[:37] + "..."
    if isinstance(v, (list, tuple)) and len(v) > 6:
        return f"[{len(v)}]"
    if isinstance(v, dict):
        return f"{{{len(v)}}}"
    return str(v)


# ════════════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════════════
def main():
    import argparse
    ap = argparse.ArgumentParser(description="SW 万法归一 op-stream 执行器")
    ap.add_argument("--ops", type=str, help="JSON 文件路径 (含 ops 列表) 或 '-' 读 stdin")
    ap.add_argument("--out", type=str, help="输出 JSON 报告")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    if args.ops:
        if args.ops == "-":
            ops_data = json.loads(sys.stdin.read())
        else:
            ops_data = json.loads(Path(args.ops).read_text(encoding="utf-8"))
        if isinstance(ops_data, dict) and "ops" in ops_data:
            ops = ops_data["ops"]
        else:
            ops = ops_data
    else:
        # self-test
        ops = [
            {"op": "ensure_live"},
            {"op": "list_docs"},
        ]

    omni = SWOmni(verbose=args.verbose)
    result = omni.execute_ops(ops)
    out_json = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(out_json, encoding="utf-8")
    print(out_json)
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
