import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Request

from app.models import VpnUserDevice


@dataclass(frozen=True)
class HwidContext:
    raw_hwid: str
    normalized_hwid: str
    hwid_hash: str
    hwid_masked: str
    platform: str | None
    client_name: str | None
    device_model: str | None
    os_version: str | None
    app_version: str | None
    user_agent: str | None
    ip_address: str | None
    display_name: str


def normalize_x_hwid(value: str) -> str:
    return re.sub(r"\s+", "", value.strip()).lower()


def hash_hwid(normalized_x_hwid: str) -> str:
    return hashlib.sha256(normalized_x_hwid.encode("utf-8")).hexdigest()


def mask_hwid(normalized_x_hwid: str) -> str:
    if len(normalized_x_hwid) <= 12:
        return f"{normalized_x_hwid[:2]}...{normalized_x_hwid[-2:]}" if len(normalized_x_hwid) > 4 else "***"
    return f"{normalized_x_hwid[:6]}...{normalized_x_hwid[-4:]}"


def request_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else None


def normalize_label(value: str | None) -> str | None:
    if not value:
        return None
    normalized = " ".join(value.strip().split())
    return normalized[:160] or None


def nice_client_name(client: str | None, user_agent: str | None) -> str | None:
    value = normalize_label(client)
    if value:
        mapping = {
            "happ": "Happ",
            "fclashx": "FClashX",
            "flclash": "FClashX",
            "v2rayn": "v2rayN",
            "streisand": "Streisand",
        }
        return mapping.get(value.lower(), value)
    ua = (user_agent or "").lower()
    for key, label in [
        ("happ", "Happ"),
        ("flclash", "FClashX"),
        ("fclash", "FClashX"),
        ("v2rayn", "v2rayN"),
        ("streisand", "Streisand"),
    ]:
        if key in ua:
            return label
    return None


def nice_platform(platform: str | None, user_agent: str | None) -> str | None:
    value = normalize_label(platform)
    if value:
        mapping = {
            "android": "Android",
            "windows": "Windows",
            "iphone": "iPhone",
            "ios": "iPhone",
            "ipad": "iPad",
            "macos": "macOS",
            "darwin": "macOS",
        }
        return mapping.get(value.lower(), value)
    ua = (user_agent or "").lower()
    for key, label in [("android", "Android"), ("windows", "Windows"), ("iphone", "iPhone"), ("ipad", "iPad"), ("mac", "macOS")]:
        if key in ua:
            return label
    return None


def build_display_name(
    *,
    device_model: str | None,
    platform: str | None,
    os_version: str | None,
    client_name: str | None,
    device_id: int | None = None,
) -> str:
    parts: list[str] = []
    if device_model:
        parts.append(device_model)
    if platform:
        parts.append(f"{platform} {os_version}".strip() if os_version else platform)
    if client_name:
        parts.append(client_name)
    if parts:
        return " · ".join(parts)
    suffix = f"DEV-{device_id}" if device_id else "Новое устройство"
    return suffix


def compute_hwid_context(request: Request, platform: str | None, client: str | None) -> HwidContext | None:
    raw = request.headers.get("x-hwid")
    if not raw or not raw.strip():
        return None
    normalized = normalize_x_hwid(raw)
    if not normalized:
        return None
    user_agent = normalize_label(request.headers.get("user-agent"))
    normalized_platform = nice_platform(request.headers.get("x-device-os") or platform, user_agent)
    normalized_client = nice_client_name(client, user_agent)
    device_model = normalize_label(request.headers.get("x-device-model"))
    os_version = normalize_label(request.headers.get("x-ver-os"))
    app_version = normalize_label(request.headers.get("x-app-version"))
    display_name = build_display_name(
        device_model=device_model,
        platform=normalized_platform,
        os_version=os_version,
        client_name=normalized_client,
    )
    return HwidContext(
        raw_hwid=raw,
        normalized_hwid=normalized,
        hwid_hash=hash_hwid(normalized),
        hwid_masked=mask_hwid(normalized),
        platform=normalized_platform,
        client_name=normalized_client,
        device_model=device_model,
        os_version=os_version,
        app_version=app_version,
        user_agent=user_agent,
        ip_address=request_ip(request),
        display_name=display_name,
    )


def apply_device_metadata(device: VpnUserDevice, context: HwidContext, *, created: bool = False) -> None:
    now = datetime.now(timezone.utc)
    if created:
        device.hwid_hash = context.hwid_hash
        device.hwid_masked = context.hwid_masked
        device.hwid_bound_at = now
        device.activated_at = now
        device.created_ip = context.ip_address
    device.platform = context.platform or device.platform
    device.client_name = context.client_name or device.client_name
    device.device_model = context.device_model or device.device_model
    device.os_version = context.os_version or device.os_version
    device.app_version = context.app_version or device.app_version
    device.user_agent = context.user_agent or device.user_agent
    device.ip_address = context.ip_address or device.ip_address
    device.last_ip_address = context.ip_address or device.last_ip_address
    device.last_seen_at = now
    device.last_subscribed_at = now
    if context.display_name and (created or not device.display_name):
        device.display_name = context.display_name
