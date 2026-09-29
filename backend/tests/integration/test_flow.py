"""통합 테스트 — 지시서 시나리오 1, 3, 4, 5 + 문서 버전/서명 무효화."""
from __future__ import annotations

import hashlib

from tests.conftest import complete_contract, create_text_contract, sign


def test_scenario1_text_contract_to_pdf(client_factory):
    """로그인 → 계약 생성 → 텍스트 입력 → 빈칸 생성 → 값 입력 → PDF 생성 → 완료"""
    a, b, cid = complete_contract(client_factory)
    view = a.get(f"/api/contracts/{cid}").json()
    assert view["status"] == "COMPLETED"
    assert view["final_version_no"] == 1
    assert len(view["document_hash"]) == 64
    assert view["verification_id"].startswith("V-")
    pdf = a.get(f"/api/contracts/{cid}/pdf/contract")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF-")
    assert hashlib.sha256(pdf.content).hexdigest() == view["document_hash"]
    # 상대방도 같은 파일을 받는다
    assert b.get(f"/api/contracts/{cid}/pdf/contract").content == pdf.content
    # PDF 텍스트에 입력값이 들어갔는지
    import io

    import pdfplumber

    with pdfplumber.open(io.BytesIO(pdf.content)) as doc:
        txt = "\n".join((p.extract_text() or "") for p in doc.pages)
    assert "10,000,000" in txt and "김철수" in txt and "2027년 3월 31일" in txt
    assert "전자서명 정보" in txt


def test_audit_events_complete_and_chained(client_factory):
    a, _, cid = complete_contract(client_factory)
    r = a.get(f"/api/contracts/{cid}/events").json()
    types = [e["event_type"] for e in r["events"]]
    for t in ["CONTRACT_CREATED", "CONTRACT_VIEWED", "IDENTITY_VERIFIED", "CONTRACT_REVIEWED", "SIGNATURE_STARTED",
              "SIGNATURE_COMPLETED", "CONTRACT_COMPLETED", "PDF_GENERATED", "HASH_CREATED"]:
        assert t in types, t
    assert r["chain_valid"] is True
    for e in r["events"]:
        assert set(e) >= {"event_id", "contract_id", "actor_id", "event_type", "timestamp", "document_version", "document_hash", "metadata"}


def test_audit_chain_detects_tampering(client_factory, db):
    from sqlalchemy import select

    from app.models import AuditEvent
    from app.services import evidence

    a, _, cid = complete_contract(client_factory)
    ev = db.scalars(select(AuditEvent).where(AuditEvent.contract_id == cid).order_by(AuditEvent.seq)).all()[2]
    ev.event_type = "CONTRACT_CANCELED"
    db.commit()
    assert evidence.verify_chain(db, cid) is False


def test_scenario3_blockchain_mock_tx_and_certificate(client_factory):
    """계약 완료 → Hash → Blockchain Mock → TX 생성 → 확인서 생성"""
    a, _, cid = complete_contract(client_factory)
    co = a.post(f"/api/contracts/{cid}/anchor/checkout").json()
    assert co["amount"] == 990
    r = a.post(f"/api/contracts/{cid}/anchor/confirm", {"payment_id": co["payment_id"], "result": "success"}).json()
    assert r["payment_status"] == "PAID"
    assert r["anchor_status"] == "CONFIRMED"
    st = a.get(f"/api/contracts/{cid}/anchor").json()["anchor"]
    assert st["tx_id"].startswith("0x") and len(st["tx_id"]) == 66
    cert = a.get(f"/api/contracts/{cid}/pdf/certificate")
    assert cert.status_code == 200 and cert.content.startswith(b"%PDF-")
    import io

    import pdfplumber

    with pdfplumber.open(io.BytesIO(cert.content)) as doc:
        txt = "\n".join((p.extract_text() or "") for p in doc.pages)
    view = a.get(f"/api/contracts/{cid}").json()
    assert "전자계약 확인서" in txt
    assert view["verification_id"] in txt
    assert view["document_hash"][:20] in txt.replace("\n", "")
    assert "기록 완료" in txt
    types = [e["event_type"] for e in a.get(f"/api/contracts/{cid}/events").json()["events"]]
    assert "BLOCKCHAIN_SUBMITTED" in types and "BLOCKCHAIN_CONFIRMED" in types


def test_scenario4_verify_original_pdf_success(client_factory):
    a, _, cid = complete_contract(client_factory)
    pdf = a.get(f"/api/contracts/{cid}/pdf/contract").content
    vid = a.get(f"/api/contracts/{cid}").json()["verification_id"]
    anon = client_factory()
    r = anon.post("/api/verify/check", {"verification_id": vid, "document_hash": hashlib.sha256(pdf).hexdigest()}).json()
    assert r["match"] is True
    r2 = anon.post("/api/verify/upload", files={"file": ("c.pdf", pdf, "application/pdf")}, data={"verification_id": vid}).json()
    assert r2["match"] is True
    # 공개 조회는 개인정보를 포함하지 않는다
    pub = anon.get(f"/api/verify/{vid}").json()
    blob = str(pub)
    assert "홍길동" not in blob and "김철수" not in blob and "홍*동" not in blob
    assert set(pub) == {"verification_id", "contract_status", "completed_at", "document_hash", "document_hash_short", "anchor"}


def test_scenario5_modified_pdf_fails(client_factory):
    a, _, cid = complete_contract(client_factory)
    pdf = bytearray(a.get(f"/api/contracts/{cid}/pdf/contract").content)
    vid = a.get(f"/api/contracts/{cid}").json()["verification_id"]
    # 한 바이트만 바꿈
    idx = len(pdf) // 2
    pdf[idx] = (pdf[idx] + 1) % 256
    r = client_factory().post("/api/verify/check", {"verification_id": vid, "document_hash": hashlib.sha256(bytes(pdf)).hexdigest()}).json()
    assert r["match"] is False
    assert "다릅니다" in r["message"]


def test_version_bump_invalidates_signature(client_factory):
    """B 가 서명한 뒤 A 가 내용을 바꾸면 v2 가 생기고 B 의 서명이 무효화된다."""
    a, b = client_factory(), client_factory()
    a.login("hong")
    b.login("kim")
    cid, fields = create_text_contract(a)
    by = {f["label"]: f for f in fields}
    vals = {by["대여금액"]["field_id"]: "5000000", by["채권자"]["field_id"]: "홍길동", by["채무자"]["field_id"]: "김철수",
            by["상환일"]["field_id"]: "2027-01-31", by["이자율"]["field_id"]: "3"}
    a.put(f"/api/contracts/{cid}/values", {"values": vals})
    token = a.post(f"/api/contracts/{cid}/invite").json()["invite_token"]
    b.post(f"/api/invites/{token}/accept")
    sign(b, cid)
    view = a.get(f"/api/contracts/{cid}").json()
    assert view["status"] == "SIGNING"
    # A 가 금액 변경 → 봉인된 v1 → v2
    r = a.put(f"/api/contracts/{cid}/values", {"values": {by["대여금액"]["field_id"]: "6000000"}})
    assert r.json()["version_no"] == 2
    view = a.get(f"/api/contracts/{cid}").json()
    pb = next(p for p in view["parties"] if p["role"] == "B")
    assert pb["signature_status"] == "INVALIDATED"
    assert view["status"] == "INVITED"
    diff = a.get(f"/api/contracts/{cid}/versions/1/diff/2").json()
    assert diff["changes"][0]["before"] == "5000000" and diff["changes"][0]["after"] == "6000000"
    types = [e["event_type"] for e in a.get(f"/api/contracts/{cid}/events").json()["events"]]
    assert "VERSION_CREATED" in types and "SIGNATURE_INVALIDATED" in types
    # 둘 다 v2 에 다시 서명 → 완료, 최종 버전은 v2
    sign(b, cid)
    assert sign(a, cid)["completed"] is True
    view = a.get(f"/api/contracts/{cid}").json()
    assert view["final_version_no"] == 2
    assert [v["status"] for v in view["versions"]] == ["PROPOSED", "FINAL"]


def test_stale_review_rejected(client_factory):
    a, b = client_factory(), client_factory()
    a.login("hong")
    b.login("kim")
    cid, fields = create_text_contract(a)
    by = {f["label"]: f for f in fields}
    a.put(f"/api/contracts/{cid}/values", {"values": {by["대여금액"]["field_id"]: "1", by["채권자"]["field_id"]: "a", by["채무자"]["field_id"]: "b",
                                                        by["상환일"]["field_id"]: "2027-01-01", by["이자율"]["field_id"]: "1"}})
    token = a.post(f"/api/contracts/{cid}/invite").json()["invite_token"]
    b.post(f"/api/invites/{token}/accept")
    r = b.post(f"/api/contracts/{cid}/review", {"version_no": 99, "content_checked": True, "own_will": True, "e_signature_consent": True})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "VERSION_CHANGED"
    r = b.post(f"/api/contracts/{cid}/review", {"version_no": 1, "content_checked": True, "own_will": False, "e_signature_consent": True})
    assert r.status_code == 422
    # 본인확인 없이 서명 시작 불가
    b.post(f"/api/contracts/{cid}/review", {"version_no": 1, "content_checked": True, "own_will": True, "e_signature_consent": True})
    r = b.post(f"/api/contracts/{cid}/sign/start")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "IDENTITY_REQUIRED"


def test_access_control_other_user_gets_404(client_factory):
    a, _, cid = complete_contract(client_factory)
    c = client_factory()
    c.login("lee")
    assert c.get(f"/api/contracts/{cid}").status_code == 404
    assert c.get(f"/api/contracts/{cid}/pdf/contract").status_code == 404


def test_invite_token_single_use_and_self_invite_blocked(client_factory):
    a, b, c = client_factory(), client_factory(), client_factory()
    a.login("hong")
    b.login("kim")
    c.login("lee")
    cid, fields = create_text_contract(a)
    by = {f["label"]: f for f in fields}
    a.put(f"/api/contracts/{cid}/values", {"values": {by["대여금액"]["field_id"]: "1", by["채권자"]["field_id"]: "a", by["채무자"]["field_id"]: "b",
                                                        by["상환일"]["field_id"]: "2027-01-01", by["이자율"]["field_id"]: "1"}})
    token = a.post(f"/api/contracts/{cid}/invite").json()["invite_token"]
    assert a.post(f"/api/invites/{token}/accept").status_code == 409
    assert b.post(f"/api/invites/{token}/accept").status_code == 200
    assert c.post(f"/api/invites/{token}/accept").status_code == 404
