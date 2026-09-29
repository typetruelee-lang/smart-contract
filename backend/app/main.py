from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import admin, routes
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.rate_limit import limit_for, limiter
from app.core.security import SECURITY_HEADERS, csrf_ok
from app.services.contracts import ContractError
from app.services.states import InvalidTransition

log = logging.getLogger("app")


def create_app() -> FastAPI:
    setup_logging()
    s = get_settings()
    if not s.JWT_SECRET:
        raise RuntimeError("JWT_SECRET 이 없습니다. ./start.sh 를 실행하면 .env.local 이 자동 생성됩니다.")
    app = FastAPI(title="계약하자 API", version="1.0.0", docs_url=None if s.is_production else "/api/docs",
                  openapi_url=None if s.is_production else "/api/openapi.json", redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=True,
                       allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Content-Type", "X-CSRF-Token", "Authorization", "X-Auth-Mode", "X-Admin-Token"])

    @app.middleware("http")
    async def guard(request: Request, call_next):
        path = request.url.path
        rate_limited = s.APP_ENV != "test" or bool(request.headers.get("X-RateLimit-Test"))
        if path.startswith("/api/") and not path.startswith("/api/dev/") and rate_limited:
            group, limit = limit_for(path, request.method)
            # 클라이언트가 보낸 X-Forwarded-For 는 위조할 수 있으므로 직접 믿지 않는다.
            # 신뢰하는 프록시(nginx) 뒤에서는 uvicorn --proxy-headers 가 client.host 를 실제 IP 로 바꿔 준다.
            ip = request.client.host if request.client else "?"
            if not limiter.hit(f"{group}:{ip}", limit):
                return JSONResponse(status_code=429, content={"detail": {"code": "RATE_LIMITED", "message": "요청이 너무 많아요. 잠시 후 다시 시도해 주세요."}},
                                    headers=SECURITY_HEADERS)
        if not csrf_ok(request):
            return JSONResponse(status_code=403, content={"detail": {"code": "CSRF", "message": "보안 토큰이 올바르지 않아요. 새로고침 후 다시 시도해 주세요."}},
                                headers=SECURITY_HEADERS)
        response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            if k == "Cache-Control" and "Cache-Control" in response.headers:
                continue
            response.headers.setdefault(k, v)
        return response

    @app.exception_handler(ContractError)
    async def contract_error(_: Request, e: ContractError):
        return routes.error_response(e)

    @app.exception_handler(InvalidTransition)
    async def invalid_transition(_: Request, e: InvalidTransition):
        return JSONResponse(status_code=409, content={"detail": {"code": "INVALID_STATE", "message": "지금 상태에서는 할 수 없는 작업이에요. 새로고침해 주세요."}})

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, e: RequestValidationError):
        errs = e.errors()
        msg = "입력값을 확인해 주세요."
        for er in errs:
            m = str(er.get("msg", ""))
            if m.startswith("Value error, "):
                msg = m.replace("Value error, ", "")
                break
        return JSONResponse(status_code=422, content={"detail": {"code": "VALIDATION", "message": msg,
                                                                 "fields": [".".join(map(str, er.get("loc", []))) for er in errs][:10]}})

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, e: HTTPException):
        detail = e.detail if isinstance(e.detail, dict) else {"code": "HTTP_" + str(e.status_code), "message": "요청을 처리할 수 없어요." if e.status_code != 404 else "찾을 수 없어요."}
        return JSONResponse(status_code=e.status_code, content={"detail": detail})

    @app.exception_handler(Exception)
    async def unhandled(_: Request, e: Exception):
        log.exception("unhandled error: %s", type(e).__name__)
        return JSONResponse(status_code=500, content={"detail": {"code": "SERVER_ERROR", "message": "일시적인 오류가 발생했어요. 잠시 후 다시 시도해 주세요."}})

    @app.get("/api/health")
    def health():
        return {"ok": True, "env": s.APP_ENV}

    @app.get("/api/config")
    def public_config():
        return {"app_name": s.APP_NAME, "env": s.APP_ENV, "blockchain_enabled": s.BLOCKCHAIN_ENABLED, "blockchain_price": s.BLOCKCHAIN_PRICE,
                "mock_login": not s.is_production, "toss_provider": s.TOSS_PROVIDER, "max_upload_mb": s.MAX_UPLOAD_MB}

    app.include_router(routes.router)
    app.include_router(admin.router)
    return app


app = create_app()
