# 내가 해야 할 일 (컴퓨터가 대신할 수 없는 일만)

개발 작업은 모두 끝났습니다. 아래는 **계정, 계약, 법률, 사업자 정보처럼 당신 명의로만 할 수 있는 일**입니다.
위에서부터 순서대로 진행하면 됩니다. 값을 넣어야 하는 곳은 모두 `.env`(운영은 Secret Manager)이고, 코드를 고칠 필요는 없습니다.

---

## [ ] 1. 앱인토스 담당자에게 사전 문의 (가장 먼저)

- **무엇을:** 두 가지를 확인받습니다.
  - ① "계약서의 SHA-256 디지털 지문을 블록체인에 기록하는 유료 기능(자산·토큰·지갑 없음)"이 등록 가능한지
  - ② 이 기능의 결제를 인앱결제(IAP)로 받아야 하는지, 토스페이로 받아야 하는지
- **왜:** 앱인토스는 가상자산 관련 기능(소유·이전·저장·거래·발행)을 등록할 수 없습니다. 우리 기능은 해당하지 않도록 설계했지만, 심사는 전체 맥락을 봅니다. 결제 방식도 디지털 재화에 따라 달라집니다. 자세한 내용은 `TOSS_POLICY_NOTES.md`에 있습니다.
- **어디서:** 앱인토스 개발자센터 → 채널톡 문의
- **필요한 정보:** 서비스 소개 한 줄("계약서는 내가 보관하고, 계약의 디지털 지문은 검증할 수 있게 합니다"), `FINAL_REVIEW/07-complete.png`, `09-blockchain.png` 스크린샷
- **완료 확인:** 담당자의 답변을 받았다.
  - 블록체인 기능이 불가하다면 `.env`에서 `BLOCKCHAIN_ENABLED=false`로 바꿉니다. 나머지 기능은 그대로 출시할 수 있습니다.

## [ ] 2. 사업자 등록 · 앱인토스 개발자 계정 · 서비스 등록

- **무엇을:** 앱인토스 콘솔 가입 → 워크스페이스 생성 → 미니앱 등록 (앱 이름: `kyeyakhaja` 또는 원하는 이름)
- **왜:** 토스 로그인, 결제, 배포를 하려면 등록된 앱이 필요합니다.
- **어디서:** https://developers-apps-in-toss.toss.im 콘솔
- **필요한 정보:** 사업자등록번호, 대표자 정보, 정산 계좌, 고객센터 연락처, 서비스 아이콘·설명
- **완료 확인:** 콘솔에 앱이 보인다.
  - 앱 이름을 바꿨다면 `frontend/apps-in-toss.config.ts`의 `appName`과 `frontend/.env.toss`의 `VITE_AIT_APP_NAME`을 같은 값으로 맞춥니다.

## [ ] 3. 토스 로그인 설정 (mTLS 인증서 · 복호화 키)

- **무엇을:** 콘솔에서 토스 로그인을 켜고 mTLS 인증서와 사용자 정보 복호화 키를 발급받습니다.
- **왜:** 서버가 로그인 코드를 사용자 정보로 바꾸려면 인증서가 필요합니다.
- **어디서:** 앱인토스 콘솔 → 토스 로그인
- **필요한 정보:** 인증서 파일(.crt/.key), 복호화 키, AAD
- **입력할 곳(운영 .env):** `TOSS_PROVIDER=production`, `TOSS_MTLS_CERT_PATH`, `TOSS_MTLS_KEY_PATH`, `TOSS_DECRYPTION_KEY`, `TOSS_AAD`
- **완료 확인:** 샌드박스 앱에서 "토스로 로그인" 성공 → `/admin`의 Providers에서 toss가 `production`(운영)으로 표시됨

## [ ] 4. 인앱결제 상품 등록 (블록체인 기록 990원)

- **무엇을:** 비소모성/소모성 1회 결제 상품을 등록합니다(예: `blockchain_record_990`).
- **왜:** 유료 기록 기능의 결제에 필요합니다.
- **어디서:** 앱인토스 콘솔 → 인앱결제
- **입력할 곳:** `PAYMENT_PROVIDER=production`, `TOSS_IAP_SKU_BLOCKCHAIN=<상품 ID>`, 가격은 `BLOCKCHAIN_PRICE`
- **완료 확인:** 샌드박스에서 결제 → 기록 완료. `/admin`에서 payment가 `production`으로 표시됨
- **참고:** 서버측 주문 검증 API 호출부는 콘솔 문서의 최신 명세를 확인한 뒤 연결해야 합니다(`KNOWN_ISSUES.md` #1). 명세를 받으면 개발자가 30분 안에 연결할 수 있는 작업입니다.

## [ ] 5. 본인확인 · 전자서명 사업자 계약 (토스인증 권장)

- **무엇을:** 토스인증(본인확인 + 전자서명) 가맹 계약을 맺고 Client ID/Secret을 받습니다.
- **왜:** 지금 개발 환경의 본인확인과 서명은 모의(mock) 방식입니다. 법적 효력이 있는 전자서명과 본인확인을 하려면 인증 사업자가 필요합니다. 앱인토스 SDK에 토스인증서 서명 기능(`appsInTossSignTossCert`)이 있어 가장 자연스럽게 맞습니다.
- **어디서:** https://toss.im/tosscert (제휴 문의)
- **입력할 곳:** `IDENTITY_PROVIDER=production`, `SIGNATURE_PROVIDER=production`, `TOSS_CERT_CLIENT_ID`, `TOSS_CERT_CLIENT_SECRET`
- **완료 확인:** 실제 휴대폰으로 본인확인·서명 성공 → 전자계약 확인서의 서명 방식에 `production`이 표시됨

## [ ] 6. 블록체인 운영 방식 결정 · 지갑 준비 (1번 답변 후)

- **무엇을:** 다음 중 하나를 고릅니다.
  - (A) EVM 테스트넷/메인넷 (예: Polygon, Base) — 운영 지갑과 가스비용 코인이 필요합니다.
  - (B) OpenTimestamps — 지갑이 필요 없고 무료지만, 연동 개발이 추가로 필요합니다.
- **왜:** 실제 체인에 기록하려면 운영 지갑이 필요합니다. 개발 환경은 로컬 체인과 Mock입니다.
- **어디서:** 지갑은 운영자 명의로 생성하고, **개인키는 Secret Manager에만 보관**합니다.
- **입력할 곳:** `BLOCKCHAIN_PROVIDER=evm`, `BLOCKCHAIN_NETWORK`, `BLOCKCHAIN_RPC_URL`, `BLOCKCHAIN_PRIVATE_KEY`(Secret Manager), `BLOCKCHAIN_EXPLORER_TX_URL`
  - 컨트랙트 배포는 개발자 도구로 1회 하고, 나온 주소를 `BLOCKCHAIN_CONTRACT_ADDRESS`에 넣습니다.
- **완료 확인:** 테스트 계약 1건을 기록한 뒤 블록 탐색기에서 TX가 보인다.

## [ ] 7. 운영 서버 · 도메인 · 비밀값 저장소

- **무엇을:** 클라우드 계정(AWS/GCP 등)에 PostgreSQL, Redis, 컨테이너 실행 환경, Secret Manager를 만들고 도메인과 HTTPS를 연결합니다.
- **왜:** 앱인토스 번들은 토스가 호스팅하고, API 서버는 우리가 운영해야 합니다.
- **어디서:** 클라우드 콘솔 + 도메인 등록업체
- **필요한 정보:** 결제 수단, 도메인. 설정 순서는 `DEPLOYMENT.md`에 있습니다.
- **입력할 곳:** `APP_ENV=production`, `PUBLIC_BASE_URL=https://도메인`, `CORS_ORIGINS`(토스 WebView 출처 — 담당자 확인), `COOKIE_SECURE=true`, `KEY_PROVIDER=secret_manager`, `ADMIN_TOKEN`
- **완료 확인:** `https://도메인/admin?token=...`에서 **PRODUCTION: READY**가 표시된다.

## [ ] 8. 개인정보처리방침 · 이용약관 · 보존 정책 법률 검토

- **무엇을:** 변호사(또는 개인정보 전문가)에게 `PRIVACY_CHECKLIST.md`와 `LEGAL_REVIEW_CHECKLIST.md`를 전달해 검토받고, 방침과 약관 문서를 확정합니다.
- **왜:** 전자서명법, 전자문서법, 개인정보보호법, 근로기준법(근로계약서 보존의무 3년) 등이 관련되며, 템플릿 문구도 검토가 필요합니다.
- **필요한 정보:** 사업자 정보, 개인정보 보호책임자, 위탁업체(클라우드, 토스인증 등)
- **완료 확인:** 방침·약관 URL을 앱인토스 콘솔에 등록했고, `backend/retention_policies.yaml`의 기간과 안내 문구를 검토 결과대로 수정했다(필요하면 개발자에게 요청).

## [ ] 9. 앱인토스 번들 빌드 · 업로드 · 검수 제출

- **무엇을:** 다음 순서로 진행합니다.
  1. `frontend/.env.toss`에 운영 API 주소를 입력합니다.
  2. `make ait`를 실행합니다(`kyeyakhaja.ait` 생성).
  3. `cd frontend && npx ait deploy --api-key <콘솔 API 키>`로 업로드합니다.
  4. 콘솔에서 검수를 요청합니다.
- **왜:** 앱인토스 배포는 콘솔 권한이 있는 사람만 할 수 있습니다.
- **필요한 정보:** 콘솔 API 키, 스크린샷(`FINAL_REVIEW/`), 앱 설명
- **완료 확인:** `TOSS_SUBMISSION_CHECKLIST.md`의 모든 항목에 체크하고, 검수 승인 알림을 받았다.

## [ ] 10. 출시 후

- 정기 품질점검(뒤로가기 동작, 테스트 키 잔존 등) 알림이 오면 14일 안에 개선합니다. `RELEASE_CHECKLIST.md`를 참고하세요.
