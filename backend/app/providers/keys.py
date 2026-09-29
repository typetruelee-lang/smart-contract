"""KeyProvider — 문서 암호화용 KEK 공급자.

- EnvKeyProvider: 개발/테스트. DATA_ENCRYPTION_KEY(base64 32바이트)를 사용.
- SecretManagerKeyProvider: 운영. AWS Secrets Manager / GCP Secret Manager 에서 KEK 를 가져온다.
  (운영 계정이 필요하므로 골격만 제공. 설정 누락 시 명확한 오류)
"""
from __future__ import annotations

import base64
import os
from abc import ABC, abstractmethod

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings


class KeyProviderError(RuntimeError):
    pass


class KeyProvider(ABC):
    name = "base"

    @abstractmethod
    def current_version(self) -> str: ...

    @abstractmethod
    def get_kek(self, version: str) -> bytes: ...


class EnvKeyProvider(KeyProvider):
    name = "env"

    def __init__(self, key_b64: str, version: str):
        if not key_b64:
            raise KeyProviderError("DATA_ENCRYPTION_KEY 가 설정되지 않았습니다. ./start.sh 가 .env.local 에 자동 생성합니다.")
        key = base64.b64decode(key_b64)
        if len(key) != 32:
            raise KeyProviderError("DATA_ENCRYPTION_KEY 는 base64 인코딩된 32바이트여야 합니다.")
        self._keys = {version: key}
        self._version = version

    def current_version(self) -> str:
        return self._version

    def get_kek(self, version: str) -> bytes:
        try:
            return self._keys[version]
        except KeyError as e:
            raise KeyProviderError(f"알 수 없는 키 버전: {version}") from e


class SecretManagerKeyProvider(KeyProvider):
    name = "secret_manager"

    def __init__(self, backend: str, key_id: str, version: str):
        if not backend or not key_id:
            raise KeyProviderError("SECRET_MANAGER_BACKEND / SECRET_MANAGER_KEY_ID 설정이 필요합니다.")
        self.backend = backend
        self.key_id = key_id
        self._version = version
        self._cache: dict[str, bytes] = {}

    def current_version(self) -> str:
        return self._version

    def get_kek(self, version: str) -> bytes:
        if version in self._cache:
            return self._cache[version]
        if self.backend == "aws":
            try:
                import boto3  # type: ignore
            except ImportError as e:  # pragma: no cover - 운영 전용
                raise KeyProviderError("boto3 설치 필요: pip install boto3") from e
            client = boto3.client("secretsmanager")  # pragma: no cover
            secret = client.get_secret_value(SecretId=self.key_id, VersionStage=version)  # pragma: no cover
            key = base64.b64decode(secret["SecretString"])  # pragma: no cover
        elif self.backend == "gcp":
            try:
                from google.cloud import secretmanager  # type: ignore
            except ImportError as e:  # pragma: no cover
                raise KeyProviderError("google-cloud-secret-manager 설치 필요") from e
            client = secretmanager.SecretManagerServiceClient()  # pragma: no cover
            name = f"{self.key_id}/versions/{version}"  # pragma: no cover
            key = base64.b64decode(client.access_secret_version(name=name).payload.data)  # pragma: no cover
        else:
            raise KeyProviderError(f"지원하지 않는 Secret Manager: {self.backend}")
        self._cache[version] = key  # pragma: no cover
        return key  # pragma: no cover


_provider: KeyProvider | None = None


def get_key_provider() -> KeyProvider:
    global _provider
    if _provider is None:
        s = get_settings()
        if s.KEY_PROVIDER == "secret_manager":
            _provider = SecretManagerKeyProvider(s.SECRET_MANAGER_BACKEND, s.SECRET_MANAGER_KEY_ID, s.DATA_ENCRYPTION_KEY_VERSION)
        else:
            if s.is_production:
                raise KeyProviderError("운영 환경에서는 KEY_PROVIDER=secret_manager 를 사용해야 합니다.")
            _provider = EnvKeyProvider(s.DATA_ENCRYPTION_KEY, s.DATA_ENCRYPTION_KEY_VERSION)
    return _provider


def reset_key_provider() -> None:
    global _provider
    _provider = None


# ---- Envelope encryption (AES-256-GCM) ----

def encrypt(plaintext: bytes, aad: bytes = b"") -> tuple[bytes, bytes, str]:
    """문서마다 새 DEK 로 암호화하고 DEK 는 KEK 로 감싼다."""
    kp = get_key_provider()
    version = kp.current_version()
    kek = kp.get_kek(version)
    dek = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    ciphertext = nonce + AESGCM(dek).encrypt(nonce, plaintext, aad)
    wnonce = os.urandom(12)
    wrapped = wnonce + AESGCM(kek).encrypt(wnonce, dek, version.encode())
    return ciphertext, wrapped, version


def decrypt(ciphertext: bytes, wrapped_dek: bytes, version: str, aad: bytes = b"") -> bytes:
    kek = get_key_provider().get_kek(version)
    dek = AESGCM(kek).decrypt(wrapped_dek[:12], wrapped_dek[12:], version.encode())
    return AESGCM(dek).decrypt(ciphertext[:12], ciphertext[12:], aad)
