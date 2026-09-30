"""특약·옵션 조항: 본문 줄·빈칸 반영, 멱등성, 제한."""
import re

import pytest

from app.services import catalog, clauses
from app.services.fields import FieldSpec, FieldValueError, normalize_value


def _payload(tid):
    t = catalog.get_template(tid)
    return {"body_text": t["body"], "fields": t["fields"]}, t["contract_type"]


def test_every_clause_fits_every_template_it_applies_to():
    """조항 빈칸 이름이 템플릿 빈칸과 겹치지 않고, 모든 자리표시자에 빈칸 정의가 있다."""
    for tid in catalog.TEMPLATES:
        p, ctype = _payload(tid)
        ids = [c["id"] for c in clauses.available(ctype, tid)]
        labels = {f["label"] for f in p["fields"]}
        for cid in ids:
            params = {x["label"] for x in clauses.BY_ID[cid]["params"]}
            assert not (params & labels), (tid, cid, params & labels)
            assert set(re.findall(r"\{([^{}]+)\}", clauses.BY_ID[cid]["text"])) == params, cid
        r = clauses.apply_clauses(p, ctype, tid, ids, [])
        FieldSpec  # noqa: B018
        assert all(clauses.line_of(c) in r["body_text"] for c in ids)


def test_apply_inserts_above_free_text_and_adds_fields():
    p, ctype = _payload("loan")
    r = clauses.apply_clauses(p, ctype, "loan", ["loan_late_interest", "court"], ["반려동물 양육 금지"])
    lines = r["body_text"].split("\n")
    i = lines.index("{특약사항}")
    assert lines[i - 3:i] == [clauses.line_of("loan_late_interest"), clauses.line_of("court"), "- 반려동물 양육 금지"]
    labels = [f["label"] for f in r["fields"]]
    assert "지연손해금률" in labels and "관할법원" in labels
    assert r["clauses"] == ["loan_late_interest", "court"] and r["custom_clauses"] == ["반려동물 양육 금지"]


def test_turning_off_removes_line_and_field_but_keeps_other_values():
    p, ctype = _payload("loan")
    r1 = clauses.apply_clauses(p, ctype, "loan", ["loan_late_interest", "court"], ["메모"])
    for f in r1["fields"]:
        if f["label"] == "관할법원":
            f["value"] = "서울중앙지방법원"
    p2 = {**p, **r1}
    r2 = clauses.apply_clauses(p2, ctype, "loan", ["court"], [])
    assert clauses.line_of("loan_late_interest") not in r2["body_text"] and "- 메모" not in r2["body_text"]
    by = {f["label"]: f for f in r2["fields"]}
    assert "지연손해금률" not in by and by["관할법원"]["value"] == "서울중앙지방법원"
    # 멱등: 같은 선택을 다시 보내도 결과가 같다
    r3 = clauses.apply_clauses({**p2, **r2}, ctype, "loan", ["court"], [])
    assert r3["body_text"] == r2["body_text"] and len(r3["fields"]) == len(r2["fields"])
    # 모두 끄면 원래 본문으로 돌아간다
    r4 = clauses.apply_clauses({**p2, **r3}, ctype, "loan", [], [])
    assert r4["body_text"] == p["body_text"]


def test_text_contract_without_section_gets_and_loses_heading():
    p = {"body_text": "갑과 을은 다음과 같이 약정한다.\n1. 내용", "fields": []}
    r = clauses.apply_clauses(p, "general", None, ["confidential"], ["직접 쓴 특약"])
    assert r["body_text"].endswith("특약사항\n" + clauses.line_of("confidential") + "\n- 직접 쓴 특약")
    r2 = clauses.apply_clauses({**p, **r}, "general", None, [], [])
    assert r2["body_text"] == p["body_text"]


def test_custom_clause_is_sanitized_and_limited():
    p, ctype = _payload("goods")
    r = clauses.apply_clauses(p, ctype, "goods", [], ["  {가격}은 <b>협의</b>\n한다  "])
    assert r["custom_clauses"] == ["가격은 b협의/b 한다"]
    with pytest.raises(clauses.ClauseError):
        clauses.apply_clauses(p, ctype, "goods", [], ["가" * 301])
    with pytest.raises(clauses.ClauseError):
        clauses.apply_clauses(p, ctype, "goods", [], [f"특약 {i}" for i in range(11)])
    with pytest.raises(clauses.ClauseError):
        clauses.apply_clauses(p, ctype, "goods", [], ["   "])


def test_clause_for_other_contract_type_is_rejected():
    p, ctype = _payload("goods")
    with pytest.raises(clauses.ClauseError):
        clauses.apply_clauses(p, ctype, "goods", ["emp_probation"], [])
    # 수습기간은 정규직 표준근로계약서에만 (일용·단시간 제외)
    p, ctype = _payload("employment_daily")
    with pytest.raises(clauses.ClauseError):
        clauses.apply_clauses(p, ctype, "employment_daily", ["emp_probation"], [])
    assert "daily_idle" in [c["id"] for c in clauses.available(ctype, "employment_daily")]


def test_legal_limits_on_clause_values():
    rate = FieldSpec(**clauses.BY_ID["loan_late_interest"]["params"][0])
    assert normalize_value(rate, "15") == "15"
    with pytest.raises(FieldValueError):
        normalize_value(rate, "25")
    ratio = FieldSpec(**clauses.BY_ID["emp_probation"]["params"][1])
    with pytest.raises(FieldValueError):
        normalize_value(ratio, "80")
    months = FieldSpec(**clauses.BY_ID["emp_probation"]["params"][0])
    with pytest.raises(FieldValueError):
        normalize_value(months, "6")


def test_excluded_clauses_are_not_offered():
    texts = " ".join(c["text"] for c in clauses.CLAUSES)
    assert "위약금" not in texts and "교육비" not in texts and "연대보증" not in texts
    assert set(clauses.EXCLUDED) >= {"근로자 위약금·교육비 반환 약정", "연대보증"}
