"""Provider 선택기. 운영 provider 설정이 불완전하면 (production 환경 제외) mock 으로 대체하고 기록한다."""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.providers.base import ProviderNotConfigured, note

log = logging.getLogger(__name__)


def _fallback(kind: str, requested: str, err: Exception):
    if get_settings().is_production:
        raise err
    log.warning("%s provider '%s' 사용 불가 → mock 으로 대체: %s", kind, requested, err)
    note(kind, requested, "mock", str(err))


def get_toss_login():
    from app.providers.toss import AppsInTossLoginProvider, MockTossLoginProvider

    req = get_settings().TOSS_PROVIDER
    if req == "production":
        try:
            p = AppsInTossLoginProvider()
            note("toss", req, req)
            return p
        except ProviderNotConfigured as e:
            _fallback("toss", req, e)
            return MockTossLoginProvider()
    note("toss", req, "mock")
    return MockTossLoginProvider()


def get_identity():
    from app.providers.identity_signature import MockIdentityProvider, TossCertIdentityProvider

    req = get_settings().IDENTITY_PROVIDER
    if req == "production":
        try:
            p = TossCertIdentityProvider()
            note("identity", req, req)
            return p
        except ProviderNotConfigured as e:
            _fallback("identity", req, e)
    else:
        note("identity", req, "mock")
    return MockIdentityProvider()


def get_signature():
    from app.providers.identity_signature import (
        DevelopmentSignatureProvider,
        MockSignatureProvider,
        TossCertSignatureProvider,
    )

    req = get_settings().SIGNATURE_PROVIDER
    if req == "production":
        try:
            p = TossCertSignatureProvider()
            note("signature", req, req)
            return p
        except ProviderNotConfigured as e:
            _fallback("signature", req, e)
            return MockSignatureProvider()
    if req == "development":
        note("signature", req, req)
        return DevelopmentSignatureProvider()
    note("signature", req, "mock")
    return MockSignatureProvider()


def signature_by_name(name: str):
    from app.providers.identity_signature import DevelopmentSignatureProvider, MockSignatureProvider

    return {"development": DevelopmentSignatureProvider, "mock": MockSignatureProvider}.get(name, MockSignatureProvider)()


def get_payment():
    from app.providers.payment import MockPaymentProvider, TossIapPaymentProvider

    req = get_settings().PAYMENT_PROVIDER
    if req == "production":
        try:
            p = TossIapPaymentProvider()
            note("payment", req, req)
            return p
        except ProviderNotConfigured as e:
            _fallback("payment", req, e)
    else:
        note("payment", req, "mock")
    return MockPaymentProvider()


def get_ocr():
    from app.providers.ocr import LocalTesseractOCR, ProviderAOCR, ProviderBOCR

    req = get_settings().OCR_PROVIDER
    cls = {"provider_a": ProviderAOCR, "provider_b": ProviderBOCR}.get(req)
    if cls:
        try:
            p = cls()
            note("ocr", req, req)
            return p
        except ProviderNotConfigured as e:
            _fallback("ocr", req, e)
    note("ocr", req, "local")
    return LocalTesseractOCR()


_evm_cache: dict = {}


def get_blockchain(db: Session):
    from app.providers.blockchain import EvmBlockchainProvider, MockBlockchainProvider, OpenTimestampsProvider

    s = get_settings()
    req = s.BLOCKCHAIN_PROVIDER
    if req == "evm":
        try:
            p = EvmBlockchainProvider(db)
            note("blockchain", req, req)
            return p
        except Exception as e:  # noqa: BLE001 - 연결 실패 포함
            _fallback("blockchain", req, e if isinstance(e, ProviderNotConfigured) else ProviderNotConfigured(str(e)))
    elif req == "opentimestamps":
        try:
            return OpenTimestampsProvider(db)
        except ProviderNotConfigured as e:
            _fallback("blockchain", req, e)
    else:
        note("blockchain", req, "mock")
    return MockBlockchainProvider(db)
