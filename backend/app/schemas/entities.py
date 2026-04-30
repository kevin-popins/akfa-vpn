from datetime import datetime

import re

from pydantic import BaseModel, Field, field_validator

from app.constants import DEFAULT_DIRECT_DOMAINS
from app.schemas.common import ConfigApplySummaryRead, OrmModel
from app.services.domain_lists import normalize_blocked_domains
from app.services.reality import DEFAULT_REALITY_FINGERPRINT, DEFAULT_REALITY_SNI


SNI_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.IGNORECASE)


def validate_sni(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        raise ValueError("Укажите SNI / Reality target")
    if normalized.startswith(("https://", "http://")):
        raise ValueError("Укажите домен без http:// или https://")
    if "/" in normalized:
        raise ValueError("SNI не должен содержать путь или символ /")
    if any(char.isspace() for char in normalized):
        raise ValueError("SNI не должен содержать пробелы")
    if ":" in normalized:
        raise ValueError("Порт указывается отдельно, не добавляйте его в SNI")
    if len(normalized) > 253:
        raise ValueError("SNI слишком длинный")
    labels = normalized.split(".")
    if len(labels) < 2 or any(not label for label in labels):
        raise ValueError("Укажите корректный домен SNI")
    if any(len(label) > 63 or not SNI_LABEL_RE.match(label) for label in labels):
        raise ValueError("SNI содержит недопустимые символы")
    return normalized


class AccessProfileBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    routing_mode: str = "ru_direct"
    direct_domains: list[str] = Field(default_factory=lambda: DEFAULT_DIRECT_DOMAINS.copy())
    blocked_domains: list[str] = Field(default_factory=list)
    traffic_limit_bytes: int | None = None
    expires_in_days: int | None = None
    allowed_nodes: list[int] = Field(default_factory=list)
    client_template: str = "vless_uri"
    is_active: bool = True

    @field_validator("blocked_domains", mode="before")
    @classmethod
    def validate_blocked_domains(cls, value: list[str] | None) -> list[str]:
        return normalize_blocked_domains(value)


class AccessProfileCreate(AccessProfileBase):
    pass


class AccessProfileRead(AccessProfileBase, OrmModel):
    id: int


class DepartmentBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    default_access_profile_id: int | None = None


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentRead(DepartmentBase, OrmModel):
    id: int


class NodeBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    ip_address: str = Field(min_length=1, max_length=64)
    ssh_port: int = Field(default=22, ge=1, le=65535)
    ssh_username: str = Field(min_length=1, max_length=120)
    ssh_auth_type: str = "password"
    location: str | None = None
    public_host: str | None = None
    vless_port: int = Field(default=443, ge=1, le=65535)
    sni: str = Field(default=DEFAULT_REALITY_SNI, min_length=1, max_length=255)
    fingerprint: str = DEFAULT_REALITY_FINGERPRINT
    xray_config_path: str = "/usr/local/etc/xray/config.json"
    xray_service_name: str = "xray"

    @field_validator("sni")
    @classmethod
    def validate_reality_sni(cls, value: str) -> str:
        return validate_sni(value)


class NodeCreate(NodeBase):
    ssh_password: str | None = None
    private_key: str | None = None


class NodeUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    ip_address: str = Field(min_length=1, max_length=64)
    location: str | None = None
    public_host: str | None = None
    vless_port: int = Field(default=443, ge=1, le=65535)
    sni: str = Field(default=DEFAULT_REALITY_SNI, min_length=1, max_length=255)
    fingerprint: str = DEFAULT_REALITY_FINGERPRINT
    xray_config_path: str = "/usr/local/etc/xray/config.json"
    xray_service_name: str = "xray"

    @field_validator("sni")
    @classmethod
    def validate_reality_sni(cls, value: str) -> str:
        return validate_sni(value)


class NodeRead(NodeBase, OrmModel):
    id: int
    reality_public_key: str | None = None
    short_id: str | None = None
    status: str
    last_check_at: datetime | None = None
    last_config_applied_at: datetime | None = None
    last_config_apply_status: str = "pending"
    last_config_apply_error: str | None = None
    last_config_version: str | None = None
    created_at: datetime
    install_log: list[dict] = Field(default_factory=list)
    apply_status: ConfigApplySummaryRead | None = None


class NodeMetricsRead(BaseModel):
    node_id: int
    name: str
    ip_address: str
    status: str
    cpu_percent: float | None = None
    ram_used_bytes: int | None = None
    ram_total_bytes: int | None = None
    ram_percent: float | None = None
    disk_used_bytes: int | None = None
    disk_total_bytes: int | None = None
    disk_percent: float | None = None
    traffic_upload_bytes: int = 0
    traffic_download_bytes: int = 0
    traffic_total_bytes: int = 0
    traffic_source: str = "users_sum_fallback"
    last_checked_at: datetime | None = None
    errors: list[str] = Field(default_factory=list)


class VpnUserBase(BaseModel):
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)
    username: str = Field(min_length=1, max_length=120)
    department_id: int | None = None
    access_profile_id: int | None = None
    allowed_node_ids: list[int] = Field(default_factory=list)
    primary_node_id: int | None = None
    traffic_limit_bytes: int | None = None
    expires_at: datetime | None = None
    status: str = "active"


class VpnUserCreate(VpnUserBase):
    pass


class VpnUserRead(VpnUserBase, OrmModel):
    id: int
    uuid: str
    subscription_token: str
    access_status: str
    online_status: str
    used_upload_bytes: int
    used_download_bytes: int
    used_total_bytes: int
    last_seen_delta_bytes: int
    last_traffic_collected_at: datetime | None = None
    last_online_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    apply_status: ConfigApplySummaryRead | None = None


class BulkImportResult(BaseModel):
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = Field(default_factory=list)
    users: list[VpnUserRead] = Field(default_factory=list)
    apply_status: ConfigApplySummaryRead | None = None


class RestoreSummary(BaseModel):
    restored: dict[str, int] = Field(default_factory=dict)
    apply_status: ConfigApplySummaryRead | None = None


class TrafficSnapshotRead(OrmModel):
    id: int
    vpn_user_id: int
    node_id: int
    upload_bytes: int
    download_bytes: int
    total_bytes: int
    collected_at: datetime


class TrafficUserRead(BaseModel):
    id: int
    username: str
    first_name: str
    last_name: str
    status: str
    access_status: str
    online_status: str
    upload_bytes: int = 0
    download_bytes: int = 0
    total_bytes: int = 0
    last_seen_delta_bytes: int = 0
    last_online_at: datetime | None = None
    last_traffic_collected_at: datetime | None = None
    traffic_limit_bytes: int | None = None
    collected: bool = False


class SniCheckRequest(BaseModel):
    sni: str

    @field_validator("sni")
    @classmethod
    def validate_reality_sni(cls, value: str) -> str:
        return validate_sni(value)


class SniCheckResponse(BaseModel):
    sni: str
    dns_ok: bool
    tcp_443_ok: bool
    tls_ok: bool
    latency_ms: int | None = None
    certificate_summary: str | None = None
    errors: list[str] = Field(default_factory=list)


class SshCheckResponse(BaseModel):
    ok: bool
    logs: list[dict] = Field(default_factory=list)
