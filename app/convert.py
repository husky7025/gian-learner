"""ODT·PDF 샘플을 글자 줄 목록으로 읽어, 기본 서식의 hwpx 샘플로 바꾼다.

- ODT(K-에듀파인 「본문」 내려받기 등): 문단·표를 문서 순서대로 줄로 펼친다.
- PDF: 글자가 들어 있는 PDF만 가능(스캔 이미지 PDF는 불가). 쪽 번호·쪽마다 반복되는 줄은 뺀다.
바뀐 샘플은 원본의 글꼴·표 모양 대신 기본 서식(기본 꾸러미의 품의 예시)을 따른다.
"""
from __future__ import annotations

import io
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

from lxml import etree

RESOURCES = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
DEFAULT_PACK = RESOURCES / "packs" / "기본양식.gianpack"
BASE_IN_PACK = "forms/2/sample1.hwpx"  # 기본 꾸러미의 품의 예시(서식이 가장 단순)
CONVERTED_MARK = "gian-learner:converted"
MAX_LINES = 3000

TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
TABLE = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
OFFICE = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
T = "{%s}" % TEXT
TB = "{%s}" % TABLE
SKIP = {T + "note", T + "note-citation", "{%s}annotation" % OFFICE, T + "bookmark", T + "bookmark-start",
        T + "bookmark-end", T + "sequence-decls", T + "tracked-changes"}


class ConvertError(ValueError):
    pass


# ───────── ODT ─────────

def _odt_inline(el) -> str:
    s = el.text or ""
    for c in el:
        if c.tag in SKIP:
            pass
        elif c.tag == T + "s":
            s += " " * int(c.get(T + "c", "1"))
        elif c.tag == T + "tab":
            s += "    "
        elif c.tag == T + "line-break":
            s += "\n"
        elif c.tag in (TB + "table",):
            pass  # 글상자 안 표는 따로 처리
        else:
            s += _odt_inline(c)
        s += c.tail or ""
    return s


def _odt_walk(el, out: list[str]) -> None:
    for c in el:
        if c.tag in (T + "p", T + "h"):
            inner_tables = list(c.iter(TB + "table"))
            text = _odt_inline(c)
            if text.strip():
                out.extend(text.split("\n"))
            elif not inner_tables:
                out.append("")
            for t in inner_tables:  # 문단 안 글상자에 든 표
                if not any(a.tag == TB + "table" for a in t.iterancestors() if a is not c and c in a.iterancestors()):
                    _odt_table(t, out)
        elif c.tag == TB + "table":
            _odt_table(c, out)
        elif c.tag in SKIP:
            continue
        else:
            _odt_walk(c, out)


def _odt_table(tbl, out: list[str]) -> None:
    for row in tbl.iter(TB + "table-row"):
        if next((a for a in row.iterancestors(TB + "table")), None) is not tbl:
            continue  # 안쪽 표의 행은 안쪽 표에서 처리
        cells = [c for c in row if c.tag == TB + "table-cell"]
        cell_lines = []
        for cell in cells:
            lines: list[str] = []
            _odt_walk(cell, lines)
            cell_lines.append([x for x in lines if x.strip()])
        if all(len(x) <= 1 for x in cell_lines):
            joined = "  ".join(x[0].strip() for x in cell_lines if x)
            if joined:
                out.append(joined)
        else:
            for x in cell_lines:
                out.extend(x)


def odt_lines(data: bytes) -> list[str]:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        root = etree.fromstring(z.read("content.xml"), etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False))
    except (zipfile.BadZipFile, KeyError, etree.XMLSyntaxError) as e:
        raise ConvertError("ODT 문서를 읽을 수 없습니다.") from e
    body = root.find(f"{{{OFFICE}}}body/{{{OFFICE}}}text")
    if body is None:
        raise ConvertError("ODT 문서에 본문이 없습니다.")
    out: list[str] = []
    _odt_walk(body, out)
    return _tidy(out)


# ───────── PDF ─────────

PAGE_NO = re.compile(r"^\s*[-–]?\s*\d{1,3}\s*[-–]?\s*$|^\s*\d{1,3}\s*/\s*\d{1,3}\s*$")


def pdf_lines(data: bytes) -> list[str]:
    try:
        import logging
        logging.getLogger("pypdf").setLevel(logging.ERROR)
        from pypdf import PdfReader
        r = PdfReader(io.BytesIO(data))
        if r.is_encrypted:
            r.decrypt("")
        pages = [(p.extract_text() or "").splitlines() for p in r.pages[:50]]
    except Exception as e:  # noqa: BLE001
        raise ConvertError("PDF를 읽을 수 없습니다. (암호가 걸렸거나 손상된 파일일 수 있습니다)") from e
    if not any(x.strip() for p in pages for x in p):
        raise ConvertError("글자를 찾을 수 없는 PDF입니다. (스캔한 이미지 PDF는 읽을 수 없습니다)")
    repeated = set()
    if len(pages) >= 2:  # 쪽마다 반복되는 머리말·꼬리말
        cnt = Counter(x.strip() for p in pages for x in set(p) if x.strip())
        repeated = {k for k, v in cnt.items() if v >= max(2, len(pages) * 0.8)}
    out = []
    for p in pages:
        out.extend(x for x in p if not PAGE_NO.match(x) and x.strip() not in repeated)
    return _tidy(out)


# ───────── 공통 ─────────

def _tidy(lines: list[str]) -> list[str]:
    res: list[str] = []
    for x in lines:
        x = x.replace(" ", " ").replace("\t", "    ").rstrip()
        if not x.strip() and (not res or not res[-1].strip()):
            continue  # 빈 줄 여러 개는 하나로
        res.append(x)
    while res and not res[-1].strip():
        res.pop()
    if not any(x.strip() for x in res):
        raise ConvertError("문서에서 글자를 찾지 못했습니다.")
    return res[:MAX_LINES]


def read_lines(filename: str, data: bytes) -> list[str]:
    low = filename.lower()
    if low.endswith(".odt"):
        return odt_lines(data)
    if low.endswith(".pdf"):
        return pdf_lines(data)
    raise ConvertError("지원하지 않는 파일 형식입니다.")


def base_hwpx() -> bytes:
    if not DEFAULT_PACK.exists():
        raise ConvertError("기본 서식 파일이 없어 변환할 수 없습니다.")
    return zipfile.ZipFile(DEFAULT_PACK).read(BASE_IN_PACK)


def to_hwpx(filename: str, data: bytes) -> bytes:
    from . import hwpx_engine as E
    lines = read_lines(filename, data)
    return E.from_lines(base_hwpx(), lines, CONVERTED_MARK)
