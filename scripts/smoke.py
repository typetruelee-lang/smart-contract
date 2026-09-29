"""실행 중인 서버에 대한 스모크 테스트 (기본: http://localhost:5173).

두 테스트 계정으로 템플릿 계약 → 입력 → 초대 → 본인확인 → 서명 → 완료 → PDF → 결제 → 블록체인 기록 → 검증.
사용: python3 scripts/smoke.py [BASE_URL]   (개발 환경 전용 — mock 로그인 사용)
"""
import base64
import hashlib
import struct
import sys
import zlib

import httpx

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5173").rstrip("/")


def png() -> str:
    """외부 라이브러리 없이 만드는 간단한 서명 PNG (지그재그 선)."""
    w, h = 120, 40
    rows = []
    for y in range(h):
        row = bytearray(b"\x00")
        for x in range(w):
            on = abs((x % 20) - 10) + 10 == y
            row += b"\x00\x00\x00" if on else b"\xff\xff\xff"
        rows.append(bytes(row))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b"")
    return "data:image/png;base64," + base64.b64encode(data).decode()


def client(who):
    c = httpx.Client(base_url=BASE, timeout=60)
    r = c.post("/api/auth/mock-login", json={"test_user": who})
    r.raise_for_status()
    c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    return c


def ok(r):
    if r.status_code >= 400:
        raise SystemExit(f"FAIL {r.request.method} {r.request.url.path} {r.status_code} {r.text[:200]}")
    return r.json() if r.headers.get("content-type", "").startswith("application/json") else r


def sign(c, cid):
    v = ok(c.get(f"/api/contracts/{cid}"))
    s = ok(c.post(f"/api/contracts/{cid}/identity/start"))
    ok(c.post(f"/api/contracts/{cid}/identity/complete", json={"session_id": s["session_id"]}))
    ok(c.post(f"/api/contracts/{cid}/review", json={"version_no": v["current_version_no"], "content_checked": True, "own_will": True, "e_signature_consent": True}))
    st = ok(c.post(f"/api/contracts/{cid}/sign/start"))
    return ok(c.post(f"/api/contracts/{cid}/sign/complete", json={"request_id": st["request_id"], "version_no": st["version_no"], "signature_image": png()}))


a, b = client("hong"), client("kim")
t = ok(a.get("/api/templates/loan"))
cid = ok(a.post("/api/contracts", json={"title": t["title"], "source": "TEMPLATE", "contract_type": "loan", "body_text": t["body"], "fields": t["fields"]}))["id"]
fields = ok(a.get(f"/api/contracts/{cid}"))["payload"]["fields"]
val = {"TEXT": "홍길동", "NUMBER": "1000000", "DATE": "2027-12-31", "PHONE": "010-1111-2222", "SELECT": None, "LONG_TEXT": "없음"}
ok(a.put(f"/api/contracts/{cid}/values", json={"values": {f["field_id"]: (f["options"][0] if f["type"] == "SELECT" else val[f["type"]]) for f in fields if f["assignee"] == "A" and f["type"] != "SIGNATURE"}}))
tok = ok(a.post(f"/api/contracts/{cid}/invite"))["invite_token"]
ok(b.post(f"/api/invites/{tok}/accept"))
ok(b.put(f"/api/contracts/{cid}/values", json={"values": {f["field_id"]: ("김철수" if f["type"] == "TEXT" else "010-3333-4444") for f in fields if f["assignee"] == "B" and f["type"] != "SIGNATURE"}}))
sign(b, cid)
assert sign(a, cid)["completed"], "계약 완료 실패"
view = ok(a.get(f"/api/contracts/{cid}"))
pdf = ok(a.get(f"/api/contracts/{cid}/pdf/contract")).content
assert hashlib.sha256(pdf).hexdigest() == view["document_hash"]
print("✓ 계약 완료 · PDF", len(pdf), "bytes · 지문", view["document_hash"][:16], "· 검증번호", view["verification_id"])
co = ok(a.post(f"/api/contracts/{cid}/anchor/checkout"))
r = ok(a.post(f"/api/contracts/{cid}/anchor/confirm", json={"payment_id": co["payment_id"], "result": "success"}))
an = ok(a.get(f"/api/contracts/{cid}/anchor"))["anchor"]
print("✓ 결제", r["payment_status"], "· 기록", an["status"], "· 네트워크", an["network"], "· TX", an["tx_id"])
v = ok(httpx.post(BASE + "/api/verify/check", json={"verification_id": view["verification_id"], "document_hash": hashlib.sha256(pdf).hexdigest()}))
bad = ok(httpx.post(BASE + "/api/verify/check", json={"verification_id": view["verification_id"], "document_hash": hashlib.sha256(pdf + b"x").hexdigest()}))
print("✓ 원본 검증", v["match"], "· 온체인", v["onchain"], "· 수정본 검증", bad["match"])
cert = ok(a.get(f"/api/contracts/{cid}/pdf/certificate")).content
print("✓ 전자계약 확인서", len(cert), "bytes")
assert an["status"] == "CONFIRMED" and v["match"] and not bad["match"]
print("SMOKE PASS")
