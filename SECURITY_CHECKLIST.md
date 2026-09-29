# 보안 체크리스트

✅ = 구현했고 자동 테스트로 확인함 · 🟡 = 구현했지만 운영 설정이 필요함 · ⬜ = 운영자가 할 일

## 애플리케이션

| 항목 | 상태 | 구현 · 근거 |
|---|---|---|
| 입력값 검증 | ✅ | Pydantic 스키마(길이·형식), 빈칸 유형별 검증(`services/fields.py`), 테스트 `test_contract_data_matrix.py` |
| SQL Injection 방어 | ✅ | SQLAlchemy ORM 파라미터 바인딩만 사용(문자열 SQL 없음), `test_sql_injection_attempts_are_harmless` |
| XSS 방어 | ✅ | React 자동 이스케이프(`dangerouslySetInnerHTML` 미사용), 서버 템플릿 Jinja2 autoescape, 빈칸 이름에 `<>{}` 금지, CSP. `test_xss_payload_is_escaped_in_pdf_and_api` |
| PDF 렌더링 격리 | ✅ | Chromium에서 `data:` 외 모든 네트워크 요청 차단(SSRF·추적 방지) |
| CSRF | ✅ | 쿠키 세션은 double-submit 토큰 필수, SameSite=Lax. Bearer 토큰(앱인토스)은 CSRF 대상 아님. `test_csrf_required_for_state_changes` |
| 인증 | ✅ | JWT HS256, httpOnly 쿠키 또는 Bearer, 만료 60분, `alg=none`·위조 토큰 거부 테스트 |
| 권한 | ✅ | 계약 당사자만 조회 가능. 다른 사람의 계약은 존재 여부도 숨김(404). 상대방은 자기 칸만 입력 가능 |
| 오픈 리다이렉트 | ✅ | 로그인 후 이동 경로 검증(`safeRedirect`), E2E 테스트 |
| 파일 업로드 | ✅ | 확장자·MIME·`%PDF-` 매직바이트·크기(10MB)·쪽수(30)·암호화 PDF·파싱 검증. 위조 PDF 테스트 |
| 서명 이미지 | ✅ | PNG 시그니처·크기·해상도 검증, SVG/JS URL 거부 |
| Rate limit | ✅ | Redis 고정 윈도우(인증·업로드·검증 별도 한도). `X-Forwarded-For` 위조로 우회 불가 |
| 보안 헤더 | ✅ | API: CSP `default-src 'none'`, X-Frame-Options, nosniff, no-store. 웹(nginx): CSP·헤더를 모든 location에 적용 |
| 오류 메시지 | ✅ | 내부 예외를 숨기고 한국어 안내만 반환. 운영에서는 `/api/docs` 비활성 |
| 로그 개인정보 제거 | ✅ | 전화·이메일·주민번호·카드번호·초대 토큰 마스킹 필터, 요청 본문 로깅 없음. `test_logs_do_not_contain_pii` |
| 감사 로그 무결성 | ✅ | 이벤트 해시체인(`prev_event_hash`), 변조 탐지 테스트 |
| 개발 기능 차단 | ✅ | 운영에서 mock 로그인·장애 주입 API는 404, 관리자 화면은 `ADMIN_TOKEN` 필요 |

## 데이터 · 비밀값

| 항목 | 상태 | 구현 · 근거 |
|---|---|---|
| 원문 암호화 저장 | ✅ | 문서마다 DEK로 AES-256-GCM 암호화, DEK는 KEK로 감쌈(envelope), AAD로 계약·버전 결합. DB 평문 미포함 테스트 |
| 원문 장기 미보관 | ✅ | 계약 종류별 보존 정책(`retention_policies.yaml`) → 자동 삭제 + `DOCUMENT_PURGED` 기록 |
| 비밀값 하드코딩 금지 | ✅ | 모든 키는 환경변수. `scripts/secret_scan.py`가 Git 추적 파일 검사(결과 0건) |
| `.env` Git 제외 | ✅ | `.gitignore`: `.env`, `.env.local`, `*.pem`, `*.key` |
| 운영 키 관리 | 🟡 | `KEY_PROVIDER=secret_manager`(AWS/GCP) 골격. 운영에서 env 키를 쓰면 부팅 거부 |
| 블록체인 개인키 | 🟡 | 코드·Git에 없음. 로컬 체인은 잠금해제 계정 사용, 운영은 Secret Manager 주입 필수(없으면 거부) |
| 블록체인 개인정보 | ✅ | 컨트랙트 입력은 `bytes32` Hash·버전만(ABI 검사 테스트) |

## 의존성 · 정적 분석 (`make test` 자동 실행)

| 도구 | 결과 |
|---|---|
| bandit (Python 정적 분석) | 0건 (assert → 명시적 검사로 교체) |
| pip-audit (Python 취약점) | 0건 (fastapi, starlette, pypdf, pillow, cryptography, PyJWT, python-multipart, jinja2 업그레이드) |
| npm audit (웹 운영 의존성) | 0건 (React Router v7 업그레이드) |
| 비밀값 스캔 | 0건 |

## 운영자가 할 일

- ⬜ `COOKIE_SECURE=true`, HTTPS 강제, `PUBLIC_BASE_URL=https://…`
- ⬜ `ADMIN_TOKEN` 설정, 관리자 화면 접근 IP 제한(선택)
- ⬜ DB 백업 · 접근 제어 · 암호화(클라우드 기본 기능)
- ⬜ 키 교체 주기 정하기(`DATA_ENCRYPTION_KEY_VERSION`으로 교체 지원)
- ⬜ 침투 테스트(선택) · 모니터링 · 알림 설정
