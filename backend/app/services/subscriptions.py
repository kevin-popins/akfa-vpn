import base64
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AccessProfile, DeviceStatus, UserStatus, VpsNode, VpnUser, VpnUserDevice
from app.services.reality import ensure_reality_credentials
from app.services.subscription_settings import (
    absolute_connect_url,
    happ_metadata_comments,
    read_subscription_settings,
    subscription_headers,
    yaml_notice_comment,
)
from app.services.xray_config import (
    clean_server_names,
    ordered_available_nodes,
    render_sing_box_config_for_nodes,
    render_xray_client_config_for_nodes,
    vless_uri,
)


def validate_subscription_user(user: VpnUser | None) -> VpnUser:
    if not user or user.status != UserStatus.active.value:
        raise HTTPException(status_code=404, detail="Подписка недоступна")
    now = datetime.now(timezone.utc)
    expires_at = user.expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at and expires_at <= now:
        raise HTTPException(status_code=403, detail="Подписка истекла")
    if user.traffic_limit_bytes and (user.used_total_bytes or 0) >= user.traffic_limit_bytes:
        raise HTTPException(status_code=403, detail="Лимит трафика исчерпан")
    return user


def subscription_nodes(db: Session, user: VpnUser) -> list[VpsNode]:
    nodes = ordered_available_nodes(
        user,
        list(db.scalars(select(VpsNode).where(VpsNode.status == "online")).all()),
    )
    if not nodes:
        raise HTTPException(status_code=404, detail="Нет доступных серверов")
    for node in nodes:
        ensure_reality_credentials(node)
    return nodes


def subscription_payload(db: Session, user: VpnUser, device: VpnUserDevice | None = None) -> dict[str, object]:
    try:
        db.expire(user, ["devices", "node_links"])
    except Exception:
        pass
    device = device or next((item for item in user.devices if item.status == DeviceStatus.active.value and item.hwid_hash), None)
    nodes = subscription_nodes(db, user)
    if not device:
        raw_uris: list[dict[str, object]] = []
        first_uri = ""
        xray_json = render_xray_client_config_for_nodes(nodes, user, user.access_profile, None)
        sing_box = render_sing_box_config_for_nodes(nodes, user, user.access_profile, None)
    else:
        metadata = read_subscription_settings(db)
        names = clean_server_names(nodes, metadata.server_prefix)
        raw_uris = [
            {
                "node_id": node.id,
                "name": names[node.id],
                "location": node.location,
                "ip_address": node.ip_address,
                "uri": vless_uri(node, device, names[node.id]),
            }
            for node in nodes
        ]
        first_uri = str(raw_uris[0]["uri"]) if raw_uris else ""
        xray_json = render_xray_client_config_for_nodes(nodes, user, user.access_profile, device)
        sing_box = render_sing_box_config_for_nodes(nodes, user, user.access_profile, device)
    return {
        "vless_uri": first_uri,
        "vless_uris": raw_uris,
        "xray_json": xray_json,
        "sing_box": sing_box,
    }


def raw_subscription_text(db: Session, user: VpnUser, device: VpnUserDevice, *, include_happ_metadata: bool = False) -> str:
    nodes = subscription_nodes(db, user)
    metadata = read_subscription_settings(db)
    names = clean_server_names(nodes, metadata.server_prefix)
    body = "\n".join(vless_uri(node, device, names[node.id]) for node in nodes)
    if include_happ_metadata:
        connect_url = absolute_connect_url(user)
        return f"{happ_metadata_comments(metadata, user, connect_url)}\n{body}"
    return body


def clash_yaml(db: Session, user: VpnUser, device: VpnUserDevice) -> str:
    nodes = subscription_nodes(db, user)
    metadata = read_subscription_settings(db)
    names = clean_server_names(nodes, metadata.server_prefix)
    proxies = []
    for node in nodes:
        proxies.append(
            {
                "name": names[node.id],
                "type": "vless",
                "server": node.public_host or node.ip_address,
                "port": node.vless_port,
                "uuid": device.uuid,
                "network": "tcp",
                "tls": True,
                "udp": True,
                "flow": "xtls-rprx-vision",
                "servername": node.sni,
                "client-fingerprint": node.fingerprint or "chrome",
                "reality-opts": {
                    "public-key": node.reality_public_key,
                    "short-id": node.short_id,
                },
            }
        )
    body = render_yaml(
        {
            "proxies": proxies,
            "proxy-groups": [{"name": metadata.title, "type": "select", "proxies": [item["name"] for item in proxies]}],
            "rules": [f"MATCH,{metadata.title}"],
        }
    )
    notice = yaml_notice_comment(metadata, user)
    return f"{notice}\n{body}" if notice else body


def render_yaml(value: Any, indent: int = 0) -> str:
    pad = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}{key}:")
                lines.append(render_yaml(item, indent + 2))
            else:
                lines.append(f"{pad}{key}: {yaml_scalar(item)}")
        return "\n".join(lines)
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, dict):
                lines.append(f"{pad}- {next(iter(item))}: {yaml_scalar(next(iter(item.values())))}")
                for key, child in list(item.items())[1:]:
                    if isinstance(child, (dict, list)):
                        lines.append(f"{pad}  {key}:")
                        lines.append(render_yaml(child, indent + 4))
                    else:
                        lines.append(f"{pad}  {key}: {yaml_scalar(child)}")
            else:
                lines.append(f"{pad}- {yaml_scalar(item)}")
        return "\n".join(lines)
    return f"{pad}{yaml_scalar(value)}"


def yaml_scalar(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return '""'
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def subscription_response(db: Session, user: VpnUser, device: VpnUserDevice, fmt: str | None, client: str | None = None) -> Response:
    requested = (fmt or "raw").lower()
    metadata = read_subscription_settings(db)
    connect_url = absolute_connect_url(user)
    include_happ_metadata = is_happ_client(client or device.client_name)
    if requested in {"", "raw", "vless"}:
        return Response(
            raw_subscription_text(db, user, device, include_happ_metadata=include_happ_metadata),
            media_type="text/plain; charset=utf-8",
            headers=subscription_headers(metadata, user, extension="txt", connect_url=connect_url),
        )
    if requested == "base64":
        raw = raw_subscription_text(db, user, device, include_happ_metadata=include_happ_metadata).encode("utf-8")
        return Response(
            base64.b64encode(raw).decode("ascii"),
            media_type="text/plain; charset=utf-8",
            headers=subscription_headers(metadata, user, extension="txt", connect_url=connect_url),
        )
    if requested == "clash":
        return Response(
            clash_yaml(db, user, device),
            media_type="application/yaml; charset=utf-8",
            headers=subscription_headers(metadata, user, extension="yaml", connect_url=connect_url),
        )
    if requested == "singbox":
        body = render_sing_box_config_for_nodes(subscription_nodes(db, user), user, user.access_profile, device)
        json.loads(body)
        return Response(
            body,
            media_type="application/json; charset=utf-8",
            headers=subscription_headers(metadata, user, extension="json", connect_url=connect_url),
        )
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неподдерживаемый формат подписки")


def is_happ_client(value: str | None) -> bool:
    return "happ" in (value or "").strip().lower()
