"""로컬 저장소: %LOCALAPPDATA%\\기안학습기 (OneDrive 동기화 폴더 밖, 이 PC에만 저장)."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(os.environ.get("GIAN_DATA_DIR") or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "기안학습기")
DB_PATH = DATA_DIR / "data.db"
SAMPLES = DATA_DIR / "samples"
OUTPUTS = DATA_DIR / "outputs"
BACKUPS = DATA_DIR / "backups"
MAX_BACKUPS = 20          # 중요한 백업(초기화·삭제·복원·가져오기 전 등)
MAX_ROUTINE_BACKUPS = 10  # 자주 생기는 백업(샘플 삭제·옮기기) — 중요한 백업을 밀어내지 않게 따로 센다
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
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    """연결 → 성공하면 저장(commit), 실패하면 되돌림(rollback) → 항상 닫기.
    (sqlite3의 `with con:`은 닫아 주지 않아 Windows에서 파일 잠금이 남을 수 있다)"""
    con = connect()
    try:
        with con:
            yield con
    finally:
        con.close()


def atomic_write_text(path: Path, text: str) -> None:
    """임시 파일에 다 쓴 뒤 바꿔치기 — 쓰는 도중 꺼져도 원래 파일이 깨지지 않는다."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, "utf-8")
    os.replace(tmp, path)


def init() -> None:
    for d in (DATA_DIR, SAMPLES, OUTPUTS, BACKUPS):
        d.mkdir(parents=True, exist_ok=True)
    with db() as con:
        con.executescript(SCHEMA)
        cols = [r["name"] for r in con.execute("PRAGMA table_info(forms)")]
        if "category" not in cols:  # 1단계에서 만든 DB 이어서 쓰기
            con.execute("ALTER TABLE forms ADD COLUMN category TEXT NOT NULL DEFAULT 'gian'")
        con.execute("CREATE INDEX IF NOT EXISTS idx_samples_form ON samples(form_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_history_form ON history(form_id)")
    ensure_defaults()


def ensure_defaults() -> None:
    """분류마다 양식이 하나도 없으면 기본 양식을 하나 만든다."""
    with _lock, db() as con:
        for key, label in CATEGORIES.items():
            if not con.execute("SELECT 1 FROM forms WHERE category=?", (key,)).fetchone():
                con.execute("INSERT INTO forms(name, category, created) VALUES (?, ?, ?)", (label, key, now()))


# ───────── 양식 ─────────

def list_forms() -> list[dict]:
    with db() as con:
        rows = con.execute(
            "SELECT f.id, f.name, f.category, f.created, (SELECT COUNT(*) FROM samples s WHERE s.form_id=f.id) AS sample_count "
            "FROM forms f ORDER BY f.id"
        ).fetchall()
    return [dict(r) for r in rows]


def get_form(form_id: int) -> dict | None:
    with db() as con:
        r = con.execute("SELECT * FROM forms WHERE id=?", (form_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["overrides"] = json.loads(d["overrides"] or "{}")
    return d


def create_form(name: str, category: str = "gian") -> int:
    if category not in CATEGORIES:
        category = "gian"
    with _lock, db() as con:
        cur = con.execute("INSERT INTO forms(name, category, created) VALUES (?, ?, ?)", (name, category, now()))
        return cur.lastrowid


def rename_form(form_id: int, name: str) -> None:
    with _lock, db() as con:
        con.execute("UPDATE forms SET name=? WHERE id=?", (name, form_id))


def set_category(form_id: int, category: str) -> None:
    if category not in CATEGORIES:
        raise ValueError(category)
    with _lock, db() as con:
        con.execute("UPDATE forms SET category=? WHERE id=?", (category, form_id))


def set_overrides(form_id: int, overrides: dict) -> None:
    with _lock, db() as con:
        con.execute("UPDATE forms SET overrides=? WHERE id=?", (json.dumps(overrides, ensure_ascii=False), form_id))


def delete_form(form_id: int) -> None:
    with _lock:
        _remove_form_files(form_id)
        with db() as con:
            con.execute("DELETE FROM forms WHERE id=?", (form_id,))


def reset_form(form_id: int) -> None:
    """학습 내용(샘플·수정 설정)만 지우고 양식 이름과 생성 이력은 남긴다."""
    with _lock:
        shutil.rmtree(SAMPLES / str(form_id), ignore_errors=True)
        with db() as con:
            con.execute("DELETE FROM samples WHERE form_id=?", (form_id,))
            con.execute("UPDATE forms SET overrides='{}' WHERE id=?", (form_id,))


def _remove_form_files(form_id: int) -> None:
    shutil.rmtree(SAMPLES / str(form_id), ignore_errors=True)
    with db() as con:
        for r in con.execute("SELECT stored FROM history WHERE form_id=?", (form_id,)):
            (OUTPUTS / r["stored"]).unlink(missing_ok=True)


# ───────── 샘플 ─────────

def add_sample(form_id: int, filename: str, data: bytes) -> int:
    with _lock:
        folder = SAMPLES / str(form_id)
        folder.mkdir(parents=True, exist_ok=True)
        with db() as con:
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
    with db() as con:
        rows = con.execute("SELECT * FROM samples WHERE form_id=? ORDER BY id", (form_id,)).fetchall()
    return [dict(r) for r in rows]


def sample_bytes(sample: dict) -> bytes:
    return (SAMPLES / sample["stored"]).read_bytes()


def sample_stamp(sample: dict) -> tuple:
    """캐시 열쇠: 파일이 바뀌면(복원·교체) 같이 바뀐다."""
    try:
        st = (SAMPLES / sample["stored"]).stat()
        return (sample["id"], sample["stored"], st.st_size, st.st_mtime_ns)
    except OSError:
        return (sample["id"], sample["stored"], -1, -1)


def _link_tree(src: Path, dst: Path) -> None:
    """백업용 복사: 같은 디스크면 하드링크(용량·시간 거의 0), 안 되면 복사.
    샘플·생성 파일은 한 번 쓰면 고치지 않으므로 하드링크로 충분하다."""
    dst.mkdir(parents=True, exist_ok=True)
    if not src.exists():
        return
    for p in src.rglob("*"):
        q = dst / p.relative_to(src)
        if p.is_dir():
            q.mkdir(parents=True, exist_ok=True)
            continue
        q.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(p, q)
        except OSError:
            shutil.copy2(p, q)


def move_sample(form_id: int, sample_id: int, to_form: int) -> None:
    with _lock, db() as con:
        r = con.execute("SELECT stored FROM samples WHERE id=? AND form_id=?", (sample_id, form_id)).fetchone()
        if not r:
            return
        folder = SAMPLES / str(to_form)
        folder.mkdir(parents=True, exist_ok=True)
        stored = f"{to_form}/{sample_id}.hwpx"
        shutil.move(str(SAMPLES / r["stored"]), str(SAMPLES / stored))
        con.execute("UPDATE samples SET form_id=?, stored=? WHERE id=?", (to_form, stored, sample_id))


def delete_sample(form_id: int, sample_id: int) -> None:
    with _lock, db() as con:
        r = con.execute("SELECT stored FROM samples WHERE id=? AND form_id=?", (sample_id, form_id)).fetchone()
        if r:
            (SAMPLES / r["stored"]).unlink(missing_ok=True)
            con.execute("DELETE FROM samples WHERE id=?", (sample_id,))


def import_forms(forms: list[dict]) -> list[dict]:
    """꾸러미에서 읽은 양식을 저장. 같은 분류·같은 이름의 빈 양식이 있으면 거기에 채운다."""
    result = []
    with _lock:
        for f in forms:
            with db() as con:
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
    with _lock, db() as con:
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
    with db() as con:
        rows = con.execute(
            "SELECT id, filename, payload, created FROM history WHERE form_id=? ORDER BY id DESC LIMIT 200", (form_id,)
        ).fetchall()
    return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]


def get_history(hid: int) -> dict | None:
    with db() as con:
        r = con.execute("SELECT * FROM history WHERE id=?", (hid,)).fetchone()
    return dict(r) if r else None


def history_bytes(h: dict) -> bytes:
    return (OUTPUTS / h["stored"]).read_bytes()


def delete_history(hid: int) -> None:
    with _lock, db() as con:
        r = con.execute("SELECT stored FROM history WHERE id=?", (hid,)).fetchone()
        if r:
            (OUTPUTS / r["stored"]).unlink(missing_ok=True)
            con.execute("DELETE FROM history WHERE id=?", (hid,))


# ───────── 백업·초기화·복원 ─────────

def _backup_info(p: Path) -> dict:
    try:
        return json.loads((p / "info.json").read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _prune_backups() -> None:
    """중요한 백업과 자주 생기는 백업을 따로 세어 오래된 것부터 지운다."""
    groups: dict[str, list[Path]] = {"important": [], "routine": []}
    for p in sorted(p for p in BACKUPS.iterdir() if p.is_dir()):
        kind = "routine" if _backup_info(p).get("kind") == "routine" else "important"
        groups[kind].append(p)
    for kind, limit in (("important", MAX_BACKUPS), ("routine", MAX_ROUTINE_BACKUPS)):
        for p in groups[kind][:-limit]:
            shutil.rmtree(p, ignore_errors=True)


def backup(reason: str, routine: bool = False) -> str:
    """routine=True: 샘플 삭제·옮기기처럼 자주 생기는 백업 (중요한 백업 개수에 넣지 않음)."""
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
        _link_tree(SAMPLES, dest / "samples")
        _link_tree(OUTPUTS, dest / "outputs")
        info = {"reason": reason, "created": now(), "kind": "routine" if routine else "important"}
        (dest / "info.json").write_text(json.dumps(info, ensure_ascii=False), "utf-8")
        _prune_backups()
        return name


def list_backups() -> list[dict]:
    res = []
    for p in sorted((p for p in BACKUPS.iterdir() if p.is_dir()), reverse=True):
        info = _backup_info(p)
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
        with db() as con:
            con.execute("DELETE FROM history")
            con.execute("DELETE FROM samples")
            con.execute("DELETE FROM forms")
            con.execute("DELETE FROM sqlite_sequence")
        for target in (SAMPLES, OUTPUTS):
            shutil.rmtree(target, ignore_errors=True)
            target.mkdir(parents=True, exist_ok=True)
    ensure_defaults()
