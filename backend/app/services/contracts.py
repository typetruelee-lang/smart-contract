"""계약 엔진 — 생성, 편집, 문서 버전 관리, 초대, 본인확인, 검토, 서명, 완료.

문서 버전 규칙
- 버전은 '봉인(sealed)' 되기 전까지는 제자리에서 수정된다.
- 초대(INVITE) 또는 서명 시점에 현재 버전이 봉인된다.
- 봉인된 버전의 내용이 바뀌면 새 버전(v+1)이 생기고(VERSION_CREATED),
  바뀐 내용에 서명한 적 없는 서명은 모두 무효화된다(SIGNATURE_INVALIDATED).
- 서명은 (version_no, content_hash) 에 묶인다. content_hash 는 서명 이미지 값을 제외한 계약 내용의 SHA-256.
- 모든 당사자가 같은 버전·같은 content_hash 에 서명하면 그 버전이 FINAL 이 되고 계약서 PDF 가 1회 생성된다.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import io
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Any

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    AnchorJob,
    AuditEvent,
    CertificateIssuance,
    Contract,
    ContractParty,
    DocumentBlob,
    DocumentVersion,
    Payment,
    User,
)
from app.providers import get_identity, get_signature, keys, signature_by_name
from app.services import evidence, pdf_engine, retention, states
from app.services.fields import (
    FieldSpec,
    FieldValueError,
    missing_required,
    normalize_value,
    placeholders_in,
    validate_field_set,
)
from app.services.hashing import sha256_bytes, sha256_json, short_hash

ROLE_LABEL = {"A": "당사자 A (작성자)", "B": "당사자 B (상대방)"}
MAX_BODY = 50_000
INVITE_TTL_HOURS = 72


class ContractError(Exception):
    def __init__(self, status: int, code: str, message: str, extra: dict | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra or {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _rand(n: int, alphabet: str = string.ascii_uppercase + string.digits) -> str:
    return "".join(secrets.choice(alphabet) for _ in range(n))


def new_contract_no() -> str:
    return f"KZ-{_now():%Y%m%d}-{_rand(6)}"


def new_verification_id() -> str:
    # 추측 불가능한 난수 (Crockford base32 계열, 혼동 문자 제외) — 약 60bit
    alpha = "23456789ABCDEFGHJKMNPQRSTVWXYZ"
    return f"V-{_rand(4, alpha)}-{_rand(4, alpha)}-{_rand(4, alpha)}"


def issuer_info() -> dict:
    s = get_settings()
    return {"service": s.APP_NAME, "company": s.COMPANY_NAME, "biz_no": s.COMPANY_BIZ_NO,
            "representative": s.COMPANY_REPRESENTATIVE, "address": s.COMPANY_ADDRESS, "contact": s.COMPANY_CONTACT}


def is_test_mode(c: Contract) -> bool:
    """운영 본인확인·전자서명(토스인증)을 거치지 않은 계약은 '시험용 · 법적 효력 없음' 으로 표시한다."""
    return not all(p.signature_provider == "production" and p.identity_provider == "production" for p in c.parties)


# ---------------- 페이로드(암호화 원문) ----------------

def content_hash_of(payload: dict) -> str:
    p = copy.deepcopy(payload)
    for f in p.get("fields", []):
        if f.get("type") == "SIGNATURE":
            f["value"] = None
    p.pop("sig_meta", None)
    return sha256_json(p)


def _aad(contract_id: str, version_no: int) -> bytes:
    return f"{contract_id}:v{version_no}".encode()


def load_payload(v: DocumentVersion) -> dict:
    if v.payload_ciphertext is None:
        raise ContractError(410, "PURGED", "보존 기간이 지나 계약서 원문이 삭제되었어요. 내려받은 PDF 로 확인해 주세요.")
    import json

    raw = keys.decrypt(v.payload_ciphertext, v.payload_wrapped_dek, v.key_version, _aad(v.contract_id, v.version_no))
    return json.loads(raw)


def _store_payload(v: DocumentVersion, payload: dict) -> None:
    import json

    ct, wrapped, kv = keys.encrypt(json.dumps(payload, ensure_ascii=False).encode(), _aad(v.contract_id, v.version_no))
    v.payload_ciphertext, v.payload_wrapped_dek, v.key_version = ct, wrapped, kv
    v.content_hash = content_hash_of(payload)


def _store_blob(db: Session, contract_id: str, kind: str, data: bytes, ref: str | None = None) -> DocumentBlob:
    b = DocumentBlob(contract_id=contract_id, kind=kind, ref=ref, sha256=sha256_bytes(data), size=len(data))
    ct, wrapped, kv = keys.encrypt(data, f"{contract_id}:{kind}:{b.sha256}".encode())
    b.ciphertext, b.wrapped_dek, b.key_version = ct, wrapped, kv
    db.add(b)
    db.flush()
    return b


def read_blob(b: DocumentBlob) -> bytes:
    if b.ciphertext is None:
        raise ContractError(410, "PURGED", "보존 기간이 지나 파일이 삭제되었어요. 내려받아 둔 파일을 사용해 주세요.")
    return keys.decrypt(b.ciphertext, b.wrapped_dek, b.key_version, f"{b.contract_id}:{b.kind}:{b.sha256}".encode())


def current_version(db: Session, c: Contract) -> DocumentVersion:
    v = db.scalar(select(DocumentVersion).where(DocumentVersion.contract_id == c.id, DocumentVersion.version_no == c.current_version_no))
    if v is None:
        raise RuntimeError("내부 상태 오류: v 없음")
    return v


def fields_of(payload: dict) -> list[FieldSpec]:
    return [FieldSpec(**f) for f in payload.get("fields", [])]


# ---------------- 접근 제어 ----------------

def get_contract_for(db: Session, contract_id: str, user: User) -> tuple[Contract, ContractParty]:
    c = db.get(Contract, contract_id)
    if c is None:
        raise ContractError(404, "NOT_FOUND", "계약을 찾을 수 없어요.")
    for p in c.parties:
        if p.user_id == user.id:
            return c, p
    raise ContractError(404, "NOT_FOUND", "계약을 찾을 수 없어요.")  # 존재 여부를 노출하지 않음


def _require_owner(c: Contract, party: ContractParty) -> None:
    if party.role != "A":
        raise ContractError(403, "FORBIDDEN", "계약서를 만든 사람만 할 수 있어요.")


def _require_editable(c: Contract) -> None:
    if c.status in ("COMPLETED", "CANCELED", "EXPIRED"):
        raise ContractError(409, "NOT_EDITABLE", "완료되었거나 취소된 계약은 수정할 수 없어요.")


# ---------------- 생성 / 편집 ----------------

def _clean_payload(title: str, body_text: str | None, fields: list[FieldSpec], source: str, extra: dict | None = None) -> dict:
    title = (title or "").strip()
    if not 1 <= len(title) <= 100:
        raise ContractError(422, "INVALID_TITLE", "계약서 제목을 1~100자로 입력해 주세요.")
    body_text = (body_text or "").replace("\r\n", "\n")
    if len(body_text) > MAX_BODY:
        raise ContractError(422, "BODY_TOO_LONG", f"계약서 내용은 {MAX_BODY:,}자 이하로 작성해 주세요.")
    if source != "PDF" and not body_text.strip():
        raise ContractError(422, "EMPTY_BODY", "계약서 내용을 입력해 주세요.")
    try:
        validate_field_set(fields, source)
    except ValueError as e:
        raise ContractError(422, "INVALID_FIELDS", str(e)) from e
    if source != "PDF":
        labels = {f.label for f in fields}
        unknown = [p for p in placeholders_in(body_text) if p not in labels]
        if unknown:
            raise ContractError(422, "UNKNOWN_PLACEHOLDER", f"본문의 {{{unknown[0]}}} 빈칸 설정이 없어요. 빈칸을 추가하거나 괄호를 지워 주세요.")
    # 값 검증
    normalized = []
    for f in fields:
        try:
            f.value = normalize_value(f, f.value) if f.type != "SIGNATURE" else None
        except FieldValueError as e:
            raise ContractError(422, "INVALID_VALUE", e.message, {"field_id": e.field_id}) from e
        normalized.append(f.model_dump())
    payload = {"title": title, "body_text": body_text if source != "PDF" else "", "fields": normalized, "source": source}
    if extra:
        payload.update(extra)
    return payload


def create_contract(db: Session, user: User, *, title: str, contract_type: str, source: str, body_text: str | None,
                    fields: list[FieldSpec], source_pdf: bytes | None = None) -> Contract:
    if contract_type not in retention.load_policies() and contract_type != "general":
        contract_type = "general"
    if source not in ("TEXT", "PDF", "TEMPLATE"):
        raise ContractError(422, "INVALID_SOURCE", "알 수 없는 작성 방식이에요.")
    if source == "PDF" and not source_pdf:
        raise ContractError(422, "PDF_REQUIRED", "PDF 파일을 먼저 올려 주세요.")
    c = Contract(contract_no=new_contract_no(), title=title.strip()[:100], contract_type=contract_type, source=source, owner_id=user.id)
    db.add(c)
    db.flush()
    extra: dict = {}
    if source_pdf:
        blob = _store_blob(db, c.id, "SOURCE_PDF", source_pdf)
        extra = {"source_pdf_sha256": blob.sha256, "source_blob_id": blob.id, "pages": pdf_engine.page_sizes(source_pdf)}
    payload = _clean_payload(title, body_text, fields, source, extra)
    v = DocumentVersion(contract_id=c.id, version_no=1, status="DRAFT", created_by=user.id, reason="최초 작성", content_hash="")
    _store_payload(v, payload)
    db.add(v)
    db.add(ContractParty(contract_id=c.id, role="A", user_id=user.id, display_name_masked=user.display_name_masked))
    db.flush()
    retention.schedule_draft(c)
    evidence.record(db, c.id, "CONTRACT_CREATED", user.id, 1, v.content_hash, {"source": source, "field_count": len(fields)})
    db.commit()
    db.refresh(c)
    return c


def _diff(old: dict, new: dict) -> list[str]:
    changed = []
    if old.get("title") != new.get("title"):
        changed.append("title")
    if old.get("body_text") != new.get("body_text"):
        changed.append("body")
    of = {f["field_id"]: f for f in old.get("fields", [])}
    nf = {f["field_id"]: f for f in new.get("fields", [])}
    for fid in sorted(set(of) | set(nf)):
        a, b = of.get(fid), nf.get(fid)
        if a is None or b is None:
            changed.append(fid)
            continue
        if a.get("type") == "SIGNATURE" and b.get("type") == "SIGNATURE":
            a, b = {**a, "value": None}, {**b, "value": None}
        if a != b:
            changed.append(fid)
    return changed


def _modify(db: Session, c: Contract, actor: ContractParty, new_payload: dict, reason: str) -> DocumentVersion:
    cur = current_version(db, c)
    old = load_payload(cur)
    new_hash = content_hash_of(new_payload)
    if new_hash == cur.content_hash:
        return cur
    changed = _diff(old, new_payload)
    if cur.sealed:
        nv = DocumentVersion(
            contract_id=c.id, version_no=cur.version_no + 1, created_by=actor.user_id, reason=reason[:200],
            status="PROPOSED" if c.status in ("INVITED", "SIGNING") else "DRAFT", changed_fields=changed, content_hash="",
        )
        _store_payload(nv, new_payload)
        db.add(nv)
        c.current_version_no = nv.version_no
        db.flush()
        evidence.record(db, c.id, "VERSION_CREATED", actor.user_id, nv.version_no, nv.content_hash,
                        {"version_from": cur.version_no, "version_to": nv.version_no, "changed_fields": changed, "reason": reason[:100]})
        target = nv
    else:
        cur.changed_fields = sorted(set(cur.changed_fields or []) | set(changed))
        _store_payload(cur, new_payload)
        evidence.record(db, c.id, "CONTRACT_UPDATED", actor.user_id, cur.version_no, cur.content_hash, {"changed_fields": changed})
        target = cur
    # 내용이 바뀌면 이전 내용에 대한 검토/서명은 무효
    invalidated = []
    for p in c.parties:
        p.reviewed_version_no = None
        if p.signature_status == "SIGNED" and p.signed_content_hash != target.content_hash:
            p.signature_status = "INVALIDATED"
            invalidated.append(p.role)
        elif p.signature_status == "STARTED":
            p.signature_status = "PENDING"
    if invalidated:
        evidence.record(db, c.id, "SIGNATURE_INVALIDATED", actor.user_id, target.version_no, target.content_hash,
                        {"invalidated_parties": invalidated, "reason": "내용 변경"})
    if c.status == "SIGNING" and not any(p.signature_status == "SIGNED" for p in c.parties):
        states.transition("contract", c, "INVITED")
    if c.status == "READY":
        states.transition("contract", c, "DRAFT")
    return target


def update_content(db: Session, c: Contract, party: ContractParty, *, title: str | None, body_text: str | None,
                   fields: list[FieldSpec], reason: str = "내용 수정") -> DocumentVersion:
    _require_owner(c, party)
    _require_editable(c)
    cur = current_version(db, c)
    old = load_payload(cur)
    # 기존 값 유지: 필드 정의만 바뀌고 값이 None 으로 오면 이전 값을 유지하지 않음 (클라이언트가 전체 상태를 보냄)
    extra = {k: old[k] for k in ("source_pdf_sha256", "source_blob_id", "pages") if k in old}
    # 서명 값은 서명 단계에서만 바뀐다
    old_sig = {f["field_id"]: f.get("value") for f in old.get("fields", []) if f.get("type") == "SIGNATURE"}
    new_payload = _clean_payload(title if title is not None else old["title"], body_text if body_text is not None else old.get("body_text"),
                                 fields, old.get("source", c.source), extra)
    for f in new_payload["fields"]:
        if f["type"] == "SIGNATURE":
            f["value"] = old_sig.get(f["field_id"])
    v = _modify(db, c, party, new_payload, reason)
    c.title = new_payload["title"][:100]
    db.commit()
    return v


def fill_values(db: Session, c: Contract, party: ContractParty, values: dict[str, Any]) -> DocumentVersion:
    _require_editable(c)
    cur = current_version(db, c)
    payload = load_payload(cur)
    fields = fields_of(payload)
    by_id = {f.field_id: f for f in fields}
    for fid, val in values.items():
        f = by_id.get(fid)
        if f is None:
            raise ContractError(422, "UNKNOWN_FIELD", "없는 빈칸이에요. 화면을 새로고침해 주세요.")
        if f.type == "SIGNATURE":
            raise ContractError(422, "SIGNATURE_FIELD", "서명 칸은 서명 단계에서 채워져요.")
        if f.assignee not in (party.role, "ANY"):
            raise ContractError(403, "NOT_ASSIGNEE", f"'{f.label}' 칸은 상대방이 입력하는 칸이에요.")
        try:
            f.value = normalize_value(f, val)
        except FieldValueError as e:
            raise ContractError(422, "INVALID_VALUE", e.message, {"field_id": e.field_id}) from e
    new_payload = {**payload, "fields": [f.model_dump() for f in fields]}
    v = _modify(db, c, party, new_payload, f"{ROLE_LABEL[party.role]} 입력")
    db.commit()
    return v


def mark_ready(db: Session, c: Contract, party: ContractParty) -> None:
    _require_owner(c, party)
    if c.status != "DRAFT":
        return
    payload = load_payload(current_version(db, c))
    if not payload.get("fields") and c.source == "PDF":
        raise ContractError(422, "NO_FIELDS", "PDF 에 빈칸을 한 개 이상 추가해 주세요.")
    states.transition("contract", c, "READY")
    db.commit()


def cancel(db: Session, c: Contract, party: ContractParty) -> None:
    _require_owner(c, party)
    states.transition("contract", c, "CANCELED")
    evidence.record(db, c.id, "CONTRACT_CANCELED", party.user_id, c.current_version_no, None, {})
    retention.purge_contract(db, c, "canceled")
    db.commit()


# ---------------- 초대 ----------------

def invite(db: Session, c: Contract, party: ContractParty) -> dict:
    _require_owner(c, party)
    _require_editable(c)
    cur = current_version(db, c)
    payload = load_payload(cur)
    miss = missing_required(fields_of(payload), assignee="A")
    if miss:
        raise ContractError(422, "MISSING_FIELDS", f"내가 입력할 칸을 먼저 채워 주세요: {', '.join(f.label for f in miss[:3])}",
                            {"field_ids": [f.field_id for f in miss]})
    token = secrets.token_urlsafe(24)
    b = next((p for p in c.parties if p.role == "B"), None)
    if b is None:
        b = ContractParty(contract_id=c.id, role="B")
        db.add(b)
        c.parties.append(b)
    elif b.user_id is not None:
        raise ContractError(409, "ALREADY_JOINED", "상대방이 이미 참여했어요.")
    b.invite_token_hash = hashlib.sha256(token.encode()).hexdigest()
    b.invite_expires_at = _now() + timedelta(hours=INVITE_TTL_HOURS)
    if not cur.sealed:
        cur.sealed = True
        cur.status = "PROPOSED"
    if c.status in ("DRAFT", "READY"):
        states.transition("contract", c, "INVITED")
    db.flush()
    evidence.record(db, c.id, "INVITED", party.user_id, cur.version_no, cur.content_hash, {"role": "B"})
    db.commit()
    return {"invite_token": token, "invite_url": f"{get_settings().PUBLIC_BASE_URL}/invite/{token}", "expires_at": b.invite_expires_at.isoformat()}


def _party_by_token(db: Session, token: str) -> ContractParty:
    h = hashlib.sha256(token.encode()).hexdigest()
    p = db.scalar(select(ContractParty).where(ContractParty.invite_token_hash == h))
    if p is None:
        raise ContractError(404, "INVITE_NOT_FOUND", "초대 링크가 올바르지 않아요.")
    if p.invite_expires_at and p.invite_expires_at < _now():
        raise ContractError(410, "INVITE_EXPIRED", "초대 링크가 만료되었어요. 상대방에게 다시 요청해 주세요.")
    return p


def invite_preview(db: Session, token: str) -> dict:
    p = _party_by_token(db, token)
    c = db.get(Contract, p.contract_id)
    if c is None:
        raise RuntimeError("내부 상태 오류: c 없음")
    owner = next(x for x in c.parties if x.role == "A")
    return {"contract_id": c.id, "title": c.title, "from": owner.display_name_masked, "status": c.status, "joined": p.user_id is not None}


def accept_invite(db: Session, token: str, user: User) -> Contract:
    p = _party_by_token(db, token)
    c = db.get(Contract, p.contract_id)
    if c is None:
        raise RuntimeError("내부 상태 오류: c 없음")
    _require_editable(c)
    if any(x.user_id == user.id and x.role == "A" for x in c.parties):
        raise ContractError(409, "SELF_INVITE", "내가 만든 계약에는 상대방으로 참여할 수 없어요. 상대방에게 링크를 보내 주세요.")
    if p.user_id and p.user_id != user.id:
        raise ContractError(409, "ALREADY_JOINED", "이미 다른 사람이 참여한 초대예요.")
    if p.user_id is None:
        p.user_id = user.id
        p.display_name_masked = user.display_name_masked
        p.invite_token_hash = None  # 1회용
        evidence.record(db, c.id, "INVITE_ACCEPTED", user.id, c.current_version_no, None, {"role": "B"})
    db.commit()
    return c


# ---------------- 조회 ----------------

def record_view(db: Session, c: Contract, party: ContractParty) -> None:
    exists = db.scalar(
        select(AuditEvent.event_id).where(AuditEvent.contract_id == c.id, AuditEvent.event_type == "CONTRACT_VIEWED",
                                          AuditEvent.actor_id == party.user_id, AuditEvent.document_version == c.current_version_no).limit(1)
    )
    if not exists:
        v = current_version(db, c)
        evidence.record(db, c.id, "CONTRACT_VIEWED", party.user_id, v.version_no, v.content_hash, {"role": party.role})
        db.commit()


def latest_payment(db: Session, c: Contract) -> Payment | None:
    return db.scalar(select(Payment).where(Payment.contract_id == c.id).order_by(Payment.created_at.desc()).limit(1))


def latest_anchor(db: Session, c: Contract) -> AnchorJob | None:
    return db.scalar(select(AnchorJob).where(AnchorJob.contract_id == c.id).order_by(AnchorJob.created_at.desc()).limit(1))


def anchor_view(job: AnchorJob | None) -> dict:
    if job is None:
        return {"status": "NOT_REQUESTED"}
    from app.providers.blockchain import BlockchainProvider

    return {
        "status": job.status, "tx_id": job.tx_id, "network": job.network, "provider": job.provider, "attempts": job.attempts,
        "confirmed_at": job.confirmed_at.isoformat() if job.confirmed_at else None, "block_number": job.block_number,
        "mode": job.mode, "merkle_root": job.anchored_value if job.mode == "merkle" else None, "merkle_proof": job.merkle_proof,
        "last_error": job.last_error, "explorer_url": BlockchainProvider.explorer_url(BlockchainProvider, job.tx_id) if job.tx_id else None,  # type: ignore[arg-type]
    }


def contract_view(db: Session, c: Contract, party: ContractParty) -> dict:
    v = current_version(db, c)
    payload = None
    if c.purged_at is None:
        payload = load_payload(v)
        # 서명 이미지 값은 내부 참조만 노출 (이미지는 별도 API)
    pay = latest_payment(db, c)
    anchor = latest_anchor(db, c)
    pol = retention.policy_for(c.contract_type)
    versions = db.scalars(select(DocumentVersion).where(DocumentVersion.contract_id == c.id).order_by(DocumentVersion.version_no)).all()
    return {
        "id": c.id, "contract_no": c.contract_no, "title": c.title, "contract_type": c.contract_type, "source": c.source,
        "status": c.status, "my_role": party.role, "current_version_no": c.current_version_no, "final_version_no": c.final_version_no,
        "content_hash": v.content_hash, "document_hash": c.document_hash, "verification_id": c.verification_id,
        "completed_at": c.completed_at.isoformat() if c.completed_at else None,
        "created_at": c.created_at.isoformat(), "purge_at": c.purge_at.isoformat() if c.purge_at else None,
        "purged": c.purged_at is not None, "retention_note": pol.get("legal_basis_note"),
        "allow_extended_retention": bool(pol.get("allow_extended_retention")), "keep_encrypted_original": c.keep_encrypted_original,
        "payload": payload,
        "parties": [
            {"role": p.role, "role_label": ROLE_LABEL[p.role], "name": p.display_name_masked, "joined": p.user_id is not None,
             "is_me": p.user_id == party.user_id, "identity_status": p.identity_status,
             "reviewed": p.reviewed_version_no == c.current_version_no, "signature_status": p.signature_status,
             "signed_version_no": p.signed_version_no, "signed_at": p.signed_at.isoformat() if p.signed_at else None,
             "invite_pending": p.user_id is None and p.invite_token_hash is not None}
            for p in c.parties
        ],
        "versions": [{"version_no": x.version_no, "status": x.status, "sealed": x.sealed, "reason": x.reason,
                      "changed_fields": x.changed_fields, "content_hash": x.content_hash, "created_at": x.created_at.isoformat()} for x in versions],
        "payment": {"status": pay.status if pay else "NONE", "id": pay.id if pay else None, "amount": pay.amount if pay else None,
                    "failure_reason": pay.failure_reason if pay else None},
        "anchor": anchor_view(anchor),
        "blockchain_enabled": get_settings().BLOCKCHAIN_ENABLED, "blockchain_price": get_settings().BLOCKCHAIN_PRICE,
    }


def version_diff(db: Session, c: Contract, a: int, b: int) -> dict:
    va = db.scalar(select(DocumentVersion).where(DocumentVersion.contract_id == c.id, DocumentVersion.version_no == a))
    vb = db.scalar(select(DocumentVersion).where(DocumentVersion.contract_id == c.id, DocumentVersion.version_no == b))
    if va is None or vb is None:
        raise ContractError(404, "VERSION_NOT_FOUND", "버전을 찾을 수 없어요.")
    pa, pb = load_payload(va), load_payload(vb)
    fa = {f["field_id"]: f for f in pa["fields"]}
    fb = {f["field_id"]: f for f in pb["fields"]}
    changes = []
    for fid in _diff(pa, pb):
        if fid in ("title", "body"):
            changes.append({"key": fid, "label": "제목" if fid == "title" else "본문", "before": pa.get("title" if fid == "title" else "body_text"),
                            "after": pb.get("title" if fid == "title" else "body_text")})
        else:
            x, y = fa.get(fid), fb.get(fid)
            changes.append({"key": fid, "label": (y or x)["label"], "before": x.get("value") if x else None, "after": y.get("value") if y else None,
                            "kind": "added" if x is None else "removed" if y is None else "changed"})
    return {"from": a, "to": b, "changes": changes}


# ---------------- 본인확인 / 검토 / 서명 ----------------

def _require_signable(c: Contract) -> None:
    if c.status not in ("INVITED", "SIGNING"):
        if c.status in ("DRAFT", "READY"):
            raise ContractError(409, "NOT_INVITED", "상대방을 먼저 초대해 주세요.")
        raise ContractError(409, "NOT_SIGNABLE", "서명할 수 없는 상태의 계약이에요.")
    if not all(p.user_id for p in c.parties) or len(c.parties) < 2:
        raise ContractError(409, "WAITING_PARTY", "상대방이 아직 참여하지 않았어요.")


def identity_start(db: Session, c: Contract, party: ContractParty) -> dict:
    _require_editable(c)
    s = get_identity().start(party.user_id or "")
    return {"session_id": s.session_id, "provider": s.provider, "redirect_url": s.redirect_url}


def identity_complete(db: Session, c: Contract, party: ContractParty, session_id: str, payload: dict) -> None:
    _require_editable(c)
    prov = get_identity()
    r = prov.complete(session_id, party.user_id or "", payload)
    if not r.verified:
        raise ContractError(422, "IDENTITY_FAILED", "본인확인에 실패했어요. 다시 시도해 주세요.")
    party.identity_status = "VERIFIED"
    party.identity_provider = r.provider
    party.identity_verified_at = _now()
    evidence.record(db, c.id, "IDENTITY_VERIFIED", party.user_id, c.current_version_no, None, {"provider": r.provider, "role": party.role})
    db.commit()


def review(db: Session, c: Contract, party: ContractParty, version_no: int, confirmations: dict) -> None:
    _require_signable(c)
    need = ("content_checked", "own_will", "e_signature_consent", "retention_acknowledged")
    if not all(confirmations.get(k) is True for k in need):
        raise ContractError(422, "CONFIRM_REQUIRED", "확인 항목에 모두 체크해 주세요.")
    if version_no != c.current_version_no:
        raise ContractError(409, "VERSION_CHANGED", "그 사이 계약 내용이 바뀌었어요. 바뀐 내용을 다시 확인해 주세요.", {"current_version_no": c.current_version_no})
    v = current_version(db, c)
    miss = missing_required(fields_of(load_payload(v)))
    if miss:
        raise ContractError(422, "MISSING_FIELDS", f"아직 비어 있는 필수 칸이 있어요: {', '.join(f.label for f in miss[:3])}",
                            {"field_ids": [f.field_id for f in miss]})
    party.reviewed_version_no = v.version_no
    evidence.record(db, c.id, "CONTRACT_REVIEWED", party.user_id, v.version_no, v.content_hash,
                    {"role": party.role, "confirmations": list(need), "consent_version": get_settings().CONSENT_VERSION})
    db.commit()


def sign_start(db: Session, c: Contract, party: ContractParty) -> dict:
    _require_signable(c)
    if party.identity_status != "VERIFIED":
        raise ContractError(409, "IDENTITY_REQUIRED", "본인확인을 먼저 해 주세요.")
    if party.reviewed_version_no != c.current_version_no:
        raise ContractError(409, "REVIEW_REQUIRED", "계약 내용을 먼저 확인해 주세요.")
    if party.signature_status == "SIGNED" and party.signed_version_no == c.current_version_no:
        raise ContractError(409, "ALREADY_SIGNED", "이미 서명했어요.")
    v = current_version(db, c)
    prov = get_signature()
    req = prov.start(party.user_id or "", v.content_hash)
    party.signature_status = "STARTED"
    party.signature_request_id = req.request_id
    party.signature_provider = req.provider
    evidence.record(db, c.id, "SIGNATURE_STARTED", party.user_id, v.version_no, v.content_hash, {"provider": req.provider, "role": party.role})
    db.commit()
    return {"request_id": req.request_id, "provider": req.provider, "version_no": v.version_no, "content_hash": v.content_hash}


def _decode_signature_image(data_url: str) -> bytes:
    if not isinstance(data_url, str) or not data_url.startswith("data:image/png;base64,"):
        raise ContractError(422, "INVALID_SIGNATURE_IMAGE", "서명 이미지 형식이 올바르지 않아요.")
    try:
        raw = base64.b64decode(data_url.split(",", 1)[1], validate=True)
    except Exception as e:  # noqa: BLE001
        raise ContractError(422, "INVALID_SIGNATURE_IMAGE", "서명 이미지 형식이 올바르지 않아요.") from e
    if len(raw) > 300_000 or not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ContractError(422, "INVALID_SIGNATURE_IMAGE", "서명 이미지가 너무 크거나 PNG 가 아니에요.")
    try:
        img = Image.open(io.BytesIO(raw))
        img.verify()
        if img.width > 2000 or img.height > 1000:
            raise ValueError
    except Exception as e:  # noqa: BLE001
        raise ContractError(422, "INVALID_SIGNATURE_IMAGE", "서명 이미지를 읽을 수 없어요.") from e
    return raw


def sign_complete(db: Session, c: Contract, party: ContractParty, request_id: str, version_no: int, signature_image: str) -> dict:
    _require_signable(c)
    if party.signature_status != "STARTED" or party.signature_request_id != request_id:
        raise ContractError(409, "SIGNATURE_NOT_STARTED", "서명 요청이 만료되었어요. 다시 시도해 주세요.")
    if version_no != c.current_version_no or party.reviewed_version_no != c.current_version_no:
        raise ContractError(409, "VERSION_CHANGED", "그 사이 계약 내용이 바뀌었어요. 바뀐 내용을 다시 확인해 주세요.")
    raw = _decode_signature_image(signature_image)
    v = current_version(db, c)
    payload = load_payload(v)
    if content_hash_of(payload) != v.content_hash:
        raise ContractError(500, "INTEGRITY", "문서 무결성 확인에 실패했어요.")
    prov = get_signature()
    res = prov.complete(request_id, party.user_id or "", v.content_hash, {})
    blob = _store_blob(db, c.id, "SIGNATURE_IMAGE", raw, ref=party.role)
    sig_value = f"sig:{blob.id}"
    for f in payload["fields"]:
        if f["type"] == "SIGNATURE" and f["assignee"] in (party.role,) and not f.get("value"):
            f["value"] = sig_value
    payload.setdefault("sig_meta", {})[party.role] = sig_value
    _store_payload(v, payload)  # content_hash 는 변하지 않는다 (서명 값 제외)
    v.sealed = True
    party.signature_status = "SIGNED"
    party.signature_ref = res.signature_ref
    party.signed_version_no = v.version_no
    party.signed_content_hash = v.content_hash
    party.signed_at = _now()
    if c.status == "INVITED":
        states.transition("contract", c, "SIGNING")
    evidence.record(db, c.id, "SIGNATURE_COMPLETED", party.user_id, v.version_no, v.content_hash,
                    {"provider": res.provider, "role": party.role})
    db.flush()
    done = all(p.signature_status == "SIGNED" and p.signed_version_no == v.version_no and p.signed_content_hash == v.content_hash
               for p in c.parties) and len(c.parties) >= 2
    if done:
        _finalize(db, c, v, payload)
    else:
        v.status = "PROPOSED"
    db.commit()
    return {"completed": done, "status": c.status}


def _sig_images(db: Session, c: Contract) -> dict[str, str]:
    out = {}
    for b in db.scalars(select(DocumentBlob).where(DocumentBlob.contract_id == c.id, DocumentBlob.kind == "SIGNATURE_IMAGE")):
        out[f"sig:{b.id}"] = "data:image/png;base64," + base64.b64encode(read_blob(b)).decode()
    return out


def _party_signs(c: Contract, payload: dict, images: dict[str, str]) -> list[pdf_engine.PartySign]:
    out = []
    for p in c.parties:
        sig_val = (payload.get("sig_meta") or {}).get(p.role)
        out.append(pdf_engine.PartySign(
            role=p.role, role_label=ROLE_LABEL[p.role], name_masked=p.display_name_masked or "-", identity_status=p.identity_status,
            identity_verified_at=p.identity_verified_at, signed_at=p.signed_at, signature_ref=p.signature_ref,
            signature_image=images.get(sig_val) if sig_val else None, provider=p.signature_provider,
        ))
    return out


def _finalize(db: Session, c: Contract, v: DocumentVersion, payload: dict) -> None:
    # 서명 무결성 재확인
    for p in c.parties:
        prov = signature_by_name(p.signature_provider or "mock")
        if not prov.verify(p.signature_ref or "", p.signature_request_id or "", p.user_id or "", v.content_hash):
            raise ContractError(500, "SIGNATURE_VERIFY_FAILED", "전자서명 검증에 실패했어요.")
    v.status = "FINAL"
    v.sealed = True
    c.final_version_no = v.version_no
    c.completed_at = _now()
    states.transition("contract", c, "COMPLETED")
    evidence.record(db, c.id, "CONTRACT_COMPLETED", None, v.version_no, v.content_hash, {})
    images = _sig_images(db, c)
    source_pdf = None
    if c.source == "PDF" and payload.get("source_blob_id"):
        source_pdf = read_blob(db.get(DocumentBlob, payload["source_blob_id"]))  # type: ignore[arg-type]
    pdf = pdf_engine.render_contract_pdf(
        contract_no=c.contract_no, title=payload["title"], source=c.source, body_text=payload.get("body_text"),
        fields=fields_of(payload), parties=_party_signs(c, payload, images), version_no=v.version_no,
        content_hash=v.content_hash, completed_at=c.completed_at, source_pdf=source_pdf, sig_images=images,
        test_mode=is_test_mode(c), issuer=issuer_info(),
    )
    blob = _store_blob(db, c.id, "CONTRACT_PDF", pdf, ref=f"v{v.version_no}")
    evidence.record(db, c.id, "PDF_GENERATED", None, v.version_no, blob.sha256, {"kind": "CONTRACT_PDF", "size": blob.size})
    c.document_hash = blob.sha256
    c.verification_id = new_verification_id()
    evidence.record(db, c.id, "HASH_CREATED", None, v.version_no, blob.sha256, {"verification_id": c.verification_id})
    retention.schedule_after_completion(c)


def contract_pdf(db: Session, c: Contract) -> tuple[bytes, str]:
    if c.status != "COMPLETED":
        raise ContractError(409, "NOT_COMPLETED", "계약이 완료된 뒤 PDF 를 받을 수 있어요.")
    b = db.scalar(select(DocumentBlob).where(DocumentBlob.contract_id == c.id, DocumentBlob.kind == "CONTRACT_PDF"))
    if b is None:
        raise ContractError(404, "NOT_FOUND", "계약서 PDF 가 없어요.")
    data = read_blob(b)
    if sha256_bytes(data) != c.document_hash:
        raise ContractError(500, "INTEGRITY", "PDF 무결성 확인에 실패했어요.")
    return data, f"{c.contract_no}.pdf"


def preview_pdf(db: Session, c: Contract) -> bytes:
    """완료 전 미리보기 PDF (서명 전, 워터마크 없이 현재 내용)."""
    v = current_version(db, c)
    payload = load_payload(v)
    images = _sig_images(db, c)
    source_pdf = None
    if c.source == "PDF" and payload.get("source_blob_id"):
        source_pdf = read_blob(db.get(DocumentBlob, payload["source_blob_id"]))  # type: ignore[arg-type]
    return pdf_engine.render_contract_pdf(
        contract_no=c.contract_no + " (미리보기)", title=payload["title"], source=c.source, body_text=payload.get("body_text"),
        fields=fields_of(payload), parties=_party_signs(c, payload, images), version_no=v.version_no,
        content_hash=v.content_hash, completed_at=_now(), source_pdf=source_pdf, sig_images=images,
        test_mode=is_test_mode(c), issuer=issuer_info(),
    )


def new_issue_no() -> str:
    return f"C-{_now():%Y%m%d}-{_rand(8)}"


def certificate_context(db: Session, c: Contract, issue_no: str) -> dict:
    job = latest_anchor(db, c)
    av = anchor_view(job)
    final = db.scalar(select(DocumentVersion).where(DocumentVersion.contract_id == c.id, DocumentVersion.version_no == c.final_version_no))
    version_count = len(db.scalars(select(DocumentVersion.version_no).where(DocumentVersion.contract_id == c.id)).all())
    blob = db.scalar(select(DocumentBlob).where(DocumentBlob.contract_id == c.id, DocumentBlob.kind == "CONTRACT_PDF"))
    roles = {p.user_id: p.role for p in c.parties}
    evs = evidence.list_events(db, c.id)
    events = [{"seq": e.seq, "timestamp": e.timestamp, "label": evidence.EVENT_LABELS.get(e.event_type, e.event_type),
               "role": ("당사자 " + roles[e.actor_id]) if e.actor_id in roles else (("당사자 " + e.event_metadata["role"]) if e.event_metadata.get("role") else None),
               "version": e.document_version, "hash": e.document_hash}
              for e in evs if e.event_type != "CERTIFICATE_GENERATED"]
    return {
        "issue_no": issue_no, "issuer": issuer_info(), "test_mode": is_test_mode(c),
        "contract_no": c.contract_no, "title": c.title, "completed_at": c.completed_at, "version_no": c.final_version_no,
        "version_count": version_count,
        "parties": [{"role_label": ROLE_LABEL[p.role], "name_masked": p.display_name_masked or "-", "identity_status": p.identity_status,
                     "identity_verified_at": p.identity_verified_at, "signed_at": p.signed_at, "provider": p.signature_provider} for p in c.parties],
        "document_hash": c.document_hash, "content_hash": final.content_hash if final else "", "document_size": blob.size if blob else 0,
        "verification_id": c.verification_id, "verify_url": f"{get_settings().PUBLIC_BASE_URL}/verify/{c.verification_id}",
        "anchor": {**av, "confirmed_at": job.confirmed_at if job else None}, "issued_at": _now(),
        "events": events, "chain_valid": evidence.verify_chain(db, c.id), "chain_head": evs[-1].event_hash if evs else "",
        "short_hash": short_hash(c.document_hash),
    }


def certificate_pdf(db: Session, c: Contract, actor_id: str | None) -> tuple[bytes, str]:
    """전자계약 체결 확인서 — 발급할 때마다 발급번호를 부여하고 파일의 SHA-256 을 발급 대장에 남긴다."""
    if c.status != "COMPLETED":
        raise ContractError(409, "NOT_COMPLETED", "계약이 완료된 뒤 확인서를 받을 수 있어요.")
    issue_no = new_issue_no()
    ctx = certificate_context(db, c, issue_no)
    pdf = pdf_engine.render_certificate_pdf(ctx)
    digest = sha256_bytes(pdf)
    anchor_status = ctx["anchor"]["status"]
    db.add(CertificateIssuance(issue_no=issue_no, contract_id=c.id, sha256=digest, issued_by=actor_id,
                               anchor_status=anchor_status, test_mode=ctx["test_mode"]))
    evidence.record(db, c.id, "CERTIFICATE_GENERATED", actor_id, c.final_version_no, c.document_hash,
                    {"kind": "CERTIFICATE_PDF", "sha256": digest, "status": anchor_status, "issue_no": issue_no})
    db.commit()
    return pdf, f"{c.contract_no}-certificate-{issue_no}.pdf"


def source_pdf_bytes(db: Session, c: Contract) -> bytes:
    payload = load_payload(current_version(db, c))
    if not payload.get("source_blob_id"):
        raise ContractError(404, "NOT_FOUND", "원본 PDF 가 없어요.")
    return read_blob(db.get(DocumentBlob, payload["source_blob_id"]))  # type: ignore[arg-type]


def signature_image(db: Session, c: Contract, sig_value: str) -> bytes:
    if not sig_value.startswith("sig:"):
        raise ContractError(404, "NOT_FOUND", "서명을 찾을 수 없어요.")
    b = db.get(DocumentBlob, sig_value[4:])
    if b is None or b.contract_id != c.id or b.kind != "SIGNATURE_IMAGE":
        raise ContractError(404, "NOT_FOUND", "서명을 찾을 수 없어요.")
    return read_blob(b)


def extend_retention(db: Session, c: Contract, party: ContractParty) -> None:
    _require_owner(c, party)
    pol = retention.policy_for(c.contract_type)
    if not pol.get("allow_extended_retention"):
        raise ContractError(409, "NOT_ALLOWED", "이 계약 종류는 보관 연장을 지원하지 않아요.")
    if c.status != "COMPLETED":
        raise ContractError(409, "NOT_COMPLETED", "계약 완료 후 보관 연장을 선택할 수 있어요.")
    retention.schedule_after_completion(c, extended=True)
    db.commit()


def list_my_contracts(db: Session, user: User) -> list[dict]:
    rows = db.scalars(
        select(Contract).join(ContractParty, ContractParty.contract_id == Contract.id).where(ContractParty.user_id == user.id)
        .order_by(Contract.created_at.desc()).limit(100)
    ).all()
    out = []
    for c in rows:
        me = next(p for p in c.parties if p.user_id == user.id)
        other = next((p for p in c.parties if p.user_id != user.id), None)
        anchor = latest_anchor(db, c)
        out.append({"id": c.id, "title": c.title, "status": c.status, "my_role": me.role, "counterparty": other.display_name_masked if other else None,
                    "created_at": c.created_at.isoformat(), "completed_at": c.completed_at.isoformat() if c.completed_at else None,
                    "anchor_status": anchor.status if anchor else "NOT_REQUESTED", "needs_my_action": _needs_action(c, me)})
    return out


def _needs_action(c: Contract, me: ContractParty) -> bool:
    if c.status in ("INVITED", "SIGNING"):
        return me.signature_status != "SIGNED"
    return c.status in ("DRAFT", "READY") and me.role == "A"
