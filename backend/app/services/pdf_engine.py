"""PDF 엔진.

- HTML/CSS → PDF : Chromium(Playwright) + Noto Sans CJK(한글) — 외부 네트워크 요청은 모두 차단
- 업로드 PDF 검증 / 텍스트 추출 / OCR / 빈칸 위치 추천
- 업로드 PDF 위에 입력값·서명을 새겨 넣기(flatten) : 페이지 크기의 오버레이 PDF 를 만들어 pypdf 로 병합
"""
from __future__ import annotations

import base64
import io
import logging
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber
import qrcode
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

from app.core.config import get_settings
from app.services.fields import FieldSpec, display_value, infer_type

log = logging.getLogger(__name__)
TEMPLATES = Path(__file__).resolve().parents[1] / "templates"
_jinja = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html"]))
KST_OFFSET_HOURS = 9


def fmt_kst(dt: datetime | None) -> str:
    if dt is None:
        return "-"
    from datetime import timedelta

    k = dt.astimezone(timezone.utc) + timedelta(hours=KST_OFFSET_HOURS)
    return k.strftime("%Y-%m-%d %H:%M:%S") + " (KST)"


_jinja.filters["kst"] = fmt_kst


def _chromium_path() -> str | None:
    p = get_settings().PDF_BROWSER_EXECUTABLE
    if p and os.path.exists(p):
        return p
    return None


class _PdfRenderer:
    """Chromium 을 한 번만 띄워 재사용하는 전용 스레드.

    Playwright sync API 객체는 만든 스레드에서만 쓸 수 있으므로, 요청 스레드(FastAPI threadpool)는
    큐에 작업을 넣고 결과를 기다린다. 브라우저가 죽으면 다음 작업에서 다시 띄운다.
    """

    def __init__(self) -> None:
        import queue

        self._q: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._start_lock = threading.Lock()

    def _ensure(self) -> None:
        with self._start_lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name="pdf-renderer", daemon=True)
                self._thread.start()

    def _launch(self, pw):
        kwargs: dict = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
        exe = _chromium_path()
        if exe:
            kwargs["executable_path"] = exe
        return pw.chromium.launch(**kwargs)

    def _run(self) -> None:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = None
            while True:
                html, opts, fut = self._q.get()
                try:
                    if browser is None or not browser.is_connected():
                        browser = self._launch(pw)
                    ctx = browser.new_context()
                    try:
                        page = ctx.new_page()
                        # 문서 렌더링 중 외부 요청 금지 (SSRF/추적 방지) — data: URI 만 허용
                        page.route("**/*", lambda route: route.abort() if not route.request.url.startswith("data:") else route.continue_())
                        page.set_content(html, wait_until="load")
                        fut.set_result(page.pdf(**opts))
                    finally:
                        ctx.close()
                except Exception as e:  # noqa: BLE001
                    fut.set_exception(e)
                    try:
                        if browser is not None:
                            browser.close()
                    except Exception:  # noqa: BLE001
                        pass
                    browser = None

    def render(self, html: str, opts: dict, timeout: float = 60) -> bytes:
        from concurrent.futures import Future

        self._ensure()
        fut: Future = Future()
        self._q.put((html, opts, fut))
        return fut.result(timeout=timeout)


_renderer = _PdfRenderer()


def html_to_pdf(html: str, *, width: str | None = None, height: str | None = None) -> bytes:
    opts: dict = {"print_background": True, "prefer_css_page_size": True}
    if width and height:
        opts.update(width=width, height=height)
    else:
        opts["format"] = "A4"
    return _renderer.render(html, opts)


def qr_data_uri(url: str) -> str:
    img = qrcode.make(url, box_size=6, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


# ---------------- 업로드 PDF ----------------

class UploadError(ValueError):
    pass


@dataclass
class PageInfo:
    width: float
    height: float
    text: str
    ocr: bool = False


@dataclass
class ExtractResult:
    pages: list[PageInfo]
    text: str
    ocr_used: bool
    position_suggestions: list[dict] = field(default_factory=list)


def validate_pdf_upload(data: bytes, filename: str, content_type: str | None) -> PdfReader:
    s = get_settings()
    if not filename or not filename.lower().endswith(".pdf"):
        raise UploadError("PDF 파일(.pdf)만 올릴 수 있어요.")
    if content_type not in ("application/pdf", "application/x-pdf"):
        raise UploadError("PDF 파일 형식이 아니에요.")
    if len(data) == 0:
        raise UploadError("빈 파일이에요.")
    if len(data) > s.MAX_UPLOAD_MB * 1024 * 1024:
        raise UploadError(f"파일이 너무 커요. {s.MAX_UPLOAD_MB}MB 이하로 올려 주세요.")
    if not data[:1024].lstrip().startswith(b"%PDF-"):
        raise UploadError("확장자만 PDF 이고 실제 PDF 파일이 아니에요.")
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            raise UploadError("암호가 걸린 PDF 는 올릴 수 없어요. 암호를 해제한 뒤 다시 올려 주세요.")
        n = len(reader.pages)
    except UploadError:
        raise
    except (PdfReadError, Exception) as e:  # noqa: BLE001
        raise UploadError("손상되었거나 읽을 수 없는 PDF 예요.") from e
    if n == 0:
        raise UploadError("페이지가 없는 PDF 예요.")
    if n > s.MAX_PDF_PAGES:
        raise UploadError(f"{s.MAX_PDF_PAGES}쪽 이하의 PDF 만 올릴 수 있어요.")
    return reader


_UNDERSCORE = re.compile(r"_{3,}")


def extract_pdf(data: bytes, ocr_provider=None) -> ExtractResult:
    pages: list[PageInfo] = []
    suggestions: list[dict] = []
    ocr_used = False
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            w, h = float(page.width), float(page.height)
            text = page.extract_text() or ""
            is_ocr = False
            if len(text.strip()) < 15:
                # 이미지(스캔) PDF → OCR
                if ocr_provider is not None:
                    text = _ocr_page(data, pno - 1, ocr_provider)
                    is_ocr = True
                    ocr_used = True
            else:
                suggestions.extend(_position_suggestions(page, pno, w, h))
            pages.append(PageInfo(width=w, height=h, text=text, ocr=is_ocr))
    full = "\n\n".join(p.text for p in pages)
    return ExtractResult(pages=pages, text=full, ocr_used=ocr_used, position_suggestions=suggestions)


def _ocr_page(data: bytes, index: int, ocr_provider) -> str:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(data)
    try:
        img = doc[index].render(scale=2.5).to_pil()
    finally:
        doc.close()
    return ocr_provider.image_to_text(img)


def _position_suggestions(page, pno: int, w: float, h: float) -> list[dict]:
    """텍스트 PDF 의 밑줄 빈칸(____) 위치를 찾아 PDF 필드 위치를 추천."""
    out = []
    words = page.extract_words(keep_blank_chars=False, use_text_flow=True)
    for i, wd in enumerate(words):
        m = _UNDERSCORE.search(wd["text"])
        if not m:
            continue
        # 같은 줄에서 앞 단어들로 라벨 추정
        line_words = [x for x in words[max(0, i - 6) : i] if abs(x["top"] - wd["top"]) < 3]
        before = " ".join(x["text"] for x in line_words)
        prefix = wd["text"][: m.start()]
        line_text = (before + " " + prefix).strip()
        from app.services.fields import _label_before

        label, _ = _label_before(line_text, len(line_text))
        label = label.strip(":： ")[:40] or "빈칸"
        x0 = wd["x0"] + (wd["x1"] - wd["x0"]) * (m.start() / max(len(wd["text"]), 1))
        x1 = wd["x0"] + (wd["x1"] - wd["x0"]) * (m.end() / max(len(wd["text"]), 1))
        top = max(wd["top"] - 6, 0)
        bottom = min(wd["bottom"] + 2, h)
        out.append({
            "label": label, "type": infer_type(label, wd["text"][m.end():]), "page": pno,
            "position": {"x": round(x0 / w, 4), "y": round(top / h, 4), "w": round(max(x1 - x0, 20) / w, 4), "h": round(max(bottom - top, 14) / h, 4)},
            "confidence": 0.7, "reason": "PDF 의 밑줄 위치를 찾아 추천했어요.",
        })
    return out


def page_sizes(data: bytes) -> list[dict]:
    reader = PdfReader(io.BytesIO(data), strict=False)
    return [{"width": float(p.mediabox.width), "height": float(p.mediabox.height)} for p in reader.pages]


# ---------------- 최종 계약서 PDF ----------------

@dataclass
class PartySign:
    role: str
    role_label: str
    name_masked: str
    identity_status: str
    identity_verified_at: datetime | None
    signed_at: datetime | None
    signature_ref: str | None
    signature_image: str | None  # data URI
    provider: str | None


def _render_body(body_text: str, fields: list[FieldSpec], sig_images: dict[str, str]) -> list[dict]:
    """본문을 [{kind:text|value|signature|empty, text}] 조각으로 나눈다 (Jinja 에서 이스케이프)."""
    by_label = {f.label: f for f in fields}
    parts: list[dict] = []
    pos = 0
    for m in re.finditer(r"\{([^{}\n]{1,40})\}", body_text):
        parts.append({"kind": "text", "text": body_text[pos : m.start()]})
        f = by_label.get(m.group(1).strip())
        if f is None:
            parts.append({"kind": "text", "text": m.group(0)})
        elif f.type == "SIGNATURE":
            img = sig_images.get(str(f.value)) if f.value else None
            parts.append({"kind": "signature", "src": img, "text": f.label})
        else:
            v = display_value(f)
            parts.append({"kind": "value" if v else "empty", "text": v or "(미입력)", "long": f.type == "LONG_TEXT"})
        pos = m.end()
    parts.append({"kind": "text", "text": body_text[pos:]})
    return parts


def render_contract_pdf(
    *, contract_no: str, title: str, source: str, body_text: str | None, fields: list[FieldSpec],
    parties: list[PartySign], version_no: int, content_hash: str, completed_at: datetime,
    source_pdf: bytes | None, sig_images: dict[str, str],
) -> bytes:
    """완성 계약서 PDF. 계약서 자신의 Hash 는 넣을 수 없으므로 '내용 지문(content_hash)'과 서명정보만 포함."""
    sign_html = _jinja.get_template("signature_page.html").render(
        contract_no=contract_no, title=title, parties=parties, version_no=version_no,
        content_hash=content_hash, completed_at=completed_at,
    )
    if source == "PDF" and source_pdf:
        return _flatten_pdf(source_pdf, fields, sig_images, sign_html)
    body = body_text or ""
    first, _, rest = body.lstrip("\n").partition("\n")
    if first.strip() == title.strip():
        body = rest.lstrip("\n")  # 본문 첫 줄이 제목과 같으면 중복 표시하지 않음
    html = _jinja.get_template("contract.html").render(
        contract_no=contract_no, title=title, parts=_render_body(body, fields, sig_images),
        sign_html=sign_html,
    )
    return html_to_pdf(html)


def _flatten_pdf(source_pdf: bytes, fields: list[FieldSpec], sig_images: dict[str, str], sign_html: str) -> bytes:
    reader = PdfReader(io.BytesIO(source_pdf), strict=False)
    writer = PdfWriter()
    for idx, page in enumerate(reader.pages, start=1):
        w, h = float(page.mediabox.width), float(page.mediabox.height)
        page_fields = [f for f in fields if f.page == idx and f.position is not None]
        if page_fields:
            items = []
            for f in page_fields:
                p = f.position
                assert p is not None
                item = {"x": p.x * 100, "y": p.y * 100, "w": p.w * 100, "h": p.h * 100, "type": f.type}
                if f.type == "SIGNATURE":
                    item["src"] = sig_images.get(str(f.value)) if f.value else None
                else:
                    item["text"] = display_value(f)
                    item["size"] = max(min(p.h * h * 0.62, 14), 7)
                items.append(item)
            overlay_html = _jinja.get_template("overlay.html").render(w=w, h=h, items=items)
            overlay = PdfReader(io.BytesIO(html_to_pdf(overlay_html, width=f"{w / 72:.5f}in", height=f"{h / 72:.5f}in")))
            page.merge_page(overlay.pages[0])
        writer.add_page(page)
    sign_pdf = PdfReader(io.BytesIO(html_to_pdf(_jinja.get_template("standalone.html").render(body=sign_html))))
    for p in sign_pdf.pages:
        writer.add_page(p)
    writer.add_metadata({"/Producer": "KyeyakHaja PDF Engine", "/Title": "계약서"})
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def render_certificate_pdf(ctx: dict) -> bytes:
    ctx = dict(ctx)
    ctx["qr"] = qr_data_uri(ctx["verify_url"])
    return html_to_pdf(_jinja.get_template("certificate.html").render(**ctx))
