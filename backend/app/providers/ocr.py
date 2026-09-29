"""OCR provider.

- local     : Tesseract(kor+eng) — 무료, 개발/테스트 기본값
- provider_a: 외부 OCR (예: CLOVA OCR 호환 General API) — URL/Secret 만 입력하면 동작
- provider_b: 외부 OCR (예: Google Vision 호환 REST) — API Key 만 입력하면 동작
"""
from __future__ import annotations

import base64
import io
from abc import ABC, abstractmethod

import httpx
from PIL import Image

from app.core.config import get_settings
from app.providers.base import ProviderError, ProviderNotConfigured


class OCRProvider(ABC):
    name = "base"

    @abstractmethod
    def image_to_text(self, image: Image.Image) -> str: ...


class LocalTesseractOCR(OCRProvider):
    name = "local"

    def image_to_text(self, image: Image.Image) -> str:
        import pytesseract

        try:
            return pytesseract.image_to_string(image, lang="kor+eng")
        except pytesseract.TesseractNotFoundError as e:
            raise ProviderNotConfigured("tesseract-ocr 와 tesseract-ocr-kor 설치가 필요해요.") from e


def _png_b64(image: Image.Image) -> str:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


class ProviderAOCR(OCRProvider):  # pragma: no cover - 외부 키 필요
    name = "provider_a"

    def __init__(self) -> None:
        s = get_settings()
        if not (s.OCR_PROVIDER_A_URL and s.OCR_PROVIDER_A_SECRET):
            raise ProviderNotConfigured("OCR_PROVIDER_A_URL / OCR_PROVIDER_A_SECRET 를 입력하세요.")
        self.url, self.secret = s.OCR_PROVIDER_A_URL, s.OCR_PROVIDER_A_SECRET

    def image_to_text(self, image: Image.Image) -> str:
        import time
        import uuid

        body = {"version": "V2", "requestId": str(uuid.uuid4()), "timestamp": int(time.time() * 1000), "lang": "ko",
                "images": [{"format": "png", "name": "page", "data": _png_b64(image)}]}
        r = httpx.post(self.url, json=body, headers={"X-OCR-SECRET": self.secret}, timeout=30)
        if r.status_code != 200:
            raise ProviderError(f"OCR 실패: {r.status_code}")
        lines = []
        for f in r.json()["images"][0].get("fields", []):
            lines.append(f["inferText"] + ("\n" if f.get("lineBreak") else " "))
        return "".join(lines)


class ProviderBOCR(OCRProvider):  # pragma: no cover - 외부 키 필요
    name = "provider_b"

    def __init__(self) -> None:
        key = get_settings().OCR_PROVIDER_B_API_KEY
        if not key:
            raise ProviderNotConfigured("OCR_PROVIDER_B_API_KEY 를 입력하세요.")
        self.key = key

    def image_to_text(self, image: Image.Image) -> str:
        r = httpx.post(
            f"https://vision.googleapis.com/v1/images:annotate?key={self.key}",
            json={"requests": [{"image": {"content": _png_b64(image)}, "features": [{"type": "DOCUMENT_TEXT_DETECTION"}]}]},
            timeout=30,
        )
        if r.status_code != 200:
            raise ProviderError(f"OCR 실패: {r.status_code}")
        return r.json()["responses"][0].get("fullTextAnnotation", {}).get("text", "")
