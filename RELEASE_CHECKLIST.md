# 출시 체크리스트

## A. 개발 완료 기준 (DEVELOPMENT COMPLETE) — 자동 확인

- [x] 전체 자동 테스트 통과 (`make test` → `test-results/summary.json`, FAIL 0)
- [x] 지시서 시나리오 1~8 E2E 통과
- [x] 화면 검수 22장 OK (`FINAL_REVIEW/VISUAL_REVIEW.md`)
- [x] 웹 빌드 · 앱인토스 `.ait` 빌드 · 스마트컨트랙트 컴파일 성공
- [x] 보안 점검: bandit·pip-audit·npm audit·비밀값 스캔 0건
- [x] `docker compose up --build` 로 전체 스택 기동 + Docker 대상 E2E 통과

## B. 운영 준비 (PRODUCTION READY) — `/admin` 에서 READY 가 되면 완료

- [ ] 운영 `.env` / Secret Manager 값 입력 (`ENVIRONMENT_SETUP.md`)
- [ ] Providers 전부 운영 모드: toss, payment, identity, signature, blockchain, ocr(선택)
- [ ] `APP_ENV=production`, `COOKIE_SECURE=true`, `KEY_PROVIDER=secret_manager`, `ADMIN_TOKEN`
- [ ] `/admin` 보안 경고 0건, PRODUCTION: READY
- [ ] 운영 스모크 테스트: 실계정 2개로 계약 1건 → 서명 → PDF → 결제 → 기록 → 검증
- [ ] 법률 검토 완료 · 방침/약관 게시
- [ ] 앱인토스 검수 승인

## C. 출시 당일

- [ ] DB 백업 확인, 롤백 방법 확인 (`DEPLOYMENT.md`)
- [ ] 워커 동작 확인 (블록체인 재시도·보존정책 삭제 로그)
- [ ] 모니터링: 5xx 비율, 블록체인 FAILED 작업 수, 운영 지갑 잔액
- [ ] 고객센터 대응 문구: "기록이 늦어지고 있어요", "원문이 삭제되었어요", "결제했는데 기록 실패"

## D. 출시 후 정기 점검 (앱인토스 품질점검 대비, 14일 개선 기간)

- [ ] 매월: 뒤로가기·오류 화면·테스트 키 잔존 점검 (`make test` 재실행)
- [ ] 매월: 의존성 보안 점검 (`pip-audit`, `npm audit`) 후 업데이트
- [ ] 분기: 보존 정책 삭제가 제대로 되는지 감사 로그 표본 확인
- [ ] 비용: 블록체인 TX 수와 비용 → 필요하면 `ANCHOR_MODE=merkle` 전환 검토
