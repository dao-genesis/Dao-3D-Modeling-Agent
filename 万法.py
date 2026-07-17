#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
万法.py — 3D建模Agent · 万法归一 · 单一入口
═══════════════════════════════════════════════════════════════════════════════

    聖人總而用之，其數一也  ——  意出《莊子·養生主》

    天之道, 利而不害; 聖人之道, 為而不爭.       ——  《道德經》八十一
    大曰逝, 逝曰遠, 遠曰反.                    ——  《道德經》二十五
    以神遇而不以目視, 官知止而神欲行.           ——  《莊子·養生主》
    反者道之動, 弱者道之用.                    ——  《道德經》四十

本器之立:

    此文 3D建模Agent 已歷七百餘稿, 散為本源/反笙/萬法/驗/模板/演示/實戰/天下
    九層, 字元逾千萬. 然 Agent 欲用其一, 須記其路; 欲組其全, 須縫其線.

    故立此 `万法.py` 一卷, 以一字御萬法:

        `from 万法 import 道`

    其下掛十五妙門, 皆懶加載, 隨用隨取, 不用不擾:

        核 (kernel)   · OCP/OCCT BREP · 無中間層建模本源
        反 (reverse)  · 外(天下 20 平台) / 內(FCStd/STEP/BREP)
        秀 (show)     · FreeCAD GUI 反向鎖定為展示台
        活體 (live)   · SolidWorks memid 直連 (sldworks.tlb 710 接口)
        審 (audit)    · 八層審核 (拓撲→幾何→工程→裝配→格式→參→意→感)
        驗 (verify)   · N 相驗證框架 (Phase/Check/評分)
        循 (loop)     · probe→build→verify→heal 閉環控制器
        運動 (kine)   · FK/IK/動力/干涉/臨界轉速 零依賴純 Python
        網格 (mesh)   · STL/OBJ/GLB 讀寫 + 流形檢測
        圖紙 (dxf)    · AC1009+ DXF 解析 + 尺寸抽取
        文檔 (docx)   · docx ZIP 解析 · 段落/圖/表/關係
        鍛 (forge)    · FreeCAD 動態持久化
        執 (engine)   · 多引擎透明執行
        宗 (zong)     · 第十四妙門 · 源碼總攝 · 16 宗 221 倉 · 取之盡錙銖
        感 (perceive) · 第十五妙門 · 三維心象 · 渲/寫/述/復/校 · 純 numpy 自洽

    另有 `道.意(…)` 一門, 受自然語言之意念, 自動反向優先, 天下無有方從無到有.

    本器從零加一, 不改一行既有代碼; 是謂 "為而不爭".

用法梗概:

    from 万法 import 道

    道.summary()                                    # 眾相一覽
    道.意("設計手機支架 70mm 可調角")                # 意念直達 (先反天下, 後建)

    道.反.外("phone stand 70mm, adjustable")        # 20 平台搜索+擇優
    道.反.内("model.FCStd", patch={"Body.L": 120})  # 反·內: ops+改參+重放

    道.秀.live_show("part.step", shots=["iso","front","top"])

    dao = 道.活体.connect()                         # SW 直連 (道_直連_底層)
    dao.transform.set("screen_plate-1", (508, 100, 0))
    dao.mate.concentric(face_a, face_b, align=1)

    道.核.box(80, 60, 40).fillet(r=3)               # OCP 建模
    道.審.full(shape, intent=spec)                   # 八層審核
    道.運動.Mechanism("crusher")                     # 運動鏈

CLI (python 万法.py <cmd>):

    summary                     系統狀態匯總
    验证 | verify               萬法驗 · 16 相懶加載煙霧測
    意 <text> | intent <text>   意念直達
    反 <text> | reverse <text>  反·外(天下 20 平台)
    适 <file> [k=v...]          反·內+改參+重放
    秀 <file> | show <file>     FreeCAD GUI 展示
    活體 | live                 連 SolidWorks 活體
    審 <step> | audit <step>    八層審核
    清冊 | manifest             打印 `萬法清冊.md`
"""
from __future__ import annotations

import json
import os
import sys
import time
import types
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

# ═══════════════════════════════════════════════════════════════════════════
# ① 路徑引導 · 五層 sys.path 自動注入 (借 _paths.py)
# ═══════════════════════════════════════════════════════════════════════════
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    import _paths as _P  # noqa: F401 — 觸發五層 sys.path 注入
except Exception as _e:
    _P = None  # 極端情形 (搬遷中) 仍可運行, 單項懶加載各自自保

__version__ = "1.0.0"
__all__ = [
    "道", "Res", "Dao",
    "ROOT", "LAYERS",
]

ROOT: Path = _ROOT
LAYERS: Dict[str, Path] = {}
if _P is not None:
    for k, v in _P.LAYER_DIRS.items():
        p = _ROOT / v
        if p.exists():
            LAYERS[k] = p


# ═══════════════════════════════════════════════════════════════════════════
# ② 統一結果契約 · {ok, data, warnings, error}
# ═══════════════════════════════════════════════════════════════════════════
class Res(dict):
    """統一結果字典 · 子類 dict · 屬性訪問.

    所有 `道.*` 門面之方法, 若有返回, 應為 Res 或可序列化值.
    約定:
        ok        : bool         是否成功
        data      : Any          主體結果
        warnings  : List[str]    非致命警告
        error     : Optional[str] 致命錯誤 (ok=False 時)
        elapsed_s : float        用時 (秒, 若量測)
    """

    @classmethod
    def succ(cls, data: Any = None, warnings: Optional[List[str]] = None,
             **extra) -> "Res":
        r = cls(ok=True, data=data, warnings=list(warnings or []), error=None)
        r.update(extra)
        return r

    @classmethod
    def fail(cls, error: str, data: Any = None,
             warnings: Optional[List[str]] = None, **extra) -> "Res":
        r = cls(ok=False, data=data, warnings=list(warnings or []),
                error=str(error))
        r.update(extra)
        return r

    def __getattr__(self, name: str) -> Any:
        if name in self:
            return self[name]
        raise AttributeError(name)

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


# ═══════════════════════════════════════════════════════════════════════════
# ③ 懶加載描述子 · 首次訪問時 import, 後續緩存
# ═══════════════════════════════════════════════════════════════════════════
class _Lazy:
    """對外像屬性, 首次訪問時調 loader, 結果掛到 owner 上取代自己."""

    __slots__ = ("loader", "name", "fallback_ok")

    def __init__(self, loader: Callable[[], Any], name: str = "",
                 fallback_ok: bool = True):
        self.loader = loader
        self.name = name
        self.fallback_ok = fallback_ok

    def __set_name__(self, owner, name):
        if not self.name:
            self.name = name

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        try:
            val = self.loader()
        except Exception as e:
            if not self.fallback_ok:
                raise
            # 返回佔位符 · 帶 error, 避免阻斷其他門
            val = _Missing(self.name, str(e))
        # 寫回實例, 後續直取
        obj.__dict__[self.name] = val
        return val


class _Missing:
    """懶加載失敗時的占位 · 任何操作返 Res.fail, 不炸."""

    __slots__ = ("_name", "_err")

    def __init__(self, name: str, err: str):
        self._name = name
        self._err = err

    def __bool__(self):
        return False

    def __repr__(self):
        return f"<_Missing {self._name!r} error={self._err!r}>"

    def __getattr__(self, key: str) -> Any:
        err = f"{self._name} 未就緒: {self._err}"

        def _stub(*a, **kw):
            return Res.fail(err)
        return _stub

    def __call__(self, *args, **kwargs):
        return Res.fail(f"{self._name} 未就緒: {self._err}")


# ═══════════════════════════════════════════════════════════════════════════
# ④ 反·面 (reverse facet) · 外反+內反統一
# ═══════════════════════════════════════════════════════════════════════════
class _ReverseFacet:
    """反者道之動 — 外(天下 20 平台)+內(本地件 ops)."""

    def __init__(self):
        self._reverse = None    # DaoReverse
        self._fc_reverse = None  # FCReverse

    def _load_outer(self):
        if self._reverse is None:
            from dao_reverse import DaoReverse
            self._reverse = DaoReverse()
        return self._reverse

    def _load_inner(self):
        if self._fc_reverse is None:
            from fc_reverse import FCReverse
            self._fc_reverse = FCReverse
        return self._fc_reverse

    # ── 外 (天下) ─────────────────────────────────────────────
    def 外(self, intent: str, **kw) -> Res:
        """反·外: 20 平台+GitHub+Web 搜索, 排序擇優, 返 plan.

        plan.cascade_protocol.action ∈ {use_directly, adapt_existing,
                                          reference_and_build, build_from_scratch}
        """
        try:
            rev = self._load_outer()
            plan = rev.fulfill(intent, **kw)
            return Res.succ(data=plan)
        except Exception as e:
            return Res.fail(f"反·外: {e}")

    outer = 外  # English alias

    def 搜(self, query: str, **kw) -> Res:
        """反·外 的搜索子命令 (不含排序/適配)."""
        try:
            rev = self._load_outer()
            results = rev.world.search(query, **kw) if hasattr(rev, "world") \
                else rev.search(query, **kw)
            return Res.succ(data=results)
        except Exception as e:
            return Res.fail(f"反·搜: {e}")

    search = 搜

    # ── 內 (本地件) ───────────────────────────────────────────
    def 内(self, path: str, patch: Optional[Dict[str, Any]] = None,
           **kw) -> Res:
        """反·內: 本地 FCStd/STEP/BREP → ops → [patch] → replay."""
        try:
            FC = self._load_inner()
            if patch:
                r = FC.adapt(path, patch=patch, **kw)
            else:
                r = FC.reverse(path, **kw)
            return Res.succ(data=r)
        except Exception as e:
            return Res.fail(f"反·內: {e}")

    adapt = 内
    inner = 内

    def 诊(self, path: str) -> Res:
        """反·內 診斷: op_count + warnings + replayable."""
        try:
            FC = self._load_inner()
            return Res.succ(data=FC.probe(path))
        except Exception as e:
            return Res.fail(f"反·診: {e}")

    probe = 诊

    # ── 版本化 (diff/merge/依賴圖) ────────────────────────────
    def 差(self, path_a: str, path_b: str) -> Res:
        """反·差: 兩件模型級語義 diff (對象/參數/草圖幾何/約束)."""
        try:
            from fc_diff import FCDiff
            return Res.succ(data=FCDiff.diff_files(path_a, path_b))
        except Exception as e:
            return Res.fail(f"反·差: {e}")

    diff = 差

    def 合(self, base: list, ours: list, theirs: list) -> Res:
        """反·合: ops 三方語義合併, 非重疊自動合, 重疊列 conflicts."""
        try:
            from fc_diff import FCDiff
            return Res.succ(data=FCDiff.merge3(base, ours, theirs))
        except Exception as e:
            return Res.fail(f"反·合: {e}")

    merge = 合

    def 图(self, path: str) -> Res:
        """反·圖: 件 → ops 特徵依賴 DAG (deps/rdeps/order/roots/leaves/cycles)."""
        try:
            from fc_dag import FCDag
            FC = self._load_inner()
            ops = FC.reverse(path).get("ops", [])
            return Res.succ(data=FCDag.build(ops))
        except Exception as e:
            return Res.fail(f"反·圖: {e}")

    dag = 图

    def 变(self, path: str, patch: Dict[str, Any], replay: bool = False,
           **kw) -> Res:
        """反·變: 增量改參 — 只重算受影響鏈路 (patch_plan), replay=True 即重放."""
        try:
            from fc_dag import FCDag
            FC = self._load_inner()
            ops = FC.reverse(path).get("ops", [])
            plan = FCDag.patch_plan(ops, patch)
            if replay and plan["replay_ops"]:
                plan["replay"] = FC.replay(plan["replay_ops"], **kw)
            return Res.succ(data=plan)
        except Exception as e:
            return Res.fail(f"反·變: {e}")

    evolve = 变


# ═══════════════════════════════════════════════════════════════════════════
# ⑤ 秀·面 (show facet) · FreeCAD GUI 為天生展示台
# ═══════════════════════════════════════════════════════════════════════════
class _ShowFacet:
    """任何產物 → FreeCAD GUI 展示."""

    def __init__(self):
        self._fc = None

    def _load(self):
        if self._fc is None:
            from fc_show import FCShow
            self._fc = FCShow
        return self._fc

    def live_show(self, src: Union[str, List[Dict[str, Any]]],
                  shots: Optional[List[str]] = None,
                  **kw) -> Res:
        """一鍵: 清空→加載→多視角截圖. shots 預設 iso."""
        try:
            FC = self._load()
            FC.ensure_gui()
            r = FC.live_show(src, shots=shots, **kw)
            return Res.succ(data=r)
        except Exception as e:
            return Res.fail(f"秀·live_show: {e}")

    def load(self, path: str) -> Res:
        try:
            FC = self._load()
            FC.ensure_gui()
            return Res.succ(data=FC.load(path))
        except Exception as e:
            return Res.fail(f"秀·load: {e}")

    def screenshot(self, out_path: str, width: int = 1920,
                   height: int = 1080) -> Res:
        try:
            FC = self._load()
            FC.ensure_gui()
            return Res.succ(data=FC.screenshot(out_path, width=width,
                                                height=height))
        except Exception as e:
            return Res.fail(f"秀·screenshot: {e}")

    def view(self, action: str = "isometric") -> Res:
        try:
            FC = self._load()
            return Res.succ(data=FC.view(action))
        except Exception as e:
            return Res.fail(f"秀·view: {e}")

    def status(self) -> Res:
        try:
            FC = self._load()
            return Res.succ(data=FC.status())
        except Exception as e:
            return Res.fail(f"秀·status: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# ⑥ 活体·面 (live facet) · SolidWorks memid 直連
# ═══════════════════════════════════════════════════════════════════════════
class _LiveFacet:
    """活體 SolidWorks · 走 道_直連_底層 (memid 無中間層)."""

    def __init__(self):
        self._dao_cls = None
        self._dao_inst = None

    def _load(self):
        if self._dao_cls is None:
            from 道_直连_底层 import Dao as _SWDao  # noqa: N813
            import 道_直连_底层_facets  # noqa: F401 — 掛 facets
            self._dao_cls = _SWDao
        return self._dao_cls

    def connect(self, launch_if_dead: bool = False) -> Any:
        """返 Dao 單例 (已連接).

        launch_if_dead=True 時 SW 未運行則自動啟動.
        直接返回 Dao 實例 (非 Res 包裹) · 供 agent 鏈式調用.
        """
        DaoCls = self._load()
        dao = DaoCls()
        if not dao.connected:
            if launch_if_dead:
                dao.connect_or_launch()
            else:
                dao.connect()
        self._dao_inst = dao
        return dao

    def is_alive(self) -> bool:
        try:
            DaoCls = self._load()
            d = DaoCls()
            if not d.connected:
                d.connect()
            return d.connected and d.sw is not None
        except Exception:
            return False

    def summary(self) -> Res:
        try:
            dao = self.connect()
            return Res.succ(data=dao.summary())
        except Exception as e:
            return Res.fail(f"活體·summary: {e}")

    def memid(self, iface: str, name: Optional[str] = None) -> Res:
        """查方法 memid/簽名 (無需活體, 只讀 tlb)."""
        try:
            from 道_直连_底层 import MemidTable
            mt = MemidTable()
            mt.load()
            if name is None:
                return Res.succ(data={
                    "methods": mt.list_methods(iface),
                    "properties": mt.list_properties(iface),
                })
            return Res.succ(data={
                "memid": mt.memid(iface, name),
                "signature": mt.signature(iface, name),
                "which_iface": mt.which_iface(iface, name),
            })
        except Exception as e:
            return Res.fail(f"活體·memid: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# ⑦ 核·面 (kernel facet) · OCP/OCCT BREP 本源
# ═══════════════════════════════════════════════════════════════════════════
class _KernelFacet:
    """BREP 內核 · 零中間層 · 離線可用."""

    def __init__(self):
        self._kernel_cls = None
        self._bridge_cls = None

    def _load_kernel(self):
        if self._kernel_cls is None:
            from dao_kernel import DaoKernel
            self._kernel_cls = DaoKernel
        return self._kernel_cls

    def _load_bridge(self):
        if self._bridge_cls is None:
            from dao_kernel import DaoBridge
            self._bridge_cls = DaoBridge
        return self._bridge_cls

    def instance(self):
        """返 DaoKernel 實例 (由調用方持有)."""
        return self._load_kernel()()

    # 常用原語快捷 (Res 包裹 · 失敗不炸)
    def make(self, primitive: str, **params) -> Res:
        """make('box', L=80, W=60, H=40) / make('cylinder', R=10, H=50) ..."""
        try:
            k = self.instance()
            fn = getattr(k, f"make_{primitive}", None) or getattr(
                k, primitive, None)
            if fn is None:
                return Res.fail(f"未知原語: {primitive}")
            shape = fn(**params)
            return Res.succ(data=shape)
        except Exception as e:
            return Res.fail(f"核·make_{primitive}: {e}")

    def bridge(self):
        return self._load_bridge()()


# ═══════════════════════════════════════════════════════════════════════════
# ⑧ 審·面 (audit facet) · 八層審核
# ═══════════════════════════════════════════════════════════════════════════
class _AuditFacet:
    """八層審核: 拓撲→幾何→工程→裝配→格式→參→意→感."""

    def __init__(self):
        self._mod = None

    def _load(self):
        if self._mod is None:
            import dao_audit
            self._mod = dao_audit
        return self._mod

    def full(self, shape, **kw) -> Res:
        try:
            m = self._load()
            report = m.full_audit(shape, **kw)
            return Res.succ(data=report)
        except Exception as e:
            return Res.fail(f"審·full: {e}")

    def topology(self, shape) -> Res:
        try:
            m = self._load()
            return Res.succ(data=m.audit_topology(shape))
        except Exception as e:
            return Res.fail(f"審·topology: {e}")

    def geometry(self, shape, **kw) -> Res:
        try:
            m = self._load()
            return Res.succ(data=m.audit_geometry(shape, **kw))
        except Exception as e:
            return Res.fail(f"審·geometry: {e}")

    def engineering(self, shape, **kw) -> Res:
        try:
            m = self._load()
            return Res.succ(data=m.audit_engineering(shape, **kw))
        except Exception as e:
            return Res.fail(f"審·engineering: {e}")

    def heal(self, shape, precision: float = 1e-4) -> Res:
        try:
            m = self._load()
            healed, report = m.heal_shape(shape, precision=precision)
            return Res.succ(data={"shape": healed, "report": report})
        except Exception as e:
            return Res.fail(f"審·heal: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# ⑨ 驗·面 (verify facet) · N 相驗證框架
# ═══════════════════════════════════════════════════════════════════════════
class _VerifierFacet:
    """N 相驗證框架 · Phase/Check/評分 · 零依賴."""

    def __init__(self):
        self._mod = None

    def _load(self):
        if self._mod is None:
            import dao_verifier
            self._mod = dao_verifier
        return self._mod

    def new(self, title: str = "驗"):
        m = self._load()
        return m.Verifier(title=title)

    def phase_ctx(self, verifier, title: str):
        return verifier.phase(title)


# ═══════════════════════════════════════════════════════════════════════════
# ⑩ 循·面 (loop facet) · probe→build→verify→heal 閉環
# ═══════════════════════════════════════════════════════════════════════════
class _LoopFacet:
    """通用閉環控制器 · 零依賴."""

    def __init__(self):
        self._mod = None

    def _load(self):
        if self._mod is None:
            import dao_loop
            self._mod = dao_loop
        return self._mod

    def controller(self, **kw):
        m = self._load()
        return m.LoopController(**kw)

    def snapshot_env(self, **kw):
        m = self._load()
        return m.Environment.snapshot(**kw)


# ═══════════════════════════════════════════════════════════════════════════
# ⑪ 運動·面 (kinematics facet) · FK/IK/動力學 · 零依賴
# ═══════════════════════════════════════════════════════════════════════════
class _KinematicsFacet:
    """FK/IK/干涉/臨界轉速 · 零依賴純 Python · 8 種關節."""

    def __init__(self):
        self._mod = None

    def _load(self):
        if self._mod is None:
            import dao_kinematics
            self._mod = dao_kinematics
        return self._mod

    def Mechanism(self, name: str = "mechanism"):
        m = self._load()
        return m.Mechanism(name=name)

    def SE3(self, *a, **kw):
        m = self._load()
        return m.SE3(*a, **kw)

    def fk(self, mechanism, q):
        m = self._load()
        return m.forward_kinematics(mechanism, q)

    def ik(self, mechanism, target_se3, **kw):
        m = self._load()
        return m.inverse_kinematics(mechanism, target_se3, **kw)

    def simulate(self, mechanism, **kw):
        m = self._load()
        return m.simulate(mechanism, **kw)


# ═══════════════════════════════════════════════════════════════════════════
# ⑫ 網格·面 (mesh facet) · STL/OBJ/GLB 零依賴
# ═══════════════════════════════════════════════════════════════════════════
class _MeshFacet:
    def __init__(self):
        self._mod = None

    def _load(self):
        if self._mod is None:
            import dao_mesh
            self._mod = dao_mesh
        return self._mod

    def read(self, path: str, **kw) -> Res:
        try:
            m = self._load()
            stats = m.read_mesh(path, **kw)
            if stats is None:
                return Res.fail(f"無法讀取: {path}")
            return Res.succ(data=stats)
        except Exception as e:
            return Res.fail(f"網格·read: {e}")

    def triangles(self, path: str) -> Res:
        try:
            m = self._load()
            return Res.succ(data=m.read_stl_triangles(path))
        except Exception as e:
            return Res.fail(f"網格·triangles: {e}")

    def write_stl(self, path: str, triangles) -> Res:
        try:
            m = self._load()
            n = m.write_stl_binary(path, triangles)
            return Res.succ(data={"bytes": n, "path": path})
        except Exception as e:
            return Res.fail(f"網格·write_stl: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# ⑬ 圖紙/文檔 · 零依賴 DXF + docx
# ═══════════════════════════════════════════════════════════════════════════
class _DxfFacet:
    def __init__(self):
        self._mod = None

    def _load(self):
        if self._mod is None:
            import dao_dxf
            self._mod = dao_dxf
        return self._mod

    def parse(self, path: str) -> Res:
        try:
            m = self._load()
            return Res.succ(data=m.parse(path) if hasattr(m, "parse")
                             else m.DxfDocument(path))
        except Exception as e:
            return Res.fail(f"圖紙·parse: {e}")


class _DocxFacet:
    def __init__(self):
        self._mod = None

    def _load(self):
        if self._mod is None:
            import dao_docx
            self._mod = dao_docx
        return self._mod

    def parse(self, path: str) -> Res:
        try:
            m = self._load()
            return Res.succ(data=m.parse(path) if hasattr(m, "parse")
                             else m.DocxDocument(path))
        except Exception as e:
            return Res.fail(f"文檔·parse: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# ⑭ 鍛 / 執 · FreeCAD 動態持久化 + 多引擎執行
# ═══════════════════════════════════════════════════════════════════════════
class _ForgeFacet:
    def __init__(self):
        self._cls = None

    def _load(self):
        if self._cls is None:
            from dao_forge import DaoForge
            self._cls = DaoForge
        return self._cls

    def instance(self, output_dir: Optional[str] = None):
        return self._load()(output_dir=output_dir)


class _EngineFacet:
    def __init__(self):
        self._cls = None

    def _load(self):
        if self._cls is None:
            from dao_engine import DaoEngine
            self._cls = DaoEngine
        return self._cls

    def instance(self, output_dir: Optional[str] = None):
        return self._load()(output_dir=output_dir)


# ═══════════════════════════════════════════════════════════════════════════
# ⑮ 感·面 (perception facet) · 三维心象 · 不依赖任何外部建模/云平台
#     見小曰明 · 以神遇而不以目視 · 道生一(光栅)一生二(轮廓+深度)二生三(位姿)三生万物
#     render 渲 → sketch 写 → describe 述 → recover 复 → compare 校
# ═══════════════════════════════════════════════════════════════════════════
class _PerceptionFacet:
    """第十五妙门 · 三维感知 · 纯 numpy 自洽闭环 (dao_perception).

    五能, 皆零外部依赖 (仅 numpy; 读网格可选 trimesh):
        渲(render)   · 软光栅 z-buffer → 深度/掩膜/法线/明暗
        写(sketch)   · Marr 2.5D 初草图 (轮廓/深度棱/折痕)
        述(describe) · 结构理解 (PCA 主轴/对称/连通件/欧拉/五问)
        复(recover)  · 分析-综合反演位姿 (藏一姿→多视轮廓→从头复原)
        校(compare)  · 两模型 ICP 对齐 + Hausdorff 差异 (抓幻觉/错坐标)
    """

    def __init__(self):
        self._mod = None

    def _load(self):
        if self._mod is None:
            import dao_perception
            self._mod = dao_perception
        return self._mod

    def 述(self, path: str, **kw) -> Res:
        """述: 读网格→结构理解, 答五问 (拓扑/失败/约束/手感/负空间)."""
        try:
            m = self._load()
            V, F = m.load_mesh(path)
            return Res.succ(data=m.describe(V, F, **kw))
        except Exception as e:
            return Res.fail(f"感·述: {e}")

    def 渲(self, path: str, view: str = "iso", res: int = 320,
           out: Optional[str] = None) -> Res:
        """渲: 软光栅渲染一视角, 返回掩膜像素数; out 给定则存明暗 PNG."""
        try:
            m = self._load()
            V, F = m.load_mesh(path)
            cam = m._auto_cam(V, view, res)
            rr = m.render(V, F, cam)
            if out:
                m.save_gray(rr.shaded, out)
            return Res.succ(data={"view": view, "res": res,
                                  "mask_px": int(rr.mask.sum()), "out": out})
        except Exception as e:
            return Res.fail(f"感·渲: {e}")

    def 写(self, path: str, view: str = "iso", res: int = 320,
           out: Optional[str] = None) -> Res:
        """写: 提取 2.5D 初草图 (轮廓/深度棱/折痕); out 给定则存 RGB 叠加图."""
        try:
            m = self._load()
            V, F = m.load_mesh(path)
            cam = m._auto_cam(V, view, res)
            rr = m.render(V, F, cam)
            sk = m.sketch(rr)
            if out:
                m.save_rgb(m.sketch_rgb(rr), out)
            return Res.succ(data={
                "view": view, "res": res, "out": out,
                "silhouette_px": int(sk["silhouette"].sum()),
                "depth_edge_px": int(sk["depth_edge"].sum()),
                "crease_px": int(sk["crease"].sum()),
            })
        except Exception as e:
            return Res.fail(f"感·写: {e}")

    def 复(self, path: str, res: int = 128, n_pts: int = 7000,
           seed: int = 2026) -> Res:
        """复: 自洽闭环位姿反演 — 藏一姿→多视轮廓→从头复原, 报角度/位移误差."""
        try:
            m = self._load()
            V, F = m.load_mesh(path)
            return Res.succ(data=m.recover_selftest(V, F, res=res, n_pts=n_pts, seed=seed))
        except Exception as e:
            return Res.fail(f"感·复: {e}")

    def 校(self, a: str, b: str, align: bool = True, n: int = 4000) -> Res:
        """校: 两模型对齐+差异 (mean/Hausdorff/匹配率), 抓错坐标与幻觉."""
        try:
            m = self._load()
            Va, Fa = m.load_mesh(a)
            Vb, Fb = m.load_mesh(b)
            return Res.succ(data=m.compare(Va, Fa, Vb, Fb, n=n, align=align))
        except Exception as e:
            return Res.fail(f"感·校: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# ⑭ 宗·面 (zong facet) · 第十四妙门 · 源码总摄
#     取之尽锱铢, 用之如泥沙 · 圣人总而用之, 其数一也.
# ═══════════════════════════════════════════════════════════════════════════
class _ZongFacet:
    """第十四妙门 · 源码总摄 · 16 宗 221 仓 (含 十六·真底层 DeepCore).

    归一切常用建模软件源码于一处, 供 agent 按意查取.
    圣人总而用之, 其数一也.
    """

    def __init__(self):
        self._cls = None
        self._inst = None

    def _load(self):
        if self._inst is None:
            from dao_归宗 import DaoZong
            self._cls = DaoZong
            self._inst = DaoZong()
        return self._inst

    def summary(self) -> Res:
        try:
            z = self._load()
            return Res.succ(data=z.summary())
        except Exception as e:
            return Res.fail(f"宗·summary: {e}")

    def 取(self, category: Optional[str] = None,
           name: Optional[str] = None,
           workers: int = 4,
           dry_run: bool = False) -> Res:
        """取源码. category/name/全部 三选一."""
        try:
            z = self._load()
            results = z.取(category=category, name=name,
                          workers=workers, dry_run=dry_run)
            ok_n = sum(1 for r in results if r.ok and not r.skipped)
            skip_n = sum(1 for r in results if r.skipped)
            fail_n = sum(1 for r in results if not r.ok)
            return Res.succ(data={
                "ok": ok_n, "skip": skip_n, "fail": fail_n,
                "total": len(results),
                "results": [
                    {"name": r.name, "category": r.category,
                     "ok": r.ok, "skipped": r.skipped,
                     "size_mb": r.size_mb, "reason": r.reason}
                    for r in results
                ],
            })
        except Exception as e:
            return Res.fail(f"宗·取: {e}")

    fetch = 取

    def 取_all(self, workers: int = 4, **kw) -> Res:
        return self.取(workers=workers, **kw)

    fetch_all = 取_all

    def 查(self, keyword: str) -> Res:
        """按名/标签/描述查. 返 [{name, category, path, present, size_mb, tags}...]."""
        try:
            z = self._load()
            return Res.succ(data=z.查(keyword))
        except Exception as e:
            return Res.fail(f"宗·查: {e}")

    query = 查

    def 索(self) -> Res:
        """重建 MASTER_INDEX.json."""
        try:
            z = self._load()
            idx = z.索()
            return Res.succ(data={
                "total_indexed": len(idx.get("by_name", {})),
                "categories": list(idx.get("by_category", {}).keys()),
                "tags": len(idx.get("by_tag", {})),
            })
        except Exception as e:
            return Res.fail(f"宗·索: {e}")

    index = 索

    def 路径(self, name: str) -> Res:
        """查某仓的本地路径 (若已取)."""
        try:
            z = self._load()
            hits = z.查(name)
            exact = [h for h in hits if h["name"].lower() == name.lower()]
            if exact:
                return Res.succ(data=exact[0])
            if hits:
                return Res.succ(data=hits[0], warnings=["非精确匹配"])
            return Res.fail(f"未知仓: {name}")
        except Exception as e:
            return Res.fail(f"宗·路径: {e}")

    path_of = 路径


# ═══════════════════════════════════════════════════════════════════════════
# ⑮ Dao — 總門面 · 單例 · 懶加載
# ═══════════════════════════════════════════════════════════════════════════
class Dao:
    """萬法歸一·單一入口.

    屬性皆懶加載. 首次訪問時 import+實例化, 後續直取緩存.
    """

    _instance: Optional["Dao"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_once()
        return cls._instance

    def _init_once(self):
        self._t0 = time.time()
        self._caps: Dict[str, Any] = {}  # facet 緩存

    # ─── 屬性式懶加載 (facet) ────────────────────────────────────────────
    @property
    def 反(self) -> _ReverseFacet:
        return self._caps.setdefault("反", _ReverseFacet())

    reverse = 反  # English alias (via descriptor 不行, 用屬性 function)

    @property
    def 秀(self) -> _ShowFacet:
        return self._caps.setdefault("秀", _ShowFacet())

    @property
    def 活体(self) -> _LiveFacet:
        return self._caps.setdefault("活体", _LiveFacet())

    live = 活体

    @property
    def 核(self) -> _KernelFacet:
        return self._caps.setdefault("核", _KernelFacet())

    kernel = 核

    @property
    def 审(self) -> _AuditFacet:
        return self._caps.setdefault("审", _AuditFacet())

    audit = 审

    @property
    def 验(self) -> _VerifierFacet:
        return self._caps.setdefault("验", _VerifierFacet())

    verifier = 验

    @property
    def 循(self) -> _LoopFacet:
        return self._caps.setdefault("循", _LoopFacet())

    loop = 循

    @property
    def 运动(self) -> _KinematicsFacet:
        return self._caps.setdefault("运动", _KinematicsFacet())

    kinematics = 运动

    @property
    def 网格(self) -> _MeshFacet:
        return self._caps.setdefault("网格", _MeshFacet())

    mesh = 网格

    @property
    def 图纸(self) -> _DxfFacet:
        return self._caps.setdefault("图纸", _DxfFacet())

    dxf = 图纸

    @property
    def 文档(self) -> _DocxFacet:
        return self._caps.setdefault("文档", _DocxFacet())

    docx = 文档

    @property
    def 锻(self) -> _ForgeFacet:
        return self._caps.setdefault("锻", _ForgeFacet())

    forge = 锻

    @property
    def 执(self) -> _EngineFacet:
        return self._caps.setdefault("执", _EngineFacet())

    engine = 执

    @property
    def 感(self) -> _PerceptionFacet:
        return self._caps.setdefault("感", _PerceptionFacet())

    perception = 感
    perceive = 感

    @property
    def 宗(self) -> _ZongFacet:
        return self._caps.setdefault("宗", _ZongFacet())

    zong = 宗
    sources = 宗  # English alias (源码总摄)

    # ─── 意·面 (intent dispatcher) ──────────────────────────────────────
    def 意(self, text: str, mode: str = "auto", **kw) -> Res:
        """意念直達. 自動反向優先.

        mode:
          'auto'      — 自動判別: 先 反·外 → 無則 核·create
          'reverse'   — 強制 反·外
          'adapt'     — 強制 反·內 (需 path)
          'create'    — 強制 核·create (需 參數)
          'verify'    — 強制 審·full (需 shape/step)
        """
        t0 = time.time()
        if mode == "reverse" or mode == "auto":
            r = self.反.外(text, **kw)
            if mode == "reverse" or r.ok:
                r["elapsed_s"] = round(time.time() - t0, 3)
                r["route"] = "反·外"
                return r
        if mode == "adapt":
            path = kw.pop("path", None) or kw.pop("file", None)
            if not path:
                return Res.fail("adapt 需要 path 參數")
            patch = kw.pop("patch", None)
            r = self.反.内(path, patch=patch, **kw)
            r["elapsed_s"] = round(time.time() - t0, 3)
            r["route"] = "反·內"
            return r
        if mode == "verify":
            shape = kw.pop("shape", None)
            if shape is None:
                return Res.fail("verify 需要 shape 參數")
            r = self.审.full(shape, **kw)
            r["elapsed_s"] = round(time.time() - t0, 3)
            r["route"] = "審·full"
            return r
        # create / auto 回退
        return Res.succ(data={
            "hint": "意 未匹配到明確意圖. 可指定 mode='reverse'/'adapt'/'create'.",
            "text": text,
        }, elapsed_s=round(time.time() - t0, 3), route="none")

    intent = 意

    # ─── 系統匯總 ───────────────────────────────────────────────────────
    def summary(self) -> Dict[str, Any]:
        """快速狀態匯總 · 不觸發懶加載."""
        info = {
            "root": str(ROOT),
            "version": __version__,
            "layers": {k: str(v) for k, v in LAYERS.items()},
            "loaded_caps": list(self._caps.keys()),
            "uptime_s": round(time.time() - self._t0, 3),
        }
        # 探測 SW 活體 (只讀狀態, 不重連)
        try:
            info["sw_alive"] = self.活体.is_alive()
        except Exception as e:
            info["sw_alive"] = False
            info["sw_probe_error"] = str(e)[:200]
        # 探測 FC GUI
        try:
            from fc_show import FCShow
            info["fc_gui_alive"] = bool(FCShow.alive())
        except Exception:
            info["fc_gui_alive"] = False
        # 探測 宗 (源码总摄) 覆盖率
        try:
            info["zong"] = self.宗.summary().get("data", {})
        except Exception:
            info["zong"] = {}
        return info

    def manifest_path(self) -> Path:
        return ROOT / "万法清册.md"

    def __repr__(self):
        caps = ",".join(self._caps.keys()) or "∅"
        return f"<道 v{__version__} caps={caps}>"


# ═══════════════════════════════════════════════════════════════════════════
# ⑯ 全域單例 · `from 万法 import 道`
# ═══════════════════════════════════════════════════════════════════════════
道: Dao = Dao()


# ═══════════════════════════════════════════════════════════════════════════
# ⑰ CLI
# ═══════════════════════════════════════════════════════════════════════════
def _print_json(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _cli() -> int:
    import argparse
    ap = argparse.ArgumentParser(
        prog="万法",
        description="萬法歸一·3D建模Agent 單一入口",
    )
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("summary", help="系統狀態匯總")
    sub.add_parser("verify", help="萬法驗 (懶加載煙霧測)")
    sub.add_parser("manifest", help="打印清冊路徑")

    p_i = sub.add_parser("intent", help="意念直達")
    p_i.add_argument("text")
    p_i.add_argument("--mode", default="auto",
                     choices=["auto", "reverse", "adapt", "create", "verify"])

    p_r = sub.add_parser("reverse", help="反·外 · 天下搜索")
    p_r.add_argument("text")

    p_a = sub.add_parser("adapt", help="反·內 · 本地件改參重放")
    p_a.add_argument("path")
    p_a.add_argument("kv", nargs="*", help="k=v 參數對")

    p_s = sub.add_parser("show", help="秀於 FreeCAD GUI")
    p_s.add_argument("path")
    p_s.add_argument("--shots", nargs="*",
                     default=["iso", "front", "top", "right"])

    sub.add_parser("live", help="連 SolidWorks 活體")

    p_u = sub.add_parser("audit", help="八層審核 (STEP/BREP)")
    p_u.add_argument("path")

    p_z = sub.add_parser("zong", help="宗 · 第十四妙门 · 源码总摄")
    p_z.add_argument("action", choices=["summary", "fetch", "query", "index", "path"])
    p_z.add_argument("--category", help="限定宗类 (仅 fetch)")
    p_z.add_argument("--name", help="限定单仓 (fetch/path)")
    p_z.add_argument("--all", action="store_true", help="全取 (fetch)")
    p_z.add_argument("--workers", type=int, default=4)
    p_z.add_argument("--dry-run", action="store_true")
    p_z.add_argument("--keyword", help="查询关键字 (query)")

    args = ap.parse_args()

    if not args.cmd:
        ap.print_help()
        return 0

    if args.cmd == "summary":
        _print_json(道.summary())
        return 0

    if args.cmd == "verify":
        # 轉交 _万法验.py
        verify_py = ROOT / "30-验证_Verify" / "_万法验.py"
        if not verify_py.exists():
            print(f"未找到 {verify_py}")
            return 2
        import subprocess
        rc = subprocess.call([sys.executable, str(verify_py)])
        return rc

    if args.cmd == "manifest":
        mf = 道.manifest_path()
        print(str(mf))
        if mf.exists():
            print("─" * 60)
            print(mf.read_text(encoding="utf-8"))
        return 0 if mf.exists() else 2

    if args.cmd == "intent":
        r = 道.意(args.text, mode=args.mode)
        _print_json(r)
        return 0 if r.get("ok") else 1

    if args.cmd == "reverse":
        r = 道.反.外(args.text)
        _print_json(r)
        return 0 if r.get("ok") else 1

    if args.cmd == "adapt":
        patch: Dict[str, Any] = {}
        for tok in args.kv:
            if "=" in tok:
                k, v = tok.split("=", 1)
                # try float/int
                for cast in (int, float):
                    try:
                        v_cast = cast(v)
                        patch[k] = v_cast
                        break
                    except ValueError:
                        continue
                else:
                    patch[k] = v
        r = 道.反.内(args.path, patch=patch or None)
        _print_json(r)
        return 0 if r.get("ok") else 1

    if args.cmd == "show":
        r = 道.秀.live_show(args.path, shots=args.shots)
        _print_json(r)
        return 0 if r.get("ok") else 1

    if args.cmd == "live":
        r = 道.活体.summary()
        _print_json(r)
        return 0 if r.get("ok") else 1

    if args.cmd == "audit":
        # STEP 讀 + full_audit
        try:
            from dao_kernel import DaoKernel
            k = DaoKernel()
            if args.path.lower().endswith((".step", ".stp")):
                shape = k.import_step(args.path) if hasattr(k, "import_step") \
                    else None
            else:
                print(f"audit: 目前僅支援 .step/.stp")
                return 2
            if shape is None:
                print("audit: 無法載入 shape")
                return 2
            r = 道.审.full(shape)
            _print_json(r)
            return 0 if r.get("ok") else 1
        except Exception as e:
            print(f"audit: {e}")
            return 1

    if args.cmd == "zong":
        if args.action == "summary":
            _print_json(道.宗.summary())
            return 0
        if args.action == "fetch":
            if args.name:
                r = 道.宗.取(name=args.name, workers=1, dry_run=args.dry_run)
            elif args.category:
                r = 道.宗.取(category=args.category, workers=args.workers,
                           dry_run=args.dry_run)
            elif args.all:
                r = 道.宗.取_all(workers=args.workers, dry_run=args.dry_run)
            else:
                print("需指定 --name / --category / --all")
                return 2
            _print_json(r)
            return 0 if r.get("ok") else 1
        if args.action == "query":
            if not args.keyword:
                print("需指定 --keyword")
                return 2
            _print_json(道.宗.查(args.keyword))
            return 0
        if args.action == "index":
            _print_json(道.宗.索())
            return 0
        if args.action == "path":
            if not args.name:
                print("需指定 --name")
                return 2
            _print_json(道.宗.路径(args.name))
            return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
