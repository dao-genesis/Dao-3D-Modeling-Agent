#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dao_docx.py · 通用 docx 本源 · 万法之资归一
══════════════════════════════════════════════════════════════════════════════
反者道之动 — docx = ZIP(XML); 不靠 python-docx 也能提尽文/图/表/关系.
弱者道之用 — 零外部依赖 (只用 zipfile/xml/re/base64).
无为而无不为 — 单一 API open_docx(path) 返回 DocxBundle, 直取所需.

提取维度:
  · 文本段落 (含 style / level, 保持文档顺序)
  · 嵌入媒体 (word/media/*, 原字节)
  · 关系映射 (rId → media file, rId → hyperlink target)
  · 文档中图片的实际出现顺序 (r:embed)
  · 图题 / 表题 / 章节标题 (按中文/英文常见模式)
  · 表格内容 (tbl > tr > tc > p > r > t)

非侵入写入支持 (可选): 使用 python-docx 时自动启用; 否则 read-only.
"""
from __future__ import annotations

import base64
import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from xml.etree import ElementTree as ET

__version__ = "1.0.0"
__all__ = [
    "DocxParagraph", "DocxImage", "DocxBundle",
    "open_docx", "extract_docx_texts", "extract_docx_images",
    "find_figure_captions", "find_table_captions", "find_sections",
    "data_uri",
]

PathLike = Union[str, Path]

# ══════════════════════════════════════════════════════════════════════════════
# 零、命名空间
# ══════════════════════════════════════════════════════════════════════════════
_W  = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_R  = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_A  = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_PIC = "{http://schemas.openxmlformats.org/drawingml/2006/picture}"

IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp",
            ".emf", ".wmf", ".svg"}
MIME_MAP = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".bmp": "image/bmp", ".webp": "image/webp",
    ".tiff": "image/tiff", ".svg": "image/svg+xml",
    ".emf": "image/x-emf",  ".wmf": "image/x-wmf",
}


# ══════════════════════════════════════════════════════════════════════════════
# 一、数据结构
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class DocxParagraph:
    index: int                 # 1-based 文档内段落序号
    text: str
    style: str = ""
    heading_level: Optional[int] = None   # 从 pStyle "Heading1~9" 解析; None 表示非标题
    images_inline: List[str] = field(default_factory=list)  # 本段内嵌的 media 文件名

    def to_dict(self) -> Dict[str, Any]:
        return {
            "p": self.index, "style": self.style, "text": self.text,
            "heading_level": self.heading_level,
            "images_inline": list(self.images_inline),
        }


@dataclass
class DocxImage:
    filename: str           # media 文件名 (image1.png 等)
    zip_path: str           # word/media/xxx
    ext: str
    size_bytes: int
    data: bytes             # 原始字节 (常驻内存; docx 通常几 MB)
    doc_order: Optional[int] = None   # 在 document.xml 中的出现次序, 1-based
    rid: Optional[str] = None

    @property
    def size_kb(self) -> float:
        return round(self.size_bytes / 1024, 1)

    def to_dict(self, include_data: bool = False) -> Dict[str, Any]:
        d = {
            "filename": self.filename, "zip_path": self.zip_path,
            "ext": self.ext, "size_bytes": self.size_bytes,
            "size_kb": self.size_kb,
            "doc_order": self.doc_order, "rid": self.rid,
        }
        if include_data:
            d["data_b64"] = base64.b64encode(self.data).decode("ascii")
        return d


@dataclass
class DocxTable:
    rows: List[List[str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"rows": self.rows, "n_rows": len(self.rows),
                "n_cols": max((len(r) for r in self.rows), default=0)}


@dataclass
class DocxBundle:
    """一次打开 docx 提取所有可用信息, 按结构化 API 返回."""
    source: Path
    paragraphs: List[DocxParagraph] = field(default_factory=list)
    images: List[DocxImage] = field(default_factory=list)
    tables: List[DocxTable] = field(default_factory=list)
    rid_to_media: Dict[str, str] = field(default_factory=dict)   # rId → filename
    rid_to_link:  Dict[str, str] = field(default_factory=dict)   # rId → URL
    doc_image_order: List[str] = field(default_factory=list)     # filename 序列
    all_media_names: List[str] = field(default_factory=list)
    document_xml: str = ""
    rels_xml: str = ""

    def find_image(self, filename: str) -> Optional[DocxImage]:
        for img in self.images:
            if img.filename == filename:
                return img
        return None

    def concat_text(self, separator: str = "\n") -> str:
        return separator.join(p.text for p in self.paragraphs if p.text)

    def to_dict(self, include_image_data: bool = False) -> Dict[str, Any]:
        return {
            "source": str(self.source),
            "paragraphs": [p.to_dict() for p in self.paragraphs],
            "images": [img.to_dict(include_data=include_image_data) for img in self.images],
            "tables": [t.to_dict() for t in self.tables],
            "rid_to_media": self.rid_to_media,
            "rid_to_link":  self.rid_to_link,
            "doc_image_order": self.doc_image_order,
            "all_media_names": self.all_media_names,
        }


# ══════════════════════════════════════════════════════════════════════════════
# 二、核心打开器
# ══════════════════════════════════════════════════════════════════════════════

def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _paragraph_text(p_elem: ET.Element) -> str:
    """合并一个 w:p 下所有 w:t (包含 w:br 作为换行)."""
    parts: List[str] = []
    for node in p_elem.iter():
        ln = _local_name(node.tag)
        if ln == "t" and node.text:
            parts.append(node.text)
        elif ln == "br":
            parts.append("\n")
        elif ln == "tab":
            parts.append("\t")
    return "".join(parts)


def _paragraph_style(p_elem: ET.Element) -> Tuple[str, Optional[int]]:
    """从 w:pPr/w:pStyle/@w:val 取出样式名; 并从 Heading1~9 推断级别."""
    ppr = p_elem.find(f"{_W}pPr")
    if ppr is None:
        return "", None
    pstyle = ppr.find(f"{_W}pStyle")
    if pstyle is None:
        return "", None
    val = pstyle.get(f"{_W}val", "") or ""
    level = None
    m = re.match(r"(?:Heading|heading)(\d)", val)
    if m:
        level = int(m.group(1))
    return val, level


def _paragraph_images(p_elem: ET.Element) -> List[str]:
    """抽取本段 inline 图片的 r:embed id."""
    rids: List[str] = []
    for node in p_elem.iter():
        if _local_name(node.tag) == "blip":
            rid = node.get(f"{_R}embed") or node.get(f"{_R}link")
            if rid:
                rids.append(rid)
    return rids


def _parse_rels(rels_bytes: bytes) -> Tuple[Dict[str, str], Dict[str, str]]:
    """解析 word/_rels/document.xml.rels. 返回 (rId→media_filename, rId→hyperlink_url)."""
    media: Dict[str, str] = {}
    links: Dict[str, str] = {}
    try:
        root = ET.fromstring(rels_bytes)
    except ET.ParseError:
        return media, links
    for rel in root.iter():
        if _local_name(rel.tag) != "Relationship":
            continue
        rid = rel.get("Id") or ""
        target = rel.get("Target") or ""
        rtype = rel.get("Type") or ""
        if "media" in target.lower() or "image" in rtype.lower():
            media[rid] = Path(target).name
        elif "hyperlink" in rtype.lower():
            links[rid] = target
    return media, links


def _parse_tables(doc_root: ET.Element) -> List[DocxTable]:
    tables: List[DocxTable] = []
    for tbl in doc_root.iter(f"{_W}tbl"):
        t = DocxTable()
        for tr in tbl.findall(f"{_W}tr"):
            row: List[str] = []
            for tc in tr.findall(f"{_W}tc"):
                cell_texts: List[str] = []
                for p in tc.findall(f"{_W}p"):
                    cell_texts.append(_paragraph_text(p))
                row.append("\n".join(ct for ct in cell_texts if ct).strip())
            if row:
                t.rows.append(row)
        if t.rows:
            tables.append(t)
    return tables


def open_docx(path: PathLike) -> DocxBundle:
    """
    打开 docx 一次性提取所有结构化内容. 仅使用标准库.

    raises: FileNotFoundError, zipfile.BadZipFile
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))
    bundle = DocxBundle(source=p)

    with zipfile.ZipFile(p) as zf:
        names = zf.namelist()
        bundle.all_media_names = [n for n in names if n.startswith("word/media/")]

        # rels 先解析 (图片命名所需)
        if "word/_rels/document.xml.rels" in names:
            rels_bytes = zf.read("word/_rels/document.xml.rels")
            bundle.rels_xml = rels_bytes.decode("utf-8", errors="replace")
            bundle.rid_to_media, bundle.rid_to_link = _parse_rels(rels_bytes)

        # media 抽取 (原字节)
        for zpath in bundle.all_media_names:
            data = zf.read(zpath)
            fname = Path(zpath).name
            bundle.images.append(DocxImage(
                filename=fname, zip_path=zpath,
                ext=Path(fname).suffix.lower(),
                size_bytes=len(data), data=data,
            ))

        # rId 反查 → 为 DocxImage 填 rid
        rid_by_file = {v: k for k, v in bundle.rid_to_media.items()}
        for img in bundle.images:
            img.rid = rid_by_file.get(img.filename)

        # document.xml
        if "word/document.xml" not in names:
            return bundle  # legacy .doc 或损坏文件
        doc_bytes = zf.read("word/document.xml")
        bundle.document_xml = doc_bytes.decode("utf-8", errors="replace")
        try:
            doc_root = ET.fromstring(doc_bytes)
        except ET.ParseError:
            return bundle

        # paragraphs (按文档顺序)
        pi = 0
        for p_elem in doc_root.iter(f"{_W}p"):
            pi += 1
            style, level = _paragraph_style(p_elem)
            txt = _paragraph_text(p_elem)
            inline_rids = _paragraph_images(p_elem)
            inline_files: List[str] = []
            for rid in inline_rids:
                fname = bundle.rid_to_media.get(rid)
                if fname:
                    inline_files.append(fname)
            if txt.strip() or inline_files:
                bundle.paragraphs.append(DocxParagraph(
                    index=pi, text=txt.strip(), style=style,
                    heading_level=level, images_inline=inline_files,
                ))

        # tables
        bundle.tables = _parse_tables(doc_root)

        # Image appearance order in document
        seen: List[str] = []
        for m in re.finditer(r'r:embed="(rId\d+)"', bundle.document_xml):
            rid = m.group(1)
            fname = bundle.rid_to_media.get(rid)
            if fname and fname not in seen:
                seen.append(fname)
        bundle.doc_image_order = seen
        for order_idx, fname in enumerate(seen, start=1):
            img = bundle.find_image(fname)
            if img:
                img.doc_order = order_idx

    return bundle


# ══════════════════════════════════════════════════════════════════════════════
# 三、结构化扫描 · 图题 / 表题 / 章节
# ══════════════════════════════════════════════════════════════════════════════

# "图2.1 ..." / "图6-1 ..." / "Figure 2.1 ..."
_FIG_RX = re.compile(
    r"^(?:图|Figure|Fig\.)\s*(\d+[\.\-]\d+(?:[\.\-]\d+)?)\s+(.+)$",
    re.IGNORECASE,
)
# "表2.1 ..." / "Table 2.1 ..."
_TAB_RX = re.compile(
    r"^(?:表|Table|Tab\.)\s*(\d+[\.\-]\d+(?:[\.\-]\d+)?)\s+(.+)$",
    re.IGNORECASE,
)


def find_figure_captions(bundle: DocxBundle, context_chars: int = 200) -> List[Dict[str, Any]]:
    """扫描全部段落, 抽出符合图题模式的条目. 附带前后上下文 (截断)."""
    out: List[Dict[str, Any]] = []
    paras = bundle.paragraphs
    for idx, p in enumerate(paras):
        m = _FIG_RX.match(p.text)
        if not m:
            continue
        prev_t = paras[idx - 1].text if idx > 0 else ""
        next_t = paras[idx + 1].text if idx + 1 < len(paras) else ""
        out.append({
            "fig_num": f"图{m.group(1)}",
            "caption": m.group(2),
            "p_index": p.index,
            "context_before": prev_t[:context_chars],
            "context_after":  next_t[:context_chars],
        })
    return out


def find_table_captions(bundle: DocxBundle) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for p in bundle.paragraphs:
        m = _TAB_RX.match(p.text)
        if not m:
            continue
        out.append({"tab_num": f"表{m.group(1)}", "caption": m.group(2),
                    "p_index": p.index})
    return out


def find_sections(bundle: DocxBundle) -> List[Dict[str, Any]]:
    """从 Heading 样式或章节编号模式抽取章节列表."""
    out: List[Dict[str, Any]] = []
    for p in bundle.paragraphs:
        text = p.text
        if p.heading_level is not None:
            out.append({"level": p.heading_level, "title": text, "p": p.index})
            continue
        # 回退: 基于编号模式推断
        if re.match(r"^\d+\s+\S", text):
            out.append({"level": 1, "title": text, "p": p.index})
        elif re.match(r"^\d+\.\d+\s+\S", text):
            out.append({"level": 2, "title": text, "p": p.index})
        elif re.match(r"^\d+\.\d+\.\d+\s+\S", text):
            out.append({"level": 3, "title": text, "p": p.index})
    return out


# ══════════════════════════════════════════════════════════════════════════════
# 四、便捷导出
# ══════════════════════════════════════════════════════════════════════════════

def extract_docx_texts(path: PathLike) -> List[str]:
    return [p.text for p in open_docx(path).paragraphs if p.text]


def extract_docx_images(path: PathLike, out_dir: PathLike) -> List[Path]:
    """把 docx 内嵌媒体全部写到 out_dir. 返回写出的路径列表."""
    out_d = Path(out_dir); out_d.mkdir(parents=True, exist_ok=True)
    bundle = open_docx(path)
    written: List[Path] = []
    for img in bundle.images:
        target = out_d / img.filename
        target.write_bytes(img.data)
        written.append(target)
    return written


def data_uri(img: DocxImage) -> str:
    """生成 inline <img src="data:..."> 的 URI."""
    mime = MIME_MAP.get(img.ext, "application/octet-stream")
    b64 = base64.b64encode(img.data).decode("ascii")
    return f"data:{mime};base64,{b64}"


# ══════════════════════════════════════════════════════════════════════════════
# 五、自验证 · 合成一个极简 docx in-memory
# ══════════════════════════════════════════════════════════════════════════════

def _build_minimal_docx() -> bytes:
    """构造一个含 1 段文本 + 1 图 + 1 表 + 1 图题的最小 docx bytes."""
    # 最小 PNG: 1x1 transparent
    png = bytes.fromhex("89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C48900000001737"
                        "5524742005CDA000000044944415478DA63001000000005000153DFCEC00000000049454E44"
                        "AE426082")

    document_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
            xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <w:body>
    <w:p>
      <w:pPr><w:pStyle w:val="Heading1"/></w:pPr>
      <w:r><w:t>1 绪论</w:t></w:r>
    </w:p>
    <w:p><w:r><w:t>这是正文段落。</w:t></w:r></w:p>
    <w:p>
      <w:r>
        <w:drawing><w:inline><a:graphic><a:graphicData>
          <pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
            <pic:blipFill><a:blip r:embed="rId1"/></pic:blipFill>
          </pic:pic>
        </a:graphicData></a:graphic></w:inline></w:drawing>
      </w:r>
    </w:p>
    <w:p><w:r><w:t>图1.1 示意图</w:t></w:r></w:p>
    <w:tbl>
      <w:tr><w:tc><w:p><w:r><w:t>项目</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>值</w:t></w:r></w:p></w:tc></w:tr>
      <w:tr><w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>1</w:t></w:r></w:p></w:tc></w:tr>
    </w:tbl>
  </w:body>
</w:document>
'''.encode("utf-8")

    rels_xml = b'''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
    Target="media/image1.png"/>
</Relationships>
'''

    content_types = b'''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="png" ContentType="image/png"/>
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml"  ContentType="application/xml"/>
  <Override PartName="/word/document.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
'''

    root_rels = b'''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdMain"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
    Target="word/document.xml"/>
</Relationships>
'''
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/_rels/document.xml.rels", rels_xml)
        zf.writestr("word/media/image1.png", png)
    return buf.getvalue()


def _self_test() -> int:
    tmp = Path("__dao_docx_test.docx")
    tmp.write_bytes(_build_minimal_docx())
    try:
        bundle = open_docx(tmp)
        assert len(bundle.paragraphs) >= 3, f"paragraphs={len(bundle.paragraphs)}"
        assert len(bundle.images) == 1, f"images={len(bundle.images)}"
        img = bundle.images[0]
        assert img.filename == "image1.png", img.filename
        assert img.rid == "rId1", img.rid
        assert img.doc_order == 1, img.doc_order
        assert len(bundle.tables) == 1 and bundle.tables[0].rows[0] == ["项目", "值"], bundle.tables
        figs = find_figure_captions(bundle)
        assert len(figs) == 1 and figs[0]["fig_num"] == "图1.1", figs
        secs = find_sections(bundle)
        assert any(s["level"] == 1 and "绪论" in s["title"] for s in secs), secs
        print(f"  OK  paragraphs: {len(bundle.paragraphs)}")
        print(f"  OK  images: {len(bundle.images)} (rid={img.rid}, order={img.doc_order})")
        print(f"  OK  tables: {len(bundle.tables)} first={bundle.tables[0].rows[0]}")
        print(f"  OK  fig_captions: {figs}")
        print(f"  OK  sections: {len(secs)} first={secs[0]}")
        # Data URI round-trip
        uri = data_uri(img)
        assert uri.startswith("data:image/png;base64,"), uri[:50]
        print(f"  OK  data_uri: len={len(uri)} prefix={uri[:40]}")
    finally:
        tmp.unlink(missing_ok=True)

    print("\n  dao_docx self-test: all assertions passed ✓")
    return 0


if __name__ == "__main__":
    import json
    import sys
    if len(sys.argv) > 1:
        b = open_docx(sys.argv[1])
        print(json.dumps({
            "source": str(b.source),
            "paragraphs": len(b.paragraphs),
            "images": len(b.images),
            "tables": len(b.tables),
            "figures": find_figure_captions(b)[:3],
            "tables_captions": find_table_captions(b)[:3],
            "sections_first5": find_sections(b)[:5],
        }, ensure_ascii=False, indent=2))
    else:
        raise SystemExit(_self_test())
