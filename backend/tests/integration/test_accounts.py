"""회원 탈퇴 · 토스 로그인 연결 끊기 콜백."""
import base64

from app.core import config
from app.core.db import SessionLocal
from app.models import Contract, User
from tests.conftest import complete_contract, create_text_contract


def test_withdraw_cancels_active_keeps_completed_and_kills_session(client_factory):
    a, b, done_cid = complete_contract(client_factory)
    draft_cid, _ = create_text_contract(a)
    old_id = a.get("/api/auth/me").json()["user"]["id"]
    r = a.c.delete("/api/auth/me", headers=a._h())
    assert r.status_code == 200 and r.json()["canceled_contracts"] == 1
    assert a.get("/api/auth/me").status_code == 401  # 남은 세션도 즉시 무효
    with SessionLocal() as db:
        assert db.get(Contract, draft_cid).status == "CANCELED"
        assert db.get(Contract, done_cid).status == "COMPLETED"  # 상대방 보호를 위해 유지
        u = db.get(User, old_id)
        assert u.deleted_at and u.display_name_masked == "탈퇴한 사용자" and u.provider_user_key.startswith("deleted:")
    # 상대방은 완료된 계약을 계속 볼 수 있다
    assert b.get(f"/api/contracts/{done_cid}").status_code == 200
    # 같은 계정으로 다시 로그인하면 새 회원이 된다
    a.login("hong")
    assert a.get("/api/auth/me").json()["user"]["id"] != old_id


def test_withdraw_requires_csrf(client_factory):
    a = client_factory()
    a.login("kim")
    assert a.c.delete("/api/auth/me").status_code == 403


def _toss_user(key: str) -> str:
    with SessionLocal() as db:
        u = User(provider="toss", provider_user_key=key, display_name_masked="홍*동")
        db.add(u)
        db.commit()
        return u.id


def test_toss_unlink_callback(client_factory, monkeypatch):
    monkeypatch.setenv("TOSS_UNLINK_BASIC_AUTH", "toss:s3cret-callback")
    config.get_settings.cache_clear()
    try:
        uid = _toss_user("443731104")
        c = client_factory().c
        assert c.post("/api/auth/toss/unlink", json={"userKey": 443731104, "referrer": "UNLINK"}).status_code == 401
        bad = "Basic " + base64.b64encode(b"toss:wrong").decode()
        assert c.post("/api/auth/toss/unlink", json={"userKey": 443731104}, headers={"Authorization": bad}).status_code == 401
        good = "Basic " + base64.b64encode(b"toss:s3cret-callback").decode()
        r = c.post("/api/auth/toss/unlink", json={"userKey": 443731104, "referrer": "WITHDRAWAL_TOSS"}, headers={"Authorization": good})
        assert r.status_code == 200 and r.json()["found"] is True
        with SessionLocal() as db:
            assert db.get(User, uid).deleted_at is not None
        # GET + 쿼리 형식도 받는다, 모르는 사용자도 200 (토스가 재시도하지 않도록)
        r = c.get("/api/auth/toss/unlink?userKey=999&referrer=UNLINK", headers={"Authorization": good})
        assert r.status_code == 200 and r.json()["found"] is False
    finally:
        config.get_settings.cache_clear()


def test_toss_unlink_disabled_without_secret(client_factory):
    good = "Basic " + base64.b64encode(b"a:b").decode()
    assert client_factory().c.post("/api/auth/toss/unlink", json={"userKey": 1}, headers={"Authorization": good}).status_code == 401
