"""시나리오 2 — PDF 업로드 → 텍스트 추출 → 빈칸 생성 → 값 입력 → PDF 생성 (+ OCR, 업로드 보안)."""
from __future__ import annotations

import hashlib
import io

import pdfplumber
import pytest

from tests.conftest import sign
from tests.fixtures.pdfs import fake_pdf, scanned_pdf, text_pdf


@pytest.fixture(scope="module")
def tpdf():
    return text_pdf()


def test_scenario2_pdf_upload_to_final_pdf(client_factory, tpdf):
    a, b = client_factory(), client_factory()
    a.login("hong")
    b.login("kim")
    an = a.post("/api/uploads/pdf/analyze", files={"file": ("contract.pdf", tpdf, "application/pdf")})
    assert an.status_code == 200, an.text
    data = an.json()
    assert "용역계약서" in data["text"]
    assert data["ocr_used"] is False
    pos = data["position_suggestions"]
    labels = [p["label"] for p in pos]
    assert "발주자" in labels and "수행자" in labels
    # 추천 위치를 필드로 확정 + 사용자가 수동으로 서명 칸 추가
    fields = []
    for p in pos:
        fields.append({"label": p["label"], "type": p["type"], "page": p["page"], "position": p["position"],
                       "assignee": "B" if p["label"] == "수행자" else "A", "required": True})
    fields.append({"label": "발주자 서명", "type": "SIGNATURE", "page": 1, "position": {"x": 0.6, "y": 0.8, "w": 0.25, "h": 0.06}, "assignee": "A"})
    fields.append({"label": "수행자 서명", "type": "SIGNATURE", "page": 1, "position": {"x": 0.6, "y": 0.87, "w": 0.25, "h": 0.06}, "assignee": "B"})
    import json

    r = a.post("/api/contracts/upload", files={"file": ("contract.pdf", tpdf, "application/pdf")},
               data={"title": "용역계약서", "contract_type": "service", "fields_json": json.dumps(fields)})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    view = a.get(f"/api/contracts/{cid}").json()
    assert view["source"] == "PDF" and view["payload"]["pages"][0]["width"] > 500
    fs = {f["label"]: f for f in view["payload"]["fields"]}
    vals = {fs["발주자"]["field_id"]: "주식회사 가나다", fs["용역 대금"]["field_id"]: "3300000", fs["연락처"]["field_id"]: "010-2222-3333"}
    assert a.put(f"/api/contracts/{cid}/values", {"values": vals}).status_code == 200
    # 원본 PDF 는 당사자만 받을 수 있다
    assert a.get(f"/api/contracts/{cid}/source.pdf").content == tpdf
    token = a.post(f"/api/contracts/{cid}/invite").json()["invite_token"]
    b.post(f"/api/invites/{token}/accept")
    assert b.put(f"/api/contracts/{cid}/values", {"values": {fs["수행자"]["field_id"]: "김철수"}}).status_code == 200
    # B 가 A 칸을 수정하려 하면 거부
    r = b.put(f"/api/contracts/{cid}/values", {"values": {fs["발주자"]["field_id"]: "변조"}})
    assert r.status_code == 403
    sign(b, cid)
    assert sign(a, cid)["completed"] is True
    pdf = a.get(f"/api/contracts/{cid}/pdf/contract").content
    view = a.get(f"/api/contracts/{cid}").json()
    assert hashlib.sha256(pdf).hexdigest() == view["document_hash"]
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        assert len(doc.pages) >= 2
        p1 = doc.pages[0].extract_text()
        allt = "\n".join(p.extract_text() or "" for p in doc.pages)
    assert "주식회사 가나다" in p1 and "3,300,000" in p1 and "김철수" in p1
    assert "전자서명 정보" in allt
    assert view["final_version_no"] == 2  # v1(초대 시 봉인) → v2(상대방 입력)


def test_scanned_pdf_uses_ocr(client_factory):
    a = client_factory()
    a.login("hong")
    r = a.post("/api/uploads/pdf/analyze", files={"file": ("scan.pdf", scanned_pdf(), "application/pdf")})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ocr_used"] is True and d["pages"][0]["ocr"] is True
    assert "매도인" in d["text"] and "매수인" in d["text"]
    labels = {s["label"] for s in d["suggestions"]}
    assert {"매도인", "매수인"} <= labels


@pytest.mark.parametrize("name,content,ctype,msg", [
    ("x.png", b"%PDF-1.4 ...", "application/pdf", "PDF 파일(.pdf)만"),
    ("fake.pdf", None, "application/pdf", "실제 PDF 파일이 아니에요"),
    ("x.pdf", b"%PDF-1.4 garbage", "application/pdf", "손상"),
    ("x.pdf", b"%PDF-1.4", "image/png", "PDF 파일 형식이 아니에요"),
    ("x.pdf", b"", "application/pdf", "빈 파일"),
])
def test_upload_rejects_bad_files(client_factory, name, content, ctype, msg):
    a = client_factory()
    a.login("hong")
    content = fake_pdf() if content is None else content
    r = a.post("/api/uploads/pdf/analyze", files={"file": (name, content, ctype)})
    assert r.status_code == 422
    assert msg in r.json()["detail"]["message"]


def test_upload_too_large(client_factory, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "MAX_UPLOAD_MB", 1)
    a = client_factory()
    a.login("hong")
    big = b"%PDF-1.4\n" + b"0" * (1024 * 1024 + 10)
    r = a.post("/api/uploads/pdf/analyze", files={"file": ("big.pdf", big, "application/pdf")})
    assert r.status_code == 422 and "너무 커요" in r.json()["detail"]["message"]


def test_encrypted_pdf_rejected(client_factory, tpdf):
    from pypdf import PdfReader, PdfWriter

    w = PdfWriter()
    for p in PdfReader(io.BytesIO(tpdf)).pages:
        w.add_page(p)
    w.encrypt("pw")
    buf = io.BytesIO()
    w.write(buf)
    a = client_factory()
    a.login("hong")
    r = a.post("/api/uploads/pdf/analyze", files={"file": ("enc.pdf", buf.getvalue(), "application/pdf")})
    assert r.status_code == 422 and "암호" in r.json()["detail"]["message"]


def test_pdf_contract_requires_field_positions(client_factory, tpdf):
    import json

    a = client_factory()
    a.login("hong")
    r = a.post("/api/contracts/upload", files={"file": ("c.pdf", tpdf, "application/pdf")},
               data={"title": "t", "fields_json": json.dumps([{"label": "이름", "type": "TEXT"}])})
    assert r.status_code == 422 and "위치" in r.json()["detail"]["message"]
