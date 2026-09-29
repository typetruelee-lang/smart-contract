"""보안 테스트 — 인증, 세션 만료, CSRF, XSS, SQL Injection, Rate limit, 헤더, 개발 API 차단, 로그 PII."""
from __future__ import annotations

import io
import logging
from datetime import datetime, timedelta, timezone

import jwt
import pdfplumber
import pytest

from tests.conftest import complete_contract, create_text_contract


def test_unauthenticated_requests_rejected(client_factory):
    c = client_factory()
    for method, url in [("get", "/api/contracts"), ("post", "/api/contracts"), ("get", "/api/contracts/abc"), ("post", "/api/fields/suggest")]:
        r = getattr(c.c, method)(url, json={}) if method == "post" else c.c.get(url)
        assert r.status_code == 401, url
        assert r.json()["detail"]["code"] == "UNAUTHENTICATED"


def test_expired_session_returns_session_expired(client_factory):
    from app.core.config import get_settings

    c = client_factory()
    user = c.login("hong")
    expired = jwt.encode({"sub": user["id"], "iat": datetime.now(timezone.utc) - timedelta(hours=2),
                          "exp": datetime.now(timezone.utc) - timedelta(hours=1)}, get_settings().JWT_SECRET, algorithm="HS256")
    c.c.cookies.set("kz_session", expired)
    r = c.get("/api/contracts")
    assert r.status_code == 401 and r.json()["detail"]["code"] == "SESSION_EXPIRED"


def test_forged_session_rejected(client_factory):
    c = client_factory()
    user = c.login("hong")
    forged = jwt.encode({"sub": user["id"], "exp": datetime.now(timezone.utc) + timedelta(hours=1)}, "wrong-secret-" * 4, algorithm="HS256")
    c.c.cookies.set("kz_session", forged)
    assert c.get("/api/contracts").status_code == 401
    none_alg = jwt.encode({"sub": user["id"]}, key=None, algorithm="none")
    c.c.cookies.set("kz_session", none_alg)
    assert c.get("/api/contracts").status_code == 401


def test_csrf_required_for_state_changes(client_factory):
    c = client_factory()
    c.login("hong")
    r = c.c.post("/api/contracts", json={"title": "x", "body_text": "y"})  # 헤더 없음
    assert r.status_code == 403 and r.json()["detail"]["code"] == "CSRF"
    r = c.c.post("/api/contracts", json={"title": "x", "body_text": "y"}, headers={"X-CSRF-Token": "wrong"})
    assert r.status_code == 403
    r = c.post("/api/contracts", {"title": "x", "body_text": "y"})
    assert r.status_code == 200


def test_session_cookie_flags(client_factory):
    c = client_factory()
    r = c.c.post("/api/auth/mock-login", json={"test_user": "hong"})
    cookies = r.headers.get_list("set-cookie")
    sess = next(x for x in cookies if x.startswith("kz_session="))
    assert "HttpOnly" in sess and "SameSite=lax" in sess.replace("Lax", "lax")
    csrf = next(x for x in cookies if x.startswith("kz_csrf="))
    assert "HttpOnly" not in csrf


def test_security_headers(client_factory):
    r = client_factory().get("/api/health")
    for h in ("X-Content-Type-Options", "X-Frame-Options", "Content-Security-Policy", "Referrer-Policy"):
        assert h in r.headers
    assert r.headers["X-Frame-Options"] == "DENY"


XSS = '<script>alert("x")</script><img src=x onerror=alert(1)>'


def test_xss_payload_is_escaped_in_pdf_and_api(client_factory):
    a, b = client_factory(), client_factory()
    a.login("hong")
    b.login("kim")
    body = f"계약서\n\n내용: {XSS}\n\n이름: {{이름}}\n"
    fields = [{"label": "이름", "type": "TEXT", "value": XSS}]
    r = a.post("/api/contracts", {"title": f"제목 {XSS}"[:100], "body_text": body, "fields": fields})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    token = a.post(f"/api/contracts/{cid}/invite").json()["invite_token"]
    b.post(f"/api/invites/{token}/accept")
    from tests.conftest import sign

    sign(b, cid)
    sign(a, cid)
    pdf = a.get(f"/api/contracts/{cid}/pdf/contract").content
    with pdfplumber.open(io.BytesIO(pdf)) as d:
        txt = "".join(p.extract_text() or "" for p in d.pages)
    # 스크립트가 실행되지 않고 문자 그대로 출력되어야 한다
    assert "<script>" in txt.replace(" ", "") or "&lt;script" in txt
    # API 는 JSON 으로만 반환 (content-type)
    assert a.get(f"/api/contracts/{cid}").headers["content-type"].startswith("application/json")


def test_xss_in_field_label_rejected(client_factory):
    a = client_factory()
    a.login("hong")
    r = a.post("/api/contracts", {"title": "t", "body_text": "{<b>}", "fields": [{"label": "<b>", "type": "TEXT"}]})
    assert r.status_code == 422


@pytest.mark.parametrize("payload", ["' OR '1'='1", "1; DROP TABLE contracts; --", "\" OR 1=1 --", "V-' UNION SELECT * FROM users --"])
def test_sql_injection_attempts_are_harmless(client_factory, payload, db):
    from sqlalchemy import text

    a = client_factory()
    a.login("hong")
    assert a.get(f"/api/contracts/{payload}").status_code == 404
    r = client_factory().get(f"/api/verify/{payload}")
    assert r.status_code == 404
    r = client_factory().post("/api/verify/check", {"verification_id": payload, "document_hash": "a" * 64})
    assert r.status_code in (404, 422)
    r = a.post("/api/contracts", {"title": payload, "body_text": payload})
    assert r.status_code == 200
    assert db.execute(text("select count(*) from contracts")).scalar() >= 1  # 테이블 멀쩡


def test_rate_limit(client_factory, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "RATE_LIMIT_VERIFY_PER_MINUTE", 5)
    c = client_factory()
    codes = [c.c.get("/api/verify/V-AAAA-BBBB-CCCC", headers={"X-RateLimit-Test": "1", "X-Forwarded-For": "10.9.9.9"}).status_code for _ in range(8)]
    assert codes[:5] == [404] * 5 and 429 in codes[5:]


def test_dev_endpoints_disabled_in_production(client_factory, monkeypatch):
    from app.core.config import get_settings

    c = client_factory()
    monkeypatch.setattr(get_settings(), "APP_ENV", "production")
    assert c.c.post("/api/dev/faults", json={"key": "blockchain_fail", "value": 1}).status_code == 404
    assert c.c.post("/api/auth/mock-login", json={"test_user": "hong"}).status_code == 404
    assert c.c.get("/api/admin/status").status_code == 404  # ADMIN_TOKEN 없음


def test_validation_limits(client_factory):
    a = client_factory()
    a.login("hong")
    assert a.post("/api/contracts", {"title": "t", "body_text": "x" * 50_001}).status_code == 422
    assert a.post("/api/contracts", {"title": "", "body_text": "x"}).status_code == 422
    assert a.post("/api/contracts", {"title": "t", "body_text": "{없는칸}"}).status_code == 422
    bad = [{"label": f"f{i}", "type": "TEXT"} for i in range(201)]
    assert a.post("/api/contracts", {"title": "t", "body_text": "x", "fields": bad}).status_code == 422
    assert a.post("/api/contracts", {"title": "t", "body_text": "x", "fields": [{"label": "a", "type": "UNKNOWN"}]}).status_code == 422


def test_signature_image_validation(client_factory):
    a, b = client_factory(), client_factory()
    a.login("hong")
    b.login("kim")
    cid, fields = create_text_contract(a, "계약\n이름: ____\n")
    a.put(f"/api/contracts/{cid}/values", {"values": {fields[0]["field_id"]: "홍길동"}})
    token = a.post(f"/api/contracts/{cid}/invite").json()["invite_token"]
    b.post(f"/api/invites/{token}/accept")
    s = b.post(f"/api/contracts/{cid}/identity/start").json()
    b.post(f"/api/contracts/{cid}/identity/complete", {"session_id": s["session_id"]})
    b.post(f"/api/contracts/{cid}/review", {"version_no": 1, "content_checked": True, "own_will": True, "e_signature_consent": True})
    st = b.post(f"/api/contracts/{cid}/sign/start").json()
    for bad in ["data:image/svg+xml;base64,PHN2Zz4=", "data:image/png;base64,AAAA", "javascript:alert(1)"]:
        r = b.post(f"/api/contracts/{cid}/sign/complete", {"request_id": st["request_id"], "version_no": 1, "signature_image": bad})
        assert r.status_code == 422


def test_identity_failure(client_factory):
    a, b = client_factory(), client_factory()
    a.login("hong")
    b.login("kim")
    cid, fields = create_text_contract(a, "계약\n이름: ____\n")
    a.put(f"/api/contracts/{cid}/values", {"values": {fields[0]["field_id"]: "홍길동"}})
    s = a.post(f"/api/contracts/{cid}/identity/start").json()
    r = a.post(f"/api/contracts/{cid}/identity/complete", {"session_id": s["session_id"], "fail": True})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "IDENTITY_FAILED"


def test_logs_do_not_contain_pii(client_factory, caplog):
    from app.core.logging import PIIMaskingFilter

    caplog.handler.addFilter(PIIMaskingFilter())
    with caplog.at_level(logging.INFO):
        complete_contract(client_factory)
        logging.getLogger("app").warning("user phone 010-9876-5432 email kim@example.com")
    out = caplog.text
    assert "010-9876-5432" not in out and "kim@example.com" not in out
    assert "홍길동" not in out and "김철수" not in out and "10000000" not in out


def test_db_stores_no_plaintext_contract_content(client_factory, db):
    from sqlalchemy import text

    complete_contract(client_factory)
    dump = str(db.execute(text("select * from document_versions")).all()) + str(db.execute(text("select * from contract_parties")).all()) \
        + str(db.execute(text("select * from audit_events")).all()) + str(db.execute(text("select * from users")).all())
    assert "홍길동" not in dump and "김철수" not in dump and "10000000" not in dump and "매월 말일" not in dump
