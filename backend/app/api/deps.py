from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import read_session, verify_csrf_token
from app.db.session import get_db
from app.models import Admin


def current_admin(
    request: Request,
    db: Session = Depends(get_db),
    session_cookie: str | None = Cookie(default=None, alias=settings.access_cookie_name),
) -> Admin:
    session = read_session(session_cookie)
    if not session or session.get("needs_2fa"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется вход")
    admin = db.get(Admin, int(session["admin_id"]))
    if not admin or not admin.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется вход")
    request.state.admin = admin
    return admin


def require_write(
    request: Request,
    admin: Admin = Depends(current_admin),
    csrf_header: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> Admin:
    if admin.role == "read_only":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Администратор доступен только для чтения")
    if not verify_csrf_token(csrf_header, admin.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Неверный CSRF-токен")
    request.state.admin = admin
    return admin
