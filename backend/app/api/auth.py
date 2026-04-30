from datetime import datetime, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    check_rate_limit,
    create_csrf_token,
    create_session,
    read_session,
    verify_password,
    verify_totp,
)
from app.db.session import get_db
from app.models import Admin
from app.schemas.auth import AdminRead, LoginRequest, LoginResponse, TotpVerifyRequest

router = APIRouter(prefix="/auth", tags=["auth"])


def _admin_read(admin: Admin) -> AdminRead:
    return AdminRead(
        id=admin.id,
        email=admin.email,
        role=admin.role,
        is_active=admin.is_active,
        totp_enabled=bool(admin.totp_secret),
    )


def _set_session_cookie(response: Response, value: str) -> None:
    response.set_cookie(
        settings.access_cookie_name,
        value,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        max_age=60 * 60 * 12,
    )


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> LoginResponse:
    key = f"{request.client.host if request.client else 'unknown'}:{payload.email}"
    if not check_rate_limit(key):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Слишком много попыток входа")
    admin = db.scalar(select(Admin).where(Admin.email == payload.email))
    if not admin or not admin.is_active or not verify_password(payload.password, admin.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный email или пароль")
    if admin.totp_secret:
        _set_session_cookie(response, create_session(admin.id, needs_2fa=True))
        return LoginResponse(requires_2fa=True)
    admin.last_login_at = datetime.now(timezone.utc)
    csrf = create_csrf_token(admin.id)
    _set_session_cookie(response, create_session(admin.id))
    response.set_cookie(settings.csrf_cookie_name, csrf, secure=settings.secure_cookies, samesite="lax")
    db.commit()
    return LoginResponse(requires_2fa=False, csrf_token=csrf, admin=_admin_read(admin))


@router.post("/2fa", response_model=LoginResponse)
def verify_2fa(
    payload: TotpVerifyRequest,
    response: Response,
    session_cookie: str | None = Cookie(default=None, alias=settings.access_cookie_name),
    db: Session = Depends(get_db),
) -> LoginResponse:
    session = read_session(session_cookie or "")
    if not session or not session.get("needs_2fa"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется сессия 2FA")
    admin = db.get(Admin, int(session["admin_id"]))
    if not admin or not verify_totp(admin.totp_secret, payload.code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный код 2FA")
    admin.last_login_at = datetime.now(timezone.utc)
    csrf = create_csrf_token(admin.id)
    _set_session_cookie(response, create_session(admin.id))
    response.set_cookie(settings.csrf_cookie_name, csrf, secure=settings.secure_cookies, samesite="lax")
    db.commit()
    return LoginResponse(requires_2fa=False, csrf_token=csrf, admin=_admin_read(admin))


@router.get("/me", response_model=AdminRead)
def me(request: Request, db: Session = Depends(get_db)) -> AdminRead:
    session = read_session(request.cookies.get(settings.access_cookie_name))
    if not session or session.get("needs_2fa"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется вход")
    admin = db.get(Admin, int(session["admin_id"]))
    if not admin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется вход")
    return _admin_read(admin)


@router.post("/logout")
def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(settings.access_cookie_name)
    response.delete_cookie(settings.csrf_cookie_name)
    return {"message": "ok"}
