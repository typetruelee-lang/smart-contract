# 프로젝트 환경 조사 (PHASE 0)

조사 일시: 2026-09-29 · 조사 위치: 클라우드 개발 컨테이너 (Claude Code on the web)

## 개발 컨테이너

| 항목 | 결과 |
|---|---|
| OS | Linux 6.18 (Ubuntu 24.04 계열) · 4 vCPU · 메모리 15GB · 여유 디스크 약 30GB |
| Node.js / npm | v22.22.2 / 10.9.7 |
| Python / pip | 3.11.15 / 24.0 |
| Docker | 29.3.1 (데몬은 직접 시작해야 했음 — `dockerd`) |
| Git | 2.43.0 |
| PostgreSQL | 16.13 (서비스 중지 상태였음 → 시작) |
| Redis | 7.0.15 (서비스 중지 상태였음 → 시작) |
| 브라우저 | Chromium (Playwright 1.56 / chromium-1194) — E2E·PDF 생성에 사용 |
| OCR | Tesseract 없음 → `tesseract-ocr` `tesseract-ocr-kor` 설치 |
| 한글 폰트 | 없음 → `fonts-noto-cjk` 설치 (PDF 한글 렌더링) |
| 사용 포트 | 5173(웹 개발), 8000(API 개발), 5180/8100(E2E 전용), 8545(로컬 체인), 5432, 6379 |
| 작업 폴더 | `/home/user/smart-contract` (Git 저장소 `typetruelee-lang/smart-contract`) |
| 기존 프로젝트 | **없음** (커밋 0개의 빈 저장소) → 재사용·백업할 코드 없음, 전부 새로 작성 |

## 네트워크 제약 (이 컨테이너에만 해당)

| 대상 | 결과 | 대응 |
|---|---|---|
| npm / PyPI | 사용 가능 | — |
| developers-apps-in-toss.toss.im | 차단 | 웹 검색 결과 + 공식 SDK 패키지(`@apps-in-toss/web-framework`)의 타입 정의로 확인 |
| binaries.soliditylang.org (Solidity 컴파일러 다운로드) | 차단 | npm `solc`(solc-js) 로 컴파일 → `contracts/artifacts/` 에 결과 커밋 |
| cdn.playwright.dev | 차단 | 설치된 Chromium 사용, Docker 는 `mcr.microsoft.com/playwright/python` 이미지 사용 |
| Docker Hub | 익명 다운로드 한도(429) | `mirror.gcr.io` 미러에서 같은 이미지를 받아 태그 |
| 컨테이너 내부 TLS | 프록시 인증서 필요 | `EXTRA_CA_CERT` 빌드 secret (선택 사항, 일반 PC 에서는 불필요) |

위 제약은 사용자 PC 에서는 발생하지 않는다. `docker compose up --build` 는 일반 인터넷 환경에서 그대로 동작한다.

## 선택한 기술 스택

- Frontend: React 18 + TypeScript + Vite 6 + Tailwind CSS 4, pdf.js(PDF 표시), 앱인토스 SDK `@apps-in-toss/web-framework` 3.6.0
- Backend: Python 3.11 · FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL 16 · Redis 7
- PDF: Chromium(Playwright) HTML→PDF + Noto Sans CJK, pypdf/pdfplumber(추출·병합), pypdfium2(OCR용 렌더링)
- OCR: Tesseract(kor) + 외부 OCR adapter 2종
- 블록체인: Solidity `DocumentRegistry` + web3.py (로컬 Hardhat / 테스트넷 / 메인넷 공용 adapter), Mock 원장
- 테스트: pytest · Vitest · Playwright
