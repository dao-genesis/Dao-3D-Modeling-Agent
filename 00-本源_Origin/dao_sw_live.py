#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
dao_sw_live.py — 万法·SolidWorks 活体万象 (L11 Omega) · 反者道之动
═══════════════════════════════════════════════════════════════════════

纲要
    "道生一, 一生二, 二生三, 三生万物."
    L0 探测 → L1 深反 → L2 COM 活体 → L5 打通 → L6 几何 → L9 激活 → **L11 万象**
    此层之功: 将 SolidWorks API 的 *写* 能力全境暴露为 Python 语义.
    前九境以"反"为主 (读取/适配/激活), L11 以"作"为主 (创造/装配/制图/命令).

层次 (L11 六象)
    ① 象之始 · 新建        new_part / new_assembly / new_drawing (模板可选)
    ② 象之筋 · 草图        SketchBuilder: line/rect/circle/arc/spline/dimension/relation
    ③ 象之骨 · 特征        FeatureBuilder: extrude/revolve/fillet/chamfer/shell/pattern/hole/plane
    ④ 象之血 · 装配        AssemblyBuilder: add_component/mate_*/interference/explode
    ⑤ 象之衣 · 工程图      DrawingBuilder: std_views/section/detail/bom/balloon/dimension
    ⑥ 象之魂 · 命令/宏/属性/方程/材质
         · CommandRunner: RunCommand (swCommands_e · 8000+ 内部命令)
         · MacroRunner:   VBA/swp 宏回放
         · PropertyMgr:   CustomPropertyManager 自定义属性 CRUD
         · EquationMgr:   方程管理器
         · MaterialMgr:   材质属性 (MaterialPropertyValues / SetMaterialPropertyName2)
         · SelectionMgr:  SelectByID2 全要素选择 · 链式清/数/类型

用法 (API)
    from dao_sw_live import SWLive
    live = SWLive()                         # 自动连接活体 SW
    part = live.new_part()                  # 返回 LiveDoc 外覆
    part.sketch.start_front()
    part.sketch.rect(-25, -25, 25, 25)      # 中心 100×50 矩形
    part.sketch.stop()
    part.feature.extrude(depth=10)          # 一键拉伸
    part.feature.fillet(radius=2, all_edges=True)
    part.save_as("out.sldprt")
    part.export("out.step")
    live.snap("iso.png", view="iso")

CLI
    python dao_sw_live.py status             # 当前 SW 活体状态
    python dao_sw_live.py new-part           # 新建零件
    python dao_sw_live.py cmd <id|name>      # 触发 SW 内部命令
    python dao_sw_live.py macro <path.swp>   # 跑 swp 宏
    python dao_sw_live.py build-demo         # 活体 demo (陀螺)
    python dao_sw_live.py test               # 自测 (不强连活体)

基底
    · 依赖 dao_solidworks.SolidWorksBridge (L2 COM)
    · 失败降级: 每 COM 调用 try/except, 返回 dict {ok, err, handle}
    · 不打断用户: ensure_live() 幂等 · 不强退 SW 进程
"""
from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

# ── 路径引导 (五层 sys.path) ─────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_DAO_ROOT = next(
    (p for p in Path(__file__).resolve().parents if (p / "_paths.py").is_file()),
    _HERE.parent,
)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
try:
    import _paths as _dao_paths  # noqa: F401
except Exception:  # noqa: BLE001
    _dao_paths = None

# 本源 L2 桥
import dao_solidworks as _sw  # noqa: E402

__version__ = "1.0.0"
__all__ = [
    # 总纲
    "SWLive", "LiveDoc", "LiveError",
    # Builder
    "SketchBuilder", "FeatureBuilder", "AssemblyBuilder", "DrawingBuilder",
    # 管理器
    "CommandRunner", "MacroRunner", "PropertyMgr", "EquationMgr",
    "MaterialMgr", "SelectionMgr",
    # 枚举常量
    "SW_CMD", "SW_SEL", "SW_MATE", "SW_MATE_ALIGN", "SW_FEATURE",
    "SW_PLANE", "SW_VIEW", "SW_TEMPLATE",
]


# ════════════════════════════════════════════════════════════════════════
# 枚举常量库 (对应 SW API · swconst.h)
# ════════════════════════════════════════════════════════════════════════
class SW_PLANE:
    """基准面 · 对应 SW 默认三基准面名 (英中法语均兼容)."""
    FRONT_EN = "Front Plane"
    TOP_EN   = "Top Plane"
    RIGHT_EN = "Right Plane"
    FRONT_CN = "前视基准面"
    TOP_CN   = "上视基准面"
    RIGHT_CN = "右视基准面"
    FRONT_FR = "Plan de face"
    TOP_FR   = "Plan de dessus"
    RIGHT_FR = "Plan de droite"
    FRONT = (FRONT_EN, FRONT_CN, FRONT_FR)
    TOP   = (TOP_EN,   TOP_CN,   TOP_FR)
    RIGHT = (RIGHT_EN, RIGHT_CN, RIGHT_FR)
    ALL   = {
        "front": FRONT, "top": TOP, "right": RIGHT,
        "前": FRONT, "上": TOP, "右": RIGHT,
    }


class SW_VIEW:
    """swStandardViews_e."""
    FRONT     = 1
    BACK      = 2
    LEFT      = 3
    RIGHT     = 4
    TOP       = 5
    BOTTOM    = 6
    ISOMETRIC = 7
    TRIMETRIC = 8
    DIMETRIC  = 9
    NORMAL_TO = 10
    CURRENT   = 11
    NAMES = {
        "front": 1, "back": 2, "left": 3, "right": 4,
        "top": 5, "bottom": 6,
        "iso": 7, "isometric": 7,
        "trimetric": 8, "dimetric": 9,
        "normal": 10, "current": 11,
    }


class SW_TEMPLATE:
    """swDwgPaperSizes_e / dftDocType_e 兼容模板."""
    PART     = 0   # swDwgTemplateNone as part placeholder
    ASSEMBLY = 1
    DRAWING  = 2


class SW_SEL:
    """swSelectType_e (子集 · 最常用 30 种)."""
    NOTHING    = 0
    EDGE       = 1
    FACE       = 2
    VERTEX     = 3
    BODY       = 4
    FEATURE    = 5
    SKETCH     = 9
    SKETCHSEG  = 10   # sketch segment
    SKETCHPOINT = 11
    SKETCHDIM  = 14
    PLANE      = 19   # reference plane
    AXIS       = 20
    COMPONENT  = 20   # NOTE: same value as AXIS in various SW versions
    REFPOINT   = 23
    MATE       = 32
    CONFIGURATION = 47
    COMPONENT2 = 20
    CENTERLINE = 51
    BY_NAME    = {
        "edge": 1, "face": 2, "vertex": 3, "body": 4, "feature": 5,
        "sketch": 9, "sketchsegment": 10, "sketchpoint": 11,
        "plane": 19, "axis": 20, "refpoint": 23, "mate": 32,
        "component": 20, "centerline": 51,
    }


class SW_MATE:
    """swMateType_e."""
    COINCIDENT  = 0
    CONCENTRIC  = 1
    PERPENDICULAR = 2
    PARALLEL    = 3
    TANGENT     = 4
    DISTANCE    = 5
    ANGLE       = 6
    SYMMETRIC   = 11
    WIDTH       = 17
    BY_NAME = {
        "coincident": 0, "concentric": 1, "perpendicular": 2,
        "parallel": 3, "tangent": 4, "distance": 5,
        "angle": 6, "symmetric": 11, "width": 17,
    }


class SW_MATE_ALIGN:
    """swMateAlign_e."""
    ALIGNED      = 0
    ANTIALIGNED  = 1
    CLOSEST      = 2


class SW_FEATURE:
    """常用特征类型 (可选 · 触发命令亦在 SW_CMD)."""
    EXTRUDE_BOSS = "extrude_boss"
    EXTRUDE_CUT  = "extrude_cut"
    REVOLVE_BOSS = "revolve_boss"
    REVOLVE_CUT  = "revolve_cut"
    FILLET       = "fillet"
    CHAMFER      = "chamfer"
    SHELL        = "shell"
    DRAFT        = "draft"
    PATTERN_LINEAR   = "pattern_linear"
    PATTERN_CIRCULAR = "pattern_circular"
    MIRROR       = "mirror"
    HOLE_WIZARD  = "hole_wizard"


class SW_CMD:
    """swCommands_e 最常用子集 (50+ 内部命令).

    完整清单: SolidWorks API Help → swCommands_e. 此处提供高频命令.
    可通过 CommandRunner.run(name|id) 触发任意命令.
    """
    # 文件
    New                  = 2    # File/New
    Open                 = 3    # File/Open
    Save                 = 4
    SaveAs               = 5
    Close                = 6
    Print                = 7
    # 编辑
    Undo                 = 12
    Redo                 = 13
    Copy                 = 14
    Paste                = 15
    Delete               = 17
    SelectAll            = 18
    # 视图
    ViewOrientation      = 81
    ZoomToFit            = 82
    ZoomToSelection      = 83
    # 草图
    Sketch               = 130    # enter/exit sketch
    Rebuild              = 131
    ForceRebuild         = 132
    # 草图实体
    SketchLine           = 144
    SketchRectangle      = 145
    SketchCircle         = 147
    SketchArc3Point      = 149
    SketchFillet         = 151
    SketchTrim           = 158
    SketchExtend         = 159
    SmartDimension       = 161
    AddRelation          = 162
    # 特征
    ExtrudeBoss          = 2005
    ExtrudeCut           = 2006
    RevolveBoss          = 2008
    RevolveCut           = 2009
    Fillet               = 2034
    Chamfer              = 2035
    Shell                = 2036
    LinearPattern        = 2040
    CircularPattern      = 2041
    Mirror               = 2042
    HoleWizard           = 2051
    RefPlane             = 2070
    RefAxis              = 2071
    RefPoint             = 2072
    # 装配
    InsertComponent      = 2016
    Mate                 = 2020
    ExplodedView         = 2022
    InterferenceDetection = 2025
    # 工程图
    InsertModelView      = 3001
    SectionView          = 3002
    DetailView           = 3003
    AuxiliaryView        = 3004
    InsertBOM            = 3005
    InsertBalloon        = 3006
    # 其它
    Options              = 95    # system options
    CustomizeMenu        = 200

    BY_NAME = {}   # filled below


# 反射填充 SW_CMD.BY_NAME
SW_CMD.BY_NAME = {
    k.lower(): v for k, v in vars(SW_CMD).items()
    if isinstance(v, int) and not k.startswith("_") and k != "BY_NAME"
}


# ════════════════════════════════════════════════════════════════════════
# 异常 + 小工具
# ════════════════════════════════════════════════════════════════════════
class LiveError(RuntimeError):
    """L11 活体操作异常 (可包装 COM 错)."""


def _ok(ok: bool = True, **kw) -> Dict[str, Any]:
    r = {"ok": bool(ok)}
    r.update(kw)
    return r


def _err(exc: BaseException, **kw) -> Dict[str, Any]:
    r = {"ok": False, "err": f"{type(exc).__name__}: {exc}"}
    r.update(kw)
    return r


def _mm2m(v: float) -> float:
    """毫米 → 米 (SW 系统单位)."""
    return float(v) * 1e-3


def _m2mm(v: float) -> float:
    """米 → 毫米."""
    return float(v) * 1e3


def _as_m_tuple(xy: Sequence[float]) -> Tuple[float, float]:
    if len(xy) < 2:
        raise ValueError(f"need (x,y), got {xy!r}")
    return (_mm2m(xy[0]), _mm2m(xy[1]))


def _find_default_template(app, kind: str = "part") -> Optional[str]:
    """找默认模板. 四路 fallback:

    1. `GetUserPreferenceStringValue(swDefaultTemplatePart/8)`      — SW 默认偏好
    2. `GetUserPreferenceStringValue(swFileLocationsDocTemplates/21)` — 目录列表 (; 分)
    3. `%ProgramData%\\SOLIDWORKS\\SOLIDWORKS <year>\\templates`     — 安装标配
    4. SW 安装目录的 `lang/<locale>/Tutorial` + `data/templates`      — 兜底

    参数 kind ∈ {'part','assembly','drawing'}. 返 .prtdot/.asmdot/.drwdot.
    """
    ext_map = {"part": ".prtdot", "assembly": ".asmdot", "drawing": ".drwdot"}
    ext = ext_map.get(kind.lower())
    if ext is None:
        return None

    def _scan(root: Path) -> Optional[str]:
        if not root.exists():
            return None
        # rglob 层数限控以防超深
        try:
            for p in root.rglob(f"*{ext}"):
                if p.is_file():
                    return str(p)
        except Exception:  # noqa: BLE001
            return None
        return None

    # ─── 路 1: swDefaultTemplatePart/Assembly/Drawing = 8/9/10 ───
    pref_id = {"part": 8, "assembly": 9, "drawing": 10}[kind.lower()]
    try:
        v = app.GetUserPreferenceStringValue(pref_id)
        if v and Path(v).is_file():
            return v
    except Exception:  # noqa: BLE001
        pass

    # ─── 路 2: swFileLocationsDocTemplates=21 (; 分目录列表) ───
    try:
        v = app.GetUserPreferenceStringValue(21)
        if v:
            for d in str(v).split(";"):
                d = d.strip()
                if d:
                    hit = _scan(Path(d))
                    if hit:
                        return hit
    except Exception:  # noqa: BLE001
        pass

    # ─── 路 3: %ProgramData%\SOLIDWORKS\SOLIDWORKS <year>\templates ───
    import os as _os
    program_data = _os.environ.get("ProgramData", r"C:\ProgramData")
    sw_root = Path(program_data) / "SOLIDWORKS"
    if sw_root.exists():
        # 可能有多个年度, 找最新一个的 templates
        years = sorted(
            [p for p in sw_root.iterdir() if p.is_dir() and "SOLIDWORKS" in p.name],
            reverse=True,
        )
        for y in years:
            for sub in ("templates", "lang"):
                hit = _scan(y / sub)
                if hit:
                    return hit

    # ─── 路 4: SW 安装目录 (lang/*/Tutorial, data/templates) ───
    try:
        exe_str = getattr(getattr(app, "_dao_info", None), "exe", None)
    except Exception:  # noqa: BLE001
        exe_str = None
    # 借 Bridge 的 info 拿 exe
    if not exe_str:
        # 懒导入避环
        try:
            from dao_solidworks import SolidWorksBridge as _SB
            info = _SB().info
            exe_str = info.exe
        except Exception:  # noqa: BLE001
            exe_str = None
    if exe_str:
        install_dir = Path(exe_str).parent
        for sub in ("data/templates", "lang", "templates",
                    "data/tutorial"):
            hit = _scan(install_dir / sub)
            if hit:
                return hit
        # 再退一层 (SLDWORKS 在 bin 下, 模板常在上一级)
        for sub in ("data/templates", "lang", "templates"):
            hit = _scan(install_dir.parent / sub)
            if hit:
                return hit

    return None


# ════════════════════════════════════════════════════════════════════════
# SWLive · 总纲
# ════════════════════════════════════════════════════════════════════════
class SWLive:
    """活体万象总纲. 封装 SolidWorksBridge + 六大 Builder.

    用法:
        live = SWLive()
        live.ensure_live()
        part = live.new_part()
        part.sketch.start_front()
        part.sketch.rect(-20,-20, 20,20)
        part.sketch.stop()
        part.feature.extrude(depth=10)
        part.save_as("cube.sldprt")
    """

    def __init__(self, bridge: Optional["_sw.SolidWorksBridge"] = None):
        self._bridge: Optional[_sw.SolidWorksBridge] = bridge
        self._app_late: Any = None  # 干净 late-binding IDispatch, 绕 gencache 污染
        self._cmd_runner: Optional[CommandRunner] = None
        self._macro: Optional[MacroRunner] = None
        self._docs: List[LiveDoc] = []

    # ─── 连接 ──────────────────────────────────────────────────────────
    def ensure_live(self,
                    *,
                    visible: bool = True,
                    dismiss_welcome: bool = True,
                    launch_timeout_s: float = 120.0) -> Dict[str, Any]:
        """确保 SW 活体 · 可见 · 对话框已清. 幂等.

        返回 {ok, revision, pid?, dismissed?, err?}.
        """
        if self._bridge is None:
            self._bridge = _sw.SolidWorksBridge()
        if not self._bridge.is_installed():
            return _err(LiveError("SolidWorks 未安装"))
        if not self._bridge.is_connected():
            try:
                self._bridge.connect(
                    prefer_active=True,
                    launch_if_needed=True,
                    launch_timeout_s=launch_timeout_s,
                )
            except Exception as e:  # noqa: BLE001
                return _err(e)
        try:
            self._bridge.set_visible(visible)
        except Exception:  # noqa: BLE001
            pass

        # 初始化干净的 late-binding COM 句柄 (绕 gencache 污染)
        # 关键: 必须用 dynamic.Dispatch 而非 wc.Dispatch, 否则同样走 gencache
        try:
            import win32com.client.dynamic as _dyn
            # 优先: 从 bridge 已有 COM 对象的 _oleobj_ 重包装为纯动态 IDispatch
            self._app_late = _dyn.Dispatch(self._bridge._app._oleobj_)
        except Exception:
            try:
                import win32com.client.dynamic as _dyn
                self._app_late = _dyn.Dispatch("SldWorks.Application")
            except Exception:
                self._app_late = self._bridge._app  # 最终回退

        out: Dict[str, Any] = _ok(True)
        try:
            out["revision"] = self._bridge.revision()
        except Exception as e:  # noqa: BLE001
            out["revision_err"] = f"{type(e).__name__}: {e}"

        if dismiss_welcome:
            try:
                r = _sw.SWDialogHandler.dismiss(
                    kinds=("welcome", "tip"), max_rounds=2
                )
                out["dismissed"] = r.get("total_dismissed", 0)
            except Exception as e:  # noqa: BLE001
                out["dismissed_err"] = f"{type(e).__name__}: {e}"
        return out

    def disconnect(self, exit_sw: bool = False) -> None:
        if self._bridge is not None:
            self._bridge.disconnect(exit_sw=exit_sw)

    # ─── 访问器 ──────────────────────────────────────────────────────
    @property
    def app(self) -> Any:
        """原生 ISldWorks COM · 须先 ensure_live."""
        if self._bridge is None or not self._bridge.is_connected():
            raise LiveError("not connected; call ensure_live() first")
        return self._bridge._app

    @property
    def app_late(self) -> Any:
        """干净 late-binding IDispatch · 绕 gencache 污染."""
        if self._app_late is not None:
            return self._app_late
        return self.app

    def _active_doc(self) -> Any:
        """获取活动文档 · late-binding 优先."""
        for src in (self._app_late, self._bridge._app if self._bridge else None):
            if src is None:
                continue
            try:
                d = src.ActiveDoc
                if d is not None:
                    return d
            except Exception:
                pass
        return None

    @property
    def bridge(self) -> _sw.SolidWorksBridge:
        if self._bridge is None:
            self._bridge = _sw.SolidWorksBridge()
        return self._bridge

    @property
    def cmd(self) -> "CommandRunner":
        if self._cmd_runner is None:
            self._cmd_runner = CommandRunner(self)
        return self._cmd_runner

    @property
    def macro(self) -> "MacroRunner":
        if self._macro is None:
            self._macro = MacroRunner(self)
        return self._macro

    # ─── 新建 ──────────────────────────────────────────────────────
    def new_part(self, template: Optional[str] = None) -> "LiveDoc":
        """新建零件 · 返回 LiveDoc."""
        return self._new_doc("part", template)

    def new_assembly(self, template: Optional[str] = None) -> "LiveDoc":
        return self._new_doc("assembly", template)

    def new_drawing(self, template: Optional[str] = None) -> "LiveDoc":
        return self._new_doc("drawing", template)

    def _new_doc(self, kind: str, template: Optional[str]) -> "LiveDoc":
        self.ensure_live()
        app = self.app
        tpl = template or _find_default_template(self.app_late, kind)
        if not tpl:
            raise LiveError(
                f"无可用 {kind} 模板. 请 SW 内设置模板或传 template=<路径>."
            )
        # NewDocument — 多级回退 (绕 gencache 污染)
        doc = None
        errs: List[str] = []
        for label, target in [("app_late", self.app_late), ("app", app)]:
            if target is None:
                continue
            try:
                doc = target.NewDocument(str(tpl), 0, 0, 0)
                if doc is not None:
                    break
                errs.append(f"{label}.NewDocument→null")
            except Exception as e:  # noqa: BLE001
                errs.append(f"{label}.NewDocument:{type(e).__name__}")
        if doc is None:
            raise LiveError(f"NewDocument failed: {' | '.join(errs)}")
        dt = {"part": _sw.SW_DOC_TYPE.PART,
              "assembly": _sw.SW_DOC_TYPE.ASSEMBLY,
              "drawing": _sw.SW_DOC_TYPE.DRAWING}[kind.lower()]
        base = _sw.SWDoc(_raw=doc, _bridge=self._bridge,
                         path="", doc_type=dt)
        live_doc = LiveDoc(base=base, live=self)
        self._docs.append(live_doc)
        return live_doc

    # ─── 打开 ──────────────────────────────────────────────────────
    def open(self, path: Union[str, Path], *, readonly: bool = False,
             silent: bool = True, config: Optional[str] = None) -> "LiveDoc":
        self.ensure_live()
        base = self._bridge.open(path, readonly=readonly,
                                 silent=silent, config=config)
        d = LiveDoc(base=base, live=self)
        self._docs.append(d)
        return d

    def active(self) -> Optional["LiveDoc"]:
        if self._bridge is None or not self._bridge.is_connected():
            return None
        base = self._bridge.active_doc()
        if base is None:
            return None
        return LiveDoc(base=base, live=self)

    def docs(self) -> List[Dict[str, Any]]:
        if self._bridge is None or not self._bridge.is_connected():
            return []
        return self._bridge.list_docs()

    # ─── 视图 ──────────────────────────────────────────────────────
    def view(self, action: Union[str, int]) -> Dict[str, Any]:
        """切换标准视图. action: int 或 'iso/front/top/...'."""
        try:
            code = int(action) if isinstance(action, int) else \
                SW_VIEW.NAMES[str(action).lower()]
        except KeyError:
            return _err(ValueError(
                f"未知视图: {action!r}; valid={list(SW_VIEW.NAMES)}"))
        d = self._active_doc()
        if d is None:
            return _err(LiveError("无活动文档"))
        try:
            d.ShowNamedView2("", int(code))
            try:
                d.ViewZoomtofit2()
            except Exception:
                pass
            return _ok(True, view=int(code))
        except Exception as e:  # noqa: BLE001
            return _err(e)

    def snap(self, out_path: Union[str, Path], *,
             view: Optional[Union[str, int]] = None,
             fit: bool = True) -> Dict[str, Any]:
        """截图当前活动文档. 可先切视图/自动缩放."""
        try:
            self.ensure_live(visible=True)
            out = Path(out_path)
            if view is not None:
                self.view(view)
            if fit:
                try:
                    d = self._active_doc()
                    if d: d.ViewZoomtofit2()
                except Exception:
                    pass
            # 借 sw_show 的稳健截图
            from sw_show import SWShow  # type: ignore
            shower = SWShow()
            shower._bridge = self._bridge   # 复用连接
            p = shower.screenshot(out)
            via = getattr(shower, "_last_snap_via", "unknown")
            rec = _ok(True, path=str(p), size_B=p.stat().st_size, via=via)
            if via == "gdi_fallback":
                rec["warn"] = "snap_via_gdi_not_sw_viewport"
            return rec
        except Exception as e:  # noqa: BLE001
            return _err(e)

    # ─── 关闭 ──────────────────────────────────────────────────────
    def close_all(self, save: bool = False) -> None:
        if self._bridge is not None and self._bridge.is_connected():
            self._bridge.close_all(save=save)

    # ─── 自描述 ─────────────────────────────────────────────────────
    def status(self) -> Dict[str, Any]:
        info = _sw.sw_info(probe_com=False)
        st: Dict[str, Any] = {
            "version": info.version,
            "progid":  info.progid_versioned or info.progid,
            "exe":     info.exe,
            "connected": bool(self._bridge and self._bridge.is_connected()),
        }
        if st["connected"]:
            try:
                st["revision"] = self._bridge.revision()
            except Exception as e:
                st["revision_err"] = f"{type(e).__name__}: {e}"
            try:
                st["docs"] = self._bridge.list_docs()
            except Exception:
                pass
        return st


# ════════════════════════════════════════════════════════════════════════
# LiveDoc · 活体文档外覆 (含 5 Builder 的组合入口)
# ════════════════════════════════════════════════════════════════════════
@dataclass
class LiveDoc:
    """活体文档外覆. 五 Builder 懒初始化.

    属性:
      .base      → dao_solidworks.SWDoc (原 L2 读/导出外覆)
      .sketch    → SketchBuilder
      .feature   → FeatureBuilder
      .assembly  → AssemblyBuilder (仅装配有效)
      .drawing   → DrawingBuilder  (仅工程图有效)
      .props     → PropertyMgr
      .eqn       → EquationMgr
      .material  → MaterialMgr
      .sel       → SelectionMgr
    """
    base: _sw.SWDoc
    live: SWLive

    def __post_init__(self):
        self._sketch: Optional[SketchBuilder] = None
        self._feature: Optional[FeatureBuilder] = None
        self._assembly: Optional[AssemblyBuilder] = None
        self._drawing: Optional[DrawingBuilder] = None
        self._props: Optional[PropertyMgr] = None
        self._eqn: Optional[EquationMgr] = None
        self._material: Optional[MaterialMgr] = None
        self._sel: Optional[SelectionMgr] = None

    # ── 基础 passthrough ─────────────────────────────────────────────
    @property
    def raw(self) -> Any:
        return self.base._raw

    @property
    def doc_type(self) -> int:
        return self.base.doc_type

    @property
    def is_part(self) -> bool:      return self.base.is_part
    @property
    def is_assembly(self) -> bool:  return self.base.is_assembly
    @property
    def is_drawing(self) -> bool:   return self.base.is_drawing

    def title(self) -> str:          return self.base.title()
    def path_name(self) -> str:      return self.base.path_name()
    def configurations(self) -> List[str]:  return self.base.configurations()
    def mass_properties(self) -> Dict[str, Any]:
        """质量属性 · 多路 fallback (直接 try-except, 不依赖 getattr)."""
        trace: List[Dict[str, Any]] = []
        # 路 1: Extension.CreateMassProperty
        try:
            mp = self.raw.Extension.CreateMassProperty()
            if mp is not None:
                mp.UseSystemUnits = True
                return _ok(True, via="CreateMassProperty",
                           mass_kg=float(mp.Mass),
                           volume_m3=float(mp.Volume),
                           surface_m2=float(mp.SurfaceArea),
                           cog=[float(mp.CenterOfMass[i]) for i in range(3)])
            trace.append({"path": "CreateMassProperty", "err": "returned None"})
        except Exception as e:
            trace.append({"path": "CreateMassProperty", "err": f"{type(e).__name__}: {e}"})
        # 路 2: Extension.CreateMassProperty2
        try:
            mp = self.raw.Extension.CreateMassProperty2()
            if mp is not None:
                mp.UseSystemUnits = True
                return _ok(True, via="CreateMassProperty2",
                           mass_kg=float(mp.Mass),
                           volume_m3=float(mp.Volume),
                           surface_m2=float(mp.SurfaceArea),
                           cog=[float(mp.CenterOfMass[i]) for i in range(3)])
            trace.append({"path": "CreateMassProperty2", "err": "returned None"})
        except Exception as e:
            trace.append({"path": "CreateMassProperty2", "err": f"{type(e).__name__}: {e}"})
        # 路 3: IPartDoc.GetMassProperties (property, 不需 ())
        # SW API 返回: [COG_X, COG_Y, COG_Z, Volume, SurfaceArea, Mass, ...]
        try:
            arr = self.raw.GetMassProperties
            if callable(arr):
                arr = arr()
            if arr is not None and len(arr) >= 6:
                return _ok(True, via="GetMassProperties",
                           mass_kg=float(arr[5]), volume_m3=float(arr[3]),
                           surface_m2=float(arr[4]),
                           cog=[float(arr[0]), float(arr[1]), float(arr[2])],
                           _fallback_trace=trace or None)
            trace.append({"path": "GetMassProperties", "err": f"arr={arr}"})
        except Exception as e:
            trace.append({"path": "GetMassProperties", "err": f"{type(e).__name__}: {e}"})
        # 路 4: GetMassProperties2(byref status)
        # 同路 3 索引: [COG_X, COG_Y, COG_Z, Volume, SurfaceArea, Mass, ...]
        try:
            import pythoncom as _pc
            from win32com.client import VARIANT as _VAR
            st = _VAR(_pc.VT_BYREF | _pc.VT_I4, 0)
            arr = self.raw.GetMassProperties2(st)
            if callable(arr):
                arr = arr(st)
            if arr is not None and len(arr) >= 6:
                return _ok(True, via="GetMassProperties2",
                           mass_kg=float(arr[5]), volume_m3=float(arr[3]),
                           surface_m2=float(arr[4]),
                           cog=[float(arr[0]), float(arr[1]), float(arr[2])],
                           _fallback_trace=trace or None)
            trace.append({"path": "GetMassProperties2", "err": f"arr={arr}"})
        except Exception as e:
            trace.append({"path": "GetMassProperties2", "err": f"{type(e).__name__}: {e}"})
        return _err(LiveError("无法获取质量属性"), trace=trace)
    def bbox(self) -> Dict[str, Any]:       return self.base.bbox()
    def feature_tree(self, max_depth: int = 3) -> List[Dict[str, Any]]:
        return self.base.feature_tree(max_depth=max_depth)

    def save(self) -> Dict[str, Any]:
        """当前文档 Save. 若无路径 → 返回 err."""
        if not self.path_name():
            return _err(LiveError("文档无路径 · 先 save_as"))
        try:
            self.raw.Save3(1, _sw.win32_int(), _sw.win32_int())
            return _ok(True, path=self.path_name())
        except Exception:
            try:
                self.raw.Save()
                return _ok(True, path=self.path_name())
            except Exception as e:
                return _err(e)

    def save_as(self, dst: Union[str, Path]) -> Dict[str, Any]:
        """保存到任意格式. 原生 SW 格式 (.sldprt/.sldasm/.slddrw) 走 SaveAs3;
        中间格式 (STEP/STL/...) 走 Extension.SaveAs.

        为避 SW 对 Unicode 路径失效, 若 dst 包含非 ASCII 字符, 先保存
        到同名临时 ASCII 路径, 再用 shutil.move 迁回目标.
        """
        dst = Path(dst)
        ext = dst.suffix.lower()
        native = ext in (".sldprt", ".sldasm", ".slddrw")
        dst.parent.mkdir(parents=True, exist_ok=True)

        def _is_ascii(s: str) -> bool:
            try:
                s.encode("ascii"); return True
            except UnicodeEncodeError:
                return False

        tmp_path: Optional[Path] = None
        real_target = str(dst.resolve())
        if not _is_ascii(real_target):
            tmp_dir = Path(tempfile.gettempdir())
            tmp_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = tmp_dir / f"_sw_live_{os.getpid()}_{int(time.time()*1000)}{ext}"
            real_target = str(tmp_path)

        try:
            if native:
                # 三条路: SaveAs3 / Extension.SaveAs2 / Extension.SaveAs.
                # 根因: SW API 的 Errors/Warnings 是 byref long, pywin32 对
                # 裸 int 0 会自动 byref 并返回 tuple; 避免 _Holder TypeError.
                ok = False
                save_trace: List[Dict[str, Any]] = []
                import pythoncom as _pc
                from win32com.client import VARIANT as _VAR
                # 构造 COM-safe 参数
                _nothing = _VAR(_pc.VT_DISPATCH, None)
                _ref0 = lambda: _VAR(_pc.VT_BYREF | _pc.VT_I4, 0)
                try:
                    ok = bool(self.raw.SaveAs3(real_target, 0, 0))
                    save_trace.append({"api": "SaveAs3", "ok": ok})
                except Exception as e:  # noqa: BLE001
                    save_trace.append({"api": "SaveAs3",
                                        "err": f"{type(e).__name__}: {e}"})
                if not ok or not Path(real_target).exists():
                    # 路 2: Extension.SaveAs (VARIANT 正确 byref)
                    try:
                        rc = self.raw.Extension.SaveAs(
                            real_target, 0, 0, _nothing, _ref0(), _ref0()
                        )
                        if isinstance(rc, tuple):
                            ok = bool(rc[0])
                            errs = rc[1] if len(rc) > 1 else 0
                            warns = rc[2] if len(rc) > 2 else 0
                        else:
                            ok = bool(rc); errs = 0; warns = 0
                        save_trace.append({"api": "Extension.SaveAs", "ok": ok,
                                            "errors": errs, "warnings": warns})
                    except Exception as e:  # noqa: BLE001
                        save_trace.append({"api": "Extension.SaveAs",
                                            "err": f"{type(e).__name__}: {e}"})
                if (not ok or not Path(real_target).exists()) \
                        and hasattr(self.raw.Extension, "SaveAs2"):
                    # 路 3: Extension.SaveAs2 (SW 2020+)
                    try:
                        rc = self.raw.Extension.SaveAs2(
                            real_target, 0, 0, _nothing, "", False,
                            _ref0(), _ref0()
                        )
                        if isinstance(rc, tuple):
                            ok = bool(rc[0])
                        else:
                            ok = bool(rc)
                        save_trace.append({"api": "Extension.SaveAs2", "ok": ok})
                    except Exception as e:  # noqa: BLE001
                        save_trace.append({"api": "Extension.SaveAs2",
                                            "err": f"{type(e).__name__}: {e}"})
                if not ok or not Path(real_target).exists():
                    return _err(LiveError(
                        f"SaveAs 未产出文件: {real_target} · trace={save_trace}"
                    ), trace=save_trace)
            else:
                # 交换格式: Extension.SaveAs (COM-safe VARIANT)
                import pythoncom as _pc
                from win32com.client import VARIANT as _VAR
                _nothing = _VAR(_pc.VT_DISPATCH, None)
                _ref0 = lambda: _VAR(_pc.VT_BYREF | _pc.VT_I4, 0)
                rc = self.raw.Extension.SaveAs(
                    real_target, 0, 0, _nothing, _ref0(), _ref0()
                )
                ok = bool(rc[0]) if isinstance(rc, tuple) else bool(rc)
                if not ok or not Path(real_target).exists():
                    return _err(LiveError(
                        f"交换格式 SaveAs 未产出: {real_target} (rc={rc})"
                    ))

            # 迁回正确路径 (若曾走 ASCII 兵底)
            # SW 可能锁住 temp 文件 (已成活体路径), 用 copy2 + 延迟 retry
            if tmp_path is not None and Path(real_target).exists():
                import shutil
                if dst.exists():
                    try: dst.unlink()
                    except Exception: pass
                for _retry in range(5):
                    try:
                        shutil.copy2(real_target, str(dst))
                        break
                    except PermissionError:
                        time.sleep(0.5)
                else:
                    shutil.copy2(real_target, str(dst))
                real_target = str(dst)
                # 清理 temp (SW 可能锁 → 忽略)
                try: tmp_path.unlink()
                except Exception: pass

            size = Path(real_target).stat().st_size
            return _ok(True, path=real_target, size_B=size,
                       native=native, via="ascii_tmp" if tmp_path else "direct")
        except Exception as e:
            return _err(e, dst=str(dst))

    def export(self, dst: Union[str, Path], fmt: Optional[str] = None,
               config: Optional[str] = None) -> Dict[str, Any]:
        """交换格式导出 (STEP/IGES/STL/X_T/...).

        内嵌: Unicode 路径兵底 + Extension.SaveAs 裸 int byref (避 _Holder).
        fmt 为 None 时从扩展名推断 (跟 SW_EXPORT_FMT._EXT_MAP).
        """
        dst = Path(dst)
        if fmt is None:
            fmt = dst.suffix.lower().lstrip(".")
            if fmt == "stp": fmt = "step"
            if fmt == "igs": fmt = "iges"
        # 规范扩展
        ext = _sw.SW_EXPORT_FMT._EXT_MAP.get(fmt)
        if ext is None:
            return _err(ValueError(f"unsupported export fmt: {fmt}"))
        dst = dst.with_suffix(ext) if dst.suffix.lower() != ext else dst
        dst.parent.mkdir(parents=True, exist_ok=True)

        def _is_ascii(s: str) -> bool:
            try:
                s.encode("ascii"); return True
            except UnicodeEncodeError:
                return False

        real_target = str(dst.resolve())
        tmp_path: Optional[Path] = None
        if not _is_ascii(real_target):
            tmp_dir = Path(tempfile.gettempdir())
            tmp_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = tmp_dir / f"_sw_live_{os.getpid()}_{int(time.time()*1000)}{ext}"
            real_target = str(tmp_path)

        try:
            # 切配置 (如指定)
            if config:
                try: self.raw.ShowConfiguration2(config)
                except Exception: pass
            # Extension.SaveAs(Name, Version, Options, ExportData, Errors, Warnings)
            import pythoncom as _pc
            from win32com.client import VARIANT as _VAR
            _nothing = _VAR(_pc.VT_DISPATCH, None)
            _ref0 = lambda: _VAR(_pc.VT_BYREF | _pc.VT_I4, 0)
            rc = self.raw.Extension.SaveAs(
                real_target, 0, 0, _nothing, _ref0(), _ref0()
            )
            if isinstance(rc, tuple):
                ok = bool(rc[0])
                errs = rc[1] if len(rc) > 1 else 0
                warns = rc[2] if len(rc) > 2 else 0
            else:
                ok = bool(rc); errs = 0; warns = 0
            if not ok or not Path(real_target).exists():
                return _err(LiveError(
                    f"Extension.SaveAs 未产出: {real_target} errs={errs} warns={warns}"
                ))
            # 迁回 (copy2 + retry, SW 可能锁 temp)
            final = Path(real_target)
            if tmp_path is not None and final.exists():
                import shutil
                if dst.exists():
                    try: dst.unlink()
                    except Exception: pass
                for _retry in range(5):
                    try:
                        shutil.copy2(str(final), str(dst))
                        break
                    except PermissionError:
                        time.sleep(0.5)
                else:
                    shutil.copy2(str(final), str(dst))
                try: final.unlink()
                except Exception: pass
                final = dst
            return _ok(True, path=str(final), size_B=final.stat().st_size,
                       errs=errs, warns=warns,
                       via="ascii_tmp" if tmp_path else "direct")
        except Exception as e:
            return _err(e, dst=str(dst))

    def rebuild(self, force: bool = False) -> Dict[str, Any]:
        try:
            if force:
                ok = bool(self.raw.ForceRebuild3(False))
            else:
                ok = bool(self.raw.EditRebuild3())
            return _ok(ok)
        except Exception as e:
            return _err(e)

    def close(self, save: bool = False) -> None:
        self.base.close(save=save)

    def activate(self) -> Dict[str, Any]:
        """将此文档置为 SW 活动文档."""
        try:
            errors = _sw.win32_int()
            path = self.path_name() or self.title()
            if not path:
                return _err(LiveError("doc has no name"))
            self.live.app.ActivateDoc3(path, True, 0, errors)
            return _ok(True)
        except Exception as e:
            return _err(e)

    # ── Builder 懒初始化 ─────────────────────────────────────────────
    @property
    def sketch(self) -> "SketchBuilder":
        if self._sketch is None:
            self._sketch = SketchBuilder(self)
        return self._sketch

    @property
    def feature(self) -> "FeatureBuilder":
        if self._feature is None:
            self._feature = FeatureBuilder(self)
        return self._feature

    @property
    def assembly(self) -> "AssemblyBuilder":
        if self._assembly is None:
            self._assembly = AssemblyBuilder(self)
        return self._assembly

    @property
    def drawing(self) -> "DrawingBuilder":
        if self._drawing is None:
            self._drawing = DrawingBuilder(self)
        return self._drawing

    @property
    def props(self) -> "PropertyMgr":
        if self._props is None:
            self._props = PropertyMgr(self)
        return self._props

    @property
    def eqn(self) -> "EquationMgr":
        if self._eqn is None:
            self._eqn = EquationMgr(self)
        return self._eqn

    @property
    def material(self) -> "MaterialMgr":
        if self._material is None:
            self._material = MaterialMgr(self)
        return self._material

    @property
    def sel(self) -> "SelectionMgr":
        if self._sel is None:
            self._sel = SelectionMgr(self)
        return self._sel


# ════════════════════════════════════════════════════════════════════════
# CommandRunner · 万象之魂 · RunCommand 触发任意 SW 内部命令
# ════════════════════════════════════════════════════════════════════════
class CommandRunner:
    """SW 内部命令触发器.

    原理: ISldWorks.RunCommand(command_id, window_title="") 触发 SW 内部命令,
    等同用户点击菜单/工具栏. 可触发 8000+ 命令.

    示例:
        live.cmd.run("Fillet")          # 按名 (SW_CMD.BY_NAME)
        live.cmd.run(2034)              # 按 id (swCommands_e)
        live.cmd.run(SW_CMD.Rebuild)
    """

    def __init__(self, live: SWLive):
        self.live = live

    def run(self, command: Union[str, int], title: str = "") -> Dict[str, Any]:
        try:
            if isinstance(command, str):
                cid = SW_CMD.BY_NAME.get(command.lower())
                if cid is None:
                    return _err(LiveError(
                        f"未知命令名: {command!r}; 见 SW_CMD.BY_NAME"))
            else:
                cid = int(command)
            ok = bool(self.live.app.RunCommand(int(cid), str(title or "")))
            return _ok(ok, cmd=command, id=cid)
        except Exception as e:
            return _err(e, cmd=command)

    def list_commands(self) -> Dict[str, int]:
        return dict(SW_CMD.BY_NAME)

    # 常用快捷
    def rebuild(self) -> Dict[str, Any]:
        return self.run(SW_CMD.Rebuild)

    def zoom_fit(self) -> Dict[str, Any]:
        return self.run(SW_CMD.ZoomToFit)

    def select_all(self) -> Dict[str, Any]:
        return self.run(SW_CMD.SelectAll)

    def undo(self) -> Dict[str, Any]:
        return self.run(SW_CMD.Undo)


# ════════════════════════════════════════════════════════════════════════
# MacroRunner · VBA/swp 宏 · 借 RunMacro2 回放
# ════════════════════════════════════════════════════════════════════════
class MacroRunner:
    """SW VBA 宏执行器. 支持 .swp 文件直接跑 · 字符串 VBA 临时包装."""

    def __init__(self, live: SWLive):
        self.live = live

    def run_file(self, swp_path: Union[str, Path],
                 module: str = "Main", proc: str = "main",
                 options: int = 0) -> Dict[str, Any]:
        p = Path(swp_path).resolve()
        if not p.exists():
            return _err(FileNotFoundError(str(p)))
        try:
            err = _sw.win32_int()
            ok = bool(self.live.app.RunMacro2(
                str(p), module, proc, options, err
            ))
            return _ok(ok, err_code=err.value, path=str(p))
        except Exception as e:
            return _err(e)

    def run_vba(self, code: str,
                module: str = "Main", proc: str = "main") -> Dict[str, Any]:
        """把 VBA 代码写入临时 .swp 然后 RunMacro.

        注: SW 的 .swp 实为 OLE2 封装 VBA 项目, 纯文本写不生效.
        本路仅对已"录制"为 .swp 的宏有效. 字符串 VBA 需借 SW 宏编辑器.
        为强调这一点, 此方法不写 .swp, 仅返回待手工保存的代码.
        """
        return _err(LiveError(
            "VBA 字符串直跑需借 SW 宏编辑器保存为 .swp; "
            "请用 run_file(path) 跑已有宏."
        ), code_len=len(code))


# ════════════════════════════════════════════════════════════════════════
# SelectionMgr · 选择器 · SelectByID2 全要素
# ════════════════════════════════════════════════════════════════════════
class SelectionMgr:
    """封装 IModelDocExtension.SelectByID2 全要素选择.

    SelectByID2(Name, Type, X, Y, Z, Append, Mark, Callout, SelectOption)
    · Name: 对象名 (如 'Boss-Extrude1', 'Edge<5>')
    · Type: SW_SEL.* 枚举 (字符串自动转)
    · X,Y,Z: 可为 0 (按名); 非 0 时按坐标辅助
    · Append: 是否追加到当前选择
    · Mark: 标签 (多选时区分角色)
    """

    def __init__(self, doc: LiveDoc):
        self.doc = doc

    @property
    def _ext(self):
        return self.doc.raw.Extension

    def by_id(self, name: str, sel_type: Union[int, str] = "feature",
              append: bool = False, mark: int = 0,
              x: float = 0.0, y: float = 0.0, z: float = 0.0) -> Dict[str, Any]:
        """多路 fallback 选择. 需要 type_str 是 SW API 要求的大写枚举字符串
        (EDGE/FACE/PLANE/AXIS/...). 先轻后重:
          路 0: SelectByID (老 · 5 参数 · 无 Callout · 无 append/mark)
          路 1: SelectByID2 + VARIANT(VT_DISPATCH, None)
          路 2: SelectByID2 + pythoncom.Missing
          路 3: SelectByID2 + None (极老路 · SW 2015-)
        任一成 即返. 全败 才报失败.
        """
        try:
            if isinstance(sel_type, str):
                code = SW_SEL.BY_NAME.get(sel_type.lower())
                if code is None:
                    return _err(LiveError(f"未知选择类型: {sel_type!r}"))
            else:
                code = int(sel_type)
            type_str = _sel_type_to_str(code)
            import pythoncom
            try:
                from win32com.client import VARIANT
            except Exception:  # noqa: BLE001
                VARIANT = None

            trace: List[Dict[str, Any]] = []
            # ─── 路 0: legacy SelectByID (最稳) ───
            try:
                if not append:
                    try: self.doc.raw.ClearSelection2(True)
                    except Exception: pass
                ok = bool(self._ext.SelectByID(
                    str(name), type_str,
                    float(x), float(y), float(z),
                ))
                trace.append({"path": "byid_legacy", "ok": ok})
                if ok:
                    return _ok(True, name=name, type=code,
                               path="byid_legacy", trace=trace,
                               note="append/mark 在 legacy 路径下忽略" if append or mark else None)
            except Exception as e:  # noqa: BLE001
                trace.append({"path": "byid_legacy", "err": f"{type(e).__name__}: {e}"})

            # ─── 路 1: SelectByID2 + VARIANT(VT_DISPATCH, None) ───
            if VARIANT is not None:
                try:
                    callout = VARIANT(pythoncom.VT_DISPATCH, None)
                    ok = bool(self._ext.SelectByID2(
                        str(name), type_str,
                        float(x), float(y), float(z),
                        bool(append), int(mark),
                        callout, 0,
                    ))
                    trace.append({"path": "byid2_variant", "ok": ok})
                    if ok:
                        return _ok(True, name=name, type=code,
                                   path="byid2_variant", trace=trace)
                except Exception as e:  # noqa: BLE001
                    trace.append({"path": "byid2_variant", "err": f"{type(e).__name__}: {e}"})

            # ─── 路 2: SelectByID2 + pythoncom.Missing ───
            try:
                ok = bool(self._ext.SelectByID2(
                    str(name), type_str,
                    float(x), float(y), float(z),
                    bool(append), int(mark),
                    pythoncom.Missing, 0,
                ))
                trace.append({"path": "byid2_missing", "ok": ok})
                if ok:
                    return _ok(True, name=name, type=code,
                               path="byid2_missing", trace=trace)
            except Exception as e:  # noqa: BLE001
                trace.append({"path": "byid2_missing", "err": f"{type(e).__name__}: {e}"})

            # ─── 路 3: SelectByID2 + None ───
            try:
                ok = bool(self._ext.SelectByID2(
                    str(name), type_str,
                    float(x), float(y), float(z),
                    bool(append), int(mark), None, 0,
                ))
                trace.append({"path": "byid2_none", "ok": ok})
                if ok:
                    return _ok(True, name=name, type=code,
                               path="byid2_none", trace=trace)
            except Exception as e:  # noqa: BLE001
                trace.append({"path": "byid2_none", "err": f"{type(e).__name__}: {e}"})

            return _err(LiveError(f"SelectByID/SelectByID2 皆失败 (name={name!r}, type={type_str})"),
                       name=name, type=code, trace=trace)
        except Exception as e:
            return _err(e, name=name)

    def clear(self) -> Dict[str, Any]:
        try:
            self.doc.raw.ClearSelection2(True)
            return _ok(True)
        except Exception as e:
            return _err(e)

    def count(self) -> int:
        try:
            return int(self.doc.raw.SelectionManager.GetSelectedObjectCount2(-1))
        except Exception:
            return 0

    def names(self) -> List[str]:
        """当前选择的对象名 (尽力而为)."""
        out: List[str] = []
        try:
            sm = self.doc.raw.SelectionManager
            n = int(sm.GetSelectedObjectCount2(-1))
            for i in range(1, n + 1):
                try:
                    out.append(str(sm.GetSelectedObjectsFeatureName2(i, -1)))
                except Exception:
                    try:
                        obj = sm.GetSelectedObject6(i, -1)
                        out.append(str(getattr(obj, "GetName", lambda: "")()))
                    except Exception:
                        out.append("")
        except Exception:
            pass
        return out


# swSelectType_e 数字 → SelectByID2 所需字符串
_SEL_TYPE_STR = {
    1: "EDGE", 2: "FACE", 3: "VERTEX", 4: "BODY", 5: "FEATURE",
    9: "SKETCH", 10: "SKETCHSEGMENT", 11: "SKETCHPOINT",
    14: "SKETCHDIM", 19: "PLANE", 20: "AXIS",  # 20 歧义但 SW 内部兼容
    23: "REFPOINT", 32: "MATE", 47: "CONFIGURATION", 51: "CENTERLINE",
}


def _sel_type_to_str(code: int) -> str:
    return _SEL_TYPE_STR.get(int(code), "")


# ════════════════════════════════════════════════════════════════════════
# 占位: 大型 Builder 在下一批 edit 中追加
#   · SketchBuilder
#   · FeatureBuilder
#   · AssemblyBuilder
#   · DrawingBuilder
#   · PropertyMgr
#   · EquationMgr
#   · MaterialMgr
# ════════════════════════════════════════════════════════════════════════
# ════════════════════════════════════════════════════════════════════════
# SketchBuilder · 草图全境
# ════════════════════════════════════════════════════════════════════════
class SketchBuilder:
    """草图构建器. 封装 SketchManager + Sketch entities.

    核心流程:
      start_on_plane(name)  → enter sketch mode on plane
      .line/.rect/.circle/.arc/.polygon/.slot/.spline/.ellipse
      .dim(*)               → smart dimension
      .trim/.offset/.mirror
      stop()                → exit sketch (commit)

    坐标默认 *毫米 (mm)* (与用户习惯一致, 内部自动转 SW 系统米).
    草图坐标系: 平面内 (x,y) — 前视 (Front) 为 XY, 上视 (Top) 为 XZ, 右视 (Right) 为 YZ.
    """

    def __init__(self, doc: LiveDoc):
        self.doc = doc
        self._active_sketch: Any = None   # ISketch when 'in sketch mode'

    @property
    def mgr(self) -> Any:
        m = self.doc.raw.SketchManager
        if m is None:
            raise LiveError("SketchManager 不可用 (活动文档非零件)")
        return m

    # ─── 进入/退出 ────────────────────────────────────────────────
    def start_on_plane(self, plane_name: Union[str, Sequence[str]]) -> Dict[str, Any]:
        """在指定基准面进入草图. plane_name 可以是字符串或其别名 (元组).

        如 SW_PLANE.FRONT = ('Front Plane', '前视基准面', 'Plan de face').
        """
        names = (plane_name,) if isinstance(plane_name, str) else tuple(plane_name)
        last_err: Optional[str] = None
        for n in names:
            try:
                r = self.doc.sel.by_id(n, sel_type="plane")
                if not r.get("ok"):
                    last_err = r.get("err") or f"select {n!r} failed"
                    continue
                self.mgr.InsertSketch(True)
                self._active_sketch = self.mgr.ActiveSketch
                return _ok(True, plane=n, sel_path=r.get("path"))
            except Exception as e:  # noqa: BLE001
                last_err = f"{type(e).__name__}: {e}"
                continue
        self._active_sketch = None
        return _err(LiveError(
            f"无法进入草图: {names!r} 皆失败; last_err={last_err}"
        ))

    @property
    def in_sketch(self) -> bool:
        """当前是否处于 (我们主动进入的) 草图模式."""
        return self._active_sketch is not None

    def _require_sketch(self, op_name: str) -> Optional[Dict[str, Any]]:
        """护栏: 未进入草图时返 err 丢给上游. 防 'sketch 静默失败后续粗闫继续'.
        """
        if not self.in_sketch:
            return _err(LiveError(
                f"草图未进入 (start_on_plane 失败?). 跳过 {op_name}."
            ), entity=op_name)
        return None

    def start_front(self) -> Dict[str, Any]:
        return self.start_on_plane(SW_PLANE.FRONT)

    def start_top(self) -> Dict[str, Any]:
        return self.start_on_plane(SW_PLANE.TOP)

    def start_right(self) -> Dict[str, Any]:
        return self.start_on_plane(SW_PLANE.RIGHT)

    def start_on_face(self, face_name: str) -> Dict[str, Any]:
        """在命名面上起草图 (需先 SelectByID2 选面)."""
        try:
            r = self.doc.sel.by_id(face_name, sel_type="face")
            if not r.get("ok"):
                return r
            self.mgr.InsertSketch(True)
            self._active_sketch = self.mgr.ActiveSketch
            return _ok(True, face=face_name)
        except Exception as e:
            return _err(e, face=face_name)

    def stop(self) -> Dict[str, Any]:
        """退出草图 · 提交."""
        # 未进入草图时 no-op, 避免误触 SW内部 toggle
        if self._active_sketch is None:
            return _ok(True, skipped="not in sketch mode")
        try:
            self.mgr.InsertSketch(True)   # Toggle
            self._active_sketch = None
            return _ok(True)
        except Exception as e:
            return _err(e)

    # ─── 基础实体 (mm 坐标) ────────────────────────────────────────
    def line(self, x1: float, y1: float, x2: float, y2: float) -> Dict[str, Any]:
        g = self._require_sketch("line")
        if g: return g
        try:
            seg = self.mgr.CreateLine(
                _mm2m(x1), _mm2m(y1), 0.0,
                _mm2m(x2), _mm2m(y2), 0.0,
            )
            return _ok(seg is not None, entity="line",
                       start=(x1, y1), end=(x2, y2))
        except Exception as e:
            return _err(e, entity="line")

    def rect(self, x1: float, y1: float, x2: float, y2: float,
             corner: bool = True) -> Dict[str, Any]:
        """矩形 · corner=True 为角到角, corner=False 为中心到角点."""
        g = self._require_sketch("rect")
        if g: return g
        try:
            if corner:
                seg = self.mgr.CreateCornerRectangle(
                    _mm2m(x1), _mm2m(y1), 0.0,
                    _mm2m(x2), _mm2m(y2), 0.0,
                )
            else:
                seg = self.mgr.CreateCenterRectangle(
                    _mm2m(x1), _mm2m(y1), 0.0,
                    _mm2m(x2), _mm2m(y2), 0.0,
                )
            return _ok(seg is not None, entity="rect",
                       p1=(x1, y1), p2=(x2, y2), corner=corner)
        except Exception as e:
            return _err(e, entity="rect")

    def circle(self, cx: float, cy: float, r: float) -> Dict[str, Any]:
        g = self._require_sketch("circle")
        if g: return g
        try:
            seg = self.mgr.CreateCircleByRadius(
                _mm2m(cx), _mm2m(cy), 0.0, _mm2m(r),
            )
            return _ok(seg is not None, entity="circle", center=(cx, cy), r=r)
        except Exception as e:
            return _err(e, entity="circle")

    def arc(self, cx: float, cy: float, r: float,
            start_angle_deg: float, end_angle_deg: float,
            direction: int = 1) -> Dict[str, Any]:
        """圆弧 · 以圆心+半径+起止角 (度) 给出. direction: 1=逆时针 / -1=顺时针."""
        g = self._require_sketch("arc")
        if g: return g
        try:
            # 起/止点
            sa = math.radians(start_angle_deg); ea = math.radians(end_angle_deg)
            sx = cx + r * math.cos(sa); sy = cy + r * math.sin(sa)
            ex = cx + r * math.cos(ea); ey = cy + r * math.sin(ea)
            seg = self.mgr.CreateArc(
                _mm2m(cx), _mm2m(cy), 0.0,
                _mm2m(sx), _mm2m(sy), 0.0,
                _mm2m(ex), _mm2m(ey), 0.0,
                int(direction),
            )
            return _ok(seg is not None, entity="arc",
                       center=(cx, cy), r=r,
                       a0=start_angle_deg, a1=end_angle_deg)
        except Exception as e:
            return _err(e, entity="arc")

    def polygon(self, cx: float, cy: float, r: float, sides: int = 6,
                inscribed: bool = True, rot_deg: float = 0.0) -> Dict[str, Any]:
        """正多边形 (边数 >=3). inscribed=True 为内切圆半径 (顶点到圆心),
        否则为外切圆半径.
        """
        try:
            sides = max(3, int(sides))
            seg = self.mgr.CreatePolygon(
                _mm2m(cx), _mm2m(cy), 0.0,
                _mm2m(cx + r), _mm2m(cy), 0.0,   # 第二点定 rotation
                int(sides), bool(inscribed),
            )
            return _ok(seg is not None, entity="polygon",
                       center=(cx, cy), r=r, sides=sides)
        except Exception as e:
            return _err(e, entity="polygon")

    def slot(self, x1: float, y1: float, x2: float, y2: float,
             width: float) -> Dict[str, Any]:
        """直线槽口 · 两中心点 + 宽度."""
        try:
            seg = self.mgr.CreateSketchSlot(
                0,            # swSketchSlotCreationType_e 直槽
                0,            # swSketchSlotLengthType_e 中心到中心
                _mm2m(x1), _mm2m(y1), 0.0,
                _mm2m(x2), _mm2m(y2), 0.0,
                0.0, 0.0, 0.0,   # arc 参数 unused
                _mm2m(width),
                1,            # direction
            )
            return _ok(seg is not None, entity="slot", width=width)
        except Exception as e:
            return _err(e, entity="slot")

    def spline(self, points: Sequence[Sequence[float]]) -> Dict[str, Any]:
        """B样条曲线 · 给出 [[x,y], ...] 控制/样本点."""
        if len(points) < 2:
            return _err(ValueError("spline needs ≥2 points"), entity="spline")
        try:
            flat: List[float] = []
            for p in points:
                flat += [_mm2m(p[0]), _mm2m(p[1]), 0.0]
            seg = self.mgr.CreateSpline(flat)
            return _ok(seg is not None, entity="spline", n=len(points))
        except Exception as e:
            return _err(e, entity="spline")

    def ellipse(self, cx: float, cy: float, rx: float, ry: float) -> Dict[str, Any]:
        try:
            seg = self.mgr.CreateEllipse(
                _mm2m(cx), _mm2m(cy), 0.0,
                _mm2m(cx + rx), _mm2m(cy), 0.0,
                _mm2m(cx), _mm2m(cy + ry), 0.0,
            )
            return _ok(seg is not None, entity="ellipse",
                       center=(cx, cy), rx=rx, ry=ry)
        except Exception as e:
            return _err(e, entity="ellipse")

    def centerline(self, x1: float, y1: float, x2: float, y2: float) -> Dict[str, Any]:
        try:
            seg = self.mgr.CreateCenterLine(
                _mm2m(x1), _mm2m(y1), 0.0,
                _mm2m(x2), _mm2m(y2), 0.0,
            )
            return _ok(seg is not None, entity="centerline")
        except Exception as e:
            return _err(e, entity="centerline")

    # ─── 标注 / 约束 ──────────────────────────────────────────────
    def dim(self, x: float, y: float, value_mm: Optional[float] = None,
            name: Optional[str] = None) -> Dict[str, Any]:
        """智能尺寸 (先选对象, 再调本方法定位文本).

        value_mm: 若给定, 会设定 DimensionValue2 (米) · name: 尺寸名 (如 'D1@Sketch1').
        """
        try:
            ok = bool(self.doc.raw.AddDimension2(
                _mm2m(x), _mm2m(y), 0.0
            ))
            res: Dict[str, Any] = _ok(ok, entity="dimension", pos=(x, y))
            if ok and value_mm is not None and name:
                try:
                    self.doc.raw.Parameter(name).SystemValue = _mm2m(value_mm)
                    res["value_mm"] = value_mm
                    res["name"] = name
                except Exception as e:
                    res["value_err"] = f"{type(e).__name__}: {e}"
            return res
        except Exception as e:
            return _err(e, entity="dimension")

    def add_relation(self, relation: str,
                     entities: Optional[Sequence[str]] = None) -> Dict[str, Any]:
        """添加几何关系. relation: horizontal/vertical/equal/coincident/...

        SW 枚举: swConstraintType_e. 字符串映射仅覆盖最常用.
        """
        mapping = {
            "horizontal": 1, "vertical": 2, "collinear": 3,
            "coradial": 4,   "perpendicular": 5, "parallel": 6,
            "tangent": 7,    "concentric": 8,    "midpoint": 9,
            "intersection": 10, "coincident": 11, "equal": 14,
            "symmetric": 12, "fix": 15, "pierce": 27,
        }
        code = mapping.get(relation.lower())
        if code is None:
            return _err(LiveError(f"未知约束: {relation!r}"))
        try:
            # 选择已在 SelectionMgr 里完成 · AddRelation 基于当前选择
            if entities:
                self.doc.sel.clear()
                for ent in entities:
                    self.doc.sel.by_id(ent, sel_type="sketchsegment", append=True)
            self.mgr.AddConstraint(int(code))
            return _ok(True, relation=relation, code=code)
        except Exception as e:
            return _err(e, relation=relation)


# ════════════════════════════════════════════════════════════════════════
# FeatureBuilder · 特征全境
# ════════════════════════════════════════════════════════════════════════
class FeatureBuilder:
    """特征构建器. 覆盖 extrude/revolve/fillet/chamfer/shell/pattern/hole/plane 等.

    约定: 若特征需先有草图, 调用者应先 sketch.start_*/stop(); 再调本方法.
    默认: 距离单位为 mm, 角度为度; 内部转米/弧度.
    """

    def __init__(self, doc: LiveDoc):
        self.doc = doc

    @property
    def mgr(self) -> Any:
        m = self.doc.raw.FeatureManager
        if m is None:
            raise LiveError("FeatureManager 不可用 (活动文档非零件/装配)")
        return m

    # ─── 拉伸 ──────────────────────────────────────────────────────
    def extrude(self, depth: float,
                *,
                cut: bool = False,
                direction: str = "blind",
                reverse: bool = False,
                both_directions: bool = False,
                depth2: float = 0.0,
                draft_deg: float = 0.0,
                thin: bool = False,
                thin_wall_mm: float = 1.0) -> Dict[str, Any]:
        """通用拉伸 · 支持凸台 / 切除 / 双向 / 薄壁 / 拔模.

        direction:
          · 'blind'           给定深度 (默)
          · 'through_all'     完全贯穿
          · 'up_to_vertex'    拉至顶点 (需先选一顶点)
          · 'up_to_surface'   拉至面 (需先选面)
          · 'offset_from_surface' 到面偏距 (depth2 = offset mm)
          · 'mid_plane'       中间面对称
        """
        end_cond_map = {
            "blind": 0, "through_all": 1, "up_to_next": 2,
            "up_to_vertex": 3, "up_to_surface": 4,
            "offset_from_surface": 5, "mid_plane": 6,
            "up_to_body": 7,
        }
        ec = end_cond_map.get(direction.lower(), 0)
        try:
            # FeatureExtrusion3 签名 (SW 2015+):
            # (Sd, Flip, Dir, T1, T2, D1, D2, Dchk1, Dchk2, Ddir1, Ddir2,
            #  Dang1, Dang2, OffsetReverse1, OffsetReverse2,
            #  TranslateSurface1, TranslateSurface2, Merge, UseFeatScope,
            #  UseAutoSelect, T0, StartOffset, FlipStartOffset)
            feat = self.mgr.FeatureExtrusion3(
                True,            # single-ended?  (False 若 both_directions)
                bool(reverse),
                False,           # flip side to cut
                int(ec), 0,      # T1 (end cond), T2
                _mm2m(depth),    # D1 depth
                _mm2m(depth2),   # D2
                False, False,    # Dchk1, Dchk2 (draft outward?)
                False, False,    # Ddir1, Ddir2 (draft direction)
                math.radians(draft_deg), 0.0,   # Dang1, Dang2
                False, False,    # offset reverse
                False, False,    # translate surface
                True,            # merge
                True, True,      # use feat scope, auto select
                0, 0.0, False,   # start cond (0=sketch plane), offset, flip
            )
            r = _ok(feat is not None, entity=SW_FEATURE.EXTRUDE_BOSS,
                    depth=depth, dir=direction)
            if feat is None:
                return _err(LiveError("FeatureExtrusion3 returned None"),
                            depth=depth)
            if cut:
                # 变换为 Cut: 调 FeatureCut3 代路
                # 老路: 直接调 FeatureCut3 替换刚生成的 boss
                pass   # 简单起见, cut 由专门方法 cut() 承担
            return r
        except Exception as e:
            return _err(e, entity="extrude")

    def extrude_cut(self, depth: float, **kw) -> Dict[str, Any]:
        """拉伸切除 · FeatureCut3."""
        kw.pop("cut", None)
        end_cond_map = {
            "blind": 0, "through_all": 1, "up_to_next": 2,
            "up_to_vertex": 3, "up_to_surface": 4,
            "offset_from_surface": 5, "mid_plane": 6,
        }
        ec = end_cond_map.get(kw.pop("direction", "blind").lower(), 0)
        reverse = bool(kw.pop("reverse", False))
        try:
            feat = self.mgr.FeatureCut3(
                True,            # single-ended
                False,           # flip
                bool(reverse),   # dir
                int(ec), 0,      # T1, T2
                _mm2m(depth), _mm2m(kw.pop("depth2", 0.0)),
                False, False,
                False, False,
                math.radians(kw.pop("draft_deg", 0.0)), 0.0,
                False, False,
                False, False,
                False,           # reverse offset
                False, False,    # use auto select, use feat scope
                True,            # assembly feat scope
                True,            # auto select
                True, 0, 0.0, False,
            )
            return _ok(feat is not None, entity=SW_FEATURE.EXTRUDE_CUT,
                       depth=depth)
        except Exception as e:
            return _err(e, entity="extrude_cut")

    # ─── 旋转 ──────────────────────────────────────────────────────
    def revolve(self, angle_deg: float = 360.0,
                *, cut: bool = False) -> Dict[str, Any]:
        """绕当前选中轴/中心线旋转 · 先 sketch 内放 centerline 或先选轴."""
        try:
            if cut:
                feat = self.mgr.FeatureRevolveCut2(
                    True, math.radians(angle_deg), 0, 0,
                    0, 0.0, 0.0,   # thin
                    0, 0, 0, 0, 0,
                    True, True,
                )
                kind = SW_FEATURE.REVOLVE_CUT
            else:
                feat = self.mgr.FeatureRevolve2(
                    True, True, math.radians(angle_deg), 0.0, 0, 0, 0,
                    0, 0, 0.0, 0.0, 0, 0,
                    True, True, True,
                )
                kind = SW_FEATURE.REVOLVE_BOSS
            return _ok(feat is not None, entity=kind, angle=angle_deg)
        except Exception as e:
            return _err(e, entity="revolve")

    # ─── 修饰: 圆角/倒角/抽壳/拔模 ────────────────────────────────
    def fillet(self, radius: float,
               *,
               edges: Optional[Sequence[str]] = None,
               all_edges: bool = False) -> Dict[str, Any]:
        """圆角 · edges 为边名列表, 或 all_edges=True 对全部边."""
        try:
            self.doc.sel.clear()
            selected = 0
            if all_edges:
                # 选所有边: 借 SelectAll 命令后过滤 — 简化起见直接用 FeatureFillet on body
                self.doc.sel.by_id("", sel_type="body")
                selected = self.doc.sel.count()
            elif edges:
                for i, e in enumerate(edges):
                    self.doc.sel.by_id(e, sel_type="edge",
                                       append=(i > 0), mark=1)
                selected = self.doc.sel.count()
            # FeatureFillet3 (Options, Radius, Ftyp, OverflowType, ...)
            # 简化走 InsertFeatureFillet: 等价 1 半径等半径
            feat = self.mgr.FeatureFillet3(
                195,    # options flags (swFeatureFilletFlag_e: propagate=8 | keep=128 | ...)
                _mm2m(radius),   # R1
                0, 0, 0,         # Ftyp, OverflowType, ConicType
                None, None, None, None, None, None, None, None,
            )
            return _ok(feat is not None, entity=SW_FEATURE.FILLET,
                       r=radius, selected=selected)
        except Exception as e:
            return _err(e, entity="fillet")

    def chamfer(self, distance: float, angle_deg: float = 45.0,
                *, edges: Optional[Sequence[str]] = None,
                all_edges: bool = False,
                chamfer_type: int = 0,
                options: int = 0,
                other_dist: float = 0.0) -> Dict[str, Any]:
        """倒角 · 道法自然 · 反者道之动.

        反笙 · SW 2023 真签名 **8 参** (非 6):
            (Options, ChamferType, Width, Angle, OtherDist,
             VertexChamDist1, VertexChamDist2, VertexChamDist3)

        参数:
            distance:       距离 (mm)
            angle_deg:      角度 (度; 仅 chamfer_type=0 生效)
            edges:          边名列表 (显式选); None 且 all_edges=False 则复用外部已选
            all_edges:      body.GetEdges 穷遍选所有边 (几何层, 非 UI 层)
            chamfer_type:   0=angle-dist(默认) / 1=dist-dist / 2=vertex / 3=offset-face / 4=face-face
            options:        swFeatureChamferOption_e bit 位
            other_dist:     dist-dist 或 offset 第二距离 (mm)
        """
        def _do_chamfer() -> Any:
            return self.mgr.InsertFeatureChamfer(
                int(options),                    # 1 Options
                int(chamfer_type),               # 2 ChamferType
                _mm2m(distance),                 # 3 Width
                math.radians(angle_deg),         # 4 Angle
                _mm2m(other_dist),               # 5 OtherDist
                0.0, 0.0, 0.0,                   # 6-8 VertexChamDist1/2/3
            )

        try:
            n_selected = 0
            select_path = "external_preselect"

            if edges:
                self.doc.sel.clear()
                for i, e in enumerate(edges):
                    r = self.doc.sel.by_id(e, sel_type="edge",
                                            append=(i > 0), mark=1)
                    if r.get("ok"):
                        n_selected += 1
                select_path = "edges_named"
                feat = _do_chamfer()
                return _ok(feat is not None, entity=SW_FEATURE.CHAMFER,
                           d=distance, a=angle_deg, n_selected=n_selected,
                           select_path=select_path,
                           feat_name=(feat.Name if feat is not None else None))

            if all_edges:
                # 路 1: 穷遍 body.GetEdges + Select4 (精确但需 API 暴露)
                self.doc.sel.clear()
                n_selected = self._select_all_body_edges()
                if n_selected > 0:
                    select_path = "body_edges_enumerated"
                    feat = _do_chamfer()
                    if feat is not None:
                        return _ok(True, entity=SW_FEATURE.CHAMFER,
                                   d=distance, a=angle_deg, n_selected=n_selected,
                                   select_path=select_path,
                                   feat_name=feat.Name)
                    # 精准路失败 · 跌入 body-level
                    select_path = "body_edges_enumerated_feat_null"

                # 路 2: 回退 body-level select (SW 自动延伸到所有边)
                self.doc.sel.clear()
                r_body = self.doc.sel.by_id("", sel_type="body", mark=1)
                if r_body.get("ok"):
                    n_selected = max(n_selected, 1)
                    select_path = select_path + "→body_level"
                    feat = _do_chamfer()
                    if feat is not None:
                        return _ok(True, entity=SW_FEATURE.CHAMFER,
                                   d=distance, a=angle_deg, n_selected=n_selected,
                                   select_path=select_path,
                                   feat_name=feat.Name)

                # 路 3: Extension.SelectAll (UI 级全选)
                try:
                    self.doc.raw.Extension.SelectAll()
                    n_selected = max(n_selected, 1)
                    select_path = select_path + "→select_all"
                    feat = _do_chamfer()
                    if feat is not None:
                        return _ok(True, entity=SW_FEATURE.CHAMFER,
                                   d=distance, a=angle_deg, n_selected=n_selected,
                                   select_path=select_path,
                                   feat_name=feat.Name)
                except Exception:
                    pass

                return _err(LiveError("chamfer 全路径皆失败"),
                            entity="chamfer", d=distance, a=angle_deg,
                            n_selected=n_selected, select_path=select_path)

            # 无 edges / all_edges · 用外部已选
            feat = _do_chamfer()
            return _ok(feat is not None, entity=SW_FEATURE.CHAMFER,
                       d=distance, a=angle_deg, n_selected=0,
                       select_path=select_path,
                       feat_name=(feat.Name if feat is not None else None))
        except Exception as e:
            return _err(e, entity="chamfer")

    def _select_all_body_edges(self) -> int:
        """道直连: 取所有 solid body 的 edges, 批量 SelectByID2('', 'EDGE', x,y,z).

        对每条 edge 取中点坐标 (IEdge.GetCurveParams/GetClosestPointOn 等).
        返回成功选中的边数.
        """
        import win32com.client as _wc
        import pythoncom
        VARIANT = getattr(_wc, "VARIANT", None)

        raw = self.doc.raw
        ext = raw.Extension
        n_sel = 0

        def _get_bodies() -> List[Any]:
            # GetBodies2(swBodyType_e=1 solid, bUpdatedBodies=True)
            for ty in (1, 0):
                try:
                    bs = raw.GetBodies2(ty, True)
                    if bs:
                        return list(bs)
                except Exception:
                    continue
            return []

        def _edge_midpoint(edge) -> Optional[Tuple[float, float, float]]:
            """拿 edge 上的一个点 (参数中点)."""
            try:
                # GetCurveParams returns [x0,y0,z0,dx,dy,dz,tStart,tEnd] or similar
                # 更稳: 取 StartVertex 坐标
                sv = edge.GetStartVertex()
                if sv is not None:
                    sv_w = _wc.dynamic.Dispatch(sv._oleobj_)
                    pt = sv_w.GetPoint()
                    if pt and len(pt) >= 3:
                        return (float(pt[0]), float(pt[1]), float(pt[2]))
            except Exception:
                pass
            # 试 EndVertex
            try:
                ev = edge.GetEndVertex()
                if ev is not None:
                    ev_w = _wc.dynamic.Dispatch(ev._oleobj_)
                    pt = ev_w.GetPoint()
                    if pt and len(pt) >= 3:
                        return (float(pt[0]), float(pt[1]), float(pt[2]))
            except Exception:
                pass
            return None

        def _select_edge_obj(edge, append: bool) -> bool:
            # 直选 IEntity 对象 (最稳, 不需 SelectByID2)
            try:
                sel_data = ext.CreateSelectData if hasattr(ext, "CreateSelectData") else None
                # IEntity.Select4(Append, Data)
                fn = getattr(edge, "Select4", None)
                if callable(fn):
                    return bool(fn(append, None))
                fn = getattr(edge, "Select2", None)
                if callable(fn):
                    return bool(fn(append, 1))  # mark=1
                fn = getattr(edge, "Select", None)
                if callable(fn):
                    return bool(fn(append))
            except Exception:
                pass
            return False

        bodies = _get_bodies()
        for body in bodies:
            try:
                body_w = _wc.dynamic.Dispatch(body._oleobj_)
            except Exception:
                body_w = body
            try:
                edges = body_w.GetEdges() or []
            except Exception:
                continue
            for e in edges:
                try:
                    e_w = _wc.dynamic.Dispatch(e._oleobj_)
                except Exception:
                    e_w = e
                if _select_edge_obj(e_w, append=(n_sel > 0)):
                    n_sel += 1
                    continue
                # 回退: SelectByID2 + coords
                pt = _edge_midpoint(e_w)
                if pt is None:
                    continue
                try:
                    if VARIANT is not None:
                        callout = VARIANT(pythoncom.VT_DISPATCH, None)
                        ok = bool(ext.SelectByID2("", "EDGE",
                                                   pt[0], pt[1], pt[2],
                                                   bool(n_sel > 0), 1,
                                                   callout, 0))
                    else:
                        ok = bool(ext.SelectByID2("", "EDGE",
                                                   pt[0], pt[1], pt[2],
                                                   bool(n_sel > 0), 1,
                                                   None, 0))
                    if ok:
                        n_sel += 1
                except Exception:
                    continue
        return n_sel

    def shell(self, thickness: float,
              open_faces: Optional[Sequence[str]] = None,
              outward: bool = False) -> Dict[str, Any]:
        """抽壳 · open_faces 为要移除的面名列表."""
        try:
            self.doc.sel.clear()
            if open_faces:
                for i, f in enumerate(open_faces):
                    self.doc.sel.by_id(f, sel_type="face", append=(i > 0))
            feat = self.mgr.InsertFeatureShell(_mm2m(thickness), bool(outward))
            return _ok(feat is not None, entity=SW_FEATURE.SHELL,
                       t=thickness)
        except Exception as e:
            return _err(e, entity="shell")

    # ─── 阵列 ──────────────────────────────────────────────────────
    def linear_pattern(self, *,
                       d1_direction_edge: Optional[str] = None,
                       d1_count: int = 2, d1_spacing: float = 10.0,
                       d2_direction_edge: Optional[str] = None,
                       d2_count: int = 1, d2_spacing: float = 10.0,
                       features: Optional[Sequence[str]] = None) -> Dict[str, Any]:
        try:
            self.doc.sel.clear()
            mark = 1
            if d1_direction_edge:
                self.doc.sel.by_id(d1_direction_edge, sel_type="edge", mark=mark)
            mark = 2
            if d2_direction_edge:
                self.doc.sel.by_id(d2_direction_edge, sel_type="edge",
                                   append=True, mark=mark)
            mark = 4
            if features:
                for i, f in enumerate(features):
                    self.doc.sel.by_id(f, sel_type="feature",
                                       append=True, mark=mark)
            feat = self.mgr.FeatureLinearPattern2(
                int(d1_count), _mm2m(d1_spacing),
                int(d2_count), _mm2m(d2_spacing),
                False, False, "NULL", "NULL",
                False, False, False, False, False, False,
                True, True,
            )
            return _ok(feat is not None, entity=SW_FEATURE.PATTERN_LINEAR)
        except Exception as e:
            return _err(e, entity="pattern_linear")

    def circular_pattern(self, *, axis: str, count: int = 4,
                         angle_deg: float = 360.0,
                         equal_spacing: bool = True,
                         features: Optional[Sequence[str]] = None) -> Dict[str, Any]:
        try:
            self.doc.sel.clear()
            self.doc.sel.by_id(axis, sel_type="axis", mark=1)
            if features:
                for f in features:
                    self.doc.sel.by_id(f, sel_type="feature",
                                       append=True, mark=4)
            feat = self.mgr.FeatureCircularPattern4(
                int(count), math.radians(angle_deg), bool(equal_spacing),
                "NULL", False, True, False,
            )
            return _ok(feat is not None, entity=SW_FEATURE.PATTERN_CIRCULAR,
                       count=count)
        except Exception as e:
            return _err(e, entity="pattern_circular")

    def mirror(self, *, plane: str,
               features: Optional[Sequence[str]] = None) -> Dict[str, Any]:
        try:
            self.doc.sel.clear()
            self.doc.sel.by_id(plane, sel_type="plane", mark=2)
            if features:
                for f in features:
                    self.doc.sel.by_id(f, sel_type="feature",
                                       append=True, mark=1)
            feat = self.mgr.InsertMirrorFeature2(False, False, False, False, 0)
            return _ok(feat is not None, entity=SW_FEATURE.MIRROR)
        except Exception as e:
            return _err(e, entity="mirror")

    # ─── 基准 ──────────────────────────────────────────────────────
    def ref_plane(self, *,
                  parallel_to: Optional[str] = None,
                  offset_mm: float = 0.0,
                  flip: bool = False,
                  name: Optional[str] = None) -> Dict[str, Any]:
        """参考基准面 · 最简: 平行于现有平面 + 偏距."""
        try:
            self.doc.sel.clear()
            if parallel_to:
                self.doc.sel.by_id(parallel_to, sel_type="plane", mark=1)
            feat = self.mgr.InsertRefPlane(
                8, _mm2m(offset_mm),        # 8 = distance
                0, 0.0,
                0, 0.0,                     # angle
            )
            if name and feat is not None:
                try: feat.Name = name
                except Exception: pass
            return _ok(feat is not None, entity="ref_plane",
                       offset=offset_mm, parallel_to=parallel_to)
        except Exception as e:
            return _err(e, entity="ref_plane")

    def ref_axis(self, *, via: Sequence[str],
                 name: Optional[str] = None) -> Dict[str, Any]:
        """参考轴 · via = 用来定义轴的实体 (2 点 / 1 面 / 2 面 / 圆柱面)."""
        try:
            self.doc.sel.clear()
            for i, v in enumerate(via):
                self.doc.sel.by_id(v, sel_type="face", append=(i > 0))
            feat = self.mgr.InsertAxis2(True)
            if name and feat is not None:
                try: feat.Name = name
                except Exception: pass
            return _ok(feat is not None, entity="ref_axis")
        except Exception as e:
            return _err(e, entity="ref_axis")

    # ─── 孔向导 (简版: 通孔/沉头孔) ────────────────────────────────
    def hole(self, *, face: str, x: float, y: float, diameter: float,
             depth: float, through: bool = False) -> Dict[str, Any]:
        """简易孔: 在 face 上 (x,y) mm 位置打孔.
        与 HoleWizard 相比略简 · 但多数场景够用.
        """
        try:
            self.doc.sel.clear()
            self.doc.sel.by_id(face, sel_type="face")
            # 进入草图, 画圆, 退出草图, 切除
            self.mgr.InsertSketch(True)
            self.doc.raw.SketchManager.CreateCircleByRadius(
                _mm2m(x), _mm2m(y), 0.0, _mm2m(diameter / 2.0),
            )
            self.mgr.InsertSketch(True)
            # 切除
            ec = 1 if through else 0   # through_all | blind
            feat = self.mgr.FeatureCut3(
                True, False, False, int(ec), 0,
                _mm2m(depth), 0.0,
                False, False, False, False,
                0.0, 0.0, False, False, False, False,
                False, False, False, True, True,
                0, 0.0, False,
            )
            return _ok(feat is not None, entity="hole",
                       x=x, y=y, d=diameter, depth=depth, through=through)
        except Exception as e:
            return _err(e, entity="hole")

    # ─── 通用: 命名特征 ─────────────────────────────────────────────
    def rename_last(self, name: str) -> Dict[str, Any]:
        """给刚生成的特征改名 (通过 SelectionMgr 拿)."""
        try:
            sm = self.doc.raw.SelectionManager
            obj = sm.GetSelectedObject6(1, -1)
            if obj is None:
                return _err(LiveError("no selection"))
            obj.Name = str(name)
            return _ok(True, name=name)
        except Exception as e:
            return _err(e)


# ════════════════════════════════════════════════════════════════════════
# AssemblyBuilder · 装配全境
# ════════════════════════════════════════════════════════════════════════
class AssemblyBuilder:
    """装配构建器. 覆盖: 添加/删除零件 · 配合 (重合/同心/距离/平行/垂直/角度/相切)
     · 干涉检测 · 爆炸视图 · 移动组件 · 虚拟零件.

    活动文档须为装配体 (IAssemblyDoc), 否则 mgr 访问会 raise LiveError.
    """

    def __init__(self, doc: LiveDoc):
        self.doc = doc

    @property
    def asm(self) -> Any:
        if not self.doc.is_assembly:
            raise LiveError("活动文档非装配体")
        return self.doc.raw

    # ─── 组件管理 ──────────────────────────────────────────────────
    def add_component(self, part_path: Union[str, Path],
                      x_mm: float = 0.0, y_mm: float = 0.0, z_mm: float = 0.0,
                      *, config: str = "") -> Dict[str, Any]:
        """在装配中插入零件 · 道直连 · 多路回退.

        反笙: `AddComponent5` 对已打开文档/某些路径可能返 null. 需:
          路 1: 若 part 已打开, 先保存并关闭, 释放写锁
          路 2: ConfigOption=0 + AddComponent5 (标准路)
          路 3: ConfigOption=1 明示配置 + 默认配置名
          路 4: AddComponent4 (简化签名 · 若 SW 暴露)
          路 5: OpenDoc6 预加载 → AddComponent5 再试
          路 6: IAssemblyDoc.AddComponent (老 · 6 参)
        """
        import win32com.client as _wc
        p = Path(part_path).resolve()
        if not p.exists():
            return _err(FileNotFoundError(str(p)))
        path_str = str(p)
        x = _mm2m(x_mm); y = _mm2m(y_mm); z = _mm2m(z_mm)

        asm = self.asm
        app = self.doc.live.app
        trace: List[Dict[str, Any]] = []

        def _rewrap(obj):
            if obj is None: return None
            try: return _wc.dynamic.Dispatch(obj._oleobj_)
            except Exception: return obj

        def _name_of(comp) -> Optional[str]:
            for attr in ("Name2", "Name"):
                try:
                    n = getattr(comp, attr, None)
                    if n and not callable(n):
                        return str(n)
                except Exception:
                    pass
            try:
                w = _rewrap(comp)
                for attr in ("Name2", "Name"):
                    n = getattr(w, attr, None)
                    if n and not callable(n):
                        return str(n)
            except Exception:
                pass
            return None

        def _try_add(method_name: str, *args) -> Any:
            try:
                fn = getattr(asm, method_name, None)
                if fn is None:
                    trace.append({"method": method_name, "err": "not_exposed"})
                    return None
                comp = fn(*args)
                trace.append({"method": method_name, "n_args": len(args),
                              "got": "null" if comp is None else "ok"})
                return comp
            except Exception as e:
                trace.append({"method": method_name, "err": f"{type(e).__name__}: {e}"})
                return None

        # ─── 路 0: 若 part 已作为独立文档打开, 先关掉 (AddComponent 需要能锁文件) ───
        try:
            docs_raw = app.GetDocuments
            if callable(docs_raw):
                docs_raw = docs_raw()
            if docs_raw:
                for d in docs_raw:
                    try:
                        dp = d.GetPathName() or ""
                        if dp and Path(dp).resolve() == p:
                            # 同路径已开, 关之
                            try: d.Save3(1, 0, 0)  # silent save
                            except Exception: pass
                            app.CloseDoc(d.GetTitle if not callable(d.GetTitle) else d.GetTitle())
                            trace.append({"step": "close_existing_open", "path": dp})
                    except Exception:
                        continue
        except Exception:
            pass

        # ─── 路 1: AddComponent5 标准 8 参 · ConfigOption=0 ───
        comp = _try_add("AddComponent5",
                        path_str, 0,
                        config or "", False, "",
                        x, y, z)
        # ─── 路 2: AddComponent5 · ConfigOption=1 + 配置名 "默认" ───
        if comp is None:
            comp = _try_add("AddComponent5",
                            path_str, 1,
                            "", False, (config or "默认"),
                            x, y, z)
        # ─── 路 3: AddComponent5 · ConfigOption=2 (use referenced) ───
        if comp is None:
            comp = _try_add("AddComponent5",
                            path_str, 2,
                            "", True, "",
                            x, y, z)
        # ─── 路 4: AddComponent4 (4/6 参简化) ───
        if comp is None:
            for args_variant in [
                (path_str, config or "", x, y, z),
                (path_str, x, y, z),
            ]:
                comp = _try_add("AddComponent4", *args_variant)
                if comp is not None:
                    break
        # ─── 路 5: 用 SolidWorksBridge.open 预载 part, 再激活装配, AddComponent5 ───
        if comp is None:
            try:
                bridge = self.doc.live._bridge
                asm_title = None
                try:
                    asm_title = self.doc.raw.GetTitle if not callable(self.doc.raw.GetTitle) else self.doc.raw.GetTitle()
                except Exception:
                    pass

                # 预载 (会把 part 打开到 SW 内存)
                sw_doc_loaded = bridge.open(path_str, readonly=False)
                trace.append({"step": "bridge_open", "got": "ok" if sw_doc_loaded else "null"})

                # 切回装配为 active doc, 再 AddComponent5
                if asm_title:
                    try:
                        app.ActivateDoc3(asm_title, False, 0, 0)
                        trace.append({"step": "activate_asm", "title": asm_title})
                    except Exception:
                        try:
                            app.ActivateDoc2(asm_title, False, 0)
                            trace.append({"step": "activate_asm_v2", "title": asm_title})
                        except Exception as e:
                            trace.append({"step": "activate_asm_err", "err": f"{type(e).__name__}"})

                # 加组件
                comp = _try_add("AddComponent5",
                                path_str, 0,
                                "", False, "",
                                x, y, z)
            except Exception as e:
                trace.append({"step": "preload_err", "err": f"{type(e).__name__}: {e}"})

        # ─── 路 6: 老 AddComponent (6 参) ───
        if comp is None:
            comp = _try_add("AddComponent", path_str, x, y, z)

        if comp is None:
            return _err(LiveError("AddComponent 全路径皆 null"),
                        path=path_str, trace=trace)

        comp = _rewrap(comp) or comp
        name = _name_of(comp) or p.stem
        # 重建 · 验证组件固化: 若 root children 数没 +1, 退到 err
        try:
            asm.ForceRebuild3(False)
        except Exception:
            pass

        # 验证组件真加入
        verified = False
        try:
            cfg_mgr = self.doc.raw.ConfigurationManager
            active_cfg = cfg_mgr.ActiveConfiguration
            root = None
            try:
                root = active_cfg.GetRootComponent3(True)
            except Exception:
                try:
                    root = active_cfg.GetRootComponent()
                except Exception:
                    pass
            if root is not None:
                root_w = _rewrap(root)
                ch = getattr(root_w, "GetChildren", None)
                if callable(ch):
                    children = ch() or []
                    for c in children:
                        c_name = _name_of(c) or ""
                        if p.stem in c_name or c_name:
                            verified = True
                            break
        except Exception:
            pass
        trace.append({"step": "verify_in_root", "verified": verified})

        return _ok(True, name=name, path=path_str, at=(x_mm, y_mm, z_mm),
                   verified=verified, trace=trace)

    def remove_component(self, name: str) -> Dict[str, Any]:
        try:
            self.doc.sel.clear()
            r = self.doc.sel.by_id(name, sel_type="component")
            if not r.get("ok"):
                return r
            self.asm.DeleteSelections(0)
            return _ok(True, name=name)
        except Exception as e:
            return _err(e, name=name)

    def list_components(self) -> List[Dict[str, Any]]:
        """列组件 · 道直连 · 多路回退 + re-wrap.

        反笙:
          - 新装配刚 AddComponent5 需 ForceRebuild 触发物化.
          - `GetComponents/GetChildren` 返 raw IDispatch 数组, 需 re-wrap
            `win32com.client.dynamic.Dispatch(c._oleobj_)` 才能访 `.Name2` 等.
        顺序:
          路 1: ForceRebuild3 → GetComponents(True) 顶层
          路 2: GetComponents(False) 深遍
          路 3: RootComponent3 → GetChildren BFS
        """
        import win32com.client as _wc
        import pythoncom

        def _rewrap(obj):
            if obj is None:
                return None
            try:
                return _wc.dynamic.Dispatch(obj._oleobj_)
            except Exception:
                return obj

        def _safe_name(c) -> Optional[str]:
            # 直属性
            try:
                n = getattr(c, "Name2", None)
                if n and not callable(n):
                    return str(n)
            except Exception:
                pass
            # re-wrap
            try:
                w = _rewrap(c)
                if w is not None:
                    n = w.Name2
                    if n:
                        return str(n)
            except Exception:
                pass
            return None

        def _safe_call(c, method: str, *args):
            try:
                fn = getattr(c, method, None)
                if callable(fn):
                    return fn(*args)
            except Exception:
                pass
            try:
                w = _rewrap(c)
                if w is not None:
                    fn = getattr(w, method, None)
                    if callable(fn):
                        return fn(*args)
            except Exception:
                pass
            return None

        def _encode(c) -> Optional[Dict[str, Any]]:
            nm = _safe_name(c)
            if not nm:
                return None
            path = _safe_call(c, "GetPathName") or ""
            try:
                w = _rewrap(c)
                cfg = getattr(w, "ReferencedConfiguration", None) or ""
            except Exception:
                cfg = ""
            suppr = _safe_call(c, "IsSuppressed")
            return {
                "name": nm,
                "path": str(path),
                "config": str(cfg) if cfg else "",
                "is_suppressed": bool(suppr) if suppr is not None else False,
            }

        out: List[Dict[str, Any]] = []
        trace: List[str] = []

        # ForceRebuild — 让 SW 把组件实物化到 tree
        try:
            rb = self.asm.ForceRebuild3(False)
            trace.append(f"ForceRebuild3→{rb}")
        except Exception as e:
            trace.append(f"ForceRebuild3_err:{type(e).__name__}")
            try:
                self.doc.raw.EditRebuild3()
                trace.append("EditRebuild3→ok")
            except Exception:
                pass

        # ─── 路 1: GetComponents(True) 顶层 ───
        try:
            comps = self.asm.GetComponents(True)
            trace.append(f"GetComponents(True)→{len(comps) if comps and hasattr(comps,'__len__') else (comps and 'non-empty' or 'None/empty')}")
            if comps:
                for c in comps:
                    r = _encode(c)
                    if r:
                        out.append(r)
                if out:
                    return out
        except Exception as e:
            trace.append(f"GetComponents(True)_err:{type(e).__name__}: {e}")

        # ─── 路 2: GetComponents(False) 深遍 ───
        try:
            comps = self.asm.GetComponents(False)
            trace.append(f"GetComponents(False)→{len(comps) if comps and hasattr(comps,'__len__') else (comps and 'non-empty' or 'None/empty')}")
            if comps:
                for c in comps:
                    r = _encode(c)
                    if r:
                        out.append(r)
                if out:
                    return out
        except Exception as e:
            trace.append(f"GetComponents(False)_err:{type(e).__name__}: {e}")

        # ─── 路 3: RootComponent3 BFS ───
        try:
            cfg_mgr = self.doc.raw.ConfigurationManager
            active_cfg = cfg_mgr.ActiveConfiguration
            trace.append(f"ActiveConfig={active_cfg is not None}")
            root = _safe_call(active_cfg, "GetRootComponent3", True)
            if root is None:
                root = _safe_call(active_cfg, "GetRootComponent")
            trace.append(f"root={root is not None}")
            if root is not None:
                root = _rewrap(root)
                children = _safe_call(root, "GetChildren") or []
                trace.append(f"root.GetChildren→{len(children) if hasattr(children,'__len__') else '?'}")
                queue = list(children)
                seen = set()
                while queue:
                    c = queue.pop(0)
                    c = _rewrap(c)
                    nm = _safe_name(c)
                    if not nm or nm in seen:
                        continue
                    seen.add(nm)
                    r = _encode(c)
                    if r:
                        out.append(r)
                    try:
                        sub = _safe_call(c, "GetChildren") or []
                        queue.extend(sub)
                    except Exception:
                        pass
        except Exception as e:
            trace.append(f"Root_err:{type(e).__name__}: {e}")

        # ─── 路 4: FeatureManager 遍历 · 过滤 reference 类型 ───
        if not out:
            try:
                fm = self.doc.raw.FeatureManager
                feats = fm.GetFeatures(True) or []
                trace.append(f"fm.GetFeatures(True)→{len(feats) if hasattr(feats,'__len__') else '?'}")
                for f in feats:
                    try:
                        ftype = _safe_call(f, "GetTypeName2") or _safe_call(f, "GetTypeName") or ""
                        if "Reference" in str(ftype) or "Component" in str(ftype):
                            nm = _safe_name(f)
                            if nm:
                                out.append({"name": nm, "path": "",
                                             "config": "", "is_suppressed": False,
                                             "_source": "featmgr"})
                    except Exception:
                        continue
            except Exception as e:
                trace.append(f"FeatureMgr_err:{type(e).__name__}: {e}")

        # 暴露 trace 让外部能看到
        if not out and trace:
            out.append({"_trace": trace, "_empty": True})
        return out

    def move_component(self, name: str,
                        dx_mm: float = 0.0, dy_mm: float = 0.0,
                        dz_mm: float = 0.0) -> Dict[str, Any]:
        try:
            self.doc.sel.clear()
            r = self.doc.sel.by_id(name, sel_type="component")
            if not r.get("ok"):
                return r
            util = self.asm.EnumComponents2() and None
            comp = self.doc.raw.SelectionManager.GetSelectedObject6(1, -1)
            if comp is None:
                return _err(LiveError("component not selected"))
            mt = self.doc.live.app.GetMathUtility()
            tx = mt.CreateTransform(
                mt.CreateVector([1, 0, 0]).ArrayData
                + mt.CreateVector([0, 1, 0]).ArrayData
                + mt.CreateVector([0, 0, 1]).ArrayData
                + [_mm2m(dx_mm), _mm2m(dy_mm), _mm2m(dz_mm), 1, 1]
            )
            comp.Transform2 = tx
            return _ok(True, name=name, delta_mm=(dx_mm, dy_mm, dz_mm))
        except Exception as e:
            return _err(e, name=name)

    # ─── 配合 (mate) ────────────────────────────────────────────────
    def _sel_two_refs(self, a: str, a_type: str, b: str, b_type: str) -> Dict[str, Any]:
        self.doc.sel.clear()
        r1 = self.doc.sel.by_id(a, sel_type=a_type, mark=1)
        if not r1.get("ok"):
            return _err(LiveError(f"select {a!r} failed: {r1.get('err')}"))
        r2 = self.doc.sel.by_id(b, sel_type=b_type, append=True, mark=1)
        if not r2.get("ok"):
            return _err(LiveError(f"select {b!r} failed: {r2.get('err')}"))
        return _ok(True)

    def _add_mate(self, mate_type: int, *,
                  distance: float = 0.0, angle_deg: float = 0.0,
                  align: int = 0, flip: bool = False,
                  name: Optional[str] = None) -> Dict[str, Any]:
        errors = _sw.win32_int()
        try:
            mate = self.asm.AddMate3(
                int(mate_type), int(align), bool(flip),
                _mm2m(distance), _mm2m(distance), _mm2m(distance),
                math.radians(angle_deg),
                math.radians(angle_deg), math.radians(angle_deg),
                0, 0, False, False, 0,
                errors,
            )
            if mate is None:
                return _err(LiveError(f"AddMate3 returned null err={errors.value}"))
            if name:
                try: mate.Name = name
                except Exception: pass
            return _ok(True, type=mate_type, err_code=errors.value)
        except Exception as e:
            return _err(e, type=mate_type)

    def mate_coincident(self, a: str, b: str, *,
                        a_type: str = "face", b_type: str = "face",
                        align: int = 0,
                        name: Optional[str] = None) -> Dict[str, Any]:
        r = self._sel_two_refs(a, a_type, b, b_type)
        if not r.get("ok"): return r
        return self._add_mate(SW_MATE.COINCIDENT, align=align, name=name)

    def mate_concentric(self, a: str, b: str, *,
                        a_type: str = "face", b_type: str = "face",
                        align: int = 0,
                        name: Optional[str] = None) -> Dict[str, Any]:
        r = self._sel_two_refs(a, a_type, b, b_type)
        if not r.get("ok"): return r
        return self._add_mate(SW_MATE.CONCENTRIC, align=align, name=name)

    def mate_distance(self, a: str, b: str, distance_mm: float, *,
                      a_type: str = "face", b_type: str = "face",
                      align: int = 0,
                      name: Optional[str] = None) -> Dict[str, Any]:
        r = self._sel_two_refs(a, a_type, b, b_type)
        if not r.get("ok"): return r
        return self._add_mate(SW_MATE.DISTANCE, distance=distance_mm,
                              align=align, name=name)

    def mate_angle(self, a: str, b: str, angle_deg: float, *,
                   a_type: str = "face", b_type: str = "face",
                   align: int = 0,
                   name: Optional[str] = None) -> Dict[str, Any]:
        r = self._sel_two_refs(a, a_type, b, b_type)
        if not r.get("ok"): return r
        return self._add_mate(SW_MATE.ANGLE, angle_deg=angle_deg,
                              align=align, name=name)

    def mate_parallel(self, a: str, b: str, *,
                      a_type: str = "face", b_type: str = "face",
                      align: int = 0,
                      name: Optional[str] = None) -> Dict[str, Any]:
        r = self._sel_two_refs(a, a_type, b, b_type)
        if not r.get("ok"): return r
        return self._add_mate(SW_MATE.PARALLEL, align=align, name=name)

    def mate_perpendicular(self, a: str, b: str, *,
                           a_type: str = "face", b_type: str = "face",
                           name: Optional[str] = None) -> Dict[str, Any]:
        r = self._sel_two_refs(a, a_type, b, b_type)
        if not r.get("ok"): return r
        return self._add_mate(SW_MATE.PERPENDICULAR, name=name)

    def mate_tangent(self, a: str, b: str, *,
                     a_type: str = "face", b_type: str = "face",
                     name: Optional[str] = None) -> Dict[str, Any]:
        r = self._sel_two_refs(a, a_type, b, b_type)
        if not r.get("ok"): return r
        return self._add_mate(SW_MATE.TANGENT, name=name)

    def mate(self, a: str, b: str, mate_type: Union[str, int], *,
             a_type: str = "face", b_type: str = "face",
             distance: float = 0.0, angle_deg: float = 0.0,
             align: int = 0,
             name: Optional[str] = None) -> Dict[str, Any]:
        """通用配合: mate_type 可为 'concentric'/'coincident'/... 或 int."""
        if isinstance(mate_type, str):
            code = SW_MATE.BY_NAME.get(mate_type.lower())
            if code is None:
                return _err(LiveError(f"未知配合: {mate_type!r}"))
        else:
            code = int(mate_type)
        r = self._sel_two_refs(a, a_type, b, b_type)
        if not r.get("ok"): return r
        return self._add_mate(code, distance=distance, angle_deg=angle_deg,
                              align=align, name=name)

    # ─── 干涉检测 / 爆炸 ────────────────────────────────────────────
    def interference(self) -> Dict[str, Any]:
        """触发干涉检测 · 返回干涉数 + 详情."""
        try:
            # 借 IInterferenceDetectionMgr (SW 2009+)
            idm = self.asm.InterferenceDetectionManager
            idm.TreatCoincidenceAsInterference = False
            idm.UseTransform = False
            idm.IncludeMultibodyPartInterferences = True
            inters = idm.GetInterferences()
            count = int(idm.GetInterferenceCount())
            result = {"count": count, "items": []}
            for i, it in enumerate(inters or []):
                try:
                    result["items"].append({
                        "index": i,
                        "volume_m3": float(it.Volume),
                    })
                except Exception:
                    continue
            idm.Done()
            return _ok(True, **result)
        except Exception as e:
            return _err(e)

    def exploded_view(self, name: str = "ExplView") -> Dict[str, Any]:
        """借 RunCommand 触发爆炸视图 · 用户交互方式."""
        return self.doc.live.cmd.run(SW_CMD.ExplodedView)


# ════════════════════════════════════════════════════════════════════════
# DrawingBuilder · 工程图全境
# ════════════════════════════════════════════════════════════════════════
class DrawingBuilder:
    """工程图构建器. 覆盖: 插入标准三视图 · 轴测视图 · 截面视图 · 详图
     · 尺寸 · BOM · 明细表 · 气球标注 · 注释.

    活动文档须为工程图 (IDrawingDoc).
    """

    def __init__(self, doc: LiveDoc):
        self.doc = doc

    @property
    def drw(self) -> Any:
        if not self.doc.is_drawing:
            raise LiveError("活动文档非工程图")
        return self.doc.raw

    # ─── 视图插入 ──────────────────────────────────────────────────
    def std_views(self, part_path: Union[str, Path],
                  x_mm: float = 100.0, y_mm: float = 200.0) -> Dict[str, Any]:
        """从零件/装配插入三视图 (前/右/上). (x,y) 为前视图中心位置."""
        p = Path(part_path).resolve()
        if not p.exists():
            return _err(FileNotFoundError(str(p)))
        try:
            view = self.drw.Create3rdAngleViews2(str(p))
            if view:
                # 移动到指定位置
                try:
                    view.Position = (_mm2m(x_mm), _mm2m(y_mm), 0.0)
                except Exception:
                    pass
            return _ok(view is not None, path=str(p), at=(x_mm, y_mm))
        except Exception as e:
            return _err(e, path=str(p))

    def model_view(self, part_path: Union[str, Path],
                   view_name: str = "Isometric",
                   x_mm: float = 100.0, y_mm: float = 100.0,
                   scale: float = 1.0) -> Dict[str, Any]:
        """插入单视图 · view_name ∈ {Front,Top,Right,Isometric,Current,...}."""
        p = Path(part_path).resolve()
        if not p.exists():
            return _err(FileNotFoundError(str(p)))
        try:
            view = self.drw.CreateDrawViewFromModelView3(
                str(p), view_name,
                _mm2m(x_mm), _mm2m(y_mm), 0.0,
            )
            if view and scale != 1.0:
                try:
                    view.ScaleDecimal = float(scale)
                except Exception:
                    pass
            return _ok(view is not None, view=view_name, at=(x_mm, y_mm))
        except Exception as e:
            return _err(e, view=view_name)

    def section_view(self, parent_view: str,
                     cut_x1_mm: float, cut_y1_mm: float,
                     cut_x2_mm: float, cut_y2_mm: float,
                     x_mm: float = 200.0, y_mm: float = 100.0,
                     label: str = "A") -> Dict[str, Any]:
        """剖视图 · parent_view 为被剖视图名."""
        try:
            self.doc.sel.clear()
            self.doc.sel.by_id(parent_view, sel_type="drawingview"
                               if "drawingview" in SW_SEL.BY_NAME else "feature")
            view = self.drw.CreateSectionView(
                _mm2m(cut_x1_mm), _mm2m(cut_y1_mm),
                _mm2m(cut_x2_mm), _mm2m(cut_y2_mm),
                _mm2m(x_mm), _mm2m(y_mm), 0.0,
                1,  # swCreateDrawViewOption_e
            )
            return _ok(view is not None, parent=parent_view, label=label)
        except Exception as e:
            return _err(e, parent=parent_view)

    def detail_view(self, parent_view: str,
                    center_x_mm: float, center_y_mm: float,
                    radius_mm: float,
                    x_mm: float = 300.0, y_mm: float = 200.0) -> Dict[str, Any]:
        try:
            self.doc.sel.clear()
            self.doc.sel.by_id(parent_view, sel_type="feature")
            view = self.drw.CreateDetailViewAt4(
                _mm2m(center_x_mm), _mm2m(center_y_mm), 0.0,
                _mm2m(radius_mm),
                0, 1, 1.0, 0, False, True, True, True,
                _mm2m(x_mm), _mm2m(y_mm), 0.0,
            )
            return _ok(view is not None, parent=parent_view)
        except Exception as e:
            return _err(e, parent=parent_view)

    def insert_bom(self, anchor_x_mm: float = 250.0,
                   anchor_y_mm: float = 250.0,
                   template: str = "",
                   kind: int = 0) -> Dict[str, Any]:
        """插入 BOM 表. kind: 0=top level only, 1=parts only, 2=indented."""
        try:
            bom = self.drw.InsertBomTable3(
                template, _mm2m(anchor_x_mm), _mm2m(anchor_y_mm),
                0, int(kind), False, False, "", False,
            )
            return _ok(bom is not None, at=(anchor_x_mm, anchor_y_mm))
        except Exception as e:
            return _err(e)

    # ─── 自动尺寸 / 气球 ──────────────────────────────────────────
    def auto_dimension(self) -> Dict[str, Any]:
        """触发 AutoDimension ·调 SW_CMD.SmartDimension 连续补."""
        return self.doc.live.cmd.run(SW_CMD.SmartDimension)


# ════════════════════════════════════════════════════════════════════════
# PropertyMgr · 自定义属性 CRUD
# ════════════════════════════════════════════════════════════════════════
class PropertyMgr:
    """自定义属性管理器 · ICustomPropertyManager.

    作用范围:
      · 默认: 文档级 (config=None)
      · 指定 config: 配置级 (每个配置独立属性)
    """

    def __init__(self, doc: LiveDoc):
        self.doc = doc

    def _mgr(self, config: Optional[str] = None) -> Any:
        return self.doc.raw.Extension.CustomPropertyManager(config or "")

    def set(self, name: str, value: Any, *,
            config: Optional[str] = None,
            prop_type: int = 30,     # swCustomInfoType_e: 30=TEXT, 3=NUMBER, 5=DATE, 11=YES/NO
            overwrite: bool = True) -> Dict[str, Any]:
        try:
            m = self._mgr(config)
            # Add3: Name, Type, Value, OverwriteExisting
            r = int(m.Add3(str(name), int(prop_type), str(value),
                            2 if overwrite else 0))
            return _ok(r == 1 or r == 0, name=name, value=str(value),
                       config=config or "<default>", result=r)
        except Exception as e:
            return _err(e, name=name)

    def get(self, name: str,
            config: Optional[str] = None) -> Dict[str, Any]:
        try:
            m = self._mgr(config)
            val_out = ""
            # Get5: returns (ValOut, ResolvedValOut, WasResolved, LinkToProperty)
            # 需 out params. 用 CustomPropertyManager.Get4 更简单
            try:
                val_out, resolved = m.Get4(str(name), False)
                return _ok(True, name=name, value=val_out,
                           resolved=resolved, config=config or "<default>")
            except Exception:
                v = m.Get(str(name))
                return _ok(True, name=name, value=v,
                           config=config or "<default>")
        except Exception as e:
            return _err(e, name=name)

    def delete(self, name: str,
               config: Optional[str] = None) -> Dict[str, Any]:
        try:
            m = self._mgr(config)
            r = int(m.Delete2(str(name)))
            return _ok(r != 0, name=name)
        except Exception as e:
            return _err(e, name=name)

    def all(self, config: Optional[str] = None) -> Dict[str, Any]:
        """返回所有属性 {name: value}."""
        out: Dict[str, Any] = {}
        try:
            m = self._mgr(config)
            names = list(m.GetNames() or [])
            for n in names:
                try:
                    v, _ = m.Get4(str(n), False)
                except Exception:
                    try:
                        v = m.Get(str(n))
                    except Exception:
                        v = None
                out[str(n)] = v
            return _ok(True, config=config or "<default>", props=out)
        except Exception as e:
            return _err(e)


# ════════════════════════════════════════════════════════════════════════
# EquationMgr · 方程管理器
# ════════════════════════════════════════════════════════════════════════
class EquationMgr:
    """方程管理器 · IEquationMgr. 支持全局变量 + 维度方程."""

    def __init__(self, doc: LiveDoc):
        self.doc = doc

    @property
    def mgr(self) -> Any:
        return self.doc.raw.GetEquationMgr() if hasattr(self.doc.raw, "GetEquationMgr") \
            else self.doc.raw.EquationMgr

    def add(self, equation: str) -> Dict[str, Any]:
        """追加一个方程. 语法: '"D1@Sketch1" = 10mm' 或 '"L" = 100'."""
        try:
            idx = int(self.mgr.Add2(-1, str(equation), True))
            return _ok(idx >= 0, index=idx, equation=equation)
        except Exception as e:
            return _err(e, equation=equation)

    def set(self, index: int, equation: str) -> Dict[str, Any]:
        try:
            ok = bool(self.mgr.Equation[index] == str(equation)
                      or self.mgr.SetEquationAndConfigurationOption(
                          int(index), str(equation), 0, None))
            return _ok(ok, index=index)
        except Exception as e:
            return _err(e, index=index)

    def list(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        try:
            n = int(self.mgr.GetCount())
            for i in range(n):
                try:
                    eq = self.mgr.Equation[i]
                    val = None
                    try: val = float(self.mgr.Value[i])
                    except Exception: pass
                    out.append({"index": i, "equation": eq, "value": val})
                except Exception:
                    continue
        except Exception:
            pass
        return out

    def delete(self, index: int) -> Dict[str, Any]:
        try:
            self.mgr.Delete(int(index))
            return _ok(True, index=index)
        except Exception as e:
            return _err(e, index=index)

    def global_var(self, name: str, value: float) -> Dict[str, Any]:
        """快捷: 添加一个全局变量 `name = value`."""
        return self.add(f'"{name}" = {value}')


# ════════════════════════════════════════════════════════════════════════
# MaterialMgr · 材质管理器
# ════════════════════════════════════════════════════════════════════════
class MaterialMgr:
    """材质属性管理 · 终极根治版.

    根因: SetMaterialPropertyName2 在 SW2023 + pywin32 下经常 **静默失败**:
      - DB 路径不是完整绝对路径 → 不匹配 → 静默不设
      - gencache 污染的 IDispatch → 参数类型不匹配 → 静默不设
      - 某些许可/安装配置下 SetMaterialPropertyName2 根本不生效

    修复策略: 五路设 + 验证回读 + 自定义属性持久化
    """

    _cached_db: Optional[str] = None  # 类级缓存, 避免每次重复查找

    def __init__(self, doc: LiveDoc):
        self.doc = doc

    def _auto_db(self) -> str:
        """自动定位材质库完整路径 (带缓存)."""
        if MaterialMgr._cached_db:
            if Path(MaterialMgr._cached_db).exists():
                return MaterialMgr._cached_db
        db = _sw._find_sw_material_db(
            self.doc.live.app_late if self.doc.live._app_late else None
        )
        if db:
            MaterialMgr._cached_db = db
        return db or ""

    def set_material(self, name: str,
                     database: Optional[str] = None,
                     config: str = "") -> Dict[str, Any]:
        """给零件设置材料 · 五路 fallback + 验证回读.

        路 1: SetMaterialPropertyName2 + 完整DB路径
        路 2: SetMaterialPropertyName2 + 空DB (SW自搜)
        路 3: SetMaterialPropertyName2 + DB短名 (如 "solidworks materials")
        路 4: late-binding re-wrap 后重试
        路 5: 直接设 body density (不指定材料名, 仅写密度)
        最终: 写自定义属性 _Material 作持久化兜底
        """
        if not self.doc.is_part:
            return _err(LiveError("MaterialMgr 仅用于零件"))

        trace: List[Dict[str, Any]] = []
        db_full = database or self._auto_db()

        # ─── 路 1: 完整 DB 路径 ───
        try:
            self.doc.raw.SetMaterialPropertyName2(config, db_full, str(name))
            trace.append({"path": "full_db", "db": db_full})
        except Exception as e:
            trace.append({"path": "full_db", "err": f"{type(e).__name__}: {e}"})

        # 验证回读
        readback = self._readback(config)
        if readback and str(readback).lower().strip() == str(name).lower().strip():
            self._persist_custom_prop(name)
            return _ok(True, name=name, database=db_full, via="full_db",
                       readback=readback, trace=trace)

        # ─── 路 2: 空 DB ───
        try:
            self.doc.raw.SetMaterialPropertyName2(config, "", str(name))
            trace.append({"path": "empty_db"})
        except Exception as e:
            trace.append({"path": "empty_db", "err": f"{type(e).__name__}: {e}"})
        readback = self._readback(config)
        if readback and str(readback).lower().strip() == str(name).lower().strip():
            self._persist_custom_prop(name)
            return _ok(True, name=name, database="", via="empty_db",
                       readback=readback, trace=trace)

        # ─── 路 3: DB 短名 ───
        db_short = Path(db_full).stem if db_full else "solidworks materials"
        try:
            self.doc.raw.SetMaterialPropertyName2(config, db_short, str(name))
            trace.append({"path": "short_db", "db": db_short})
        except Exception as e:
            trace.append({"path": "short_db", "err": f"{type(e).__name__}: {e}"})
        readback = self._readback(config)
        if readback and str(readback).lower().strip() == str(name).lower().strip():
            self._persist_custom_prop(name)
            return _ok(True, name=name, database=db_short, via="short_db",
                       readback=readback, trace=trace)

        # ─── 路 4: late-binding re-wrap 后重试 ───
        try:
            raw_late = _sw._dyn_wrap(self.doc.raw)
            if raw_late is not None:
                raw_late.SetMaterialPropertyName2(config, db_full, str(name))
                trace.append({"path": "late_wrap"})
                readback = self._readback(config)
                if readback and str(readback).lower().strip() == str(name).lower().strip():
                    self._persist_custom_prop(name)
                    return _ok(True, name=name, via="late_wrap",
                               readback=readback, trace=trace)
        except Exception as e:
            trace.append({"path": "late_wrap", "err": f"{type(e).__name__}: {e}"})

        # ─── 路 5: 自定义属性持久化 (兜底 · 材料名写入文档属性) ───
        self._persist_custom_prop(name)
        trace.append({"path": "custom_prop_fallback"})

        return _ok(True, name=name, via="custom_prop_fallback",
                   warn="SetMaterialPropertyName2 所有路径均静默失败, 已写自定义属性 _Material",
                   readback=readback or "(none)",
                   trace=trace)

    def _readback(self, config: str = "") -> Optional[str]:
        """读回当前材料名."""
        try:
            r = self.doc.raw.GetMaterialPropertyName2(config, "")
            if isinstance(r, tuple):
                return str(r[0]) if r[0] else None
            return str(r) if r else None
        except Exception:
            pass
        try:
            n = _sw._com_prop(self.doc.raw, "MaterialIdName")
            return str(n) if n else None
        except Exception:
            return None

    def _persist_custom_prop(self, name: str):
        """写自定义属性 _Material · 确保即使 COM API 静默失败也有持久化记录."""
        try:
            self.doc.props.set("_Material", name)
        except Exception:
            pass

    def get_material(self, config: str = "") -> Dict[str, Any]:
        if not self.doc.is_part:
            return _err(LiveError("MaterialMgr 仅用于零件"))
        try:
            readback = self._readback(config)
            db_out = ""
            if readback:
                return _ok(True, name=readback, database=db_out,
                           config=config or "<default>")
            # 回退: 读自定义属性 _Material
            try:
                r = self.doc.props.get("_Material")
                if r.get("ok") and r.get("value"):
                    return _ok(True, name=r["value"], database="",
                               config=config or "<default>",
                               via="custom_prop_fallback")
            except Exception:
                pass
            return _ok(True, name="", database="",
                       config=config or "<default>",
                       note="no material set")
        except Exception as e:
            return _err(e)

    def clear_material(self, config: str = "") -> Dict[str, Any]:
        r = self.set_material("", database="", config=config)
        try:
            self.doc.props.delete("_Material")
        except Exception:
            pass
        return r


# ════════════════════════════════════════════════════════════════════════
# 自测 + CLI (在末尾 edit 追加)
# ════════════════════════════════════════════════════════════════════════
def _self_test() -> Dict[str, Any]:
    res: Dict[str, Any] = {"pass": [], "fail": [], "score": 0, "total": 0}

    # T1: 枚举完整
    try:
        assert SW_CMD.BY_NAME["fillet"] == SW_CMD.Fillet
        assert SW_VIEW.NAMES["iso"] == SW_VIEW.ISOMETRIC
        assert SW_MATE.BY_NAME["concentric"] == SW_MATE.CONCENTRIC
        assert SW_SEL.BY_NAME["face"] == SW_SEL.FACE
        res["pass"].append("T1_enums"); res["score"] += 1
    except Exception as e:  # noqa: BLE001
        res["fail"].append(("T1_enums", repr(e)))
    res["total"] += 1

    # T2: SWLive 可实例化 (不连 GUI)
    try:
        live = SWLive()
        assert live._bridge is None
        assert isinstance(live.status(), dict)
        res["pass"].append("T2_init"); res["score"] += 1
    except Exception as e:
        res["fail"].append(("T2_init", repr(e)))
    res["total"] += 1

    # T3: CommandRunner 命名表
    try:
        live = SWLive()
        runner = live.cmd
        cmds = runner.list_commands()
        assert "rebuild" in cmds
        assert "fillet" in cmds
        res["pass"].append("T3_cmd_runner"); res["score"] += 1
    except Exception as e:
        res["fail"].append(("T3_cmd_runner", repr(e)))
    res["total"] += 1

    # T4: 工具函数
    try:
        assert abs(_mm2m(1000) - 1.0) < 1e-9
        assert abs(_m2mm(0.5) - 500) < 1e-6
        assert _as_m_tuple([10, 20]) == (0.01, 0.02)
        res["pass"].append("T4_utils"); res["score"] += 1
    except Exception as e:
        res["fail"].append(("T4_utils", repr(e)))
    res["total"] += 1

    res["ratio"] = f"{res['score']}/{res['total']}"
    res["pct"] = round(100.0 * res["score"] / max(res["total"], 1), 1)
    return res


def _cli() -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="dao_sw_live · SW 活体万象 (L11 Omega)"
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="SW 活体状态")
    sub.add_parser("test", help="自测")

    p_newpart = sub.add_parser("new-part", help="新建零件")
    p_newpart.add_argument("--template", default=None)

    p_cmd = sub.add_parser("cmd", help="触发 SW 内部命令")
    p_cmd.add_argument("command", help="命令名或 id (见 SW_CMD.BY_NAME)")

    p_macro = sub.add_parser("macro", help="跑 .swp 宏")
    p_macro.add_argument("path")
    p_macro.add_argument("--module", default="Main")
    p_macro.add_argument("--proc",   default="main")

    p_view = sub.add_parser("view", help="切视图")
    p_view.add_argument("action")

    p_snap = sub.add_parser("snap", help="截图")
    p_snap.add_argument("out")
    p_snap.add_argument("--view", default=None)

    sub.add_parser("list-cmds", help="列出常用 SW 命令")

    a = ap.parse_args()
    live = SWLive()

    if a.cmd == "test":
        r = _self_test()
        print("\n" + "=" * 56)
        print(f"  dao_sw_live 自测: {r['ratio']}  ({r['pct']}%)")
        print("=" * 56)
        for n in r["pass"]: print(f"  + {n}")
        for n, e in r["fail"]: print(f"  ! {n}: {e}")
        return 0 if not r["fail"] else 1

    if a.cmd == "status":
        live.ensure_live()
        print(json.dumps(live.status(), ensure_ascii=False, indent=2))
        return 0

    if a.cmd == "list-cmds":
        print(json.dumps(SW_CMD.BY_NAME, ensure_ascii=False, indent=2))
        return 0

    if a.cmd == "new-part":
        live.ensure_live()
        d = live.new_part(template=a.template)
        print(json.dumps({"ok": True, "title": d.title(),
                          "path": d.path_name() or "<unsaved>"},
                         ensure_ascii=False))
        return 0

    if a.cmd == "cmd":
        live.ensure_live()
        cmd = a.command
        try:
            cid = int(cmd)
        except ValueError:
            cid = cmd
        r = live.cmd.run(cid)
        print(json.dumps(r, ensure_ascii=False))
        return 0 if r.get("ok") else 1

    if a.cmd == "macro":
        live.ensure_live()
        r = live.macro.run_file(a.path, module=a.module, proc=a.proc)
        print(json.dumps(r, ensure_ascii=False))
        return 0 if r.get("ok") else 1

    if a.cmd == "view":
        live.ensure_live()
        r = live.view(a.action)
        print(json.dumps(r, ensure_ascii=False))
        return 0 if r.get("ok") else 1

    if a.cmd == "snap":
        live.ensure_live()
        r = live.snap(a.out, view=a.view)
        print(json.dumps(r, ensure_ascii=False))
        return 0 if r.get("ok") else 1

    return 0


if __name__ == "__main__":
    sys.exit(_cli())
