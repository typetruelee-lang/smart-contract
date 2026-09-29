"""계약 종류별 보존 정책 + 원문 삭제(purge) 작업."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Contract, DocumentBlob, DocumentVersion
from app.services import evidence


@lru_cache
def load_policies() -> dict:
    with open(get_settings().RETENTION_POLICY_FILE, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    default = raw["default"]
    out = {"default": default}
    for k, v in (raw.get("policies") or {}).items():
        out[k] = {**default, **(v or {})}
    return out


def policy_for(contract_type: str) -> dict:
    p = load_policies()
    return p.get(contract_type, p["default"])


def schedule_after_completion(c: Contract, extended: bool = False) -> None:
    pol = policy_for(c.contract_type)
    days = pol["post_completion_ttl_days"]
    if extended and pol.get("allow_extended_retention"):
        days = pol.get("extended_retention_days", days)
        c.keep_encrypted_original = True
    c.purge_at = (c.completed_at or datetime.now(timezone.utc)) + timedelta(days=days)


def schedule_draft(c: Contract) -> None:
    pol = policy_for(c.contract_type)
    c.purge_at = (c.created_at or datetime.now(timezone.utc)) + timedelta(days=pol["draft_ttl_days"])


def purge_contract(db: Session, c: Contract, reason: str) -> dict:
    now = datetime.now(timezone.utc)
    items = 0
    for v in db.scalars(select(DocumentVersion).where(DocumentVersion.contract_id == c.id, DocumentVersion.purged_at.is_(None))):
        v.payload_ciphertext = None
        v.payload_wrapped_dek = None
        v.purged_at = now
        items += 1
    for b in db.scalars(select(DocumentBlob).where(DocumentBlob.contract_id == c.id, DocumentBlob.purged_at.is_(None))):
        b.ciphertext = None
        b.wrapped_dek = None
        b.purged_at = now
        items += 1
    c.purged_at = now
    if c.status not in ("COMPLETED",):
        c.status = "EXPIRED" if reason == "policy" else c.status
    evidence.record(db, c.id, "DOCUMENT_PURGED", None, c.final_version_no or c.current_version_no, c.document_hash,
                    {"reason": reason, "purged_items": items, "policy": c.contract_type})
    return {"contract_id": c.id, "items": items}


def run_retention(db: Session, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    due = db.scalars(
        select(Contract).where(Contract.purged_at.is_(None), Contract.purge_at.is_not(None), Contract.purge_at <= now)
    ).all()
    out = [purge_contract(db, c, "policy") for c in due]
    db.commit()
    return out
