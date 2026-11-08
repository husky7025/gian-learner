"""기본 양식 꾸러미(packs/기본양식.gianpack) 만들기.

실제 기안 파일은 서식(글꼴·문단 모양·여백)만 빌려 쓰고, 글자는 전부 아래의 가상 예시로 바꾼다.
모든 줄·표 칸을 입력칸으로 만든 뒤 빠짐없이 채우므로, 하나라도 빠지면 오류로 멈춘다(원본 글자 유출 방지).

사용:
  python tools/make_default_pack.py --gian 기안.hwpx --pumui 품의.hwpx --gatong 가정통신문.hwpx
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import hwpx_engine as E  # noqa: E402
from app import packs as P  # noqa: E402

SLOGAN = "오고 싶은 학교! 기본에 충실한 창의성을 기르는 교육!"
SCHOOL = "대전동산고등학교"


def item(depth, label, value):
    return {"kind": "item", "depth": depth, "label": label, "value": value}


# ───────── 기안 (내부결재) ─────────
GIAN_HEAD = lambda title: {  # noqa: E731
    "h0": SLOGAN, "h1": SCHOOL, "h3": "수신  내부결재", "h4": "(경유)", "h5": f"제목  {title}",
}
GIAN = [
    {
        "fields": GIAN_HEAD("2027학년도 교원 디지털 역량 강화 연수 실시"),
        "outline": [
            item(0, "관련", "대전동산고등학교-1001(2027. 3. 2.)"),
            item(0, "", "2027학년도 교원 디지털 역량 강화 연수를 다음과 같이 실시하고자 합니다."),
            item(1, "일시", "2027. 3. 17.(수) 15:00~17:00"),
            item(1, "장소", "본교 시청각실"),
            item(1, "대상", "본교 교원 중 희망자"),
            item(1, "내용", "수업에 활용하는 AI 도구 실습"),
            item(1, "강사", "○○○(외부 강사)"),
        ],
        "attach": ["연수 계획서 1부"],
    },
    {
        "fields": GIAN_HEAD("2027학년도 동아리 발표회 운영 계획"),
        "outline": [
            item(0, "관련", "대전동산고등학교-1002(2027. 4. 1.)"),
            item(0, "", "2027학년도 동아리 발표회를 다음과 같이 운영하고자 합니다."),
            item(1, "일시", "2027. 7. 14.(수) 13:00~16:00"),
            item(1, "장소", "본교 강당"),
            item(1, "대상", "본교 1, 2학년 전체"),
            item(1, "내용", "동아리별 활동 결과 발표 및 전시"),
            item(1, "운영방법", ""),
            item(2, "1부", "동아리 발표(강당)"),
            item(2, "2부", "활동 결과물 전시(각 교실)"),
        ],
        "attach": ["운영 계획서 1부", "동아리 발표 순서 1부"],
    },
]

# ───────── 품의 ─────────
PUMUI = [
    {"outline": [
        item(0, "관련", "대전동산고등학교-2001(2027. 3. 5.)"),
        item(0, "건명", "2027학년도 과학 동아리 실험 재료 구입"),
        item(0, "금액", "금250,000원(금이십오만원)"),
        item(0, "품목", "실험 재료"),
        item(0, "내역", "비커 외 12종"),
    ], "attach": ["견적서 1부", "구입 목록 1부"]},
    {"outline": [
        item(0, "관련", "대전동산고등학교-2002(2027. 4. 12.)"),
        item(0, "건명", "2027학년도 독서 동아리 도서 구입"),
        item(0, "금액", "금180,000원(금일십팔만원)"),
        item(0, "품목", "도서"),
        item(0, "내역", "10종 12권"),
    ], "attach": ["견적서 1부", "도서 목록 1부"]},
]

# ───────── 가정통신문 ─────────
CONSENT = {
    "h17": None,  # 아래에서 행사 이름으로 채움
    "h21": "□ 개인정보 수집 · 이용 동의",
    "h23": " ※ 개인정보 수집·이용에 대한 동의를 거부할 권리가 있습니다. 그러나 동의를 거부할 경우 행사 참가 신청에 제한을 받을 수 있습니다.",
    "h24": " 위와 같이 개인정보를 수집·이용하는 데 동의하십니까?          □ 예     □ 아니요",
    "h26": "□ 개인정보 제3자 제공 동의",
    "h28": " ※ 개인정보 제공에 대한 동의를 거부할 권리가 있습니다. 그러나 동의를 거부할 경우 행사 참가 신청에 제한을 받을 수 있습니다.",
    "h29": " 위와 같이 개인정보를 제3자에게 제공하는 데 동의하십니까?          □ 예     □ 아니요",
    "h31": " ※ 수집한 개인정보는 정보주체의 동의 없이 수집한 목적 외로 사용하거나 제3자에게 제공되지 않습니다.",
    "h33": "2027년      월      일",
    "h35": "학생 성명 :                   (서명)",
    "h36": "보호자 성명 :                   (서명)",
    "h38": "대전동산고등학교장 귀하",
}
GATONG_COMMON = {
    "h0": SLOGAN, "h5": "  학부모님 안녕하십니까?", "h6": "  학부모님의 가정에 늘 건강과 행복이 가득하시기를 기원합니다.",
    "h9": "▣ 세부 안내", "h14": "대 전 동 산 고 등 학 교 장",
    "h15": "----------------------------------- 절      취      선 -----------------------------------",
    **{k: v for k, v in CONSENT.items() if v},
}
GATONG_CELLS_COMMON = {
    "c0_0_1": "가 정 통 신 문\n담당자 : 교사 ○○○      ☏ 042-000-0000",
    "c1_0_0": "일시", "c1_1_0": "장소", "c1_2_0": "대상", "c1_3_0": "내용", "c1_4_0": "준비물", "c1_5_0": "신청 방법", "c1_6_0": "안내사항",
    "c2_0_0": "학년/반/번", "c2_0_1": "성명", "c2_0_2": "휴대폰 번호", "c2_0_3": "이메일 주소",
    "c3_0_0": "항목", "c3_0_1": "수집목적", "c3_0_2": "보유기간",
    "c3_1_0": "성명, 휴대폰 번호", "c3_1_2": "행사 종료 후 파기",
    "c4_0_0": "제공받는 기관", "c4_0_1": "제공목적", "c4_0_2": "제공하는 항목", "c4_0_3": "보유기간",
    "c4_1_0": "없음", "c4_1_1": "-", "c4_1_2": "-", "c4_1_3": "-",
    "c4_2_0": "-", "c4_2_1": "-", "c4_2_2": "-",
}
GATONG = [
    {
        "fields": {**GATONG_COMMON,
                   "h3": "[ 2027학년도 학부모 진로 특강 안내 ]",
                   "h7": "  본교에서는 자녀의 진로 설계를 돕기 위하여 학부모 진로 특강을 아래와 같이 운영합니다. 바쁘시더라도 많은 참여 부탁드립니다.",
                   "h12": "2027년  3월  10일",
                   "h17": "2027학년도 학부모 진로 특강 참여 신청서"},
        "cells": {**GATONG_CELLS_COMMON,
                  "c0_0_2": "제2027 - 15호",
                  "c1_0_1": "2027. 3. 24.(수) 18:30 ~ 20:00",
                  "c1_1_1": "본교 시청각실",
                  "c1_2_1": "본교 1, 2학년 학부모 중 희망자 (선착순 80명)",
                  "c1_3_1": "▪ 주제: 고교학점제와 진로 설계\n▪ 대입 제도 변화와 준비 방법 안내",
                  "c1_4_1": "없음",
                  "c1_5_1": "▪ 2027. 3. 17.(수)까지 하단 신청서를 작성하여 자녀 편으로 담임 선생님께 제출",
                  "c1_6_1": "▪ 주차 공간이 부족하니 대중교통을 이용해 주시기 바랍니다.\n▪ 문의: 본교 진로진학부",
                  "c3_1_1": "학부모 진로 특강 운영"},
    },
    {
        "fields": {**GATONG_COMMON,
                   "h3": "[ 2027학년도 학교 도서관 독서 행사 안내 ]",
                   "h7": "  본교에서는 독서 문화 확산을 위하여 가족과 함께하는 독서 행사를 아래와 같이 운영합니다. 학생과 학부모님의 많은 관심 바랍니다.",
                   "h12": "2027년  4월  7일",
                   "h17": "2027학년도 학교 도서관 독서 행사 참여 신청서"},
        "cells": {**GATONG_CELLS_COMMON,
                  "c0_0_2": "제2027 - 31호",
                  "c1_0_1": "2027. 4. 23.(금) 16:00 ~ 18:00",
                  "c1_1_1": "본교 도서관",
                  "c1_2_1": "본교 학생 및 학부모 중 희망자",
                  "c1_3_1": "▪ 작가와의 만남\n▪ 가족 독서 퀴즈",
                  "c1_4_1": "필기도구",
                  "c1_5_1": "▪ 2027. 4. 16.(금)까지 하단 신청서를 작성하여 도서관에 제출",
                  "c1_6_1": "▪ 참여 학생에게는 독서 활동 기록이 남습니다.\n▪ 문의: 본교 도서관",
                  "c3_1_1": "독서 행사 운영"},
    },
]


def all_fields_overrides(base: bytes) -> dict:
    tpl = E.learn([base], ["b"])
    lines = {}
    for b in tpl["blocks"]:
        if b["type"] in ("fixed", "field") and not b.get("object") and (b.get("text") or "").strip():
            lines[b["id"]] = "field"
    for t in tpl["tables"]:
        for row in t["rows"]:
            for c in row:
                if not c["locked"] and c["text"].strip():
                    lines[c["key"]] = "field"
    return {"lines": lines}


def build(base: bytes, variant: dict) -> bytes:
    tpl = E.learn([base], ["b"], all_fields_overrides(base))
    fields = variant.get("fields", {})
    cells = variant.get("cells", {})
    for b in tpl["blocks"]:
        if b["type"] == "field" and b["id"] not in fields:
            raise SystemExit(f"채우지 않은 줄이 있습니다: {b['id']} (원본 글자가 남을 수 있어 중단)")
    for t in tpl["tables"]:
        for row in t["rows"]:
            for c in row:
                if c["type"] == "field" and c["key"] not in cells:
                    raise SystemExit(f"채우지 않은 표 칸이 있습니다: {c['key']} (원본 글자가 남을 수 있어 중단)")
    # 줄 전체를 바꾸므로 prefix 없이 넣기
    for b in tpl["blocks"]:
        if b["type"] == "field":
            b["prefix"] = ""
    data = {"fields": fields, "cells": cells, "outline": variant.get("outline", []), "attach": variant.get("attach", [])}
    out, _ = E.generate(base, tpl, data)
    return P.scrub(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gian", required=True)
    ap.add_argument("--pumui", required=True)
    ap.add_argument("--gatong", required=True)
    ap.add_argument("--out", default=str(ROOT / "packs" / "기본양식.gianpack"))
    a = ap.parse_args()
    forms = []
    for cat, name, path, variants in (("gian", "기안", a.gian, GIAN), ("pumui", "품의", a.pumui, PUMUI),
                                      ("gatong", "가정통신문", a.gatong, GATONG)):
        base = Path(path).read_bytes()
        samples = [{"id": i, "data": build(base, v)} for i, v in enumerate(variants)]
        forms.append({"name": name, "category": cat, "overrides": {}, "samples": samples})
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(P.export_pack(forms))
    print(f"만듦: {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
