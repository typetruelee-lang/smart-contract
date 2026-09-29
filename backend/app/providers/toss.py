"""Toss 로그인 provider.

흐름 (Apps in Toss 공식 문서 기준):
  미니앱에서 appLogin() → authorizationCode, referrer(DEFAULT|SANDBOX)
  → 백엔드가 mTLS 인증서로 POST /api-partner/v1/apps-in-toss/user/oauth2/generate-token
  → accessToken 으로 GET /api-partner/v1/apps-in-toss/user/oauth2/login-me → userKey 등
  (사용자 정보 일부는 암호화되어 오며 콘솔에서 받은 복호화 키로 풀어야 한다)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.providers.base import ProviderError, ProviderNotConfigured

MOCK_USERS = {
    "hong": ("mock-hong", "홍길동"),
    "kim": ("mock-kim", "김철수"),
    "lee": ("mock-lee", "이영희"),
    "park": ("mock-park", "박민수"),
}


@dataclass
class TossIdentity:
    user_key: str
    name: str


class TossLoginProvider(ABC):
    name = "base"

    @abstractmethod
    def exchange(self, authorization_code: str, referrer: str) -> TossIdentity: ...


class MockTossLoginProvider(TossLoginProvider):
    """개발용: authorization_code 로 테스트 계정 키(hong/kim/lee/park)를 받는다."""

    name = "mock"

    def exchange(self, authorization_code: str, referrer: str) -> TossIdentity:
        code = authorization_code.replace("mock-code-", "")
        if code not in MOCK_USERS:
            raise ProviderError("알 수 없는 테스트 계정이에요.")
        key, name = MOCK_USERS[code]
        return TossIdentity(user_key=key, name=name)


class AppsInTossLoginProvider(TossLoginProvider):
    name = "production"

    def __init__(self) -> None:
        s = get_settings()
        if not (s.TOSS_MTLS_CERT_PATH and s.TOSS_MTLS_KEY_PATH):
            raise ProviderNotConfigured("TOSS_MTLS_CERT_PATH / TOSS_MTLS_KEY_PATH 가 필요합니다 (앱인토스 콘솔에서 발급).")
        self.base = s.TOSS_API_BASE_URL.rstrip("/")
        self.cert = (s.TOSS_MTLS_CERT_PATH, s.TOSS_MTLS_KEY_PATH)

    def exchange(self, authorization_code: str, referrer: str) -> TossIdentity:  # pragma: no cover - 실계정 필요
        with httpx.Client(cert=self.cert, timeout=10) as c:
            r = c.post(
                f"{self.base}/api-partner/v1/apps-in-toss/user/oauth2/generate-token",
                json={"authorizationCode": authorization_code, "referrer": referrer},
            )
            if r.status_code != 200 or r.json().get("resultType") != "SUCCESS":
                raise ProviderError(f"토스 토큰 발급 실패: {r.status_code}")
            token = r.json()["success"]["accessToken"]
            me = c.get(f"{self.base}/api-partner/v1/apps-in-toss/user/oauth2/login-me", headers={"Authorization": f"Bearer {token}"})
            if me.status_code != 200:
                raise ProviderError("토스 사용자 조회 실패")
            data = me.json()["success"]
            # 이름 등 개인정보 필드는 암호화되어 전달됨 — 복호화 키(TOSS_DECRYPTION_KEY)로 복호화 필요.
            return TossIdentity(user_key=str(data["userKey"]), name=_decrypt_name(data.get("name")))


def _decrypt_name(enc: str | None) -> str:  # pragma: no cover - 실계정 필요
    s = get_settings()
    if not enc:
        return "토스 사용자"
    if not s.TOSS_DECRYPTION_KEY:
        return "토스 사용자"
    import base64

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    raw = base64.b64decode(enc)
    key = base64.b64decode(s.TOSS_DECRYPTION_KEY)
    iv, ct = raw[:12], raw[12:]
    return AESGCM(key).decrypt(iv, ct, s.TOSS_AAD.encode() or None).decode()
