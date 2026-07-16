"""code.* 代码化 CAD 语义层进入工具契约 — 纯 Python, 无 FreeCAD 依赖。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import tool_catalog


def test_code_run_is_curated():
    spec = tool_catalog.spec_for("code.run")
    assert spec["category"] == "code"
    assert spec["parameters"]["required"] == ["code"]
    assert "export" in spec["parameters"]["properties"]


def test_code_group_in_catalog():
    cat = tool_catalog.build_catalog(["code.run", "code.env"])
    groups = {g["group"]: g for g in cat["groups"]}
    assert "code" in groups
    assert "CadQuery" in groups["code"]["desc"]
    assert {t["name"] for t in groups["code"]["tools"]} == {"code.run", "code.env"}
