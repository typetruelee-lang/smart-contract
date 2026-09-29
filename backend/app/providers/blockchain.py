"""BlockchainProvider — 특정 체인에 종속되지 않는 adapter.

인터페이스 (지시서 22항):
  register_document_hash(hash, version) -> TxReceipt
  verify_document_hash(hash)            -> OnchainRecord | None
  get_transaction(tx_id)                -> TxInfo | None
  get_network_status()                  -> dict
(+ register_root(root) : Merkle 확장 기능)

구현:
  MockBlockchainProvider   : DB 원장. 비용 없음. dev_faults.blockchain_fail 로 N회 실패 주입.
  EvmBlockchainProvider    : Hardhat 로컬 / 테스트넷 / 메인넷 공용 (web3.py). DocumentRegistry.sol 사용.
  OpenTimestampsProvider   : 운영 후보(비트코인 기반, 지갑 불필요) — 골격만 제공.
블록체인에는 문서 Hash·시각·버전 외의 어떤 정보도 기록하지 않는다.
"""
from __future__ import annotations

import json
import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import ROOT_DIR, get_settings
from app.models import DevFault, MockLedgerRecord
from app.providers.base import ProviderError, ProviderNotConfigured
from app.services.hashing import normalize_hash

ARTIFACT = ROOT_DIR / "contracts" / "artifacts" / "DocumentRegistry.json"


@dataclass
class TxReceipt:
    tx_id: str
    status: str  # SUBMITTED | CONFIRMED
    block_number: int | None = None


@dataclass
class OnchainRecord:
    value: str
    timestamp: datetime
    version: int
    tx_id: str | None = None


@dataclass
class TxInfo:
    tx_id: str
    confirmed: bool
    block_number: int | None
    confirmations: int


class BlockchainProvider(ABC):
    name = "base"
    network = "unknown"

    @abstractmethod
    def register_document_hash(self, document_hash: str, version: int = 1) -> TxReceipt: ...

    @abstractmethod
    def register_root(self, root: str) -> TxReceipt: ...

    @abstractmethod
    def verify_document_hash(self, document_hash: str) -> OnchainRecord | None: ...

    @abstractmethod
    def get_transaction(self, tx_id: str) -> TxInfo | None: ...

    @abstractmethod
    def get_network_status(self) -> dict: ...

    def explorer_url(self, tx_id: str | None) -> str | None:
        base = get_settings().BLOCKCHAIN_EXPLORER_TX_URL
        return f"{base.rstrip('/')}/{tx_id}" if (base and tx_id) else None


def _consume_fault(db: Session, key: str) -> bool:
    f = db.get(DevFault, key, with_for_update=True)
    if f and f.value > 0:
        f.value -= 1
        db.flush()
        return True
    return False


class MockBlockchainProvider(BlockchainProvider):
    name = "mock"
    network = "mock-ledger"

    def __init__(self, db: Session):
        self.db = db

    def _write(self, value: str, kind: str, version: int) -> TxReceipt:
        if _consume_fault(self.db, "blockchain_fail"):
            raise ProviderError("모의 블록체인 네트워크 오류 (장애 주입)")
        existing = self.db.scalar(select(MockLedgerRecord).where(MockLedgerRecord.value == value))
        if existing:  # 멱등: 같은 값은 같은 TX
            return TxReceipt(existing.tx_id, "CONFIRMED", existing.block_number)
        block = (self.db.scalar(select(func.max(MockLedgerRecord.block_number))) or 0) + 1
        tx = "0x" + secrets.token_hex(32)
        self.db.add(MockLedgerRecord(tx_id=tx, value=value, kind=kind, version=version, block_number=block))
        self.db.flush()
        return TxReceipt(tx, "CONFIRMED", block)

    def register_document_hash(self, document_hash: str, version: int = 1) -> TxReceipt:
        return self._write(normalize_hash(document_hash), "HASH", version)

    def register_root(self, root: str) -> TxReceipt:
        return self._write(normalize_hash(root), "ROOT", 0)

    def verify_document_hash(self, document_hash: str) -> OnchainRecord | None:
        r = self.db.scalar(select(MockLedgerRecord).where(MockLedgerRecord.value == normalize_hash(document_hash)))
        if not r:
            return None
        return OnchainRecord(value=r.value, timestamp=r.timestamp, version=r.version, tx_id=r.tx_id)

    def get_transaction(self, tx_id: str) -> TxInfo | None:
        r = self.db.get(MockLedgerRecord, tx_id)
        if not r:
            return None
        head = self.db.scalar(select(func.max(MockLedgerRecord.block_number))) or r.block_number
        return TxInfo(tx_id, True, r.block_number, head - r.block_number + 1)

    def get_network_status(self) -> dict:
        n = self.db.scalar(select(func.count()).select_from(MockLedgerRecord)) or 0
        return {"ok": True, "provider": self.name, "network": self.network, "records": n}


class EvmBlockchainProvider(BlockchainProvider):
    name = "evm"

    def __init__(self, db: Session, w3=None, contract_address: str | None = None):
        from web3 import Web3

        s = get_settings()
        self.db = db
        self.network = s.BLOCKCHAIN_NETWORK
        if w3 is None:
            if not s.BLOCKCHAIN_RPC_URL:
                raise ProviderNotConfigured("BLOCKCHAIN_RPC_URL 이 필요합니다.")
            w3 = Web3(Web3.HTTPProvider(s.BLOCKCHAIN_RPC_URL, request_kwargs={"timeout": 10}))
        self.w3 = w3
        art = json.loads(Path(ARTIFACT).read_text())
        self.abi, self.bytecode = art["abi"], art["bytecode"]
        self.account = None
        if s.BLOCKCHAIN_PRIVATE_KEY:
            self.account = w3.eth.account.from_key(s.BLOCKCHAIN_PRIVATE_KEY)
            self.sender = self.account.address
        else:
            # 로컬 개발 체인(Hardhat/eth-tester)의 잠금 해제 계정 — 운영에서는 Private Key 필수
            if s.is_production:
                raise ProviderNotConfigured("운영 환경에서는 BLOCKCHAIN_PRIVATE_KEY(Secret Manager) 가 필요합니다.")
            accounts = w3.eth.accounts
            if not accounts:
                raise ProviderNotConfigured("서명 계정이 없습니다. BLOCKCHAIN_PRIVATE_KEY 를 설정하세요.")
            self.sender = accounts[0]
        address = contract_address or s.BLOCKCHAIN_CONTRACT_ADDRESS or self._stored_address()
        if not address:
            if s.is_production:
                raise ProviderNotConfigured("BLOCKCHAIN_CONTRACT_ADDRESS 가 필요합니다.")
            address = self.deploy()
        self.contract = w3.eth.contract(address=Web3.to_checksum_address(address), abi=self.abi)

    # 로컬 체인에서는 최초 1회 자동 배포하고 주소를 app_kv 에 저장
    def _kv_key(self) -> str:
        return f"evm_contract:{self.network}:{self.w3.eth.chain_id}"

    def _stored_address(self) -> str | None:
        from app.models import AppKV

        kv = self.db.get(AppKV, self._kv_key())
        if kv and self.w3.eth.get_code(kv.value) not in (b"", b"\x00"):
            return kv.value
        return None

    def deploy(self) -> str:
        from app.models import AppKV

        factory = self.w3.eth.contract(abi=self.abi, bytecode=self.bytecode)
        receipt = self._send(factory.constructor())
        address = receipt.contractAddress
        kv = self.db.get(AppKV, self._kv_key())
        if kv:
            kv.value = address
        else:
            self.db.add(AppKV(key=self._kv_key(), value=address))
        self.db.flush()
        return address

    def _send(self, fn):
        try:
            if self.account is not None:
                tx = fn.build_transaction({"from": self.sender, "nonce": self.w3.eth.get_transaction_count(self.sender)})
                signed = self.account.sign_transaction(tx)
                tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            else:
                tx_hash = fn.transact({"from": self.sender})
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"EVM 트랜잭션 실패: {type(e).__name__}") from e
        if receipt.status != 1:
            raise ProviderError("EVM 트랜잭션이 revert 되었어요.")
        return receipt

    def _write(self, fn, value: str) -> TxReceipt:
        if _consume_fault(self.db, "blockchain_fail"):
            raise ProviderError("블록체인 네트워크 오류 (장애 주입)")
        existing = self.verify_document_hash(value) if fn.fn_name == "register" else None
        if existing:
            return TxReceipt(existing.tx_id or "", "CONFIRMED", None)
        r = self._send(fn)
        return TxReceipt(r.transactionHash.hex() if hasattr(r.transactionHash, "hex") else str(r.transactionHash), "SUBMITTED", r.blockNumber)

    def register_document_hash(self, document_hash: str, version: int = 1) -> TxReceipt:
        h = normalize_hash(document_hash)
        return self._write(self.contract.functions.register(bytes.fromhex(h), version), h)

    def register_root(self, root: str) -> TxReceipt:
        r = normalize_hash(root)
        return self._write(self.contract.functions.registerRoot(bytes.fromhex(r)), r)

    def verify_document_hash(self, document_hash: str) -> OnchainRecord | None:
        h = normalize_hash(document_hash)
        ts, version, exists = self.contract.functions.get(bytes.fromhex(h)).call()
        if not exists:
            ts_root = self.contract.functions.getRoot(bytes.fromhex(h)).call()
            if not ts_root:
                return None
            return OnchainRecord(value=h, timestamp=datetime.fromtimestamp(ts_root, timezone.utc), version=0)
        tx_id = None
        try:
            logs = self.contract.events.DocumentRegistered().get_logs(from_block=0, argument_filters={"documentHash": bytes.fromhex(h)})
            if logs:
                tx_id = logs[-1].transactionHash.hex()
        except Exception:  # noqa: BLE001
            pass
        return OnchainRecord(value=h, timestamp=datetime.fromtimestamp(ts, timezone.utc), version=version, tx_id=tx_id)

    def get_transaction(self, tx_id: str) -> TxInfo | None:
        try:
            r = self.w3.eth.get_transaction_receipt(tx_id)
        except Exception:  # noqa: BLE001
            return None
        head = self.w3.eth.block_number
        conf = head - r.blockNumber + 1
        return TxInfo(tx_id, r.status == 1 and conf >= get_settings().BLOCKCHAIN_CONFIRMATIONS, r.blockNumber, conf)

    def get_network_status(self) -> dict:
        try:
            return {"ok": self.w3.is_connected(), "provider": self.name, "network": self.network,
                    "chain_id": self.w3.eth.chain_id, "block": self.w3.eth.block_number, "contract": self.contract.address}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "provider": self.name, "network": self.network, "error": type(e).__name__}


class OpenTimestampsProvider(BlockchainProvider):  # pragma: no cover - 운영 후보 골격
    name = "opentimestamps"
    network = "bitcoin-ots"

    def __init__(self, db: Session):
        raise ProviderNotConfigured(
            "OpenTimestamps provider 는 운영 후보로 설계만 되어 있습니다. 채택 시 calendar 서버 연동을 구현합니다 (DEPLOYMENT.md 참조)."
        )

    def register_document_hash(self, document_hash: str, version: int = 1) -> TxReceipt: ...
    def register_root(self, root: str) -> TxReceipt: ...
    def verify_document_hash(self, document_hash: str) -> OnchainRecord | None: ...
    def get_transaction(self, tx_id: str) -> TxInfo | None: ...
    def get_network_status(self) -> dict: ...
