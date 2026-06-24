"""
道 · Audit E2E Test — 八层审核系统完整端到端验证
"""
import sys, os, json, time
from pathlib import Path

# ═══ 万法归一 · 路径引导 ════════════════════════════════════════════
_DAO_ROOT = next((p for p in Path(__file__).resolve().parents
                  if (p / '_paths.py').is_file()), Path(__file__).resolve().parent.parent)
if str(_DAO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAO_ROOT))
import _paths as _dao_paths  # noqa: F401  (registers 五层 sys.path)
# ═══════════════════════════════════════════════════════════════════

from dao_kernel import DaoKernel as K, DaoPatterns as P
from dao_audit import (
    audit_topology, audit_geometry, audit_engineering,
    audit_format, audit_params, audit_intent, audit_perception,
    full_audit, heal_shape, _print_audit,
)


def _test_shape():
    """Create a test enclosure with holes and fillets."""
    body = P.enclosure(60, 40, 30, 2, fillet_r=2)
    h1 = K.cylinder(1.7, 50, origin=(20, 10, -25))
    h2 = K.cylinder(1.7, 50, origin=(-20, 10, -25))
    body = K.cut(K.cut(body, h1), h2)
    return body


def main():
    t0 = time.time()
    shape = _test_shape()
    results = []

    def check(name, fn):
        try:
            t = time.time()
            r = fn()
            dt = (time.time() - t) * 1000
            grade = r.get('grade', '?') if isinstance(r, dict) else '?'
            score = r.get('score', 0) if isinstance(r, dict) else 0
            results.append({"test": name, "ok": True, "grade": grade, "score": score, "ms": round(dt, 1)})
            print(f"  OK  {name:<30} {grade} ({score:.0f}) {dt:.0f}ms")
            return r
        except Exception as e:
            results.append({"test": name, "ok": False, "error": str(e)})
            print(f"  FAIL {name:<30} {e}")
            return None

    print("=" * 70)
    print("  道 · Audit — 八层审核系统 E2E 验证")
    print("=" * 70)

    # Layer 0-2, 4
    check("L0: Topology", lambda: audit_topology(shape))
    check("L1: Geometry", lambda: audit_geometry(shape))
    check("L2: Engineering (fdm)", lambda: audit_engineering(shape, process="fdm"))
    check("L2: Engineering (cnc)", lambda: audit_engineering(shape, process="cnc"))
    check("L4: Format", lambda: audit_format(shape))

    # Layer 5
    specs = {"volume_range": (10000, 20000), "bbox_L_range": (55, 65)}
    check("L5: Params (pass)", lambda: audit_params(shape, specs))
    specs_fail = {"volume_range": (1, 100)}
    check("L5: Params (fail)", lambda: audit_params(shape, specs_fail))

    # Layer 6
    intent = {
        "expected_genus": 0,
        "expected_faces_range": (8, 30),
        "expected_holes": 2,
        "volume_range": (10000, 20000),
        "key_features": [
            {"type": "hole", "diameter": 3.4, "tolerance": 0.5},
        ],
    }
    check("L6: Intent (pass)", lambda: audit_intent(shape, intent))
    intent_fail = {"expected_holes": 10, "volume_range": (1, 100)}
    check("L6: Intent (fail)", lambda: audit_intent(shape, intent_fail))

    # Layer 7
    perc = check("L7: Perception", lambda: audit_perception(shape))
    if perc:
        print(f"       symmetry={perc.get('symmetry')}, "
              f"stability={perc.get('stability', {}).get('assessment')}, "
              f"complexity={perc.get('visual_complexity')}")
        print(f"       affordances={perc.get('affordances')}")

    # Heal
    check("Heal", lambda: {"grade": "S", "score": 100, **heal_shape(shape)[1]})

    # Full audit
    print()
    full = check("Full 8-Layer Audit", lambda: full_audit(
        shape, name="audit_test_enclosure",
        intent=intent, process="fdm"))
    if full:
        print()
        _print_audit(full, verbose=True)
        print()
        for layer in full.get('layers', []):
            ln = layer.get('name', '?')
            lg = layer.get('grade', '?')
            ls = layer.get('score', 0)
            print(f"    Layer {layer['layer']}: {ln:<16} {lg} ({ls:.0f})")

    # Summary
    total = len(results)
    passed = sum(1 for r in results if r["ok"])
    failed = total - passed
    total_ms = (time.time() - t0) * 1000

    print()
    print("=" * 70)
    print(f"  {passed}/{total} passed | {failed} failed | {total_ms:.0f}ms")
    if failed == 0:
        print("  道法自然 — 八层审核系统验证通过")
    else:
        for r in results:
            if not r["ok"]:
                print(f"  FAIL: {r['test']}: {r.get('error', '?')}")
    print("=" * 70)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
