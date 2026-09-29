"""테스트 데이터 — 계약서 4종 × (정상/빈/잘못된/긴/한글/특수문자/숫자/날짜)."""
from __future__ import annotations

import pytest

from app.services import catalog
from tests.conftest import sign

TEMPLATE_IDS = ["loan", "service", "goods", "employment"]


def _good_value(f):
    return {
        "TEXT": "홍길동", "NUMBER": "1500000", "DATE": "2027-06-30", "PHONE": "010-1234-5678", "EMAIL": "test@example.com",
        "LONG_TEXT": "특약 없음", "CHECKBOX": True,
    }.get(f["type"], f["options"][0] if f["type"] == "SELECT" else None)


def _bad_value(f):
    return {"NUMBER": "천원", "DATE": "2027-02-30", "PHONE": "12-34", "EMAIL": "메일주소", "SELECT": "없는선택지", "TEXT": "a" * 300,
            "LONG_TEXT": "b" * 2500, "CHECKBOX": "maybe"}.get(f["type"])


def _create(a, tid):
    t = catalog.get_template(tid)
    r = a.post("/api/contracts", {"title": t["title"], "source": "TEMPLATE", "contract_type": t["contract_type"], "body_text": t["body"], "fields": t["fields"]})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    return cid, a.get(f"/api/contracts/{cid}").json()["payload"]["fields"]


def _fill(client, cid, fields, role, maker):
    vals = {f["field_id"]: maker(f) for f in fields if f["assignee"] == role and f["type"] != "SIGNATURE"}
    return client.put(f"/api/contracts/{cid}/values", {"values": vals})


@pytest.mark.parametrize("tid", TEMPLATE_IDS)
def test_template_normal_full_flow(client_factory, tid):
    a, b = client_factory(), client_factory()
    a.login("hong")
    b.login("kim")
    cid, fields = _create(a, tid)
    assert _fill(a, cid, fields, "A", _good_value).status_code == 200
    token = a.post(f"/api/contracts/{cid}/invite").json()["invite_token"]
    b.post(f"/api/invites/{token}/accept")
    assert _fill(b, cid, fields, "B", _good_value).status_code == 200
    sign(b, cid)
    assert sign(a, cid)["completed"] is True
    v = a.get(f"/api/contracts/{cid}").json()
    assert v["status"] == "COMPLETED"
    # SIGNATURE 필드가 서명으로 채워졌는지
    sig_fields = [f for f in v["payload"]["fields"] if f["type"] == "SIGNATURE"]
    assert sig_fields and all(str(f["value"]).startswith("sig:") for f in sig_fields)
    assert a.get(f"/api/contracts/{cid}/pdf/contract").status_code == 200


@pytest.mark.parametrize("tid", TEMPLATE_IDS)
def test_template_empty_data_blocks_invite(client_factory, tid):
    a = client_factory()
    a.login("hong")
    cid, _ = _create(a, tid)
    r = a.post(f"/api/contracts/{cid}/invite")
    assert r.status_code == 422 and r.json()["detail"]["code"] == "MISSING_FIELDS"


@pytest.mark.parametrize("tid", TEMPLATE_IDS)
def test_template_invalid_data_rejected(client_factory, tid):
    a = client_factory()
    a.login("hong")
    cid, fields = _create(a, tid)
    for f in fields:
        if f["assignee"] != "A" or f["type"] == "SIGNATURE":
            continue
        bad = _bad_value(f)
        if bad is None:
            continue
        r = a.put(f"/api/contracts/{cid}/values", {"values": {f["field_id"]: bad}})
        assert r.status_code == 422, (f["label"], bad, r.text)
        assert r.json()["detail"]["field_id"] == f["field_id"]


@pytest.mark.parametrize("tid", TEMPLATE_IDS)
@pytest.mark.parametrize("kind,maker", [
    ("long", lambda f: ("가" * 200 if f["type"] == "TEXT" else "나" * 2000 if f["type"] == "LONG_TEXT" else _good_value(f))),
    ("korean", lambda f: ("대한민국 서울특별시 종로구" if f["type"] == "TEXT" else "한글 특약: 가나다라마바사" if f["type"] == "LONG_TEXT" else _good_value(f))),
    ("special", lambda f: ("!@#$%^&*()_+-=[]{};':\",./<>?`~\\|" if f["type"] in ("TEXT", "LONG_TEXT") else _good_value(f))),
    ("numbers", lambda f: ("999999999999" if f["type"] == "NUMBER" else "12345" if f["type"] == "TEXT" else _good_value(f))),
    ("dates", lambda f: ("2028-02-29" if f["type"] == "DATE" else _good_value(f))),
])
def test_template_data_kinds_render_pdf(client_factory, tid, kind, maker):
    """긴/한글/특수문자/숫자/날짜 값이 저장되고 미리보기 PDF 가 만들어진다."""
    a = client_factory()
    a.login("hong")
    cid, fields = _create(a, tid)
    r = _fill(a, cid, fields, "A", maker)
    assert r.status_code == 200, r.text
    pdf = a.get(f"/api/contracts/{cid}/pdf/preview")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
