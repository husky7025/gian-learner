"""기본 양식 꾸러미(packs/기본양식.gianpack) 만들기.

실제 파일은 서식(글꼴·문단 모양·여백)만 빌려 쓰고, 글자는 전부 아래의 가상 예시로 바꾼다.
모든 줄·표 칸을 입력칸으로 만든 뒤 빠짐없이 채우므로, 하나라도 빠지면 오류로 멈춘다(원본 글자 유출 방지).

사용:
  python tools/make_default_pack.py --gian 기안.hwpx --pumui 품의.hwpx --gatong 가정통신문.hwpx

2026-11-21 기준 서식: 학습용/기안 「…후속 교원 연수 실시 계획」, 학습용/품의 「…도서 구입 품의」,
학습용/가정통신문 「…수학여행 참가 희망 동의서」 (학부모에게 직접 배부하는 안내문)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import hwpx_engine as E  # noqa: E402
from app import packs as P  # noqa: E402

SLOGAN = "꿈을 키우는 배움, 함께 자라는 푸른솔!"
SCHOOL = "푸른솔고등학교"


def item(depth, label, value):
    return {"kind": "item", "depth": depth, "label": label, "value": value}


# ───────── 기안 (K-에듀파인 본문: 제목 + 본문 + 붙임) ─────────
GIAN = [
    {
        "fields": {"h0": "2027학년도 교원 수업 나눔 연수 실시 계획"},
        "outline": [
            item(0, "관련", "푸른솔고등학교-1001(2027. 3. 2.)"),
            item(0, "", "2027학년도 교원 수업 나눔 연수를 다음과 같이 실시하고자 합니다."),
            item(1, "", "일시 및 주제"),
            item(2, "", "2027. 4. 14.(수) 16:10 - 18:00: 학생 참여형 수업 설계"),
            item(2, "", "2027. 4. 21.(수) 16:10 - 18:00: 과정 중심 평가 사례 나눔"),
            item(1, "장소", "본관 2층 시청각실"),
            item(1, "대상", "본교 교원 중 희망자"),
        ],
        "attach": ["교원 수업 나눔 연수 신청자 명단 1부"],
    },
    {
        "fields": {"h0": "2027학년도 학부모 진로 특강 안내 가정통신문 배부"},
        "outline": [
            item(0, "관련", "푸른솔고등학교-1002(2027. 3. 5.)"),
            item(0, "", "2027학년도 학부모 진로 특강 안내 가정통신문을 다음과 같이 배부하고자 합니다."),
            item(1, "배부일", "2027. 3. 10.(수)"),
            item(1, "배부 대상", "본교 1, 2학년 학부모"),
            item(1, "배부 방법", "학교 알림 앱 발송 및 자녀 편 종이 배부"),
            item(1, "회신 기한", "2027. 3. 17.(수)까지 담임교사 제출"),
        ],
        "attach": ["학부모 진로 특강 안내 가정통신문 1부"],
    },
]

# ───────── 품의 ─────────
PUMUI = [
    {"outline": [
        item(0, "건명", "[2027학년도] 과학 동아리 활동을 위한 실험 재료 구입"),
        item(0, "금액", "250,000원"),
        item(0, "품명", "실험 재료"),
        item(0, "기간", "2027.04.01. - 2027.04.15."),
        item(0, "내역", "비커 외 12종(붙임 구입목록 참조)"),
    ], "attach": ["견적서 1부", "구입목록 1부"]},
    {"outline": [
        item(0, "건명", "[2027학년도] 학부모 진로 특강 강사비 지급"),
        item(0, "금액", "300,000원"),
        item(0, "품명", "강사비"),
        item(0, "기간", "2027.03.24."),
        item(0, "내역", "외부 강사 1명, 2시간(붙임 강사 이력서 참조)"),
    ], "attach": ["강사 이력서 1부", "강의 계획서 1부"]},
]

# ───────── 가정통신문 (학부모 배부용 안내문) ─────────
# outline은 기준 서식의 순서대로: 항목 3개, 그 아래 문단(안내 문구·날짜·학교장·절취선·회신서)
GATONG_HEAD = {
    "h0": SLOGAN,
    "h3": "학부모님 안녕하십니까?",
    "h5": " 학부모님의 가정에 건강과 행복이 늘 함께 하시길 기원합니다.",
}
GATONG = [
    {
        "fields": {**GATONG_HEAD,
                   "h6": "교육과정 운영 계획에 따라, 교과 수업에서 배운 내용을 직접 체험하며 탐구심을 기를 수 있도록 아래와 같이 1학년 현장체험학습을 실시하고자 합니다. 자녀가 안전하고 뜻깊은 시간을 보낼 수 있도록 4월 9일(금)까지 참가 동의서 제출을 부탁드립니다."},
        "items": [
            ("현장체험학습 일시", "2027. 4. 23.(금) 08:30 ~ 16:00"),
            ("현장체험학습 장소", "국립중앙과학관(대전 유성구) 일원"),
            ("현장체험학습 경비", "1인당 15,000원 내외(버스 임차료, 참가 인원에 따라 변동 가능)"),
        ],
        "paras": [
            "*체험학습 경비 지원 계획을 아래와 같이 안내하오니, 해당 가정에선 추후 안내 시 신청 바랍니다.",
            "2027. 4. 2.",
            "푸 른 솔 고 등 학 교 장",
            "---------------------------절   취    선----------------------",
            "현장체험학습 참가 동의서",
            "1학년 (    )반 (    )번 성명 :                (서명) ",
            "보호자 :                (서명)",
            "푸른솔고등학교장 귀하",
        ],
        "cells": {
            "c0_0_1": "가 정 통 신 문\n담당자 : 교사 ○ ○ ○    ☏ 042-000-0000",
            "c0_0_2": "제2027–21호",
            "c1_0_0": "현장체험학습 경비 지원 안내\n\n- 지원 대상: 교육급여 수급 가정 학생\n- 지원 내용: 체험학습 경비 전액 지원\n  * 신청 방법 및 시기 추후 안내 예정",
            "c2_0_0": "현장체험학습 참가",
            "c2_1_0": "참가함",
            "c2_1_1": "참가하지 않음",
        },
    },
    {
        "fields": {**GATONG_HEAD,
                   "h6": "방학 중에도 자녀가 계획적으로 학습할 수 있도록 아래와 같이 겨울방학 방과후학교를 운영하고자 합니다. 자녀와 충분히 상의하신 후 12월 10일(금)까지 수강 신청서 제출을 부탁드립니다."},
        "items": [
            ("운영 기간", "2028. 1. 4.(화) ~ 1. 14.(금) 9일간"),
            ("수강 강좌", "국어, 수학, 영어, 탐구 등 12개 강좌(강좌별 20명 이내)"),
            ("수강료", "1강좌당 40,000원 내외(수강 인원에 따라 변동 가능)"),
        ],
        "paras": [
            "*방과후학교 자유수강권 지원 계획을 아래와 같이 안내하오니, 해당 가정에선 참고하시기 바랍니다.",
            "2027. 12. 3.",
            "푸 른 솔 고 등 학 교 장",
            "---------------------------절   취    선----------------------",
            "겨울방학 방과후학교 수강 신청서",
            "(    )학년 (    )반 (    )번 성명 :                (서명) ",
            "보호자 :                (서명)",
            "푸른솔고등학교장 귀하",
        ],
        "cells": {
            "c0_0_1": "가 정 통 신 문\n담당자 : 교사 ○ ○ ○    ☏ 042-000-0000",
            "c0_0_2": "제2027–132호",
            "c1_0_0": "방과후학교 자유수강권 지원 안내\n\n- 지원 대상: 교육급여 수급 가정 및 차상위 계층 학생\n- 지원 금액: 연간 60만원 이내\n  * 신청 방법은 담임 선생님께 문의",
            "c2_0_0": "방과후학교 수강",
            "c2_1_0": "신청함",
            "c2_1_1": "신청하지 않음",
        },
    },
]


def fill_outline(tpl: dict, variant: dict) -> list:
    """기준 서식의 outline 순서(항목·문단·빈 줄·표)를 그대로 두고 항목·문단 글자만 바꾼다."""
    items, paras = list(variant["items"]), list(variant["paras"])
    out = []
    for b in tpl["blocks"]:
        if b["type"] != "outline":
            continue
        for it in b["items"]:
            k = it.get("kind", "item")
            if k == "item":
                label, value = items.pop(0)
                out.append({"kind": "item", "depth": it["depth"], "label": label, "value": value})
            elif k == "para":
                out.append({"kind": "para", "src": it["src"], "indent": it.get("indent", ""), "value": paras.pop(0)})
            else:
                out.append(dict(it))
    if items or paras:
        raise SystemExit(f"남은 항목·문단이 있습니다: {items} {paras}")
    return out


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
    outline = fill_outline(tpl, variant) if "paras" in variant else variant.get("outline", [])
    data = {"fields": fields, "cells": cells, "outline": outline, "attach": variant.get("attach", [])}
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
