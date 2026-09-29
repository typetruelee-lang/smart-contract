# 계약하자 API / 워커 이미지
# Playwright 공식 이미지(Chromium 포함) 위에 한글 폰트 + Tesseract(한국어) 를 설치한다.
FROM mcr.microsoft.com/playwright/python:v1.56.0-noble

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 DEBIAN_FRONTEND=noninteractive
# (선택) 회사/클라우드 프록시가 TLS 를 검사하는 환경이면 EXTRA_CA_CERT 로 CA 를 넘긴다 (docker-compose.yml 참고).
# 인증서를 넘기지 않으면 아무 영향이 없고, TLS 검증은 항상 켜져 있다.
RUN --mount=type=secret,id=extra_ca \
    if [ -s /run/secrets/extra_ca ]; then cp /run/secrets/extra_ca /usr/local/share/ca-certificates/extra-ca.crt && update-ca-certificates; fi; \
    apt-get update \
 && apt-get install -y --no-install-recommends fonts-noto-cjk tesseract-ocr tesseract-ocr-kor \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN --mount=type=secret,id=extra_ca \
    if [ -s /run/secrets/extra_ca ]; then export PIP_CERT=/run/secrets/extra_ca; fi; \
    pip install --break-system-packages -r requirements.txt

COPY backend/ ./
COPY contracts/artifacts /app/contracts/artifacts
RUN chmod +x docker-entrypoint.sh && useradd -m -u 10001 app && mkdir -p /data && chown -R app /app /data
USER app

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["api"]
