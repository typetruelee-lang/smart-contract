#!/usr/bin/env bash
# 굳건 외부 모바일 테스트 서버 — ./start.sh staging 이 이 스크립트를 부른다.
#
#   ./start.sh staging          시작 (또는 다시 시작) → 임시 https 주소와 테스터 비밀번호 출력
#   ./start.sh staging-stop     종료 (테스트 데이터는 남는다)
#   ./start.sh staging-reset    종료 + 테스트 데이터 삭제
#
# 선택 환경 변수
#   STAGING_PUBLIC_URL=https://test.example.com   자기 도메인을 쓸 때 (터널을 띄우지 않음, 127.0.0.1:5180 으로 프록시)
#   STAGING_BLOCKCHAIN=mock                       서버에서 OpenTimestamps 접속이 막혔을 때
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
COMPOSE=(docker compose -f "$DIR/docker-compose.yml")
ACTION="${1:-up}"

ensure_secrets() {
  [ -f .env ] && [ -f .htpasswd ] && return
  umask 077
  python3 - <<'PY'
import base64, hashlib, os, secrets
pw = secrets.token_urlsafe(9)
salt = os.urandom(8)
with open(".env", "w") as f:
    f.write(f"JWT_SECRET={secrets.token_urlsafe(48)}\n")
    f.write(f"DATA_ENCRYPTION_KEY={base64.b64encode(os.urandom(32)).decode()}\n")
    f.write(f"STAGING_USER=tester\nSTAGING_PASSWORD={pw}\n")
with open(".htpasswd", "w") as f:
    f.write("tester:{SSHA}" + base64.b64encode(hashlib.sha1(pw.encode() + salt).digest() + salt).decode() + "\n")
PY
  chmod 644 .htpasswd  # nginx 컨테이너가 읽을 수 있게 (해시만 들어 있음)
  echo "✓ 테스터 비밀번호와 서버 비밀값을 deploy/staging/.env 에 만들었어요 (Git 에 올라가지 않아요)"
}

tunnel_url() {
  "${COMPOSE[@]}" --profile tunnel logs tunnel 2>/dev/null | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1
}

case "$ACTION" in
  up)
    command -v docker >/dev/null || { echo "Docker 가 필요해요: https://docs.docker.com/get-docker/"; exit 1; }
    ensure_secrets
    if [ -n "${STAGING_PUBLIC_URL:-}" ]; then
      URL="${STAGING_PUBLIC_URL%/}"
      case "$URL" in https://*) ;; *) echo "STAGING_PUBLIC_URL 은 https 주소여야 해요 (휴대폰 브라우저의 검증 기능이 https 에서만 동작)"; exit 1 ;; esac
    else
      "${COMPOSE[@]}" --profile tunnel up -d tunnel
      echo "⏳ 임시 https 주소를 받는 중..."
      URL=""
      for _ in $(seq 1 60); do URL="$(tunnel_url)"; [ -n "$URL" ] && break; sleep 2; done
      [ -n "$URL" ] || { echo "⚠ 터널 주소를 받지 못했어요. '${COMPOSE[*]} --profile tunnel logs tunnel' 로 확인해 주세요."; exit 1; }
    fi
    export PUBLIC_BASE_URL="$URL"
    "${COMPOSE[@]}" up -d --build db redis backend worker frontend
    echo "⏳ 서비스가 준비될 때까지 기다리는 중..."
    ok=""
    for _ in $(seq 1 120); do
      if curl -fsS -m 5 "http://127.0.0.1:${STAGING_LOCAL_PORT:-5180}/api/health" >/dev/null 2>&1; then ok=1; break; fi
      sleep 2
    done
    [ -n "$ok" ] || { echo "⚠ 시작이 늦어지고 있어요. '${COMPOSE[*]} logs backend' 로 확인해 주세요."; exit 1; }
    . ./.env
    echo
    echo "✅ 외부 테스트 서버 준비 완료"
    echo "   주소     : $URL"
    echo "   아이디   : $STAGING_USER"
    echo "   비밀번호 : $STAGING_PASSWORD"
    echo "   관리자   : $URL/admin"
    echo
    "${COMPOSE[@]}" exec -T backend python3 -c "import qrcode,sys; q=qrcode.QRCode(border=1); q.add_data(sys.argv[1]); q.print_ascii(invert=True)" "$URL" 2>/dev/null || true
    echo "휴대폰 카메라로 QR 을 찍거나 주소를 열고, 아이디·비밀번호를 넣으면 돼요."
    [ -z "${STAGING_PUBLIC_URL:-}" ] && echo "※ 터널을 다시 만들면 주소가 바뀌어요. 다시 실행해도 주소는 유지돼요 (staging-stop 후 시작하면 새 주소)."
    ;;
  stop)
    "${COMPOSE[@]}" --profile tunnel down
    echo "종료했어요. 테스트 데이터는 남아 있어요 (지우려면 ./start.sh staging-reset)."
    ;;
  reset)
    "${COMPOSE[@]}" --profile tunnel down -v
    echo "종료하고 테스트 데이터를 지웠어요."
    ;;
  *)
    echo "사용법: ./start.sh staging | staging-stop | staging-reset"; exit 1 ;;
esac
