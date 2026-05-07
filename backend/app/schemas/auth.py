from pydantic import BaseModel, EmailStr

from app.schemas.common import OrmModel


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TotpVerifyRequest(BaseModel):
    code: str
    login_token: str | None = None


class TotpSetupStartRequest(BaseModel):
    login_token: str | None = None


class TotpSetupConfirmRequest(BaseModel):
    code: str
    login_token: str | None = None


class TotpDisableRequest(BaseModel):
    password: str


class AdminRead(OrmModel):
    id: int
    email: EmailStr
    role: str
    is_active: bool
    totp_enabled: bool = False


class LoginResponse(BaseModel):
    requires_2fa: bool
    setup_required: bool = False
    login_token: str | None = None
    csrf_token: str | None = None
    admin: AdminRead | None = None


class TotpSetupStartResponse(BaseModel):
    secret: str
    otpauth_url: str
