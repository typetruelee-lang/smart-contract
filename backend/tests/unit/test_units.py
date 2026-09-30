"""단위 테스트 — Hash, 필드 파싱, 값 검증, Merkle, 상태 머신, 암호화, 로그 마스킹."""
from __future__ import annotations

import hashlib

import pytest

from app.core.logging import mask_name, mask_pii
from app.providers import keys
from app.services import states
from app.services.fields import (
    FieldSpec,
    FieldValueError,
    apply_suggestions,
    display_value,
    infer_type,
    missing_required,
    normalize_value,
    suggest_fields,
)
from app.services.hashing import normalize_hash, sha256_bytes, sha256_json
from app.services.merkle import MerkleService

# ---------------- Hash ----------------

def test_sha256_known_vector():
    assert sha256_bytes(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_hash_changes_on_single_byte():
    a = b"%PDF-1.7 contract body"
    b = bytearray(a)
    b[-1] ^= 1
    assert sha256_bytes(a) != sha256_bytes(bytes(b))


def test_hash_of_real_pdf_changes_on_one_char():
    from app.services.pdf_engine import html_to_pdf

    p1 = html_to_pdf("<html><body>대여금액 1,000,000원</body></html>")
    p2 = html_to_pdf("<html><body>대여금액 1,000,001원</body></html>")
    assert sha256_bytes(p1) != sha256_bytes(p2)


def test_canonical_json_hash_order_independent():
    assert sha256_json({"a": 1, "b": "한글"}) == sha256_json({"b": "한글", "a": 1})


@pytest.mark.parametrize("bad", ["", "xyz", "0x123", "g" * 64, "a" * 63])
def test_normalize_hash_rejects(bad):
    with pytest.raises(ValueError):
        normalize_hash(bad)


def test_normalize_hash_accepts_0x_upper():
    h = hashlib.sha256(b"x").hexdigest()
    assert normalize_hash("0x" + h.upper()) == h

# ---------------- 필드 자동 추천 ----------------

SAMPLE = """금전소비대차계약서

대여금액: __________ 원
채권자: __________
채무자: __________
상환일: ____년 __월 __일
이자율: 연 ____%
연락처: [          ]
이메일: {이메일}
서명: ________ (인)
□ 개인정보 수집에 동의합니다
특약사항:
________________________
________________________
"""


def test_suggest_types_and_labels():
    s = {x.label: x for x in suggest_fields(SAMPLE)}
    assert s["대여금액"].type == "NUMBER"
    assert s["채권자"].type == "TEXT"
    assert s["상환일"].type == "DATE"
    assert s["이자율"].type == "NUMBER"
    assert s["연락처"].type == "PHONE"
    assert s["이메일"].type == "EMAIL"
    assert any(x.type == "SIGNATURE" for x in s.values())
    assert s["개인정보 수집에 동의합니다"].type == "CHECKBOX"
    assert s["특약사항"].type == "LONG_TEXT"


def test_suggestions_do_not_modify_text_until_applied():
    sug = suggest_fields(SAMPLE)
    assert "__________" in SAMPLE
    out = apply_suggestions(SAMPLE, sug)
    assert "_" not in out.replace("\n", "")
    for x in sug:
        assert "{" + x.label + "}" in out


def test_apply_subset_only():
    sug = suggest_fields(SAMPLE)
    only = [x for x in sug if x.label == "채권자"]
    out = apply_suggestions(SAMPLE, only)
    assert "{채권자}" in out and "대여금액: __________" in out


def test_apply_stale_suggestion_rejected():
    sug = suggest_fields(SAMPLE)
    with pytest.raises(ValueError):
        apply_suggestions(SAMPLE.replace("대여금액", "빌린돈"), sug)


def test_duplicate_labels_get_suffix():
    s = suggest_fields("이름: ____\n이름: ____\n")
    assert [x.label for x in s] == ["이름", "이름 2"]


def test_unlabeled_blank_low_confidence():
    s = suggest_fields("_____ 은 _____ 에게")
    assert all(x.confidence <= 0.5 for x in s)


def test_existing_curly_labels_skipped():
    s = suggest_fields("{채권자} 와 {채무자}", existing_labels={"채권자"})
    assert [x.label for x in s] == ["채무자"]


@pytest.mark.parametrize("label,trail,expected", [
    ("전화번호", "", "PHONE"), ("이메일 주소", "", "EMAIL"), ("계약일", "", "DATE"), ("임금", "", "NUMBER"),
    ("수량", "", "NUMBER"), ("비고", "", "LONG_TEXT"), ("주소", "", "TEXT"), ("", "원", "NUMBER"), ("갑 서명", "", "SIGNATURE"),
])
def test_infer_type(label, trail, expected):
    assert infer_type(label, trail) == expected

# ---------------- 값 검증 ----------------

def F(t, **kw):
    return FieldSpec(label="항목", type=t, **kw)


@pytest.mark.parametrize("t,val,expected", [
    ("NUMBER", "1,000,000", "1000000"), ("NUMBER", "3.5", "3.5"), ("DATE", "2027-02-28", "2027-02-28"),
    ("PHONE", "010-1234-5678", "010-1234-5678"), ("PHONE", "01012345678", "01012345678"), ("EMAIL", "a.b@c.co.kr", "a.b@c.co.kr"),
    ("TEXT", "  홍길동 ", "홍길동"), ("CHECKBOX", True, True), ("CHECKBOX", "false", False), ("LONG_TEXT", "줄1\r\n줄2", "줄1\n줄2"),
    ("TEXT", "!@#$%^&*()<>\"'", "!@#$%^&*()<>\"'"),
])
def test_normalize_ok(t, val, expected):
    assert normalize_value(F(t), val) == expected


@pytest.mark.parametrize("t,val", [
    ("NUMBER", "abc"), ("NUMBER", "-5"), ("NUMBER", "1e9"), ("DATE", "2027-13-01"), ("DATE", "27/01/01"), ("DATE", "1800-01-01"),
    ("PHONE", "12345"), ("EMAIL", "not-an-email"), ("TEXT", "a" * 201), ("TEXT", "두\n줄"), ("LONG_TEXT", "a" * 2001),
    ("CHECKBOX", "maybe"), ("SIGNATURE", "data:image/png;base64,xx"),
])
def test_normalize_rejects(t, val):
    with pytest.raises(FieldValueError):
        normalize_value(F(t), val)


def test_select_requires_option():
    f = F("SELECT", options=["계좌이체", "현금"])
    assert normalize_value(f, "현금") == "현금"
    with pytest.raises(FieldValueError):
        normalize_value(f, "카드")


def test_empty_value_is_none():
    assert normalize_value(F("NUMBER"), "  ") is None


def test_missing_required_respects_assignee_and_signature():
    fs = [FieldSpec(label="a", assignee="A"), FieldSpec(label="b", assignee="B"), FieldSpec(label="s", type="SIGNATURE"),
          FieldSpec(label="c", type="CHECKBOX"), FieldSpec(label="opt", required=False)]
    assert {f.label for f in missing_required(fs)} == {"a", "b", "c"}
    assert {f.label for f in missing_required(fs, assignee="B")} == {"b"}
    assert "s" in {f.label for f in missing_required(fs, include_signature=True)}


def test_label_validation():
    with pytest.raises(ValueError):
        FieldSpec(label="<script>")
    with pytest.raises(ValueError):
        FieldSpec(label="")


def test_display_value_formats():
    assert display_value(FieldSpec(label="x", type="NUMBER", value="10000000")) == "10,000,000"
    assert display_value(FieldSpec(label="x", type="DATE", value="2027-03-01")) == "2027년 3월 1일"

# ---------------- Merkle (시나리오 6) ----------------

def _h(i):
    return hashlib.sha256(f"contract-{i}".encode()).hexdigest()


def test_scenario6_merkle_root_proof_verify():
    hs = [_h(i) for i in range(4)]
    tree = MerkleService.create_tree(hs)
    root = MerkleService.get_root(tree)
    for h in hs:
        proof = MerkleService.get_proof(tree, h)
        assert len(proof) == 2
        assert MerkleService.verify_proof(h, proof, root)


@pytest.mark.parametrize("n", [1, 2, 3, 5, 7, 16, 33])
def test_merkle_various_sizes(n):
    hs = [_h(i) for i in range(n)]
    tree = MerkleService.create_tree(hs)
    root = tree.get_root()
    for h in hs:
        assert MerkleService.verify_proof(h, tree.get_proof(h), root)


def test_merkle_rejects_wrong_hash_and_tampered_proof():
    hs = [_h(i) for i in range(4)]
    tree = MerkleService.create_tree(hs)
    root = tree.get_root()
    proof = tree.get_proof(hs[0])
    assert not MerkleService.verify_proof(_h(99), proof, root)
    bad = list(proof)
    bad[0] = _h(98)
    assert not MerkleService.verify_proof(hs[0], bad, root)
    with pytest.raises(ValueError):
        tree.get_proof(_h(99))


def test_merkle_manual_ab_cd_root():
    a, b, c, d = (_h(i) for i in range(4))
    pair = lambda x, y: hashlib.sha256(min(bytes.fromhex(x), bytes.fromhex(y)) + max(bytes.fromhex(x), bytes.fromhex(y))).hexdigest()  # noqa: E731
    leaves = sorted([a, b, c, d])
    expected = pair(pair(leaves[0], leaves[1]), pair(leaves[2], leaves[3]))
    assert MerkleService.create_tree([a, b, c, d]).get_root() == expected

# ---------------- 상태 머신 ----------------

class Obj:
    def __init__(self, s):
        self.status = s


def test_contract_state_machine():
    o = Obj("DRAFT")
    states.transition("contract", o, "INVITED")
    states.transition("contract", o, "SIGNING")
    states.transition("contract", o, "COMPLETED")
    with pytest.raises(states.InvalidTransition):
        states.transition("contract", o, "DRAFT")


def test_payment_state_machine():
    o = Obj("PENDING")
    states.transition("payment", o, "FAILED")
    with pytest.raises(states.InvalidTransition):
        states.transition("payment", o, "PAID")


def test_anchor_state_machine_independent_of_payment():
    o = Obj("PENDING")
    states.transition("anchor", o, "RETRY")
    states.transition("anchor", o, "RETRY")
    states.transition("anchor", o, "CONFIRMED")
    with pytest.raises(states.InvalidTransition):
        states.transition("anchor", o, "FAILED")
    assert not states.can("contract", "COMPLETED", "SIGNING")

# ---------------- 암호화 ----------------

def test_envelope_encryption_roundtrip_and_tamper():
    keys.reset_key_provider()
    ct, w, v = keys.encrypt("계약 원문".encode(), b"aad")
    assert keys.decrypt(ct, w, v, b"aad").decode() == "계약 원문"
    with pytest.raises(Exception):
        keys.decrypt(ct, w, v, b"other-aad")
    bad = bytearray(ct)
    bad[-1] ^= 1
    with pytest.raises(Exception):
        keys.decrypt(bytes(bad), w, v, b"aad")


def test_production_refuses_env_key_provider(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    keys.reset_key_provider()
    try:
        with pytest.raises(keys.KeyProviderError):
            keys.get_key_provider()
    finally:
        monkeypatch.setenv("APP_ENV", "test")
        get_settings.cache_clear()
        keys.reset_key_provider()

# ---------------- 로그 마스킹 ----------------

def test_mask_pii():
    s = mask_pii("전화 010-1234-5678 메일 a@b.com 주민 900101-1234567 카드 1234-5678-9012-3456 /api/invites/abcdefghijklmnop")
    assert "010-1234-5678" not in s and "a@b.com" not in s and "900101-1234567" not in s and "1234-5678-9012-3456" not in s
    assert "abcdefghijklmnop" not in s


def test_mask_name():
    assert mask_name("홍길동") == "홍*동"
    assert mask_name("남궁민수") == "남**수"
    assert mask_name("김철") == "김*"
    assert mask_name("") == "*"


def test_time_field_pattern():
    from app.services.fields import TIME_PATTERN
    f = F("TEXT", validation={"pattern": TIME_PATTERN, "maxLength": 5})
    assert normalize_value(f, " 09:00 ") == "09:00"
    assert normalize_value(f, "23:59") == "23:59"
    for bad in ("25:00", "9시", "9:00", "12:60"):
        with pytest.raises(FieldValueError) as e:
            normalize_value(f, bad)
        assert "HH:MM" in e.value.message


def test_client_validation_is_sanitized():
    """클라이언트가 보낸 임의 정규식(ReDoS 위험)·과도한 길이 제한은 버린다."""
    f = F("TEXT", validation={"pattern": r"^(a+)+$", "hint": "<b>x</b>", "maxLength": 10**9, "evil": 1})
    assert f.validation == {"maxLength": 2000}
    assert normalize_value(f, "a" * 30 + "!") == "a" * 30 + "!"
    with pytest.raises(FieldValueError):
        normalize_value(f, "a" * 201)


def test_templates_include_employment_forms_with_notes():
    from app.services import catalog
    ids = {t["id"]: t for t in catalog.list_templates()}
    assert {"employment", "employment_daily"} <= ids.keys()
    assert "근로기준법" in ids["employment"]["note"] and "일용" in ids["employment_daily"]["name"]
    for tid in ("employment", "employment_daily"):
        t = catalog.get_template(tid)
        FieldSpec.model_validate(t["fields"][0])
        assert any(f["type"] == "SIGNATURE" and f["assignee"] == "B" for f in t["fields"])


def test_parttime_day_schedule_patterns():
    from app.services.fields import BREAK_RANGE_PATTERN, WORK_RANGE_PATTERN
    work = F("TEXT", validation={"pattern": WORK_RANGE_PATTERN, "maxLength": 13})
    rest = F("TEXT", validation={"pattern": BREAK_RANGE_PATTERN, "maxLength": 13})
    assert work.validation["example"] == "09:00~13:00"
    for ok in ("09:00~13:00", "18:00 ~ 22:30", "22:00-02:00", "휴무"):
        assert normalize_value(work, ok) == ok
    for ok in ("12:00~12:30", "없음"):
        assert normalize_value(rest, ok) == ok
    for bad in ("9-13", "09:00", "휴일", "없음", "25:00~26:00"):
        with pytest.raises(FieldValueError):
            normalize_value(work, bad)
    with pytest.raises(FieldValueError):
        normalize_value(rest, "휴무")


def test_parttime_template_requires_overtime_premium_of_50_percent():
    from app.services import catalog
    t = catalog.get_template("employment_parttime")
    labels = [f["label"] for f in t["fields"]]
    assert all(f"{d} 근로시간" in labels and f"{d} 휴게시간" in labels for d in catalog.WEEKDAYS)
    assert "100분의 50" in t["body"] and "15시간 미만" in t["note"]
    rate = FieldSpec(**next(f for f in t["fields"] if f["label"] == "초과근로 가산임금률"))
    assert normalize_value(rate, "50") == "50"
    with pytest.raises(FieldValueError):
        normalize_value(rate, "30")


def test_templates_grouped_everyday_first():
    from app.services import catalog
    ts = catalog.list_templates()
    assert [t["id"] for t in ts if t["group"] == "everyday"] == ["loan", "service", "goods"]
    assert {t["id"] for t in ts if t["group"] == "employment"} == {"employment", "employment_daily", "employment_parttime"}
    assert [t["group"] for t in ts] == sorted([t["group"] for t in ts], key=list(catalog.GROUPS).index)
