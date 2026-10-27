"""OpenTimestamps provider — 실제 .ots 직렬화 형식을 쓰는 가짜 calendar·블록 탐색기로 전 과정을 검증."""
import hashlib
import json

import httpx
import pytest
from opentimestamps.core.notary import BitcoinBlockHeaderAttestation, PendingAttestation
from opentimestamps.core.op import OpPrepend, OpSHA256
from opentimestamps.core.serialize import BytesDeserializationContext, BytesSerializationContext
from opentimestamps.core.timestamp import DetachedTimestampFile, Timestamp

from app.providers.base import ProviderError
from app.providers.ots import OpenTimestampsProvider

CAL = "https://a.pool.opentimestamps.org"
API = "https://blockstream.info/api"
HEIGHT = 870123


def _ser(ts):
    ctx = BytesSerializationContext()
    ts.serialize(ctx)
    return ctx.getbytes()


class FakeNet:
    """calendar: 제출 → pending 증명, mined 후 → 비트코인 증명. explorer: 머클 루트 제공."""

    def __init__(self):
        self.received, self.commitments, self.mined, self.down, self.calls = [], {}, False, False, []
        self.merkle_root = None

    def handler(self, req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        self.calls.append(url)
        if self.down:
            raise httpx.ConnectError("down")
        if req.method == "POST" and url == f"{CAL}/digest":
            msg = req.content
            self.received.append(msg)
            ts = Timestamp(msg)
            commit = ts.ops.add(OpPrepend(b"\x01" * 8)).ops.add(OpSHA256())
            commit.attestations.add(PendingAttestation(CAL))
            self.commitments[commit.msg.hex()] = commit.msg
            return httpx.Response(200, content=_ser(ts))
        if url.startswith(f"{CAL}/timestamp/"):
            c = self.commitments.get(url.rsplit("/", 1)[1])
            if c is None or not self.mined:
                return httpx.Response(404)
            ts = Timestamp(c)
            leaf = ts.ops.add(OpPrepend(b"\x02" * 32)).ops.add(OpSHA256())
            leaf.attestations.add(BitcoinBlockHeaderAttestation(HEIGHT))
            self.merkle_root = leaf.msg
            return httpx.Response(200, content=_ser(ts))
        if url == f"{API}/block-height/{HEIGHT}":
            return httpx.Response(200, text="00000000000000000001abcd")
        if url == f"{API}/block/00000000000000000001abcd":
            return httpx.Response(200, json={"id": "00000000000000000001abcd", "merkle_root": self.merkle_root[::-1].hex(), "timestamp": 1790000000})
        if url == f"{API}/blocks/tip/height":
            return httpx.Response(200, text=str(HEIGHT + 10))
        return httpx.Response(404)


@pytest.fixture
def net(monkeypatch):
    from app.core import config
    monkeypatch.setenv("OTS_CALENDARS", CAL)
    config.get_settings.cache_clear()
    yield FakeNet()
    config.get_settings.cache_clear()


def _prov(db, net):
    return OpenTimestampsProvider(db, client=httpx.Client(transport=httpx.MockTransport(net.handler)))


def test_ots_full_lifecycle(db, net):
    doc = hashlib.sha256(b"contract pdf bytes").hexdigest()
    p = _prov(db, net)
    r = p.register_document_hash(doc)
    assert r.status == "SUBMITTED" and r.tx_id == "ots:" + doc
    # 개인정보 보호: calendar 는 문서 Hash 자체를 받지 않는다 (nonce 로 한 번 더 해시한 값)
    assert net.received and net.received[0] != bytes.fromhex(doc)
    # 같은 Hash 재제출은 calendar 를 다시 부르지 않는다 (멱등)
    p.register_document_hash(doc)
    assert len(net.received) == 1
    # 비트코인 포함 전: 미확정
    info = p.get_transaction(r.tx_id)
    assert info.confirmed is False and p.verify_document_hash(doc) is None
    # 채굴 후: 업그레이드 → 확정 → 블록 머클 루트 대조
    net.mined = True
    info = p.get_transaction(r.tx_id)
    assert info.confirmed and info.block_number == HEIGHT
    rec = p.verify_document_hash(doc)
    assert rec is not None and rec.value == doc and rec.timestamp.year >= 2026
    # 대조 결과는 저장되어 블록 탐색기를 다시 부르지 않는다
    before = len(net.calls)
    assert p.verify_document_hash(doc) is not None and len(net.calls) == before
    # 내려받는 .ots 파일은 표준 형식이며 이 문서 Hash 에 대한 비트코인 증명을 담고 있다
    dtf = DetachedTimestampFile.deserialize(BytesDeserializationContext(p.proof_file(doc)))
    assert dtf.file_digest == bytes.fromhex(doc)
    assert any(isinstance(a, BitcoinBlockHeaderAttestation) and a.height == HEIGHT for _, a in dtf.timestamp.all_attestations())


def test_ots_wrong_merkle_root_is_not_verified(db, net):
    doc = hashlib.sha256(b"other").hexdigest()
    p = _prov(db, net)
    p.register_document_hash(doc)
    net.mined = True
    p.get_transaction("ots:" + doc)
    net.merkle_root = b"\x00" * 32  # 탐색기가 다른 머클 루트를 돌려주면 (위조 증명) 검증 실패
    assert p.verify_document_hash(doc) is None


def test_ots_all_calendars_down_raises_for_retry(db, net):
    net.down = True
    with pytest.raises(ProviderError):
        _prov(db, net).register_document_hash(hashlib.sha256(b"x").hexdigest())


def test_ots_upgrade_ignores_unknown_calendar_uri(db, net):
    """증명 안의 임의 주소(SSRF 시도)로는 요청하지 않는다."""
    doc = hashlib.sha256(b"ssrf").hexdigest()
    p = _prov(db, net)
    p.register_document_hash(doc)
    dtf, rec = p._load(doc)
    for sub in list(__import__("app.providers.ots", fromlist=["_walk"])._walk(dtf.timestamp)):
        if sub.attestations:
            sub.attestations.add(PendingAttestation("http://169.254.169.254"))
    p._save(doc, dtf)
    net.calls.clear()
    p.get_transaction("ots:" + doc)
    assert not any("169.254" in u for u in net.calls)


def test_ots_network_status(db, net):
    st = _prov(db, net).get_network_status()
    assert st["ok"] and st["bitcoin_tip"] == str(HEIGHT + 10)
