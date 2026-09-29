"""로그 개인정보 마스킹.

요청 본문은 절대 로그에 남기지 않는다. 그래도 메시지에 섞여 들어올 수 있는 패턴(전화번호,
이메일, 주민등록번호, 카드번호)은 필터에서 가린다.
"""
from __future__ import annotations

import logging
import re

PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b\d{6}\s*-\s*[1-8]\d{6}\b"), "[RRN]"),
    (re.compile(r"\b(?:\d{4}[- ]?){3}\d{4}\b"), "[CARD]"),
    (re.compile(r"\b01[016789][- ]?\d{3,4}[- ]?\d{4}\b"), "[PHONE]"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[EMAIL]"),
    (re.compile(r"(/invites?/)[A-Za-z0-9_-]{8,}"), r"\1[TOKEN]"),
]


def mask_pii(text: str) -> str:
    for pattern, repl in PII_PATTERNS:
        text = pattern.sub(repl, text)
    return text


class PIIMaskingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = mask_pii(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(mask_pii(a) if isinstance(a, str) else a for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: mask_pii(v) if isinstance(v, str) else v for k, v in record.args.items()}
        return True


def setup_logging() -> None:
    root = logging.getLogger()
    if any(isinstance(f, PIIMaskingFilter) for h in root.handlers for f in h.filters):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(PIIMaskingFilter())
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        for h in logging.getLogger(name).handlers:
            h.addFilter(PIIMaskingFilter())


def mask_name(name: str) -> str:
    """홍길동 → 홍*동, 김철 → 김*, 한 글자 → *"""
    name = (name or "").strip()
    if len(name) <= 1:
        return "*"
    if len(name) == 2:
        return name[0] + "*"
    return name[0] + "*" * (len(name) - 2) + name[-1]
