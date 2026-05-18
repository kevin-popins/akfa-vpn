from datetime import datetime
from urllib.parse import urlparse

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
    ssh_host_key_fingerprint: str | None = None
    reality_public_key: str | None = None
    xray_installed: bool = False
    managed_mode: str = "akfa_owned"
    inbound_tag: str | None = None
    import_status: str | None = None
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


class NodeActionJobAccepted(BaseModel):
    job_id: str
    status: str
    current_step: str


class NodeActionJobRead(BaseModel):
    job_id: str
    node_id: int
    action: str
    status: str
    current_step: str
    logs: list[dict] = Field(default_factory=list)
    error: str | None = None
    result: dict | None = None
    created_at: datetime
    updated_at: datetime


class NodeBulkUserRequest(BaseModel):
    scope: str = "all_active"
    department_id: int | None = None
    access_profile_id: int | None = None
    user_ids: list[int] = Field(default_factory=list)


class NodeProfileActionRequest(BaseModel):
    profile_id: int


class NodeReplaceRequest(BaseModel):
    new_node_id: int


class NodeBulkActionResult(BaseModel):
    ok: bool = True
    message: str
    users_changed: int = 0
    profiles_changed: int = 0
    affected_node_ids: list[int] = Field(default_factory=list)
    apply_status: ConfigApplySummaryRead | None = None
    apply_error: str | None = None
    errors: list[str] = Field(default_factory=list)


class NodeMetricsRead(BaseModel):
    node_id: int
    name: str
    ip_address: str
    status: str
    metrics_status: str = "pending"
    metrics_error: str | None = None
    cpu_percent: float | None = None
    ram_used_bytes: int | None = None
    ram_total_bytes: int | None = None
    ram_percent: float | None = None
    disk_used_bytes: int | None = None
    disk_total_bytes: int | None = None
    disk_percent: float | None = None
    vpn_traffic_upload_bytes: int = 0
    vpn_traffic_download_bytes: int = 0
    vpn_traffic_total_bytes: int = 0
    vpn_traffic_source: str = "xray_stats"
    traffic_upload_bytes: int = 0
    traffic_download_bytes: int = 0
    traffic_total_bytes: int = 0
    traffic_type: str = "vpn_xray"
    traffic_source: str = "node_traffic"
    system_traffic_upload_bytes: int | None = None
    system_traffic_download_bytes: int | None = None
    system_traffic_total_bytes: int | None = None
    system_traffic_source: str = "unavailable"
    system_traffic_interface: str | None = None
    system_traffic_available: bool = False
    system_traffic_error: str | None = None
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
    device_limit: int = Field(default=5, ge=1, le=100)
    traffic_limit_bytes: int | None = None
    expires_at: datetime | None = None
    status: str = "active"


class VpnUserCreate(VpnUserBase):
    pass


class VpnUserRead(VpnUserBase, OrmModel):
    id: int
    uuid: str
    subscription_token: str
    connect_url: str | None = None
    devices_label: str = "0/5"
    active_devices_count: int = 0
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
    apply_error: str | None = None


class VpnUserDeviceRead(OrmModel):
    id: int
    vpn_user_id: int
    name: str | None = None
    display_name: str | None = None
    uuid: str
    status: str
    hwid_masked: str | None = None
    platform: str | None = None
    client_name: str | None = None
    device_model: str | None = None
    os_version: str | None = None
    app_version: str | None = None
    user_agent: str | None = None
    created_ip: str | None = None
    ip_address: str | None = None
    last_ip_address: str | None = None
    upload_bytes: int = 0
    download_bytes: int = 0
    total_bytes: int = 0
    last_seen_delta_bytes: int = 0
    online_status: str = "offline"
    activated_at: datetime | None = None
    last_seen_at: datetime | None = None
    last_subscribed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class VpnUserDeviceUpdate(BaseModel):
    name: str | None = None
    display_name: str | None = None
    status: str | None = None


class PublicHelpLinks(BaseModel):
    android_happ_url: str | None = None
    iphone_happ_url: str | None = None
    windows_fclashx_url: str | None = None
    macos_fclashx_url: str | None = None

    @field_validator("*", mode="before")
    @classmethod
    def validate_public_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized:
            return None
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Укажите корректный URL или оставьте поле пустым")
        return normalized


class SubscriptionSettings(BaseModel):
    title: str = Field(default="AKFA VPN", min_length=1, max_length=120)
    filename: str = Field(default="akfa-vpn", min_length=1, max_length=80)
    announcement: str = Field(default="", max_length=1200)
    update_interval_hours: int = Field(default=12, ge=1, le=168)
    server_prefix: str = Field(default="AKFA", min_length=1, max_length=48)

    @field_validator("title", "filename", "server_prefix", mode="before")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Поле не может быть пустым")
        return normalized

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        if any(char in value for char in ["\\", "/", "\x00"]):
            raise ValueError("Имя файла не должно содержать / или \\")
        return value.strip(". ")

    @field_validator("announcement", mode="before")
    @classmethod
    def validate_announcement(cls, value: str | None) -> str:
        return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()


class PublicConnectRead(BaseModel):
    display_name: str
    status: str
    expires_at: datetime | None = None
    traffic_limit: int | None = None
    used_traffic: int = 0
    device_limit: int
    active_devices_count: int
    devices_label: str
    devices: list[VpnUserDeviceRead] = Field(default_factory=list)
    help_links: PublicHelpLinks = Field(default_factory=PublicHelpLinks)


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
    vpn_user_id: int | None = None
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
    devices_label: str = "0/5"
    active_devices_count: int = 0
    device_limit: int = 5
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


class XrayProbeRequest(NodeCreate):
    pass


class XrayProbeResponse(BaseModel):
    ssh_ok: bool = False
    xray_installed: bool = False
    xray_version: str | None = None
    service_active: bool | None = None
    service_enabled: bool | None = None
    config_found: bool = False
    config_valid: bool = False
    reality_inbound_found: bool = False
    partial_import_required: bool = False
    manual_public_key_required: bool = False
    public_key_missing: bool = False
    error: str | None = None
    inbound_tag: str | None = None
    listen: str | None = None
    port: int | None = None
    clients_count: int = 0
    server_names: list[str] = Field(default_factory=list)
    dest: str | None = None
    private_key: str | None = None
    public_key: str | None = None
    short_ids: list[str] = Field(default_factory=list)
    network: str | None = None
    security: str | None = None
    logs: list[dict] = Field(default_factory=list)
    raw_config: dict | None = None
    inbound: dict | None = None


class XrayImportRequest(BaseModel):
    probe: XrayProbeResponse | None = None
    public_key: str | None = None
