"""
锤式破碎机 · DXF源文件参数提取
从7个DXF工程图自动提取几何特征：线段极值→零件尺寸 + TEXT注释→工程标注
道法自然 · 万法归宗

用法:
    python dxf_extract.py              # 提取所有DXF，输出到 output_cq/dxf_params.json
    python dxf_extract.py shaft        # 仅提取主轴

★ 反者道之动 (2026-04-18): DXF 解析与尺寸抽取底层 hoist 到
  00-本源_Origin/dao_dxf.py · 单一本源, 所有工程图通用.
"""
import sys, json, math, re
from pathlib import Path

# ═══ 万法归一 · 路径引导 (五层 sys.path 自动注入) ══════════════════
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
_DAO_ROOT = next((p for p in Path(__file__).resolve().parents
                  if (p / '_paths.py').is_file()), _HERE)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
import _paths as _dao_paths  # noqa: F401
from dao_dxf import parse_dxf as _dao_parse_dxf, parse_text_dims as _dao_parse_text_dims
# ═══════════════════════════════════════════════════════════════

from config import BASE_DIR, DXF_DIR, OUT_DIR, DXF_FILES


def parse_text_dims(texts: list) -> dict:
    """
    从DXF TEXT注释列表提取结构化工程尺寸 (兼容原 API).
    本源实现: dao_dxf.parse_text_dims.
    """
    ed = _dao_parse_text_dims(list(texts))
    return {
        "diameters_mm":  ed.diameters_mm,
        "lengths_mm":    ed.lengths_mm,
        "threads":       [{"major": int(t["major"]), "pitch": t["pitch"]} for t in ed.threads],
        "bare_nums":     ed.bare_nums,
        "all_dims":      ed.all_dims,
    }


def parse_dxf(path: Path) -> dict:
    """
    解析AC1009格式DXF文件, 返回兼容原 API 的 dict.
    本源实现: dao_dxf.parse_dxf (含 LINE / TEXT / CIRCLE / ARC 全类, 自动编码识别).
    """
    r = _dao_parse_dxf(path)
    bbox = None
    if r.bbox is not None:
        bbox = {
            "minx": round(r.bbox.minx, 3), "miny": round(r.bbox.miny, 3),
            "maxx": round(r.bbox.maxx, 3), "maxy": round(r.bbox.maxy, 3),
            "width":  round(r.bbox.width, 3), "height": round(r.bbox.height, 3),
        }
    return {
        "source":     r.source,
        "line_count": r.line_count,
        "text_count": r.text_count,
        "texts":      list(r.texts),
        "bbox":       bbox,
        "dims": {
            "top10_lengths":    r.lengths_top10,
            "top10_horizontal": r.horizontal_top10,
            "top10_vertical":   r.vertical_top10,
        },
    }


def extract_shaft(raw: dict) -> dict:
    """从主轴DXF推断关键参数"""
    bbox  = raw.get("bbox")
    texts = "\n".join(raw.get("texts", [])).upper()
    horiz = raw.get("dims", {}).get("top10_horizontal", [])
    vert  = raw.get("dims", {}).get("top10_vertical", [])
    return {
        "part": "main_shaft",
        "total_length_est":   round(bbox["width"] * 1145 / 268.35, 1) if (bbox and bbox.get("width")) else 1145,
        "max_radius_est":     round(max(horiz[:3]) if horiz else 19.2, 3),
        "keyway_noted":       "KEYWAY" in texts,
        "segment_x_coords":   vert[:8],
        "texts": raw.get("texts", []),
        "nominal": {"L": 1145, "D_max": 90, "D_mid": 80, "D_end": 60},
    }


def extract_rotor_disc(raw: dict) -> dict:
    horiz = raw.get("dims", {}).get("top10_horizontal", [])
    return {
        "part": "rotor_disc",
        "max_radius_est": round(max(horiz[:2]) if horiz else 250, 3),
        "texts": raw.get("texts", []),
        "nominal": {"OD": 500, "bore": 80, "thk": 25, "pin_holes": 4, "pin_pcd": 440},
    }


def extract_hammer(raw: dict) -> dict:
    horiz = raw.get("dims", {}).get("top10_horizontal", [])
    vert  = raw.get("dims", {}).get("top10_vertical", [])
    return {
        "part": "hammer",
        "height_est":  round(max(horiz[:2]) if horiz else 180, 3),
        "width_est":   round(max(vert[:2])  if vert  else 80,  3),
        "texts": raw.get("texts", []),
        "nominal": {"H": 180, "W_bot": 80, "W_top": 40, "thk": 40, "hole_d": 40, "hole_y": 120},
    }


def extract_hammer_pin(raw: dict) -> dict:
    vert  = raw.get("dims", {}).get("top10_vertical", [])
    horiz = raw.get("dims", {}).get("top10_horizontal", [])
    return {
        "part": "hammer_pin",
        "total_length_est": round(max(vert[:3]) if vert else 142, 3),
        "body_radius_est":  round(max(horiz[:2]) if horiz else 20, 3),
        "texts": raw.get("texts", []),
        "nominal": {"body_d": 40, "body_l": 92, "thread_d": 30, "thread_l": 25, "total_l": 142},
    }


def extract_driven_pulley(raw: dict) -> dict:
    horiz = raw.get("dims", {}).get("top10_horizontal", [])
    vert  = raw.get("dims", {}).get("top10_vertical", [])
    return {
        "part": "driven_pulley",
        "od_est":    round(max(horiz[:2]) if horiz else 120, 3),
        "width_est": round(max(vert[:2])  if vert  else 90,  3),
        "texts": raw.get("texts", []),
        "nominal": {"OD": 240, "bore": 70, "width": 90, "grooves": 4, "type": "B"},
    }


def extract_screen_plate(raw: dict) -> dict:
    horiz = raw.get("dims", {}).get("top10_horizontal", [])
    vert  = raw.get("dims", {}).get("top10_vertical", [])
    return {
        "part": "screen_plate",
        "width_est": round(max(vert[:2])  if vert  else 800, 3),
        "od_est":    round(max(horiz[:2]) if horiz else 201,  3),
        "texts": raw.get("texts", []),
        "nominal": {"Ri": 390, "Ro": 402, "thk": 12, "width": 800, "arc": 120, "hole_d": 15},
    }


EXTRACTORS = {
    "shaft":         extract_shaft,
    "rotor_disc":    extract_rotor_disc,
    "hammer":        extract_hammer,
    "hammer_pin":    extract_hammer_pin,
    "driven_pulley": extract_driven_pulley,
    "screen_plate":  extract_screen_plate,
}


def run(target: str = "all") -> dict:
    results = {}
    for key, path in DXF_FILES.items():
        if target != "all" and key != target:
            continue
        if not path.exists():
            print(f"  ⚠️  {key}: DXF不存在 ({path.name})")
            results[key] = {"error": "file_not_found"}
            continue
        raw = parse_dxf(path)
        extractor = EXTRACTORS.get(key)
        if extractor:
            info = extractor(raw)
        else:
            info = {"part": key, "raw": raw}
        info["parsed_dims"] = parse_text_dims(raw.get("texts", []))
        info["_raw_line_count"] = raw.get("line_count", 0)
        info["_raw_bbox"]       = raw.get("bbox")
        results[key] = info
        bbox_str = (f"bbox=({raw['bbox']['width']:.1f}×{raw['bbox']['height']:.1f})"
                    if raw.get("bbox") else "bbox=N/A")
        print(f"  ✅ {key}: {raw.get('line_count',0)} lines, {raw.get('text_count',0)} texts {bbox_str}")
        if raw["texts"]:
            for t in raw["texts"][:6]:
                print(f"      📝 {t}")
    return results


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    print(f"\n{'='*60}")
    print(f"  DXF参数提取 — 锤式破碎机 ({target})")
    print(f"{'='*60}\n")

    data = run(target)

    out_path = OUT_DIR / "dxf_params.json"
    out_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8"
    )
    print(f"\n  💾 已保存: {out_path}")
    print(f"\n{'='*60}")
    print(f"  提取完成! {len(data)} 个DXF文件")
    print(f"{'='*60}")
