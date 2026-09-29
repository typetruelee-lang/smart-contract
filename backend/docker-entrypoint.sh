#!/bin/sh
# 개발용 편의: JWT_SECRET / DATA_ENCRYPTION_KEY 가 없으면 /data/secrets.env 에 1회 생성해 재사용한다.
# (APP_ENV=production 에서는 생성하지 않고 즉시 실패 — Secret Manager 로 주입해야 한다)
set -e
if [ -z "$JWT_SECRET" ] || [ -z "$DATA_ENCRYPTION_KEY" ]; then
  if [ "$APP_ENV" = "production" ]; then
    echo "JWT_SECRET / DATA_ENCRYPTION_KEY 가 필요합니다 (운영)." >&2; exit 1
  fi
  if [ ! -f /data/secrets.env ]; then
    umask 077
    python3 -c 'import secrets,os,base64;print("JWT_SECRET="+secrets.token_urlsafe(48));print("DATA_ENCRYPTION_KEY="+base64.b64encode(os.urandom(32)).decode())' > /data/secrets.env
  fi
  set -a; . /data/secrets.env; set +a
fi
case "$1" in
  api)
    alembic upgrade head
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'
    ;;
  worker)
    exec python3 -m app.workers.run
    ;;
  *)
    exec "$@"
    ;;
esac
