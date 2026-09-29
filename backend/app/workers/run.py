"""백그라운드 워커 — 블록체인 기록 재시도, Merkle 배치(확장), 보존정책 원문 삭제.

실행: python -m app.workers.run            (무한 루프, WORKER_INTERVAL_SECONDS 간격)
      python -m app.workers.run --once     (1회 실행 후 종료 — cron 용)
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import time

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.logging import setup_logging
from app.services import anchoring, retention

log = logging.getLogger("worker")
_stop = False


def _handle(*_):
    global _stop
    _stop = True


def tick() -> dict:
    db = SessionLocal()
    try:
        n = anchoring.run_due_jobs(db)
        merkle = anchoring.run_merkle_batch(db) if get_settings().ANCHOR_MODE == "merkle" else None
        purged = retention.run_retention(db)
        return {"anchor_jobs": n, "merkle": merkle, "purged": len(purged)}
    finally:
        db.close()


def main() -> None:
    setup_logging()
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()
    interval = int(os.environ.get("WORKER_INTERVAL_SECONDS", "10"))
    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)
    log.info("worker started (interval=%ss)", interval)
    while not _stop:
        try:
            r = tick()
            if r["anchor_jobs"] or r["merkle"] or r["purged"]:
                log.info("worker tick: %s", r)
        except Exception:  # noqa: BLE001
            log.exception("worker tick failed")
        if args.once:
            break
        for _ in range(interval):
            if _stop:
                break
            time.sleep(1)


if __name__ == "__main__":
    main()
