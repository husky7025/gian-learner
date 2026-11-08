"""새 버전 확인: GitHub에 「최신 출시 버전 번호」만 물어본다 (문서 내용·개인정보는 보내지 않음).

- 인터넷이 막혀 있거나 실패하면 조용히 넘어간다.
- 결과는 6시간 동안 기억해 두고 다시 묻지 않는다.
- 설정(settings.json의 update_check)으로 끌 수 있다.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.request

from . import storage as S
from .version import __version__

REPO = "husky7025/gian-learner"
API_URL = os.environ.get("GIAN_UPDATE_URL") or f"https://api.github.com/repos/{REPO}/releases/latest"
PAGE_URL = f"https://github.com/{REPO}/releases/latest"
CACHE_SECONDS = 6 * 3600
SETTINGS = S.DATA_DIR / "settings.json"

_lock = threading.Lock()
_cache: dict = {"at": 0.0, "result": None}


def parse_version(v: str) -> tuple[int, ...] | None:
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", (v or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def is_newer(latest: str, current: str = __version__) -> bool:
    a, b = parse_version(latest), parse_version(current)
    return bool(a and b and a > b)


def load_settings() -> dict:
    try:
        return {"update_check": True, **json.loads(SETTINGS.read_text("utf-8"))}
    except (OSError, ValueError):
        return {"update_check": True}


def save_settings(values: dict) -> dict:
    cur = load_settings()
    cur.update({k: v for k, v in values.items() if k in ("update_check",)})
    SETTINGS.write_text(json.dumps(cur, ensure_ascii=False), "utf-8")
    return cur


def _fetch() -> dict:
    req = urllib.request.Request(API_URL, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"gian-learner/{__version__}",
    })
    with urllib.request.urlopen(req, timeout=5) as r:  # noqa: S310 (고정된 주소)
        data = json.loads(r.read(200_000).decode("utf-8"))
    tag = str(data.get("tag_name", ""))
    url = str(data.get("html_url") or PAGE_URL)
    if not url.startswith(f"https://github.com/{REPO}/"):
        url = PAGE_URL
    return {"latest": tag.lstrip("v"), "url": url, "name": str(data.get("name") or tag)[:80]}


def check(force: bool = False) -> dict:
    base = {"enabled": load_settings()["update_check"], "current": __version__, "newer": False, "page": PAGE_URL}
    if not base["enabled"]:
        return base
    with _lock:
        if not force and _cache["result"] is not None and time.time() - _cache["at"] < CACHE_SECONDS:
            info = _cache["result"]
        else:
            try:
                info = _fetch()
            except Exception:  # noqa: BLE001 — 인터넷 없음·차단 등은 조용히 넘어감
                info = {"error": True}
            _cache.update(at=time.time(), result=info)
    if info.get("error"):
        return {**base, "error": True}
    return {**base, **info, "newer": is_newer(info.get("latest", ""))}
