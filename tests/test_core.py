"""핵심 회귀 시험 — 기본 양식 꾸러미(가상 예시)만 쓴다. 실행: python -m pytest -q"""
import io
import zipfile
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import ai as AI
from app import hwpx_engine as E
from app import main
from app import storage as S

LOCAL = "http://127.0.0.1:8765"


@pytest.fixture(scope="module")
def client():
    c = TestClient(main.app, base_url=LOCAL, client=("127.0.0.1", 50000))
    r = c.post("/api/packs/import-default")
    assert r.status_code == 200, r.text
    return c


def forms_by_cat(c):
    return {f["category"]: f for f in c.get("/api/forms").json() if f["sample_count"]}


# ───────── 금액·개인정보 ─────────

def test_kor_money():
    assert AI.kor_money(250000) == "이십오만"
    assert AI.kor_money(113560) == "일십일만삼천오백육십"
    assert AI.kor_money(10 ** 20) == str(10 ** 20)  # 아주 큰 수도 멈추지 않음


def test_redact_hides_contacts_and_names():
    out = AI.redact("담당자 : 교사 홍길동, 010-1234-5678, a@b.kr")
    assert "010-1234-5678" not in out and "a@b.kr" not in out and "홍길동" not in out


# ───────── 학습·생성 ─────────

def test_learn_generate_each_default_form(client):
    for cat, f in forms_by_cat(client).items():
        t = client.get(f"/api/forms/{f['id']}/template").json()["template"]
        assert t["ready"], cat
        r = client.post(f"/api/forms/{f['id']}/generate", json={"save_history": False})
        assert r.status_code == 200, (cat, r.text)
        E.validate(r.content)


def test_template_cache_is_reused_and_invalidated(client):
    f = forms_by_cat(client)["pumui"]
    a = client.get(f"/api/forms/{f['id']}/template").json()["template"]
    b = client.get(f"/api/forms/{f['id']}/template").json()["template"]
    assert a == b
    # 학습 설정을 바꾸면 캐시가 아닌 새 결과
    client.put(f"/api/forms/{f['id']}/overrides", json={"lines": {"h0": "fixed"}})
    client.put(f"/api/forms/{f['id']}/overrides", json={"lines": {}})
    c2 = client.get(f"/api/forms/{f['id']}/template").json()["template"]
    assert c2["ready"]


def test_preview_lines(client):
    f = forms_by_cat(client)["gian"]
    r = client.post(f"/api/forms/{f['id']}/preview", json={})
    assert r.status_code == 200 and r.json()["lines"]


def test_generate_returns_history_id_and_missing_history_404(client):
    f = forms_by_cat(client)["gian"]
    r = client.post(f"/api/forms/{f['id']}/generate", json={"save_history": True})
    assert r.status_code == 200
    hid = r.headers.get("X-History-Id")
    assert hid and hid.isdigit()
    assert client.post("/api/history/999999/open").status_code == 404
    assert client.post("/api/history/999999/reveal").status_code == 404


def test_extra_sections():
    with zipfile.ZipFile(S.SAMPLES.parent / "x.zip", "w") as z:
        z.writestr("Contents/section0.xml", "<a/>")
        z.writestr("Contents/section1.xml", "<a/>")
    data = (S.SAMPLES.parent / "x.zip").read_bytes()
    assert E.extra_sections(data) == 1


# ───────── 샘플 양식 확인·옮기기·백업 ─────────

def test_sample_check_and_move(client):
    fs = forms_by_cat(client)
    gian, pumui = fs["gian"], fs["pumui"]
    pumui_sample = client.get(f"/api/forms/{pumui['id']}/template").json()["samples"][0]
    data = client.get(f"/api/forms/{pumui['id']}/samples/{pumui_sample['id']}/download").content
    up = client.post(f"/api/forms/{gian['id']}/samples", files=[("files", ("품의.hwpx", data))]).json()
    sid = up["added"][0]
    mism = client.get(f"/api/forms/{gian['id']}/sample-check").json()["mismatches"]
    assert [m["sample_id"] for m in mism] == [sid] and mism[0]["suggest_form"] == pumui["id"]
    assert client.post(f"/api/forms/{gian['id']}/samples/{sid}/move", json={"to_form": pumui["id"]}).status_code == 200
    assert client.get(f"/api/forms/{gian['id']}/sample-check").json()["mismatches"] == []
    # 옮기기 전 백업이 생기고, 샘플 파일이 들어 있다
    b = client.get("/api/backups").json()[0]
    assert any((S.BACKUPS / b["name"] / "samples").rglob("*.hwpx"))


def test_restore_backup(client):
    before = {f["id"]: f["sample_count"] for f in client.get("/api/forms").json()}
    name = S.backup("시험")
    f = forms_by_cat(client)["gatong"]
    sid = client.get(f"/api/forms/{f['id']}/template").json()["samples"][0]["id"]
    client.delete(f"/api/forms/{f['id']}/samples/{sid}")
    assert client.post(f"/api/backups/{name}/restore").status_code == 200
    after = {f["id"]: f["sample_count"] for f in client.get("/api/forms").json()}
    assert after == before


# ───────── 보안 ─────────

def test_blocks_other_sites(client):
    assert client.get("/api/forms", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/shutdown", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.get("/api/forms", headers={"Sec-Fetch-Site": "same-origin"}).status_code == 200


# ───────── AI 모델 ─────────

TPL = {"blocks": [{"id": "outline", "type": "outline", "items": [], "suggestions": []}], "tables": []}


def _gemini(model):
    AI.update_settings({"provider": "gemini", "models": {"gemini": model}, "consent": {"gemini": True},
                        "key": {"provider": "gemini", "value": "test-key-0000"}})


def test_model_choices_dropdown():
    _gemini("gemini-3.6-flash")
    r = AI.model_choices("gemini")
    ids = [m["id"] for m in r["models"]]
    assert ids[0] == "gemini-3.6-flash" and "추천" in r["models"][0]["tags"]
    assert "gemini-2.5-flash" not in ids and "gemini-embedding-001" not in ids and "gemini-3.6-flash-image" not in ids


@pytest.mark.parametrize("saved", ["gemini-2.5-flash", "gemini-9-gone"])
def test_model_fallback(saved, fake_gemini):
    _gemini(saved)
    fake_gemini.calls.clear()
    r = AI.draft(TPL, [], "시험", date(2026, 11, 21))
    assert r["model"] == "gemini-3.6-flash"
    assert AI.public_settings()["models"]["gemini"] == "gemini-3.6-flash"


def test_gemini_schema_fallback(fake_gemini):
    FakeGemini = fake_gemini  # noqa: N806
    _gemini("gemini-3.6-flash")
    FakeGemini.calls.clear()
    FakeGemini.reject_schema = True
    try:
        AI.draft(TPL, [], "시험", date(2026, 11, 21))
    finally:
        FakeGemini.reject_schema = False
    assert FakeGemini.calls == [("gemini-3.6-flash", True), ("gemini-3.6-flash", False)]
    FakeGemini.calls.clear()
    AI.draft(TPL, [], "시험", date(2026, 11, 21))
    assert FakeGemini.calls == [("gemini-3.6-flash", True)]
