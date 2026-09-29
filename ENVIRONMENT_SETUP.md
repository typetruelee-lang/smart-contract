# 환경 설정 가이드

## 1. 내 컴퓨터에서 실행하기 (개발/확인용)

### 방법 A — Docker (권장)

준비물: [Docker Desktop](https://www.docker.com/products/docker-desktop/) 설치

```bash
git clone https://github.com/typetruelee-lang/smart-contract.git
cd smart-contract
git checkout claude/loving-clarke-wdc1k2
./start.sh              # Windows 는: docker compose up --build -d
```

- 처음에는 이미지를 받고 빌드하느라 5~10분 걸립니다.
- 끝나면 `✅ 준비 완료: http://localhost:5173` 이 표시됩니다.

| 주소 | 내용 |
|---|---|
| http://localhost:5173 | 서비스 (휴대폰 크기로 보려면 브라우저 개발자도구 → 모바일 보기) |
| http://localhost:5173/admin | 시스템 상태 대시보드 |
| http://localhost:5173/verify | 공개 검증 페이지 |

**테스트 계정** (토스 로그인 Mock — 로그인 화면에서 버튼으로 선택):

| 계정 | 역할 예시 |
|---|---|
| 홍길동 | 계약서를 만드는 사람 |
| 김철수 | 초대받는 상대방 |
| 이영희 | 제3자 (남의 계약에 접근할 수 없는지 확인) |

두 사람의 흐름을 확인하려면 **일반 창에서 홍길동**, **시크릿 창에서 김철수**로 로그인하세요. 홍길동이 받은 초대 링크를 시크릿 창에 붙여넣으면 됩니다.

체험용 PDF는 `samples/sample-text-contract.pdf`(텍스트 PDF)와 `samples/sample-scanned-contract.pdf`(스캔 PDF, OCR)입니다.

종료: `./start.sh stop`

> 회사망처럼 TLS 검사 프록시가 있는 곳에서 빌드가 인증서 오류로 실패하면, 회사 CA 인증서 경로를 `EXTRA_CA_CERT=/경로/ca.crt ./start.sh` 로 넘기세요. 일반 인터넷 환경에서는 필요 없습니다.

### 방법 B — Docker 없이 (개발자용)

준비물: Python 3.11, Node 22, PostgreSQL 16, Redis 7, (선택) Tesseract + 한국어 데이터, Noto CJK 폰트

```bash
./start.sh local      # 가상환경·패키지 설치 → DB 마이그레이션 → API·워커·웹 실행
make test             # 전체 테스트 → test-results/summary.json
```

## 2. 환경 변수

전체 목록과 설명은 `.env.example` 에 있습니다. **값이 비어 있는 외부 서비스는 자동으로 Mock 으로 동작합니다.** 단, `APP_ENV=production` 에서는 Mock으로 대체되지 않고 오류가 납니다.

| 구분 | 변수 | 개발 기본값 | 운영 |
|---|---|---|---|
| 기본 | `APP_ENV` | development | production |
| 보안 | `JWT_SECRET`, `DATA_ENCRYPTION_KEY` | start.sh / 컨테이너가 자동 생성 | Secret Manager |
| 키 관리 | `KEY_PROVIDER` | env | secret_manager |
| 토스 로그인 | `TOSS_PROVIDER` + mTLS 인증서 | mock | production |
| 결제 | `PAYMENT_PROVIDER`, `TOSS_IAP_SKU_BLOCKCHAIN`, `BLOCKCHAIN_PRICE` | mock, 990 | production |
| 본인확인/서명 | `IDENTITY_PROVIDER`, `SIGNATURE_PROVIDER`, `TOSS_CERT_*` | mock / development | production |
| OCR | `OCR_PROVIDER` | local | local / provider_a / provider_b |
| 블록체인 | `BLOCKCHAIN_ENABLED`, `BLOCKCHAIN_PROVIDER`, `BLOCKCHAIN_RPC_URL`, `BLOCKCHAIN_PRIVATE_KEY`, `BLOCKCHAIN_CONTRACT_ADDRESS` | mock (Docker 는 로컬 Hardhat) | evm + Secret Manager |
| 보존 정책 | `backend/retention_policies.yaml` | 완료 후 7일 | 법률 검토 후 조정 |

## 3. 앱인토스 번들용 (프론트엔드)

`frontend/.env.toss.example` 을 복사해 `frontend/.env.toss` 를 만들고 운영 API 주소를 넣은 뒤 `make ait` 를 실행합니다.

| 변수 | 의미 |
|---|---|
| `VITE_RUNTIME=toss` | 토스 런타임 (SDK 사용, Bearer 토큰 인증) |
| `VITE_API_BASE_URL` | 운영 API 주소 (https) |
| `VITE_AIT_APP_NAME` | 앱인토스 콘솔의 appName |

## 4. 자주 쓰는 명령

| 명령 | 설명 |
|---|---|
| `./start.sh` / `./start.sh stop` | Docker 전체 실행 / 종료 |
| `make test` | 전체 테스트 + 보안 점검 → `test-results/summary.json` |
| `make visual` | 화면 캡처 → `FINAL_REVIEW/` |
| `make ait` | 앱인토스 `.ait` 번들 빌드 |
| `python3 scripts/smoke.py http://localhost:5173` | 실행 중인 서버 스모크 테스트 |
| `docker compose logs -f backend worker` | 서버 로그 보기 |
