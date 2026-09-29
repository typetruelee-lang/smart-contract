"""결제 → 블록체인 기록(anchor) 흐름.

규칙
1) 결제가 PAID 가 된 경우에만 AnchorJob 을 만든다. (결제 실패 → 블록체인 호출 없음)
2) 결제 성공 ≠ 블록체인 성공. AnchorJob 은 PENDING → (RETRY)* → CONFIRMED | FAILED 로 독립적으로 움직인다.
3) idempotency_key = sha256(contract_id + document_hash) — 결제·기록 모두 UNIQUE. 중복 결제/중복 기록 방지.
4) 실패 시 지수 백오프 재시도 (ANCHOR_RETRY_BASE_SECONDS * 2^n), ANCHOR_MAX_ATTEMPTS 초과 시 FAILED.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AnchorJob, Contract, DevFault, Payment, User
from app.providers import get_blockchain, get_payment
from app.providers.base import ProviderError
from app.services import evidence, states
from app.services.contracts import ContractError
from app.services.hashing import sha256_bytes
from app.services.merkle import MerkleService

log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def idempotency_key(contract: Contract) -> str:
    return sha256_bytes(f"anchor|{contract.id}|{contract.document_hash}".encode())


def checkout(db: Session, c: Contract, user: User) -> dict:
    s = get_settings()
    if not s.BLOCKCHAIN_ENABLED:
        raise ContractError(404, "FEATURE_DISABLED", "이 기능은 현재 제공되지 않아요.")
    if c.status != "COMPLETED" or not c.document_hash:
        raise ContractError(409, "NOT_COMPLETED", "계약이 완료된 뒤 기록할 수 있어요.")
    key = idempotency_key(c)
    existing = db.scalar(select(Payment).where(Payment.idempotency_key == key))
    if existing:
        if existing.status == "PAID":
            raise ContractError(409, "ALREADY_PAID", "이미 결제한 계약이에요.", {"payment_id": existing.id})
        if existing.status == "PENDING":
            prov = get_payment()
            return {"payment_id": existing.id, "order_id": existing.provider_order_id, "amount": existing.amount,
                    "provider": existing.provider, "client_params": prov.create_checkout(existing.id, existing.amount, existing.product).client_params}
        # FAILED/CANCELED → 새 시도: 이전 결제 기록은 보존하고 키를 회전
        existing.idempotency_key = f"{key}:{existing.id}"
        db.flush()
    prov = get_payment()
    p = Payment(contract_id=c.id, user_id=user.id, provider=prov.name, amount=s.BLOCKCHAIN_PRICE, idempotency_key=key)
    db.add(p)
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        raise ContractError(409, "DUPLICATE", "이미 결제가 진행 중이에요. 잠시 후 다시 확인해 주세요.") from e
    cs = prov.create_checkout(p.id, p.amount, p.product)
    p.provider_order_id = cs.order_id
    evidence.record(db, c.id, "PAYMENT_REQUESTED", user.id, c.final_version_no, c.document_hash,
                    {"payment_id": p.id, "amount": p.amount, "provider": prov.name})
    db.commit()
    return {"payment_id": p.id, "order_id": cs.order_id, "amount": p.amount, "provider": prov.name, "client_params": cs.client_params}


def _fault(db: Session, key: str) -> bool:
    f = db.get(DevFault, key, with_for_update=True)
    if f and f.value > 0:
        f.value -= 1
        return True
    return False


def confirm_payment(db: Session, c: Contract, user: User, payment_id: str, client_payload: dict) -> dict:
    p = db.get(Payment, payment_id, with_for_update=True)
    if p is None or p.contract_id != c.id or p.user_id != user.id:
        raise ContractError(404, "NOT_FOUND", "결제 정보를 찾을 수 없어요.")
    if p.status == "PAID":
        job = db.scalar(select(AnchorJob).where(AnchorJob.payment_id == p.id))
        return {"payment_status": p.status, "anchor_status": job.status if job else "NOT_REQUESTED"}
    if p.status != "PENDING":
        raise ContractError(409, "PAYMENT_CLOSED", "이미 끝난 결제예요. 다시 결제해 주세요.")
    prov = get_payment()
    outcome = prov.confirm(p.provider_order_id or "", p.amount, client_payload, force_fail=_fault(db, "payment_fail"))
    states.transition("payment", p, outcome.status)
    p.failure_reason = outcome.reason
    if outcome.status != "PAID":
        evidence.record(db, c.id, "PAYMENT_FAILED", user.id, c.final_version_no, c.document_hash,
                        {"payment_id": p.id, "status": outcome.status, "reason": (outcome.reason or "")[:100]})
        db.commit()
        # 결제 실패 → 블록체인 호출 없음
        return {"payment_status": p.status, "anchor_status": "NOT_REQUESTED", "reason": outcome.reason}
    evidence.record(db, c.id, "PAYMENT_SUCCEEDED", user.id, c.final_version_no, c.document_hash, {"payment_id": p.id, "amount": p.amount})
    job = _create_job(db, c, p)
    db.commit()
    # 결제 직후 1회 즉시 시도 (실패해도 결제는 PAID 로 유지되고 워커가 재시도)
    process_job(db, job.id)
    db.refresh(job)
    return {"payment_status": p.status, "anchor_status": job.status}


def _create_job(db: Session, c: Contract, p: Payment) -> AnchorJob:
    s = get_settings()
    key = idempotency_key(c)
    job = db.scalar(select(AnchorJob).where(AnchorJob.idempotency_key == key))
    if job:
        return job
    bc_name = s.BLOCKCHAIN_PROVIDER
    job = AnchorJob(contract_id=c.id, payment_id=p.id, document_hash=c.document_hash, idempotency_key=key, mode=s.ANCHOR_MODE,
                    status="PENDING", provider=bc_name, network=s.BLOCKCHAIN_NETWORK, next_attempt_at=_now())
    db.add(job)
    db.flush()
    return job


def process_job(db: Session, job_id: str) -> AnchorJob:
    s = get_settings()
    job = db.get(AnchorJob, job_id, with_for_update=True)
    assert job is not None
    if job.status in ("CONFIRMED", "FAILED"):
        return job
    if job.mode == "merkle":
        # 배치 대상은 run_merkle_batch 가 처리
        return job
    c = db.get(Contract, job.contract_id)
    assert c is not None
    job.attempts += 1
    try:
        bc = get_blockchain(db)
        job.provider, job.network = bc.name, bc.network
        if job.status == "SUBMITTED" and job.tx_id:
            receipt_tx = job.tx_id
        else:
            r = bc.register_document_hash(job.document_hash, c.final_version_no or 1)
            job.tx_id, job.block_number, job.anchored_value = r.tx_id, r.block_number, job.document_hash
            job.submitted_at = _now()
            if job.status != "SUBMITTED":
                states.transition("anchor", job, "SUBMITTED")
            evidence.record(db, c.id, "BLOCKCHAIN_SUBMITTED", None, c.final_version_no, c.document_hash,
                            {"tx_id": r.tx_id, "network": bc.network, "attempt": job.attempts})
            receipt_tx = r.tx_id
        info = bc.get_transaction(receipt_tx)
        onchain = bc.verify_document_hash(job.document_hash)
        if info and info.confirmed and onchain:
            states.transition("anchor", job, "CONFIRMED")
            job.confirmed_at = _now()
            job.block_number = info.block_number
            job.last_error = None
            evidence.record(db, c.id, "BLOCKCHAIN_CONFIRMED", None, c.final_version_no, c.document_hash,
                            {"tx_id": receipt_tx, "network": bc.network, "block_number": info.block_number, "confirmations": info.confirmations})
        else:
            job.next_attempt_at = _now() + timedelta(seconds=s.ANCHOR_RETRY_BASE_SECONDS)
    except ProviderError as e:
        job.last_error = str(e)[:300]
        if job.attempts >= s.ANCHOR_MAX_ATTEMPTS:
            states.transition("anchor", job, "FAILED")
            evidence.record(db, c.id, "BLOCKCHAIN_FAILED", None, c.final_version_no, c.document_hash,
                            {"attempt": job.attempts, "error": str(e)[:100]})
        else:
            if job.status != "RETRY":
                states.transition("anchor", job, "RETRY")
            job.next_attempt_at = _now() + timedelta(seconds=s.ANCHOR_RETRY_BASE_SECONDS * (2 ** (job.attempts - 1)))
            evidence.record(db, c.id, "BLOCKCHAIN_RETRY", None, c.final_version_no, c.document_hash,
                            {"attempt": job.attempts, "error": str(e)[:100]})
    db.commit()
    return job


def run_due_jobs(db: Session, now: datetime | None = None, force: bool = False) -> int:
    now = now or _now()
    q = select(AnchorJob.id).where(AnchorJob.status.in_(["PENDING", "RETRY", "SUBMITTED"]), AnchorJob.mode == "single")
    if not force:
        q = q.where(AnchorJob.next_attempt_at <= now)
    ids = list(db.scalars(q.limit(50)))
    for jid in ids:
        process_job(db, jid)
    return len(ids)


def manual_retry(db: Session, job: AnchorJob) -> AnchorJob:
    """운영자 수동 재시도: FAILED → PENDING (결제는 다시 받지 않음)."""
    if job.status == "FAILED":
        states.transition("anchor", job, "PENDING")
        job.attempts = 0
        job.next_attempt_at = _now()
        db.commit()
    return process_job(db, job.id)


def run_merkle_batch(db: Session) -> dict | None:
    """ANCHOR_MODE=merkle 확장 기능: 대기 중인 Hash 들을 Merkle Root 1건으로 기록."""
    jobs = list(db.scalars(select(AnchorJob).where(AnchorJob.mode == "merkle", AnchorJob.status.in_(["PENDING", "RETRY"])).limit(1000)))
    if not jobs:
        return None
    tree = MerkleService.create_tree([j.document_hash for j in jobs])
    root = tree.get_root()
    bc = get_blockchain(db)
    try:
        r = bc.register_root(root)
    except ProviderError as e:
        for j in jobs:
            j.attempts += 1
            j.last_error = str(e)[:300]
            if j.status != "RETRY":
                states.transition("anchor", j, "RETRY")
        db.commit()
        return {"root": root, "error": str(e)}
    for j in jobs:
        j.attempts += 1
        j.tx_id, j.anchored_value, j.merkle_proof = r.tx_id, root, tree.get_proof(j.document_hash)
        j.provider, j.network = bc.name, bc.network
        states.transition("anchor", j, "CONFIRMED")
        j.confirmed_at = _now()
        evidence.record(db, j.contract_id, "BLOCKCHAIN_CONFIRMED", None, None, j.document_hash,
                        {"tx_id": r.tx_id, "network": bc.network, "mode": "merkle", "anchored_value": root})
    db.commit()
    return {"root": root, "tx_id": r.tx_id, "count": len(jobs)}
