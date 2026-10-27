"""OpenTimestamps 로 운영할 때의 전체 흐름: 결제 → 제출(SUBMITTED) → 비트코인 포함 후 확정 → .ots 내려받기 → 공개 검증."""
from datetime import timedelta

import httpx
import pytest
from opentimestamps.core.serialize import BytesDeserializationContext
from opentimestamps.core.timestamp import DetachedTimestampFile

from app.core.db import SessionLocal
from app.services import anchoring
from tests.conftest import complete_contract
from tests.unit.test_ots import CAL, HEIGHT, FakeNet


@pytest.fixture
def ots_net(monkeypatch):
    from app.core import config
    from app.providers import ots

    net = FakeNet()
    monkeypatch.setenv("BLOCKCHAIN_PROVIDER", "opentimestamps")
    monkeypatch.setenv("OTS_CALENDARS", CAL)
    config.get_settings.cache_clear()
    real = httpx.Client
    monkeypatch.setattr(ots.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(net.handler)))
    yield net
    config.get_settings.cache_clear()


def test_ots_anchoring_flow(client_factory, ots_net):
    a, _, cid = complete_contract(client_factory)
    co = a.post(f"/api/contracts/{cid}/anchor/checkout").json()
    r = a.post(f"/api/contracts/{cid}/anchor/confirm", {"payment_id": co["payment_id"], "result": "success"}).json()
    assert r["payment_status"] == "PAID" and r["anchor_status"] == "SUBMITTED"  # 비트코인 포함 대기
    st = a.get(f"/api/contracts/{cid}/anchor").json()["anchor"]
    assert st["provider"] == "opentimestamps" and st["proof_available"] and st["explorer_url"] is None
    # 대기 중에도 .ots(대기 증명)를 내려받을 수 있다
    pending = a.get(f"/api/contracts/{cid}/anchor/proof")
    assert pending.status_code == 200 and pending.headers["content-disposition"].endswith('.pdf.ots"')
    # 다음 확인은 OTS_POLL_SECONDS 뒤로 예약된다
    with SessionLocal() as db:
        from app.models import AnchorJob
        job = db.query(AnchorJob).filter_by(contract_id=cid).one()
        assert job.next_attempt_at - job.submitted_at >= timedelta(seconds=1700)
    # 비트코인 블록에 포함됨 → 워커가 확정
    ots_net.mined = True
    with SessionLocal() as db:
        anchoring.run_due_jobs(db, force=True)
    st = a.get(f"/api/contracts/{cid}/anchor").json()["anchor"]
    assert st["status"] == "CONFIRMED" and st["block_number"] == HEIGHT
    assert st["explorer_url"].endswith(f"/block-height/{HEIGHT}")
    proof = a.get(f"/api/contracts/{cid}/anchor/proof").content
    dtf = DetachedTimestampFile.deserialize(BytesDeserializationContext(proof))
    assert dtf.file_digest.hex() == a.get(f"/api/contracts/{cid}").json()["document_hash"]
    # 공개 검증: 원본 PDF Hash 로 조회하면 기록 완료로 보인다
    pdf_hash = a.get(f"/api/contracts/{cid}").json()["document_hash"]
    vid = a.get(f"/api/contracts/{cid}").json()["verification_id"]
    v = a.post("/api/verify/check", {"verification_id": vid, "document_hash": pdf_hash}).json()
    assert v["match"] is True
    pub = client_factory().get(f"/api/verify/{vid}").json()
    assert "CONFIRMED" in str(pub) or "기록 완료" in str(pub)


def test_ots_certificate_shows_bitcoin_block_and_independent_verification(client_factory, ots_net):
    import io

    import pdfplumber

    a, _, cid = complete_contract(client_factory)
    co = a.post(f"/api/contracts/{cid}/anchor/checkout").json()
    a.post(f"/api/contracts/{cid}/anchor/confirm", {"payment_id": co["payment_id"], "result": "success"})
    ots_net.mined = True
    with SessionLocal() as db:
        anchoring.run_due_jobs(db, force=True)
    cert = a.get(f"/api/contracts/{cid}/pdf/certificate").content
    with pdfplumber.open(io.BytesIO(cert)) as doc:
        txt = "".join((p.extract_text() or "") for p in doc.pages).replace("\n", "")
    assert "OpenTimestamps" in txt and f"#{HEIGHT}" in txt and "opentimestamps.org" in txt and "기록 완료" in txt
