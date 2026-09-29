"""시나리오 7, 8 + 멱등성 + Merkle 배치 + EVM(로컬 체인) + 보존 정책."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.models import AnchorJob, Contract, MockLedgerRecord, Payment
from tests.conftest import complete_contract


def _faults(client, **kw):
    for k, v in kw.items():
        assert client.post("/api/dev/faults", {"key": k, "value": v}).status_code == 200


def test_scenario7_payment_failure_never_calls_blockchain(client_factory, db, monkeypatch):
    a, _, cid = complete_contract(client_factory)
    calls = []
    from app.providers import blockchain

    orig = blockchain.MockBlockchainProvider.register_document_hash
    monkeypatch.setattr(blockchain.MockBlockchainProvider, "register_document_hash", lambda self, *x, **k: calls.append(1) or orig(self, *x, **k))
    co = a.post(f"/api/contracts/{cid}/anchor/checkout").json()
    r = a.post(f"/api/contracts/{cid}/anchor/confirm", {"payment_id": co["payment_id"], "result": "fail"}).json()
    assert r["payment_status"] == "FAILED" and r["anchor_status"] == "NOT_REQUESTED"
    # 장애 주입으로 인한 실패도 동일
    co2 = a.post(f"/api/contracts/{cid}/anchor/checkout").json()
    _faults(a, payment_fail=1)
    r2 = a.post(f"/api/contracts/{cid}/anchor/confirm", {"payment_id": co2["payment_id"], "result": "success"}).json()
    assert r2["payment_status"] == "FAILED"
    assert calls == []
    assert db.scalar(select(func.count()).select_from(AnchorJob)) == 0
    assert db.scalar(select(func.count()).select_from(MockLedgerRecord)) == 0
    # 계약 상태는 결제와 무관하게 COMPLETED
    assert a.get(f"/api/contracts/{cid}").json()["status"] == "COMPLETED"
    types = [e["event_type"] for e in a.get(f"/api/contracts/{cid}/events").json()["events"]]
    assert types.count("PAYMENT_FAILED") == 2 and "BLOCKCHAIN_SUBMITTED" not in types


def test_payment_cancel(client_factory):
    a, _, cid = complete_contract(client_factory)
    co = a.post(f"/api/contracts/{cid}/anchor/checkout").json()
    r = a.post(f"/api/contracts/{cid}/anchor/confirm", {"payment_id": co["payment_id"], "result": "cancel"}).json()
    assert r["payment_status"] == "CANCELED"


def test_scenario8_blockchain_failure_pending_retry_success(client_factory, db):
    a, _, cid = complete_contract(client_factory)
    _faults(a, blockchain_fail=2)
    co = a.post(f"/api/contracts/{cid}/anchor/checkout").json()
    r = a.post(f"/api/contracts/{cid}/anchor/confirm", {"payment_id": co["payment_id"], "result": "success"}).json()
    # 결제 성공 + 블록체인 재시도 대기 (서로 다른 상태)
    assert r["payment_status"] == "PAID"
    assert r["anchor_status"] == "RETRY"
    view = a.get(f"/api/contracts/{cid}").json()
    assert view["payment"]["status"] == "PAID" and view["anchor"]["status"] == "RETRY"
    assert view["anchor"]["last_error"]
    # 확인서에는 '진행 중' 으로 표시
    import io

    import pdfplumber

    with pdfplumber.open(io.BytesIO(a.get(f"/api/contracts/{cid}/pdf/certificate").content)) as d:
        assert "기록 진행 중" in "".join(p.extract_text() or "" for p in d.pages)
    # 워커 재시도 1회 → 여전히 실패(주입 2회 중 두 번째)
    a.post("/api/admin/workers/run")
    assert a.get(f"/api/contracts/{cid}/anchor").json()["anchor"]["status"] == "RETRY"
    # 재시도 → 성공
    a.post("/api/admin/workers/run")
    st = a.get(f"/api/contracts/{cid}/anchor").json()["anchor"]
    assert st["status"] == "CONFIRMED" and st["attempts"] == 3 and st["tx_id"]
    types = [e["event_type"] for e in a.get(f"/api/contracts/{cid}/events").json()["events"]]
    assert types.count("BLOCKCHAIN_RETRY") == 2 and "BLOCKCHAIN_CONFIRMED" in types
    # 결제는 1건뿐
    assert db.scalar(select(func.count()).select_from(Payment).where(Payment.status == "PAID")) == 1


def test_blockchain_exhausted_retries_marks_failed_payment_stays_paid(client_factory, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "ANCHOR_MAX_ATTEMPTS", 2)
    a, _, cid = complete_contract(client_factory)
    _faults(a, blockchain_fail=5)
    co = a.post(f"/api/contracts/{cid}/anchor/checkout").json()
    a.post(f"/api/contracts/{cid}/anchor/confirm", {"payment_id": co["payment_id"], "result": "success"})
    a.post("/api/admin/workers/run")
    v = a.get(f"/api/contracts/{cid}").json()
    assert v["anchor"]["status"] == "FAILED" and v["payment"]["status"] == "PAID"


def test_idempotent_no_double_payment_or_double_record(client_factory, db):
    a, _, cid = complete_contract(client_factory)
    co1 = a.post(f"/api/contracts/{cid}/anchor/checkout").json()
    co2 = a.post(f"/api/contracts/{cid}/anchor/checkout").json()
    assert co1["payment_id"] == co2["payment_id"]  # 진행 중 결제 재사용
    a.post(f"/api/contracts/{cid}/anchor/confirm", {"payment_id": co1["payment_id"], "result": "success"})
    # 같은 결제 확인을 두 번 → 한 번만 처리
    r = a.post(f"/api/contracts/{cid}/anchor/confirm", {"payment_id": co1["payment_id"], "result": "success"}).json()
    assert r["payment_status"] == "PAID" and r["anchor_status"] == "CONFIRMED"
    # 이미 결제 완료 → 새 결제 불가
    assert a.post(f"/api/contracts/{cid}/anchor/checkout").status_code == 409
    assert db.scalar(select(func.count()).select_from(AnchorJob)) == 1
    assert db.scalar(select(func.count()).select_from(MockLedgerRecord)) == 1


def test_retry_after_failed_payment_allowed(client_factory, db):
    a, _, cid = complete_contract(client_factory)
    co = a.post(f"/api/contracts/{cid}/anchor/checkout").json()
    a.post(f"/api/contracts/{cid}/anchor/confirm", {"payment_id": co["payment_id"], "result": "fail"})
    co2 = a.post(f"/api/contracts/{cid}/anchor/checkout").json()
    assert co2["payment_id"] != co["payment_id"]
    r = a.post(f"/api/contracts/{cid}/anchor/confirm", {"payment_id": co2["payment_id"], "result": "success"}).json()
    assert r["anchor_status"] == "CONFIRMED"


def test_checkout_requires_completed_contract(client_factory):
    from tests.conftest import create_text_contract

    a = client_factory()
    a.login("hong")
    cid, _ = create_text_contract(a)
    assert a.post(f"/api/contracts/{cid}/anchor/checkout").status_code == 409


def test_blockchain_disabled_hides_feature(client_factory, monkeypatch):
    from app.core.config import get_settings

    a, _, cid = complete_contract(client_factory)
    monkeypatch.setattr(get_settings(), "BLOCKCHAIN_ENABLED", False)
    assert a.post(f"/api/contracts/{cid}/anchor/checkout").status_code == 404
    assert a.get(f"/api/contracts/{cid}").json()["blockchain_enabled"] is False


def test_merkle_batch_mode_end_to_end(client_factory, monkeypatch, db):
    """확장 기능: ANCHOR_MODE=merkle — 여러 계약 Hash 를 Root 1건으로 기록, 개별 검증은 Proof 로."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "ANCHOR_MODE", "merkle")
    cids = []
    for _ in range(3):
        a, _, cid = complete_contract(client_factory)
        co = a.post(f"/api/contracts/{cid}/anchor/checkout").json()
        r = a.post(f"/api/contracts/{cid}/anchor/confirm", {"payment_id": co["payment_id"], "result": "success"}).json()
        assert r["anchor_status"] == "PENDING"  # 배치 대기
        cids.append((a, cid))
    out = a.post("/api/admin/workers/run").json()["merkle"]
    assert out["count"] == 3
    assert db.scalar(select(func.count()).select_from(MockLedgerRecord)) == 1  # TX 1건
    for cl, cid in cids:
        st = cl.get(f"/api/contracts/{cid}").json()
        assert st["anchor"]["status"] == "CONFIRMED" and st["anchor"]["merkle_root"] == out["root"]
        pdf = cl.get(f"/api/contracts/{cid}/pdf/contract").content
        v = client_factory().post("/api/verify/check", {"verification_id": st["verification_id"], "document_hash": hashlib.sha256(pdf).hexdigest()}).json()
        assert v["match"] is True and v["onchain"]["proof_valid"] is True and v["onchain"]["recorded"] is True


# ---------------- EVM (py-evm 인메모리 체인 + DocumentRegistry.sol) ----------------

@pytest.fixture
def evm(db):
    from web3 import Web3
    from web3.providers.eth_tester import EthereumTesterProvider

    from app.providers.blockchain import EvmBlockchainProvider

    w3 = Web3(EthereumTesterProvider())
    return EvmBlockchainProvider(db, w3=w3)


def test_evm_register_verify_and_duplicate(evm, db):
    h = hashlib.sha256(b"contract-pdf").hexdigest()
    assert evm.verify_document_hash(h) is None
    r = evm.register_document_hash(h, 1)
    db.commit()
    assert r.tx_id and r.block_number
    rec = evm.verify_document_hash(h)
    assert rec is not None and rec.value == h and rec.version == 1
    info = evm.get_transaction(r.tx_id if r.tx_id.startswith("0x") else "0x" + r.tx_id)
    assert info is not None and info.confirmed
    # 중복 기록은 새 TX 없이 기존 기록 반환
    r2 = evm.register_document_hash(h, 1)
    assert r2.status == "CONFIRMED"
    st = evm.get_network_status()
    assert st["ok"] and st["chain_id"]


def test_evm_contract_stores_no_personal_data(evm):
    """스마트컨트랙트 ABI 에는 bytes32 hash / uint 값만 존재 (문자열 저장 함수 없음)."""
    for item in evm.abi:
        for inp in item.get("inputs", []):
            assert inp["type"] in ("bytes32", "uint16", "uint64", "bool", "address"), inp
    fn_names = {i["name"] for i in evm.abi if i["type"] == "function"}
    assert fn_names == {"register", "registerRoot", "get", "getRoot", "owner"}


def test_evm_only_owner_can_register(evm):
    from web3 import Web3

    other = evm.w3.eth.accounts[1]
    with pytest.raises(Exception) as ei:
        evm.contract.functions.register(b"\x01" * 32, 1).transact({"from": other})
    selector = bytes(Web3.keccak(text="NotOwner()")[:4])
    assert repr(selector)[2:-1] in str(ei.value)  # 커스텀 에러 NotOwner() 로 revert


def test_evm_merkle_root(evm):
    from app.services.merkle import MerkleService

    hs = [hashlib.sha256(bytes([i])).hexdigest() for i in range(5)]
    tree = MerkleService.create_tree(hs)
    evm.register_root(tree.get_root())
    rec = evm.verify_document_hash(tree.get_root())
    assert rec is not None and rec.version == 0


def test_full_flow_with_evm_provider(client_factory, monkeypatch, db):
    """BLOCKCHAIN_PROVIDER=evm 으로 전체 결제→기록→검증 (인메모리 EVM)."""
    from web3 import Web3
    from web3.providers.eth_tester import EthereumTesterProvider

    import app.providers as providers
    from app.providers.blockchain import EvmBlockchainProvider

    w3 = Web3(EthereumTesterProvider())
    monkeypatch.setattr(providers, "get_blockchain", lambda d: EvmBlockchainProvider(d, w3=w3))
    import app.services.anchoring as anch
    import app.services.verification as ver

    monkeypatch.setattr(anch, "get_blockchain", lambda d: EvmBlockchainProvider(d, w3=w3))
    monkeypatch.setattr(ver, "get_blockchain", lambda d: EvmBlockchainProvider(d, w3=w3))
    a, _, cid = complete_contract(client_factory)
    co = a.post(f"/api/contracts/{cid}/anchor/checkout").json()
    r = a.post(f"/api/contracts/{cid}/anchor/confirm", {"payment_id": co["payment_id"], "result": "success"}).json()
    assert r["anchor_status"] == "CONFIRMED"
    st = a.get(f"/api/contracts/{cid}").json()
    assert st["anchor"]["provider"] == "evm"
    pdf = a.get(f"/api/contracts/{cid}/pdf/contract").content
    v = client_factory().post("/api/verify/check", {"verification_id": st["verification_id"], "document_hash": hashlib.sha256(pdf).hexdigest()}).json()
    assert v["match"] and v["onchain"]["recorded"] is True


# ---------------- 보존 정책 ----------------

def test_retention_purges_original_but_keeps_evidence(client_factory, db):
    from app.services import retention

    a, _, cid = complete_contract(client_factory)
    pdf = a.get(f"/api/contracts/{cid}/pdf/contract").content
    c = db.get(Contract, cid)
    assert c.purge_at is not None
    days = (c.purge_at - c.completed_at).days
    assert days == 7
    retention.run_retention(db, now=datetime.now(timezone.utc) + timedelta(days=8))
    r = a.get(f"/api/contracts/{cid}/pdf/contract")
    assert r.status_code == 410 and "삭제" in r.json()["detail"]["message"]
    view = a.get(f"/api/contracts/{cid}").json()
    assert view["purged"] is True and view["payload"] is None and view["status"] == "COMPLETED"
    # 검증은 계속 가능 (Hash 는 영구 보관)
    v = client_factory().post("/api/verify/check", {"verification_id": view["verification_id"], "document_hash": hashlib.sha256(pdf).hexdigest()}).json()
    assert v["match"] is True
    ev = a.get(f"/api/contracts/{cid}/events").json()
    assert ev["events"][-1]["event_type"] == "DOCUMENT_PURGED" and ev["chain_valid"]
    # 확인서는 원문 없이도 발급 가능
    assert a.get(f"/api/contracts/{cid}/pdf/certificate").status_code == 200


def test_retention_policy_per_type(client_factory, db):
    from app.services import retention

    assert retention.policy_for("employment")["allow_extended_retention"] is True
    assert retention.policy_for("loan")["post_completion_ttl_days"] == 7
    assert retention.policy_for("unknown-type")["post_completion_ttl_days"] == 7


def test_employment_extended_retention(client_factory, db):
    a, _, cid = complete_contract(client_factory)
    c = db.get(Contract, cid)
    # 금전소비대차는 연장 불가
    assert a.post(f"/api/contracts/{cid}/retention/extend").status_code == 409
    c.contract_type = "employment"
    db.commit()
    r = a.post(f"/api/contracts/{cid}/retention/extend")
    assert r.status_code == 200
    db.refresh(c)
    assert (c.purge_at - c.completed_at).days == 1095 and c.keep_encrypted_original


def test_draft_expires_after_draft_ttl(client_factory, db):
    from app.services import retention
    from tests.conftest import create_text_contract

    a = client_factory()
    a.login("hong")
    cid, _ = create_text_contract(a)
    retention.run_retention(db, now=datetime.now(timezone.utc) + timedelta(days=31))
    v = a.get(f"/api/contracts/{cid}").json()
    assert v["status"] == "EXPIRED" and v["purged"]
