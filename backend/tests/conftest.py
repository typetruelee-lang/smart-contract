from __future__ import annotations

import base64
import io
import os
import secrets

os.environ.setdefault("APP_ENV", "test")
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://contract:contract@localhost:5432/contract_test")
os.environ.setdefault("JWT_SECRET", secrets.token_urlsafe(48))
os.environ.setdefault("DATA_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
os.environ.setdefault("BLOCKCHAIN_PROVIDER", "mock")
os.environ.setdefault("PAYMENT_PROVIDER", "mock")
os.environ.setdefault("ANCHOR_RETRY_BASE_SECONDS", "0")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import Base, SessionLocal, get_engine  # noqa: E402
import app.models  # noqa: E402,F401

get_settings.cache_clear()


@pytest.fixture(scope="session", autouse=True)
def _schema():
    eng = get_engine()
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield


@pytest.fixture(autouse=True)
def _clean():
    eng = get_engine()
    with eng.begin() as conn:
        names = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    from app.core.rate_limit import limiter

    limiter.reset()
    yield


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


class ApiClient:
    def __init__(self, app):
        self.c = TestClient(app)
        self.csrf = None

    def login(self, who: str):
        r = self.c.post("/api/auth/mock-login", json={"test_user": who})
        assert r.status_code == 200, r.text
        self.csrf = r.json()["csrf_token"]
        return r.json()["user"]

    def _h(self, extra=None):
        h = {"X-CSRF-Token": self.csrf} if self.csrf else {}
        h.update(extra or {})
        return h

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, json=None, **kw):
        return self.c.post(url, json=json, headers=self._h(kw.pop("headers", None)), **kw)

    def put(self, url, json=None, **kw):
        return self.c.put(url, json=json, headers=self._h(kw.pop("headers", None)), **kw)


@pytest.fixture
def app():
    from app.main import create_app

    return create_app()


@pytest.fixture
def client_factory(app):
    return lambda: ApiClient(app)


def signature_png() -> str:
    img = Image.new("RGBA", (300, 100), (255, 255, 255, 0))
    d = ImageDraw.Draw(img)
    d.line([(10, 70), (80, 20), (150, 80), (220, 30), (290, 60)], fill=(20, 20, 20, 255), width=4)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


LOAN_TEXT = """금전소비대차계약서

대여금액: __________ 원

채권자: __________

채무자: __________

상환일: ____년 __월 __일

이자율: 연 ____%

특약사항:

________________________

________________________
"""


def create_text_contract(a: ApiClient, text_body: str = LOAN_TEXT, title: str = "금전소비대차계약서") -> tuple[str, list[dict]]:
    sug = a.post("/api/fields/suggest", {"text": text_body}).json()["suggestions"]
    applied = a.post("/api/fields/apply", {"text": text_body, "suggestions": sug}).json()
    fields = applied["fields"]
    r = a.post("/api/contracts", {"title": title, "source": "TEXT", "contract_type": "loan", "body_text": applied["text"], "fields": fields})
    assert r.status_code == 200, r.text
    return r.json()["id"], fields


def sign(client: ApiClient, cid: str) -> dict:
    view = client.get(f"/api/contracts/{cid}").json()
    s = client.post(f"/api/contracts/{cid}/identity/start").json()
    assert client.post(f"/api/contracts/{cid}/identity/complete", {"session_id": s["session_id"]}).status_code == 200
    r = client.post(f"/api/contracts/{cid}/review", {"version_no": view["current_version_no"], "content_checked": True, "own_will": True, "e_signature_consent": True})
    assert r.status_code == 200, r.text
    st = client.post(f"/api/contracts/{cid}/sign/start").json()
    r = client.post(f"/api/contracts/{cid}/sign/complete", {"request_id": st["request_id"], "version_no": st["version_no"], "signature_image": signature_png()})
    assert r.status_code == 200, r.text
    return r.json()


def complete_contract(factory) -> tuple[ApiClient, ApiClient, str]:
    """A(홍길동) 작성 → 초대 → B(김철수) 참여·입력·서명 → A 서명 → 완료."""
    a, b = factory(), factory()
    a.login("hong")
    b.login("kim")
    cid, fields = create_text_contract(a)
    by = {f["label"]: f for f in fields}
    vals = {by["대여금액"]["field_id"]: "10000000", by["채권자"]["field_id"]: "홍길동", by["채무자"]["field_id"]: "김철수",
            by["상환일"]["field_id"]: "2027-03-31", by["이자율"]["field_id"]: "5", by["특약사항"]["field_id"]: "매월 말일 이자 지급"}
    assert a.put(f"/api/contracts/{cid}/values", {"values": vals}).status_code == 200
    inv = a.post(f"/api/contracts/{cid}/invite").json()
    token = inv["invite_token"]
    assert b.post(f"/api/invites/{token}/accept").status_code == 200
    r1 = sign(b, cid)
    assert r1["completed"] is False
    r2 = sign(a, cid)
    assert r2["completed"] is True
    return a, b, cid
