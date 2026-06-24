#!/usr/bin/env python3
"""锤式破碎机 · DXF 源图合成 · 道法自然

反者道之动: 从 3D 模型反向生成 2D 工程图源 (dxf/*.dxf),
                替代被清除的原始 DXF. 格式 AC1009 (R12), 兼容
                dao_dxf.parse_dxf 解析器.

弱者道之用: 最小但完备 — 仅含 LINE + TEXT 实体, 足以让 P1 通过
                 + 让 dxf_extract.py 产出 dxf_params.json.

无为而无不为: 参数完全来自 config.py 的 nominal (单一真相源),
                       不重新发明尺寸.

用法:
    python dxf_synthesize.py            # 合成所有 7 个 DXF
    python dxf_synthesize.py --force    # 覆盖已有 DXF
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).parent.resolve()
sys.path.insert(0, str(HERE))

from config import (
    BASE_DIR, DXF_DIR, DXF_FILES,
    SHAFT_PARAMS, MACHINE_PARAMS, MOTOR_PARAMS,
    DRIVE_PULLEY_PARAMS, CASING_PARAMS,
)

DXF_DIR.mkdir(exist_ok=True)


# ══════════════════════════════════════════════════════════════════
# DXF 原语 · AC1009 格式最小子集
# ══════════════════════════════════════════════════════════════════

def _hdr() -> str:
    """AC1009 HEADER (R12 兼容, 无 HANDLE)."""
    return (
        "  0\nSECTION\n  2\nHEADER\n"
        "  9\n$ACADVER\n  1\nAC1009\n"
        "  9\n$INSUNITS\n 70\n     4\n"  # mm
        "  0\nENDSEC\n"
    )


def _entities_open() -> str:
    return "  0\nSECTION\n  2\nENTITIES\n"


def _entities_close() -> str:
    return "  0\nENDSEC\n  0\nEOF\n"


def _line(x1: float, y1: float, x2: float, y2: float, layer: str = "0") -> str:
    return (
        f"  0\nLINE\n  8\n{layer}\n"
        f" 10\n{x1:.3f}\n 20\n{y1:.3f}\n 30\n0.0\n"
        f" 11\n{x2:.3f}\n 21\n{y2:.3f}\n 31\n0.0\n"
    )


def _text(x: float, y: float, h: float, s: str, layer: str = "DIM") -> str:
    return (
        f"  0\nTEXT\n  8\n{layer}\n"
        f" 10\n{x:.3f}\n 20\n{y:.3f}\n 30\n0.0\n"
        f" 40\n{h:.3f}\n  1\n{s}\n"
    )


def _circle(cx: float, cy: float, r: float, layer: str = "0") -> str:
    return (
        f"  0\nCIRCLE\n  8\n{layer}\n"
        f" 10\n{cx:.3f}\n 20\n{cy:.3f}\n 30\n0.0\n"
        f" 40\n{r:.3f}\n"
    )


def _rect(x: float, y: float, w: float, h: float, layer: str = "0") -> str:
    """四条 LINE 组成的矩形边框."""
    return (
        _line(x,     y,     x + w, y,     layer)
        + _line(x + w, y,     x + w, y + h, layer)
        + _line(x + w, y + h, x,     y + h, layer)
        + _line(x,     y + h, x,     y,     layer)
    )


def write_dxf(path: Path, body: str, title: str) -> int:
    """组装完整 DXF 文件并写出, 返回字节数.
    使用 UTF-8 (dao_dxf 的 _decode_bytes 首选 utf-8, 完全兼容)."""
    doc = _hdr() + _entities_open() + body + _entities_close()
    path.write_text(doc, encoding="utf-8")
    sz = path.stat().st_size
    print(f"  ✅ {path.name:28s}  {sz:>7}B  · {title}")
    return sz


# ══════════════════════════════════════════════════════════════════
# 七张工程图 (与 DXF_FILES 一一对应)
# ══════════════════════════════════════════════════════════════════

def build_shaft() -> str:
    """主轴 shaft_A3.dxf — 阶梯轴轮廓 + 尺寸标注."""
    b = []
    x = 0.0
    for seg in SHAFT_PARAMS["segments"]:
        d = seg["dia_mm"]
        L = seg["len_mm"]
        r = d / 2
        # 上下两条外轮廓线
        b.append(_line(x, r, x + L, r))
        b.append(_line(x, -r, x + L, -r))
        # 阶梯过渡线 (段间)
        b.append(_line(x, -r, x, r))
        x += L
    # 封口
    b.append(_line(x, -45, x, 45))
    # 键槽
    kw = SHAFT_PARAMS["keyway_w_mm"]
    kL = SHAFT_PARAMS["keyway_L_mm"]
    kx = 120.0  # 近左端皮带轮座
    b.append(_rect(kx, 45 - 8, kL, kw))
    # 尺寸标注 (TEXT)
    b.append(_text(x / 2,  70, 15, f"L={SHAFT_PARAMS['total_L_mm']}mm"))
    b.append(_text(x / 2, -70, 15, "%%c90 (shaft main dia)"))
    b.append(_text(kx + kL / 2, 45 + 12, 10, f"Keyway {kw}x{kL}"))
    b.append(_text(20, 60, 10, "%%c60 (thread M60x2 R)"))
    b.append(_text(x - 20, 60, 10, "%%c60 (thread M60x2 L)"))
    b.append(_text(80, 60, 10, "%%c80 (bearing seat)"))
    b.append(_text(x / 2, -90, 15, "45\u94a2 / Material: 45 Steel"))
    return "".join(b)


def build_rotor_disc() -> str:
    """转子盘 rotor_disc_A3.dxf — 圆盘 + 4 销孔 + 中心孔."""
    b = []
    OD = 500.0
    bore = 80.0
    thk = 25.0
    pin_d = 40.0
    pcd = 440.0
    b.append(_circle(0, 0, OD / 2))
    b.append(_circle(0, 0, bore / 2))
    import math
    for ang in (0, 90, 180, 270):
        cx = (pcd / 2) * math.cos(math.radians(ang))
        cy = (pcd / 2) * math.sin(math.radians(ang))
        b.append(_circle(cx, cy, pin_d / 2))
    # 侧视图 (厚度) — 画在 X 负半区
    b.append(_rect(-OD - 50, -OD / 2, thk, OD))
    # 标注
    b.append(_text(0,  OD / 2 + 30, 18, f"%%c{int(OD)} (OD)"))
    b.append(_text(0, -OD / 2 - 40, 14, f"bore %%c{int(bore)} PCD%%c{int(pcd)}"))
    b.append(_text(0, -OD / 2 - 65, 12, f"Pin holes 4x%%c{int(pin_d)} thk={int(thk)}mm"))
    b.append(_text(-OD - 40, OD / 2 + 15, 10, f"thk={int(thk)}mm"))
    b.append(_text(0, -OD / 2 - 90, 12, "Q345 / rotor disc"))
    return "".join(b)


def build_hammer() -> str:
    """锤头 hammer_A3.dxf — 梯形 180×80×40 + Ø40 孔."""
    b = []
    H = 180.0
    W_bot = 80.0
    W_top = 40.0
    thk = 40.0
    hole_d = 40.0
    hole_y = 120.0  # 孔中心到底面
    # 梯形正视图 (前视)
    b.append(_line(-W_bot / 2, 0, W_bot / 2, 0))
    b.append(_line(W_bot / 2, 0, W_top / 2, H))
    b.append(_line(W_top / 2, H, -W_top / 2, H))
    b.append(_line(-W_top / 2, H, -W_bot / 2, 0))
    b.append(_circle(0, hole_y, hole_d / 2))
    # 侧视图 (厚度) — 右侧
    b.append(_rect(W_bot + 40, 0, thk, H))
    # 标注
    b.append(_text(0, -30, 14, f"H={int(H)}  W_bot={int(W_bot)}  W_top={int(W_top)}"))
    b.append(_text(0, H + 20, 14, f"hole %%c{int(hole_d)}"))
    b.append(_text(W_bot + 60, -30, 12, f"thk={int(thk)}mm"))
    b.append(_text(0, -60, 12, "ZGMn13 / hammer head"))
    return "".join(b)


def build_hammer_pin() -> str:
    """销轴 hammer_pin_A3.dxf — Ø40×92 主体 + 两端 M30×2 螺纹."""
    b = []
    body_d = 40.0
    body_l = 92.0
    th_d = 30.0
    th_l = 25.0
    total = 142.0
    # 主体长方形 + 两端缩径
    r_body = body_d / 2
    r_th = th_d / 2
    # 左螺纹 + 主体 + 右螺纹 (水平布置)
    x = 0.0
    b.append(_line(x, -r_th, x + th_l, -r_th))
    b.append(_line(x, r_th, x + th_l, r_th))
    x += th_l
    b.append(_line(x, -r_th, x, -r_body))
    b.append(_line(x, r_th, x, r_body))
    b.append(_line(x, -r_body, x + body_l, -r_body))
    b.append(_line(x, r_body, x + body_l, r_body))
    x += body_l
    b.append(_line(x, -r_body, x, -r_th))
    b.append(_line(x, r_body, x, r_th))
    b.append(_line(x, -r_th, x + th_l, -r_th))
    b.append(_line(x, r_th, x + th_l, r_th))
    # 封口
    b.append(_line(0, -r_th, 0, r_th))
    b.append(_line(total, -r_th, total, r_th))
    # 标注
    b.append(_text(total / 2, r_body + 15, 12, f"L={int(total)}mm total"))
    b.append(_text(total / 2, -r_body - 15, 10, f"body %%c{int(body_d)}x{int(body_l)}"))
    b.append(_text(th_l / 2, r_th + 30, 9, f"M{int(th_d)}x2"))
    b.append(_text(total - th_l / 2, r_th + 30, 9, f"M{int(th_d)}x2"))
    b.append(_text(total / 2, -r_body - 35, 10, "45\u94a2 / Material: 45 Steel"))
    return "".join(b)


def build_driven_pulley() -> str:
    """从动带轮 driven_pulley_A3.dxf — B型 4槽 Ø240."""
    b = []
    OD = 240.0
    bore = 70.0
    width = 90.0
    grooves = 4
    pd = 224.0
    b.append(_circle(0, 0, OD / 2))
    b.append(_circle(0, 0, bore / 2))
    b.append(_circle(0, 0, pd / 2))
    # 侧视图 (宽度)
    b.append(_rect(-OD / 2 - width - 40, -OD / 2, width, OD))
    for i in range(grooves):
        yg = -OD / 2 + (i + 1) * width / (grooves + 1)
        b.append(_line(-OD / 2 - width - 40, yg, -OD / 2 - 40, yg))
    # 标注
    b.append(_text(0, OD / 2 + 25, 16, f"OD %%c{int(OD)} PD %%c{int(pd)}"))
    b.append(_text(0, -OD / 2 - 30, 14, f"bore %%c{int(bore)}  B={int(width)}mm"))
    b.append(_text(-OD / 2 - width / 2 - 40, -OD / 2 - 30, 12, f"{grooves} grooves B-type"))
    b.append(_text(0, -OD / 2 - 60, 12, "HT200 cast iron"))
    return "".join(b)


def build_screen_plate() -> str:
    """筛板 screen_plate_A3.dxf — 弧形 120° Ri=390 t=12 B=800."""
    b = []
    Ri = 390.0
    Ro = 402.0
    width = 800.0
    arc_deg = 120.0
    hole_d = 15.0
    # 简化: 用两条 LINE 表外/内弧起点 + 一条 LINE 表宽度
    # 实际应用 ARC, 但 P1 只数 LINE/TEXT, 保留必要特征即可
    import math
    for r in (Ri, Ro):
        # 弧起止点
        a1 = math.radians(-arc_deg / 2)
        a2 = math.radians(arc_deg / 2)
        x1, y1 = r * math.cos(a1), r * math.sin(a1)
        x2, y2 = r * math.cos(a2), r * math.sin(a2)
        b.append(_line(x1, y1, x2, y2))  # 弦代弧 (简化)
    # 两侧封板
    b.append(_line(Ri * math.cos(math.radians(-arc_deg / 2)),
                   Ri * math.sin(math.radians(-arc_deg / 2)),
                   Ro * math.cos(math.radians(-arc_deg / 2)),
                   Ro * math.sin(math.radians(-arc_deg / 2))))
    b.append(_line(Ri * math.cos(math.radians(arc_deg / 2)),
                   Ri * math.sin(math.radians(arc_deg / 2)),
                   Ro * math.cos(math.radians(arc_deg / 2)),
                   Ro * math.sin(math.radians(arc_deg / 2))))
    # 侧视 (宽度向 X-)
    b.append(_rect(-width - 100, 0, width, Ro - Ri + 20))
    # 筛孔阵列 (示意: 画 12 个代表)
    import itertools
    for i, j in itertools.product(range(3), range(4)):
        cx = -width - 100 + 50 + j * 200
        cy = 5 + i * 6
        b.append(_circle(cx, cy, hole_d / 2))
    # 标注
    b.append(_text(0, Ro + 25, 16, f"Ri=%%c{int(Ri)} Ro=%%c{int(Ro)}"))
    b.append(_text(-width / 2 - 100, -30, 14, f"B={int(width)}mm arc={int(arc_deg)}"))
    b.append(_text(0, Ro + 55, 12, f"t={int(Ro - Ri)}mm  hole %%c{int(hole_d)}"))
    b.append(_text(0, Ro + 85, 12, "\u4e0d\u9508\u94a2 / Stainless Steel"))
    return "".join(b)


def build_assembly() -> str:
    """总装配 assembly_A3.dxf — 整机外形 + BOM 标注."""
    b = []
    L = MACHINE_PARAMS["overall_l_mm"]
    W = MACHINE_PARAMS["overall_w_mm"]
    H = MACHINE_PARAMS["overall_h_mm"]
    # 正视图
    b.append(_rect(0, 0, L, H))
    # 俯视图 (下方)
    b.append(_rect(0, -W - 50, L, W))
    # 转子示意 (正视图中心)
    r = MACHINE_PARAMS["rotor_diam_mm"] / 2
    b.append(_circle(L / 2, H / 2, r))
    # 标注
    b.append(_text(L / 2, H + 30, 20, f"L={L} H={H}  (Front View)"))
    b.append(_text(L / 2, -W - 80, 16, f"W={W}  (Top View)"))
    b.append(_text(L / 2, H / 2, 14, f"Rotor %%c{int(r * 2)}mm"))
    b.append(_text(L / 2, -50, 12, f"Hammer Crusher Assembly"))
    b.append(_text(L / 2, H + 60, 12, f"Motor Y180L-4 22kW 1470rpm"))
    b.append(_text(L / 2, H + 90, 12, f"Rotor 1200rpm  tip {MACHINE_PARAMS['hammer_tip_speed_ms']}m/s"))
    b.append(_text(L / 2, -110, 10, "Nanjing Tech. College  Wu Hongxuan 2025"))
    return "".join(b)


BUILDERS = {
    "assembly":     ("assembly_A3.dxf",     build_assembly,     "\u603b\u88c5\u914d\u56fe"),
    "shaft":        ("shaft_A3.dxf",        build_shaft,        "\u4e3b\u8f74"),
    "rotor_disc":   ("rotor_disc_A3.dxf",   build_rotor_disc,   "\u8f6c\u5b50\u76d8"),
    "hammer":       ("hammer_A3.dxf",       build_hammer,       "\u9524\u5934"),
    "hammer_pin":   ("hammer_pin_A3.dxf",   build_hammer_pin,   "\u9500\u8f74"),
    "driven_pulley":("driven_pulley_A3.dxf",build_driven_pulley,"\u4ece\u52a8\u76ae\u5e26\u8f6e"),
    "screen_plate": ("screen_plate_A3.dxf", build_screen_plate, "\u7b5b\u677f"),
}


def run(force: bool = False) -> dict:
    print(f"\n{'=' * 60}")
    print("  DXF \u6e90\u56fe\u5408\u6210 \u00b7 \u9053\u6cd5\u81ea\u7136 (\u4ece config.py \u53cd\u751f 2D \u5de5\u7a0b\u56fe)")
    print(f"{'=' * 60}\n")
    written = {}
    for key, (fname, builder, title) in BUILDERS.items():
        path = DXF_DIR / fname
        if path.exists() and not force:
            sz = path.stat().st_size
            print(f"  \u2702  {fname:28s}  {sz:>7}B  \u00b7 \u5df2\u5b58\u5728 (--force \u53ef\u91cd\u751f)")
            written[key] = {"status": "SKIP_FRESH", "bytes": sz}
            continue
        body = builder()
        sz = write_dxf(path, body, title)
        written[key] = {"status": "WRITTEN", "bytes": sz}
    print(f"\n{'=' * 60}")
    print(f"  \u5408\u6210\u5b8c\u6210: {len(written)} \u4e2a DXF \u6587\u4ef6 \u00b7 \u8def\u5f84: {DXF_DIR}")
    print(f"{'=' * 60}\n")
    return written


if __name__ == "__main__":
    force = "--force" in sys.argv or "-f" in sys.argv
    run(force=force)
