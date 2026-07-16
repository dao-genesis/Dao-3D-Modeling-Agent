"""verify.* 核审门进入工具契约 — 纯 Python, 无 FreeCAD 依赖。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import tool_catalog


def test_verify_audit_is_curated():
    spec = tool_catalog.spec_for("verify.audit")
    assert spec["name"] == "verify.audit"
    assert spec["category"] == "verify"
    props = spec["parameters"]["properties"]
    assert "object" in props
    assert "vol_range" in props
    assert spec["parameters"]["required"] == ["object"]


def test_verify_group_in_catalog():
    cat = tool_catalog.build_catalog(["verify.audit", "solid.box"])
    groups = {g["group"]: g for g in cat["groups"]}
    assert "verify" in groups
    assert groups["verify"]["title"].startswith("核审")
    assert any(t["name"] == "verify.audit" for t in groups["verify"]["tools"])


def test_prompt_block_mentions_audit():
    block = tool_catalog.prompt_block(["verify.audit"])
    assert "verify.audit" in block
    assert "object*" in block
