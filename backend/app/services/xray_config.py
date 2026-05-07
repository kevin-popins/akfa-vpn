import json
from typing import Any

from app.constants import DEFAULT_DIRECT_DOMAINS, RU_DIRECT_DOMAIN_SUFFIXES, RU_DIRECT_ZONE_RULES
from urllib.parse import quote

from app.models import AccessProfile, DeviceStatus, NodeManagedMode, NodeStatus, RoutingMode, UserStatus, VpsNode, VpnUser, VpnUserDevice
from app.services.domain_lists import blocked_domain_matchers, normalize_blocked_domains


def active_users(users: list[VpnUser]) -> list[VpnUser]:
    return [user for user in users if user.status == UserStatus.active.value]


def active_hwid_devices_for_node(users: list[VpnUser], node: VpsNode) -> list[tuple[VpnUser, VpnUserDevice]]:
    if node.status != NodeStatus.online.value:
        return []
    pairs: list[tuple[VpnUser, VpnUserDevice]] = []
    for user in active_users(users):
        if not user_allowed_on_node(user, node):
            continue
        for device in user.devices:
            if device.status == DeviceStatus.active.value and device.hwid_hash:
                pairs.append((user, device))
    return pairs


def device_email(user: VpnUser, device: VpnUserDevice) -> str:
    return f"akfa_user_{user.id}_device_{device.id}"


def render_server_config(node: VpsNode, users: list[VpnUser]) -> str:
    akfa_clients = [
        {"id": device.uuid, "email": device_email(user, device), "flow": "xtls-rprx-vision"}
        for user, device in active_hwid_devices_for_node(users, node)
    ]
    clients = merge_imported_safe_clients(node, akfa_clients)
    inbound_tag = node.inbound_tag or "vless-reality"
    config: dict[str, Any] = {
        "log": {"loglevel": "warning"},
        "api": {"services": ["StatsService"], "tag": "api"},
        "stats": {},
        "policy": {
            "levels": {"0": {"statsUserUplink": True, "statsUserDownlink": True}},
            "system": {"statsInboundUplink": True, "statsInboundDownlink": True},
        },
        "inbounds": [
            {
                "tag": inbound_tag,
                "listen": "0.0.0.0",
                "port": node.vless_port,
                "protocol": "vless",
                "settings": {
                    "clients": clients,
                    "decryption": "none",
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "show": False,
                        "dest": f"{node.sni}:443",
                        "xver": 0,
                        "serverNames": [node.sni],
                        "privateKey": node.reality_private_key,
                        "shortIds": [node.short_id],
                    },
                    "tcpSettings": {"acceptProxyProtocol": False},
                },
                "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"]},
            },
            {
                "tag": "api-in",
                "listen": "127.0.0.1",
                "port": 10085,
                "protocol": "dokodemo-door",
                "settings": {"address": "127.0.0.1"},
            },
        ],
        "outbounds": [
            {"protocol": "freedom", "tag": "direct"},
            {"protocol": "blackhole", "tag": "block"},
        ],
        "routing": {
            "domainStrategy": "IPIfNonMatch",
            "rules": [
                {"type": "field", "inboundTag": ["api-in"], "outboundTag": "api"},
                {"type": "field", "protocol": ["bittorrent"], "outboundTag": "block"},
            ]
            + server_blocked_domain_rules(users, node),
        },
    }
    validate_server_config(config, node)
    return validate_json(config)


def merge_imported_safe_clients(node: VpsNode, akfa_clients: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if node.managed_mode != NodeManagedMode.imported_safe.value or not node.imported_inbound:
        return akfa_clients
    imported_clients = ((node.imported_inbound.get("settings") or {}).get("clients") or [])
    akfa_emails = {client.get("email") for client in akfa_clients}
    unknown_clients = [
        client
        for client in imported_clients
        if isinstance(client, dict)
        and not str(client.get("email") or "").startswith("akfa_user_")
        and client.get("email") not in akfa_emails
    ]
    return unknown_clients + akfa_clients


def validate_server_config(config: dict[str, Any], node: VpsNode) -> None:
    if not config or config == {}:
        raise ValueError("Нельзя применить конфиг: JSON пустой")
    inbounds = config.get("inbounds")
    if not isinstance(inbounds, list) or not inbounds:
        raise ValueError("Нельзя применить конфиг: inbound не найден")
    inbound = inbounds[0]
    if inbound.get("protocol") != "vless":
        raise ValueError("Нельзя применить конфиг: inbound должен использовать VLESS")
    if inbound.get("port") != node.vless_port:
        raise ValueError("Нельзя применить конфиг: порт VLESS не совпадает с сервером")
    stream_settings = inbound.get("streamSettings") or {}
    if stream_settings.get("security") != "reality":
        raise ValueError("Нельзя применить конфиг: security должен быть reality")
    reality_settings = stream_settings.get("realitySettings") or {}
    if reality_settings.get("dest") != f"{node.sni}:443":
        raise ValueError("Нельзя применить конфиг: Reality dest не совпадает с SNI")
    if node.sni not in (reality_settings.get("serverNames") or []):
        raise ValueError("Нельзя применить конфиг: Reality serverNames не содержит SNI")
    if not reality_settings.get("privateKey"):
        raise ValueError("Нельзя применить конфиг: Reality privateKey не создан")
    if not (reality_settings.get("shortIds") or []):
        raise ValueError("Нельзя применить конфиг: Reality shortId не создан")
    clients = (inbound.get("settings") or {}).get("clients")
    if not isinstance(clients, list):
        raise ValueError("Нельзя применить конфиг: clients должен быть списком")
    for client in clients:
        if str(client.get("email") or "").startswith("akfa_user_") and client.get("flow") != "xtls-rprx-vision":
            raise ValueError("Нельзя применить конфиг: flow клиента должен быть xtls-rprx-vision")
    if "stats" not in config or "policy" not in config:
        raise ValueError("Нельзя применить конфиг: stats и policy обязательны")


def direct_domain_rules(profile: AccessProfile | None) -> list[dict[str, Any]]:
    if not profile or profile.routing_mode == RoutingMode.full_tunnel.value:
        return []
    domains = profile.direct_domains or DEFAULT_DIRECT_DOMAINS
    if profile.routing_mode == RoutingMode.ru_direct.value:
        domains = RU_DIRECT_ZONE_RULES + domains
    return [{"type": "field", "domain": domains, "outboundTag": "direct"}]


def blocked_domain_rules(profile: AccessProfile | None) -> list[dict[str, Any]]:
    matchers = blocked_domain_matchers(profile.blocked_domains if profile else [])
    if not matchers:
        return []
    return [{"type": "field", "domain": matchers, "outboundTag": "block"}]


def server_blocked_domain_rules(users: list[VpnUser], node: VpsNode) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for user in active_users(users):
        if not user_allowed_on_node(user, node):
            continue
        matchers = blocked_domain_matchers(user.access_profile.blocked_domains if user.access_profile else [])
        emails = [
            device_email(user, device)
            for device in user.devices
            if device.status == DeviceStatus.active.value and device.hwid_hash
        ]
        if matchers and emails:
            rules.append(
                {
                    "type": "field",
                    "user": emails,
                    "domain": matchers,
                    "outboundTag": "block",
                }
            )
    return rules


def user_allowed_on_node(user: VpnUser, node: VpsNode) -> bool:
    allowed_ids = effective_node_ids(user)
    return node.id in allowed_ids


def effective_node_ids(user: VpnUser) -> set[int]:
    explicit_ids = set(user.allowed_node_ids or [])
    if explicit_ids:
        return explicit_ids
    profile_ids = set((user.access_profile.allowed_nodes or []) if user.access_profile else [])
    return profile_ids


def torrent_block_rule(outbound_tag: str = "block") -> dict[str, Any]:
    return {"type": "field", "protocol": ["bittorrent"], "outboundTag": outbound_tag}


def sing_box_direct_rules(profile: AccessProfile | None) -> list[dict[str, Any]]:
    if not profile or profile.routing_mode == RoutingMode.full_tunnel.value:
        return []
    domains = profile.direct_domains or DEFAULT_DIRECT_DOMAINS
    rule: dict[str, Any] = {"domain": domains, "outbound": "direct"}
    if profile.routing_mode == RoutingMode.ru_direct.value:
        rule["domain_suffix"] = RU_DIRECT_DOMAIN_SUFFIXES
    return [rule]


def sing_box_blocked_domain_rules(profile: AccessProfile | None) -> list[dict[str, Any]]:
    normalized_domains = normalize_blocked_domains(profile.blocked_domains if profile else [])
    if not normalized_domains:
        return []
    return [{"domain": normalized_domains, "domain_suffix": normalized_domains, "outbound": "block"}]


def node_label(node: VpsNode) -> str:
    return node.location or node.name


COUNTRY_NAMES = {
    "nl": ("🇳🇱", "Нидерланды"),
    "netherlands": ("🇳🇱", "Нидерланды"),
    "holland": ("🇳🇱", "Нидерланды"),
    "нидерланды": ("🇳🇱", "Нидерланды"),
    "голландия": ("🇳🇱", "Нидерланды"),
    "de": ("🇩🇪", "Германия"),
    "germany": ("🇩🇪", "Германия"),
    "deutschland": ("🇩🇪", "Германия"),
    "германия": ("🇩🇪", "Германия"),
    "fi": ("🇫🇮", "Финляндия"),
    "finland": ("🇫🇮", "Финляндия"),
    "финляндия": ("🇫🇮", "Финляндия"),
    "ie": ("🇮🇪", "Ирландия"),
    "ireland": ("🇮🇪", "Ирландия"),
    "ирландия": ("🇮🇪", "Ирландия"),
    "fr": ("🇫🇷", "Франция"),
    "france": ("🇫🇷", "Франция"),
    "франция": ("🇫🇷", "Франция"),
    "pl": ("🇵🇱", "Польша"),
    "poland": ("🇵🇱", "Польша"),
    "польша": ("🇵🇱", "Польша"),
    "se": ("🇸🇪", "Швеция"),
    "sweden": ("🇸🇪", "Швеция"),
    "швеция": ("🇸🇪", "Швеция"),
    "no": ("🇳🇴", "Норвегия"),
    "norway": ("🇳🇴", "Норвегия"),
    "норвегия": ("🇳🇴", "Норвегия"),
    "ch": ("🇨🇭", "Швейцария"),
    "switzerland": ("🇨🇭", "Швейцария"),
    "швейцария": ("🇨🇭", "Швейцария"),
    "at": ("🇦🇹", "Австрия"),
    "austria": ("🇦🇹", "Австрия"),
    "австрия": ("🇦🇹", "Австрия"),
    "cz": ("🇨🇿", "Чехия"),
    "czech": ("🇨🇿", "Чехия"),
    "czechia": ("🇨🇿", "Чехия"),
    "чехия": ("🇨🇿", "Чехия"),
    "es": ("🇪🇸", "Испания"),
    "spain": ("🇪🇸", "Испания"),
    "испания": ("🇪🇸", "Испания"),
    "it": ("🇮🇹", "Италия"),
    "italy": ("🇮🇹", "Италия"),
    "италия": ("🇮🇹", "Италия"),
    "us": ("🇺🇸", "США"),
    "usa": ("🇺🇸", "США"),
    "united states": ("🇺🇸", "США"),
    "america": ("🇺🇸", "США"),
    "сша": ("🇺🇸", "США"),
    "америка": ("🇺🇸", "США"),
    "ca": ("🇨🇦", "Канада"),
    "canada": ("🇨🇦", "Канада"),
    "канада": ("🇨🇦", "Канада"),
    "uk": ("🇬🇧", "Великобритания"),
    "gb": ("🇬🇧", "Великобритания"),
    "united kingdom": ("🇬🇧", "Великобритания"),
    "great britain": ("🇬🇧", "Великобритания"),
    "britain": ("🇬🇧", "Великобритания"),
    "англия": ("🇬🇧", "Великобритания"),
    "великобритания": ("🇬🇧", "Великобритания"),
    "tr": ("🇹🇷", "Турция"),
    "turkey": ("🇹🇷", "Турция"),
    "турция": ("🇹🇷", "Турция"),
    "ae": ("🇦🇪", "ОАЭ"),
    "uae": ("🇦🇪", "ОАЭ"),
    "united arab emirates": ("🇦🇪", "ОАЭ"),
    "оаэ": ("🇦🇪", "ОАЭ"),
    "эмираты": ("🇦🇪", "ОАЭ"),
    "jp": ("🇯🇵", "Япония"),
    "japan": ("🇯🇵", "Япония"),
    "япония": ("🇯🇵", "Япония"),
    "sg": ("🇸🇬", "Сингапур"),
    "singapore": ("🇸🇬", "Сингапур"),
    "сингапур": ("🇸🇬", "Сингапур"),
    "kr": ("🇰🇷", "Южная Корея"),
    "korea": ("🇰🇷", "Южная Корея"),
    "south korea": ("🇰🇷", "Южная Корея"),
    "корея": ("🇰🇷", "Южная Корея"),
    "южная корея": ("🇰🇷", "Южная Корея"),
}


def clean_server_name(node: VpsNode, suffix: int | None = None) -> str:
    raw = (node.location or node.name or "").strip()
    flag, name = COUNTRY_NAMES.get(raw.lower(), ("", raw or "VPN"))
    base = f"AKFA {flag} {name}".replace("  ", " ").strip()
    return f"{base} {suffix}" if suffix else base


def clean_server_names(nodes: list[VpsNode]) -> dict[int, str]:
    buckets: dict[str, list[VpsNode]] = {}
    for node in nodes:
        buckets.setdefault(clean_server_name(node), []).append(node)
    result: dict[int, str] = {}
    for base, items in buckets.items():
        if len(items) == 1:
            result[items[0].id] = base
        else:
            for index, node in enumerate(sorted(items, key=lambda item: item.id), start=1):
                result[node.id] = f"{base} {index}"
    return result


def vless_uri(node: VpsNode, device: VpnUserDevice, remark: str | None = None) -> str:
    host = node.public_host or node.ip_address
    label = quote(remark or clean_server_name(node))
    return (
        f"vless://{device.uuid}@{host}:{node.vless_port}"
        f"?encryption=none&type=tcp&security=reality&pbk={node.reality_public_key}&fp={node.fingerprint}"
        f"&sni={node.sni}&sid={node.short_id}&flow=xtls-rprx-vision"
        f"#{label}"
    )


def ordered_available_nodes(user: VpnUser, nodes: list[VpsNode]) -> list[VpsNode]:
    allowed_ids = effective_node_ids(user)
    available = [
        node
        for node in nodes
        if node.id in allowed_ids and node.status == NodeStatus.online.value
    ]
    available.sort(key=lambda node: (0 if user.primary_node_id and node.id == user.primary_node_id else 1, node.location or node.name, node.id))
    return available


def render_xray_client_config_for_nodes(nodes: list[VpsNode], user: VpnUser, profile: AccessProfile | None, device: VpnUserDevice | None = None) -> str:
    device = device or first_active_device(user)
    proxy_outbounds = [xray_proxy_outbound(node, device, f"proxy-{node.id}" if index else "proxy") for index, node in enumerate(nodes) if device]
    final_proxy_tag = proxy_outbounds[0]["tag"] if proxy_outbounds else "proxy"
    config = {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {"tag": "socks", "port": 10808, "listen": "127.0.0.1", "protocol": "socks"},
            {"tag": "http", "port": 10809, "listen": "127.0.0.1", "protocol": "http"},
        ],
        "outbounds": proxy_outbounds
        + [
            {"tag": "direct", "protocol": "freedom"},
            {"tag": "block", "protocol": "blackhole"},
            {"tag": "dns-out", "protocol": "dns"},
        ],
        "dns": {"servers": ["1.1.1.1", "8.8.8.8"]},
        "routing": {
            "domainStrategy": "IPIfNonMatch",
            "rules": [torrent_block_rule()]
            + blocked_domain_rules(profile)
            + direct_domain_rules(profile)
            + [
                {"type": "field", "inboundTag": ["socks", "http"], "outboundTag": final_proxy_tag},
            ],
        },
    }
    return validate_json(config)


def first_active_device(user: VpnUser) -> VpnUserDevice | None:
    return next((device for device in user.devices if device.status == DeviceStatus.active.value and device.hwid_hash), None)


def xray_proxy_outbound(node: VpsNode, device: VpnUserDevice, tag: str) -> dict[str, Any]:
    return {
        "tag": tag,
        "protocol": "vless",
        "settings": {
            "vnext": [
                {
                    "address": node.public_host or node.ip_address,
                    "port": node.vless_port,
                    "users": [
                        {
                            "id": device.uuid,
                            "encryption": "none",
                            "flow": "xtls-rprx-vision",
                        }
                    ],
                }
            ]
        },
        "streamSettings": {
            "network": "tcp",
            "security": "reality",
            "realitySettings": {
                "serverName": node.sni,
                "fingerprint": node.fingerprint,
                "publicKey": node.reality_public_key,
                "shortId": node.short_id,
            },
        },
    }


def render_xray_client_config(node: VpsNode, user: VpnUser, profile: AccessProfile | None, device: VpnUserDevice | None = None) -> str:
    return render_xray_client_config_for_nodes([node], user, profile, device)


def render_sing_box_config_for_nodes(nodes: list[VpsNode], user: VpnUser, profile: AccessProfile | None, device: VpnUserDevice | None = None) -> str:
    device = device or first_active_device(user)
    proxy_outbounds = [
        sing_box_proxy_outbound(node, device, f"proxy-{node.id}" if index else "proxy")
        for index, node in enumerate(nodes)
        if device
    ]
    final_proxy_tag = proxy_outbounds[0]["tag"] if proxy_outbounds else "proxy"
    config = {
        "log": {"level": "warn"},
        "inbounds": [
            {"type": "socks", "tag": "socks", "listen": "127.0.0.1", "listen_port": 10808},
            {"type": "http", "tag": "http", "listen": "127.0.0.1", "listen_port": 10809},
        ],
        "outbounds": proxy_outbounds
        + [
            {"type": "direct", "tag": "direct"},
            {"type": "block", "tag": "block"},
            {"type": "dns", "tag": "dns-out"},
        ],
        "route": {
            "rules": [{"protocol": ["bittorrent"], "outbound": "block"}]
            + sing_box_blocked_domain_rules(profile)
            + sing_box_direct_rules(profile),
            "final": final_proxy_tag,
        },
    }
    return validate_json(config)


def sing_box_proxy_outbound(node: VpsNode, device: VpnUserDevice, tag: str) -> dict[str, Any]:
    return {
        "type": "vless",
        "tag": tag,
        "server": node.public_host or node.ip_address,
        "server_port": node.vless_port,
        "uuid": device.uuid,
        "flow": "xtls-rprx-vision",
        "tls": {
            "enabled": True,
            "server_name": node.sni,
            "utls": {"enabled": True, "fingerprint": node.fingerprint},
            "reality": {"enabled": True, "public_key": node.reality_public_key, "short_id": node.short_id},
        },
    }


def render_sing_box_config(node: VpsNode, user: VpnUser, profile: AccessProfile | None, device: VpnUserDevice | None = None) -> str:
    return render_sing_box_config_for_nodes([node], user, profile, device)


def validate_json(config: dict[str, Any]) -> str:
    rendered = json.dumps(config, ensure_ascii=False, indent=2)
    json.loads(rendered)
    return rendered
