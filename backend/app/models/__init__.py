"""DB 모델.

원칙: 계약 원문/입력값/서명 이미지/PDF 는 document_blobs · document_versions.payload_* 에만
암호화되어 존재하고, 보존정책에 따라 삭제(purge)된다. 나머지 테이블은 메타데이터만 가진다.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(32))
    provider_user_key: Mapped[str] = mapped_column(String(128))
    display_name_masked: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("provider", "provider_user_key"),)


class Contract(Base):
    __tablename__ = "contracts"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    contract_no: Mapped[str] = mapped_column(String(32), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    contract_type: Mapped[str] = mapped_column(String(32), default="general")
    source: Mapped[str] = mapped_column(String(16), default="TEXT")  # TEXT | PDF | TEMPLATE
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(16), default="DRAFT")
    current_version_no: Mapped[int] = mapped_column(Integer, default=1)
    final_version_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    document_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    verification_id: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    purge_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    keep_encrypted_original: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    parties: Mapped[list["ContractParty"]] = relationship(
        back_populates="contract", order_by="ContractParty.created_at", cascade="all, delete-orphan"
    )


class ContractParty(Base):
    __tablename__ = "contract_parties"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # A (작성자) | B (상대방)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    display_name_masked: Mapped[str | None] = mapped_column(String(64), nullable=True)
    invite_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    invite_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    identity_status: Mapped[str] = mapped_column(String(16), default="PENDING")
    identity_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    identity_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_version_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    signature_status: Mapped[str] = mapped_column(String(16), default="PENDING")  # PENDING|STARTED|SIGNED|INVALIDATED
    signature_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    signature_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    signature_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    signed_version_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    signed_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    contract: Mapped[Contract] = relationship(back_populates="parties")


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT")  # DRAFT|PROPOSED|AGREED|FINAL
    sealed: Mapped[bool] = mapped_column(Boolean, default=False)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason: Mapped[str] = mapped_column(String(200), default="")
    changed_fields: Mapped[list] = mapped_column(JSON, default=list)
    payload_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    payload_wrapped_dek: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    key_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("contract_id", "version_no"),)


class DocumentBlob(Base):
    __tablename__ = "document_blobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id"), index=True)
    kind: Mapped[str] = mapped_column(String(24))  # SOURCE_PDF | CONTRACT_PDF | CERTIFICATE_PDF | SIGNATURE_IMAGE
    ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    wrapped_dek: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    key_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    event_id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    seq: Mapped[int] = mapped_column(Integer)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id"), index=True)
    actor_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    event_type: Mapped[str] = mapped_column(String(40))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    document_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    document_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    prev_event_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_hash: Mapped[str] = mapped_column(String(64))
    __table_args__ = (UniqueConstraint("contract_id", "seq"),)


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    provider: Mapped[str] = mapped_column(String(32))
    product: Mapped[str] = mapped_column(String(32), default="BLOCKCHAIN_RECORD")
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(8), default="KRW")
    status: Mapped[str] = mapped_column(String(16), default="PENDING")  # PENDING|PAID|FAILED|CANCELED|REFUNDED
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    provider_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AnchorJob(Base):
    __tablename__ = "anchor_jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id"), index=True)
    payment_id: Mapped[str] = mapped_column(ForeignKey("payments.id"))
    document_hash: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    mode: Mapped[str] = mapped_column(String(16), default="single")
    status: Mapped[str] = mapped_column(String(16), default="PENDING")  # PENDING|RETRY|SUBMITTED|CONFIRMED|FAILED
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    provider: Mapped[str] = mapped_column(String(32))
    network: Mapped[str] = mapped_column(String(64))
    tx_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    block_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    anchored_value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    merkle_proof: Mapped[list | None] = mapped_column(JSON, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class MockLedgerRecord(Base):
    """MockBlockchainProvider 의 가짜 원장 (개발/테스트 전용)."""

    __tablename__ = "mock_ledger"
    tx_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(String(64), unique=True)
    kind: Mapped[str] = mapped_column(String(8), default="HASH")
    version: Mapped[int] = mapped_column(Integer, default=1)
    block_number: Mapped[int] = mapped_column(Integer)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DevFault(Base):
    """개발용 장애 주입 (예: 블록체인 N회 실패). production 에서는 API 가 비활성화된다."""

    __tablename__ = "dev_faults"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, default=0)


class AppKV(Base):
    __tablename__ = "app_kv"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
