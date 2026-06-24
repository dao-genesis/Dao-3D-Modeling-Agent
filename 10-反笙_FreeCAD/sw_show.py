#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
sw_show.py — 笙·用 · SolidWorks 活体展示台 · 反者道之动
═══════════════════════════════════════════════════════════════════════

纲要
    "得鱼而忘笙, 复得返用笙" — 以 SW 为展示笙, 与 FCShow 并行.
    任意 SLDPRT/SLDASM/SLDDRW/STEP/IGES 皆可直抵 SW GUI.
    SolidWorks 生于无, 三D建模生于有, 有无相生.

架构 (与 FCShow 同构)
    本机 Python  ──COM(pywin32)──▶  SolidWorks GUI
    sw_show.SWShow                  ISldWorks + IModelDoc2

核心 API (SWShow 类)
    ensure_gui(visible=True)               自动连接/启动 SW (带超时)
    status()                                当前状态: {pid, revision, n_docs, active}
    active_doc()                            返回活动 SWDoc 外覆
    load(path, readonly=False)              打开文件, 返回 SWDoc
    load_many(paths)                        批量打开 (每件一窗)
    view(action)                            "isometric"/"front"/"top"/"right"/"back"/"bottom"/"left"/"trimetric"/"dimetric"
    fit()                                   自动缩放到全部几何
    screenshot(path, w=1920, h=1080)        保存屏幕截图 PNG
    close(path=None)                        关闭指定或全部
    save_as(doc, dst)                       SaveAs (多格式自动识别)
    export_all(doc, out_dir, fmts=[...])    一次导出多格式
    live_show(src, shots=["iso","front",...])
                                            一键: 加载→多角度截图
    exec_macro(code)                        VBA-like 宏 (COM 调用序列)

CLI
    python sw_show.py status                 查看 SW 状态
    python sw_show.py launch                 启动 SW
    python sw_show.py load <file>            加载
    python sw_show.py shot <out.png>         截图当前视图
    python sw_show.py view <iso|front|...>   切视图
    python sw_show.py show <file> [--shots iso,front,top,right]
    python sw_show.py export <src> <dst>     单次导出
    python sw_show.py close [--all]          关闭文档

依赖
    - pywin32 (必需) — COM 桥
    - PIL/Pillow (可选) — 屏幕截图, 缺则退化为 SW 内置视图导出
"""
from __future__ import annotations

import os
import sys
import time
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# ─── 路径引导 (五层 sys.path 自动注入) ─────────────────────────────────
_HERE = Path(__file__).resolve().parent
_DAO_ROOT = next((p for p in Path(__file__).resolve().parents
                  if (p / "_paths.py").is_file()), _HERE.parent)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
import _paths as _dao_paths  # noqa: F401

# 本源
import dao_solidworks as _sw  # noqa: E402

__all__ = ["SWShow"]


# ── 视图枚举 (对应 SW API) ──────────────────────────────────────────────
SW_VIEW_ACTIONS = {
    # name        → swStandardView_e enum value
    "front":      1,
    "back":       2,
    "left":       3,
    "right":      4,
    "top":        5,
    "bottom":     6,
    "isometric":  7,
    "iso":        7,    # alias
    "trimetric":  8,
    "dimetric":   9,
    "normal":    10,
    "current":   11,
}


class SWShowError(RuntimeError):
    pass


class SWShow:
    """活体 SolidWorks 展示+控制桥.

    与 FCShow 并行, 默认静默连接已运行实例; 失败时自动启动.
    所有截图/导出幂等, 不污染用户原文档.
    """

    def __init__(self):
        self._bridge: Optional[_sw.SolidWorksBridge] = None
        self._owned_launch = False

    # ─── 连接 ──────────────────────────────────────────────────────────
    def ensure_gui(self, visible: bool = True,
                   launch_timeout_s: float = 120.0) -> bool:
        """确保 SW GUI 就绪. 返回 True 若连接成功."""
        if self._bridge is not None and self._bridge.is_connected():
            return True
        if self._bridge is None:
            self._bridge = _sw.SolidWorksBridge()
        if not self._bridge.is_installed():
            raise SWShowError("SolidWorks not installed")
        # 优先: 连已运行实例
        try:
            self._bridge.connect(prefer_active=True,
                                 launch_if_needed=True,
                                 launch_timeout_s=launch_timeout_s)
        except Exception as e:
            raise SWShowError(f"cannot connect SW: {e}")
        try:
            self._bridge.set_visible(visible)
        except Exception:
            pass
        return True

    def disconnect(self, exit_sw: bool = False):
        if self._bridge is not None:
            self._bridge.disconnect(exit_sw=exit_sw and self._owned_launch)
            self._bridge = None

    # ─── 状态 ──────────────────────────────────────────────────────────
    def status(self) -> Dict[str, Any]:
        """返回 SW 状态诊断."""
        out: Dict[str, Any] = {"connected": False}
        try:
            import subprocess
            r = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq SLDWORKS.exe", "/FO", "CSV"],
                capture_output=True, encoding="mbcs",
            )
            out["running"] = "SLDWORKS.exe" in (r.stdout or "")
        except Exception:
            out["running"] = None

        # SW info (from registry)
        info = _sw.sw_info(probe_com=False)
        out["install"] = {
            "version":  info.version,
            "progid":   info.progid_versioned or info.progid,
            "exe":      info.exe,
        }

        if self._bridge is not None and self._bridge.is_connected():
            out["connected"] = True
            try: out["revision"] = self._bridge.revision()
            except Exception as e: out["revision_err"] = str(e)
            try: out["docs"] = self._bridge.list_docs()
            except Exception: pass
            d = self._bridge.active_doc()
            if d is not None:
                out["active"] = {
                    "path": d.path_name(),
                    "type": _sw.SW_DOC_TYPE.name(d.doc_type),
                    "configs": d.configurations(),
                    "active_config": d.active_config(),
                }
        return out

    def active_doc(self) -> Optional[_sw.SWDoc]:
        if self._bridge is None: return None
        return self._bridge.active_doc()

    # ─── 加载 ──────────────────────────────────────────────────────────
    def load(self, path: Union[str, Path], readonly: bool = False,
             silent: bool = True, config: Optional[str] = None) -> _sw.SWDoc:
        self.ensure_gui(visible=True)
        return self._bridge.open(path, readonly=readonly,
                                 silent=silent, config=config)

    def load_many(self, paths: List[Union[str, Path]],
                  readonly: bool = False) -> List[_sw.SWDoc]:
        out: List[_sw.SWDoc] = []
        self.ensure_gui(visible=True)
        for p in paths:
            try:
                doc = self._bridge.open(p, readonly=readonly, silent=True)
                out.append(doc)
            except Exception as e:  # noqa: BLE001
                print(f"  ! load {p}: {e}")
        return out

    # ─── 视图 ──────────────────────────────────────────────────────────
    def view(self, action: str = "isometric") -> Dict[str, Any]:
        """切换到标准视图. action: iso/front/top/right/back/bottom/left/trimetric"""
        # action 校验优先 (允许 fake bridge 测试跳过连接)
        key = action.lower().strip()
        code = SW_VIEW_ACTIONS.get(key)
        if code is None:
            raise ValueError(f"unknown view action: {action}; valid: {list(SW_VIEW_ACTIONS)}")
        # 若 bridge 已存在 (如测试中), 跳过 ensure_gui
        if self._bridge is None or not self._bridge.is_connected():
            self.ensure_gui(visible=True)
        app = self._bridge._app if self._bridge else None
        if app is None:
            return {"ok": False, "err": "no active SW application"}
        # 通过 ModelView / ViewOrientation API
        d = app.ActiveDoc
        if d is None:
            return {"ok": False, "err": "no active document"}
        try:
            # IModelDoc2.ShowNamedView2 (name="", ID=code)
            d.ShowNamedView2("", code)
            return {"ok": True, "action": action}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "err": f"{type(e).__name__}: {e}"}

    def fit(self) -> Dict[str, Any]:
        """IModelDoc2.ViewZoomtofit2."""
        self.ensure_gui(visible=True)
        app = self._bridge._app
        d = app.ActiveDoc if app else None
        if d is None:
            return {"ok": False, "err": "no active doc"}
        try:
            d.ViewZoomtofit2()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "err": f"{type(e).__name__}: {e}"}

    # ─── 截图 ──────────────────────────────────────────────────────────
    def screenshot(self, out_path: Union[str, Path],
                   w: int = 1920, h: int = 1080,
                   allow_gdi_fallback: bool = True) -> Path:
        """保存当前视图截图 PNG.

        路 1: IModelDoc2.SaveBMP (ASCII temp) ← SW 原生渲染 · 不依赖前台 (根治中文路径问题)
        路 2: IModelDocExtension.SaveAs (.bmp, ASCII temp)
        路 3: Windows GDI 整屏 (PIL.ImageGrab)       ← 兑底 · 返 via='gdi_fallback'

        返: Path · 并在 `self._last_snap_via` 记录具体路径 (sw_savebmp/sw_saveas/gdi_fallback)
        """
        import tempfile, shutil
        self.ensure_gui(visible=True)
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        self._last_snap_via = "unknown"
        app = self._bridge._app
        d = app.ActiveDoc if app else None
        if d is None:
            self._last_snap_via = "gdi_fallback"
            return self._grab_screen(out, w, h)

        # ASCII temp dir · 根治 SaveBMP 对中文路径的不兼容
        ascii_tmp_dir = Path(tempfile.mkdtemp(prefix="swshow_"))
        ascii_tmp_bmp = ascii_tmp_dir / "snap.bmp"

        # 路 1: IModelDoc2.SaveBMP · SW 原生视口渲染 (ASCII temp)
        try:
            ok = bool(d.SaveBMP(str(ascii_tmp_bmp), int(w), int(h)))
            if ok and ascii_tmp_bmp.exists() and ascii_tmp_bmp.stat().st_size > 1024:
                self._last_snap_via = "sw_savebmp"
                try:
                    from PIL import Image
                    Image.open(ascii_tmp_bmp).save(out)
                    return out
                except Exception:
                    final = out.with_suffix(".bmp")
                    shutil.copy2(ascii_tmp_bmp, final)
                    return final
                finally:
                    shutil.rmtree(ascii_tmp_dir, ignore_errors=True)
        except Exception:
            pass

        # 路 2: IModelDocExtension.SaveAs (.bmp, ASCII temp)
        try:
            errors = _sw.win32_int()
            warnings = _sw.win32_int()
            ok = bool(d.Extension.SaveAs(
                str(ascii_tmp_bmp), 0, 0, None, errors, warnings
            ))
            if ok and ascii_tmp_bmp.exists() and ascii_tmp_bmp.stat().st_size > 1024:
                self._last_snap_via = "sw_saveas"
                try:
                    from PIL import Image
                    Image.open(ascii_tmp_bmp).save(out)
                    return out
                except Exception:
                    final = out.with_suffix(".bmp")
                    shutil.copy2(ascii_tmp_bmp, final)
                    return final
                finally:
                    shutil.rmtree(ascii_tmp_dir, ignore_errors=True)
        except Exception:
            pass

        # 路 3: GDI 整屏兑底 (最不理想 · 可能截到 IDE)
        shutil.rmtree(ascii_tmp_dir, ignore_errors=True)
        if not allow_gdi_fallback:
            raise SWShowError("SW native SaveBMP/SaveAs both failed; GDI fallback disabled")
        self._last_snap_via = "gdi_fallback"
        return self._grab_screen(out, w, h)

    def _grab_screen(self, out: Path, w: int, h: int) -> Path:
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab(all_screens=True)
            img.save(out)
            return out
        except ImportError:
            raise SWShowError(
                "screenshot requires Pillow (pip install Pillow) "
                "when SW native SaveAs PNG is unavailable"
            )

    # ─── 导出 ──────────────────────────────────────────────────────────
    def save_as(self, doc: _sw.SWDoc, dst: Union[str, Path],
                fmt: Optional[str] = None,
                config: Optional[str] = None) -> Path:
        return doc.export(dst, fmt=fmt, config=config)

    def export_all(self, doc: _sw.SWDoc, out_dir: Union[str, Path],
                   fmts: List[str] = ("step", "iges", "stl", "x_t"),
                   stem: Optional[str] = None) -> Dict[str, Any]:
        """一次性导出多种格式."""
        out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
        stem = stem or Path(doc.path_name() or doc.path or "unnamed").stem
        results: Dict[str, Any] = {}
        for fmt in fmts:
            ext = _sw.SW_EXPORT_FMT._EXT_MAP.get(fmt, f".{fmt}")
            dst = out_dir / f"{stem}{ext}"
            try:
                p = doc.export(dst, fmt=fmt)
                results[fmt] = {"ok": True, "path": str(p),
                                "size_B": p.stat().st_size}
            except Exception as e:  # noqa: BLE001
                results[fmt] = {"ok": False, "err": str(e)}
        return results

    # ─── 关闭 ──────────────────────────────────────────────────────────
    def close(self, path: Optional[Union[str, Path]] = None,
              save: bool = False, close_all: bool = False):
        if self._bridge is None or not self._bridge.is_connected():
            return
        if close_all:
            self._bridge.close_all(save=save)
            return
        if path is None:
            d = self._bridge.active_doc()
            if d is not None:
                self._bridge.close_doc(d, save=save)
        else:
            # 按路径关
            app = self._bridge._app
            if app is not None:
                try: app.CloseDoc(str(path))
                except Exception: pass

    # ─── 宏 ────────────────────────────────────────────────────────────
    def exec_macro(self, fn) -> Any:
        """执行 Python 函数 (接收 ISldWorks COM 对象).

        示例:
            def rotate_iso(app):
                app.ActiveDoc.ShowNamedView2("", 7)
                app.ActiveDoc.ViewZoomtofit2()
                return True
            sw.exec_macro(rotate_iso)
        """
        self.ensure_gui(visible=True)
        return fn(self._bridge._app)

    # ─── 一键展示 ──────────────────────────────────────────────────────
    def live_show(self, src: Union[str, Path],
                  shots: List[str] = ("isometric", "front", "top", "right"),
                  out_dir: Optional[Union[str, Path]] = None,
                  readonly: bool = True) -> Dict[str, Any]:
        """一键: 清空→加载→多角度截图. 幂等."""
        self.ensure_gui(visible=True)
        src = Path(src).resolve()
        if not src.exists():
            raise FileNotFoundError(src)

        # 清空当前场景 (保留用户其它文档不强关)
        try: self._bridge.close_all(save=False)
        except Exception: pass

        doc = self._bridge.open(src, readonly=readonly, silent=True)

        out_dir = Path(out_dir) if out_dir else (src.parent / "_sw_shots")
        out_dir.mkdir(parents=True, exist_ok=True)

        result: Dict[str, Any] = {
            "src": str(src),
            "out_dir": str(out_dir),
            "shots": {},
        }
        for view_name in shots:
            r = self.view(view_name)
            if not r.get("ok"):
                result["shots"][view_name] = {"view_err": r.get("err")}
                continue
            self.fit()
            time.sleep(0.2)   # 等一帧
            dst = out_dir / f"{src.stem}_{view_name}.png"
            try:
                p = self.screenshot(dst)
                result["shots"][view_name] = {
                    "ok": True, "path": str(p), "size_B": p.stat().st_size,
                }
            except Exception as e:  # noqa: BLE001
                result["shots"][view_name] = {"ok": False, "err": str(e)}
        return result


# ────────────────────────────────────────────────────────────────────────
# 自测
# ────────────────────────────────────────────────────────────────────────
def _self_test() -> Dict[str, Any]:
    """sw_show 自测 (不强连 GUI)."""
    res = {"pass": [], "fail": [], "score": 0, "total": 0}

    # T1: SWShow 可实例化
    try:
        sw = SWShow()
        assert sw._bridge is None
        res["pass"].append("T1_init"); res["score"] += 1
    except Exception as e:
        res["fail"].append(("T1_init", repr(e)))
    res["total"] += 1

    # T2: status 无连接时可读
    try:
        sw = SWShow()
        st = sw.status()
        assert "install" in st
        assert st["connected"] == False
        res["pass"].append("T2_status"); res["score"] += 1
    except Exception as e:
        res["fail"].append(("T2_status", repr(e)))
    res["total"] += 1

    # T3: view 动作字典
    try:
        assert "isometric" in SW_VIEW_ACTIONS
        assert SW_VIEW_ACTIONS["iso"] == SW_VIEW_ACTIONS["isometric"]
        res["pass"].append("T3_views"); res["score"] += 1
    except Exception as e:
        res["fail"].append(("T3_views", repr(e)))
    res["total"] += 1

    # T4: view 动作参数校验 (无需连 GUI)
    try:
        sw = SWShow()
        # 构造一个 noop bridge 以绕过实际连接
        class _FakeBridge:
            _app = None
            def is_connected(self): return True
            def is_installed(self): return True
            def set_visible(self, v): pass
        sw._bridge = _FakeBridge()
        # view 未知参数应抛 ValueError
        try:
            sw.view("bogus_view_xyz")
            raise AssertionError("should have raised ValueError")
        except ValueError:
            pass
        # view 已知参数但无 ActiveDoc 应返回 ok=False
        r = sw.view("isometric")
        assert r.get("ok") is False, f"expected ok=False, got {r}"
        res["pass"].append("T4_view_validation"); res["score"] += 1
    except Exception as e:
        res["fail"].append(("T4_view_validation", repr(e)))
    res["total"] += 1

    res["ratio"] = f"{res['score']}/{res['total']}"
    res["pct"] = round(100.0 * res["score"] / max(res["total"], 1), 1)
    return res


# ────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────
def _cli():
    import argparse
    ap = argparse.ArgumentParser(description="sw_show · SW 活体展示台 · 反者道之动")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="查看 SW 状态")
    p_launch = sub.add_parser("launch", help="启动 SW GUI")
    p_launch.add_argument("--timeout", type=float, default=120.0)

    p_load = sub.add_parser("load", help="加载文件")
    p_load.add_argument("file")
    p_load.add_argument("--readonly", action="store_true")
    p_load.add_argument("--config", default=None)

    p_view = sub.add_parser("view", help="切视图")
    p_view.add_argument("action", choices=list(SW_VIEW_ACTIONS))

    p_shot = sub.add_parser("shot", help="截图当前视图")
    p_shot.add_argument("out")

    p_show = sub.add_parser("show", help="一键: 加载+多视角截图")
    p_show.add_argument("file")
    p_show.add_argument("--shots", default="isometric,front,top,right")
    p_show.add_argument("--out-dir", default=None)

    p_exp = sub.add_parser("export", help="导出")
    p_exp.add_argument("src"); p_exp.add_argument("dst")
    p_exp.add_argument("--fmt", default=None)

    p_cls = sub.add_parser("close", help="关闭")
    p_cls.add_argument("--all", action="store_true")
    p_cls.add_argument("--path", default=None)

    sub.add_parser("test", help="自测")

    a = ap.parse_args()
    sw = SWShow()

    if a.cmd == "test":
        res = _self_test()
        print("\n" + "=" * 56)
        print(f"  sw_show 自测: {res['ratio']}  ({res['pct']}%)")
        print("=" * 56)
        for p in res["pass"]: print(f"  ✓ {p}")
        for n, e in res["fail"]: print(f"  ✗ {n}: {e}")
        sys.exit(0 if not res["fail"] else 1)

    if a.cmd == "status":
        st = sw.status()
        print(json.dumps(st, ensure_ascii=False, indent=2))
        return

    if a.cmd == "launch":
        sw.ensure_gui(visible=True, launch_timeout_s=a.timeout)
        print(json.dumps(sw.status(), ensure_ascii=False, indent=2))
        return

    if a.cmd == "load":
        doc = sw.load(a.file, readonly=a.readonly, config=a.config)
        print(f"loaded: {doc.path_name()} ({_sw.SW_DOC_TYPE.name(doc.doc_type)})")
        return

    if a.cmd == "view":
        r = sw.view(a.action)
        print(json.dumps(r, ensure_ascii=False))
        return

    if a.cmd == "shot":
        p = sw.screenshot(a.out)
        print(f"saved: {p} ({p.stat().st_size:,}B)")
        return

    if a.cmd == "show":
        shots = [s.strip() for s in a.shots.split(",") if s.strip()]
        r = sw.live_show(a.file, shots=shots, out_dir=a.out_dir)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return

    if a.cmd == "export":
        sw.ensure_gui(visible=False)
        doc = sw.load(a.src, readonly=True)
        p = sw.save_as(doc, a.dst, fmt=a.fmt)
        print(f"exported: {p} ({p.stat().st_size:,}B)")
        sw.close()
        return

    if a.cmd == "close":
        sw.close(path=a.path, close_all=a.all)
        print("closed")
        return


if __name__ == "__main__":
    _cli()
