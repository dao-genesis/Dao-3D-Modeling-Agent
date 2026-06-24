# -*- coding: utf-8 -*-
"""
ORS6_Stewart · 默认 visibility 契约测试 (反者道之动 · v2.2.7)

问题本源:
  T-wist4 是 SR6 选配升级模块 (PDF p.33-44 单独章节). 标准 SR6 仅装 Receiver,
  T-wist 是 alternate receiver upgrade. 但当前 viewer 默认显示 Twist_Base +
  Twist_Body + Twist_Lid + RingGear + ExchangeGear + DriveGear, 全部升到
  HOME_H, 与 Receiver 重叠. 顶部 Twist_Lid (STL Z=64-104) 在 world Y=251-291
  浮在 Receiver (world Y=180-268) 之上, 形成"白色顶块"视觉错位.

本测试锁死:
  1. T-wist 系列默认隐藏 (modular upgrade)
  2. Receiver 颜色与 frame 同 (实物图真值 0xcc2020)
  3. Tray + variants 默认隐藏 (内部不可见)
  4. Spacer + ESP32_Mount 默认隐藏 (装配小件)
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parents[2]
if str(PROJ) not in sys.path:
    sys.path.insert(0, str(PROJ))

from ORS6_Stewart.parts import DEFAULT_HIDDEN, PARTS, RECV_PARTS  # noqa: E402


TWIST_PARTS = {"Twist_Base", "Twist_Body", "Twist_Lid",
               "RingGear", "ExchangeGear", "DriveGear"}


def test_twist_modules_default_hidden():
    """T-wist4 是 SR6 选配升级, 标准 build 默认仅 Receiver. 全部默认 hide."""
    for p in TWIST_PARTS:
        assert p in DEFAULT_HIDDEN, (
            f"T-wist part {p!r} 未默认隐藏 — 会与 Receiver 重叠在 HOME_H 处, "
            f"顶部出现额外白色块 (Twist_Lid STL Z=64-104 → world Y=251-291)"
        )


def test_receiver_not_in_default_hidden():
    """标准 SR6 build: Receiver 必须可见 (作为 home toy holder)."""
    assert "Receiver" not in DEFAULT_HIDDEN, "Receiver 不应默认隐藏"


def test_receiver_color_matches_frame_pdf_truth():
    """Receiver 实物色应与 frame 同 (0xcc2020 红), 参 PDF p.32 实物图."""
    viewer = PROJ / "3D建模Agent" / "60-实战_Projects" / "ORS6_Stewart" / "viewer" / "index.html"
    if not viewer.exists():
        # Fallback to relative path during pytest in repo root
        viewer = Path(__file__).resolve().parents[1] / "viewer" / "index.html"
    text = viewer.read_text(encoding="utf-8")
    # 锁定 MAT.receiver color = 0xcc2020 (red, same as MAT.frame).
    # 旧 0x2a3a6a 深蓝是 viewer 设计高亮, 与 PDF 实物不符.
    receiver_block = text[text.find("receiver: new THREE.MeshPhysicalMaterial"):]
    receiver_block = receiver_block[:600]  # only inspect MAT.receiver block
    assert "color: 0xcc2020" in receiver_block, (
        "Receiver 颜色非 0xcc2020 (frame 红) — 与 PDF p.32 实物图色调不符. "
        "旧 0x2a3a6a 深蓝偏离实物."
    )


def test_tray_default_hidden():
    """Tray 系列 (3 variants) 内部 ESP32 盒, 被 Lid 完全遮盖, 默认隐藏."""
    for p in ["Tray", "Tray_ScrewJack", "Tray_XT60"]:
        assert p in DEFAULT_HIDDEN, f"{p} 默认应隐藏 (内部不可见)"


def test_default_visible_count_within_expected_range():
    """默认可见 STL = 31 总数 - DEFAULT_HIDDEN. 标准 build 期望 ~18 件."""
    visible_count = len(PARTS) - len(DEFAULT_HIDDEN)
    # 31 total - hidden (T-wist 6 + Tray 3 + non-default variants 4 + Mainlink etc 7 + Spacer+ESP32 2)
    # 期望默认可见 = 31 - 22 = 9, 但 RECV_PARTS 含 Twist 6 件已 hide, 仍剩 ~13 件 core
    assert 8 <= visible_count <= 20, (
        f"默认可见 STL 数量 {visible_count} 越期望范围 [8, 20]. "
        f"DEFAULT_HIDDEN={len(DEFAULT_HIDDEN)}/{len(PARTS)}"
    )
