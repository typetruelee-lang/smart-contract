# 앱인토스 제출 체크리스트

## 준비 (개발 완료 ✅ / 사용자 할 일 ⬜)

| 항목 | 상태 | 비고 |
|---|---|---|
| 앱인토스 SDK 연동 (`@apps-in-toss/web-framework` 3.6.0) | ✅ | `frontend/src/lib/tossBridge.ts` — TossAuth.login, IAP, Share, File.saveBase64 |
| 앱인토스 설정 파일 | ✅ | `frontend/apps-in-toss.config.ts` (appName, 브랜드 색 #3182F6, 내비게이션 바, 클립보드 권한) |
| `.ait` 번들 빌드 | ✅ | `make ait` → `frontend/goodgun.ait` (개발 컨테이너에서 빌드 성공 확인) |
| 토스 런타임 인증(Bearer 토큰, 교차 도메인) | ✅ | `VITE_RUNTIME=toss`, 백엔드 `X-Auth-Mode: token` |
| 뒤로가기 동작 | ✅ | 모든 화면 상단 뒤로가기 + 브라우저 뒤로가기 E2E 통과 |
| 테스트용 키·Mock 잔존 금지 | ✅ | 운영에서 mock 로그인·장애 주입 API 404, mock provider 사용 시 오류 |
| 모바일 레이아웃 | ✅ | 가로 스크롤 없음, 버튼 높이 48px 이상 (E2E 검사) |
| 한국어 쉬운 문구 / 블록체인 용어 최소화 | ✅ | `FINAL_REVIEW/VISUAL_REVIEW.md` |
| 스크린샷 | ✅ | `FINAL_REVIEW/*.png` (24장) |
| 회원 탈퇴 | ✅ | 홈 → 이름 → 내 정보 → 회원 탈퇴 |
| 토스 로그인 연결 끊기 콜백 | ✅ / ⬜ | `/api/auth/toss/unlink` 구현. 콘솔 등록은 FINAL_USER_ACTIONS 6-1번 |
| 운영 설정 가드 | ✅ | 개발용 로그인·결제·서명이 켜져 있으면 운영 서버가 시작되지 않음 |
| 디지털 지문 기록 = OpenTimestamps (지갑·코인 없음) | ✅ | `TOSS_LAUNCH_AUDIT.md` 2장 · FINAL_USER_ACTIONS 6번 |
| 블록체인 기능 정책 확인 | ⬜ | FINAL_USER_ACTIONS 1번 |
| 콘솔 앱 등록 · appName 일치 | ⬜ | 2번 |
| 토스 로그인 mTLS · 복호화 키 | ⬜ | 3번 |
| IAP 상품 등록 · SKU | ⬜ | 4번 |
| 운영 API 도메인 · HTTPS · CORS | ⬜ | 7번 |
| `frontend/.env.toss`에 운영 API 주소 | ⬜ | `VITE_API_BASE_URL=https://api.도메인` |
| 개인정보처리방침·이용약관 URL | ⬜ | 8번 |
| 고객센터 연락처 | ⬜ | 콘솔 |

## 빌드 · 업로드 순서

```bash
cp frontend/.env.toss.example frontend/.env.toss   # 운영 API 주소 입력
make ait                                           # → frontend/goodgun.ait
cd frontend && npx ait deploy --api-key <콘솔에서 발급한 키>
```

업로드한 뒤 콘솔에서 **샌드박스 테스트 → 검수 요청** 순서로 진행합니다.

## 샌드박스에서 직접 확인할 것 (실기기)

- [ ] 토스로 로그인
- [ ] 템플릿으로 계약 작성 → 초대 링크 공유(카카오톡 등) → 상대방 토스 앱에서 열림
- [ ] 토스인증 본인확인 · 서명 (가맹 후)
- [ ] 계약서 PDF 저장 → 휴대폰 파일 앱에서 열림
- [ ] [무료로 기록하기](또는 인앱결제) → 1~6시간 뒤 기록 완료 → 확인서에 비트코인 블록 표시 → `.ots` 파일 검증
- [ ] 회원 탈퇴 · 토스에서 연결 끊기
- [ ] 검증 QR 코드를 휴대폰 카메라로 스캔 → 검증 페이지 열림
- [ ] 뒤로가기 · 앱 재진입 · 로그인 만료 후 재로그인
