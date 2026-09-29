"""Provider adapter 전환 테스트 — 키가 없으면 개발환경에서는 mock 으로, 운영에서는 오류로."""
from __future__ import annotations

import pytest

import app.providers as providers
from app.core.config import get_settings
from app.providers.base import PROVIDER_STATUS, ProviderNotConfigured


@pytest.fixture
def settings(monkeypatch):
    s = get_settings()
    return lambda **kw: [monkeypatch.setattr(s, k, v) for k, v in kw.items()]


@pytest.mark.parametrize("kind,attr,getter,mock_name", [
    ("toss", "TOSS_PROVIDER", providers.get_toss_login, "mock"),
    ("payment", "PAYMENT_PROVIDER", providers.get_payment, "mock"),
    ("identity", "IDENTITY_PROVIDER", providers.get_identity, "mock"),
    ("signature", "SIGNATURE_PROVIDER", providers.get_signature, "mock"),
])
def test_production_provider_without_keys_falls_back_in_dev(settings, kind, attr, getter, mock_name):
    settings(**{attr: "production"})
    p = getter()
    assert p.name == mock_name
    assert PROVIDER_STATUS[kind]["fallback"] is True


@pytest.mark.parametrize("attr,getter", [
    ("TOSS_PROVIDER", providers.get_toss_login),
    ("PAYMENT_PROVIDER", providers.get_payment),
    ("IDENTITY_PROVIDER", providers.get_identity),
    ("SIGNATURE_PROVIDER", providers.get_signature),
])
def test_production_env_refuses_missing_keys(settings, attr, getter):
    settings(APP_ENV="production", **{attr: "production"})
    with pytest.raises(ProviderNotConfigured):
        getter()


def test_ocr_external_without_key_falls_back_to_local(settings):
    settings(OCR_PROVIDER="provider_b")
    assert providers.get_ocr().name == "local"


def test_blockchain_evm_unreachable_falls_back_to_mock(settings, db):
    settings(BLOCKCHAIN_PROVIDER="evm", BLOCKCHAIN_RPC_URL="http://127.0.0.1:1")
    p = providers.get_blockchain(db)
    assert p.name == "mock" and PROVIDER_STATUS["blockchain"]["fallback"]


def test_blockchain_evm_production_requires_private_key(settings, db):
    from web3 import Web3
    from web3.providers.eth_tester import EthereumTesterProvider

    from app.providers.blockchain import EvmBlockchainProvider

    settings(APP_ENV="production")
    with pytest.raises(ProviderNotConfigured):
        EvmBlockchainProvider(db, w3=Web3(EthereumTesterProvider()))


def test_signature_development_hmac_verifies(settings):
    from app.providers.identity_signature import DevelopmentSignatureProvider

    p = DevelopmentSignatureProvider()
    r = p.start("u1", "h" * 64)
    res = p.complete(r.request_id, "u1", "h" * 64, {})
    assert p.verify(res.signature_ref, r.request_id, "u1", "h" * 64)
    assert not p.verify(res.signature_ref, r.request_id, "u1", "x" * 64)


def test_mock_toss_login_exchange():
    from app.providers.toss import MockTossLoginProvider

    assert MockTossLoginProvider().exchange("mock-code-kim", "SANDBOX").name == "김철수"
    with pytest.raises(Exception):
        MockTossLoginProvider().exchange("real-code", "DEFAULT")


def test_toss_login_endpoint_mock(client_factory):
    c = client_factory()
    r = c.c.post("/api/auth/toss/login", json={"authorization_code": "mock-code-lee", "referrer": "SANDBOX"})
    assert r.status_code == 200 and r.json()["user"]["name"] == "이*희"
    r = c.c.post("/api/auth/toss/login", json={"authorization_code": "bogus", "referrer": "SANDBOX"})
    assert r.status_code == 401
