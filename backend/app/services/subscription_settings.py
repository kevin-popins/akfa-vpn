from __future__ import annotations

import re
import unicodedata
from base64 import b64encode
from dataclasses import dataclass
from datetime import timezone
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import AppSetting, VpnUser

SUBSCRIPTION_SETTING_KEYS = (
    "subscription_title",
    "subscription_filename",
    "subscription_announcement",
    "subscription_update_interval_hours",
    "subscription_server_prefix",
)

DEFAULT_SUBSCRIPTION_TITLE = "AKFA VPN"
DEFAULT_SUBSCRIPTION_FILENAME = "akfa-vpn"
DEFAULT_SUBSCRIPTION_UPDATE_INTERVAL_HOURS = 12
DEFAULT_SUBSCRIPTION_SERVER_PREFIX = "AKFA"


@dataclass(frozen=True)
class SubscriptionSettingsData:
    title: str
    filename: str
    announcement: str
    update_interval_hours: int
    server_prefix: str


def read_subscription_settings(db: Session) -> SubscriptionSettingsData:
    rows = db.scalars(select(AppSetting).where(AppSetting.key.in_(SUBSCRIPTION_SETTING_KEYS))).all()
    values = {row.key: row.value for row in rows}
    return SubscriptionSettingsData(
        title=_clean_text(
            values.get("subscription_title"),
            getattr(settings, "subscription_title", DEFAULT_SUBSCRIPTION_TITLE),
            max_length=120,
        ),
        filename=_clean_filename(
            values.get("subscription_filename"),
            getattr(settings, "subscription_filename", DEFAULT_SUBSCRIPTION_FILENAME),
        ),
        announcement=_clean_text(
            values.get("subscription_announcement"),
            getattr(settings, "subscription_announcement", ""),
            max_length=1200,
            allow_empty=True,
        ),
        update_interval_hours=_clean_interval(
            values.get("subscription_update_interval_hours"),
            getattr(settings, "subscription_update_interval_hours", DEFAULT_SUBSCRIPTION_UPDATE_INTERVAL_HOURS),
        ),
        server_prefix=_clean_text(
            values.get("subscription_server_prefix"),
            getattr(settings, "subscription_server_prefix", DEFAULT_SUBSCRIPTION_SERVER_PREFIX),
            max_length=48,
        ),
    )


def write_subscription_settings(db: Session, payload: SubscriptionSettingsData) -> SubscriptionSettingsData:
    values = {
        "subscription_title": payload.title,
        "subscription_filename": payload.filename,
        "subscription_announcement": payload.announcement,
        "subscription_update_interval_hours": str(payload.update_interval_hours),
        "subscription_server_prefix": payload.server_prefix,
    }
    existing = {
        row.key: row
        for row in db.scalars(select(AppSetting).where(AppSetting.key.in_(SUBSCRIPTION_SETTING_KEYS))).all()
    }
    for key, value in values.items():
        row = existing.get(key)
        if row:
            row.value = value
        else:
            db.add(AppSetting(key=key, value=value))
    db.flush()
    return read_subscription_settings(db)


def subscription_headers(
    metadata: SubscriptionSettingsData,
    user: VpnUser,
    *,
    extension: str,
    connect_url: str | None = None,
) -> dict[str, str]:
    headers: dict[str, str] = {
        "profile-update-interval": str(metadata.update_interval_hours),
        "subscription-userinfo": subscription_userinfo(user),
        "Content-Disposition": content_disposition(metadata.filename, extension),
    }
    ascii_title = latin1_header_value(metadata.title)
    if ascii_title:
        headers["profile-title"] = ascii_title
    headers["profile-title*"] = f"UTF-8''{quote(metadata.title, safe='')}"
    if metadata.announcement.strip():
        headers["announce"] = base64_meta_value(metadata.announcement)
    if connect_url:
        headers["profile-web-page-url"] = connect_url
    return headers


def content_disposition(filename: str, extension: str) -> str:
    clean_extension = extension.lstrip(".") or "txt"
    base = filename.rsplit(".", 1)[0] if filename.lower().endswith(f".{clean_extension.lower()}") else filename
    ascii_base = ascii_filename(base) or DEFAULT_SUBSCRIPTION_FILENAME
    utf8_filename = quote(f"{base}.{clean_extension}", safe="")
    return f'attachment; filename="{ascii_base}.{clean_extension}"; filename*=UTF-8\'\'{utf8_filename}'


def subscription_userinfo(user: VpnUser) -> str:
    parts = [
        f"upload={max(int(user.used_upload_bytes or 0), 0)}",
        f"download={max(int(user.used_download_bytes or 0), 0)}",
        f"total={max(int(user.traffic_limit_bytes or 0), 0)}",
    ]
    if user.expires_at:
        expires_at = user.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        parts.append(f"expire={int(expires_at.timestamp())}")
    return "; ".join(parts)


def yaml_notice_comment(metadata: SubscriptionSettingsData, user: VpnUser) -> str:
    lines = [f"# {subscription_userinfo(user)};"]
    if metadata.announcement.strip():
        lines.extend(f"# {line}" if line else "#" for line in metadata.announcement.strip().splitlines())
    return "\n".join(lines)


def happ_metadata_comments(metadata: SubscriptionSettingsData, user: VpnUser, connect_url: str | None) -> str:
    lines = [
        f"#profile-title: {base64_meta_value(metadata.title)}",
        f"#profile-update-interval: {metadata.update_interval_hours}",
        f"#subscription-userinfo: {subscription_userinfo(user)}",
    ]
    if connect_url:
        lines.append(f"#profile-web-page-url: {connect_url}")
    if metadata.announcement.strip():
        lines.append(f"#announce: {base64_meta_value(metadata.announcement)}")
    return "\n".join(lines)


def base64_meta_value(value: str) -> str:
    return f"base64:{b64encode(value.encode('utf-8')).decode('ascii')}"


def absolute_connect_url(user: VpnUser) -> str | None:
    base = (settings.subscription_base_url or "").strip().rstrip("/")
    if not base:
        return None
    return f"{base}/connect/{user.subscription_token}"


def latin1_header_value(value: str) -> str | None:
    normalized = " ".join(value.split())
    if not normalized:
        return None
    try:
        normalized.encode("latin-1")
    except UnicodeEncodeError:
        return ascii_filename(normalized) or DEFAULT_SUBSCRIPTION_TITLE
    return normalized


def ascii_filename(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_value = re.sub(r"[^A-Za-z0-9._-]+", "-", ascii_value).strip(".-_")
    return ascii_value[:80]


def _clean_text(value: object, fallback: object, *, max_length: int, allow_empty: bool = False) -> str:
    raw = str(value if value is not None else fallback).replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw and not allow_empty:
        raw = str(fallback or "").strip() or DEFAULT_SUBSCRIPTION_TITLE
    return raw[:max_length]


def _clean_filename(value: object, fallback: object) -> str:
    raw = str(value if value is not None else fallback).strip()
    raw = raw.replace("\\", "-").replace("/", "-").replace("\x00", "")
    return (raw[:80].strip(". ") or DEFAULT_SUBSCRIPTION_FILENAME)


def _clean_interval(value: object, fallback: object) -> int:
    try:
        interval = int(value if value is not None else fallback)
    except (TypeError, ValueError):
        interval = DEFAULT_SUBSCRIPTION_UPDATE_INTERVAL_HOURS
    return min(max(interval, 1), 168)
