"""본인확인(Identity) / 전자서명(Signature) provider.

mock        : 외부 사업자 없이 전체 흐름 테스트 (서명패드 이미지 + 모의 본인확인)
development : mock 과 동일한 UX 이나 서버 키로 HMAC 서명값을 만들어 서명 무결성까지 검증
production  : 토스인증(원터치 본인확인 / 전자서명) 연동 골격 — 가맹 계약 후 키 입력 필요
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core.config import get_settings
from app.providers.base import ProviderNotConfigured


@dataclass
class IdentitySession:
    session_id: str
    provider: str
    redirect_url: str | None = None


@dataclass
class IdentityResult:
    verified: bool
    provider: str


class IdentityProvider(ABC):
    name = "base"

    @abstractmethod
    def start(self, user_id: str) -> IdentitySession: ...

    @abstractmethod
    def complete(self, session_id: str, user_id: str, payload: dict) -> IdentityResult: ...


class MockIdentityProvider(IdentityProvider):
    name = "mock"

    def start(self, user_id: str) -> IdentitySession:
        return IdentitySession(session_id="idv_" + secrets.token_hex(8), provider=self.name)

    def complete(self, session_id: str, user_id: str, payload: dict) -> IdentityResult:
        # 모의: 사용자가 '인증 완료' 를 누르면 성공, payload.fail=True 면 실패
        return IdentityResult(verified=not bool(payload.get("fail")), provider=self.name)


class TossCertIdentityProvider(IdentityProvider):
    name = "production"

    def __init__(self) -> None:
        s = get_settings()
        if not (s.TOSS_CERT_CLIENT_ID and s.TOSS_CERT_CLIENT_SECRET):
            raise ProviderNotConfigured("토스인증 본인확인 가맹 후 TOSS_CERT_CLIENT_ID/SECRET 를 입력하세요.")

    def start(self, user_id: str) -> IdentitySession:  # pragma: no cover
        raise ProviderNotConfigured("토스인증 본인확인 API 연동은 가맹 계약 후 활성화됩니다.")

    def complete(self, session_id: str, user_id: str, payload: dict) -> IdentityResult:  # pragma: no cover
        raise ProviderNotConfigured("토스인증 본인확인 API 연동은 가맹 계약 후 활성화됩니다.")


@dataclass
class SignatureRequest:
    request_id: str
    provider: str


@dataclass
class SignatureResult:
    signature_ref: str
    provider: str


class SignatureProvider(ABC):
    name = "base"

    @abstractmethod
    def start(self, user_id: str, content_hash: str) -> SignatureRequest: ...

    @abstractmethod
    def complete(self, request_id: str, user_id: str, content_hash: str, payload: dict) -> SignatureResult: ...

    def verify(self, signature_ref: str, request_id: str, user_id: str, content_hash: str) -> bool:
        return True


class MockSignatureProvider(SignatureProvider):
    name = "mock"

    def start(self, user_id: str, content_hash: str) -> SignatureRequest:
        return SignatureRequest(request_id="sgr_" + secrets.token_hex(8), provider=self.name)

    def complete(self, request_id: str, user_id: str, content_hash: str, payload: dict) -> SignatureResult:
        ref = "mock:" + hashlib.sha256(f"{request_id}|{user_id}|{content_hash}".encode()).hexdigest()[:40]
        return SignatureResult(signature_ref=ref, provider=self.name)

    def verify(self, signature_ref: str, request_id: str, user_id: str, content_hash: str) -> bool:
        return signature_ref == "mock:" + hashlib.sha256(f"{request_id}|{user_id}|{content_hash}".encode()).hexdigest()[:40]


class DevelopmentSignatureProvider(SignatureProvider):
    """서버 비밀키 HMAC-SHA256 으로 (요청ID, 사용자, 문서 content_hash) 에 서명."""

    name = "development"

    def _key(self) -> bytes:
        return hashlib.sha256(("sig|" + get_settings().JWT_SECRET).encode()).digest()

    def start(self, user_id: str, content_hash: str) -> SignatureRequest:
        return SignatureRequest(request_id="sgr_" + secrets.token_hex(8), provider=self.name)

    def _mac(self, request_id: str, user_id: str, content_hash: str) -> str:
        return hmac.new(self._key(), f"{request_id}|{user_id}|{content_hash}".encode(), hashlib.sha256).hexdigest()

    def complete(self, request_id: str, user_id: str, content_hash: str, payload: dict) -> SignatureResult:
        return SignatureResult(signature_ref="hmac:" + self._mac(request_id, user_id, content_hash), provider=self.name)

    def verify(self, signature_ref: str, request_id: str, user_id: str, content_hash: str) -> bool:
        return hmac.compare_digest(signature_ref, "hmac:" + self._mac(request_id, user_id, content_hash))


class TossCertSignatureProvider(SignatureProvider):
    name = "production"

    def __init__(self) -> None:
        s = get_settings()
        if not (s.TOSS_CERT_CLIENT_ID and s.TOSS_CERT_CLIENT_SECRET):
            raise ProviderNotConfigured("토스인증 전자서명 가맹 후 TOSS_CERT_CLIENT_ID/SECRET 를 입력하세요.")

    def start(self, user_id: str, content_hash: str) -> SignatureRequest:  # pragma: no cover
        raise ProviderNotConfigured("토스인증 전자서명 API 연동은 가맹 계약 후 활성화됩니다.")

    def complete(self, request_id: str, user_id: str, content_hash: str, payload: dict) -> SignatureResult:  # pragma: no cover
        raise ProviderNotConfigured("토스인증 전자서명 API 연동은 가맹 계약 후 활성화됩니다.")
