"""MerkleService — 여러 계약 Hash 를 하나의 Root 로 묶는 확장 기능.

MVP 기본값은 ANCHOR_MODE=single (계약 1건 = TX 1건). merkle 모드는 비용 분석 후 활성화한다.

규칙 (sorted-pair SHA-256):
- 잎(leaf) = 계약 문서 SHA-256 (32바이트)
- 부모 = SHA256(min(a,b) || max(a,b))  → 증명에 좌/우 정보가 필요 없다
- 홀수 개인 층에서는 마지막 노드를 그대로 위로 올린다
"""
from __future__ import annotations

import hashlib

from app.services.hashing import normalize_hash


def _pair(a: bytes, b: bytes) -> bytes:
    lo, hi = (a, b) if a <= b else (b, a)
    return hashlib.sha256(lo + hi).digest()


class MerkleTree:
    def __init__(self, hashes: list[str]):
        if not hashes:
            raise ValueError("Merkle Tree 에는 최소 1개의 Hash 가 필요해요.")
        leaves = sorted({normalize_hash(h) for h in hashes})
        self.leaves: list[bytes] = [bytes.fromhex(h) for h in leaves]
        self.levels: list[list[bytes]] = [self.leaves]
        level = self.leaves
        while len(level) > 1:
            nxt = []
            for i in range(0, len(level), 2):
                if i + 1 < len(level):
                    nxt.append(_pair(level[i], level[i + 1]))
                else:
                    nxt.append(level[i])
            self.levels.append(nxt)
            level = nxt

    def get_root(self) -> str:
        return self.levels[-1][0].hex()

    def get_proof(self, h: str) -> list[str]:
        leaf = bytes.fromhex(normalize_hash(h))
        try:
            idx = self.levels[0].index(leaf)
        except ValueError as e:
            raise ValueError("Tree 에 없는 Hash 예요.") from e
        proof: list[str] = []
        for level in self.levels[:-1]:
            sib = idx ^ 1
            if sib < len(level):
                proof.append(level[sib].hex())
            idx //= 2
        return proof


class MerkleService:
    """지시서 인터페이스: createTree / getRoot / getProof / verifyProof"""

    @staticmethod
    def create_tree(hashes: list[str]) -> MerkleTree:
        return MerkleTree(hashes)

    @staticmethod
    def get_root(tree: MerkleTree) -> str:
        return tree.get_root()

    @staticmethod
    def get_proof(tree: MerkleTree, h: str) -> list[str]:
        return tree.get_proof(h)

    @staticmethod
    def verify_proof(h: str, proof: list[str], root: str) -> bool:
        try:
            cur = bytes.fromhex(normalize_hash(h))
            for p in proof:
                cur = _pair(cur, bytes.fromhex(normalize_hash(p)))
            return cur.hex() == normalize_hash(root)
        except ValueError:
            return False
