import json
from urllib.parse import parse_qs, urlparse

from app.models import VpsNode


def test_config_preview_contains_required_reality_fields(client, auth_headers):
    node = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={
            "name": "Config",
            "ip_address": "203.0.113.20",
            "ssh_username": "root",
            "ssh_password": "secret",
            "sni": "www.googletagmanager.com",
        },
    ).json()
    response = client.get(f"/admin/nodes/{node['id']}/config-preview")
    assert response.status_code == 200
    body = response.json()
    assert body != {}
    assert body["inbounds"][0]["protocol"] == "vless"
    assert body["inbounds"][0]["streamSettings"]["security"] == "reality"
    reality_settings = body["inbounds"][0]["streamSettings"]["realitySettings"]
    assert reality_settings["dest"] == "www.googletagmanager.com:443"
    assert reality_settings["serverNames"] == ["www.googletagmanager.com"]
    assert body["inbounds"][0]["settings"]["clients"] == []
    assert body["routing"]["domainStrategy"] == "IPIfNonMatch"
    assert body["api"]["services"] == ["StatsService"]
    assert body["inbounds"][1]["tag"] == "api-in"
    assert body["inbounds"][1]["listen"] == "127.0.0.1"
    assert body["routing"]["rules"][0] == {"type": "field", "inboundTag": ["api-in"], "outboundTag": "api"}
    assert body["routing"]["rules"][1] == {"type": "field", "protocol": ["bittorrent"], "outboundTag": "block"}
    assert {"protocol": "blackhole", "tag": "block"} in body["outbounds"]
    assert body["stats"] == {}
    assert body["policy"]["levels"]["0"]["statsUserUplink"] is True


def test_subscription_fails_safely_for_disabled_user(client, auth_headers):
    node = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Sub", "ip_address": "203.0.113.21", "ssh_username": "root", "ssh_password": "secret", "sni": "www.googletagmanager.com"},
    ).json()
    user = client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Петр", "last_name": "Смирнов", "username": "petr", "status": "disabled"},
    ).json()
    response = client.get(f"/sub/{user['subscription_token']}")
    assert response.status_code == 404


def test_subscription_returns_all_client_formats(client, auth_headers, db_session):
    node_payload = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Online", "ip_address": "203.0.113.22", "ssh_username": "root", "ssh_password": "secret", "sni": "www.googletagmanager.com"},
    ).json()
    node = db_session.get(VpsNode, node_payload["id"])
    node.status = "online"
    node.reality_public_key = "public"
    node.reality_private_key = "private"
    node.short_id = "abcdef1234567890"
    db_session.commit()
    user = client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Мария", "last_name": "Орлова", "username": "maria"},
    ).json()
    response = client.get(f"/admin/users/{user['id']}/subscription-preview")
    assert response.status_code == 200
    assert response.json()["vless_uri"].startswith("vless://")
    assert "xray_json" in response.json()
    assert "sing_box" in response.json()
    plain = client.get(f"/sub/{user['subscription_token']}")
    assert plain.status_code == 200
    assert plain.headers["content-type"].startswith("text/plain")
    assert plain.text.startswith("vless://")


def test_subscription_for_user_with_two_nodes_returns_two_vless_uris_primary_first(client, auth_headers, db_session):
    first_payload = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Amsterdam", "location": "Netherlands", "ip_address": "203.0.113.60", "ssh_username": "root", "ssh_password": "secret"},
    ).json()
    second_payload = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Berlin", "location": "Germany", "ip_address": "203.0.113.61", "ssh_username": "root", "ssh_password": "secret"},
    ).json()
    first = db_session.get(VpsNode, first_payload["id"])
    second = db_session.get(VpsNode, second_payload["id"])
    first.status = "online"
    second.status = "online"
    first.reality_public_key = second.reality_public_key = "public"
    first.reality_private_key = second.reality_private_key = "private"
    first.short_id = second.short_id = "abcdef1234567890"
    db_session.commit()

    user = client.post(
        "/admin/users",
        headers=auth_headers,
        json={
            "first_name": "Multi",
            "last_name": "Node",
            "username": "multi-node",
            "allowed_node_ids": [first.id, second.id],
            "primary_node_id": second.id,
        },
    ).json()

    response = client.get(f"/sub/{user['subscription_token']}")
    assert response.status_code == 200
    uri_lines = response.text.splitlines()
    assert len(uri_lines) == 2
    assert f"@{second.ip_address}:" in uri_lines[0]
    assert f"@{first.ip_address}:" in uri_lines[1]
    preview = client.get(f"/admin/users/{user['id']}/subscription-preview", headers=auth_headers).json()
    assert preview["vless_uris"][0]["node_id"] == second.id
    xray_config = json.loads(preview["xray_json"])
    assert [outbound["tag"] for outbound in xray_config["outbounds"][:2]] == ["proxy", f"proxy-{first.id}"]


def test_node_config_includes_only_users_allowed_on_that_node(client, auth_headers, db_session):
    first_payload = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Node A", "ip_address": "203.0.113.62", "ssh_username": "root", "ssh_password": "secret"},
    ).json()
    second_payload = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Node B", "ip_address": "203.0.113.63", "ssh_username": "root", "ssh_password": "secret"},
    ).json()
    first = db_session.get(VpsNode, first_payload["id"])
    second = db_session.get(VpsNode, second_payload["id"])
    first.status = "online"
    second.status = "online"
    db_session.commit()

    client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Both", "last_name": "Nodes", "username": "both-nodes", "allowed_node_ids": [first.id, second.id]},
    )
    client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Only", "last_name": "A", "username": "only-a", "allowed_node_ids": [first.id]},
    )

    first_config = client.get(f"/admin/nodes/{first.id}/config-preview", headers=auth_headers).json()
    second_config = client.get(f"/admin/nodes/{second.id}/config-preview", headers=auth_headers).json()
    first_clients = {client_item["email"] for client_item in first_config["inbounds"][0]["settings"]["clients"]}
    second_clients = {client_item["email"] for client_item in second_config["inbounds"][0]["settings"]["clients"]}
    assert first_clients == {"both-nodes", "only-a"}
    assert second_clients == {"both-nodes"}


def test_client_config_uses_node_sni_and_reality_parameters(client, auth_headers, db_session):
    node_payload = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={
            "name": "Client",
            "ip_address": "203.0.113.23",
            "ssh_username": "root",
            "ssh_password": "secret",
            "sni": "www.googletagmanager.com",
            "fingerprint": "chrome",
        },
    ).json()
    node = db_session.get(VpsNode, node_payload["id"])
    node.status = "online"
    db_session.commit()
    user = client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Илья", "last_name": "Клиент", "username": "ilya"},
    ).json()

    response = client.get(f"/admin/users/{user['id']}/subscription-preview")
    assert response.status_code == 200
    body = response.json()
    xray_config = json.loads(body["xray_json"])
    stream_settings = xray_config["outbounds"][0]["streamSettings"]
    reality_settings = stream_settings["realitySettings"]
    assert stream_settings["network"] == "tcp"
    assert stream_settings["security"] == "reality"
    assert reality_settings["serverName"] == "www.googletagmanager.com"
    assert reality_settings["fingerprint"] == "chrome"
    assert reality_settings["publicKey"] == node.reality_public_key
    assert reality_settings["shortId"] == node.short_id
    assert xray_config["outbounds"][0]["settings"]["vnext"][0]["users"][0]["flow"] == "xtls-rprx-vision"

    parsed = urlparse(body["vless_uri"])
    query = parse_qs(parsed.query)
    assert query["security"] == ["reality"]
    assert query["type"] == ["tcp"]
    assert query["flow"] == ["xtls-rprx-vision"]
    assert query["sni"] == ["www.googletagmanager.com"]
    assert query["fp"] == ["chrome"]
    assert query["pbk"] == [node.reality_public_key]
    assert query["sid"] == [node.short_id]


def test_ru_direct_client_config_blocks_torrent_and_routes_ru_zones_direct(client, auth_headers, db_session):
    node_payload = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "RU Direct", "ip_address": "203.0.113.24", "ssh_username": "root", "ssh_password": "secret"},
    ).json()
    node = db_session.get(VpsNode, node_payload["id"])
    node.status = "online"
    db_session.commit()
    profile = client.post(
        "/admin/access-profiles",
        headers=auth_headers,
        json={"name": "RU zones", "routing_mode": "ru_direct", "direct_domains": ["gosuslugi.ru"]},
    ).json()
    user = client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Ру", "last_name": "Директ", "username": "ru-direct", "access_profile_id": profile["id"]},
    ).json()

    response = client.get(f"/admin/users/{user['id']}/subscription-preview")
    assert response.status_code == 200
    xray_config = json.loads(response.json()["xray_json"])
    rules = xray_config["routing"]["rules"]
    assert rules[0] == {"type": "field", "protocol": ["bittorrent"], "outboundTag": "block"}
    assert "regexp:^.+\\.ru$" in rules[1]["domain"]
    assert "regexp:^.+\\.рф$" in rules[1]["domain"]
    assert "regexp:^.+\\.xn--p1ai$" in rules[1]["domain"]
    assert "domain:ru" in rules[1]["domain"]
    assert "domain:xn--p1ai" in rules[1]["domain"]
    assert "gosuslugi.ru" in rules[1]["domain"]
    assert rules[1]["outboundTag"] == "direct"
    assert rules[-1] == {"type": "field", "inboundTag": ["socks", "http"], "outboundTag": "proxy"}


def test_full_vpn_client_config_blocks_torrent_without_ru_direct_rules(client, auth_headers, db_session):
    node_payload = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Full", "ip_address": "203.0.113.25", "ssh_username": "root", "ssh_password": "secret"},
    ).json()
    node = db_session.get(VpsNode, node_payload["id"])
    node.status = "online"
    db_session.commit()
    profile = client.post(
        "/admin/access-profiles",
        headers=auth_headers,
        json={"name": "Full profile", "routing_mode": "full_tunnel", "direct_domains": []},
    ).json()
    user = client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Фулл", "last_name": "ВПН", "username": "full-vpn", "access_profile_id": profile["id"]},
    ).json()

    response = client.get(f"/admin/users/{user['id']}/subscription-preview")
    assert response.status_code == 200
    xray_config = json.loads(response.json()["xray_json"])
    assert xray_config["routing"]["rules"] == [
        {"type": "field", "protocol": ["bittorrent"], "outboundTag": "block"},
        {"type": "field", "inboundTag": ["socks", "http"], "outboundTag": "proxy"},
    ]


def test_blocked_domains_are_before_ru_direct_and_proxy_in_client_config(client, auth_headers, db_session):
    node_payload = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Block Client", "ip_address": "203.0.113.26", "ssh_username": "root", "ssh_password": "secret"},
    ).json()
    node = db_session.get(VpsNode, node_payload["id"])
    node.status = "online"
    db_session.commit()
    profile = client.post(
        "/admin/access-profiles",
        headers=auth_headers,
        json={
            "name": "Block YouTube",
            "routing_mode": "ru_direct",
            "direct_domains": ["gosuslugi.ru"],
            "blocked_domains": ["youtube.com", "youtu.be"],
        },
    ).json()
    user = client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Блок", "last_name": "Ютуб", "username": "block-youtube", "access_profile_id": profile["id"]},
    ).json()

    response = client.get(f"/admin/users/{user['id']}/subscription-preview")
    assert response.status_code == 200
    xray_config = json.loads(response.json()["xray_json"])
    rules = xray_config["routing"]["rules"]
    assert rules[0] == {"type": "field", "protocol": ["bittorrent"], "outboundTag": "block"}
    assert rules[1]["outboundTag"] == "block"
    assert "regexp:^(.+\\.)?youtube\\.com$" in rules[1]["domain"]
    assert "regexp:^(.+\\.)?youtu\\.be$" in rules[1]["domain"]
    assert rules[2]["outboundTag"] == "direct"
    assert "regexp:^.+\\.ru$" in rules[2]["domain"]
    assert rules[-1] == {"type": "field", "inboundTag": ["socks", "http"], "outboundTag": "proxy"}
    assert {"tag": "block", "protocol": "blackhole"} in xray_config["outbounds"]


def test_full_vpn_with_blocked_domain_blocks_domain(client, auth_headers, db_session):
    node_payload = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Full Block", "ip_address": "203.0.113.27", "ssh_username": "root", "ssh_password": "secret"},
    ).json()
    node = db_session.get(VpsNode, node_payload["id"])
    node.status = "online"
    db_session.commit()
    profile = client.post(
        "/admin/access-profiles",
        headers=auth_headers,
        json={"name": "Full with block", "routing_mode": "full_tunnel", "blocked_domains": ["youtube.com"]},
    ).json()
    user = client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Фулл", "last_name": "Блок", "username": "full-block", "access_profile_id": profile["id"]},
    ).json()

    response = client.get(f"/admin/users/{user['id']}/subscription-preview")
    assert response.status_code == 200
    xray_config = json.loads(response.json()["xray_json"])
    assert xray_config["routing"]["rules"] == [
        {"type": "field", "protocol": ["bittorrent"], "outboundTag": "block"},
        {"type": "field", "domain": ["regexp:^(.+\\.)?youtube\\.com$"], "outboundTag": "block"},
        {"type": "field", "inboundTag": ["socks", "http"], "outboundTag": "proxy"},
    ]


def test_sing_box_config_includes_blocked_domains(client, auth_headers, db_session):
    node_payload = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Sing Block", "ip_address": "203.0.113.28", "ssh_username": "root", "ssh_password": "secret"},
    ).json()
    node = db_session.get(VpsNode, node_payload["id"])
    node.status = "online"
    db_session.commit()
    profile = client.post(
        "/admin/access-profiles",
        headers=auth_headers,
        json={"name": "Sing block profile", "routing_mode": "ru_direct", "blocked_domains": ["youtube.com"]},
    ).json()
    user = client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Sing", "last_name": "Box", "username": "sing-block", "access_profile_id": profile["id"]},
    ).json()

    response = client.get(f"/admin/users/{user['id']}/subscription-preview")
    assert response.status_code == 200
    sing_box = json.loads(response.json()["sing_box"])
    rules = sing_box["route"]["rules"]
    assert rules[0] == {"protocol": ["bittorrent"], "outbound": "block"}
    assert rules[1] == {"domain": ["youtube.com"], "domain_suffix": ["youtube.com"], "outbound": "block"}
    assert rules[2]["outbound"] == "direct"


def test_subscription_reflects_blocked_domain_changes_without_token_change(client, auth_headers, db_session):
    node_payload = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Sub Block", "ip_address": "203.0.113.29", "ssh_username": "root", "ssh_password": "secret"},
    ).json()
    node = db_session.get(VpsNode, node_payload["id"])
    node.status = "online"
    db_session.commit()
    profile = client.post(
        "/admin/access-profiles",
        headers=auth_headers,
        json={"name": "Sub block profile", "routing_mode": "full_tunnel", "blocked_domains": ["youtube.com"]},
    ).json()
    user = client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Sub", "last_name": "Block", "username": "sub-block", "access_profile_id": profile["id"]},
    ).json()

    first = client.get(f"/admin/users/{user['id']}/subscription-preview", headers=auth_headers).json()
    profile_payload = {
        **profile,
        "blocked_domains": ["youtube.com", "googlevideo.com"],
    }
    response = client.put(f"/admin/access-profiles/{profile['id']}", headers=auth_headers, json=profile_payload)
    assert response.status_code == 200
    second = client.get(f"/admin/users/{user['id']}/subscription-preview", headers=auth_headers).json()

    assert first["subscription_url"] == second["subscription_url"]
    assert first["vless_uri"] == second["vless_uri"]
    xray_config = json.loads(second["xray_json"])
    assert "regexp:^(.+\\.)?googlevideo\\.com$" in xray_config["routing"]["rules"][1]["domain"]


def test_server_config_contains_per_user_blocked_domains(client, auth_headers, db_session):
    profile = client.post(
        "/admin/access-profiles",
        headers=auth_headers,
        json={"name": "Server block profile", "routing_mode": "full_tunnel", "blocked_domains": ["youtube.com"]},
    ).json()
    user = client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Server", "last_name": "Block", "username": "server-block", "access_profile_id": profile["id"]},
    ).json()
    node = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Server Block", "ip_address": "203.0.113.32", "ssh_username": "root", "ssh_password": "secret"},
    ).json()
    db_session.expire_all()

    response = client.get(f"/admin/nodes/{node['id']}/config-preview", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    rules = body["routing"]["rules"]
    assert rules[0] == {"type": "field", "inboundTag": ["api-in"], "outboundTag": "api"}
    assert rules[1] == {"type": "field", "protocol": ["bittorrent"], "outboundTag": "block"}
    assert rules[2] == {
        "type": "field",
        "user": [user["username"]],
        "domain": ["regexp:^(.+\\.)?youtube\\.com$"],
        "outboundTag": "block",
    }
