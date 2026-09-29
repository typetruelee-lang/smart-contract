#!/usr/bin/env bash
# 계약하자 — 한 번에 실행하기
#
#   ./start.sh          Docker 로 전체 실행 (권장)  → http://localhost:5173
#   ./start.sh local    Docker 없이 이 컴퓨터에서 직접 실행 (PostgreSQL·Redis·Python3.11·Node22 필요)
#   ./start.sh stop     실행 중인 것을 모두 종료
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
MODE="${1:-docker}"

ensure_secrets() {
  if [ ! -f .env.local ]; then
    umask 077
    {
      echo "JWT_SECRET=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')"
      echo "DATA_ENCRYPTION_KEY=$(python3 -c 'import os,base64;print(base64.b64encode(os.urandom(32)).decode())')"
    } > .env.local
    echo "✓ 개발용 비밀값을 .env.local 에 만들었어요 (Git 에 올라가지 않아요)"
  fi
}

case "$MODE" in
  docker)
    command -v docker >/dev/null || { echo "Docker 가 필요해요: https://docs.docker.com/get-docker/"; exit 1; }
    ensure_secrets
    docker compose up --build -d
    echo "⏳ 서비스가 준비될 때까지 기다리는 중..."
    for i in $(seq 1 120); do
      if curl -fsS http://localhost:5173/api/health >/dev/null 2>&1; then
        echo "✅ 준비 완료: http://localhost:5173   (관리자: http://localhost:5173/admin)"
        exit 0
      fi
      sleep 2
    done
    echo "⚠ 시작이 늦어지고 있어요. 'docker compose logs backend' 로 확인해 주세요."; exit 1
    ;;
  local)
    ensure_secrets
    mkdir -p .run
    # PostgreSQL / Redis (이미 실행 중이면 그대로 사용)
    (command -v service >/dev/null && (service postgresql start || true) && (service redis-server start || true)) >/dev/null 2>&1 || true
    if command -v psql >/dev/null && id postgres >/dev/null 2>&1; then
      su postgres -c "psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='contract'\"" | grep -q 1 || su postgres -c "psql -q -c \"CREATE ROLE contract LOGIN PASSWORD 'contract' CREATEDB;\""
      su postgres -c "psql -tAc \"SELECT 1 FROM pg_database WHERE datname='contract'\"" | grep -q 1 || su postgres -c "psql -q -c 'CREATE DATABASE contract OWNER contract;'"
    fi
    cd backend
    [ -d .venv ] || python3 -m venv .venv
    .venv/bin/pip install -q -r requirements-dev.txt
    .venv/bin/alembic upgrade head
    nohup .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 > ../.run/backend.log 2>&1 & echo $! > ../.run/backend.pid
    nohup .venv/bin/python -m app.workers.run > ../.run/worker.log 2>&1 & echo $! > ../.run/worker.pid
    cd ../frontend
    [ -d node_modules ] || npm ci --no-audit --no-fund
    nohup npx vite --host 127.0.0.1 --port 5173 --strictPort > ../.run/frontend.log 2>&1 & echo $! > ../.run/frontend.pid
    cd ..
    for i in $(seq 1 60); do
      if curl -fsS http://localhost:5173/api/health >/dev/null 2>&1; then
        echo "✅ 준비 완료: http://localhost:5173   (관리자: http://localhost:5173/admin)"; exit 0
      fi
      sleep 1
    done
    echo "⚠ 시작 실패 — .run/*.log 를 확인해 주세요."; exit 1
    ;;
  stop)
    if [ -d .run ]; then for f in .run/*.pid; do [ -f "$f" ] && kill "$(cat "$f")" 2>/dev/null || true; rm -f "$f"; done; fi
    command -v docker >/dev/null && docker compose down >/dev/null 2>&1 || true
    echo "종료했어요."
    ;;
  *)
    echo "사용법: ./start.sh [docker|local|stop]"; exit 1 ;;
esac
