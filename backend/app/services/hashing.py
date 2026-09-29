from __future__ import annotations

import hashlib
import json
import re
from typing import Any

HEX64 = re.compile(r"^[0-9a-f]{64}$")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def sha256_json(obj: Any) -> str:
    return sha256_bytes(canonical_json(obj))


def normalize_hash(value: str) -> str:
    v = (value or "").strip().lower()
    if v.startswith("0x"):
        v = v[2:]
    if not HEX64.match(v):
        raise ValueError("SHA-256 값은 64자리 16진수여야 해요.")
    return v


def short_hash(h: str | None) -> str:
    if not h:
        return ""
    return f"{h[:8].upper()}…{h[-8:].upper()}"
