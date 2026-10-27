"""OpenTimestamps(OTS) 기반 '디지털 지문 기록' — 운영 권장 provider.

왜 OTS 인가 (앱인토스 정책·운영 관점)
- 지갑·코인·토큰이 전혀 필요 없다. 운영사는 가상자산을 보유·구매·전송하지 않는다 (가스비 없음, 무료).
- 문서 Hash 를 공개 calendar 서버에 보내면, calendar 가 여러 Hash 를 묶어 비트코인 블록에 기록한다.
  결과물은 표준 `.ots` 증명 파일이며, 누구나 opentimestamps.org 나 공개 도구로 우리 서버 없이 검증할 수 있다.
- 개인정보 보호: 문서 Hash 에 임의 nonce 를 붙여 한 번 더 해시한 값만 calendar 로 보낸다
  (calendar 는 원래 문서 Hash 조차 알 수 없다).

흐름
1) register_document_hash: calendar 여러 곳에 제출 → '대기(pending)' 증명 저장 → SUBMITTED
2) get_transaction: 주기적으로 calendar 에 업그레이드 요청 → 비트코인 블록 증명이 붙으면 confirmed
   (보통 1~6시간. 워커가 OTS_POLL_SECONDS 간격으로 확인)
3) verify_document_hash: 증명 속 비트코인 블록 높이의 머클 루트를 공개 블록 탐색기 API 로 조회해 대조
"""
from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from typing import Iterator
from urllib.parse import urlparse

import httpx
from opentimestamps.core.notary import BitcoinBlockHeaderAttestation, PendingAttestation
from opentimestamps.core.op import OpAppend, OpSHA256
from opentimestamps.core.serialize import BytesDeserializationContext, BytesSerializationContext, DeserializationError
from opentimestamps.core.timestamp import DetachedTimestampFile, Timestamp
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AppKV
from app.providers.base import ProviderError, ProviderNotConfigured
from app.providers.blockchain import BlockchainProvider, OnchainRecord, TxInfo, TxReceipt
from app.services.hashing import normalize_hash

ACCEPT = {"Accept": "application/vnd.opentimestamps.v1", "User-Agent": "kyeyakhaja-ots/1.0"}
MAX_PROOF_BYTES = 64 * 1024


def _walk(ts: Timestamp) -> Iterator[Timestamp]:
    yield ts
    for child in ts.ops.values():
        yield from _walk(child)


def _key(document_hash: str) -> str:
    return "ots:" + document_hash[:60]  # app_kv.key 는 64자


class OpenTimestampsProvider(BlockchainProvider):
    name = "opentimestamps"
    network = "bitcoin-ots"

    def __init__(self, db: Session, client: httpx.Client | None = None):
        s = get_settings()
        self.db = db
        self.calendars = [u.strip().rstrip("/") for u in s.OTS_CALENDARS.split(",") if u.strip()]
        if not self.calendars:
            raise ProviderNotConfigured("OTS_CALENDARS 가 비어 있어요.")
        for u in self.calendars:
            if urlparse(u).scheme != "https" and s.APP_ENV == "production":
                raise ProviderNotConfigured("운영에서는 https calendar 만 쓸 수 있어요.")
        self.explorer_api = s.BITCOIN_EXPLORER_API.rstrip("/")
        self.poll_seconds = s.OTS_POLL_SECONDS
        self.http = client or httpx.Client(timeout=s.OTS_HTTP_TIMEOUT, headers=ACCEPT, follow_redirects=False)

    # ---------- 저장 ----------
    def _load(self, document_hash: str) -> tuple[DetachedTimestampFile, dict] | None:
        row = self.db.get(AppKV, _key(document_hash))
        if row is None:
            return None
        rec = json.loads(row.value)
        if rec.get("hash") != document_hash:
            return None
        raw = base64.b64decode(rec["ots"])
        dtf = DetachedTimestampFile.deserialize(BytesDeserializationContext(raw))
        if dtf.file_digest != bytes.fromhex(document_hash):  # 증명이 이 문서의 것인지
            return None
        return dtf, rec

    def _save(self, document_hash: str, dtf: DetachedTimestampFile, **extra) -> None:
        ctx = BytesSerializationContext()
        dtf.serialize(ctx)
        row = self.db.get(AppKV, _key(document_hash))
        rec = json.loads(row.value) if row else {}
        rec.update({"hash": document_hash, "ots": base64.b64encode(ctx.getbytes()).decode()}, **extra)
        if row:
            row.value = json.dumps(rec)
        else:
            self.db.add(AppKV(key=_key(document_hash), value=json.dumps(rec)))
        self.db.flush()

    def proof_file(self, document_hash: str) -> bytes | None:
        """사용자에게 내려줄 표준 .ots 파일 (opentimestamps.org 에서 원본 PDF 와 함께 검증 가능)."""
        got = self._load(normalize_hash(document_hash))
        if got is None:
            return None
        ctx = BytesSerializationContext()
        got[0].serialize(ctx)
        return ctx.getbytes()

    # ---------- calendar ----------
    def _read_timestamp(self, resp: httpx.Response, msg: bytes) -> Timestamp:
        body = resp.content
        if len(body) > MAX_PROOF_BYTES:
            raise ProviderError("calendar 응답이 너무 커요.")
        try:
            return Timestamp.deserialize(BytesDeserializationContext(body), msg)
        except DeserializationError as e:
            raise ProviderError(f"calendar 응답 형식 오류: {e}") from e

    def _stamp(self, document_hash: str) -> DetachedTimestampFile:
        digest = bytes.fromhex(document_hash)
        dtf = DetachedTimestampFile(OpSHA256(), Timestamp(digest))
        # 개인정보 보호용 nonce: calendar 에는 sha256(hash || nonce) 만 전달
        nonce_stamp = dtf.timestamp.ops.add(OpAppend(os.urandom(16)))
        tip = nonce_stamp.ops.add(OpSHA256())
        ok, errors = 0, []
        for cal in self.calendars:
            try:
                r = self.http.post(f"{cal}/digest", content=tip.msg)
                if r.status_code != 200:
                    errors.append(f"{urlparse(cal).netloc}:{r.status_code}")
                    continue
                tip.merge(self._read_timestamp(r, tip.msg))
                ok += 1
            except (httpx.HTTPError, ProviderError) as e:
                errors.append(f"{urlparse(cal).netloc}:{type(e).__name__}")
        if ok == 0:
            raise ProviderError("모든 OpenTimestamps calendar 제출 실패: " + ", ".join(errors))
        return dtf

    def _upgrade(self, dtf: DetachedTimestampFile) -> bool:
        """대기 중인 증명을 calendar 에 물어 비트코인 증명으로 업그레이드. 바뀌었으면 True."""
        changed = False
        allowed = set(self.calendars)
        for sub in list(_walk(dtf.timestamp)):
            for att in list(sub.attestations):
                if not isinstance(att, PendingAttestation):
                    continue
                uri = att.uri.rstrip("/")
                if uri not in allowed:  # 증명에 적힌 임의 주소로는 요청하지 않는다 (SSRF 방지)
                    continue
                try:
                    r = self.http.get(f"{uri}/timestamp/{sub.msg.hex()}")
                except httpx.HTTPError:
                    continue
                if r.status_code != 200:
                    continue  # 404 = 아직 비트코인에 포함 전
                try:
                    sub.merge(self._read_timestamp(r, sub.msg))
                    changed = True
                except (ProviderError, ValueError):
                    continue
        return changed

    @staticmethod
    def _bitcoin_attestations(dtf: DetachedTimestampFile) -> list[tuple[bytes, int]]:
        out = []
        for msg, att in dtf.timestamp.all_attestations():
            if isinstance(att, BitcoinBlockHeaderAttestation):
                out.append((msg, att.height))
        return sorted(out, key=lambda x: x[1])

    def _block(self, height: int) -> dict:
        try:
            h = self.http.get(f"{self.explorer_api}/block-height/{height}")
            if h.status_code != 200:
                raise ProviderError(f"블록 조회 실패({h.status_code})")
            b = self.http.get(f"{self.explorer_api}/block/{h.text.strip()}")
            if b.status_code != 200:
                raise ProviderError(f"블록 조회 실패({b.status_code})")
            return b.json()
        except httpx.HTTPError as e:
            raise ProviderError(f"블록 탐색기 연결 실패: {type(e).__name__}") from e

    # ---------- BlockchainProvider ----------
    def register_document_hash(self, document_hash: str, version: int = 1) -> TxReceipt:
        h = normalize_hash(document_hash)
        got = self._load(h)
        if got is None:  # 멱등: 이미 제출한 Hash 는 다시 제출하지 않는다
            self._save(h, self._stamp(h), submitted_at=datetime.now(timezone.utc).isoformat())
        return TxReceipt(tx_id="ots:" + h, status="SUBMITTED")

    def register_root(self, root: str) -> TxReceipt:
        return self.register_document_hash(root)

    def get_transaction(self, tx_id: str) -> TxInfo | None:
        if not tx_id.startswith("ots:"):
            return None
        h = normalize_hash(tx_id[4:])
        got = self._load(h)
        if got is None:
            return None
        dtf, rec = got
        if not self._bitcoin_attestations(dtf) and self._upgrade(dtf):
            self._save(h, dtf)
        atts = self._bitcoin_attestations(dtf)
        if not atts:
            return TxInfo(tx_id=tx_id, confirmed=False, block_number=None, confirmations=0)
        return TxInfo(tx_id=tx_id, confirmed=True, block_number=atts[0][1], confirmations=1)

    def verify_document_hash(self, document_hash: str) -> OnchainRecord | None:
        h = normalize_hash(document_hash)
        got = self._load(h)
        if got is None:
            return None
        dtf, rec = got
        if rec.get("verified"):  # 한 번 대조한 결과는 저장 (블록은 바뀌지 않음)
            v = rec["verified"]
            return OnchainRecord(value=h, timestamp=datetime.fromisoformat(v["time"]), version=1, tx_id="ots:" + h)
        for msg, height in self._bitcoin_attestations(dtf):
            blk = self._block(height)
            # 증명의 마지막 메시지 = 블록 헤더의 머클 루트 (내부 바이트 순서 → 표시용은 뒤집은 hex)
            if blk.get("merkle_root") == msg[::-1].hex():
                t = datetime.fromtimestamp(int(blk["timestamp"]), tz=timezone.utc)
                self._save(h, dtf, verified={"height": height, "block_hash": blk.get("id"), "time": t.isoformat()})
                return OnchainRecord(value=h, timestamp=t, version=1, tx_id="ots:" + h)
        return None

    def get_network_status(self) -> dict:
        try:
            r = self.http.get(f"{self.explorer_api}/blocks/tip/height")
            return {"ok": r.status_code == 200, "provider": self.name, "network": self.network,
                    "calendars": len(self.calendars), "bitcoin_tip": r.text.strip() if r.status_code == 200 else None}
        except httpx.HTTPError as e:
            return {"ok": False, "provider": self.name, "network": self.network, "error": type(e).__name__}

    def explorer_url(self, tx_id: str | None) -> str | None:  # 블록 높이 페이지로 연결
        return None


def block_explorer_url(height: int | None) -> str | None:
    base = get_settings().BITCOIN_EXPLORER_WEB.rstrip("/")
    return f"{base}/block-height/{height}" if (base and height) else None
