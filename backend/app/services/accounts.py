"""회원 탈퇴 · 토스 로그인 연결 끊기.

- 탈퇴하면 로그인 식별자(토스 userKey)를 지우고 이름을 '탈퇴한 사용자'로 바꾼다. 같은 토스 계정으로 다시 오면 새 계정이 된다.
- 진행 중인 계약(작성·초대·서명 중)은 취소하고 원문을 즉시 삭제한다 (상대방에게는 '계약 취소'로 보인다).
- 완료된 계약은 상대방의 권리(보관·검증)를 위해 지우지 않는다. 원문은 보존 정책대로 삭제되고,
  디지털 지문·진행 기록(가명 처리된 당사자 이름)만 남는다 → 개인정보처리방침에 명시.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Contract, ContractParty, User
from app.services import evidence, retention, states

ACTIVE = ("DRAFT", "READY", "INVITED", "SIGNING")


def withdraw(db: Session, user: User, trigger: str = "user") -> dict:
    if user.deleted_at is not None:
        return {"canceled_contracts": 0}
    canceled = 0
    cids = db.scalars(select(ContractParty.contract_id).where(ContractParty.user_id == user.id)).all()
    for c in db.scalars(select(Contract).where(Contract.id.in_(cids), Contract.status.in_(ACTIVE))).all():
        states.transition("contract", c, "CANCELED")
        evidence.record(db, c.id, "CONTRACT_CANCELED", user.id, c.current_version_no, None, {"reason": "withdrawal", "trigger": trigger})
        retention.purge_contract(db, c, "canceled")
        canceled += 1
    user.provider_user_key = "deleted:" + secrets.token_hex(16)
    user.display_name_masked = "탈퇴한 사용자"
    user.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return {"canceled_contracts": canceled}


def withdraw_by_toss_key(db: Session, user_key: str, trigger: str) -> bool:
    u = db.scalar(select(User).where(User.provider == "toss", User.provider_user_key == user_key))
    if u is None:
        return False
    withdraw(db, u, trigger)
    return True
