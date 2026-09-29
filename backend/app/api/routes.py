"""HTTP API."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.logging import mask_name
from app.core.security import clear_session, current_user, issue_session, issue_token
from app.models import User
from app.providers import get_ocr, get_toss_login
from app.providers.base import ProviderError, ProviderNotConfigured
from app.services import anchoring, catalog, evidence, pdf_engine, verification
from app.services import contracts as svc
from app.services.fields import FieldSpec, Suggestion, apply_suggestions, suggest_fields

router = APIRouter(prefix="/api")


def _pdf(data: bytes, filename: str) -> Response:
    return Response(data, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{filename}"', "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})


# ---------------- 인증 ----------------

class LoginIn(BaseModel):
    authorization_code: str = Field(min_length=1, max_length=512)
    referrer: str = Field(default="DEFAULT", pattern="^(DEFAULT|SANDBOX)$")


def _login(db: Session, response: Response, provider_name: str, user_key: str, name: str, token_mode: bool = False) -> dict:
    from sqlalchemy import select

    u = db.scalar(select(User).where(User.provider == provider_name, User.provider_user_key == user_key))
    if u is None:
        u = User(provider=provider_name, provider_user_key=user_key, display_name_masked=mask_name(name))
        db.add(u)
        db.commit()
    if token_mode:
        # 앱인토스 번들: 쿠키 대신 Bearer 토큰 (메모리에만 보관)
        return {"user": {"id": u.id, "name": u.display_name_masked}, "access_token": issue_token(u), "token_type": "Bearer"}
    csrf = issue_session(response, u)
    return {"user": {"id": u.id, "name": u.display_name_masked}, "csrf_token": csrf}


@router.post("/auth/toss/login")
def toss_login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    prov = get_toss_login()
    try:
        ident = prov.exchange(body.authorization_code, body.referrer)
    except ProviderError as e:
        raise HTTPException(401, detail={"code": "LOGIN_FAILED", "message": str(e)}) from e
    return _login(db, response, "toss" if prov.name == "production" else "toss-mock", ident.user_key, ident.name,
                  token_mode=request.headers.get("X-Auth-Mode") == "token")


class MockLoginIn(BaseModel):
    test_user: str = Field(pattern="^(hong|kim|lee|park)$")


@router.post("/auth/mock-login")
def mock_login(body: MockLoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    """개발용 테스트 계정 로그인 (production 에서는 비활성화)."""
    if get_settings().is_production:
        raise HTTPException(404)
    from app.providers.toss import MockTossLoginProvider

    ident = MockTossLoginProvider().exchange(f"mock-code-{body.test_user}", "SANDBOX")
    return _login(db, response, "toss-mock", ident.user_key, ident.name, token_mode=request.headers.get("X-Auth-Mode") == "token")


@router.get("/auth/me")
def me(request: Request, user: User = Depends(current_user)):
    return {"user": {"id": user.id, "name": user.display_name_masked}, "csrf_token": request.cookies.get("kz_csrf")}


@router.post("/auth/logout")
def logout(response: Response):
    clear_session(response)
    return {"ok": True}


# ---------------- 템플릿 / 빈칸 추천 ----------------

@router.get("/templates")
def templates():
    return {"templates": catalog.list_templates()}


@router.get("/templates/{tid}")
def template(tid: str):
    if tid not in catalog.TEMPLATES:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "템플릿이 없어요."})
    return catalog.get_template(tid)


class SuggestIn(BaseModel):
    text: str = Field(max_length=svc.MAX_BODY)
    existing_labels: list[str] = Field(default_factory=list, max_length=200)


@router.post("/fields/suggest")
def fields_suggest(body: SuggestIn, user: User = Depends(current_user)):
    return {"suggestions": [s.model_dump() for s in suggest_fields(body.text, set(body.existing_labels))]}


class ApplyIn(BaseModel):
    text: str = Field(max_length=svc.MAX_BODY)
    suggestions: list[Suggestion] = Field(max_length=200)


@router.post("/fields/apply")
def fields_apply(body: ApplyIn, user: User = Depends(current_user)):
    try:
        text = apply_suggestions(body.text, body.suggestions)
    except ValueError as e:
        raise HTTPException(409, detail={"code": "STALE_SUGGESTION", "message": str(e)}) from e
    from app.services.fields import default_validation

    fields = [FieldSpec(label=s.label, type=s.type, required=s.required, assignee=s.assignee, options=s.options,
                        validation=default_validation(s.type)).model_dump() for s in body.suggestions]
    return {"text": text, "fields": fields}


# ---------------- PDF 업로드 (계약 생성 전 분석) ----------------

@router.post("/uploads/pdf/analyze")
async def analyze_pdf(file: UploadFile = File(...), user: User = Depends(current_user)):
    data = await file.read(get_settings().MAX_UPLOAD_MB * 1024 * 1024 + 1)
    try:
        pdf_engine.validate_pdf_upload(data, file.filename or "", file.content_type)
        ocr = None
        try:
            ocr = get_ocr()
        except ProviderNotConfigured:
            ocr = None
        res = pdf_engine.extract_pdf(data, ocr)
    except pdf_engine.UploadError as e:
        raise HTTPException(422, detail={"code": "INVALID_UPLOAD", "message": str(e)}) from e
    except ProviderNotConfigured as e:
        raise HTTPException(503, detail={"code": "OCR_UNAVAILABLE", "message": str(e)}) from e
    return {
        "pages": [{"width": p.width, "height": p.height, "ocr": p.ocr, "text": p.text} for p in res.pages],
        "text": res.text, "ocr_used": res.ocr_used,
        "suggestions": [s.model_dump() for s in suggest_fields(res.text)],
        "position_suggestions": res.position_suggestions,
    }


# ---------------- 계약 ----------------

class CreateIn(BaseModel):
    title: str = Field(max_length=100)
    contract_type: str = Field(default="general", max_length=32)
    source: str = Field(default="TEXT", pattern="^(TEXT|TEMPLATE)$")
    body_text: str = Field(default="", max_length=svc.MAX_BODY)
    fields: list[FieldSpec] = Field(default_factory=list, max_length=200)


@router.post("/contracts")
def create_contract(body: CreateIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = svc.create_contract(db, user, title=body.title, contract_type=body.contract_type, source=body.source,
                            body_text=body.body_text, fields=body.fields)
    return {"id": c.id}


@router.post("/contracts/upload")
async def create_from_pdf(file: UploadFile = File(...), title: str = Form(..., max_length=100), contract_type: str = Form("general"),
                          fields_json: str = Form("[]"), db: Session = Depends(get_db), user: User = Depends(current_user)):
    import json

    data = await file.read(get_settings().MAX_UPLOAD_MB * 1024 * 1024 + 1)
    try:
        pdf_engine.validate_pdf_upload(data, file.filename or "", file.content_type)
    except pdf_engine.UploadError as e:
        raise HTTPException(422, detail={"code": "INVALID_UPLOAD", "message": str(e)}) from e
    try:
        fields = [FieldSpec(**f) for f in json.loads(fields_json)]
    except Exception as e:  # noqa: BLE001
        raise HTTPException(422, detail={"code": "INVALID_FIELDS", "message": "빈칸 정보가 올바르지 않아요."}) from e
    c = svc.create_contract(db, user, title=title, contract_type=contract_type, source="PDF", body_text="", fields=fields, source_pdf=data)
    return {"id": c.id}


@router.get("/contracts")
def my_contracts(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return {"contracts": svc.list_my_contracts(db, user)}


@router.get("/contracts/{cid}")
def get_contract(cid: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c, p = svc.get_contract_for(db, cid, user)
    svc.record_view(db, c, p)
    return svc.contract_view(db, c, p)


class UpdateIn(BaseModel):
    title: str | None = Field(default=None, max_length=100)
    body_text: str | None = Field(default=None, max_length=svc.MAX_BODY)
    fields: list[FieldSpec] = Field(max_length=200)
    reason: str = Field(default="내용 수정", max_length=100)


@router.put("/contracts/{cid}/content")
def update_content(cid: str, body: UpdateIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c, p = svc.get_contract_for(db, cid, user)
    v = svc.update_content(db, c, p, title=body.title, body_text=body.body_text, fields=body.fields, reason=body.reason)
    return {"version_no": v.version_no, "content_hash": v.content_hash}


class ValuesIn(BaseModel):
    values: dict[str, Any] = Field(max_length=200)


@router.put("/contracts/{cid}/values")
def fill_values(cid: str, body: ValuesIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c, p = svc.get_contract_for(db, cid, user)
    v = svc.fill_values(db, c, p, body.values)
    return {"version_no": v.version_no, "content_hash": v.content_hash}


@router.post("/contracts/{cid}/ready")
def ready(cid: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c, p = svc.get_contract_for(db, cid, user)
    svc.mark_ready(db, c, p)
    return {"status": c.status}


@router.post("/contracts/{cid}/invite")
def invite(cid: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c, p = svc.get_contract_for(db, cid, user)
    return svc.invite(db, c, p)


@router.post("/contracts/{cid}/cancel")
def cancel(cid: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c, p = svc.get_contract_for(db, cid, user)
    svc.cancel(db, c, p)
    return {"status": c.status}


@router.get("/invites/{token}")
def invite_preview(token: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return svc.invite_preview(db, token)


@router.post("/invites/{token}/accept")
def invite_accept(token: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = svc.accept_invite(db, token, user)
    return {"contract_id": c.id}


class IdentityIn(BaseModel):
    session_id: str = Field(max_length=64)
    fail: bool = False


@router.post("/contracts/{cid}/identity/start")
def identity_start(cid: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c, p = svc.get_contract_for(db, cid, user)
    return svc.identity_start(db, c, p)


@router.post("/contracts/{cid}/identity/complete")
def identity_complete(cid: str, body: IdentityIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c, p = svc.get_contract_for(db, cid, user)
    svc.identity_complete(db, c, p, body.session_id, {"fail": body.fail})
    return {"identity_status": p.identity_status}


class ReviewIn(BaseModel):
    version_no: int
    content_checked: bool
    own_will: bool
    e_signature_consent: bool


@router.post("/contracts/{cid}/review")
def review(cid: str, body: ReviewIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c, p = svc.get_contract_for(db, cid, user)
    svc.review(db, c, p, body.version_no, body.model_dump())
    return {"reviewed_version_no": p.reviewed_version_no}


@router.post("/contracts/{cid}/sign/start")
def sign_start(cid: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c, p = svc.get_contract_for(db, cid, user)
    return svc.sign_start(db, c, p)


class SignIn(BaseModel):
    request_id: str = Field(max_length=64)
    version_no: int
    signature_image: str = Field(max_length=450_000)


@router.post("/contracts/{cid}/sign/complete")
def sign_complete(cid: str, body: SignIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c, p = svc.get_contract_for(db, cid, user)
    return svc.sign_complete(db, c, p, body.request_id, body.version_no, body.signature_image)


@router.get("/contracts/{cid}/versions/{a}/diff/{b}")
def diff(cid: str, a: int, b: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c, _ = svc.get_contract_for(db, cid, user)
    return svc.version_diff(db, c, a, b)


@router.get("/contracts/{cid}/events")
def events(cid: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c, _ = svc.get_contract_for(db, cid, user)
    return {"events": [evidence.to_dict(e) for e in evidence.list_events(db, c.id)], "chain_valid": evidence.verify_chain(db, c.id)}


@router.get("/contracts/{cid}/pdf/contract")
def pdf_contract(cid: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c, _ = svc.get_contract_for(db, cid, user)
    return _pdf(*svc.contract_pdf(db, c))


@router.get("/contracts/{cid}/pdf/preview")
def pdf_preview(cid: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c, _ = svc.get_contract_for(db, cid, user)
    return _pdf(svc.preview_pdf(db, c), f"{c.contract_no}-preview.pdf")


@router.get("/contracts/{cid}/pdf/certificate")
def pdf_certificate(cid: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c, _ = svc.get_contract_for(db, cid, user)
    return _pdf(*svc.certificate_pdf(db, c, user.id))


@router.get("/contracts/{cid}/source.pdf")
def source_pdf(cid: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c, _ = svc.get_contract_for(db, cid, user)
    return Response(svc.source_pdf_bytes(db, c), media_type="application/pdf", headers={"Cache-Control": "no-store"})


@router.get("/contracts/{cid}/signatures/{sig}")
def signature(cid: str, sig: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c, _ = svc.get_contract_for(db, cid, user)
    return Response(svc.signature_image(db, c, sig), media_type="image/png", headers={"Cache-Control": "no-store"})


@router.post("/contracts/{cid}/retention/extend")
def extend(cid: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c, p = svc.get_contract_for(db, cid, user)
    svc.extend_retention(db, c, p)
    return {"purge_at": c.purge_at.isoformat() if c.purge_at else None}


# ---------------- 결제 / 블록체인 ----------------

@router.post("/contracts/{cid}/anchor/checkout")
def anchor_checkout(cid: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c, _ = svc.get_contract_for(db, cid, user)
    return anchoring.checkout(db, c, user)


class ConfirmIn(BaseModel):
    payment_id: str = Field(max_length=32)
    result: str = Field(default="success", pattern="^(success|fail|cancel)$")
    provider_payload: dict = Field(default_factory=dict)


@router.post("/contracts/{cid}/anchor/confirm")
def anchor_confirm(cid: str, body: ConfirmIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c, _ = svc.get_contract_for(db, cid, user)
    return anchoring.confirm_payment(db, c, user, body.payment_id, {"result": body.result, **body.provider_payload})


@router.get("/contracts/{cid}/anchor")
def anchor_status(cid: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c, _ = svc.get_contract_for(db, cid, user)
    job = svc.latest_anchor(db, c)
    pay = svc.latest_payment(db, c)
    return {"anchor": svc.anchor_view(job), "payment": {"status": pay.status if pay else "NONE"}}


@router.post("/contracts/{cid}/anchor/retry")
def anchor_retry(cid: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c, _ = svc.get_contract_for(db, cid, user)
    job = svc.latest_anchor(db, c)
    if job is None:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "기록 요청이 없어요."})
    if job.status in ("RETRY", "PENDING", "SUBMITTED"):
        job = anchoring.process_job(db, job.id)
    return {"anchor": svc.anchor_view(job)}


# ---------------- 공개 검증 ----------------

@router.get("/verify/{vid}")
def verify_lookup(vid: str, db: Session = Depends(get_db)):
    try:
        return verification.lookup(db, vid)
    except verification.VerifyError as e:
        raise HTTPException(e.status, detail={"code": "NOT_FOUND", "message": e.message}) from e


class CheckIn(BaseModel):
    document_hash: str = Field(max_length=80)
    verification_id: str | None = Field(default=None, max_length=24)


@router.post("/verify/check")
def verify_check(body: CheckIn, db: Session = Depends(get_db)):
    try:
        return verification.check(db, body.verification_id, body.document_hash)
    except verification.VerifyError as e:
        raise HTTPException(e.status, detail={"code": "VERIFY_ERROR", "message": e.message}) from e


@router.post("/verify/upload")
async def verify_upload(file: UploadFile = File(...), verification_id: str | None = Form(None), db: Session = Depends(get_db)):
    """서버측 검증 (파일은 저장하지 않고 Hash 만 계산)."""
    from app.services.hashing import sha256_bytes

    data = await file.read(get_settings().MAX_UPLOAD_MB * 1024 * 1024 + 1)
    try:
        pdf_engine.validate_pdf_upload(data, file.filename or "", file.content_type)
    except pdf_engine.UploadError as e:
        raise HTTPException(422, detail={"code": "INVALID_UPLOAD", "message": str(e)}) from e
    try:
        return verification.check(db, verification_id, sha256_bytes(data))
    except verification.VerifyError as e:
        raise HTTPException(e.status, detail={"code": "VERIFY_ERROR", "message": e.message}) from e


def error_response(e: svc.ContractError) -> JSONResponse:
    return JSONResponse(status_code=e.status, content={"detail": {"code": e.code, "message": e.message, **e.extra}})
