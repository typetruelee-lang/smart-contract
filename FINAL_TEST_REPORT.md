# 최종 테스트 보고서

- 실행: `make test` (`scripts/run_all_tests.sh`) — 2026-09-30 02:41 UTC, 개발 컨테이너
- 근거 파일: `test-results/summary.json`
- 실제로 실행한 결과만 적었습니다. 외부 계정이 필요한 운영 연동은 **테스트하지 않았고**, 해당 칸은 "Mock"으로 표시했습니다.

## 요약

| 구분 | PASS | FAIL |
|---|---|---|
| 백엔드 (pytest: 단위·통합·보안·EVM 스마트컨트랙트·증빙 문서) | 195 | 0 |
| 프론트엔드 (vitest) | 20 | 0 |
| E2E 기능 (Playwright, 모바일 iPhone 13 에뮬레이션) | 19 | 0 |
| E2E 화면 캡처 | 1 (22장) | 0 |
| **합계** | **235** | **0** |

추가로 확인한 것:

| 확인 | 결과 |
|---|---|
| `./start.sh`(= `docker compose up --build`)로 전체 스택 새로 기동 | PASS — db·redis·로컬 체인·API·워커·웹 healthy |
| Docker 스택 대상 E2E | PASS 15 / SKIP 1 (세션 만료: 서버 비밀값이 필요해 외부 실행에서는 건너뜀. 로컬 실행에서는 PASS) |
| Docker 스택 스모크 (`scripts/smoke.py`) | PASS — 로컬 Hardhat 체인에 실제 TX 기록 → 온체인 검증 성공, 수정본 거부 |
| 관리자 대시보드 판정 | DEVELOPMENT: **COMPLETE** / PRODUCTION: NOT READY (외부 계정 미연결 — 정상) |

## 기능 테스트

| 기능 | 결과 | 근거 테스트 |
|---|---|---|
| Contract Creation (텍스트·붙여넣기·템플릿 5종) | PASS | `test_flow.py`, `test_contract_data_matrix.py`, E2E 시나리오 1·템플릿 |
| 표준근로계약서 · 일용근로자 표준근로계약서 (고용노동부 서식 항목, 근로시간 HH:MM 검증, 템플릿 안내) | PASS | `test_contract_data_matrix.py`(2종 × 정상/빈/잘못/긴/한글/특수/숫자/날짜), `test_time_field_pattern`, E2E 일용근로자 |
| 입력 형식 규칙 서버 허용목록 (임의 정규식·과도한 길이 제한 거부) | PASS | `test_client_validation_is_sanitized` |
| PDF Upload (텍스트 PDF 추출 · 스캔 PDF OCR) | PASS | `test_pdf_upload.py`, E2E 시나리오 2·OCR |
| Field Detection (자동 **추천** → 사용자 적용) | PASS | `test_units.py`(추천·적용·라벨·유형 추론), E2E |
| Manual Field (PDF 위 드래그 추가·이동·설정) | PASS | E2E 시나리오 2 |
| Field Types 9종 + 값 검증 | PASS | `test_units.py`(정상 11 / 거부 13), 데이터 매트릭스 |
| Document Versioning (v1→v2→FINAL, 서명 무효화) | PASS | `test_version_bump_invalidates_signature`, E2E |
| PDF Export (계약서 · 확인서 · QR · 한글) | PASS | 시나리오 1·3, PDF 텍스트 추출 검증 |
| Signature (본인확인 → 3개 동의 → 서명 → 완료) | PASS (Mock/HMAC) | E2E 시나리오 1, `test_signature_development_hmac_verifies` |
| Evidence (감사 로그 · 해시체인 · 변조 탐지) | PASS | `test_audit_events_complete_and_chained`, `test_audit_chain_detects_tampering` |
| SHA-256 (한 글자·한 바이트 변경 시 Hash 다름) | PASS | `test_hash_of_real_pdf_changes_on_one_char`, 시나리오 5 |
| Blockchain | PASS (Mock · 인메모리 EVM · 로컬 Hardhat) | 시나리오 3·8, `test_evm_*`, Docker 스모크 |
| Verification (성공 · 실패 · 검증번호 없이 PDF만) | PASS | 시나리오 4·5 |
| Merkle Tree (Root · Proof · 검증 · 배치 기록) | PASS | 시나리오 6: `test_scenario6_*`, `test_merkle_*`, `test_merkle_batch_mode_end_to_end` |
| Payment Mock (성공·실패·취소·멱등성) | PASS | 시나리오 7, `test_idempotent_*` |
| Toss Mock (로그인 · Bearer 토큰 모드 · provider 전환) | PASS | `test_providers.py`, `test_bearer_token_mode_for_apps_in_toss` |
| Retention (종류별 보존·삭제 후 검증 유지) | PASS | `test_retention_*`, `test_draft_expires_after_draft_ttl` |
| 앱인토스 `.ait` 번들 빌드 | PASS | `kyeyakhaja.ait` 생성 |
| 제출용 증빙 PDF (발급번호·쪽번호·진행 기록·검증 방법·유의사항) | PASS | `test_legal_documents.py` |
| 확인서 자체 진위 확인 (발급 대장 대조) | PASS | `test_certificate_itself_can_be_verified`, E2E 법적 고지 |
| 시험용 워터마크 (모의 서명 시) / 운영 서명 시 미표시 | PASS | `test_contract_pdf_has_footer_notice_and_test_watermark`, `test_production_grade_signatures_have_no_test_watermark` |
| 서명 전 원본 보관 동의(4번째) + 동의 문구 버전 기록 | PASS | `test_review_requires_retention_acknowledgement_and_records_consent` |
| 법적 고지 문구 표시 (로그인·만들기·완료·검증·이자율 경고·약관) | PASS | E2E `법적 고지` |

## 지시서 시나리오 1~8

| # | 시나리오 | 결과 |
|---|---|---|
| 1 | 로그인 → 계약 생성 → 텍스트 입력 → 빈칸 생성 → 값 입력 → PDF 생성 → 완료 | PASS (E2E + 통합) |
| 2 | PDF 업로드 → 텍스트 추출 → 빈칸 생성 → 값 입력 → PDF 생성 | PASS (E2E + 통합) |
| 3 | 계약 완료 → Hash → Blockchain Mock → TX 생성 → 확인서 생성 | PASS |
| 4 | 원본 PDF → 검증 → 성공 | PASS |
| 5 | 원본 PDF 수정 → 검증 → 실패 | PASS |
| 6 | Merkle Tree → Root 생성 → Proof 생성 → Proof 검증 | PASS |
| 7 | 결제 실패 → Blockchain 호출 안 됨 | PASS |
| 8 | Blockchain 실패 → Pending(RETRY) → Retry → 성공 | PASS |

## FINAL REVIEW MODE (25항목)

| # | 항목 | 결과 | 방법 |
|---|---|---|---|
| 1 | 앱 실행 | PASS | `./start.sh` Docker 기동, E2E 서버 기동 |
| 2 | 로그인 | PASS | 모든 E2E |
| 3 | 계약 만들기 | PASS | E2E 시나리오 1 |
| 4 | 텍스트 계약서 작성 | PASS | E2E 시나리오 1 |
| 5 | 빈칸 생성 | PASS | 자동 찾기 → 모두 적용 |
| 6 | 입력 | PASS | 필드 입력·저장, 잘못된 값 거부 |
| 7 | PDF 생성 | PASS | 다운로드 → Hash 일치 |
| 8 | 상대방 흐름 | PASS | 초대 링크 → 수락 → 입력 → 서명 |
| 9 | 본인확인 Mock | PASS | |
| 10 | 전자서명 | PASS | 서명패드 → 완료 |
| 11 | 계약 완료 | PASS | 완료 화면 |
| 12 | 확인서 생성 | PASS | PDF 다운로드, 내용 검사 |
| 13 | Hash 생성 | PASS | 서버 Hash = 파일 SHA-256 |
| 14 | 블록체인 Mock | PASS | TX 표시 |
| 15 | 검증 | PASS | 성공 |
| 16 | PDF 변경 | PASS | 1바이트 변조 |
| 17 | 검증 실패 확인 | PASS | "검증 실패" 표시 |
| 18 | 결제 실패 | PASS | 기록 요청 없음 |
| 19 | Blockchain 실패 | PASS | "다시 시도 중", 결제는 완료 유지 |
| 20 | 재시도 | PASS | 수동 재시도 + 워커 → 기록 완료 |
| 21 | 모바일 화면 | PASS | 5개 화면 가로 스크롤 없음, 버튼 48px 이상 + 화면 검수 22장 |
| 22 | 오류 화면 | PASS | 없는 화면·없는 계약·타인 계약 |
| 23 | 뒤로가기 | PASS | 앱 뒤로가기 + 브라우저 뒤로가기 |
| 24 | 새로고침 | PASS | 새로고침 후 상태 유지 |
| 25 | 세션 만료 | PASS | 만료 안내 → 재로그인 → 원래 화면 |

## E2E

PASS — 19/19 (로컬) · 15/15 + 1 SKIP (Docker 스택)

## Security

PASS

- bandit 0건 · pip-audit 0건 · npm audit 0건 · 비밀값 스캔 0건
- 보안 테스트 18건: 인증·세션 만료·위조 토큰·CSRF·쿠키 플래그·보안 헤더·XSS·SQLi·rate limit(헤더 위조 우회 불가)·개발 API 차단·업로드 검증·서명 이미지 검증·로그/DB 평문 개인정보 없음·Bearer 모드·CORS
- 자세한 내용: `SECURITY_CHECKLIST.md`

## Build

PASS — 타입 검사 · 웹 빌드 · 앱인토스 `.ait` 빌드 · 스마트컨트랙트 컴파일 · Docker 이미지 4종

## 화면 검수

PASS — 22장 OK (`FINAL_REVIEW/VISUAL_REVIEW.md`)

## 테스트 중 발견해서 고친 문제 (재발 방지 테스트 포함)

| 문제 | 조치 |
|---|---|
| EVM TX ID에 `0x` 접두어 누락 (web3 v7) | `Web3.to_hex` 사용 + 테스트 강화 |
| rate limit이 위조 가능한 `X-Forwarded-For`를 신뢰 | 신뢰 프록시만 반영(`client.host`) + 우회 불가 테스트 |
| PDF 생성마다 Chromium 실행 (느림) | 전용 렌더러 스레드로 재사용 (백엔드 테스트 47초 → 27초) |
| nginx가 `.mjs`를 잘못된 MIME으로 전송 → 운영 빌드에서 PDF 미리보기 불가 | MIME 추가 (Docker E2E로 발견) |
| nginx location의 `add_header` 때문에 보안 헤더 누락 | 모든 location에 보안 헤더 include |
| 의존성 취약점 (pip 89건 · npm high 3건) | fastapi/starlette·pypdf·pillow·cryptography·PyJWT·python-multipart·jinja2 업그레이드, React Router v7 |
| 로그인 후 이동 주소 오픈 리다이렉트 가능성 | `safeRedirect` + 단위/E2E 테스트 |
| React Router v7 전환 후 세션 만료 안내 누락 | 인증 컨텍스트에 만료 상태 저장 + 4회 반복 테스트 |
| 관리자 화면이 개발용 서명·로컬 체인을 "운영"으로 표시 | 개발용 판정 수정 + 테스트 |
| 빈칸 입력 형식(정규식)을 클라이언트 값 그대로 사용 → ReDoS 가능성 | 서버가 아는 형식(전화·이메일·시각)만 허용, 길이 제한 상한 고정 + 테스트 |
| 스캔 PDF OCR이 밑줄을 인식하지 못함 | "라벨:" 빈칸·"년 월 일" 추천 규칙 추가 |
| 드래그가 하단 고정 버튼 위에서 끝나 빈칸 대신 저장이 눌림 | 테스트 좌표 수정 (UX는 스크롤로 해결) |

## Known Issues

외부 계정이 필요한 운영 연동 등 12건 → `KNOWN_ISSUES.md` (기능 테스트 실패 항목은 없음)
