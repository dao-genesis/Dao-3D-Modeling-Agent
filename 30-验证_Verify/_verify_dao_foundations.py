#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_verify_dao_foundations.py · 本源五器自验证
════════════════════════════════════════════════════════════════════
反者道之动 —— 把 dao_mesh / dao_dxf / dao_docx / dao_verifier / dao_loop
          四下合一, 对锤式破碎机产出做一次独立、只用本源模块的验证.

本脚本证明: 项目脚本完全可以从 60-实战 撤出, 仅靠 00-本源 + 数据也能
立即完成"文档→工程图→模型→验证"全链路审查. 万法归宗.

Exit code: 0 = 无 fail/warn, 1 = 有 warn, 2 = 有 fail.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ═══ 万法归一 · 路径引导 ══════════════════════════════════════════
_DAO_ROOT = next((p for p in HERE.parents if (p / "_paths.py").is_file()), HERE.parent)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
import _paths as _dao_paths  # noqa: F401

from dao_mesh import read_mesh, is_stl_binary
from dao_dxf import parse_dxf
from dao_docx import open_docx, find_figure_captions, find_sections
from dao_verifier import Verifier
# ═══════════════════════════════════════════════════════════════

PROJECT = _dao_paths.PROJECTS / "南京-吴鸿轩_锤式破碎机"
OUT     = PROJECT / "output_cq"
DXF     = PROJECT / "dxf"

# 断言目标 (与项目 config.py · BBOX_SPEC_MM 同律)
# 注: hammer_pin 之 670 — 实物装配 "全跨4盘销轴" (BOM id=4 · "Ø40×670 全跨4盘 M30×2两端").
#     DXF 工程图 hammer_pin_A3.dxf 标 单段 Ø40×142 (单根标准件), 但本项目装配选用
#     一体贯穿之 670mm 销轴 (config.py · BBOX_SPEC_MM["hammer_pin"]·L_min=130 L_max=700).
#     验证以装配实情为准, 故取 670.
PART_BBOX_TARGETS = {
    # name          : (nominal_L, nominal_D, tolerance)
    "main_shaft":    (1145.0, 90.0, 2.0),
    "rotor_disc":    (500.0, 25.0, 2.0),    # OD, thk
    "hammer":        (180.0, 40.0, 2.0),    # H, t
    "hammer_pin":    (670.0, 40.0, 2.0),    # L 全跨, D 销径 (实物装配)
    "driven_pulley": (240.0, 90.0, 2.0),    # OD, B
    "screen_plate":  (800.0, 402.0, 5.0),   # B, Ro
}
PAPER_DOCX = PROJECT / "南京-吴鸿轩_v4_动平衡维护补充.docx"


def main() -> int:
    v = Verifier(
        title="dao 本源五器 · 锤式破碎机自验证",
        subtitle="只使用 00-本源_Origin 的模块, 脱离项目脚本独立审查",
    )

    # ── P1 · DXF 源 (dao_dxf) ─────────────────────────────────────
    with v.phase("P1 — DXF 工程图 (dao_dxf)") as ph:
        for dxf in sorted(DXF.glob("*.dxf")):
            r = parse_dxf(dxf)
            if r.line_count == 0 and r.text_count == 0:
                ph.warn(f"dxf/{dxf.stem}", f"空 DXF: {dxf.name}")
                continue
            w = r.bbox.width if r.bbox else 0.0
            ph.ok(f"dxf/{dxf.stem}",
                  f"{dxf.name}: {r.line_count} lines · {r.text_count} texts · "
                  f"W={w:.0f}mm · {len(r.dims.diameters_mm)} diameters")

    # ── P2 · 网格质量 (dao_mesh) ──────────────────────────────────
    with v.phase("P2 — STL/GLB 网格 (dao_mesh)") as ph:
        for name, (n1, n2, tol) in PART_BBOX_TARGETS.items():
            stl = OUT / f"{name}.stl"
            if not stl.exists():
                ph.warn(f"stl/{name}", f"{stl.name} 不存在")
                continue
            st = read_mesh(stl)
            if st is None:
                ph.fail(f"stl/{name}", f"无法解析 {stl.name}")
                continue
            bx, by, bz = st.bbox_size
            # Check: 最长边 ≈ n1, 次长或最短 ≈ n2 (宽松匹配)
            dims = sorted([bx, by, bz], reverse=True)
            ok_long  = abs(dims[0] - n1) <= tol
            ok_short = any(abs(d - n2) <= tol for d in dims[1:])
            status = "ok" if (ok_long and ok_short) else "warn"
            msg = (f"{st.faces} faces · bbox=({bx:.1f}, {by:.1f}, {bz:.1f}) "
                   f"· vol={st.volume/1e6:.2f}×10⁶mm³")
            getattr(ph, status)(f"stl/{name}", msg)

        # GLB 总装 (本源 GLB 读取器)
        glb = OUT / "assembly_complete_v4.glb"
        if glb.exists():
            st = read_mesh(glb)
            if st is None:
                ph.warn("glb/assembly_v4", "GLB 解析失败")
            else:
                ph.ok("glb/assembly_v4",
                      f"{st.faces} faces · bbox={tuple(round(s) for s in st.bbox_size)}mm "
                      f"· vol={st.volume/1e6:.1f}×10⁶mm³")

    # ── P3 · 论文文档 (dao_docx) ──────────────────────────────────
    with v.phase("P3 — 论文 docx (dao_docx)") as ph:
        if not PAPER_DOCX.exists():
            ph.warn("docx/v4", f"{PAPER_DOCX.name} 不存在")
        else:
            bundle = open_docx(PAPER_DOCX)
            ph.ok("docx/paragraphs", f"{len(bundle.paragraphs)} 段落")
            ph.ok("docx/images",     f"{len(bundle.images)} 图片 "
                                    f"(共 {sum(i.size_bytes for i in bundle.images)//1024}KB)")
            ph.ok("docx/tables",     f"{len(bundle.tables)} 表格")
            figs = find_figure_captions(bundle)
            secs = find_sections(bundle)
            ph.ok("docx/figures", f"{len(figs)} 图题")
            ph.ok("docx/sections", f"{len(secs)} 章节")
            # 关键图题必须包含 2.2 (整机结构)
            if any(f["fig_num"] == "图2.2" for f in figs):
                ph.ok("docx/fig2.2", "图2.2 (整机结构) 存在")
            else:
                ph.warn("docx/fig2.2", "图2.2 缺失")

    print("\n" + "─" * 60)
    print(f"  {v.summary_line()}")
    print("─" * 60 + "\n")
    v.dump_markdown(_dao_paths.LOGS / "dao_foundations_verify.md",
                    title_prefix="🜂 ")
    v.dump_json(_dao_paths.LOGS / "dao_foundations_verify.json")
    return v.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
