"""결제 provider.

- MockPaymentProvider: 성공/실패/취소를 선택해 테스트. (dev_faults.payment_fail 로 강제 실패 가능)
- TossIapPaymentProvider: 앱인토스 인앱결제(IAP). 블록체인 기록은 '비실물 디지털 서비스'이므로
  앱인토스 정책상 IAP 대상일 가능성이 높다 (TOSS_POLICY_NOTES.md 참조, 담당자 확인 필요).
  IAP 는 클라이언트 SDK 가 결제를 진행하고, 서버는 주문 상태를 검증한다.
"""
from __future__ import annotations

import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core.config import get_settings
from app.providers.base import ProviderNotConfigured


@dataclass
class CheckoutSession:
    order_id: str
    provider: str
    client_params: dict


@dataclass
class PaymentOutcome:
    status: str  # PAID | FAILED | CANCELED
    reason: str | None = None


class PaymentProvider(ABC):
    name = "base"

    @abstractmethod
    def create_checkout(self, payment_id: str, amount: int, product: str) -> CheckoutSession: ...

    @abstractmethod
    def confirm(self, order_id: str, amount: int, client_payload: dict, force_fail: bool = False) -> PaymentOutcome: ...


class MockPaymentProvider(PaymentProvider):
    name = "mock"

    def create_checkout(self, payment_id: str, amount: int, product: str) -> CheckoutSession:
        order_id = "mock_order_" + secrets.token_hex(8)
        return CheckoutSession(order_id=order_id, provider=self.name, client_params={"mock": True, "amount": amount})

    def confirm(self, order_id: str, amount: int, client_payload: dict, force_fail: bool = False) -> PaymentOutcome:
        if force_fail:
            return PaymentOutcome("FAILED", "테스트용 결제 실패")
        result = client_payload.get("result", "success")
        if result == "cancel":
            return PaymentOutcome("CANCELED", "사용자가 결제를 취소했어요.")
        if result != "success":
            return PaymentOutcome("FAILED", "결제가 승인되지 않았어요.")
        return PaymentOutcome("PAID")


class TossIapPaymentProvider(PaymentProvider):
    name = "production"

    def __init__(self) -> None:
        s = get_settings()
        if not (s.TOSS_MTLS_CERT_PATH and s.TOSS_IAP_SKU_BLOCKCHAIN):
            raise ProviderNotConfigured("앱인토스 콘솔에서 인앱결제 상품(SKU) 등록 후 TOSS_IAP_SKU_BLOCKCHAIN 과 mTLS 인증서를 입력하세요.")
        self.sku = s.TOSS_IAP_SKU_BLOCKCHAIN

    def create_checkout(self, payment_id: str, amount: int, product: str) -> CheckoutSession:  # pragma: no cover
        # 클라이언트는 이 sku 로 SDK 의 인앱결제 주문을 생성한다.
        return CheckoutSession(order_id=payment_id, provider=self.name, client_params={"sku": self.sku})

    def confirm(self, order_id: str, amount: int, client_payload: dict, force_fail: bool = False) -> PaymentOutcome:  # pragma: no cover
        raise ProviderNotConfigured("인앱결제 주문 검증 API 는 앱인토스 계정 연결 후 활성화됩니다.")
