"""공개 검증 — 개인정보 없이 문서 동일성과 블록체인 기록을 확인한다.

PDF 원본은 서버로 보내지 않는다. 브라우저가 SHA-256 을 계산해 Hash 만 전송한다.
(API 는 서버측 PDF 업로드 검증도 지원하지만 업로드된 파일은 저장하지 않는다)
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Contract
from app.providers import get_blockchain
from app.services.contracts import latest_anchor
from app.services.hashing import normalize_hash, short_hash
from app.services.merkle import MerkleService


class VerifyError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def _public(db: Session, c: Contract) -> dict:
    job = latest_anchor(db, c)
    anchor = {"status": job.status if job else "NOT_REQUESTED"}
    if job and job.status == "CONFIRMED":
        anchor.update(tx_id=job.tx_id, network=job.network, confirmed_at=job.confirmed_at.isoformat() if job.confirmed_at else None,
                      mode=job.mode, merkle_root=job.anchored_value if job.mode == "merkle" else None)
    return {
        "verification_id": c.verification_id, "contract_status": "COMPLETED" if c.status == "COMPLETED" else c.status,
        "completed_at": c.completed_at.isoformat() if c.completed_at else None,
        "document_hash": c.document_hash, "document_hash_short": short_hash(c.document_hash), "anchor": anchor,
    }


def lookup(db: Session, verification_id: str) -> dict:
    vid = (verification_id or "").strip().upper()
    if not (8 <= len(vid) <= 20):
        raise VerifyError(404, "검증번호를 찾을 수 없어요.")
    c = db.scalar(select(Contract).where(Contract.verification_id == vid))
    if c is None or c.status != "COMPLETED":
        raise VerifyError(404, "검증번호를 찾을 수 없어요.")
    return _public(db, c)


def check(db: Session, verification_id: str | None, document_hash: str) -> dict:
    try:
        h = normalize_hash(document_hash)
    except ValueError as e:
        raise VerifyError(422, str(e)) from e
    if verification_id:
        info = lookup(db, verification_id)
        c = db.scalar(select(Contract).where(Contract.verification_id == info["verification_id"]))
    else:
        c = db.scalar(select(Contract).where(Contract.document_hash == h, Contract.status == "COMPLETED"))
        if c is None:
            return {"match": False, "uploaded_hash": h, "reason": "NOT_FOUND",
                    "message": "이 문서의 디지털 지문과 일치하는 계약 기록이 없어요."}
        info = _public(db, c)
    if c is None:
        raise RuntimeError("내부 상태 오류: c 없음")
    match = h == c.document_hash
    onchain = None
    job = latest_anchor(db, c)
    if match and job and job.status == "CONFIRMED":
        try:
            bc = get_blockchain(db)
            if job.mode == "merkle":
                ok = MerkleService.verify_proof(h, job.merkle_proof or [], job.anchored_value or "")
                rec = bc.verify_document_hash(job.anchored_value or "") if ok else None
                onchain = {"recorded": bool(ok and rec), "proof_valid": ok}
            else:
                rec = bc.verify_document_hash(h)
                onchain = {"recorded": rec is not None, "recorded_at": rec.timestamp.isoformat() if rec else None}
        except Exception:  # noqa: BLE001
            onchain = {"recorded": None, "error": "블록체인 조회에 잠시 실패했어요."}
    return {
        **info, "match": match, "uploaded_hash": h, "onchain": onchain,
        "message": "문서의 디지털 지문이 기록된 값과 일치합니다." if match else "현재 문서의 디지털 지문이 기록된 값과 다릅니다.",
    }
