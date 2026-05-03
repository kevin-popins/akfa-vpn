from datetime import datetime, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_admin, require_write
from app.core.config import settings
from app.core.security import (
    check_rate_limit,
    create_csrf_token,
    create_login_token,
    create_session,
    new_totp_secret,
    read_login_token,
    read_session,
    totp_uri,
    verify_password,
    verify_totp,
)
from app.db.session import get_db
from app.models import Admin
from app.schemas.auth import (
    AdminRead,
    LoginRequest,
    LoginResponse,
    TotpDisableRequest,
    TotpSetupConfirmRequest,
    TotpSetupStartRequest,
    TotpSetupStartResponse,
    TotpVerifyRequest,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _active_totp_secret(admin: Admin) -> str | None:
    return admin.totp_secret if admin.totp_enabled or admin.totp_secret else None


def _admin_read(admin: Admin) -> AdminRead:
    return AdminRead(
        id=admin.id,
        email=admin.email,
        role=admin.role,
        is_active=admin.is_active,
        totp_enabled=bool(admin.totp_enabled or admin.totp_secret),
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


def _complete_login(admin: Admin, response: Response, db: Session) -> LoginResponse:
    admin.last_login_at = datetime.now(timezone.utc)
    csrf = create_csrf_token(admin.id)
    _set_session_cookie(response, create_session(admin.id))
    response.set_cookie(settings.csrf_cookie_name, csrf, secure=settings.secure_cookies, samesite="lax")
    db.commit()
    return LoginResponse(requires_2fa=False, csrf_token=csrf, admin=_admin_read(admin))


def _admin_from_login_token(db: Session, token: str | None, purpose: str) -> Admin:
    data = read_login_token(token, purpose)
    if not data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Временный токен входа истек")
    admin = db.get(Admin, int(data["admin_id"]))
    if not admin or not admin.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется вход")
    return admin


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> LoginResponse:
    key = f"{request.client.host if request.client else 'unknown'}:{payload.email}"
    if not check_rate_limit(key):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Слишком много попыток входа")
    admin = db.scalar(select(Admin).where(Admin.email == payload.email))
    if not admin or not admin.is_active or not verify_password(payload.password, admin.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный email или пароль")
    if admin.totp_enabled or admin.totp_secret:
        return LoginResponse(requires_2fa=True, login_token=create_login_token(admin.id, "totp_verify"))
    if admin.totp_required:
        return LoginResponse(
            requires_2fa=False,
            setup_required=True,
            login_token=create_login_token(admin.id, "totp_setup"),
        )
    return _complete_login(admin, response, db)


@router.post("/2fa/verify", response_model=LoginResponse)
def verify_2fa(payload: TotpVerifyRequest, response: Response, db: Session = Depends(get_db)) -> LoginResponse:
    admin = _admin_from_login_token(db, payload.login_token, "totp_verify")
    if not verify_totp(_active_totp_secret(admin), payload.code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный код 2FA")
    return _complete_login(admin, response, db)


@router.post("/2fa", response_model=LoginResponse)
def verify_legacy_2fa(
    payload: TotpVerifyRequest,
    response: Response,
    session_cookie: str | None = Cookie(default=None, alias=settings.access_cookie_name),
    db: Session = Depends(get_db),
) -> LoginResponse:
    if payload.login_token:
        return verify_2fa(payload, response, db)
    session = read_session(session_cookie or "")
    if not session or not session.get("needs_2fa"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется сессия 2FA")
    admin = db.get(Admin, int(session["admin_id"]))
    if not admin or not verify_totp(_active_totp_secret(admin), payload.code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный код 2FA")
    return _complete_login(admin, response, db)


def _admin_from_session(db: Session, session_cookie: str | None) -> Admin | None:
    session = read_session(session_cookie)
    if not session or session.get("needs_2fa"):
        return None
    admin = db.get(Admin, int(session["admin_id"]))
    return admin if admin and admin.is_active else None


@router.post("/2fa/setup/start", response_model=TotpSetupStartResponse)
def setup_start(
    payload: TotpSetupStartRequest | None = None,
    session_cookie: str | None = Cookie(default=None, alias=settings.access_cookie_name),
    db: Session = Depends(get_db),
) -> TotpSetupStartResponse:
    target = _admin_from_session(db, session_cookie)
    if payload and payload.login_token:
        target = _admin_from_login_token(db, payload.login_token, "totp_setup")
    if target is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется вход")
    target.totp_secret = target.totp_secret or new_totp_secret()
    db.commit()
    return TotpSetupStartResponse(secret=target.totp_secret, otpauth_url=totp_uri(target.totp_secret, target.email))


@router.post("/2fa/setup/confirm", response_model=LoginResponse)
def setup_confirm(
    payload: TotpSetupConfirmRequest,
    response: Response,
    session_cookie: str | None = Cookie(default=None, alias=settings.access_cookie_name),
    db: Session = Depends(get_db),
) -> LoginResponse:
    admin = _admin_from_login_token(db, payload.login_token, "totp_setup") if payload.login_token else _admin_from_session(db, session_cookie)
    if admin is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется вход")
    if not verify_totp(admin.totp_secret, payload.code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный код 2FA")
    admin.totp_enabled = True
    admin.totp_required = False
    admin.totp_confirmed_at = datetime.now(timezone.utc)
    return _complete_login(admin, response, db)


@router.post("/2fa/disable", response_model=AdminRead)
def disable_2fa(payload: TotpDisableRequest, admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> AdminRead:
    if not verify_password(payload.password, admin.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный пароль")
    admin.totp_secret = None
    admin.totp_secret_encrypted = None
    admin.totp_enabled = False
    admin.totp_required = False
    admin.totp_confirmed_at = None
    db.commit()
    return _admin_read(admin)


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
