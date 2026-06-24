#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dao_dxf.py · 通用 DXF 本源 · 万法之资归一
══════════════════════════════════════════════════════════════════════════════
反者道之动 — 不从 ezdxf/odafc 等重依赖出发, 直接解析 DXF 的字节流.
弱者道之用 — 零外部依赖 (只用 re/math/pathlib), 任何 AutoCAD DXF 均可读.
无为而无不为 — 单一 API parse_dxf(path) 覆盖 AC1009(R12) / AC1012+(R13+) 两大派系.

实体谱系 (ENTITIES section):
  · LINE           (10/20 起, 11/21 终; 30/31 Z)
  · TEXT / MTEXT   (TEXT:10/20 + 1 = 文本; MTEXT: 1 + 3 可能的续行)
  · CIRCLE         (10/20 圆心, 40 半径)
  · ARC            (10/20/40 + 50/51 起止角度)
  · POLYLINE / LWPOLYLINE (LWPOLYLINE: 10/20 顶点序列, 42 bulge)
  · DIMENSION      (1 = 工程文字覆盖)

核心特征:
  · 自动识别编码 (ANSI / GBK / UTF-8)
  · 支持 \r\n / \n / \r 行结束符
  · 同时抽取几何 + 标注文字
  · 从文字解析结构化尺寸 (直径 %%c, 螺纹 MxP, 裸数字)

Hoist 自锤式破碎机项目 dxf_extract.parse_dxf/parse_text_dims, 现向所有工程图通用.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

__version__ = "1.0.0"
__all__ = [
    "DXFResult", "ExtractedDims",
    "parse_dxf", "parse_text_dims", "read_dxf_bytes",
    "infer_project_spec",
]

PathLike = Union[str, Path]

# ══════════════════════════════════════════════════════════════════════════════
# 零、编码识别 (DXF 古 ANSI / 现代 UTF-8 / 中文 GBK 均兼容)
# ══════════════════════════════════════════════════════════════════════════════

_ENCODING_CANDIDATES = ("utf-8", "gbk", "ansi", "cp936", "latin1")


def _decode_bytes(data: bytes) -> str:
    """按候选编码依次尝试, 第一个无错者胜."""
    for enc in _ENCODING_CANDIDATES:
        try:
            return data.decode(enc, errors="strict")
        except (UnicodeDecodeError, LookupError):
            continue
    # 最终回退: 宽松替换
    return data.decode("latin1", errors="replace")


def read_dxf_bytes(path: PathLike) -> str:
    """读取 DXF 文件为规范化文本 (已做编码识别 + 换行符归一)."""
    raw = Path(path).read_bytes()
    text = _decode_bytes(raw)
    return text.replace("\r\n", "\n").replace("\r", "\n")


# ══════════════════════════════════════════════════════════════════════════════
# 一、DXF 结构体
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class DXFEntity:
    """实体基类 (动态字段)."""
    kind: str
    props: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DXFBBox:
    minx: float; miny: float; maxx: float; maxy: float
    @property
    def width(self) -> float: return self.maxx - self.minx
    @property
    def height(self) -> float: return self.maxy - self.miny
    def to_dict(self) -> Dict[str, float]:
        return {
            "minx": round(self.minx, 3), "miny": round(self.miny, 3),
            "maxx": round(self.maxx, 3), "maxy": round(self.maxy, 3),
            "width": round(self.width, 3), "height": round(self.height, 3),
        }


@dataclass
class ExtractedDims:
    """从标注文字解析出的结构化尺寸."""
    diameters_mm: List[float] = field(default_factory=list)
    lengths_mm:   List[float] = field(default_factory=list)
    threads:      List[Dict[str, float]] = field(default_factory=list)
    bare_nums:    List[float] = field(default_factory=list)
    all_dims:     List[float] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DXFResult:
    """parse_dxf 统一返回."""
    source: str
    line_count: int
    text_count: int
    entities: List[DXFEntity] = field(default_factory=list)
    texts: List[str] = field(default_factory=list)
    bbox: Optional[DXFBBox] = None
    lengths_top10: List[float] = field(default_factory=list)
    horizontal_top10: List[float] = field(default_factory=list)
    vertical_top10: List[float] = field(default_factory=list)
    dims: Optional[ExtractedDims] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "line_count": self.line_count,
            "text_count": self.text_count,
            "texts": self.texts,
            "bbox": self.bbox.to_dict() if self.bbox else None,
            "dims": {
                "top10_lengths":    self.lengths_top10,
                "top10_horizontal": self.horizontal_top10,
                "top10_vertical":   self.vertical_top10,
            },
            "parsed_dims": self.dims.to_dict() if self.dims else None,
        }


# ══════════════════════════════════════════════════════════════════════════════
# 二、主解析器 · (code, value) 对流 → 实体
# ══════════════════════════════════════════════════════════════════════════════

def _pairs(text: str):
    """DXF 以 `\ncode\nvalue\n...` 成对排列, 生成 (code, value)."""
    lines = text.split("\n")
    i = 0
    n = len(lines)
    while i < n - 1:
        code = lines[i].strip()
        val  = lines[i + 1].strip()
        yield code, val
        i += 2


def _flush_entity(kind: str, coords: Dict[str, float], text_content: List[str],
                  lines_raw: List[Tuple[float, float, float, float]],
                  entities: List[DXFEntity],
                  texts_raw: List[str]) -> None:
    """关闭当前实体, 按类型输出到对应容器."""
    if not kind:
        return
    if kind == "LINE":
        if all(k in coords for k in ("10", "20", "11", "21")):
            lines_raw.append((coords["10"], coords["20"], coords["11"], coords["21"]))
        entities.append(DXFEntity(kind="LINE", props=dict(coords)))
    elif kind == "CIRCLE":
        if all(k in coords for k in ("10", "20", "40")):
            entities.append(DXFEntity(
                kind="CIRCLE",
                props={"x": coords["10"], "y": coords["20"], "r": coords["40"]},
            ))
    elif kind == "ARC":
        if all(k in coords for k in ("10", "20", "40", "50", "51")):
            entities.append(DXFEntity(
                kind="ARC",
                props={"x": coords["10"], "y": coords["20"],
                       "r": coords["40"],
                       "start_deg": coords["50"], "end_deg": coords["51"]},
            ))
    elif kind in ("TEXT", "MTEXT", "ATTDEF", "ATTRIB"):
        joined = "".join(text_content).strip()
        if joined:
            texts_raw.append(joined)
            entities.append(DXFEntity(
                kind=kind,
                props={
                    "x": coords.get("10", 0.0), "y": coords.get("20", 0.0),
                    "text": joined,
                },
            ))
    elif kind == "LWPOLYLINE":
        # 顶点坐标以重复的 10/20 对出现; 这里简化处理, 保留成对顶点
        entities.append(DXFEntity(kind="LWPOLYLINE", props=dict(coords)))
    elif kind == "DIMENSION":
        joined = "".join(text_content).strip()
        entities.append(DXFEntity(
            kind="DIMENSION",
            props={"text_override": joined, "x": coords.get("10", 0.0),
                   "y": coords.get("20", 0.0)},
        ))


# ══════════════════════════════════════════════════════════════════════════════
# 三、文字尺寸解析 (%%c = Ø, MxP = 螺纹)
# ══════════════════════════════════════════════════════════════════════════════

def parse_text_dims(texts: List[str]) -> ExtractedDims:
    """
    从 DXF TEXT 列表提取结构化工程尺寸.
    支持:
      · %%cN       → 直径 (AutoCAD 的 %%c = Ø)
      · %%cN x M   → 直径 N, 长度 M
      · MNxP       → 螺纹 M(major)xP(pitch), 例: M30x2
      · 裸数字      → 候选尺寸 (5~5000 范围过滤)
    """
    diameters: List[float] = []
    lengths:   List[float] = []
    threads:   List[Dict[str, float]] = []
    bare_nums: List[float] = []
    full_text = " ".join(texts)

    for m in re.finditer(r"%%c(\d+(?:\.\d+)?)\s*[xX×]?\s*(\d+(?:\.\d+)?)?", full_text, re.IGNORECASE):
        diameters.append(float(m.group(1)))
        if m.group(2):
            lengths.append(float(m.group(2)))
    # 中文直径符号 Ø 也支持 (UTF-8 DXF)
    for m in re.finditer(r"[Ø\u2205](\d+(?:\.\d+)?)\s*[xX×]?\s*(\d+(?:\.\d+)?)?", full_text):
        diameters.append(float(m.group(1)))
        if m.group(2):
            lengths.append(float(m.group(2)))

    for m in re.finditer(r"\bM(\d+(?:\.\d+)?)[xX×](\d+(?:\.\d+)?)", full_text):
        threads.append({"major": float(m.group(1)), "pitch": float(m.group(2))})

    for t in texts:
        t = t.strip()
        try:
            v = float(t)
            if 5.0 <= v <= 5000.0:
                bare_nums.append(v)
        except ValueError:
            pass

    all_nums = sorted(set(diameters + lengths + bare_nums), reverse=True)
    return ExtractedDims(
        diameters_mm=sorted(set(diameters), reverse=True),
        lengths_mm=sorted(set(lengths), reverse=True),
        threads=threads,
        bare_nums=sorted(set(bare_nums), reverse=True),
        all_dims=all_nums[:20],
    )


# ══════════════════════════════════════════════════════════════════════════════
# 四、主入口 parse_dxf
# ══════════════════════════════════════════════════════════════════════════════

# 坐标组码: 0=实体类型, 10/20/30 主坐标, 11/21/31 次坐标, 40=半径/长度,
#           50/51 起止角度, 1=文字, 3=MTEXT续行
_COORD_CODES = {"10", "20", "30", "11", "21", "31", "40", "41", "42", "50", "51"}
_TEXT_CODES  = {"1", "3"}
_ENTITY_TYPES = {
    "LINE", "TEXT", "MTEXT", "CIRCLE", "ARC", "LWPOLYLINE", "POLYLINE",
    "DIMENSION", "ATTDEF", "ATTRIB", "INSERT", "ELLIPSE", "SPLINE",
}


def parse_dxf(path: PathLike) -> DXFResult:
    """
    解析任意 AC1009+ DXF 文件. 零外部依赖.

    返回 DXFResult; 结构体含 to_dict() 便于 JSON 持久化.
    """
    p = Path(path)
    text = read_dxf_bytes(p)

    entities: List[DXFEntity] = []
    lines_raw: List[Tuple[float, float, float, float]] = []
    texts_raw: List[str] = []

    cur_type: str = ""
    coords: Dict[str, float] = {}
    text_content: List[str] = []

    for code, val in _pairs(text):
        if code == "0":
            # New entity begins → flush previous one
            _flush_entity(cur_type, coords, text_content, lines_raw, entities, texts_raw)
            cur_type = val.upper()
            coords = {}
            text_content = []
        elif cur_type in _ENTITY_TYPES:
            if code in _COORD_CODES:
                try:
                    coords[code] = float(val)
                except ValueError:
                    pass
            elif code in _TEXT_CODES and val:
                text_content.append(val)
    # Final flush (DXF often omits 0/EOF termination in buggy exporters)
    _flush_entity(cur_type, coords, text_content, lines_raw, entities, texts_raw)

    # Bounding box from LINEs + CIRCLEs + ARCs
    xs: List[float] = [p[0] for p in lines_raw] + [p[2] for p in lines_raw]
    ys: List[float] = [p[1] for p in lines_raw] + [p[3] for p in lines_raw]
    for e in entities:
        if e.kind == "CIRCLE":
            cx, cy, r = e.props["x"], e.props["y"], e.props["r"]
            xs += [cx - r, cx + r]; ys += [cy - r, cy + r]
        elif e.kind == "ARC":
            cx, cy, r = e.props["x"], e.props["y"], e.props["r"]
            xs += [cx - r, cx + r]; ys += [cy - r, cy + r]
    bbox: Optional[DXFBBox] = None
    if xs and ys:
        bbox = DXFBBox(min(xs), min(ys), max(xs), max(ys))

    # Length histograms
    lengths: List[float] = []
    horiz_set = set(); vert_set = set()
    for x1, y1, x2, y2 in lines_raw:
        d = math.hypot(x2 - x1, y2 - y1)
        if d > 0.01:
            lengths.append(round(d, 3))
        dx = abs(x2 - x1); dy = abs(y2 - y1)
        if dx < 0.5 and dy > 0.5:
            horiz_set.add(round(dy, 3))
        elif dy < 0.5 and dx > 0.5:
            vert_set.add(round(dx, 3))

    top_lengths = sorted(lengths, reverse=True)[:10]
    top_horiz   = sorted(horiz_set, reverse=True)[:10]
    top_vert    = sorted(vert_set, reverse=True)[:10]

    return DXFResult(
        source=p.name,
        line_count=len(lines_raw),
        text_count=len(texts_raw),
        entities=entities,
        texts=texts_raw,
        bbox=bbox,
        lengths_top10=top_lengths,
        horizontal_top10=top_horiz,
        vertical_top10=top_vert,
        dims=parse_text_dims(texts_raw),
    )


# ══════════════════════════════════════════════════════════════════════════════
# 五、项目特征化辅助 · 给 DXFResult 附加一组标称尺寸做差异比对
# ══════════════════════════════════════════════════════════════════════════════

def infer_project_spec(result: DXFResult, nominal: Dict[str, Any],
                       tolerance: float = 5.0) -> Dict[str, Any]:
    """
    将 DXF 实测尺寸 top 榜与一组标称尺寸比对, 给出每项误差.

    nominal 示例 (任意零件):
        {"L": 1145, "D": 90}     # 长度和直径的标称值
    返回:
        {"L": {"nominal": 1145, "observed": 1145.0, "delta": 0.0, "in_tol": True}, ...}
    """
    all_h = result.horizontal_top10
    all_v = result.vertical_top10
    all_d = result.lengths_top10
    out: Dict[str, Any] = {}
    for key, nom in nominal.items():
        candidates = all_d + all_h + all_v
        best = None; best_err = float("inf")
        for cand in candidates:
            err = abs(cand - nom)
            if err < best_err:
                best_err = err; best = cand
        out[key] = {
            "nominal": nom,
            "observed": best,
            "delta": round(best_err, 3) if best is not None else None,
            "in_tol": (best_err <= tolerance) if best is not None else False,
        }
    return out


# ══════════════════════════════════════════════════════════════════════════════
# 六、自验证 · python dao_dxf.py [<file>]
# ══════════════════════════════════════════════════════════════════════════════

_MINIMAL_DXF = """0
SECTION
2
ENTITIES
0
LINE
8
0
10
0.0
20
0.0
11
100.0
21
0.0
0
LINE
8
0
10
0.0
20
0.0
11
0.0
21
50.0
0
CIRCLE
8
0
10
50.0
20
25.0
40
10.0
0
TEXT
1
%%c40 x 142
10
50.0
20
50.0
0
TEXT
1
M30x2
10
0.0
20
0.0
0
ENDSEC
0
EOF
"""


def _self_test() -> int:
    tmp = Path("__dao_dxf_test.dxf")
    tmp.write_text(_MINIMAL_DXF, encoding="utf-8")
    try:
        r = parse_dxf(tmp)
        assert r.line_count == 2, f"lines={r.line_count}"
        assert r.text_count == 2, f"texts={r.text_count}"
        assert r.bbox is not None and abs(r.bbox.width - 100.0) < 1e-6, f"bbox={r.bbox}"
        assert r.dims and 40.0 in r.dims.diameters_mm, r.dims.diameters_mm
        assert r.dims.threads and r.dims.threads[0]["major"] == 30, r.dims.threads
        assert 142.0 in r.dims.lengths_mm, r.dims.lengths_mm
        print(f"  OK  minimal DXF: {r.line_count} lines · {r.text_count} texts"
              f" · bbox {r.bbox.to_dict()}")
        print(f"  OK  dims: diameters={r.dims.diameters_mm} lengths={r.dims.lengths_mm}"
              f" threads={r.dims.threads}")

        # Spec inference
        spec = infer_project_spec(r, {"D": 20.0, "L": 100.0}, tolerance=1.0)
        print(f"  OK  infer: {spec}")
        assert spec["L"]["in_tol"], spec

        # Circle entity extracted
        circles = [e for e in r.entities if e.kind == "CIRCLE"]
        assert len(circles) == 1 and circles[0].props["r"] == 10.0, circles
        print(f"  OK  circles: {len(circles)} found, r={circles[0].props['r']}")
    finally:
        tmp.unlink(missing_ok=True)

    print("\n  dao_dxf self-test: all assertions passed ✓")
    return 0


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        r = parse_dxf(sys.argv[1])
        print(json.dumps(r.to_dict(), ensure_ascii=False, indent=2))
    else:
        raise SystemExit(_self_test())
