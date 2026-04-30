from pydantic import BaseModel, EmailStr

from app.schemas.common import OrmModel


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TotpVerifyRequest(BaseModel):
    code: str


class AdminRead(OrmModel):
    id: int
    email: EmailStr
    role: str
    is_active: bool
    totp_enabled: bool = False


class LoginResponse(BaseModel):
    requires_2fa: bool
    csrf_token: str | None = None
    admin: AdminRead | None = None

