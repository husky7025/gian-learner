"""AI 기안 작성: 「날짜·간단한 내용」만 받아 학습된 양식대로 기안 전체를 채운다.

지원: 로컬 AI(Ollama, 기본) · Claude(Anthropic) · Gemini(Google) · ChatGPT(OpenAI)
- AI에게는 ① 학습된 양식 구조 ② 샘플 기안 글(온라인 AI면 전화번호·이메일·이름 가림) ③ 사용자 입력만 보낸다.
- 답은 양식 입력칸과 똑같은 JSON으로 받고, 날짜 요일·한글 금액은 프로그램이 다시 계산해 바로잡는다.
- API 키는 이 PC 사용자 계정으로 암호화(Windows DPAPI)해 저장하고, 화면에는 끝 4자리만 보여 준다.
"""
from __future__ import annotations

import base64
import ctypes
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date

from . import hwpx_engine as E
from . import packs as P
from . import storage as S

AI_FILE = S.DATA_DIR / "ai.json"
PROVIDERS = {
    "ollama": {"label": "로컬 AI (Ollama · 이 PC 안에서만)", "needs_key": False, "default_model": "qwen2.5:7b"},
    "claude": {"label": "Claude (Anthropic)", "needs_key": True, "default_model": "claude-opus-5-5"},
    "gemini": {"label": "Gemini (Google)", "needs_key": True, "default_model": "gemini-2.5-flash"},
    "openai": {"label": "ChatGPT (OpenAI)", "needs_key": True, "default_model": "gpt-4.1-mini"},
}
# 시험용으로 주소를 바꿀 수 있게(평소에는 공식 주소)
OPENAI_URL = os.environ.get("GIAN_OPENAI_URL", "https://api.openai.com/v1")
GEMINI_URL = os.environ.get("GIAN_GEMINI_URL", "https://generativelanguage.googleapis.com/v1beta")
CLAUDE_URL = os.environ.get("GIAN_CLAUDE_URL")  # None이면 SDK 기본 주소
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}
MAX_SAMPLE_CHARS = 6000
MAX_SAMPLES = 5


class AIError(RuntimeError):
    pass


# ───────── 키 암호화 저장 (Windows DPAPI, 이 PC·이 사용자만 풀 수 있음) ─────────

class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(data: bytes, protect: bool) -> bytes:
    if sys.platform != "win32":
        return data
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    buf = ctypes.create_string_buffer(data, len(data))
    src = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    out = _Blob()
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    if not fn(ctypes.byref(src), None, None, None, None, 0x1, ctypes.byref(out)):  # 0x1 = UI 없음
        raise AIError("API 키를 암호화/복호화하지 못했습니다.")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def _load() -> dict:
    try:
        cfg = json.loads(AI_FILE.read_text("utf-8"))
    except (OSError, ValueError):
        cfg = {}
    cfg.setdefault("provider", "ollama")
    cfg.setdefault("models", {})
    cfg.setdefault("keys", {})
    cfg.setdefault("consent", {})
    cfg.setdefault("ollama_url", "http://127.0.0.1:11434")
    return cfg


def _save(cfg: dict) -> None:
    AI_FILE.write_text(json.dumps(cfg, ensure_ascii=False), "utf-8")


def _key(cfg: dict, provider: str) -> str:
    enc = cfg["keys"].get(provider)
    if not enc:
        return ""
    try:
        return _dpapi(base64.b64decode(enc), protect=False).decode("utf-8")
    except Exception:  # noqa: BLE001
        return ""


def public_settings() -> dict:
    cfg = _load()
    keys = {}
    for p in PROVIDERS:
        k = _key(cfg, p)
        keys[p] = {"set": bool(k), "hint": ("…" + k[-4:]) if len(k) >= 8 else ""}
    return {
        "provider": cfg["provider"],
        "models": {p: cfg["models"].get(p) or v["default_model"] for p, v in PROVIDERS.items()},
        "ollama_url": cfg["ollama_url"],
        "keys": keys,
        "consent": cfg["consent"],
        "providers": [{"id": p, **{k: v for k, v in info.items() if k != "default_model"}} for p, info in PROVIDERS.items()],
    }


def update_settings(body: dict) -> dict:
    cfg = _load()
    if body.get("provider") in PROVIDERS:
        cfg["provider"] = body["provider"]
    for p, m in (body.get("models") or {}).items():
        if p in PROVIDERS and isinstance(m, str) and re.fullmatch(r"[\w.:/\-]{1,100}", m.strip()):
            cfg["models"][p] = m.strip()
    if isinstance(body.get("ollama_url"), str):
        url = body["ollama_url"].strip().rstrip("/")
        if not re.fullmatch(r"https?://(127\.0\.0\.1|localhost|\[::1\])(:\d{1,5})?", url):
            raise AIError("로컬 AI 주소는 이 PC 주소(http://127.0.0.1:11434 등)만 쓸 수 있습니다.")
        cfg["ollama_url"] = url
    key = body.get("key")
    if isinstance(key, dict) and key.get("provider") in PROVIDERS:
        val = str(key.get("value") or "").strip()
        if val:
            if len(val) > 300 or not re.fullmatch(r"[\x21-\x7e]+", val):
                raise AIError("API 키 형식이 올바르지 않습니다.")
            cfg["keys"][key["provider"]] = base64.b64encode(_dpapi(val.encode("utf-8"), protect=True)).decode()
        else:
            cfg["keys"].pop(key["provider"], None)
    for p, v in (body.get("consent") or {}).items():
        if p in PROVIDERS:
            cfg["consent"][p] = bool(v)
    _save(cfg)
    return public_settings()


# ───────── 개인정보 가리기 (온라인 AI로 보낼 샘플 글) ─────────

def redact(text: str) -> str:
    for kind, rx in P.PII_RULES:
        if kind in ("전화번호", "이메일", "주민등록번호"):
            text = rx.sub(lambda m, k=kind: {"전화번호": "000-0000-0000", "이메일": "OOO@OOO", "주민등록번호": "000000-0000000"}[k], text)
    # 앞에서부터 겹쳐서 찾기("담당자 : 교사 홍길동"의 "교사 홍길동"까지)
    spans = []
    for m in NAME_AFTER_ROLE.finditer(text):
        n = m.group(3)
        if n not in P.NOT_NAME and not n.endswith(P.PARTICLE_END):
            spans.append((m.start(3), m.end(3)))
    for a, b in sorted(set(spans), reverse=True):
        text = text[:a] + "○○○" + text[b:]
    return text


ROLE_WORDS = ("교사", "교감", "교장", "담당자", "담임", "강사", "작성자", "성명", "이름", "보호자")
NAME_AFTER_ROLE = re.compile(r"(?=(" + "|".join(ROLE_WORDS) + r")([ 　]{1,2}[:：]?[ 　]{0,3}|[ 　]*[:：][ 　]{0,3})"
                             r"([가-힣]{2,4})(?=[\s,(·)☏☎/]|$))")
LEADING_NAME = re.compile(r"^[가-힣]{2,4}(?=[\s(,·]|$)")


# ───────── 날짜 요일·한글 금액 바로잡기 ─────────

WEEK = "월화수목금토일"
DATE_FULL = re.compile(r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.\s*\(([월화수목금토일])\)")
DATE_MD = re.compile(r"(?<![\d.]\s)(?<![\d.])(\d{1,2})\.\s*(\d{1,2})\.\s*\(([월화수목금토일])\)")
MONEY = re.compile(r"금\s?([\d,]{1,20})원\s?\(\s?금\s?([가-힣]+)\s?원\s?\)")


def kor_money(n: int) -> str:
    if n == 0:
        return "영"
    d, sm, big = "_일이삼사오육칠팔구", ["천", "백", "십", ""], ["", "만", "억", "조", "경"]
    s, g = "", 0
    while n > 0:
        part, n = n % 10000, n // 10000
        if part:
            ds = f"{part:04d}"
            s = "".join(d[int(c)] + sm[i] for i, c in enumerate(ds) if c != "0") + big[g] + s
        g += 1
    return s


def fix_text(text: str, ref_year: int) -> str:
    def full(m):
        try:
            wd = WEEK[date(int(m.group(1)), int(m.group(2)), int(m.group(3))).weekday()]
            return f"{int(m.group(1))}. {int(m.group(2))}. {int(m.group(3))}.({wd})"
        except ValueError:
            return m.group(0)

    def md(m):
        try:
            wd = WEEK[date(ref_year, int(m.group(1)), int(m.group(2))).weekday()]
            return f"{int(m.group(1))}. {int(m.group(2))}.({wd})"
        except ValueError:
            return m.group(0)

    def money(m):
        digits = m.group(1).replace(",", "")
        if not digits.isdigit():
            return m.group(0)
        n = int(digits)
        return f"금{n:,}원(금{kor_money(n)}원)"

    text = DATE_FULL.sub(full, text)
    text = DATE_MD.sub(md, text)
    return MONEY.sub(money, text)


MARKER_PREFIX = re.compile(r"^\s*(?:\d{1,2}[.)]|[가-하][.)]|\(\d{1,2}\)|\([가-하]\)|[①-⑳㉮-㉻])\s*")


# ───────── 프롬프트 ─────────

SYSTEM = """당신은 대한민국 학교의 공문서(기안문·품의서·가정통신문) 작성 담당자입니다.
교사가 짧게 적은 내용을 받아, 이 학교의 기존 기안 샘플과 같은 문체·항목 구성·표현으로 새 기안을 완성합니다.

규칙
1. 샘플 기안들의 문장 투, 항목 순서, 항목 제목, 끝맺음 표현(예: "…을 다음과 같이 품의하고자 합니다.")을 그대로 따릅니다.
2. 교사가 준 내용에 없는 사실(금액, 수량, 날짜, 시간, 장소, 인원, 사람 이름, 문서번호)은 지어내지 않습니다. 필요한데 모르면 "○○"으로 비워 둡니다.
3. 항목 번호(1. 가. 1) 가) 등)는 쓰지 않습니다. 번호는 프로그램이 depth로 붙입니다(0=1. 1=가. 2=1) 3=가)).
4. outline의 각 항목: label에는 "일시", "장소"처럼 짧은 항목 제목만, value에는 내용만 씁니다. 제목 없는 문장 항목은 label을 ""로 둡니다.
5. "끝." 표시와 붙임 번호는 쓰지 않습니다(자동). attach에는 "견적서 1부"처럼 붙임 문서 이름과 부수만 씁니다. 붙임이 없으면 빈 목록입니다.
6. 날짜는 "2026. 11. 20.(금)", 시간은 "14:00~16:00", 금액은 "금250,000원(금이십오만원)" 형식으로 씁니다.
7. fields의 각 값에는 앞의 제목(예: "제목  ")을 빼고 내용만 씁니다. cells(표 칸)도 내용만 씁니다.
8. 양식 구조에 있는 항목은 되도록 모두 채우고, 교사의 내용에 맞지 않는 항목은 빼거나 바꿔도 됩니다. 필요한 항목은 추가해도 됩니다.
9. filename은 기안 제목(건명)으로 짧게 씁니다.
10. 반드시 지정한 JSON 형식으로만 답합니다."""


def build_schema(tpl: dict) -> dict:
    field_ids = [b["id"] for b in tpl["blocks"] if b["type"] == "field"]
    cell_keys = [c["key"] for t in tpl.get("tables", []) for r in t["rows"] for c in r if c["type"] == "field"]
    obj = lambda keys: {"type": "object", "properties": {k: {"type": "string"} for k in keys},  # noqa: E731
                        "required": keys, "additionalProperties": False}
    return {
        "type": "object",
        "properties": {
            "filename": {"type": "string"},
            "fields": obj(field_ids),
            "outline": {"type": "array", "items": {
                "type": "object",
                "properties": {"depth": {"type": "integer"}, "label": {"type": "string"}, "value": {"type": "string"}},
                "required": ["depth", "label", "value"], "additionalProperties": False}},
            "attach": {"type": "array", "items": {"type": "string"}},
            "cells": obj(cell_keys),
        },
        "required": ["filename", "fields", "outline", "attach", "cells"],
        "additionalProperties": False,
    }


def describe_template(tpl: dict, cloud: bool = False) -> dict:
    def ex(label: str, value: str) -> str:  # 「강사: 홍길동(외부)」처럼 역할 항목의 이름 가리기
        if cloud and any(w in (label or "") for w in ROLE_WORDS):
            return LEADING_NAME.sub("○○○", value or "")
        return value
    out: dict = {"fields": [], "outline": [], "other_items": [], "attach_examples": [], "cells": []}
    for b in tpl["blocks"]:
        if b["type"] == "field":
            out["fields"].append({"id": b["id"], "label": b["label"], "examples": b.get("examples", [])[:3]})
        elif b["type"] == "outline":
            for it in b["items"]:
                if it.get("kind", "item") == "item":
                    out["outline"].append({"depth": it["depth"], "label": it.get("label", ""),
                                           "example": ex(it.get("label", ""), it.get("example", ""))})
            out["other_items"] = [{"depth": s["depth"], "label": s["label"], "example": ex(s["label"], s["example"])} for s in b["suggestions"]]
        elif b["type"] == "attach":
            out["attach_examples"] = b.get("examples", [])
    for t in tpl.get("tables", []):
        for row in t["rows"]:
            head = next((c["text"] for c in row if c["type"] == "fixed" and c["text"].strip()), "")
            for c in row:
                if c["type"] == "field":
                    out["cells"].append({"key": c["key"], "row_title": head, "examples": c.get("examples", [])[:2]})
    return out


def sample_texts(sample_bytes: list[bytes], cloud: bool) -> list[str]:
    res = []
    for b in sample_bytes[-MAX_SAMPLES:]:
        doc = E.load_doc(b)
        lines = list(doc.texts)
        tables = E.doc_tables(doc)
        if tables:
            lines.append("[표]")
            for t in tables:
                for row in t["rows"]:
                    lines.append(" | ".join(c["text"].replace("\n", " / ") for c in row))
        text = "\n".join(lines)[:MAX_SAMPLE_CHARS]
        res.append(redact(text) if cloud else text)
    return res


def build_prompt(tpl: dict, samples: list[str], brief: str, ref: date, cloud: bool = False) -> str:
    structure = json.dumps(describe_template(tpl, cloud), ensure_ascii=False, indent=1)
    if cloud:
        structure = redact(structure)
    parts = [
        f"오늘(기안 기준일): {ref.year}. {ref.month}. {ref.day}.({WEEK[ref.weekday()]})",
        "", "[교사가 적은 내용]", brief.strip(), "",
        "[이 양식의 구조] (fields·cells의 키는 그대로 쓰고, outline은 아래 구성을 참고해 새로 씁니다)",
        structure, "",
        "[이 학교의 기존 기안 샘플] (문체와 구성을 따라 쓰세요. 내용은 베끼지 마세요)",
    ]
    for i, s in enumerate(samples, 1):
        parts += [f"--- 샘플 {i} ---", s]
    return "\n".join(parts)


# ───────── 제공자별 호출 ─────────

def _http_json(url: str, payload: dict | None, headers: dict, timeout: int) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **headers},
                                 method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (정해진 주소만)
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        if e.code in (401, 403):
            raise AIError("API 키가 올바르지 않거나 권한이 없습니다. ⚙ 설정에서 키를 확인해 주세요.") from e
        if e.code == 404:
            raise AIError("모델 이름을 찾을 수 없습니다. ⚙ 설정에서 「목록 불러오기」로 모델을 다시 골라 주세요.") from e
        if e.code == 429:
            raise AIError("사용량 한도에 걸렸습니다. 잠시 뒤 다시 시도하거나 요금제·결제 상태를 확인해 주세요.") from e
        raise AIError(f"AI 서버 오류({e.code}): {body[:200]}") from e
    except urllib.error.URLError as e:
        raise AIError("AI 서버에 연결할 수 없습니다. 인터넷 연결(로컬 AI는 Ollama 실행 여부)을 확인해 주세요.") from e
    except TimeoutError as e:
        raise AIError("AI 응답이 너무 오래 걸립니다. 잠시 뒤 다시 시도해 주세요.") from e


def _claude_client(key: str):
    import anthropic
    kw = {"api_key": key, "timeout": 180.0, "max_retries": 2}
    if CLAUDE_URL:
        kw["base_url"] = CLAUDE_URL
    return anthropic, anthropic.Anthropic(**kw)


def _call_claude(key: str, model: str, prompt: str, schema: dict) -> str:
    anthropic, client = _claude_client(key)
    common = dict(model=model, max_tokens=16000, system=SYSTEM,
                  messages=[{"role": "user", "content": prompt}],
                  output_config={"format": {"type": "json_schema", "schema": schema}})
    try:
        if model in FALLBACK_MODELS:  # 안전 장치로 거절되면 다른 모델로 자동 재시도
            resp = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **common)
        else:
            resp = client.messages.create(**common)
    except anthropic.AuthenticationError as e:
        raise AIError("Claude API 키가 올바르지 않습니다. ⚙ 설정에서 키를 확인해 주세요.") from e
    except anthropic.PermissionDeniedError as e:
        raise AIError("이 API 키로는 해당 모델을 쓸 수 없습니다.") from e
    except anthropic.NotFoundError as e:
        raise AIError("Claude 모델 이름을 찾을 수 없습니다. ⚙ 설정에서 모델을 다시 골라 주세요.") from e
    except anthropic.RateLimitError as e:
        raise AIError("Claude 사용량 한도에 걸렸습니다. 잠시 뒤 다시 시도하거나 결제 상태를 확인해 주세요.") from e
    except anthropic.BadRequestError as e:
        raise AIError(f"Claude 요청 오류: {getattr(e, 'message', e)}") from e
    except anthropic.APIStatusError as e:
        raise AIError(f"Claude 서버 오류({e.status_code}). 잠시 뒤 다시 시도해 주세요.") from e
    except anthropic.APIConnectionError as e:
        raise AIError("Claude에 연결할 수 없습니다. 인터넷 연결을 확인해 주세요.") from e
    if resp.stop_reason == "refusal":
        raise AIError("AI가 이 내용의 작성을 거절했습니다. 내용을 조금 바꿔 다시 시도해 주세요.")
    if resp.stop_reason == "max_tokens":
        raise AIError("AI 답이 너무 길어 잘렸습니다. 내용을 줄여 다시 시도해 주세요.")
    return next((b.text for b in resp.content if b.type == "text"), "")


def _call_openai(key: str, model: str, prompt: str, schema: dict) -> str:
    data = _http_json(f"{OPENAI_URL}/chat/completions", {
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        "response_format": {"type": "json_schema", "json_schema": {"name": "gian_draft", "schema": schema, "strict": True}},
    }, {"Authorization": f"Bearer {key}"}, 180)
    ch = (data.get("choices") or [{}])[0]
    if ch.get("message", {}).get("refusal"):
        raise AIError("AI가 이 내용의 작성을 거절했습니다.")
    return ch.get("message", {}).get("content") or ""


def _call_gemini(key: str, model: str, prompt: str, schema: dict) -> str:
    data = _http_json(f"{GEMINI_URL}/models/{model}:generateContent", {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": prompt + "\n\n[답 형식(JSON 스키마)]\n" + json.dumps(schema, ensure_ascii=False)}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.3},
    }, {"x-goog-api-key": key}, 180)
    cands = data.get("candidates") or []
    if not cands:
        raise AIError("Gemini가 답을 주지 않았습니다(안전 정책으로 막혔을 수 있습니다).")
    return "".join(p.get("text", "") for p in cands[0].get("content", {}).get("parts", []))


def _call_ollama(url: str, model: str, prompt: str, schema: dict) -> str:
    try:
        data = _http_json(f"{url}/api/chat", {
            "model": model, "stream": False, "format": schema,
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
            "options": {"temperature": 0.3, "num_ctx": 16384},
        }, {}, 600)
    except AIError as e:
        if "연결할 수 없습니다" in str(e):
            raise AIError("로컬 AI(Ollama)가 실행 중이 아닙니다. Ollama를 설치·실행했는지 확인해 주세요. (📖 사용설명서 → AI로 작성하기)") from e
        if "모델 이름" in str(e):
            raise AIError(f"로컬 AI에 「{model}」 모델이 없습니다. 명령 창에서 「ollama pull {model}」로 받거나, ⚙ 설정에서 설치된 모델을 고르세요.") from e
        raise
    return (data.get("message") or {}).get("content", "")


def list_models(provider: str) -> list[str]:
    cfg = _load()
    key = _key(cfg, provider)
    if PROVIDERS[provider]["needs_key"] and not key:
        raise AIError("먼저 API 키를 저장해 주세요.")
    if provider == "ollama":
        try:
            data = _http_json(f"{cfg['ollama_url']}/api/tags", None, {}, 5)
        except AIError as e:
            raise AIError("로컬 AI(Ollama)가 실행 중이 아닙니다. Ollama를 설치·실행했는지 확인해 주세요.") from e
        return sorted(m.get("name", "") for m in data.get("models", []) if m.get("name"))
    if provider == "claude":
        anthropic, client = _claude_client(key)
        try:
            return [m.id for m in client.models.list()]
        except anthropic.AuthenticationError as e:
            raise AIError("Claude API 키가 올바르지 않습니다.") from e
        except anthropic.APIConnectionError as e:
            raise AIError("Claude에 연결할 수 없습니다. 인터넷 연결을 확인해 주세요.") from e
        except anthropic.APIStatusError as e:
            raise AIError(f"Claude 서버 오류({e.status_code}).") from e
    if provider == "openai":
        data = _http_json(f"{OPENAI_URL}/models", None, {"Authorization": f"Bearer {key}"}, 20)
        ids = [m.get("id", "") for m in data.get("data", [])]
        return sorted(i for i in ids if re.match(r"(gpt|o\d|chatgpt)", i) and not re.search(r"audio|realtime|tts|image|transcribe|search", i))
    data = _http_json(f"{GEMINI_URL}/models?pageSize=200", None, {"x-goog-api-key": key}, 20)
    return sorted(m["name"].removeprefix("models/") for m in data.get("models", [])
                  if "generateContent" in m.get("supportedGenerationMethods", []) and "gemini" in m.get("name", ""))


# ───────── 기안 작성 ─────────

def _parse_json(text: str) -> dict:
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        return json.loads(t)
    except ValueError:
        m = re.search(r"\{.*\}", t, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except ValueError:
                pass
    raise AIError("AI 답을 읽을 수 없습니다. 다시 시도해 주세요. (로컬 AI라면 더 큰 모델을 고르면 나아집니다)")


def clean_result(raw: dict, tpl: dict, ref: date) -> dict:
    fx = lambda s: fix_text(str(s or "").strip(), ref.year)  # noqa: E731
    field_ids = {b["id"] for b in tpl["blocks"] if b["type"] == "field"}
    cell_keys = {c["key"] for t in tpl.get("tables", []) for r in t["rows"] for c in r if c["type"] == "field"}
    fields = {k: fx(v) for k, v in (raw.get("fields") or {}).items() if k in field_ids}
    for b in tpl["blocks"]:  # 제목(접두어)을 AI가 같이 써 넣은 경우 떼기
        if b["type"] == "field" and b["id"] in fields and b.get("prefix", "").strip():
            fields[b["id"]] = re.sub(r"^\s*" + re.escape(b["prefix"].strip()) + r"\s*", "", fields[b["id"]])
    outline = []
    for it in raw.get("outline") or []:
        if not isinstance(it, dict):
            continue
        try:
            depth = max(0, min(int(it.get("depth", 0)), 7))
        except (TypeError, ValueError):
            depth = 0
        label = MARKER_PREFIX.sub("", str(it.get("label") or "")).strip().rstrip(":：").strip()
        value = fx(MARKER_PREFIX.sub("", str(it.get("value") or "")))
        value = re.sub(r"\s*끝\.?\s*$", "", value)
        if label or value:
            outline.append({"kind": "item", "depth": depth, "label": label[:40], "value": value})
    attach = []
    for x in raw.get("attach") or []:
        x = re.sub(r"^\s*붙\s?임\s*", "", str(x))
        x = re.sub(r"^\s*\d{1,2}\.\s*", "", x)
        x = re.sub(r"\s*끝\.?\s*$", "", x).strip().rstrip(".")
        if x:
            attach.append(x)
    cells = {k: fx(v) for k, v in (raw.get("cells") or {}).items() if k in cell_keys}
    filename = re.sub(r'[\\/:*?"<>|]+', " ", str(raw.get("filename") or "")).strip()[:80]
    return {"filename": filename, "fields": fields, "outline": outline, "attach": attach, "cells": cells}


def draft(tpl: dict, sample_bytes: list[bytes], brief: str, ref: date) -> dict:
    if not brief.strip():
        raise AIError("작성할 내용을 적어 주세요.")
    cfg = _load()
    provider = cfg["provider"]
    model = cfg["models"].get(provider) or PROVIDERS[provider]["default_model"]
    cloud = provider != "ollama"
    if cloud and not cfg["consent"].get(provider):
        raise AIError("CONSENT_REQUIRED")
    key = _key(cfg, provider)
    if PROVIDERS[provider]["needs_key"] and not key:
        raise AIError(f"{PROVIDERS[provider]['label']} API 키가 없습니다. ⚙ 설정 → AI 작성 설정에서 키를 넣어 주세요.")
    schema = build_schema(tpl)
    prompt = build_prompt(tpl, sample_texts(sample_bytes, cloud), brief[:4000], ref, cloud)
    if provider == "claude":
        text = _call_claude(key, model, prompt, schema)
    elif provider == "openai":
        text = _call_openai(key, model, prompt, schema)
    elif provider == "gemini":
        text = _call_gemini(key, model, prompt, schema)
    else:
        text = _call_ollama(cfg["ollama_url"], model, prompt, schema)
    result = clean_result(_parse_json(text), tpl, ref)
    if not result["outline"] and not result["fields"] and not result["cells"]:
        raise AIError("AI가 빈 답을 주었습니다. 내용을 조금 더 자세히 적어 다시 시도해 주세요.")
    return {**result, "provider": provider, "model": model}
