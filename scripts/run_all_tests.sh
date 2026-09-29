#!/usr/bin/env bash
# 전체 테스트 실행 → test-results/summary.json (Admin 대시보드 / FINAL_TEST_REPORT.md 의 근거)
#   1) 백엔드 pytest (단위·통합·보안·EVM 스마트컨트랙트)
#   2) 프론트엔드 vitest + 타입검사 + 웹 빌드 + 앱인토스(.ait) 빌드
#   3) 스마트컨트랙트 컴파일
#   4) E2E (Playwright: 기능 + 화면 캡처)
#   5) 보안 점검 (bandit, pip-audit, npm audit, 비밀값 스캔)
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RAW="$ROOT/test-results/raw"
mkdir -p "$RAW"
cd "$ROOT"
status() { echo "$1=$2" >> "$RAW/status.env"; }
: > "$RAW/status.env"

echo "▶ 1/5 백엔드 테스트"
(cd backend && .venv/bin/pytest -q -p no:cacheprovider --junitxml="$RAW/backend.xml" tests) ; status backend_exit $?

echo "▶ 2/5 프론트엔드 테스트 · 빌드"
(cd frontend && npx vitest run --reporter=json --outputFile="$RAW/frontend.json" >/dev/null) ; status frontend_exit $?
(cd frontend && npx tsc -b --noEmit) ; status typecheck_exit $?
(cd frontend && [ -f .env.toss ] || cp .env.toss.example .env.toss; npm run -s build:ait > "$RAW/ait-build.log" 2>&1) ; status ait_build_exit $?
(cd frontend && npx vite build > "$RAW/web-build.log" 2>&1) ; status web_build_exit $?

echo "▶ 3/5 스마트컨트랙트 컴파일"
(cd contracts && npm run -s compile > "$RAW/contract-compile.log" 2>&1) ; status contract_compile_exit $?

echo "▶ 4/5 E2E (브라우저 자동화)"
rm -f "$RAW/e2e.json"
(cd e2e && npx playwright test > "$RAW/e2e.log" 2>&1) ; status e2e_exit $?   # 리포터: list + json(test-results/raw/e2e.json)

echo "▶ 5/5 보안 점검"
(cd backend && .venv/bin/bandit -q -r app -f json -o "$RAW/bandit.json" >/dev/null 2>&1) ; status bandit_exit $?
(cd backend && .venv/bin/pip-audit -r requirements.txt -f json -o "$RAW/pip-audit.json" >/dev/null 2>&1) ; status pip_audit_exit $?
(cd frontend && npm audit --omit=dev --json > "$RAW/npm-audit.json" 2>/dev/null) ; status npm_audit_exit $?
python3 scripts/secret_scan.py > "$RAW/secret-scan.json" ; status secret_scan_exit $?

python3 scripts/summarize.py
