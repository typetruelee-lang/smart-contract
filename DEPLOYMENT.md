# 운영 배포 가이드

## 구성도

```
[토스 앱] ─ 앱인토스 번들(.ait, 토스가 호스팅)
     │  HTTPS + Bearer 토큰
     ▼
[API 서버: backend 이미지, api]  ── PostgreSQL (관리형)
[워커:   backend 이미지, worker] ── Redis (관리형)
     │                             └─ Secret Manager (JWT·암호화 키·지갑 키)
     ├─ 토스 로그인 / 인앱결제 API (mTLS)
     ├─ 토스인증 (본인확인·전자서명)
     └─ 블록체인 RPC (EVM) — DocumentRegistry 컨트랙트
[웹: frontend 이미지(nginx)] — 공개 검증 페이지 /verify, QR 링크 대상
```

## 1. 이미지 빌드

```bash
docker build -f backend/Dockerfile -t <registry>/kyeyakhaja-backend:<tag> .
docker build -f frontend/Dockerfile -t <registry>/kyeyakhaja-web:<tag> .
```

- 같은 backend 이미지를 두 가지로 실행합니다. 명령 `api`는 마이그레이션 후 API 서버를 띄우고, 명령 `worker`는 블록체인 재시도와 보존정책 삭제를 담당합니다.
- 워커는 반드시 **1개 이상** 실행합니다. 여러 개를 띄워도 DB 행 잠금과 멱등성(같은 Hash 는 한 번만 기록)으로 중복 기록을 막습니다.

## 2. 운영 환경 변수 (Secret Manager 권장)

```env
APP_ENV=production
PUBLIC_BASE_URL=https://www.<도메인>          # 검증 QR / 초대 링크
CORS_ORIGINS=https://www.<도메인>,<토스 WebView 출처>
DATABASE_URL=postgresql+psycopg://...
REDIS_URL=rediss://...
JWT_SECRET=<48자 이상 난수>
COOKIE_SECURE=true
ADMIN_TOKEN=<난수>
KEY_PROVIDER=secret_manager
SECRET_MANAGER_BACKEND=aws|gcp
SECRET_MANAGER_KEY_ID=<KEK 시크릿 ID>
DATA_ENCRYPTION_KEY_VERSION=v1
TOSS_PROVIDER=production  (+ mTLS 인증서 경로, 복호화 키)
PAYMENT_PROVIDER=production  TOSS_IAP_SKU_BLOCKCHAIN=...
IDENTITY_PROVIDER=production SIGNATURE_PROVIDER=production TOSS_CERT_CLIENT_ID=... TOSS_CERT_CLIENT_SECRET=...
BLOCKCHAIN_PROVIDER=evm BLOCKCHAIN_NETWORK=<이름> BLOCKCHAIN_RPC_URL=... BLOCKCHAIN_PRIVATE_KEY=<Secret Manager> BLOCKCHAIN_CONTRACT_ADDRESS=0x...
BLOCKCHAIN_EXPLORER_TX_URL=https://<탐색기>/tx
BLOCKCHAIN_CONFIRMATIONS=2
```

운영 모드에서는 다음 경우에 **서버가 시작하지 않거나 해당 기능이 오류**를 냅니다(실수 방지).
- env 키를 사용하는 경우
- 필요한 키 없이 Mock으로 대체되려는 경우
- 개인키 없이 체인에 기록하려는 경우

## 3. 스마트컨트랙트 배포 (1회)

1. `contracts/artifacts/DocumentRegistry.json`(ABI·바이트코드)을 운영 지갑으로 배포합니다.
   - 예: 로컬에서 `BLOCKCHAIN_PROVIDER=evm`, `APP_ENV=development`, 운영 RPC와 키를 넣고 `EvmBlockchainProvider.deploy()`를 한 번 호출합니다. 또는 선호하는 배포 도구를 씁니다.
2. 나온 주소를 `BLOCKCHAIN_CONTRACT_ADDRESS`에 넣습니다.
3. 컨트랙트 `owner`만 기록할 수 있습니다(`register`). 운영 지갑 키가 유출되면 새 컨트랙트를 배포하고 주소를 바꿉니다.

## 4. 앱인토스 번들

`TOSS_SUBMISSION_CHECKLIST.md`를 참고하세요. 요약하면 `frontend/.env.toss` → `make ait` → `npx ait deploy --api-key ...` 순서입니다.

## 5. 배포 후 확인

1. `https://<도메인>/admin?token=<ADMIN_TOKEN>` → **PRODUCTION: READY**와 보안 경고 0건을 확인합니다.
2. 개발 전용 로그인이 막혔는지 확인합니다: `python3 scripts/smoke.py https://<도메인>`는 운영에서 404로 실패하는 것이 정상입니다.
3. 실제 계정 2개로 수동 스모크 테스트를 합니다(`RELEASE_CHECKLIST.md` B).

## 6. 운영 · 롤백

- **DB 마이그레이션:** `alembic upgrade head`(api 시작 시 자동). 롤백은 이전 이미지 태그로 되돌리고 필요하면 `alembic downgrade -1`.
- **모니터링 항목:** 5xx 비율, `anchor_jobs` 상태별 개수(`/admin`), 운영 지갑 잔액, 워커 로그의 `worker tick failed`.
- **키 교체:** 새 KEK를 `v2`로 등록 → `DATA_ENCRYPTION_KEY_VERSION=v2`. 기존 문서는 저장된 `key_version`으로 계속 복호화됩니다. 원문 보관 기간이 짧아서 재암호화 작업은 대부분 필요하지 않습니다.
- **Merkle 모드 전환:** 계약량이 많아 가스비가 부담되면 `ANCHOR_MODE=merkle`로 바꿉니다. 워커가 대기 중인 Hash를 모아 Root 1건으로 기록합니다. 구현과 테스트는 완료되어 있습니다.
- **OpenTimestamps**를 고르면 `providers/blockchain.py`의 `OpenTimestampsProvider`를 구현해야 합니다(calendar 서버에 제출하고 증명을 업그레이드하는 작업).
