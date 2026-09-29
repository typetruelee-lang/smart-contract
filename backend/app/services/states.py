"""서로 독립적인 3개의 상태 머신.

계약 상태 · 결제 상태 · 블록체인 기록 상태는 서로의 값을 바꾸지 않는다.
- 계약 완료(COMPLETED)는 결제/블록체인과 무관하다.
- 결제 성공(PAID)은 블록체인 성공이 아니다. (PAID + anchor PENDING/RETRY/FAILED 가 가능)
"""
from __future__ import annotations

CONTRACT = {
    "DRAFT": {"READY", "INVITED", "CANCELED", "EXPIRED"},
    "READY": {"DRAFT", "INVITED", "CANCELED", "EXPIRED"},
    "INVITED": {"INVITED", "SIGNING", "CANCELED", "EXPIRED"},
    "SIGNING": {"INVITED", "SIGNING", "COMPLETED", "CANCELED", "EXPIRED"},
    "COMPLETED": set(),
    "CANCELED": set(),
    "EXPIRED": set(),
}

PAYMENT = {
    "NONE": {"PENDING"},
    "PENDING": {"PAID", "FAILED", "CANCELED"},
    "PAID": {"REFUNDED"},
    "FAILED": set(),
    "CANCELED": set(),
    "REFUNDED": set(),
}

ANCHOR = {
    "NOT_REQUESTED": {"PENDING"},
    "PENDING": {"SUBMITTED", "CONFIRMED", "RETRY", "FAILED"},
    "RETRY": {"SUBMITTED", "CONFIRMED", "RETRY", "FAILED"},
    "SUBMITTED": {"CONFIRMED", "RETRY", "FAILED"},
    "CONFIRMED": set(),
    "FAILED": {"PENDING"},  # 운영자 수동 재시도
}

MACHINES = {"contract": CONTRACT, "payment": PAYMENT, "anchor": ANCHOR}


class InvalidTransition(Exception):
    def __init__(self, machine: str, src: str, dst: str):
        super().__init__(f"{machine}: {src} → {dst} 전이는 허용되지 않아요.")
        self.machine, self.src, self.dst = machine, src, dst


def can(machine: str, src: str, dst: str) -> bool:
    return dst in MACHINES[machine].get(src, set())


def transition(machine: str, obj, dst: str, attr: str = "status") -> None:
    src = getattr(obj, attr)
    if not can(machine, src, dst):
        raise InvalidTransition(machine, src, dst)
    setattr(obj, attr, dst)
