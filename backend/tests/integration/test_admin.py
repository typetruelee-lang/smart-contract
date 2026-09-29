"""관리자 대시보드 — 개발용 provider 는 운영 준비(PRODUCTION READY)를 막아야 한다."""
from __future__ import annotations


def test_admin_status_components_and_readiness(client_factory, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "SIGNATURE_PROVIDER", "development")
    c = client_factory()
    d = c.get("/api/admin/status").json()
    for name in ("Database", "PDF Engine", "Hash Engine", "Encryption Keys", "Blockchain", "Payment", "Toss Adapter"):
        assert d["components"][name]["ok"], (name, d["components"][name])
    assert d["readiness"]["production_ready"] is False
    blockers = " ".join(d["readiness"]["production_blockers"])
    assert "signature: 개발용(development)" in blockers and "payment: 개발용(mock)" in blockers
    assert d["providers"]["signature"]["dev_only"] is True


def test_admin_requires_token_in_production(client_factory, monkeypatch):
    from app.core.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "APP_ENV", "production")
    monkeypatch.setattr(s, "ADMIN_TOKEN", "t" * 40)
    c = client_factory()
    assert c.c.get("/api/admin/status").status_code == 404
    assert c.c.get("/api/admin/status", headers={"X-Admin-Token": "wrong"}).status_code == 404
