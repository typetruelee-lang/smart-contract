# 계약하자

> 계약서는 내가 보관하고, 계약의 디지털 지문은 검증할 수 있게 합니다.

토스 앱(앱인토스) 안에서 쓰는 초경량 전자계약 서비스입니다.
계약서 작성 → 상대방 초대 → 본인확인 → 전자서명 → 완성 PDF · 전자계약 확인서 → (선택·유료) 디지털 지문 블록체인 기록 → 누구나 검증

## 빠른 시작

```bash
./start.sh          # Docker 로 전체 실행 → http://localhost:5173
```

테스트 계정(홍길동·김철수·이영희)은 로그인 화면에서 고릅니다. 자세한 내용은 [ENVIRONMENT_SETUP.md](ENVIRONMENT_SETUP.md)에 있습니다.

## 주요 기능

| 기능 | 설명 |
|---|---|
| 계약서 작성 | 새로 쓰기 · 텍스트 붙여넣기 · 템플릿 6종(차용증/용역/거래/표준근로계약서/일용근로자·단시간근로자 표준근로계약서 — 고용노동부 표준 서식 항목 기준) · 내 PDF 불러오기 |
| 빈칸 | 9가지 유형(글·숫자·날짜·전화·이메일·선택·체크·긴 글·서명). 자동 **추천**(`____`, `[   ]`, `{이름}`, `__년 __월 __일`, `(인)`, `□`)을 사용자가 확인한 뒤 적용하고, 직접 추가도 가능 |
| PDF 편집 | PDF 위에서 빈칸 추가(드래그)·이동·크기 조절·이름/유형/필수/입력자 설정. 텍스트 PDF 밑줄 위치 자동 추천, 스캔 PDF는 OCR |
| 편집/미리보기 | 모든 작성 화면에서 전환 가능. 모바일 우선 |
| 문서 버전 | 초대할 때 봉인 → 내용이 바뀌면 v2, v3… 생성. 이전 서명은 무효화되고 재서명 필요. 버전 비교 제공 |
| 본인확인·전자서명 | provider adapter (mock / development(HMAC) / production(토스인증)) |
| 완성 PDF | 입력값과 서명이 들어간 계약서 + 전자서명 정보 페이지. 당사자 모두 같은 파일을 받음 |
| 전자계약 확인서 | 계약번호·당사자(마스킹)·본인확인·서명 시각·Document Hash·검증 ID·블록체인 상태·TX·QR |
| 원문 미보관 | 원문은 암호화해 보관하다가 보존 정책(계약 종류별)에 따라 자동 삭제. Hash·감사 로그는 영구 보관 |
| 감사 로그 | 이벤트 20여 종, 해시체인으로 변조 탐지 |
| 블록체인(유료) | 결제 성공 시에만 기록. 결제·기록 상태 분리, 재시도, 멱등성, EVM/Mock adapter, Merkle 확장 |
| 검증 | 검증번호/QR 또는 PDF 업로드(브라우저에서 Hash 계산 — 파일 전송 없음), 개인정보 비노출 |
| 관리자 | 시스템 상태 · 테스트 결과 · Provider · 보안 경고 · DEVELOPMENT/PRODUCTION 준비 상태 |

## 구조

```
backend/     FastAPI · SQLAlchemy · Alembic — 계약 엔진, PDF 엔진, provider adapter, 워커
frontend/    React · Vite · Tailwind — 모바일 UI, 앱인토스 SDK 브리지, apps-in-toss.config.ts
contracts/   Solidity DocumentRegistry + 로컬 Hardhat 체인
e2e/         Playwright (기능 테스트 + 화면 캡처)
scripts/     전체 테스트 실행 · 요약 · 비밀값 스캔 · 스모크 테스트
FINAL_REVIEW/ 화면 캡처 22장 + 화면 검수표
samples/     체험용 PDF
```

## 문서

- 결과: [FINAL_TEST_REPORT.md](FINAL_TEST_REPORT.md) · [KNOWN_ISSUES.md](KNOWN_ISSUES.md) · [FINAL_REVIEW/VISUAL_REVIEW.md](FINAL_REVIEW/VISUAL_REVIEW.md)
- 내가 할 일: [FINAL_USER_ACTIONS.md](FINAL_USER_ACTIONS.md)
- 출시: [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) · [TOSS_SUBMISSION_CHECKLIST.md](TOSS_SUBMISSION_CHECKLIST.md) · [TOSS_POLICY_NOTES.md](TOSS_POLICY_NOTES.md)
- 점검: [SECURITY_CHECKLIST.md](SECURITY_CHECKLIST.md) · [PRIVACY_CHECKLIST.md](PRIVACY_CHECKLIST.md) · [LEGAL_REVIEW_CHECKLIST.md](LEGAL_REVIEW_CHECKLIST.md)
- 운영: [ENVIRONMENT_SETUP.md](ENVIRONMENT_SETUP.md) · [DEPLOYMENT.md](DEPLOYMENT.md) · [PROJECT_ENVIRONMENT.md](PROJECT_ENVIRONMENT.md)
