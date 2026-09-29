"""개발자용 Admin 대시보드 API + 개발 전용 장애 주입."""
from __future__ import annotations

import hmac
import json
import os
import shutil
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.rate_limit import limiter
from app.models import AnchorJob, Contract, DevFault
from app.providers import (
    get_blockchain,
    get_identity,
    get_ocr,
    get_payment,
    get_signature,
    get_toss_login,
    keys,
)
from app.providers.base import PROVIDER_STATUS
from app.services import anchoring, retention
from app.services.hashing import sha256_bytes

router = APIRouter(prefix="/api")


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    s = get_settings()
    if s.is_production:
        if not s.ADMIN_TOKEN or not x_admin_token or not hmac.compare_digest(s.ADMIN_TOKEN, x_admin_token):
            raise HTTPException(404)


def require_dev() -> None:
    if get_settings().is_production:
        raise HTTPException(404)


def _check(fn) -> dict:
    t = time.perf_counter()
    try:
        detail = fn()
        return {"ok": True, "detail": detail, "ms": round((time.perf_counter() - t) * 1000)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detail": f"{type(e).__name__}: {str(e)[:160]}", "ms": round((time.perf_counter() - t) * 1000)}


def security_warnings() -> list[str]:
    s = get_settings()
    w = []
    if len(s.JWT_SECRET) < 32:
        w.append("JWT_SECRET 이 32자 미만입니다.")
    if s.is_production:
        if not s.COOKIE_SECURE:
            w.append("운영 환경에서 COOKIE_SECURE=true 가 필요합니다.")
        if s.KEY_PROVIDER != "secret_manager":
            w.append("운영 환경에서 KEY_PROVIDER=secret_manager 가 필요합니다.")
        if not s.PUBLIC_BASE_URL.startswith("https://"):
            w.append("운영 PUBLIC_BASE_URL 은 https 여야 합니다.")
        if not s.ADMIN_TOKEN:
            w.append("운영 ADMIN_TOKEN 이 필요합니다.")
    root = Path(__file__).resolve().parents[3]
    for f in (".env", ".env.local"):
        p = root / f
        if p.exists() and (p.stat().st_mode & 0o077):
            w.append(f"{f} 파일 권한이 너무 넓습니다 (chmod 600 권장).")
    return w


def test_results() -> dict | None:
    p = Path(get_settings().TEST_RESULTS_PATH)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except ValueError:
        return None


@router.get("/admin/status", dependencies=[Depends(require_admin)])
def status(db: Session = Depends(get_db)):
    s = get_settings()

    def db_check():
        db.execute(text("select 1"))
        return f"PostgreSQL · 계약 {db.scalar(select(func.count()).select_from(Contract))}건"

    def pdf_check():
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            exe = pw.chromium.executable_path
        return f"Chromium: {'OK' if os.path.exists(s.PDF_BROWSER_EXECUTABLE or exe) else 'missing'} · 한글폰트: {'OK' if shutil.which('fc-list') else '?'}"

    def hash_check():
        assert sha256_bytes(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        return "SHA-256 self-test OK"

    def bc_check():
        st = get_blockchain(db).get_network_status()
        db.commit()
        if not st.get("ok"):
            raise RuntimeError(json.dumps(st, ensure_ascii=False))
        return st

    def ocr_check():
        p = get_ocr()
        if p.name == "local" and not shutil.which("tesseract"):
            raise RuntimeError("tesseract 미설치")
        return p.name

    def key_check():
        kp = keys.get_key_provider()
        ct, w, v = keys.encrypt(b"ping")
        assert keys.decrypt(ct, w, v) == b"ping"
        return f"{kp.name} ({v})"

    components = {
        "Database": _check(db_check),
        "Backend": {"ok": True, "detail": f"FastAPI · {s.APP_ENV}", "ms": 0},
        "PDF Engine": _check(pdf_check),
        "Hash Engine": _check(hash_check),
        "Encryption Keys": _check(key_check),
        "Blockchain": _check(bc_check) if s.BLOCKCHAIN_ENABLED else {"ok": True, "detail": "비활성화 (BLOCKCHAIN_ENABLED=false)", "ms": 0},
        "Payment": _check(lambda: get_payment().name),
        "Signature": _check(lambda: get_signature().name),
        "Identity": _check(lambda: get_identity().name),
        "Toss Adapter": _check(lambda: get_toss_login().name),
        "OCR": _check(ocr_check),
        "Rate Limit": _check(lambda: limiter.backend),
    }
    anchors = dict(db.execute(select(AnchorJob.status, func.count()).group_by(AnchorJob.status)).all())
    tests = test_results()
    warnings = security_warnings()
    all_ok = all(c["ok"] for c in components.values())
    tests_ok = bool(tests) and tests.get("failed", 1) == 0 and tests.get("passed", 0) > 0 and tests.get("visual_review_ok", False) and tests.get("build_ok", False)
    mocks = {k: v for k, v in PROVIDER_STATUS.items() if v["active"] in ("mock", "local")}
    return {
        "environment": s.APP_ENV,
        "components": components,
        "providers": PROVIDER_STATUS,
        "anchor_jobs": anchors,
        "tests": tests,
        "security": {"warnings": warnings},
        "readiness": {
            "development_complete": all_ok and tests_ok,
            "production_ready": all_ok and tests_ok and not mocks and s.is_production and not warnings,
            "production_blockers": [f"{k}: mock/local 사용 중" for k in mocks] + ([] if s.is_production else ["APP_ENV != production"]) + warnings,
        },
        "config": {"blockchain_enabled": s.BLOCKCHAIN_ENABLED, "blockchain_price": s.BLOCKCHAIN_PRICE, "anchor_mode": s.ANCHOR_MODE,
                   "retention_policies": retention.load_policies()},
    }


@router.post("/admin/workers/run", dependencies=[Depends(require_admin)])
def run_workers(db: Session = Depends(get_db)):
    n = anchoring.run_due_jobs(db, force=True)
    merkle = anchoring.run_merkle_batch(db) if get_settings().ANCHOR_MODE == "merkle" else None
    purged = retention.run_retention(db)
    return {"anchor_jobs_processed": n, "merkle": merkle, "purged": purged}


class FaultIn(BaseModel):
    key: str = Field(pattern="^(blockchain_fail|payment_fail)$")
    value: int = Field(ge=0, le=100)


@router.post("/dev/faults", dependencies=[Depends(require_dev)])
def set_fault(body: FaultIn, db: Session = Depends(get_db)):
    f = db.get(DevFault, body.key)
    if f:
        f.value = body.value
    else:
        db.add(DevFault(key=body.key, value=body.value))
    db.commit()
    return {"key": body.key, "value": body.value}


@router.get("/dev/faults", dependencies=[Depends(require_dev)])
def get_faults(db: Session = Depends(get_db)):
    return {f.key: f.value for f in db.scalars(select(DevFault))}


@router.post("/dev/reset-rate-limit", dependencies=[Depends(require_dev)])
def reset_rl():
    limiter.reset()
    return {"ok": True}
