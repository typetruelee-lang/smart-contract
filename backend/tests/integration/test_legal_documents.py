"""제출용 증빙 PDF · 법적 고지 · 시험용 표시 · 확인서 진위 확인."""
from __future__ import annotations

import hashlib
import io

import pdfplumber
from sqlalchemy import select

from app.models import AuditEvent, CertificateIssuance
from tests.conftest import complete_contract, create_text_contract


def _text(pdf: bytes) -> tuple[str, int]:
    with pdfplumber.open(io.BytesIO(pdf)) as d:
        return "\n".join((p.extract_text() or "") for p in d.pages), len(d.pages)


def test_certificate_is_submission_grade(client_factory, db):
    a, _, cid = complete_contract(client_factory)
    r = a.get(f"/api/contracts/{cid}/pdf/certificate")
    assert r.status_code == 200
    txt, pages = _text(r.content)
    view = a.get(f"/api/contracts/{cid}").json()
    flat = txt.replace("\n", "")
    # 발급번호 · 쪽번호 · 발급자
    cert = db.scalar(select(CertificateIssuance).where(CertificateIssuance.contract_id == cid))
    assert cert.issue_no in txt and cert.issue_no in r.headers["content-disposition"]
    assert f"1 / {pages} 쪽" in txt
    assert "발급자" in txt
    # 계약·당사자·지문·검증
    for s in ("전자계약 체결 확인서", view["contract_no"], view["verification_id"], "당사자 A", "당사자 B", "본인확인", "서명 대상 내용의 SHA-256"):
        assert s in txt, s
    assert view["document_hash"][:32] in flat
    # 진행 기록(감사 로그) 표와 사슬 무결성
    for s in ("진행 기록", "계약서 작성", "본인확인 완료", "최종 확인·동의", "서명 완료", "계약 완료", "디지털 지문 생성", "감사 로그 무결성", "정상"):
        assert s in txt, s
    last = db.scalars(select(AuditEvent).where(AuditEvent.contract_id == cid, AuditEvent.event_type != "CERTIFICATE_GENERATED")
                      .order_by(AuditEvent.seq.desc())).first()
    assert last is not None
    # 검증 방법 · 유의사항(책임 한계)
    for s in ("검증 방법", "certutil -hashfile", "shasum -a 256", "유의사항", "보증하거나 공증하는 문서가 아닙니다", "회사는 계약의 당사자가 아니며", "법원의 판단"):
        assert s in flat.replace(" ", "") or s in txt, s
    # 개발 환경(모의 서명) → 시험용 표시
    assert "시험용" in txt and "법적 효력이 없습니다" in flat.replace(" ", "").replace("효력이없습니다", "효력이 없습니다") or "법적 효력이 없습니다" in txt
    assert cert.test_mode is True and cert.sha256 == hashlib.sha256(r.content).hexdigest()


def test_contract_pdf_has_footer_notice_and_test_watermark(client_factory):
    a, _, cid = complete_contract(client_factory)
    pdf = a.get(f"/api/contracts/{cid}/pdf/contract").content
    txt, pages = _text(pdf)
    view = a.get(f"/api/contracts/{cid}").json()
    assert f"계약번호 {view['contract_no']}" in txt and f"/ {pages} 쪽" in txt
    assert "유의사항" in txt and "시험용(모의) 서명" in txt and "시험용" in txt
    assert "계약의 당사자가 아니고" in txt.replace("\n", "")


def test_certificate_itself_can_be_verified(client_factory):
    a, _, cid = complete_contract(client_factory)
    cert = a.get(f"/api/contracts/{cid}/pdf/certificate").content
    vid = a.get(f"/api/contracts/{cid}").json()["verification_id"]
    anon = client_factory()
    r = anon.post("/api/verify/check", {"document_hash": hashlib.sha256(cert).hexdigest()}).json()
    assert r["match"] is True and r["kind"] == "CERTIFICATE" and r["issue_no"].startswith("C-") and r["test_mode"] is True
    r2 = anon.post("/api/verify/check", {"verification_id": vid, "document_hash": hashlib.sha256(cert).hexdigest()}).json()
    assert r2["match"] is True and r2["kind"] == "CERTIFICATE"
    # 확인서를 한 바이트라도 고치면 불일치
    bad = bytearray(cert)
    bad[len(bad) // 2] ^= 1
    r3 = anon.post("/api/verify/check", {"document_hash": hashlib.sha256(bytes(bad)).hexdigest()}).json()
    assert r3["match"] is False
    # 계약서 PDF 검증은 kind=CONTRACT
    pdf = a.get(f"/api/contracts/{cid}/pdf/contract").content
    assert anon.post("/api/verify/check", {"verification_id": vid, "document_hash": hashlib.sha256(pdf).hexdigest()}).json()["kind"] == "CONTRACT"


def test_review_requires_retention_acknowledgement_and_records_consent(client_factory, db):
    a, b = client_factory(), client_factory()
    a.login("hong")
    b.login("kim")
    cid, fields = create_text_contract(a, "계약\n이름: ____\n")
    a.put(f"/api/contracts/{cid}/values", {"values": {fields[0]["field_id"]: "홍길동"}})
    token = a.post(f"/api/contracts/{cid}/invite").json()["invite_token"]
    b.post(f"/api/invites/{token}/accept")
    r = b.post(f"/api/contracts/{cid}/review", {"version_no": 1, "content_checked": True, "own_will": True, "e_signature_consent": True})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "CONFIRM_REQUIRED"
    r = b.post(f"/api/contracts/{cid}/review", {"version_no": 1, "content_checked": True, "own_will": True, "e_signature_consent": True,
                                                "retention_acknowledged": True})
    assert r.status_code == 200
    ev = db.scalars(select(AuditEvent).where(AuditEvent.contract_id == cid, AuditEvent.event_type == "CONTRACT_REVIEWED")).first()
    assert "retention_acknowledged" in ev.event_metadata["confirmations"] and ev.event_metadata["consent_version"]


def test_production_grade_signatures_have_no_test_watermark(client_factory, db):
    from app.models import ContractParty, Contract
    from app.services import contracts as svc

    a, _, cid = complete_contract(client_factory)
    c = db.get(Contract, cid)
    assert svc.is_test_mode(c) is True
    for p in db.scalars(select(ContractParty).where(ContractParty.contract_id == cid)):
        p.signature_provider = "production"
        p.identity_provider = "production"
    db.commit()
    db.refresh(c)
    assert svc.is_test_mode(c) is False
    txt, _ = _text(a.get(f"/api/contracts/{cid}/pdf/certificate").content)
    i = txt.find("시험용")
    assert i == -1, txt[max(0, i - 120): i + 60]
    assert "토스인증서전자서명" in txt.replace(" ", "").replace("\n", "")
