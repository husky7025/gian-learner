"""양식 꾸러미(.gianpack): 학습된 양식(샘플 + 고정/입력칸 설정)을 파일 하나로 주고받기.

- 내보낼 때 샘플의 작성자 정보·미리보기 그림을 지우고, 파일 이름을 「샘플 1.hwpx」로 바꾼다.
- 내보내기 전 개인정보로 보이는 글자(전화번호·이메일·주민번호·이름 등)를 찾아 보여 준다.
- 가져올 때는 디스크에 풀지 않고 메모리에서 검사한 뒤 저장한다.
"""
from __future__ import annotations

import io
import json
import re
import struct
import zipfile
import zlib
from datetime import datetime

from lxml import etree

from . import hwpx_engine as E

FORMAT = "gian-pack"
VERSION = 1
MAX_PACK = 150 * 1024 * 1024
MAX_FORMS = 50
MAX_SAMPLES = 30
HPF = "Contents/content.hpf"
OPF = "{http://www.idpf.org/2007/opf/}"


class PackError(ValueError):
    pass


# ───────── 숨은 정보 지우기 ─────────

def blank_png(w: int = 8, h: int = 8) -> bytes:
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\xff\xff\xff" * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def scrub(data: bytes) -> bytes:
    """작성자·제목 등 문서 정보와 미리보기 그림·글자를 지운 hwpx를 돌려준다."""
    zin = zipfile.ZipFile(io.BytesIO(data))
    files = {n: zin.read(n) for n in zin.namelist()}
    if HPF in files:
        root = etree.fromstring(files[HPF], etree.XMLParser(resolve_entities=False, no_network=True))
        for el in root.iter(OPF + "title"):
            el.text = ""
        for el in root.iter(OPF + "meta"):
            if el.get("name") in ("creator", "lastsaveby", "subject", "description", "keyword"):
                el.text = None
        files[HPF] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    if "Preview/PrvImage.png" in files:
        files["Preview/PrvImage.png"] = blank_png()
    if "Preview/PrvText.txt" in files:
        doc = E.load_doc(data)
        txt = "\r\n".join(doc.texts)[:1024]
        old = files["Preview/PrvText.txt"]
        files["Preview/PrvText.txt"] = (b"\xff\xfe" if old.startswith(b"\xff\xfe") else b"") + txt.encode("utf-16le")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        names = zin.namelist()
        if "mimetype" in files:
            z.writestr(zipfile.ZipInfo("mimetype"), files["mimetype"], compress_type=zipfile.ZIP_STORED)
        for n in names:
            if n != "mimetype":
                z.writestr(n, files[n])
    return buf.getvalue()


# ───────── 개인정보 검사 ─────────

PII_RULES = [
    ("전화번호", re.compile(r"(?<!\d)(?:0\d{1,2}|1[5-9]\d{2})[-.) ]\s?\d{3,4}[-. ]\d{4}(?!\d)")),
    ("이메일", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("주민등록번호", re.compile(r"(?<!\d)\d{6}\s?-\s?[1-4]\d{6}(?!\d)")),
    ("학년·반·번호", re.compile(r"\d\s*학년\s*\d{1,2}\s*반\s*\d{1,2}\s*번")),
    ("문서번호", re.compile(r"[가-힣A-Za-z]+(?:과|교|청|부|실|원)?-\d{3,6}(?:\s*\(\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.\))?")),
]
# 앞에서부터 겹쳐서 찾기(예: "담당자 : 교사 홍길동"의 "교사 홍길동"까지)
NAME_RE = re.compile(r"(?=(교사|교감|교장|담당자|담임|강사|작성자|성명|이름|보호자)[ 　]{0,2}[:：]?[ 　]{0,3}([가-힣]{2,4})(?=[\s,(·)☏☎/]|$))")
PARTICLE_END = tuple("을를께님의에로와과도만")
NOT_NAME = {"성명", "이름", "중", "및", "등", "전체", "희망자", "선생님", "대상", "참여", "선착순", "본인", "귀하", "명단",
            "교사", "교직원", "학생", "학부모", "보호자", "서명", "개인", "확인", "신청", "제출", "작성", "안내", "참여자"}


def doc_strings(data: bytes) -> list[str]:
    """본문·표·머리말 등 모든 글자 + 문서 정보(작성자 등)."""
    z = zipfile.ZipFile(io.BytesIO(data))
    out = []
    for n in z.namelist():
        if n.startswith("Contents/section") and n.endswith(".xml"):
            root = etree.fromstring(z.read(n), etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False))
            for p in root.iter(E.HP + "p"):
                t = E.para_text(p)
                if t.strip():
                    out.append(t)
    return out


def scan_text(lines: list[str]) -> list[dict]:
    found, seen = [], set()
    for line in lines:
        for kind, rx in PII_RULES:
            for m in rx.finditer(line):
                key = (kind, m.group(0))
                if key not in seen:
                    seen.add(key)
                    found.append({"kind": kind, "value": m.group(0), "context": line.strip()[:80]})
        for m in NAME_RE.finditer(line):
            name = m.group(2)
            if name in NOT_NAME or name.endswith(PARTICLE_END):
                continue
            key = ("이름", name)
            if key not in seen:
                seen.add(key)
                found.append({"kind": "이름으로 보이는 글자", "value": f"{m.group(1)} {name}", "context": line.strip()[:80]})
    return found


# ───────── 내보내기·가져오기 ─────────

def export_pack(forms: list[dict]) -> bytes:
    """forms: [{name, category, overrides, samples: [{id, data}]}]"""
    manifest = {"format": FORMAT, "version": VERSION, "created": datetime.now().strftime("%Y-%m-%d %H:%M"), "forms": []}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for fi, f in enumerate(forms):
            ids = [s["id"] for s in f["samples"]]
            ov = dict(f.get("overrides") or {})
            base_idx = ids.index(ov["base_sample_id"]) if ov.get("base_sample_id") in ids else None
            entry = {"name": f["name"], "category": f["category"], "lines": ov.get("lines", {}),
                     "base_sample_index": base_idx, "samples": []}
            for si, s in enumerate(f["samples"]):
                path = f"forms/{fi + 1}/sample{si + 1}.hwpx"
                z.writestr(path, scrub(s["data"]))
                entry["samples"].append({"file": path, "filename": f"샘플 {si + 1}.hwpx"})
            manifest["forms"].append(entry)
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1))
    return buf.getvalue()


def read_pack(data: bytes, categories: dict) -> list[dict]:
    if len(data) > MAX_PACK:
        raise PackError("꾸러미 파일이 너무 큽니다.")
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        manifest = json.loads(z.read("manifest.json").decode("utf-8"))
    except (zipfile.BadZipFile, KeyError, ValueError) as e:
        raise PackError("기안 학습기 꾸러미(.gianpack) 파일이 아닙니다.") from e
    if manifest.get("format") != FORMAT or not isinstance(manifest.get("forms"), list):
        raise PackError("기안 학습기 꾸러미(.gianpack) 파일이 아닙니다.")
    if int(manifest.get("version", 0)) > VERSION:
        raise PackError("더 새 버전의 앱에서 만든 꾸러미입니다. 앱을 업데이트해 주세요.")
    if sum(i.file_size for i in z.infolist()) > MAX_PACK * 2:
        raise PackError("꾸러미 내용이 너무 큽니다.")
    names = set(z.namelist())
    out = []
    for f in manifest["forms"][:MAX_FORMS]:
        samples = []
        for s in (f.get("samples") or [])[:MAX_SAMPLES]:
            path = str(s.get("file", ""))
            if path not in names:
                raise PackError(f"꾸러미가 손상되었습니다: {path}")
            b = z.read(path)
            try:
                E.load_doc(b)
            except E.HwpxError as e:
                raise PackError(f"꾸러미 안의 샘플을 읽을 수 없습니다: {e}") from e
            samples.append({"filename": str(s.get("filename") or "샘플.hwpx")[:120], "data": b})
        lines = {k: v for k, v in (f.get("lines") or {}).items()
                 if v in ("fixed", "field") and re.fullmatch(r"[hf]\d+|c\d+_\d+_\d+", str(k))}
        bi = f.get("base_sample_index")
        out.append({
            "name": str(f.get("name") or "가져온 양식")[:60],
            "category": f.get("category") if f.get("category") in categories else "gian",
            "lines": lines,
            "base_sample_index": bi if isinstance(bi, int) and 0 <= bi < len(samples) else None,
            "samples": samples,
        })
    if not out:
        raise PackError("꾸러미에 양식이 없습니다.")
    return out
