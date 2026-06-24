#!/usr/bin/env python3
"""
道 · Reverse — 反者道之动
═══════════════════════════════════════════════════════════════
反者道之动，弱者道之用。天下万物生于有，有生于无。

不从创造出发，从已有出发。
不从刚强出发，从柔弱出发。
不从自我出发，从天下出发。

最小化操作，最大化成果。无为而无不为。

Pipeline:
  意念 → 【反】→ 搜索天下已有 → 排序 → 下载 → 分析 → 最小适配 → 交付
       ↑                                                      ↓
       └──── 仅当天下无有，方从无到有 ←────────────────────────┘

Integration Layer:
  ┌─────────────────────────────────────────────────────────────┐
  │  资源探针.py  — 20平台 (HTTP + Playwright)                   │
  │  Tavily MCP   — 实时网络搜索 (技术/方法/教程)                 │
  │  GitHub MCP   — 代码搜索 (参数化方法/库)                     │
  │  dao_kernel.py— BREP分析与适配 (OCP/OCCT直连)               │
  │  trimesh      — 网格分析 (STL质量/尺寸/特征)                 │
  └─────────────────────────────────────────────────────────────┘

Usage:
  # CLI
  python dao_reverse.py search "phone stand adjustable"
  python dao_reverse.py search "gear module 1.5 20 teeth" --download
  python dao_reverse.py analyze downloads/printables_12345/model.stl
  python dao_reverse.py adapt downloads/model.stl --scale 1.2 --add-holes "M3 x4"
  python dao_reverse.py fulfill "raspberry pi case with fan mount"

  # API (for Cascade agent)
  from dao_reverse import DaoReverse
  plan = DaoReverse.fulfill("phone stand 70mm adjustable angle")
  # Returns: search results, best candidates, analysis, adaptation plan
"""

import os
import sys
import json
import time
import math
import tempfile
import concurrent.futures
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))

# ═══ 万法归一 · 路径引导 ════════════════════════════════════════════
_DAO_ROOT = next((p for p in Path(__file__).resolve().parents
                  if (p / '_paths.py').is_file()), SCRIPT_DIR.parent)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
import _paths as _dao_paths  # noqa: F401  (registers 五层 sys.path)
ROOT_DIR = _DAO_ROOT
# ═══════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════
# 反 · 意念解构 — 将自然语言拆解为搜索向量
# ═══════════════════════════════════════════════════════════

class IntentParser:
    """
    将设计意念解构为可搜索的多维向量。
    反者道之动 — 不从CAD操作出发，从人的原始需求出发。

    意念 = 功能词 + 几何约束 + 材料约束 + 制造约束
    """

    # 功能词 → 搜索关键词扩展映射
    FUNCTIONAL_EXPANSIONS = {
        # 中文 → 英文搜索词
        "支架": ["stand", "holder", "bracket", "mount"],
        "外壳": ["case", "enclosure", "housing", "shell"],
        "盒子": ["box", "container", "case"],
        "齿轮": ["gear", "cog", "pinion"],
        "轴承": ["bearing", "bushing"],
        "夹具": ["clamp", "clip", "gripper", "jig"],
        "连接器": ["connector", "adapter", "coupler", "joint"],
        "风扇": ["fan", "blower", "duct"],
        "散热": ["heatsink", "cooler", "thermal"],
        "铰链": ["hinge", "pivot", "living hinge"],
        "卡扣": ["snap fit", "clip", "latch"],
        "螺丝": ["screw", "bolt", "fastener"],
        "垫片": ["washer", "spacer", "shim"],
        "管道": ["pipe", "tube", "duct", "fitting"],
        "把手": ["handle", "knob", "grip"],
        "托盘": ["tray", "organizer", "caddy"],
        "架子": ["shelf", "rack", "stand"],
        "挂钩": ["hook", "hanger", "holder"],
        "灯罩": ["lampshade", "light cover", "diffuser"],
        "花瓶": ["vase", "planter", "pot"],
        "手机": ["phone", "smartphone", "mobile"],
        "键盘": ["keyboard", "keycap", "keyswitch"],
        "树莓派": ["raspberry pi", "rpi"],
        "arduino": ["arduino", "uno", "nano", "esp32"],
    }

    # 几何约束模式
    DIMENSION_PATTERNS = [
        # "70mm", "70 mm", "70毫米"
        (r'(\d+(?:\.\d+)?)\s*(?:mm|毫米)', 'mm'),
        (r'(\d+(?:\.\d+)?)\s*(?:cm|厘米)', 'cm'),
        (r'(\d+(?:\.\d+)?)\s*(?:m(?:eter)?(?!m)|米)', 'm'),
        (r'(\d+(?:\.\d+)?)\s*(?:in(?:ch)?|英寸|")', 'inch'),
    ]

    # 螺丝/孔规格
    FASTENER_PATTERNS = [
        (r'M(\d+(?:\.\d+)?)', 'metric_thread'),      # M3, M4, M5
        (r'#(\d+)', 'unc_thread'),                     # #6, #8
        (r'(\d+(?:\.\d+)?)\s*(?:孔|hole)', 'hole_dia'),
    ]

    # 制造方法
    MFG_KEYWORDS = {
        "3d打印": "fdm", "fdm": "fdm", "sla": "sla", "resin": "sla",
        "cnc": "cnc", "铣削": "cnc", "车削": "lathe",
        "激光切割": "laser", "laser": "laser",
        "注塑": "injection", "钣金": "sheet_metal",
    }

    @classmethod
    def parse(cls, intent: str) -> Dict[str, Any]:
        """
        解构意念为多维搜索向量。

        Returns:
            {
                "raw": "原始意念",
                "search_terms": ["phone stand", "phone holder", ...],
                "dimensions": [{"value": 70, "unit": "mm"}],
                "fasteners": [{"type": "metric_thread", "size": 3}],
                "manufacturing": "fdm",
                "functional_keywords": ["stand", "adjustable"],
                "geometric_keywords": ["角度", "可调"],
            }
        """
        import re
        result = {
            "raw": intent,
            "search_terms": [],
            "dimensions": [],
            "fasteners": [],
            "manufacturing": None,
            "functional_keywords": [],
            "geometric_keywords": [],
        }

        text = intent.lower().strip()

        # 1. 提取尺寸约束
        for pattern, unit in cls.DIMENSION_PATTERNS:
            for match in re.finditer(pattern, text):
                val = float(match.group(1))
                if unit == 'cm':
                    val *= 10; unit = 'mm'
                elif unit == 'm':
                    val *= 1000; unit = 'mm'
                elif unit == 'inch':
                    val *= 25.4; unit = 'mm'
                result["dimensions"].append({"value": val, "unit": "mm"})

        # 2. 提取紧固件规格
        for pattern, ftype in cls.FASTENER_PATTERNS:
            for match in re.finditer(pattern, text):
                result["fasteners"].append({
                    "type": ftype,
                    "size": float(match.group(1)),
                })

        # 3. 提取制造方法
        for kw, method in cls.MFG_KEYWORDS.items():
            if kw in text:
                result["manufacturing"] = method
                break

        # 4. 功能词扩展 — 双向匹配: 中文→英文, 英文→英文
        for zh_key, en_terms in cls.FUNCTIONAL_EXPANSIONS.items():
            if zh_key in text:
                result["functional_keywords"].extend(en_terms)
            else:
                for en in en_terms:
                    if en.lower() in text:
                        result["functional_keywords"].extend(en_terms)
                        break
        # 去重
        result["functional_keywords"] = list(dict.fromkeys(result["functional_keywords"]))
        # 也把原始英文词加入（如 adjustable）
        en_words_raw = re.findall(r'[a-zA-Z][a-zA-Z0-9_-]{2,}', text)
        for w in en_words_raw:
            if w not in result["functional_keywords"] and len(w) > 3:
                result["functional_keywords"].append(w)

        # 5. 生成搜索词组合
        # 先直接用原始意念
        result["search_terms"].append(intent)

        # 提取英文词
        en_words = re.findall(r'[a-zA-Z][a-zA-Z0-9_-]+', text)
        if en_words:
            result["search_terms"].append(" ".join(en_words))

        # 功能词组合
        if result["functional_keywords"]:
            # 取前2个功能词与英文词组合
            for fn_kw in result["functional_keywords"][:3]:
                combined = " ".join(en_words + [fn_kw]) if en_words else fn_kw
                if combined not in result["search_terms"]:
                    result["search_terms"].append(combined)

        # 加尺寸上下文
        if result["dimensions"] and result["functional_keywords"]:
            dim_str = f'{result["dimensions"][0]["value"]:.0f}mm'
            for fn_kw in result["functional_keywords"][:2]:
                term = f"{fn_kw} {dim_str}"
                if term not in result["search_terms"]:
                    result["search_terms"].append(term)

        # 去重
        seen = set()
        unique = []
        for t in result["search_terms"]:
            key = t.lower().strip()
            if key and key not in seen:
                seen.add(key)
                unique.append(t)
        result["search_terms"] = unique[:8]  # 最多8个搜索词

        return result


# ═══════════════════════════════════════════════════════════
# 反 · 天下搜索 — 同时搜索20平台+GitHub+Web
# ═══════════════════════════════════════════════════════════

class WorldSearch:
    """
    彻底连接网络万法。
    天下皆知美之为美 — 搜索一切已知的美。
    """

    # Playwright平台不能在线程池中并行 — 它们共享浏览器进程
    _PW_PLATFORMS = {"thangs_pw", "grabcad_pw", "yeggi_pw", "stlfinder_pw",
                     "mmf_pw", "nih_pw", "3d66"}
    # 需要token但通常未设置的平台 — 降低优先级
    _TOKEN_PLATFORMS = {"thingiverse"}
    # HTTP平台 — 可安全并行 (排除需token的mmf/thangs/thingiverse)
    _FAST_HTTP_PLATFORMS = [
        "printables", "sketchfab", "cults3d", "nasa",
        "stlfinder", "yeggi", "mohou", "nih",
    ]

    _platforms_cache = None
    # 自适应健康表 — 记住哪些平台活着，动态跳过死的
    # {platform_name: (last_ok_time, fail_count)}
    _health = {}
    _FAIL_COOLDOWN = 300  # 平台失败后冷却5分钟再试

    @classmethod
    def _is_alive(cls, platform: str, now: float = None) -> bool:
        """平台是否可用。连续失败≥2次则冷却一段时间。随波逐流，唯变所适。"""
        if platform not in cls._health:
            return True  # 未测试过，先假设可用
        last_time, fail_count = cls._health[platform]
        if fail_count < 2:
            return True  # 偶尔失败不影响
        now = now or time.time()
        # 冷却时间随失败次数指数增长: 5min, 10min, 20min...
        cooldown = cls._FAIL_COOLDOWN * min(8, 2 ** (fail_count - 2))
        return (now - last_time) > cooldown

    @classmethod
    def _load_platforms(cls) -> tuple:
        """延迟加载资源探针平台注册表 — 只加载一次"""
        if cls._platforms_cache is not None:
            return cls._platforms_cache
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "resource_probe", SCRIPT_DIR / "资源探针.py"  # 同层 00-本源_Origin
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            cls._platforms_cache = (mod.PLATFORMS, mod.ALL_SEARCH_PLATFORMS)
            return cls._platforms_cache
        except Exception as e:
            print(f"  ✗ 资源探针加载失败: {e}")
            return {}, []

    @classmethod
    def search_all_platforms(cls, query: str, limit: int = 10,
                             platforms: List[str] = None,
                             parallel: bool = True,
                             timeout: int = 15) -> List[Dict]:
        """
        在所有平台并行搜索。柔弱胜刚强 — 广撒网，轻触达。
        HTTP平台并行, Playwright平台串行(避免浏览器冲突)。
        任何单平台失败静默跳过 — 水善利万物而不争。

        Returns: [{platform, id, name, url, likes, downloads, ...}, ...]
        """
        PLATFORMS_DICT, ALL_PLATFORMS = cls._load_platforms()
        if not PLATFORMS_DICT:
            return []

        target_platforms = platforms or cls._FAST_HTTP_PLATFORMS
        # 过滤: 只搜存在的平台, 排除需token/Playwright/冷却中的
        now = time.time()
        target_platforms = [
            p for p in target_platforms
            if p in PLATFORMS_DICT
            and p not in cls._TOKEN_PLATFORMS
            and p not in cls._PW_PLATFORMS
            and cls._is_alive(p, now)
        ]

        all_results = []
        ok_count = 0
        err_count = 0

        # ── Phase 1: HTTP平台并行 ──
        if parallel and target_platforms:
            def _search_one(plat_name):
                client = PLATFORMS_DICT.get(plat_name)
                if not client or not hasattr(client, 'search'):
                    return plat_name, []
                try:
                    results = client.search(query, limit) or []
                    if results:
                        cls._health[plat_name] = (time.time(), 0)
                    return plat_name, results
                except Exception:
                    fc = cls._health.get(plat_name, (0, 0))[1] + 1
                    cls._health[plat_name] = (time.time(), fc)
                    return plat_name, []

            pool = concurrent.futures.ThreadPoolExecutor(max_workers=6)
            futures = {pool.submit(_search_one, p): p for p in target_platforms}
            try:
                for future in concurrent.futures.as_completed(futures, timeout=timeout):
                    try:
                        pname, results = future.result(timeout=3)
                        good = [r for r in results if isinstance(r, dict) and "error" not in r]
                        all_results.extend(good)
                        if good:
                            ok_count += 1
                        else:
                            err_count += 1
                    except Exception:
                        err_count += 1
            except (concurrent.futures.TimeoutError, KeyboardInterrupt):
                pass  # 部分平台超时 — 不影响已收集的结果
            finally:
                for f in futures:
                    f.cancel()
                pool.shutdown(wait=False, cancel_futures=True)
        elif not parallel:
            for plat_name in target_platforms:
                client = PLATFORMS_DICT.get(plat_name)
                if not client or not hasattr(client, 'search'):
                    continue
                try:
                    results = client.search(query, limit) or []
                    good = [r for r in results if isinstance(r, dict) and "error" not in r]
                    all_results.extend(good)
                    if good:
                        ok_count += 1
                except Exception:
                    err_count += 1

        # ── Phase 2: Playwright平台串行(可选, 仅在显式请求时) ──
        if platforms:
            pw_targets = [p for p in platforms if p in cls._PW_PLATFORMS and p in PLATFORMS_DICT]
            for plat_name in pw_targets:
                client = PLATFORMS_DICT.get(plat_name)
                if not client or not hasattr(client, 'search'):
                    continue
                try:
                    results = client.search(query, limit) or []
                    good = [r for r in results if isinstance(r, dict) and "error" not in r]
                    all_results.extend(good)
                    if good:
                        ok_count += 1
                except Exception:
                    err_count += 1

        if ok_count or err_count:
            print(f"  搜索完成: {ok_count}平台有结果, {err_count}平台无结果, 共{len(all_results)}条")

        return all_results

    @classmethod
    def search_multi_terms(cls, terms: List[str], limit_per_term: int = 8,
                           platforms: List[str] = None) -> List[Dict]:
        """
        多搜索词搜索，去重合并。
        为学日益为道日损 — 第一个词全量搜，后续词仅补缺。
        """
        all_results = []
        seen_ids = set()

        for i, term in enumerate(terms[:3]):
            # 第一个词全量搜，后续词减少请求量
            lim = limit_per_term if i == 0 else max(3, limit_per_term // 2)
            try:
                results = cls.search_all_platforms(
                    term, limit=lim, platforms=platforms
                )
            except Exception:
                results = []
            for r in results:
                uid = f"{r.get('platform', '')}_{r.get('id', '')}"
                if uid not in seen_ids:
                    seen_ids.add(uid)
                    r["_search_term"] = term
                    all_results.append(r)
            # 自适应终止: 够了就停，少了再试一轮
            if len(all_results) >= limit_per_term * 2:
                break  # 结果充足，不再浪费时间
            if i == 0 and not results:
                continue  # 第一轮零结果，再试一个词
            if i >= 1 and not results:
                break  # 连续两轮无结果，平台都不通，停
            # 如果第一个词已经找到足够结果, 不再搜后续词
            if len(all_results) >= limit_per_term * 2 and i == 0:
                break

        return all_results

    @classmethod
    def search_github_code(cls, query: str, language: str = "python",
                           limit: int = 10) -> List[Dict]:
        """
        GitHub代码搜索 — 搜索参数化建模方法/库/示例。
        不搜模型文件，搜建模代码（方法论层面的逆向）。
        """
        PLATFORMS_DICT, _ = cls._load_platforms()
        client = PLATFORMS_DICT.get("github")
        if client and hasattr(client, 'search_code'):
            try:
                return client.search_code(query, language, limit)
            except Exception:
                pass
        return []

    @classmethod
    def download_model(cls, platform: str, model_id: str,
                       out_dir: Path = None) -> List[str]:
        """
        下载模型文件。功成而弗居 — 下载即用，不留冗余。
        """
        PLATFORMS_DICT, _ = cls._load_platforms()
        out_dir = out_dir or (_dao_paths.WORLD / "downloads")
        client = PLATFORMS_DICT.get(platform)
        if not client or not hasattr(client, 'download'):
            return []
        try:
            return client.download(model_id, out_dir)
        except Exception as e:
            print(f"  ✗ 下载失败 [{platform}#{model_id}]: {e}")
            return []


# ═══════════════════════════════════════════════════════════
# 反 · 模型分析 — 理解已有模型的一切
# ═══════════════════════════════════════════════════════════

class ModelAnalyzer:
    """
    知其白守其黑 — 彻底理解已有模型的几何本质。
    """

    @staticmethod
    def analyze_stl(path: str) -> Dict[str, Any]:
        """
        STL完整分析: 尺寸/体积/质量/拓扑/质量评分。
        """
        import trimesh
        mesh = trimesh.load(path)
        if not isinstance(mesh, trimesh.Trimesh):
            return {"error": "非三角网格文件", "path": path}

        bb = mesh.bounding_box.extents
        result = {
            "path": str(path),
            "format": "STL",
            "vertices": len(mesh.vertices),
            "faces": len(mesh.faces),
            "bounding_box_mm": {
                "x": round(float(bb[0]), 2),
                "y": round(float(bb[1]), 2),
                "z": round(float(bb[2]), 2),
            },
            "volume_mm3": round(float(abs(mesh.volume)), 2) if mesh.is_watertight else None,
            "surface_area_mm2": round(float(mesh.area), 2),
            "is_watertight": bool(mesh.is_watertight),
            "center_of_mass": [round(float(c), 2) for c in mesh.center_mass] if mesh.is_watertight else None,
            "euler_number": int(mesh.euler_number),
        }

        # 质量评分
        score = 100
        if not mesh.is_watertight:
            score -= 40
        if mesh.euler_number != 2:
            score -= 20
        if len(mesh.faces) < 12:
            score -= 30
        result["quality_score"] = max(0, score)

        return result

    @staticmethod
    def analyze_step(path: str) -> Dict[str, Any]:
        """
        STEP完整分析: 拓扑/尺寸/体积/面类型。
        使用DaoKernel直连OCCT — 零中间层。
        """
        try:
            from dao_kernel import DaoKernel as K
            shape = K.from_step(path)
            if shape is None:
                return {"error": "STEP导入失败", "path": path}

            topo = K.count_topology(shape)
            bb = K.bounding_box(shape)
            vol = K.volume(shape)
            sa = K.surface_area(shape)
            com = K.center_of_mass(shape)

            # bb is dict: {min, max, size, center}
            sz = bb.get("size", (0, 0, 0))
            bb_min = bb.get("min", (0, 0, 0))
            bb_max = bb.get("max", (0, 0, 0))
            return {
                "path": str(path),
                "format": "STEP",
                "topology": topo,
                "bounding_box_mm": {
                    "x": round(sz[0], 2),
                    "y": round(sz[1], 2),
                    "z": round(sz[2], 2),
                    "min": [round(c, 2) for c in bb_min],
                    "max": [round(c, 2) for c in bb_max],
                },
                "volume_mm3": round(vol, 2),
                "surface_area_mm2": round(sa, 2),
                "center_of_mass": [round(c, 2) for c in com],
                "quality_score": 100,  # BREP = 精确
            }
        except ImportError:
            return {"error": "DaoKernel不可用", "path": path}
        except Exception as e:
            return {"error": str(e), "path": path}

    @classmethod
    def analyze(cls, path: str) -> Dict[str, Any]:
        """自动识别格式并分析。"""
        p = Path(path)
        ext = p.suffix.lower()
        if ext in ('.stl', '.obj', '.ply', '.off'):
            return cls.analyze_stl(str(p))
        elif ext in ('.step', '.stp'):
            return cls.analyze_step(str(p))
        else:
            return {"error": f"不支持的格式: {ext}", "path": str(p)}

    @classmethod
    def compare_to_intent(cls, analysis: Dict, intent: Dict) -> Dict[str, Any]:
        """
        将已有模型的分析结果与设计意念对比。
        返回: 匹配度 + 差异 + 适配建议。

        反者道之动 — 关注差异，最小化变更。
        """
        if "error" in analysis:
            return {"match_score": 0, "gaps": ["模型分析失败"], "adaptations": []}

        gaps = []
        adaptations = []
        match_score = 50  # 基础分 — 找到就有价值

        bb = analysis.get("bounding_box_mm", {})

        # 检查尺寸匹配
        if intent.get("dimensions"):
            model_dims = sorted([bb.get("x", 0), bb.get("y", 0), bb.get("z", 0)], reverse=True)
            for dim_spec in intent["dimensions"]:
                target = dim_spec["value"]
                # 找最接近的尺寸
                best_delta = min(abs(d - target) for d in model_dims) if model_dims else target
                ratio = best_delta / target if target > 0 else 1
                if ratio < 0.05:
                    match_score += 15
                elif ratio < 0.15:
                    match_score += 10
                    scale = target / min(model_dims, key=lambda d: abs(d - target)) if model_dims else 1
                    adaptations.append({
                        "type": "scale",
                        "reason": f"尺寸差 {best_delta:.1f}mm",
                        "action": f"缩放 {scale:.3f}x",
                        "scale_factor": round(scale, 4),
                    })
                else:
                    gaps.append(f"尺寸差距过大: 需要{target}mm, 模型最近尺寸差{best_delta:.1f}mm")

        # 检查紧固件
        if intent.get("fasteners"):
            for f in intent["fasteners"]:
                if f["type"] == "metric_thread":
                    adaptations.append({
                        "type": "add_holes",
                        "reason": f"需要M{f['size']}螺丝孔",
                        "action": f"钻M{f['size']}孔 (直径{f['size']}mm)",
                        "hole_diameter": f["size"],
                    })

        # 质量评分加成
        qs = analysis.get("quality_score", 0)
        if qs >= 90:
            match_score += 10
        elif qs >= 70:
            match_score += 5

        # 是否防水 (可制造)
        if analysis.get("is_watertight") or analysis.get("format") == "STEP":
            match_score += 10
        else:
            gaps.append("模型非水密 — 需修复才能制造")
            adaptations.append({
                "type": "repair",
                "reason": "非水密网格",
                "action": "trimesh自动修复",
            })

        match_score = min(100, max(0, match_score))

        return {
            "match_score": match_score,
            "gaps": gaps,
            "adaptations": adaptations,
            "verdict": (
                "直接可用" if match_score >= 85 and not gaps else
                "小幅适配" if match_score >= 60 else
                "大幅改造" if match_score >= 40 else
                "不适用 — 需从头构建"
            ),
        }


# ═══════════════════════════════════════════════════════════
# 反 · 结果排序 — 从天下万有中选最优
# ═══════════════════════════════════════════════════════════

class ResultRanker:
    """
    天下皆知美之为美 — 知何为最佳匹配。
    排序依据: 下载量 + 点赞 + 许可证 + 文件格式 + 关键词匹配。
    """

    # 许可证评分: 越开放越好
    LICENSE_SCORES = {
        "CC0": 100, "cc0": 100,
        "CC-BY": 90, "cc-by": 90, "CC BY": 90,
        "CC-BY-SA": 80, "cc-by-sa": 80, "CC BY-SA": 80,
        "MIT": 95, "Apache": 90, "BSD": 90,
        "GPL": 60, "gpl": 60,
        "CC-BY-NC": 50, "cc-by-nc": 50,
        "CC-BY-NC-SA": 40,
        "?": 30, "": 30,
    }

    @classmethod
    def rank(cls, results: List[Dict], intent: Dict) -> List[Dict]:
        """
        对搜索结果排序。返回按综合评分降序排列的结果。
        """
        for r in results:
            score = 0

            # 1. 下载量 (log scale, 最高30分)
            dl = r.get("downloads", 0)
            if dl > 0:
                score += min(30, int(math.log10(dl + 1) * 10))

            # 2. 点赞 (log scale, 最高20分)
            likes = r.get("likes", 0)
            if likes > 0:
                score += min(20, int(math.log10(likes + 1) * 8))

            # 3. 许可证 (最高15分)
            lic = r.get("license", "?")
            lic_score = 30  # default
            for k, v in cls.LICENSE_SCORES.items():
                if k.lower() in str(lic).lower():
                    lic_score = v
                    break
            score += int(lic_score * 0.15)

            # 4. 关键词匹配 (最高20分)
            name = (r.get("name") or "").lower()
            summary = (r.get("summary") or "").lower()
            text = name + " " + summary
            kw_hits = 0
            for kw in intent.get("functional_keywords", []):
                if kw.lower() in text:
                    kw_hits += 1
            score += min(20, kw_hits * 5)

            # 5. 平台信誉加成 (最高15分)
            platform_bonus = {
                "printables": 12, "grabcad": 12, "thangs": 10,
                "sketchfab": 8, "myminifactory": 8, "thingiverse": 8,
                "github": 10, "nasa": 15, "nih": 12,
                "cults3d": 7, "yeggi": 5, "stlfinder": 5,
            }
            score += platform_bonus.get(r.get("platform", ""), 3)

            # 6. 3D相关性过滤 — 非3D内容重罚
            url = r.get("url", "")
            if "images.nasa.gov" in url:
                score -= 30  # NASA图片库，非3D模型
            if kw_hits == 0 and dl == 0 and likes == 0:
                score -= 10  # 无任何匹配信号

            r["_relevance_score"] = max(0, score)

        results.sort(key=lambda r: r.get("_relevance_score", 0), reverse=True)
        return results


# ═══════════════════════════════════════════════════════════
# 反 · 适配引擎 — 最小变更实现意念
# ═══════════════════════════════════════════════════════════

class Adapter:
    """
    为而不恃，功成而弗居。
    最小化操作，仅做必要变更。
    """

    @staticmethod
    def scale_stl(path: str, factor: float, out: str = None) -> str:
        """均匀缩放STL"""
        import trimesh
        mesh = trimesh.load(path)
        mesh.apply_scale(factor)
        out = out or str(Path(path).with_stem(Path(path).stem + f"_scaled_{factor:.2f}"))
        mesh.export(out)
        return out

    @staticmethod
    def repair_stl(path: str, out: str = None) -> str:
        """修复非水密STL"""
        import trimesh
        mesh = trimesh.load(path)
        trimesh.repair.fix_normals(mesh)
        trimesh.repair.fill_holes(mesh)
        trimesh.repair.fix_winding(mesh)
        out = out or str(Path(path).with_stem(Path(path).stem + "_repaired"))
        mesh.export(out)
        return out

    @staticmethod
    def add_holes_step(path: str, holes: List[Dict], out: str = None) -> str:
        """
        在STEP模型上添加孔。使用DaoKernel直连OCCT。
        holes: [{"x": 10, "y": 0, "z": 0, "diameter": 3, "depth": 10}, ...]
        """
        try:
            from dao_kernel import DaoKernel as K
            shape = K.from_step(path)
            if shape is None:
                return ""
            for h in holes:
                hole_cyl = K.cylinder(
                    h["diameter"] / 2, h.get("depth", 100),
                    origin=(h["x"], h["y"], h.get("z", 0) - h.get("depth", 100) / 2),
                )
                shape = K.cut(shape, hole_cyl)
            out = out or str(Path(path).with_stem(Path(path).stem + "_with_holes"))
            if out.endswith('.step') or out.endswith('.stp'):
                K.to_step(shape, out)
            else:
                K.to_stl(shape, out)
            return out
        except ImportError:
            print("  ✗ DaoKernel不可用，无法执行STEP孔操作")
            return ""

    @staticmethod
    def scale_step(path: str, factor: float, out: str = None) -> str:
        """缩放STEP模型"""
        try:
            from dao_kernel import DaoKernel as K
            shape = K.from_step(path)
            if shape is None:
                return ""
            shape = K.scale(shape, factor)
            out = out or str(Path(path).with_stem(Path(path).stem + f"_scaled_{factor:.2f}"))
            K.to_step(shape, out)
            return out
        except ImportError:
            print("  ✗ DaoKernel不可用")
            return ""
        except Exception as e:
            print(f"  ✗ 缩放失败: {e}")
            return ""

    @classmethod
    def execute_adaptations(cls, path: str, adaptations: List[Dict],
                            out_dir: str = None) -> Dict[str, Any]:
        """
        执行适配计划。无为而无不为 — 仅做计划中的操作。
        """
        out_dir = Path(out_dir) if out_dir else Path(path).parent / "adapted"
        out_dir.mkdir(parents=True, exist_ok=True)

        current_path = path
        ext = Path(path).suffix.lower()
        log = []

        for adapt in adaptations:
            atype = adapt["type"]

            if atype == "scale":
                factor = adapt.get("scale_factor", 1.0)
                if abs(factor - 1.0) < 0.001:
                    continue
                if ext in ('.step', '.stp'):
                    result = cls.scale_step(current_path, factor,
                                            str(out_dir / f"scaled{ext}"))
                else:
                    result = cls.scale_stl(current_path, factor,
                                           str(out_dir / "scaled.stl"))
                if result:
                    current_path = result
                    log.append(f"✓ 缩放 {factor:.3f}x → {result}")

            elif atype == "repair":
                if ext in ('.stl', '.obj'):
                    result = cls.repair_stl(current_path,
                                            str(out_dir / "repaired.stl"))
                    if result:
                        current_path = result
                        log.append(f"✓ 修复 → {result}")

            elif atype == "add_holes":
                if ext in ('.step', '.stp'):
                    # 需要具体孔位 — 这里返回建议让Agent决定
                    log.append(f"⚠ 需要指定孔位: {adapt['reason']}")
                else:
                    log.append(f"⚠ STL无法精确开孔 — 建议转STEP后操作")

        return {
            "original": path,
            "result": current_path,
            "log": log,
            "adaptations_applied": len(log),
        }


# ═══════════════════════════════════════════════════════════
# 道 · 主编排器 — 反者道之动的完整流水线
# ═══════════════════════════════════════════════════════════

class DaoReverse:
    """
    道生一，一生二，二生三，三生万物。
    反者道之动 — 从万物回到道。

    完整流水线:
      意念 → 解构 → 搜索天下 → 排序 → 分析 → 适配计划 → 执行/交付

    Agent调用协议:
      plan = DaoReverse.fulfill("phone stand 70mm adjustable")
      # plan 包含: 搜索结果, 最佳候选, 分析, 适配方案, 建议
      # Agent根据plan决定: 直接用 / 适配 / 从头构建
    """

    @classmethod
    def fulfill(cls, intent_text: str,
                max_results: int = 30,
                download_top: int = 0,
                platforms: List[str] = None) -> Dict[str, Any]:
        """
        完整执行反向流水线。

        Args:
            intent_text: 自然语言设计意念
            max_results: 最大搜索结果数
            download_top: 自动下载前N个候选 (0=不下载)
            platforms: 指定平台列表 (None=全部)

        Returns:
            {
                "intent": {...},           # 解构后的意念
                "search_results": [...],   # 排序后的搜索结果
                "total_found": N,          # 总发现数
                "platforms_searched": N,   # 搜索的平台数
                "top_candidates": [...],   # 前5最佳候选 (含分析)
                "downloaded": [...],       # 已下载的文件路径
                "recommendation": "...",   # 最终建议
                "cascade_protocol": {...}, # Agent行动协议
            }
        """
        t0 = time.time()
        print(f"\n{'═' * 60}")
        print(f"  反者道之动 · 天下搜索")
        print(f"  意念: {intent_text}")
        print(f"{'═' * 60}\n")

        # 1. 解构意念
        print("【一 · 解构意念】")
        intent = IntentParser.parse(intent_text)
        print(f"  搜索词: {intent['search_terms']}")
        print(f"  尺寸约束: {intent['dimensions']}")
        print(f"  功能词: {intent['functional_keywords']}")
        print()

        # 2. 搜索天下
        print("【二 · 搜索天下】")
        all_results = WorldSearch.search_multi_terms(
            intent["search_terms"],
            limit_per_term=max(5, max_results // len(intent["search_terms"])),
            platforms=platforms,
        )
        print(f"  发现 {len(all_results)} 个模型")
        print()

        # 3. 排序
        print("【三 · 排序择优】")
        ranked = ResultRanker.rank(all_results, intent)
        top5 = ranked[:5]
        for i, r in enumerate(top5):
            print(f"  #{i+1} [{r.get('platform','')}] {r.get('name','?')[:50]}")
            print(f"      ↓{r.get('downloads',0)} ♥{r.get('likes',0)} "
                  f"评分:{r.get('_relevance_score',0)} {r.get('url','')[:60]}")
        print()

        # 4. 下载候选
        downloaded = []
        analyses = []
        if download_top > 0:
            print(f"【四 · 下载前{download_top}候选】")
            for r in top5[:download_top]:
                platform = r.get("platform", "")
                model_id = str(r.get("id", ""))
                if platform and model_id:
                    files = WorldSearch.download_model(platform, model_id)
                    downloaded.extend(files)
                    # 分析下载的文件
                    for f in files:
                        analysis = ModelAnalyzer.analyze(f)
                        comparison = ModelAnalyzer.compare_to_intent(analysis, intent)
                        analyses.append({
                            "file": f,
                            "analysis": analysis,
                            "comparison": comparison,
                        })
                        print(f"  分析: {Path(f).name}")
                        print(f"    尺寸: {analysis.get('bounding_box_mm', {})}")
                        print(f"    匹配度: {comparison['match_score']}  判定: {comparison['verdict']}")
            print()

        # 5. 生成建议
        elapsed = time.time() - t0
        recommendation = cls._generate_recommendation(
            intent, ranked, analyses, downloaded
        )

        # 6. 生成Agent行动协议
        cascade_protocol = cls._generate_cascade_protocol(
            intent, ranked, analyses
        )

        print(f"{'═' * 60}")
        print(f"  完成: {elapsed:.1f}s | 发现{len(all_results)}模型 | 下载{len(downloaded)}文件")
        print(f"  建议: {recommendation}")
        print(f"{'═' * 60}\n")

        return {
            "intent": intent,
            "search_results": ranked[:max_results],
            "total_found": len(all_results),
            "platforms_searched": len(set(r.get("platform") for r in all_results)),
            "top_candidates": [
                {
                    "rank": i + 1,
                    "platform": r.get("platform"),
                    "name": r.get("name"),
                    "url": r.get("url"),
                    "downloads": r.get("downloads", 0),
                    "likes": r.get("likes", 0),
                    "relevance_score": r.get("_relevance_score", 0),
                    "license": r.get("license"),
                }
                for i, r in enumerate(top5)
            ],
            "downloaded": downloaded,
            "analyses": analyses,
            "recommendation": recommendation,
            "cascade_protocol": cascade_protocol,
            "time_seconds": round(elapsed, 1),
        }

    @classmethod
    def _generate_recommendation(cls, intent, ranked, analyses, downloaded):
        """生成最终建议"""
        if not ranked:
            return "天下无有 — 需从无到有构建"

        best = ranked[0] if ranked else {}
        best_score = best.get("_relevance_score", 0)

        if analyses:
            best_analysis = max(analyses, key=lambda a: a["comparison"]["match_score"])
            match = best_analysis["comparison"]["match_score"]
            verdict = best_analysis["comparison"]["verdict"]
            if match >= 85:
                return f"直接可用: {Path(best_analysis['file']).name} (匹配{match}分)"
            elif match >= 60:
                n_adapt = len(best_analysis["comparison"]["adaptations"])
                return f"小幅适配: {Path(best_analysis['file']).name} ({n_adapt}项变更, 匹配{match}分)"

        if best_score >= 50:
            return (f"优质候选: [{best.get('platform')}] {best.get('name','?')[:40]} "
                    f"(↓{best.get('downloads',0)}) — 建议下载后分析")

        return "候选质量一般 — 建议结合已有模型与从头构建"

    @classmethod
    def _generate_cascade_protocol(cls, intent, ranked, analyses):
        """
        生成Cascade Agent行动协议。
        告诉Agent下一步该怎么做。
        """
        protocol = {
            "action": "build_from_scratch",  # default
            "confidence": 0,
            "steps": [],
            "resources": [],
        }

        if analyses:
            best = max(analyses, key=lambda a: a["comparison"]["match_score"])
            match = best["comparison"]["match_score"]

            if match >= 85:
                protocol["action"] = "use_directly"
                protocol["confidence"] = match
                protocol["steps"] = [
                    f"使用已下载模型: {best['file']}",
                    "验证尺寸是否满足要求",
                    "如需格式转换: forge_v3.py convert",
                ]

            elif match >= 60:
                protocol["action"] = "adapt_existing"
                protocol["confidence"] = match
                protocol["steps"] = [
                    f"基于已下载模型适配: {best['file']}",
                ] + [
                    f"执行: {a['action']} ({a['reason']})"
                    for a in best["comparison"]["adaptations"]
                ] + [
                    "验证适配结果",
                ]

            elif match >= 30:
                protocol["action"] = "reference_and_build"
                protocol["confidence"] = match
                protocol["steps"] = [
                    "参考已找到的模型结构和尺寸",
                    "使用DaoKernel从头构建",
                    "对比参考模型验证",
                ]

        elif ranked:
            best = ranked[0]
            if best.get("_relevance_score", 0) >= 40:
                protocol["action"] = "download_and_evaluate"
                protocol["confidence"] = 50
                protocol["steps"] = [
                    f"下载最佳候选: [{best.get('platform')}] {best.get('name','?')}",
                    f"URL: {best.get('url', '')}",
                    "分析模型尺寸和结构",
                    "评估是否可适配",
                ]
                protocol["resources"] = [
                    {"platform": best.get("platform"), "id": best.get("id"),
                     "name": best.get("name"), "url": best.get("url")}
                ]

        if protocol["action"] == "build_from_scratch":
            protocol["steps"] = [
                "天下无合适已有模型",
                "使用DaoKernel从意念直接构建",
                f"参考搜索词: {intent.get('search_terms', [])}",
            ]
            # 搜索GitHub代码作为参考
            if intent.get("functional_keywords"):
                kw = intent["functional_keywords"][0]
                protocol["steps"].append(
                    f"建议搜索GitHub代码: '{kw} cadquery OR build123d OR openscad'"
                )

        return protocol

    # ─── 便捷方法 ─────────────────────────────────

    @classmethod
    def search(cls, query: str, limit: int = 20,
               platforms: List[str] = None) -> List[Dict]:
        """快速搜索（不下载不分析）"""
        intent = IntentParser.parse(query)
        results = WorldSearch.search_multi_terms(
            intent["search_terms"], limit_per_term=limit,
            platforms=platforms,
        )
        return ResultRanker.rank(results, intent)

    @classmethod
    def analyze_local(cls, path: str, intent_text: str = "") -> Dict:
        """分析本地模型文件"""
        analysis = ModelAnalyzer.analyze(path)
        if intent_text:
            intent = IntentParser.parse(intent_text)
            comparison = ModelAnalyzer.compare_to_intent(analysis, intent)
            return {"analysis": analysis, "comparison": comparison}
        return {"analysis": analysis}

    @classmethod
    def adapt(cls, path: str, adaptations: List[Dict],
              out_dir: str = None) -> Dict:
        """执行适配"""
        return Adapter.execute_adaptations(path, adaptations, out_dir)


# ═══════════════════════════════════════════════════════════
# 道 · Agent指南 — Cascade行动手册
# ═══════════════════════════════════════════════════════════

AGENT_GUIDE = """
# 反者道之动 · Cascade Agent Protocol

## 核心原则
当收到任何3D建模需求时，**先反后正**:

### 第一步: 反 — 搜索天下已有
```python
from dao_reverse import DaoReverse
plan = DaoReverse.fulfill("用户的原始需求描述")
```

### 第二步: 判 — 根据plan决策
- plan.cascade_protocol.action == "use_directly" → 直接使用下载的模型
- plan.cascade_protocol.action == "adapt_existing" → 小幅适配
- plan.cascade_protocol.action == "reference_and_build" → 参考构建
- plan.cascade_protocol.action == "build_from_scratch" → 从头构建

### 第三步: 行 — 执行最小操作
- 直接使用: 仅做格式转换
- 小幅适配: 缩放/开孔/修复
- 参考构建: 以已有模型为蓝本，DaoKernel构建
- 从头构建: 完全使用DaoKernel

### 补充搜索 (通过MCP)
1. **Tavily MCP** — 搜索技术方法:
   `mcp8_tavily_search(query="parametric phone stand 3d model cadquery")`

2. **GitHub MCP** — 搜索代码:
   `mcp4_search_code(q="phone stand extension:scad OR extension:py cadquery")`

3. **Context7 MCP** — 查文档:
   `mcp1_query-docs(libraryId="/CadQuery/cadquery", query="phone stand parametric")`

### 黄金法则
- 天下有 → 用天下的
- 天下近 → 改天下的
- 天下无 → 才自己建
- 每一步都取最小操作
"""


# ═══════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(
        prog="dao_reverse",
        description="反者道之动 — 搜索天下已有，最小适配，无为而无不为",
    )
    sub = parser.add_subparsers(dest="cmd")

    # search
    p_s = sub.add_parser("search", help="搜索天下已有模型")
    p_s.add_argument("query", nargs="+", help="设计意念")
    p_s.add_argument("--limit", "-n", type=int, default=20)
    p_s.add_argument("--platform", "-p", help="指定平台 (逗号分隔)")
    p_s.add_argument("--save", "-s", help="保存结果到JSON")

    # fulfill (完整流水线)
    p_f = sub.add_parser("fulfill", help="完整反向流水线")
    p_f.add_argument("query", nargs="+", help="设计意念")
    p_f.add_argument("--download", "-d", type=int, default=0,
                     help="自动下载前N个候选 (默认0)")
    p_f.add_argument("--platform", "-p", help="指定平台")
    p_f.add_argument("--save", "-s", help="保存结果到JSON")

    # analyze
    p_a = sub.add_parser("analyze", help="分析本地模型文件")
    p_a.add_argument("path", help="模型文件路径 (STL/STEP)")
    p_a.add_argument("--intent", "-i", help="设计意念 (用于对比)")

    # adapt
    p_ad = sub.add_parser("adapt", help="适配模型")
    p_ad.add_argument("path", help="模型文件路径")
    p_ad.add_argument("--scale", type=float, help="缩放比例")
    p_ad.add_argument("--repair", action="store_true", help="修复网格")
    p_ad.add_argument("--out", "-o", help="输出目录")

    # guide
    sub.add_parser("guide", help="显示Agent行动手册")

    args = parser.parse_args()

    if args.cmd == "search":
        query = " ".join(args.query)
        platforms = args.platform.split(",") if args.platform else None
        results = DaoReverse.search(query, args.limit, platforms)
        print(f"\n搜索: '{query}'  发现 {len(results)} 个模型\n")
        for i, r in enumerate(results[:20]):
            print(f"  #{i+1:2d} [{r.get('platform',''):12s}] {r.get('name','?')[:45]}")
            print(f"       ↓{r.get('downloads',0):6d} ♥{r.get('likes',0):5d} "
                  f"评分:{r.get('_relevance_score',0):3d}  {r.get('url','')[:55]}")
        if args.save:
            Path(args.save).write_text(json.dumps(results, ensure_ascii=False, indent=2))
            print(f"\n保存 → {args.save}")

    elif args.cmd == "fulfill":
        query = " ".join(args.query)
        platforms = args.platform.split(",") if args.platform else None
        result = DaoReverse.fulfill(query, download_top=args.download,
                                    platforms=platforms)
        if args.save:
            Path(args.save).write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str))
            print(f"保存 → {args.save}")

    elif args.cmd == "analyze":
        result = DaoReverse.analyze_local(args.path, args.intent or "")
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.cmd == "adapt":
        adaptations = []
        if args.scale:
            adaptations.append({"type": "scale", "scale_factor": args.scale,
                                "reason": "用户指定", "action": f"缩放{args.scale}x"})
        if args.repair:
            adaptations.append({"type": "repair", "reason": "用户指定", "action": "修复网格"})
        if not adaptations:
            print("请指定至少一个适配操作: --scale / --repair")
            return
        result = DaoReverse.adapt(args.path, adaptations, args.out)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.cmd == "guide":
        print(AGENT_GUIDE)

    else:
        parser.print_help()
        print("\n" + "=" * 60)
        print("  反者道之动 · 柔弱胜刚强 · 无为而无不为")
        print("=" * 60)


if __name__ == "__main__":
    main()
