"""기안 학습기 — 이 PC 안에서만(127.0.0.1) 동작하는 로컬 웹 서버."""
from __future__ import annotations

import os
import re
import sys
import threading
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import ai as AI
from . import convert as C
from . import hwpx_engine as E
from . import packs as P
from . import storage as S
from . import system as SYS
from . import updates as U
from .version import __version__

PORT = int(os.environ.get("GIAN_PORT", "8765"))
MAX_UPLOAD = 20 * 1024 * 1024
STATIC = Path(__file__).parent / "static"
RESOURCES = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
DEFAULT_PACK = RESOURCES / "packs" / "기본양식.gianpack"
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}

app = FastAPI(title="기안 학습기", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
S.init()


@app.middleware("http")
async def local_only(request: Request, call_next):
    # 다른 컴퓨터·다른 사이트에서 들어오는 요청 차단
    client = request.client.host if request.client else ""
    if client not in ("127.0.0.1", "::1") or request.headers.get("host", "") not in ALLOWED_HOSTS:
        return JSONResponse({"detail": "이 앱은 이 컴퓨터에서만 사용할 수 있습니다."}, status_code=403)
    origin = request.headers.get("origin")
    if origin and origin not in {f"http://{h}" for h in ALLOWED_HOSTS}:
        return JSONResponse({"detail": "허용되지 않은 요청입니다."}, status_code=403)
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _form_or_404(form_id: int) -> dict:
    f = S.get_form(form_id)
    if not f:
        raise HTTPException(404, "양식을 찾을 수 없습니다.")
    return f


def _learn(form: dict) -> tuple[dict, list[dict]]:
    samples = S.list_samples(form["id"])
    if not samples:
        return {"ready": False}, samples
    try:
        tpl = E.learn([S.sample_bytes(s) for s in samples], [s["id"] for s in samples], form["overrides"])
    except E.HwpxError as e:
        raise HTTPException(400, str(e)) from e
    return tpl, samples


def _base_bytes(tpl: dict, samples: list[dict]) -> bytes:
    s = next(s for s in samples if s["id"] == tpl["base_sample_id"])
    return S.sample_bytes(s)


def _safe_name(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", name or "").strip().strip(".")
    name = re.sub(r"\s+", " ", name)[:120] or "기안"
    return name if name.lower().endswith(".hwpx") else name + ".hwpx"


def _download(data: bytes, filename: str) -> Response:
    return Response(
        data,
        media_type="application/hwp+zip",
        headers={"Content-Disposition": f"attachment; filename=\"download.hwpx\"; filename*=UTF-8''{quote(filename)}"},
    )


class NameIn(BaseModel):
    name: str
    category: str = "gian"


class OverridesIn(BaseModel):
    base_sample_id: int | None = None
    lines: dict[str, str] = {}


class GenerateIn(BaseModel):
    filename: str = ""
    fields: dict[str, str] = {}
    outline: list[dict] | None = None
    attach: list[str] | None = None
    cells: dict[str, str] = {}
    save_history: bool = True


# ───────── API ─────────

@app.get("/api/info")
def info():
    return {"data_dir": str(S.DATA_DIR), "categories": S.CATEGORIES, "version": __version__}


@app.get("/api/forms")
def forms():
    return S.list_forms()


@app.post("/api/forms")
def create_form(body: NameIn):
    name = body.name.strip()[:60]
    if not name:
        raise HTTPException(400, "양식 이름을 입력해 주세요.")
    return {"id": S.create_form(name, body.category)}


@app.patch("/api/forms/{form_id}")
def rename_form(form_id: int, body: NameIn):
    _form_or_404(form_id)
    name = body.name.strip()[:60]
    if not name:
        raise HTTPException(400, "양식 이름을 입력해 주세요.")
    S.rename_form(form_id, name)
    return {"ok": True}


class CategoryIn(BaseModel):
    category: str


@app.put("/api/forms/{form_id}/category")
def move_form(form_id: int, body: CategoryIn):
    _form_or_404(form_id)
    if body.category not in S.CATEGORIES:
        raise HTTPException(400, "알 수 없는 분류입니다.")
    S.set_category(form_id, body.category)
    return {"ok": True}


@app.delete("/api/forms/{form_id}")
def delete_form(form_id: int):
    f = _form_or_404(form_id)
    S.backup(f"양식삭제-{f['name']}")
    S.delete_form(form_id)
    return {"ok": True}


@app.get("/api/forms/{form_id}/template")
def template(form_id: int):
    f = _form_or_404(form_id)
    tpl, samples = _learn(f)
    return {"form": {"id": f["id"], "name": f["name"], "category": f["category"], "overrides": f["overrides"]},
            "template": tpl,
            "samples": [{"id": s["id"], "filename": s["filename"], "created": s["created"]} for s in samples]}


@app.post("/api/forms/{form_id}/samples")
async def upload_samples(form_id: int, files: list[UploadFile] = File(...)):
    f = _form_or_404(form_id)
    added, errors, notes = [], [], []
    for up in files:
        name = Path(up.filename or "sample.hwpx").name
        data = await up.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            errors.append(f"{name}: 20MB를 넘는 파일은 올릴 수 없습니다.")
            continue
        low = name.lower()
        if low.endswith(".hwp"):
            errors.append(f"{name}: 구버전 .hwp 파일입니다. 한글에서 '다른 이름으로 저장 → HWPX'로 바꿔 올려 주세요.")
            continue
        if low.endswith(".ozd"):
            errors.append(f"{name}: .ozd(오즈 문서)는 암호화된 형식이라 직접 읽을 수 없습니다. "
                          "K-에듀파인에서 문서를 연 뒤 오즈 뷰어의 [PDF로 저장](또는 인쇄 → 'Microsoft Print to PDF')으로 "
                          "PDF를 만들어 올려 주세요.")
            continue
        if low.endswith((".odt", ".pdf")):
            try:
                data = C.to_hwpx(name, data)
            except C.ConvertError as e:
                errors.append(f"{name}: {e}")
                continue
            kind = "PDF" if low.endswith(".pdf") else "ODT"
            name = f"{Path(name).stem} ({kind}에서 변환).hwpx"
            notes.append(name)
        try:
            E.learn([data], ["check"])  # 분석 가능한지 미리 확인
        except (E.HwpxError, Exception) as e:  # noqa: BLE001
            msg = str(e) if isinstance(e, E.HwpxError) else "문서를 읽을 수 없습니다."
            errors.append(f"{name}: {msg}")
            continue
        added.append(S.add_sample(form_id, name, data))
    tpl, _ = _learn(f)
    return {"added": added, "errors": errors, "converted": notes, "template": tpl}


@app.delete("/api/forms/{form_id}/samples/{sample_id}")
def delete_sample(form_id: int, sample_id: int):
    f = _form_or_404(form_id)
    S.backup(f"샘플삭제-{f['name']}")
    S.delete_sample(form_id, sample_id)
    ov = f["overrides"]
    if ov.get("base_sample_id") == sample_id:
        ov.pop("base_sample_id")
        S.set_overrides(form_id, ov)
    return {"ok": True}


@app.get("/api/forms/{form_id}/samples/{sample_id}/download")
def download_sample(form_id: int, sample_id: int):
    _form_or_404(form_id)
    s = next((s for s in S.list_samples(form_id) if s["id"] == sample_id), None)
    if not s:
        raise HTTPException(404, "샘플이 없습니다.")
    return _download(S.sample_bytes(s), s["filename"])


@app.put("/api/forms/{form_id}/overrides")
def put_overrides(form_id: int, body: OverridesIn):
    _form_or_404(form_id)
    ov: dict = {"lines": {k: v for k, v in body.lines.items() if v in ("fixed", "field") and re.fullmatch(r"[hf]\d+|c\d+_\d+_\d+", k)}}
    if body.base_sample_id is not None:
        ov["base_sample_id"] = body.base_sample_id
    S.set_overrides(form_id, ov)
    return {"ok": True}


@app.post("/api/forms/{form_id}/reset")
def reset_form(form_id: int):
    f = _form_or_404(form_id)
    name = S.backup(f"초기화-{f['name']}")
    S.reset_form(form_id)
    return {"ok": True, "backup": name}


@app.post("/api/forms/{form_id}/preview")
def preview(form_id: int, body: GenerateIn):
    f = _form_or_404(form_id)
    tpl, samples = _learn(f)
    if not tpl.get("ready"):
        raise HTTPException(400, "먼저 샘플을 올려 학습시켜 주세요.")
    return {"lines": E.preview_text(tpl, body.model_dump(), _base_bytes(tpl, samples))}


@app.post("/api/forms/{form_id}/generate")
def generate(form_id: int, body: GenerateIn):
    f = _form_or_404(form_id)
    tpl, samples = _learn(f)
    if not tpl.get("ready"):
        raise HTTPException(400, "먼저 샘플을 올려 학습시켜 주세요.")
    payload = body.model_dump()
    try:
        data, _ = E.generate(_base_bytes(tpl, samples), tpl, payload)
    except E.HwpxError as e:
        raise HTTPException(400, str(e)) from e
    filename = _safe_name(body.filename or f["name"])
    if body.save_history:
        S.add_history(form_id, filename, data, payload)
    return _download(data, filename)


@app.get("/api/forms/{form_id}/history")
def history(form_id: int):
    _form_or_404(form_id)
    return S.list_history(form_id)


@app.get("/api/history/{hid}/download")
def history_download(hid: int):
    h = S.get_history(hid)
    if not h:
        raise HTTPException(404, "기록이 없습니다.")
    return _download(S.history_bytes(h), h["filename"])


@app.delete("/api/history/{hid}")
def history_delete(hid: int):
    S.delete_history(hid)
    return {"ok": True}


@app.get("/api/backups")
def backups():
    return S.list_backups()


@app.post("/api/backups/{name}/restore")
def restore(name: str):
    try:
        S.restore(name)
    except FileNotFoundError as e:
        raise HTTPException(404, "백업을 찾을 수 없습니다.") from e
    return {"ok": True}


@app.post("/api/reset-all")
def reset_all():
    name = S.backup("전체초기화")
    S.reset_all()
    return {"ok": True, "backup": name}


class PackIn(BaseModel):
    form_ids: list[int]


def _pack_forms(form_ids: list[int]) -> list[dict]:
    out = []
    for fid in dict.fromkeys(form_ids):
        f = _form_or_404(fid)
        samples = S.list_samples(fid)
        if samples:
            out.append({"id": fid, "name": f["name"], "category": f["category"], "overrides": f["overrides"],
                        "samples": [{"id": s["id"], "filename": s["filename"], "data": S.sample_bytes(s)} for s in samples]})
    if not out:
        raise HTTPException(400, "샘플이 있는 양식을 하나 이상 골라 주세요.")
    return out


@app.post("/api/packs/scan")
def pack_scan(body: PackIn):
    res = []
    for f in _pack_forms(body.form_ids):
        items = []
        for k, s in enumerate(f["samples"], 1):
            for hit in P.scan_text(P.doc_strings(s["data"])):
                items.append({**hit, "sample": f"샘플 {k} ({s['filename']})"})
        res.append({"form": f["name"], "category": S.CATEGORIES[f["category"]], "samples": len(f["samples"]), "findings": items})
    return res


@app.post("/api/packs/export")
def pack_export(body: PackIn):
    forms = _pack_forms(body.form_ids)
    data = P.export_pack(forms)
    name = forms[0]["name"] if len(forms) == 1 else f"양식 {len(forms)}개"
    return _download(data, _safe_name(f"{name} 꾸러미").removesuffix(".hwpx") + ".gianpack")


@app.post("/api/packs/import")
async def pack_import(file: UploadFile = File(...)):
    data = await file.read(P.MAX_PACK + 1)
    try:
        forms = P.read_pack(data, S.CATEGORIES)
    except P.PackError as e:
        raise HTTPException(400, str(e)) from e
    S.backup("꾸러미가져오기전")
    return {"imported": S.import_forms(forms)}


@app.get("/api/packs/default")
def pack_default_info():
    return {"available": DEFAULT_PACK.exists()}


@app.post("/api/packs/import-default")
def pack_import_default():
    if not DEFAULT_PACK.exists():
        raise HTTPException(404, "기본 양식 꾸러미가 없습니다.")
    try:
        forms = P.read_pack(DEFAULT_PACK.read_bytes(), S.CATEGORIES)
    except P.PackError as e:
        raise HTTPException(400, str(e)) from e
    S.backup("기본꾸러미가져오기전")
    return {"imported": S.import_forms(forms)}


class AISettingsIn(BaseModel):
    provider: str | None = None
    models: dict[str, str] | None = None
    ollama_url: str | None = None
    key: dict[str, str] | None = None
    consent: dict[str, bool] | None = None


class DraftIn(BaseModel):
    brief: str
    date: str | None = None  # YYYY-MM-DD


@app.get("/api/ai")
def ai_settings():
    return AI.public_settings()


@app.put("/api/ai")
def ai_update(body: AISettingsIn):
    try:
        return AI.update_settings(body.model_dump(exclude_none=True))
    except AI.AIError as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/ai/models")
def ai_models(provider: str):
    if provider not in AI.PROVIDERS:
        raise HTTPException(400, "알 수 없는 AI입니다.")
    try:
        return {"models": AI.list_models(provider)}
    except AI.AIError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/forms/{form_id}/ai-draft")
def ai_draft(form_id: int, body: DraftIn):
    from datetime import date as _date
    f = _form_or_404(form_id)
    tpl, samples = _learn(f)
    if not tpl.get("ready"):
        raise HTTPException(400, "먼저 샘플을 올려 양식을 학습시켜 주세요.")
    try:
        ref = _date.fromisoformat(body.date) if body.date else _date.today()
    except ValueError:
        ref = _date.today()
    try:
        return AI.draft(tpl, [S.sample_bytes(s) for s in samples], body.brief, ref)
    except AI.AIError as e:
        if str(e) == "CONSENT_REQUIRED":
            raise HTTPException(409, "CONSENT_REQUIRED") from e
        raise HTTPException(400, str(e)) from e


class SettingsIn(BaseModel):
    update_check: bool


@app.get("/api/settings")
def get_settings():
    return U.load_settings()


@app.put("/api/settings")
def put_settings(body: SettingsIn):
    return U.save_settings(body.model_dump())


@app.get("/api/update-check")
def update_check(force: bool = False):
    return U.check(force)


class ToggleIn(BaseModel):
    enable: bool


@app.get("/api/system")
def system_status():
    return SYS.status()


@app.post("/api/system/desktop-shortcut")
def desktop_shortcut():
    try:
        SYS.create_desktop()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"바로가기를 만들지 못했습니다: {e}") from e
    return SYS.status()


@app.post("/api/system/autostart")
def autostart(body: ToggleIn):
    try:
        SYS.set_autostart(body.enable)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"자동 실행 설정에 실패했습니다: {e}") from e
    return SYS.status()


@app.post("/api/shutdown")
def shutdown():
    threading.Timer(0.5, lambda: os._exit(0)).start()
    return {"ok": True}


@app.get("/help")
def help_page():
    return FileResponse(STATIC / "help.html")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
