"""HWPX 기안 양식 학습·생성 엔진.

학습: 샘플 hwpx들의 본문 문단을 읽어
  - 머리 부분(번호 항목 이전) : 고정 줄 / 입력 줄
  - 개요 부분(1. 가. 1) ...)  : 항목(제목:값) 트리
  - 붙임 부분                : 붙임 목록
  - 꼬리 부분                : 고정 줄 / 입력 줄
로 나누고, 샘플끼리 비교해 공통(고정)과 변하는 부분(입력칸)을 찾는다.

생성: 기준 샘플 파일을 그대로 복사하고 본문 문단만 다시 써서
글꼴·문단 모양·여백 등 서식을 원본과 같게 유지한다.
"""
from __future__ import annotations

import copy
import difflib
import io
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HP = "{%s}" % HP_NS
SECTION = "Contents/section0.xml"
MAX_UNZIPPED = 80 * 1024 * 1024

OBJECT_TAGS = {
    HP + t
    for t in (
        "tbl", "pic", "container", "rect", "ellipse", "line", "arc", "polygon",
        "curve", "connectLine", "equation", "ole", "textart", "video", "chart",
    )
}

KOR = "가나다라마바사아자차카타파하"
CIRC = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
CIRC_K = "㉮㉯㉰㉱㉲㉳㉴㉵㉶㉷㉸㉹㉺㉻"

# (종류, 정규식) — 순서가 곧 공문서 항목 단계(깊이)
MARKER_TYPES = [
    ("num_dot", r"\d{1,2}\.(?!\d)"),
    ("kor_dot", f"[{KOR}]\\."),
    ("num_par", r"\d{1,2}\)"),
    ("kor_par", f"[{KOR}]\\)"),
    ("num_ppar", r"\(\d{1,2}\)"),
    ("kor_ppar", f"\\([{KOR}]\\)"),
    ("circ", f"[{CIRC}]"),
    ("circ_k", f"[{CIRC_K}]"),
]
DEPTH_OF = {t: i for i, (t, _) in enumerate(MARKER_TYPES)}
_MARKER_ALT = "|".join(f"(?P<{t}>{rx})" for t, rx in MARKER_TYPES)
LINE_RE = re.compile(
    rf"^(?P<indent>[ 　\t]*)(?:{_MARKER_ALT})(?P<gap>[ 　]*)(?P<rest>\S.*)$"
)
LABEL_RE = re.compile(r"^(?P<label>[^:：]{1,20}?)(?P<sep>[ 　]*[:：][ 　]*)(?P<value>.*)$")
HEAD_LABEL_RE = re.compile(r"^(?P<prefix>[ 　]*(?P<label>[^\s:：]{1,8})(?:[ 　]{2,}|[ 　]*[:：][ 　]*))(?P<value>.*)$")
ATTACH_RE = re.compile(r"^(?P<indent>[ 　]*)붙\s?임(?P<gap>[ 　]*)(?P<rest>.*)$")
ATTACH_CONT_RE = re.compile(r"^[ 　]+\d{1,2}\.[ 　]*\S")
END_RE = re.compile(r"(?P<gap>[ 　]+)끝\.?[ 　]*$")
ATT_NUM_RE = re.compile(r"^[ 　]*\d{1,2}\.[ 　]*")


class HwpxError(ValueError):
    pass


# ───────────────────────── 읽기 ─────────────────────────

def _t_text(t) -> str:
    s = t.text or ""
    for c in t:
        name = etree.QName(c).localname
        if name == "tab":
            s += "\t"
        elif name == "lineBreak":
            s += " "
        elif name in ("nbSpace", "fwSpace"):
            s += " "
        s += c.tail or ""
    return s


def para_text(p) -> str:
    return "".join(_t_text(t) for r in p.findall(HP + "run") for t in r.findall(HP + "t"))


def is_object(p) -> bool:
    return any(c.tag in OBJECT_TAGS for r in p.findall(HP + "run") for c in r)


@dataclass
class Doc:
    files: dict[str, bytes]
    names: list[str]
    root: etree._Element
    paras: list
    texts: list[str]
    objs: list[bool]


def load_doc(data: bytes) -> Doc:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise HwpxError("hwpx 파일이 아닙니다. (구버전 .hwp 파일은 한글에서 '다른 이름으로 저장 → HWPX'로 바꿔 주세요)") from e
    names = z.namelist()
    if SECTION not in names:
        raise HwpxError("한글 문서 본문(Contents/section0.xml)을 찾을 수 없습니다.")
    if sum(i.file_size for i in z.infolist()) > MAX_UNZIPPED:
        raise HwpxError("파일이 너무 큽니다.")
    files = {n: z.read(n) for n in names}
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
    root = etree.fromstring(files[SECTION], parser)
    paras = root.findall(HP + "p")
    if not paras:
        raise HwpxError("본문 문단이 없습니다.")
    texts = [para_text(p).replace("\t", "    ") for p in paras]
    objs = [is_object(p) for p in paras]
    return Doc(files, names, root, paras, texts, objs)


# ───────────────────────── 줄 분석 ─────────────────────────

def parse_marker(text: str):
    m = LINE_RE.match(text)
    if not m:
        return None
    mtype = next(t for t, _ in MARKER_TYPES if m.group(t))
    rest = m.group("rest")
    label, sep, value = "", "", rest
    lm = LABEL_RE.match(rest)
    if lm and not lm.group("label")[-1].isdigit() and len(lm.group("label").strip()) >= 1:
        label, sep, value = lm.group("label").strip(), lm.group("sep"), lm.group("value")
    return {
        "type": mtype,
        "depth": DEPTH_OF[mtype],
        "indent": m.group("indent"),
        "gap": m.group("gap"),
        "label": label,
        "sep": sep,
        "value": value,
    }


def _norm(label: str) -> str:
    return re.sub(r"\s+", "", label)


def analyze(doc: Doc) -> dict:
    """한 문서를 머리/개요/붙임/꼬리로 나눈다."""
    texts, objs = doc.texts, doc.objs
    n = len(texts)
    start = next((i for i in range(n) if not objs[i] and parse_marker(texts[i])), None)
    end_gap = None
    uses_end = any(END_RE.search(t) for t in texts)

    if start is None:
        return {"header": list(range(n)), "outline": [], "attach": None, "footer": [],
                "uses_end": uses_end, "end_gap": "  "}

    att = next((i for i in range(start, n) if not objs[i] and ATTACH_RE.match(texts[i])), None)
    if att is not None:
        outline_end = att
    else:
        end_line = next((i for i in range(start, n) if END_RE.search(texts[i])), None)
        if end_line is not None:
            outline_end = end_line + 1
        else:
            outline_end = n
            while outline_end > start and not texts[outline_end - 1].strip() and not objs[outline_end - 1]:
                outline_end -= 1

    items = []
    for i in range(start, outline_end):
        t = texts[i]
        if objs[i]:
            items.append({"kind": "object", "src": i, "text": t})
            continue
        em = END_RE.search(t)
        if em:
            end_gap = em.group("gap")
            t = t[: em.start()]
        mk = parse_marker(t)
        if mk:
            items.append({"kind": "item", "src": i, **mk})
        elif not t.strip():
            items.append({"kind": "blank", "src": i})
        else:
            stripped = t.lstrip(" 　")
            items.append({"kind": "para", "src": i, "indent": t[: len(t) - len(stripped)], "value": stripped})

    attach = None
    footer_start = outline_end
    if att is not None:
        m = ATTACH_RE.match(texts[att])
        lines = [att]
        j = att + 1
        while j < n and not objs[j] and ATTACH_CONT_RE.match(texts[j]):
            lines.append(j)
            j += 1
        footer_start = j
        entries = []
        for k, li in enumerate(lines):
            raw = m.group("rest") if k == 0 else texts[li]
            em = END_RE.search(raw)
            if em:
                end_gap = em.group("gap")
                raw = raw[: em.start()]
            raw = ATT_NUM_RE.sub("", raw).strip()
            if raw.endswith("."):
                raw = raw[:-1]
            if raw:
                entries.append(raw)
        attach = {
            "src": att,
            "cont_src": lines[1] if len(lines) > 1 else None,
            "indent": m.group("indent"),
            "gap": m.group("gap") or "  ",
            "items": entries,
        }

    return {
        "header": list(range(0, start)),
        "outline": items,
        "attach": attach,
        "footer": list(range(footer_start, n)),
        "uses_end": uses_end,
        "end_gap": end_gap or "  ",
    }


# ───────────────────────── 표 ─────────────────────────

def doc_tables(doc: Doc) -> list[dict]:
    """문서의 모든 표(중첩 포함)를 순서대로: {src, el, rows:[[cell]]}."""
    res = []
    for i, p in enumerate(doc.paras):
        for tbl in p.iter(HP + "tbl"):
            rows = []
            for tr in tbl.findall(HP + "tr"):
                row = []
                for tc in tr.findall(HP + "tc"):
                    a = tc.find(HP + "cellAddr")
                    sp = tc.find(HP + "cellSpan")
                    ps = tc.findall(f"{HP}subList/{HP}p")
                    row.append({
                        "r": int(a.get("rowAddr", 0)) if a is not None else len(rows),
                        "c": int(a.get("colAddr", 0)) if a is not None else len(row),
                        "cs": int(sp.get("colSpan", 1)) if sp is not None else 1,
                        "rs": int(sp.get("rowSpan", 1)) if sp is not None else 1,
                        "text": "\n".join(para_text(x).replace("\t", "    ") for x in ps),
                        "locked": any(is_object(x) for x in ps) or not ps,
                        "el": tc,
                    })
                rows.append(row)
            res.append({"src": i, "el": tbl, "rows": rows})
    return res


def _cell_key(gti: int, cell: dict) -> str:
    return f"c{gti}_{cell['r']}_{cell['c']}"


def _learn_tables(base: Doc, others: list[Doc], overrides: dict, total: int) -> list[dict]:
    base_t = doc_tables(base)
    other_t = [doc_tables(d) for d in others]
    out = []
    for gti, t in enumerate(base_t):
        nrows = len(t["rows"])
        ncols = max((c["c"] + c["cs"] for row in t["rows"] for c in row), default=0)
        rows = []
        for row in t["rows"]:
            cells = []
            for cell in row:
                key = _cell_key(gti, cell)
                vals = [cell["text"]]
                for ot in other_t:
                    if gti < len(ot):
                        hit = next((c for r in ot[gti]["rows"] for c in r if c["r"] == cell["r"] and c["c"] == cell["c"]), None)
                        if hit is not None:
                            vals.append(hit["text"])
                if cell["locked"]:
                    auto = "fixed"
                elif len(vals) > 1:
                    auto = "fixed" if all(v == vals[0] for v in vals) else "field"
                else:
                    is_head_row = cell["r"] == 0 and nrows >= 2 and ncols >= 3
                    auto = "field" if (cell["text"].strip() and cell["c"] > 0 and not is_head_row) else "fixed"
                kind = "fixed" if cell["locked"] else overrides.get(key, auto)
                default, examples = _value_default(vals, total)
                if len(vals) == 1:
                    default = cell["text"]
                cells.append({"key": key, "r": cell["r"], "c": cell["c"], "cs": cell["cs"], "rs": cell["rs"],
                              "text": cell["text"], "type": kind, "auto": auto, "locked": cell["locked"],
                              "default": default if kind == "field" else cell["text"], "examples": examples[:5]})
            rows.append(cells)
        out.append({"gti": gti, "src": t["src"], "rows": rows})
    return out


def _set_cell_text(tc, value: str, new_id) -> None:
    paras = tc.findall(f"{HP}subList/{HP}p")
    if not paras:
        return
    lines = value.split("\n")
    sub = paras[0].getparent()
    for k, line in enumerate(lines):
        if k < len(paras):
            set_para_text(paras[k], line)
        else:
            np_ = copy.deepcopy(paras[-1])
            set_para_text(np_, line)
            np_.set("id", new_id())
            sub.insert(list(sub).index(paras[-1]) + 1 + (k - len(paras)), np_)
    for extra in paras[len(lines):]:
        sub.remove(extra)


# ───────────────────────── 학습 ─────────────────────────

def _key(item) -> tuple | None:
    if item["kind"] != "item":
        return None
    if item["label"]:
        return (item["depth"], "L:" + _norm(item["label"]))
    return (item["depth"], "V:" + item["value"].strip())


def _labelset(an) -> set:
    return {_key(it) for it in an["outline"] if it["kind"] == "item" and it["label"]}


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / max(1, len(a | b))


def _common_prefix(values: list[str]) -> str:
    if len(values) < 2:
        return ""
    pre = values[0]
    for v in values[1:]:
        k = 0
        while k < len(pre) and k < len(v) and pre[k] == v[k]:
            k += 1
        pre = pre[:k]
    cut = max((i for i, ch in enumerate(pre) if ch in "-–(:/_"), default=-1)
    pre = pre[: cut + 1] if cut >= 0 else ""
    return pre if len(pre.strip()) >= 3 else ""


def _value_default(values: list[str], total_docs: int) -> tuple[str, list[str]]:
    """값들이 모두 같으면 그 값을 기본값으로, 다르면 공통 앞부분만 기본값으로."""
    uniq = list(dict.fromkeys(v for v in values))
    if total_docs == 1 or (len(values) >= 2 and len(uniq) == 1):
        return values[0], uniq
    return _common_prefix(values), uniq


def _match_map(base_lines: list[str], other_lines: list[str]) -> set[int]:
    sm = difflib.SequenceMatcher(a=base_lines, b=other_lines, autojunk=False)
    hit = set()
    for a, _b, size in sm.get_matching_blocks():
        hit.update(range(a, a + size))
    return hit


def _line_blocks(region: str, base_idx: list[int], base: Doc, others: list[tuple[Doc, dict]],
                 overrides: dict) -> list[dict]:
    base_lines = [base.texts[i] for i in base_idx]
    matched = [
        _match_map(base_lines, [d.texts[i] for i in an[region]]) for d, an in others
    ]
    blocks = []
    for k, i in enumerate(base_idx):
        text = base.texts[i]
        key = f"{region[0]}{k}"
        if base.objs[i]:
            blocks.append({"id": key, "type": "fixed", "src": i, "text": text or "[표·그림]", "object": True})
            continue
        hm = HEAD_LABEL_RE.match(text)
        if hm and any(ch.isdigit() for ch in hm.group("label")):
            hm = None
        if not others:
            auto = "field" if (hm and text.strip()) else "fixed"
        else:
            auto = "fixed" if all(k in mm for mm in matched) else "field"
        if not text.strip():
            auto = "fixed"
        kind = overrides.get(key, auto)
        if kind == "fixed":
            blocks.append({"id": key, "type": "fixed", "src": i, "text": text, "auto": auto})
            continue
        if hm:
            prefix, label, value = hm.group("prefix"), hm.group("label"), hm.group("value")
            values = [value]
            for d, an in others:
                for j in an[region]:
                    om = HEAD_LABEL_RE.match(d.texts[j])
                    if om and om.group("label") == label:
                        values.append(om.group("value"))
                        break
        else:
            prefix, label, values = "", "", [text]
            for d, an in others:
                ol = [d.texts[j] for j in an[region]]
                if k < len(ol):
                    values.append(ol[k])
        default, examples = _value_default(values, 1 + len(others))
        blocks.append({
            "id": key, "type": "field", "src": i, "prefix": prefix, "label": label or "내용",
            "default": default, "examples": examples[:5], "auto": auto, "text": text,
        })
    return blocks


def learn(sample_bytes: list[bytes], sample_ids: list, overrides: dict | None = None) -> dict:
    overrides = overrides or {}
    if not sample_bytes:
        return {"ready": False}
    docs = [load_doc(b) for b in sample_bytes]
    ans = [analyze(d) for d in docs]

    # 기준 샘플: 다른 샘플과 항목 구성이 가장 비슷한 것
    sets = [_labelset(a) for a in ans]
    scores = [sum(_jaccard(sets[i], sets[j]) for j in range(len(docs)) if j != i) for i in range(len(docs))]
    bi = max(range(len(docs)), key=lambda i: (scores[i], -i))
    if overrides.get("base_sample_id") in sample_ids:
        bi = sample_ids.index(overrides["base_sample_id"])
    base, ban = docs[bi], ans[bi]
    others = [(docs[i], ans[i]) for i in range(len(docs)) if i != bi]
    line_ov = overrides.get("lines", {})

    similarity = 1.0
    if others:
        similarity = sum(_jaccard(sets[bi], sets[i]) for i in range(len(docs)) if i != bi) / len(others)

    # 단계별 번호 모양(들여쓰기·번호 뒤 간격·제목 뒤 구분자) 학습
    styles = {}
    all_items = [it for a in [ban] + [a for _, a in others] for it in a["outline"] if it["kind"] == "item"]
    sep_all = Counter(it["sep"] for it in all_items if it["label"])
    default_sep = sep_all.most_common(1)[0][0] if sep_all else ": "
    for d in range(len(MARKER_TYPES)):
        base_its = [it for it in ban["outline"] if it["kind"] == "item" and it["depth"] == d]
        its = base_its or [it for it in all_items if it["depth"] == d]
        if not its:
            continue
        seps = Counter(it["sep"] for it in its if it["label"])
        styles[d] = {
            "type": MARKER_TYPES[d][0],
            "indent": Counter(it["indent"] for it in its).most_common(1)[0][0],
            "gap": Counter(it["gap"] for it in its).most_common(1)[0][0],
            "sep": seps.most_common(1)[0][0] if seps else default_sep,
            "src": base_its[0]["src"] if base_its else None,
        }

    # 개요 항목: 기준 샘플 구성 + 다른 샘플과 비교한 기본값
    occur: dict[tuple, list[str]] = {}
    for _d, a in [(base, ban)] + others:
        seen = set()
        for it in a["outline"]:
            k = _key(it)
            if k and k not in seen:
                seen.add(k)
                occur.setdefault(k, []).append(it["value"])
    outline = []
    base_items = ban["outline"]
    for idx, it in enumerate(base_items):
        if it["kind"] == "item":
            k = _key(it)
            vals = occur.get(k, [it["value"]])
            default, examples = _value_default(vals, len(docs))
            if not it["label"]:
                nxt = base_items[idx + 1] if idx + 1 < len(base_items) else None
                has_child = nxt is not None and nxt["kind"] == "item" and nxt["depth"] > it["depth"]
                if has_child and len(it["value"]) <= 12:
                    default = it["value"]
            outline.append({"kind": "item", "depth": it["depth"], "label": it["label"],
                            "value": default, "example": it["value"], "examples": examples[:5]})
        elif it["kind"] == "para":
            outline.append({"kind": "para", "indent": it["indent"], "value": it["value"] if not others else "",
                            "example": it["value"], "src": it["src"]})
        elif it["kind"] == "blank":
            outline.append({"kind": "blank", "src": it["src"]})
        else:
            outline.append({"kind": "object", "src": it["src"], "example": it.get("text") or "[표·그림]"})

    base_keys = {_key(it) for it in base_items}
    suggestions, seen_s = [], set()
    for _d, a in others:
        for it in a["outline"]:
            k = _key(it)
            if it["kind"] == "item" and it["label"] and k not in base_keys and k not in seen_s:
                seen_s.add(k)
                suggestions.append({"depth": it["depth"], "label": it["label"], "example": it["value"]})

    # 붙임
    att_lists = [a["attach"]["items"] for a in ans if a["attach"]]
    if att_lists and (len(docs) == 1 or (len(att_lists) == len(docs) and all(x == att_lists[0] for x in att_lists))):
        att_default = list(att_lists[0])
    else:
        att_default = []
    att_examples = list(dict.fromkeys(x for lst in att_lists for x in lst))[:8]
    ba = ban["attach"]

    blocks = _line_blocks("header", ban["header"], base, others, line_ov)
    if ban["outline"] or ba:
        blocks.append({"id": "outline", "type": "outline", "items": outline, "suggestions": suggestions})
        blocks.append({
            "id": "attach", "type": "attach", "default": att_default, "examples": att_examples,
            "src": ba["src"] if ba else None, "cont_src": ba["cont_src"] if ba else None,
            "indent": ba["indent"] if ba else "", "gap": ba["gap"] if ba else "  ",
        })
    blocks += _line_blocks("footer", ban["footer"], base, others, line_ov)

    return {
        "ready": True,
        "base_sample_id": sample_ids[bi],
        "sample_count": len(docs),
        "similarity": round(similarity, 2),
        "similarity_warn": bool(others) and similarity < 0.25,
        "styles": {str(k): v for k, v in styles.items()},
        "default_sep": default_sep,
        "uses_end": any(a["uses_end"] for a in ans),
        "end_gap": ban["end_gap"],
        "blocks": blocks,
        "tables": _learn_tables(base, [d for d, _ in others], line_ov, len(docs)),
        "base_lines": base.texts,
    }


# ───────────────────────── 번호·줄 만들기 ─────────────────────────

def make_marker(mtype: str, n: int) -> str:
    def kor(i):
        return KOR[(i - 1) % len(KOR)]
    return {
        "num_dot": f"{n}.",
        "kor_dot": f"{kor(n)}.",
        "num_par": f"{n})",
        "kor_par": f"{kor(n)})",
        "num_ppar": f"({n})",
        "kor_ppar": f"({kor(n)})",
        "circ": CIRC[(n - 1) % len(CIRC)],
        "circ_k": CIRC_K[(n - 1) % len(CIRC_K)],
    }[mtype]


def _width(s: str) -> int:
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in s)


def style_for(tpl: dict, depth: int) -> dict:
    st = tpl["styles"].get(str(depth))
    if st:
        return st
    return {"type": MARKER_TYPES[min(depth, len(MARKER_TYPES) - 1)][0], "indent": "  " * depth,
            "gap": " ", "sep": tpl.get("default_sep", ": "), "src": None}


def render_lines(tpl: dict, data: dict) -> list[tuple[int | None, str | None, str]]:
    """(원본 문단 번호, 새 글자 또는 None=원본 그대로, 종류) 목록."""
    out: list[tuple[int | None, str | None, str]] = []
    fields = data.get("fields", {})
    style_srcs = [s["src"] for s in tpl["styles"].values() if s.get("src") is not None]
    any_outline_src = style_srcs[0] if style_srcs else None
    end_mark = tpl.get("end_gap", "  ") + "끝."
    last_outline_line = None

    def nearest_src(depth):
        for dd in sorted(tpl["styles"], key=lambda x: abs(int(x) - depth)):
            if tpl["styles"][dd].get("src") is not None:
                return tpl["styles"][dd]["src"]
        return any_outline_src

    for b in tpl["blocks"]:
        if b["type"] == "fixed":
            out.append((b["src"], None, "fixed"))
        elif b["type"] == "field":
            val = str(fields.get(b["id"], b.get("default", "")))
            parts = val.split("\n")
            out.append((b["src"], b["prefix"] + parts[0], "field"))
            pad = " " * _width(b["prefix"])
            for extra in parts[1:]:
                out.append((b["src"], pad + extra, "field"))
        elif b["type"] == "outline":
            counters: dict[int, int] = {}
            for it in data.get("outline", b["items"]):
                kind = it.get("kind", "item")
                if kind == "item":
                    d = max(0, min(int(it.get("depth", 0)), len(MARKER_TYPES) - 1))
                    for dd in [x for x in counters if x > d]:
                        del counters[dd]
                    counters[d] = counters.get(d, 0) + 1
                    st = style_for(tpl, d)
                    head = st["indent"] + make_marker(st["type"], counters[d]) + st["gap"]
                    label = (it.get("label") or "").strip()
                    if label:
                        head += label + st["sep"]
                    parts = str(it.get("value", "")).split("\n")
                    src = st["src"] if st.get("src") is not None else nearest_src(d)
                    out.append((src, head + parts[0], "outline"))
                    pad = " " * (_width(st["indent"] + make_marker(st["type"], counters[d]) + st["gap"]))
                    for extra in parts[1:]:
                        out.append((src, pad + extra, "outline"))
                    last_outline_line = len(out) - 1
                elif kind == "para":
                    src = it.get("src") if it.get("src") is not None else any_outline_src
                    for line in str(it.get("value", "")).split("\n"):
                        out.append((src, it.get("indent", "") + line, "outline"))
                    last_outline_line = len(out) - 1
                elif kind == "blank":
                    out.append((it.get("src", any_outline_src), "", "outline"))
                elif kind == "object" and it.get("src") is not None:
                    out.append((it["src"], None, "object"))
        elif b["type"] == "attach":
            items = [x.strip().rstrip(".") for x in data.get("attach", b.get("default", [])) if str(x).strip()]
            src = b["src"] if b["src"] is not None else any_outline_src
            cont = b["cont_src"] if b["cont_src"] is not None else src
            head = b.get("indent", "") + "붙임" + b.get("gap", "  ")
            if len(items) == 1:
                out.append((src, head + items[0] + ".", "attach"))
            elif items:
                pad = " " * _width(head)
                for k, x in enumerate(items, 1):
                    out.append((src if k == 1 else cont, (head if k == 1 else pad) + f"{k}. {x}.", "attach"))
            if items and tpl.get("uses_end"):
                s, t, kd = out[-1]
                out[-1] = (s, t + end_mark, kd)
            elif tpl.get("uses_end") and last_outline_line is not None:
                s, t, kd = out[last_outline_line]
                out[last_outline_line] = (s, t + end_mark, kd)
    return out


# ───────────────────────── XML 쓰기 ─────────────────────────

def _strip_section_runs(p) -> None:
    for r in p.findall(HP + "run"):
        for c in list(r):
            if c.tag in (HP + "secPr", HP + "ctrl"):
                r.remove(c)
    runs = p.findall(HP + "run")
    empty = [r for r in runs if len(r) == 0 and not (r.text or "").strip()]
    if len(empty) == len(runs):
        empty = empty[1:]
    for r in empty:
        p.remove(r)


def _section_runs(p0) -> list:
    res = []
    for r in p0.findall(HP + "run"):
        keep = [c for c in r if c.tag in (HP + "secPr", HP + "ctrl")]
        if keep:
            nr = etree.Element(r.tag, attrib=dict(r.attrib))
            for c in keep:
                nr.append(copy.deepcopy(c))
            res.append(nr)
    return res


def set_para_text(p, text: str) -> None:
    runs = p.findall(HP + "run")
    ts = [(r, t) for r in runs for t in r.findall(HP + "t")]
    if ts:
        r0, t0 = ts[0]
        for c in list(t0):
            t0.remove(c)
        t0.text = text
        for r, t in ts[1:]:
            r.remove(t)
            if len(r) == 0 and r is not r0:
                p.remove(r)
    else:
        if runs:
            r = runs[-1]
        else:
            r = etree.SubElement(p, HP + "run", charPrIDRef="0")
        t = etree.SubElement(r, HP + "t")
        t.text = text
    for ls in p.findall(HP + "linesegarray"):
        p.remove(ls)


def generate(base_bytes: bytes, tpl: dict, data: dict) -> tuple[bytes, list[str]]:
    doc = load_doc(base_bytes)
    plan = render_lines(tpl, data)
    if not plan:
        raise HwpxError("생성할 내용이 없습니다.")

    ids = [int(x) for x in doc.root.xpath("//@id") if str(x).isdigit()]
    counter = [(max(ids) + 1) if ids and max(ids) < 4_000_000_000 else 2_100_000_000]

    def new_id() -> str:
        counter[0] += 1
        return str(counter[0])

    # 표 칸 입력값 반영 (원본 문단에 먼저 적용한 뒤 복사)
    specs = {c["key"]: c for t in tpl.get("tables", []) for row in t["rows"] for c in row if c["type"] == "field"}
    cells_in = data.get("cells", {}) or {}
    if specs:
        for gti, t in enumerate(doc_tables(doc)):
            for row in t["rows"]:
                for cell in row:
                    spec = specs.get(_cell_key(gti, cell))
                    if spec is None or cell["locked"]:
                        continue
                    val = str(cells_in.get(spec["key"], spec["default"]))
                    if val != cell["text"]:
                        _set_cell_text(cell["el"], val, new_id)

    p0 = doc.paras[0]
    sec_runs = _section_runs(p0)
    new_ps, preview = [], []
    for src, text, _kind in plan:
        if src is None or src >= len(doc.paras):
            src = 0
        p = copy.deepcopy(doc.paras[src])
        if src == 0:
            _strip_section_runs(p)
        if text is not None:
            set_para_text(p, text)
            p.set("id", new_id())
        preview.append(text if text is not None else doc.texts[src])
        new_ps.append(p)

    first = new_ps[0]
    for k, r in enumerate(sec_runs):
        first.insert(k, r)

    parent = p0.getparent()
    pos = list(parent).index(p0)
    for p in doc.paras:
        parent.remove(p)
    for k, p in enumerate(new_ps):
        parent.insert(pos + k, p)

    files = dict(doc.files)
    files[SECTION] = etree.tostring(doc.root, xml_declaration=True, encoding="UTF-8", standalone=True)
    if "Preview/PrvText.txt" in files:
        old = files["Preview/PrvText.txt"]
        txt = "\r\n".join(preview)[:1024]
        files["Preview/PrvText.txt"] = (b"\xff\xfe" if old.startswith(b"\xff\xfe") else b"") + txt.encode("utf-16le")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        if "mimetype" in files:
            z.writestr(zipfile.ZipInfo("mimetype"), files["mimetype"], compress_type=zipfile.ZIP_STORED)
        for n in doc.names:
            if n != "mimetype":
                z.writestr(n, files[n])
    out = buf.getvalue()
    validate(out)
    return out, preview


def validate(data: bytes) -> None:
    z = zipfile.ZipFile(io.BytesIO(data))
    if z.namelist()[0] != "mimetype" or z.getinfo("mimetype").compress_type != zipfile.ZIP_STORED:
        raise HwpxError("생성 파일 검사 실패: mimetype")
    root = etree.fromstring(z.read(SECTION))
    ps = root.findall(HP + "p")
    if not ps or ps[0].find(f"{HP}run/{HP}secPr") is None:
        raise HwpxError("생성 파일 검사 실패: 구역 설정 없음")


def preview_text(tpl: dict, data: dict, base_bytes: bytes) -> list[str]:
    doc = load_doc(base_bytes)
    cells_in = data.get("cells", {}) or {}
    by_src: dict[int, list] = {}
    for t in tpl.get("tables", []):
        by_src.setdefault(t["src"], []).append(t)
    out: list[str] = []
    for s, t, _ in render_lines(tpl, data):
        if t is not None:
            out.append(t)
            continue
        if s is not None and s < len(doc.texts) and s in by_src:
            for tb in by_src[s]:
                for row in tb["rows"]:
                    vals = [str(cells_in.get(c["key"], c["default"])) if c["type"] == "field" else c["text"] for c in row]
                    out.append("│ " + " │ ".join(v.replace(chr(10), " / ") for v in vals) + " │")
            continue
        out.append(doc.texts[s] if s is not None and s < len(doc.texts) else "")
    return out


def read_file(path: Path) -> bytes:
    return Path(path).read_bytes()
