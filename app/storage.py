"""로컬 저장소: %LOCALAPPDATA%\\기안학습기 (OneDrive 동기화 폴더 밖, 이 PC에만 저장)."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(os.environ.get("GIAN_DATA_DIR") or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "기안학습기")
DB_PATH = DATA_DIR / "data.db"
SAMPLES = DATA_DIR / "samples"
OUTPUTS = DATA_DIR / "outputs"
BACKUPS = DATA_DIR / "backups"
MAX_BACKUPS = 20
CATEGORIES = {"gian": "기안", "pumui": "품의", "gatong": "가정통신문"}

_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS forms (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'gian',
  overrides TEXT NOT NULL DEFAULT '{}',
  created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS samples (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  form_id INTEGER NOT NULL REFERENCES forms(id) ON DELETE CASCADE,
  filename TEXT NOT NULL,
  stored TEXT NOT NULL,
  created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  form_id INTEGER NOT NULL REFERENCES forms(id) ON DELETE CASCADE,
  filename TEXT NOT NULL,
  stored TEXT NOT NULL,
  payload TEXT NOT NULL,
  created TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init() -> None:
    for d in (DATA_DIR, SAMPLES, OUTPUTS, BACKUPS):
        d.mkdir(parents=True, exist_ok=True)
    with connect() as con:
        con.executescript(SCHEMA)
        cols = [r["name"] for r in con.execute("PRAGMA table_info(forms)")]
        if "category" not in cols:  # 1단계에서 만든 DB 이어서 쓰기
            con.execute("ALTER TABLE forms ADD COLUMN category TEXT NOT NULL DEFAULT 'gian'")
    ensure_defaults()


def ensure_defaults() -> None:
    """분류마다 양식이 하나도 없으면 기본 양식을 하나 만든다."""
    with _lock, connect() as con:
        for key, label in CATEGORIES.items():
            if not con.execute("SELECT 1 FROM forms WHERE category=?", (key,)).fetchone():
                con.execute("INSERT INTO forms(name, category, created) VALUES (?, ?, ?)", (label, key, now()))


# ───────── 양식 ─────────

def list_forms() -> list[dict]:
    with connect() as con:
        rows = con.execute(
            "SELECT f.id, f.name, f.category, f.created, (SELECT COUNT(*) FROM samples s WHERE s.form_id=f.id) AS sample_count "
            "FROM forms f ORDER BY f.id"
        ).fetchall()
    return [dict(r) for r in rows]


def get_form(form_id: int) -> dict | None:
    with connect() as con:
        r = con.execute("SELECT * FROM forms WHERE id=?", (form_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["overrides"] = json.loads(d["overrides"] or "{}")
    return d


def create_form(name: str, category: str = "gian") -> int:
    if category not in CATEGORIES:
        category = "gian"
    with _lock, connect() as con:
        cur = con.execute("INSERT INTO forms(name, category, created) VALUES (?, ?, ?)", (name, category, now()))
        return cur.lastrowid


def rename_form(form_id: int, name: str) -> None:
    with _lock, connect() as con:
        con.execute("UPDATE forms SET name=? WHERE id=?", (name, form_id))


def set_category(form_id: int, category: str) -> None:
    if category not in CATEGORIES:
        raise ValueError(category)
    with _lock, connect() as con:
        con.execute("UPDATE forms SET category=? WHERE id=?", (category, form_id))


def set_overrides(form_id: int, overrides: dict) -> None:
    with _lock, connect() as con:
        con.execute("UPDATE forms SET overrides=? WHERE id=?", (json.dumps(overrides, ensure_ascii=False), form_id))


def delete_form(form_id: int) -> None:
    with _lock:
        _remove_form_files(form_id)
        with connect() as con:
            con.execute("DELETE FROM forms WHERE id=?", (form_id,))


def reset_form(form_id: int) -> None:
    """학습 내용(샘플·수정 설정)만 지우고 양식 이름과 생성 이력은 남긴다."""
    with _lock:
        shutil.rmtree(SAMPLES / str(form_id), ignore_errors=True)
        with connect() as con:
            con.execute("DELETE FROM samples WHERE form_id=?", (form_id,))
            con.execute("UPDATE forms SET overrides='{}' WHERE id=?", (form_id,))


def _remove_form_files(form_id: int) -> None:
    shutil.rmtree(SAMPLES / str(form_id), ignore_errors=True)
    with connect() as con:
        for r in con.execute("SELECT stored FROM history WHERE form_id=?", (form_id,)):
            (OUTPUTS / r["stored"]).unlink(missing_ok=True)


# ───────── 샘플 ─────────

def add_sample(form_id: int, filename: str, data: bytes) -> int:
    with _lock:
        folder = SAMPLES / str(form_id)
        folder.mkdir(parents=True, exist_ok=True)
        with connect() as con:
            cur = con.execute(
                "INSERT INTO samples(form_id, filename, stored, created) VALUES (?, ?, '', ?)",
                (form_id, filename, now()),
            )
            sid = cur.lastrowid
            stored = f"{form_id}/{sid}.hwpx"
            (SAMPLES / stored).write_bytes(data)
            con.execute("UPDATE samples SET stored=? WHERE id=?", (stored, sid))
        return sid


def list_samples(form_id: int) -> list[dict]:
    with connect() as con:
        rows = con.execute("SELECT * FROM samples WHERE form_id=? ORDER BY id", (form_id,)).fetchall()
    return [dict(r) for r in rows]


def sample_bytes(sample: dict) -> bytes:
    return (SAMPLES / sample["stored"]).read_bytes()


def delete_sample(form_id: int, sample_id: int) -> None:
    with _lock, connect() as con:
        r = con.execute("SELECT stored FROM samples WHERE id=? AND form_id=?", (sample_id, form_id)).fetchone()
        if r:
            (SAMPLES / r["stored"]).unlink(missing_ok=True)
            con.execute("DELETE FROM samples WHERE id=?", (sample_id,))


def import_forms(forms: list[dict]) -> list[dict]:
    """꾸러미에서 읽은 양식을 저장. 같은 분류·같은 이름의 빈 양식이 있으면 거기에 채운다."""
    result = []
    with _lock:
        for f in forms:
            with connect() as con:
                row = con.execute(
                    "SELECT f.id FROM forms f WHERE f.category=? AND f.name=? "
                    "AND NOT EXISTS (SELECT 1 FROM samples s WHERE s.form_id=f.id) ORDER BY f.id LIMIT 1",
                    (f["category"], f["name"])).fetchone()
                names = {r["name"] for r in con.execute("SELECT name FROM forms WHERE category=?", (f["category"],))}
            if row:
                fid, name = row["id"], f["name"]
            else:
                name = f["name"]
                k = 2
                while name in names:
                    name = f"{f['name']} ({k})"
                    k += 1
                fid = create_form(name, f["category"])
            ids = [add_sample(fid, s["filename"], s["data"]) for s in f["samples"]]
            ov = {"lines": f.get("lines", {})}
            if f.get("base_sample_index") is not None:
                ov["base_sample_id"] = ids[f["base_sample_index"]]
            set_overrides(fid, ov)
            result.append({"id": fid, "name": name, "category": f["category"], "samples": len(ids)})
    return result


# ───────── 생성 이력 ─────────

def add_history(form_id: int, filename: str, data: bytes, payload: dict) -> int:
    with _lock, connect() as con:
        cur = con.execute(
            "INSERT INTO history(form_id, filename, stored, payload, created) VALUES (?, ?, '', ?, ?)",
            (form_id, filename, json.dumps(payload, ensure_ascii=False), now()),
        )
        hid = cur.lastrowid
        stored = f"{hid}.hwpx"
        (OUTPUTS / stored).write_bytes(data)
        con.execute("UPDATE history SET stored=? WHERE id=?", (stored, hid))
        return hid


def list_history(form_id: int) -> list[dict]:
    with connect() as con:
        rows = con.execute(
            "SELECT id, filename, payload, created FROM history WHERE form_id=? ORDER BY id DESC LIMIT 200", (form_id,)
        ).fetchall()
    return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]


def get_history(hid: int) -> dict | None:
    with connect() as con:
        r = con.execute("SELECT * FROM history WHERE id=?", (hid,)).fetchone()
    return dict(r) if r else None


def history_bytes(h: dict) -> bytes:
    return (OUTPUTS / h["stored"]).read_bytes()


def delete_history(hid: int) -> None:
    with _lock, connect() as con:
        r = con.execute("SELECT stored FROM history WHERE id=?", (hid,)).fetchone()
        if r:
            (OUTPUTS / r["stored"]).unlink(missing_ok=True)
            con.execute("DELETE FROM history WHERE id=?", (hid,))


# ───────── 백업·초기화·복원 ─────────

def backup(reason: str) -> str:
    with _lock:
        name = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        dest = BACKUPS / name
        dest.mkdir(parents=True)
        src = connect()
        dst = sqlite3.connect(dest / "data.db")
        with dst:
            src.backup(dst)
        src.close()
        dst.close()
        shutil.copytree(SAMPLES, dest / "samples")
        shutil.copytree(OUTPUTS, dest / "outputs")
        (dest / "info.json").write_text(json.dumps({"reason": reason, "created": now()}, ensure_ascii=False), "utf-8")
        olds = sorted(p for p in BACKUPS.iterdir() if p.is_dir())
        for p in olds[:-MAX_BACKUPS]:
            shutil.rmtree(p, ignore_errors=True)
        return name


def list_backups() -> list[dict]:
    res = []
    for p in sorted((p for p in BACKUPS.iterdir() if p.is_dir()), reverse=True):
        try:
            info = json.loads((p / "info.json").read_text("utf-8"))
        except (OSError, ValueError):
            info = {}
        res.append({"name": p.name, "reason": info.get("reason", ""), "created": info.get("created", p.name)})
    return res


def restore(name: str) -> None:
    src = BACKUPS / name
    if not name or "/" in name or "\\" in name or ".." in name or not (src / "data.db").exists():
        raise FileNotFoundError(name)
    with _lock:
        backup("복원전자동백업")
        s = sqlite3.connect(src / "data.db")
        d = connect()
        with d:
            s.backup(d)
        s.close()
        d.close()
        for sub, target in (("samples", SAMPLES), ("outputs", OUTPUTS)):
            shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(src / sub, target)
    init()


def reset_all() -> None:
    with _lock:
        with connect() as con:
            con.execute("DELETE FROM history")
            con.execute("DELETE FROM samples")
            con.execute("DELETE FROM forms")
            con.execute("DELETE FROM sqlite_sequence")
        for target in (SAMPLES, OUTPUTS):
            shutil.rmtree(target, ignore_errors=True)
            target.mkdir(parents=True, exist_ok=True)
    ensure_defaults()
