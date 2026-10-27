"""운영 설정 가드 · 무료 기록 모드."""
import pytest

from app.core.config import Settings

SAFE = dict(APP_ENV="production", JWT_SECRET="x" * 40, TOSS_PROVIDER="production", IDENTITY_PROVIDER="production",
            SIGNATURE_PROVIDER="production", BLOCKCHAIN_PROVIDER="opentimestamps", BLOCKCHAIN_PRICE=0, PAYMENT_PROVIDER="mock",
            COOKIE_SECURE=True)


def test_safe_production_config_has_no_violations():
    assert Settings(**SAFE).production_violations() == []


@pytest.mark.parametrize("override,needle", [
    ({"TOSS_PROVIDER": "mock"}, "TOSS_PROVIDER"),
    ({"SIGNATURE_PROVIDER": "mock"}, "SIGNATURE_PROVIDER"),
    ({"BLOCKCHAIN_PROVIDER": "mock"}, "BLOCKCHAIN_PROVIDER"),
    ({"BLOCKCHAIN_PRICE": 990}, "PAYMENT_PROVIDER"),
    ({"COOKIE_SECURE": False}, "COOKIE_SECURE"),
])
def test_unsafe_production_config_is_refused(override, needle):
    assert any(needle in v for v in Settings(**{**SAFE, **override}).production_violations())


def test_blockchain_off_needs_no_chain_or_payment():
    assert Settings(**{**SAFE, "BLOCKCHAIN_ENABLED": False, "BLOCKCHAIN_PROVIDER": "mock", "BLOCKCHAIN_PRICE": 990}).production_violations() == []


def test_app_refuses_to_start_with_unsafe_production_config(monkeypatch):
    from app.core import config
    from app.main import create_app
    for k, v in {**SAFE, "TOSS_PROVIDER": "mock"}.items():
        monkeypatch.setenv(k, str(v))
    config.get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="운영 설정 오류"):
            create_app()
    finally:
        config.get_settings.cache_clear()
