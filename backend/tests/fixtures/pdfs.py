"""테스트용 PDF 생성기 — 텍스트 PDF(밑줄 빈칸 포함)와 스캔 이미지 PDF(OCR 용)."""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.services.pdf_engine import html_to_pdf

FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
]

TEXT_PDF_HTML = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>
@page { size: A4; margin: 20mm; } body { font-family: "Noto Sans CJK KR", sans-serif; font-size: 12pt; line-height: 2.2; }
h1 { text-align: center; font-size: 20pt; }</style></head><body>
<h1>용역계약서</h1>
<div>발주자: ______________</div>
<div>수행자: ______________</div>
<div>용역 대금: ______________ 원</div>
<div>연락처: ______________</div>
<div>제1조 본 계약은 발주자와 수행자가 성실히 이행한다.</div>
</body></html>"""


def text_pdf() -> bytes:
    return html_to_pdf(TEXT_PDF_HTML)


def scanned_pdf() -> bytes:
    font_path = next((p for p in FONT_CANDIDATES if Path(p).exists()), None)
    font = ImageFont.truetype(font_path, 44) if font_path else ImageFont.load_default()
    img = Image.new("RGB", (1240, 1754), "white")
    d = ImageDraw.Draw(img)
    lines = ["물품거래계약서", "", "매도인: ____________", "매수인: ____________", "총 거래대금: ____________ 원", "인도일: ____년 __월 __일"]
    y = 150
    for ln in lines:
        d.text((120, y), ln, fill="black", font=font)
        y += 90
    buf = io.BytesIO()
    img.save(buf, format="PDF", resolution=150)
    return buf.getvalue()


def fake_pdf() -> bytes:
    """확장자만 PDF 인 PNG 파일 (위조)."""
    img = Image.new("RGB", (10, 10), "white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def write_samples(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "sample-text-contract.pdf").write_bytes(text_pdf())
    (out / "sample-scanned-contract.pdf").write_bytes(scanned_pdf())
