"""인증(JWT httpOnly 쿠키) + CSRF(double-submit) + 보안 헤더."""
from __future__ import annotations

import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.models import User

SESSION_COOKIE = "kz_session"
CSRF_COOKIE = "kz_csrf"
CSRF_HEADER = "X-CSRF-Token"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# 로그인 전 호출되는 엔드포인트 (CSRF 토큰이 아직 없음)
CSRF_EXEMPT_PREFIXES = ("/api/auth/mock-login", "/api/auth/toss/login", "/api/verify/")


def _secret() -> str:
    s = get_settings().JWT_SECRET
    if not s:
        raise RuntimeError("JWT_SECRET 이 설정되지 않았습니다.")
    return s


def issue_session(response: Response, user: User) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {"sub": user.id, "iat": now, "exp": now + timedelta(minutes=s.SESSION_TTL_MINUTES), "jti": secrets.token_hex(8)},
        _secret(),
        algorithm="HS256",
    )
    csrf = secrets.token_urlsafe(24)
    max_age = s.SESSION_TTL_MINUTES * 60
    response.set_cookie(SESSION_COOKIE, token, httponly=True, secure=s.COOKIE_SECURE, samesite="lax", max_age=max_age, path="/")
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, secure=s.COOKIE_SECURE, samesite="lax", max_age=max_age, path="/")
    return csrf


def clear_session(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def decode_session(token: str) -> str:
    try:
        payload = jwt.decode(token, _secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(401, detail={"code": "SESSION_EXPIRED", "message": "로그인이 만료되었어요. 다시 로그인해 주세요."}) from e
    except jwt.PyJWTError as e:
        raise HTTPException(401, detail={"code": "UNAUTHENTICATED", "message": "로그인이 필요해요."}) from e
    return payload["sub"]


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(401, detail={"code": "UNAUTHENTICATED", "message": "로그인이 필요해요."})
    user = db.get(User, decode_session(token))
    if user is None:
        raise HTTPException(401, detail={"code": "UNAUTHENTICATED", "message": "로그인이 필요해요."})
    return user


def optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    try:
        return db.get(User, decode_session(token))
    except HTTPException:
        return None


def csrf_ok(request: Request) -> bool:
    if request.method not in UNSAFE_METHODS:
        return True
    path = request.url.path
    if not path.startswith("/api/") or any(path.startswith(p) for p in CSRF_EXEMPT_PREFIXES):
        return True
    if SESSION_COOKIE not in request.cookies:
        return True  # 인증 없는 요청은 current_user 에서 401
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get(CSRF_HEADER, "")
    return bool(cookie) and hmac.compare_digest(cookie, header)


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Cache-Control": "no-store",
}
