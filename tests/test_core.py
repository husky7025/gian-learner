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


def test_weekday_fix_crosses_year():
    # 12월에 쓰는 1월 행사: 2027. 1. 5.는 화요일 — 올해(2026) 기준 「월」로 잘못 바꾸면 안 된다
    assert AI.fix_text("1. 5.(월)", date(2026, 12, 20)) == "1. 5.(화)"
    # 1월에 쓰는 지난 12월 결과 보고: 2025. 12. 30.는 화요일
    assert AI.fix_text("12. 30.(목)", date(2026, 1, 3)) == "12. 30.(화)"
    # 같은 해 날짜와 연도를 준 경우는 그대로 계산
    assert AI.fix_text("11. 20.(월)", date(2026, 11, 21)) == "11. 20.(금)"
    assert AI.fix_text("2027. 1. 5.(월)", date(2026, 12, 20)) == "2027. 1. 5.(화)"


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


def test_category_prompts():
    gatong = AI.system_prompt("gatong")
    assert "학부모님께 직접 배부하는 가정통신문" in gatong and "하고자 합니다\"" not in gatong.split("9.")[0]
    gian = AI.system_prompt("gian")
    assert "가정통신문을 배부" in gian and "기안문" in gian
    assert "품의하고자" in AI.system_prompt("pumui")
    assert AI.system_prompt("없는분류") == gian
    p = AI.build_prompt(TPL, ["샘플 글"], "안내", date(2026, 11, 21), category="gatong")
    assert "기존 가정통신문 샘플" in p and "오늘(발행일)" in p


# ───────── AI 참고 서류 ─────────

def test_extract_ref_text():
    from app import convert as C
    assert "과학실" in C.extract_ref_text("안내.txt", "장소: 과학실".encode("utf-8"))
    assert "견적" in C.extract_ref_text("견적.txt", "품목 견적서".encode("cp949"))
    with pytest.raises(C.ConvertError):
        C.extract_ref_text("구버전.hwp", b"dummy")
    with pytest.raises(C.ConvertError):
        C.extract_ref_text("오즈.ozd", b"dummy")


def test_ai_draft_with_ref_file_only_and_redact(client, fake_gemini):
    _gemini("gemini-3.6-flash")
    f = forms_by_cat(client)["pumui"]
    ref_body = "견적서\n품목: 비커 10개\n금액: 150,000원\n담당자: 교사 홍길동 (010-9876-5432)".encode("utf-8")
    r = client.post(
        f"/api/forms/{f['id']}/ai-draft",
        data={"brief": "", "date": "2026-11-21"},
        files=[("files", ("견적서.txt", ref_body, "text/plain"))],
    )
    assert r.status_code == 200, r.text
    assert r.json()["ref_count"] == 1
    assert "참고 서류: 견적서.txt" in fake_gemini.last_prompt
    assert "비커 10개" in fake_gemini.last_prompt
    assert "010-9876-5432" not in fake_gemini.last_prompt
    assert "홍길동" not in fake_gemini.last_prompt


def test_ai_draft_rejects_hwp_ref(client):
    _gemini("gemini-3.6-flash")
    f = forms_by_cat(client)["gian"]
    r = client.post(
        f"/api/forms/{f['id']}/ai-draft",
        data={"brief": "기안 써줘"},
        files=[("files", ("공문.hwp", b"old-hwp", "application/octet-stream"))],
    )
    assert r.status_code == 400
    assert "HWPX" in r.json()["detail"]


def test_ai_draft_vision_image_gemini_ok_and_ollama_blocked(client, fake_gemini):
    from app import packs as P
    png = P.blank_png()
    f = forms_by_cat(client)["pumui"]
    _gemini("gemini-3.6-flash")
    fake_gemini.last_media_count = 0
    r = client.post(
        f"/api/forms/{f['id']}/ai-draft",
        data={"brief": ""},
        files=[("files", ("견적서.png", png, "image/png"))],
    )
    assert r.status_code == 200, r.text
    assert r.json()["vision_count"] == 1
    assert fake_gemini.last_media_count == 1

    # 로컬 AI(Ollama)에서는 Gemini/Claude 전용 안내와 함께 차단
    AI.update_settings({"provider": "ollama"})
    try:
        r2 = client.post(
            f"/api/forms/{f['id']}/ai-draft",
            data={"brief": ""},
            files=[("files", ("견적서.png", png, "image/png"))],
        )
        assert r2.status_code == 400
        assert "Gemini 또는 Claude" in r2.json()["detail"]
    finally:
        _gemini("gemini-3.6-flash")


# ---- review fixes (2026-11-21) ----

def test_ai_draft_json_without_brief_is_400_not_500(client):
    f = forms_by_cat(client)["pumui"]
    r = client.post(f"/api/forms/{f['id']}/ai-draft", json={"date": "2026-11-21"})
    assert r.status_code == 400, r.text


def test_routine_backups_do_not_push_out_important_ones():
    important = S.backup("important-keep")
    for _ in range(S.MAX_ROUTINE_BACKUPS + 3):
        S.backup("routine", routine=True)
    names = [b["name"] for b in S.list_backups()]
    assert important in names
    kinds = [S._backup_info(S.BACKUPS / n).get("kind") for n in names]
    assert kinds.count("routine") == S.MAX_ROUTINE_BACKUPS


def test_db_helper_closes_connection():
    import sqlite3
    with S.db() as con:
        con.execute("SELECT 1")
    with pytest.raises(sqlite3.ProgrammingError):
        con.execute("SELECT 1")


def test_preview_uses_learned_lines_without_file(client):
    f = forms_by_cat(client)["gian"]
    tpl = client.get(f"/api/forms/{f['id']}/template").json()["template"]
    lines = E.preview_text(tpl, {})
    assert lines and any(x.strip() for x in lines)


def test_light_load_skips_other_files(client):
    f = forms_by_cat(client)["gian"]
    s = S.list_samples(f["id"])[0]
    data = S.sample_bytes(s)
    light = E.load_doc(data, full=False)
    assert set(light.files) <= set(E.LIGHT_FILES)
    assert light.texts == E.load_doc(data).texts
