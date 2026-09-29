.PHONY: up down local test visual samples ait compile
up:        ## Docker 로 전체 실행 → http://localhost:5173
	./start.sh
down:
	./start.sh stop
local:     ## Docker 없이 실행
	./start.sh local
test:      ## 전체 테스트 → test-results/summary.json
	./scripts/run_all_tests.sh
visual:    ## 화면 캡처만 → FINAL_REVIEW/*.png
	cd e2e && npx playwright test --project=visual
samples:   ## 체험용 샘플 PDF
	cd backend && .venv/bin/python scripts/make_samples.py
ait:       ## 앱인토스 번들(.ait) 빌드 (frontend/.env.toss 필요)
	cd frontend && npm run build:ait
compile:   ## 스마트컨트랙트 컴파일
	cd contracts && npm run compile
