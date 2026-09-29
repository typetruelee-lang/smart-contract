"""애플리케이션 설정.

모든 비밀값은 환경변수(.env / .env.local / Secret Manager)로만 주입한다.
실제 키가 없으면 각 provider 는 mock 으로 동작하고, 그 사실은 /api/admin/status 에 표시된다.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(ROOT_DIR / ".env"), str(ROOT_DIR / ".env.local")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_ENV: Literal["development", "test", "production"] = "development"
    APP_NAME: str = "계약하자"
    PUBLIC_BASE_URL: str = "http://localhost:5173"
    CORS_ORIGINS: str = "http://localhost:5173"

    DATABASE_URL: str = "postgresql+psycopg://contract:contract@localhost:5432/contract"
    REDIS_URL: str = "redis://localhost:6379/0"

    # 인증 / 세션
    JWT_SECRET: str = ""
    SESSION_TTL_MINUTES: int = 60
    COOKIE_SECURE: bool = False

    # 암호화 키 관리
    KEY_PROVIDER: Literal["env", "secret_manager"] = "env"
    DATA_ENCRYPTION_KEY: str = ""  # base64 32 bytes (개발용)
    DATA_ENCRYPTION_KEY_VERSION: str = "v1"
    SECRET_MANAGER_BACKEND: str = ""  # aws | gcp
    SECRET_MANAGER_KEY_ID: str = ""

    # Provider 선택 (mock | development | production)
    TOSS_PROVIDER: str = "mock"
    TOSS_API_BASE_URL: str = "https://apps-in-toss-api.toss.im"
    TOSS_MTLS_CERT_PATH: str = ""
    TOSS_MTLS_KEY_PATH: str = ""
    TOSS_DECRYPTION_KEY: str = ""
    TOSS_AAD: str = ""

    PAYMENT_PROVIDER: str = "mock"
    TOSS_IAP_SKU_BLOCKCHAIN: str = ""

    SIGNATURE_PROVIDER: str = "mock"
    IDENTITY_PROVIDER: str = "mock"
    TOSS_CERT_CLIENT_ID: str = ""
    TOSS_CERT_CLIENT_SECRET: str = ""

    OCR_PROVIDER: str = "local"
    OCR_PROVIDER_A_URL: str = ""
    OCR_PROVIDER_A_SECRET: str = ""
    OCR_PROVIDER_B_API_KEY: str = ""

    BLOCKCHAIN_ENABLED: bool = True
    BLOCKCHAIN_PROVIDER: str = "mock"  # mock | evm | opentimestamps
    BLOCKCHAIN_NETWORK: str = "mock"
    BLOCKCHAIN_RPC_URL: str = ""
    BLOCKCHAIN_PRIVATE_KEY: str = ""
    BLOCKCHAIN_CONTRACT_ADDRESS: str = ""
    BLOCKCHAIN_EXPLORER_TX_URL: str = ""
    BLOCKCHAIN_CONFIRMATIONS: int = 1
    ANCHOR_MODE: Literal["single", "merkle"] = "single"
    ANCHOR_MAX_ATTEMPTS: int = 5
    ANCHOR_RETRY_BASE_SECONDS: int = 5

    BLOCKCHAIN_PRICE: int = Field(default=990, ge=0)

    # 업로드
    MAX_UPLOAD_MB: int = 10
    MAX_PDF_PAGES: int = 30

    # 보존 정책
    RETENTION_POLICY_FILE: str = str(BACKEND_DIR / "retention_policies.yaml")

    # Rate limit (요청/분)
    RATE_LIMIT_PER_MINUTE: int = 120
    RATE_LIMIT_AUTH_PER_MINUTE: int = 20
    RATE_LIMIT_UPLOAD_PER_MINUTE: int = 10
    RATE_LIMIT_VERIFY_PER_MINUTE: int = 30

    ADMIN_TOKEN: str = ""  # production 에서 /api/admin 접근용
    PDF_BROWSER_EXECUTABLE: str = ""
    TEST_RESULTS_PATH: str = str(ROOT_DIR / "test-results" / "summary.json")

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
