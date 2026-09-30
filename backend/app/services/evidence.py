"""감사 로그(증거 기록).

각 이벤트는 직전 이벤트의 hash 를 포함해 해시체인을 이룬다. 중간 이벤트가 삭제·수정되면
verify_chain() 이 실패한다. metadata 에는 개인정보를 넣지 않는다 (키 화이트리스트 검사).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent
from app.services.hashing import sha256_json

EVENT_TYPES = {
    "CONTRACT_CREATED", "CONTRACT_VIEWED", "CONTRACT_UPDATED", "VERSION_CREATED", "INVITED", "INVITE_ACCEPTED",
    "IDENTITY_VERIFIED", "CONTRACT_REVIEWED", "SIGNATURE_STARTED", "SIGNATURE_COMPLETED", "SIGNATURE_INVALIDATED",
    "CONTRACT_COMPLETED", "CONTRACT_CANCELED", "PDF_GENERATED", "HASH_CREATED", "CERTIFICATE_GENERATED",
    "PAYMENT_REQUESTED", "PAYMENT_SUCCEEDED", "PAYMENT_FAILED",
    "BLOCKCHAIN_SUBMITTED", "BLOCKCHAIN_RETRY", "BLOCKCHAIN_CONFIRMED", "BLOCKCHAIN_FAILED",
    "DOCUMENT_PURGED",
}

EVENT_LABELS = {
    "CONTRACT_CREATED": "계약서 작성", "CONTRACT_VIEWED": "계약서 열람", "CONTRACT_UPDATED": "내용 수정", "VERSION_CREATED": "새 버전 생성",
    "INVITED": "상대방 초대", "INVITE_ACCEPTED": "상대방 참여", "IDENTITY_VERIFIED": "본인확인 완료", "CONTRACT_REVIEWED": "최종 확인·동의",
    "SIGNATURE_STARTED": "서명 시작", "SIGNATURE_COMPLETED": "서명 완료", "SIGNATURE_INVALIDATED": "서명 무효화(내용 변경)",
    "CONTRACT_COMPLETED": "계약 완료", "CONTRACT_CANCELED": "계약 취소", "PDF_GENERATED": "계약서 PDF 생성", "HASH_CREATED": "디지털 지문 생성",
    "CERTIFICATE_GENERATED": "확인서 발급", "PAYMENT_REQUESTED": "결제 요청", "PAYMENT_SUCCEEDED": "결제 완료", "PAYMENT_FAILED": "결제 실패",
    "BLOCKCHAIN_SUBMITTED": "블록체인 전송", "BLOCKCHAIN_RETRY": "블록체인 재시도", "BLOCKCHAIN_CONFIRMED": "블록체인 기록 확인",
    "BLOCKCHAIN_FAILED": "블록체인 기록 실패", "DOCUMENT_PURGED": "원문 삭제(보존기간 만료)",
}

ALLOWED_META_KEYS = {
    "role", "provider", "reason", "version_from", "version_to", "changed_fields", "kind", "sha256", "size",
    "payment_id", "amount", "status", "tx_id", "network", "block_number", "attempt", "error", "mode",
    "invalidated_parties", "field_count", "source", "confirmations", "verification_id", "idempotency_key",
    "anchored_value", "purged_items", "policy", "consent_version", "issue_no",
}


def _clean_meta(meta: dict | None) -> dict:
    meta = meta or {}
    bad = set(meta) - ALLOWED_META_KEYS
    if bad:
        raise ValueError(f"감사 로그 metadata 에 허용되지 않은 키: {sorted(bad)}")
    return meta


def record(
    db: Session,
    contract_id: str,
    event_type: str,
    actor_id: str | None = None,
    document_version: int | None = None,
    document_hash: str | None = None,
    metadata: dict | None = None,
) -> AuditEvent:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"알 수 없는 이벤트: {event_type}")
    meta = _clean_meta(metadata)
    last = db.scalar(
        select(AuditEvent).where(AuditEvent.contract_id == contract_id).order_by(AuditEvent.seq.desc()).limit(1).with_for_update()
    )
    seq = (last.seq + 1) if last else 1
    prev = last.event_hash if last else None
    now = datetime.now(timezone.utc)
    ts = now.replace(microsecond=(now.microsecond // 1000) * 1000)
    ev = AuditEvent(
        seq=seq, contract_id=contract_id, actor_id=actor_id, event_type=event_type, timestamp=ts,
        document_version=document_version, document_hash=document_hash, event_metadata=meta, prev_event_hash=prev,
    )
    ev.event_hash = _hash_event(ev)
    db.add(ev)
    db.flush()
    return ev


def _hash_event(ev: AuditEvent) -> str:
    return sha256_json(
        {
            "seq": ev.seq, "contract_id": ev.contract_id, "actor_id": ev.actor_id, "event_type": ev.event_type,
            "timestamp": ev.timestamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "document_version": ev.document_version, "document_hash": ev.document_hash,
            "metadata": ev.event_metadata, "prev": ev.prev_event_hash,
        }
    )


def list_events(db: Session, contract_id: str) -> list[AuditEvent]:
    return list(db.scalars(select(AuditEvent).where(AuditEvent.contract_id == contract_id).order_by(AuditEvent.seq)))


def verify_chain(db: Session, contract_id: str) -> bool:
    prev = None
    for i, ev in enumerate(list_events(db, contract_id), start=1):
        if ev.seq != i or ev.prev_event_hash != prev or _hash_event(ev) != ev.event_hash:
            return False
        prev = ev.event_hash
    return True


def to_dict(ev: AuditEvent) -> dict:
    return {
        "event_id": ev.event_id, "seq": ev.seq, "contract_id": ev.contract_id, "actor_id": ev.actor_id,
        "event_type": ev.event_type, "timestamp": ev.timestamp.isoformat(), "document_version": ev.document_version,
        "document_hash": ev.document_hash, "metadata": ev.event_metadata, "prev_event_hash": ev.prev_event_hash,
        "event_hash": ev.event_hash,
    }
