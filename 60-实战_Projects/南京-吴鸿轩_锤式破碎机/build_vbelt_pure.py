#!/usr/bin/env python3
"""
V带建模 - 纯Python (struct + math only, 无任何外部依赖)
直接写二进制STL, 道法自然
"""
import struct, math, json
from pathlib import Path
import sys

HERE = Path(__file__).parent.resolve()
sys.path.insert(0, str(HERE))
from config import OUT_DIR, VBELT_PARAMS, ASSEMBLY_POSITIONS

OUT_DIR.mkdir(exist_ok=True)

# 参数
R          = VBELT_PARAMS["driven_pd_mm"] / 2
BELT_H     = 11.0
BELT_TW    = 17.0        # 顶宽
BELT_BW    = 11.0        # 底宽
N_BELTS    = int(VBELT_PARAMS["qty"])
GROOVE_P   = 19.0
DRIVEN_CX  = float(ASSEMBLY_POSITIONS["driven_pulley"]["tx"])
N_SEG      = 72          # 圆周段数

OFFSETS = [GROOVE_P * (i - (N_BELTS-1)/2) for i in range(N_BELTS)]

print(f"V带参数: R={R}mm, H={BELT_H}mm, N={N_BELTS}, offsets={OFFSETS}")

def write_stl(path, triangles):
    """写二进制STL: triangles = list of (n, v0, v1, v2) 各为(x,y,z)元组"""
    with open(path, 'wb') as f:
        f.write(b'\x00' * 80)
        f.write(struct.pack('<I', len(triangles)))
        for n, v0, v1, v2 in triangles:
            f.write(struct.pack('<3f', *n))
            f.write(struct.pack('<3f', *v0))
            f.write(struct.pack('<3f', *v1))
            f.write(struct.pack('<3f', *v2))
            f.write(struct.pack('<H', 0))
    return len(triangles)

def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])

def sub(a, b):
    return (a[0]-b[0], a[1]-b[1], a[2]-b[2])

def norm(v):
    mag = math.sqrt(v[0]**2+v[1]**2+v[2]**2)
    if mag < 1e-10: return (0,0,1)
    return (v[0]/mag, v[1]/mag, v[2]/mag)

def tri_normal(v0, v1, v2):
    return norm(cross(sub(v1,v0), sub(v2,v0)))

def make_vbelt_triangles(x_center):
    """生成一条V带的所有三角形"""
    half_tw = BELT_TW / 2
    half_bw = BELT_BW / 2
    R_in    = R - BELT_H

    # 截面4点: (axial, radial) - 轴向偏移, 径向距离
    sec = [
        ( half_tw, R),     # A: 外-正轴
        (-half_tw, R),     # B: 外-负轴
        (-half_bw, R_in),  # C: 内-负轴
        ( half_bw, R_in),  # D: 内-正轴
    ]
    n_sec = len(sec)
    angles = [2*math.pi*i/N_SEG for i in range(N_SEG)]

    def pt(ai, si):
        ax, r_val = sec[si]
        a = angles[ai % N_SEG]
        return (x_center + ax, r_val*math.cos(a), r_val*math.sin(a))

    tris = []
    for ai in range(N_SEG):
        ai2 = (ai + 1) % N_SEG
        for si in range(n_sec):
            si2 = (si + 1) % n_sec
            v0 = pt(ai,  si)
            v1 = pt(ai,  si2)
            v2 = pt(ai2, si2)
            v3 = pt(ai2, si)
            n1 = tri_normal(v0, v1, v2)
            n2 = tri_normal(v0, v2, v3)
            tris.append((n1, v0, v1, v2))
            tris.append((n2, v0, v2, v3))
    return tris

all_tris = []
for i, xoff in enumerate(OFFSETS):
    xc = DRIVEN_CX + xoff
    t  = make_vbelt_triangles(xc)
    all_tris.extend(t)
    print(f"  V带{i+1}: x={xc:+.1f}mm, triangles={len(t)}")

p_all = OUT_DIR / "vbelt_all.stl"
n = write_stl(str(p_all), all_tris)
print(f"\n✅ {p_all}  ({n} triangles, {p_all.stat().st_size//1024}KB)")

# 单带
p1 = OUT_DIR / "vbelt_single.stl"
t1 = make_vbelt_triangles(DRIVEN_CX + OFFSETS[0])
write_stl(str(p1), t1)
print(f"✅ {p1}  ({len(t1)} triangles)")

res = {"vbelt_all": "OK", "n_triangles": n}
(OUT_DIR / "vbelt_results.json").write_text(
    json.dumps(res, indent=2), encoding="utf-8")
print("\n道法自然 · V带传动完整 ✓")
