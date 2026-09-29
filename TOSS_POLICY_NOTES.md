# 앱인토스(Apps in Toss) 정책 · 연동 노트

> 개발 초기(PHASE 0)에 조사해 설계에 반영한 내용입니다.
> 개발 컨테이너에서 공식 개발자센터(developers-apps-in-toss.toss.im)에 직접 접속할 수 없었습니다. 그래서 **웹 검색으로 확인한 공식 페이지 요약**과 **공식 SDK 패키지(@apps-in-toss/web-framework 3.6.0)의 타입 정의**를 근거로 정리했습니다.
> ⚠ 표시 항목은 반드시 앱인토스 담당자(채널톡)에게 확인해야 합니다 → `FINAL_USER_ACTIONS.md` 1번

## 1. 서비스 등록 제한 — 가상자산 ⚠ (가장 중요)

- 공식 "서비스 오픈 정책/서비스별 주의사항" 요약에 따르면, 디지털 자산의 **소유·이전·저장·거래·중개·발행(NFT 포함)** 기능을 제공하는 서비스는 법적 요건 충족 여부와 관계없이 등록할 수 없습니다.
- 계약하자의 블록체인 기능은 **자산을 다루지 않습니다.** 문서의 SHA-256 지문만 기록합니다. 토큰, 지갑, 코인 결제는 사용자에게 전혀 노출되지 않고, 가스비는 운영사가 부담합니다.
- 그래도 심사에서 **소재·표현의 전체 맥락**을 본다고 하므로, 다음과 같이 설계했습니다.
  - 화면 문구는 "디지털 지문 기록", "위·변조 검증" 중심으로 쓰고, 블록체인은 설명용 보조 용어로만 씁니다.
  - `BLOCKCHAIN_ENABLED=false` 한 줄로 유료 기록 기능 전체를 숨길 수 있습니다. 이때 계약 작성·서명·PDF·확인서·Hash 검증은 모두 그대로 동작합니다.
  - 블록체인 대신 OpenTimestamps(자산·지갑 불필요)로 바꿀 수 있도록 adapter를 설계했습니다.

## 2. 결제 방식 ⚠

- 공식 가이드: **실물 재화·서비스는 토스페이(간편결제)**, **비실물 디지털 재화·서비스는 인앱결제(IAP)**를 씁니다. 디지털 재화에 따라 정책이 달라질 수 있으니 채널톡으로 확인하라고 안내합니다.
- "블록체인 기록(990원)"은 비실물 디지털 서비스이므로 **IAP로 구현**했습니다.
  - 클라이언트: `IAP.createOneTimePurchaseOrder({ options: { sku, processProductGrant }, onEvent, onError })`
  - 서버: 주문 검증 후 PAID가 되면 기록 작업을 만듭니다(`TossIapPaymentProvider`).
- 비게임 미니앱의 IAP 상품 등록 한도는 30개입니다.

## 3. 토스 로그인

- SDK: `TossAuth.login()` → `{ authorizationCode, referrer: "DEFAULT" | "SANDBOX" }`
- 서버: mTLS 인증서로 `POST /api-partner/v1/apps-in-toss/user/oauth2/generate-token` 요청 → accessToken(유효 1시간) → `login-me`로 userKey 조회
  - 이름 등 개인정보 필드는 암호화되어 오므로, 콘솔에서 받은 복호화 키로 풀어야 합니다.
- 구현 위치: `backend/app/providers/toss.py` (AppsInTossLoginProvider), `frontend/src/lib/tossBridge.ts`

## 4. 번들 · 빌드 · 배포

- `apps-in-toss.config.ts`에 appName, 브랜드 색상, 권한, 내비게이션 바를 설정합니다. `webBundleDir`은 `dist`입니다.
- `ait build`는 `dist/` 폴더를 `<appName>.ait` 파일로 묶습니다. **개발 컨테이너에서 `kyeyakhaja.ait` 빌드를 실제로 확인했습니다.**
- 배포 명령은 `ait deploy --api-key ...`입니다. 이 단계에서 콘솔 API 키가 필요하며, 사용자가 직접 해야 합니다.
- **토스가 번들을 호스팅하므로 API 서버는 다른 도메인에 있습니다.**
  - 그래서 토스 런타임에서는 쿠키 대신 **Bearer 토큰**을 쓰도록 구현했습니다(`VITE_RUNTIME=toss`, `X-Auth-Mode: token`).
  - API 서버의 `CORS_ORIGINS`에는 토스 WebView 출처를 등록해야 합니다 ⚠. 정확한 출처 도메인은 콘솔 또는 담당자에게 확인해야 합니다.

## 5. WebView 제약과 대응

| 제약 | 대응 |
|---|---|
| `<a download>`로 파일 다운로드가 안 될 수 있음 | `File.saveBase64` 사용 (지원하지 않는 앱 버전에서는 `File.openPDFViewer`) |
| 공유 | `Share.createLink({ path: "intoss://..." })` + `Share.sendMessage` |
| 전자서명 | `appsInTossSignTossCert({ txId })` — 토스인증서 서명. 운영 전자서명 provider의 후보입니다 ⚠(토스인증 가맹 필요) |

## 6. 출시 품질 점검 (비게임) — 준수 현황

| 점검 항목 | 현황 |
|---|---|
| 뒤로가기 버튼 동작 | 모든 화면 상단 뒤로가기 + 브라우저 뒤로가기 E2E 테스트 통과 |
| 테스트용 키 잔존 금지 | 운영(`APP_ENV=production`)에서 mock provider 사용 시 부팅/호출 거부, mock 로그인 API 404 |
| 콘텐츠 표현 | 투자·수익·코인 관련 표현 없음 |
| 14일 개선 기간 | 출시 후 정기 점검에 대비해 `RELEASE_CHECKLIST.md`에 항목화 |

## 출처

- [서비스별 주의사항](https://developers-apps-in-toss.toss.im/intro/caution.html)
- [서비스 오픈 정책](https://developers-apps-in-toss.toss.im/intro/guide)
- [비게임 출시 가이드](https://developers-apps-in-toss.toss.im/checklist/app-nongame)
- [미니앱 출시하기](https://developers-apps-in-toss.toss.im/guide/operation/deploy)
- [인앱 결제](https://developers-apps-in-toss.toss.im/iap/intro.html) · [인앱 결제 가이드](https://developers-apps-in-toss.toss.im/guide/monetization/in-app-payment)
- [토스 로그인](https://developers-apps-in-toss.toss.im/documentation/common/authentication/toss-login)
- [토스 인증](https://developers-apps-in-toss.toss.im/documentation/common/authentication/toss-auth)
- [토스인증 연동 — 전자서명](https://toss.im/tosscert/docs/guides/integration/signature) · [본인확인](https://toss.im/tosscert/docs/guides/integration/user)
- [토스 미니앱 전수점검 기사 (SBS Biz)](https://biz.sbs.co.kr/article/20000334429)
- npm: `@apps-in-toss/web-framework@3.6.0` (Apache-2.0) 타입 정의
