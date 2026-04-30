from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AccessProfile, UserStatus, VpsNode, VpnUser
from app.services.reality import ensure_reality_credentials
from app.services.xray_config import (
    ordered_available_nodes,
    render_sing_box_config_for_nodes,
    render_xray_client_config_for_nodes,
    vless_uri,
)


def subscription_payload(db: Session, user: VpnUser) -> dict[str, object]:
    nodes = ordered_available_nodes(
        user,
        list(db.scalars(select(VpsNode).where(VpsNode.status == "online")).all()),
    )
    if not nodes:
        raise HTTPException(status_code=503, detail="Нет доступных активных VPN-серверов")
    for node in nodes:
        ensure_reality_credentials(node)
    profile = db.get(AccessProfile, user.access_profile_id) if user.access_profile_id else None
    uris = [
        {
            "node_id": node.id,
            "name": node.name,
            "location": node.location,
            "ip_address": node.ip_address,
            "uri": vless_uri(node, user),
        }
        for node in nodes
    ]
    return {
        "vless_uri": "\n".join(item["uri"] for item in uris),
        "vless_uris": uris,
        "xray_json": render_xray_client_config_for_nodes(nodes, user, profile),
        "sing_box": render_sing_box_config_for_nodes(nodes, user, profile),
    }


def get_subscription(db: Session, token: str) -> dict[str, object]:
    user = db.scalar(select(VpnUser).where(VpnUser.subscription_token == token))
    if not user or user.status != UserStatus.active.value:
        raise HTTPException(status_code=404, detail="Подписка недоступна")
    return subscription_payload(db, user)
