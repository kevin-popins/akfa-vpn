import json
import base64
import pytest
from urllib.parse import parse_qs, urlparse

from app.models import VpnUserDevice, VpsNode
from app.services.ssh_installer import InstallResult, XrayInstaller
from app.services.config_apply import ConfigApplyService
from app.services.xray_config import render_server_config


@pytest.fixture(autouse=True)
def fake_xray_apply(monkeypatch):
    calls = []

    async def fake_apply(self):
        calls.append(
            {
                "node_id": self.node.id,
                "users": [user.username for user in self.users],
                "config": render_server_config(self.node, self.users),
            }
        )
        return InstallResult(ok=True, logs=[{"message": "applied"}])

    monkeypatch.setattr(XrayInstaller, "apply_config", fake_apply)
    monkeypatch.setattr("app.services.config_apply.node_has_installed_xray", lambda node: True)
    return calls


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


def test_hwid_hard_mode_requires_hwid_and_enforces_device_limit(client, auth_headers, db_session, fake_xray_apply):
    node_payload = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "HWID", "location": "Netherlands", "ip_address": "203.0.113.90", "ssh_username": "root", "ssh_password": "secret"},
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
        json={"first_name": "Hard", "last_name": "Mode", "username": "hard-mode", "device_limit": 2},
    ).json()

    missing = client.get(f"/sub/{user['subscription_token']}")
    assert missing.status_code == 403
    assert missing.text == "Ваш клиент не поддерживает ограничение устройств"
    assert missing.headers["x-hwid-not-supported"] == "true"
    assert db_session.query(VpnUserDevice).count() == 0

    first = client.get(f"/sub/{user['subscription_token']}", headers={"x-hwid": "phone-1", "x-device-model": "Pixel 8", "x-device-os": "Android"})
    assert first.status_code == 200
    first_device = db_session.query(VpnUserDevice).filter_by(vpn_user_id=user["id"]).one()
    applied_config = json.loads(fake_xray_apply[-1]["config"])
    assert applied_config["inbounds"][0]["settings"]["clients"][0]["id"] == first_device.uuid
    assert applied_config["inbounds"][0]["settings"]["clients"][0]["email"] == f"akfa_user_{user['id']}_device_{first_device.id}"
    second = client.get(f"/sub/{user['subscription_token']}", headers={"x-hwid": "phone-2"})
    assert second.status_code == 200
    apply_count_after_create = len(fake_xray_apply)
    repeat = client.get(f"/sub/{user['subscription_token']}", headers={"x-hwid": "phone-1", "x-real-ip": "198.51.100.10"})
    assert repeat.status_code == 200
    assert len(fake_xray_apply) == apply_count_after_create
    assert db_session.query(VpnUserDevice).filter_by(vpn_user_id=user["id"], status="active").count() == 2

    third = client.get(f"/sub/{user['subscription_token']}", headers={"x-hwid": "phone-3"})
    assert third.status_code == 403
    assert third.text == "Превышен лимит устройств"
    assert third.headers["x-hwid-max-devices-reached"] == "true"
    assert db_session.query(VpnUserDevice).filter_by(vpn_user_id=user["id"], status="active").count() == 2


def test_new_hwid_subscription_requires_assigned_node_and_successful_apply(client, auth_headers, db_session, monkeypatch):
    no_node_user = client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "No", "last_name": "Node", "username": "no-node"},
    ).json()
    no_node = client.get(f"/sub/{no_node_user['subscription_token']}", headers={"x-hwid": "lonely-phone"})
    assert no_node.status_code == 403
    assert no_node.text == "Пользователю не назначен сервер"
    assert db_session.query(VpnUserDevice).filter_by(vpn_user_id=no_node_user["id"]).count() == 0

    node_payload = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Apply failure", "ip_address": "203.0.113.92", "ssh_username": "root", "ssh_password": "secret"},
    ).json()
    node = db_session.get(VpsNode, node_payload["id"])
    node.status = "online"
    db_session.commit()
    failing_user = client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Fail", "last_name": "Apply", "username": "fail-apply"},
    ).json()

    async def failed_apply(self):
        return InstallResult(ok=False, logs=[{"level": "error", "message": "failed"}])

    monkeypatch.setattr(XrayInstaller, "apply_config", failed_apply)
    failed = client.get(f"/sub/{failing_user['subscription_token']}", headers={"x-hwid": "apply-fail-phone"})
    assert failed.status_code == 503
    assert failed.text == "Не удалось применить конфигурацию на сервер"
    assert db_session.query(VpnUserDevice).filter_by(vpn_user_id=failing_user["id"]).count() == 0


def test_device_revoke_and_reset_auto_apply_remove_hwid_clients(client, auth_headers, db_session, fake_xray_apply):
    node_payload = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Revoke apply", "ip_address": "203.0.113.93", "ssh_username": "root", "ssh_password": "secret"},
    ).json()
    node = db_session.get(VpsNode, node_payload["id"])
    node.status = "online"
    db_session.commit()
    user = client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Revoke", "last_name": "Device", "username": "revoke-device"},
    ).json()
    created = client.get(f"/sub/{user['subscription_token']}", headers={"x-hwid": "revoke-phone"})
    assert created.status_code == 200
    device = db_session.query(VpnUserDevice).filter_by(vpn_user_id=user["id"]).one()
    old_device_token = device.subscription_token
    old_device_uuid = device.uuid
    assert device.uuid in fake_xray_apply[-1]["config"]

    revoked = client.post(f"/admin/users/{user['id']}/devices/{device.id}/revoke", headers=auth_headers)
    assert revoked.status_code == 200
    assert old_device_uuid not in fake_xray_apply[-1]["config"]
    assert client.get(f"/sub/device/{old_device_token}", headers={"x-hwid": "revoke-phone"}).status_code == 404
    assert db_session.query(VpnUserDevice).filter_by(vpn_user_id=user["id"]).count() == 0
    repeated = client.post(f"/admin/users/{user['id']}/devices/{device.id}/revoke", headers=auth_headers)
    assert repeated.status_code == 200
    assert repeated.json()["message"] == "Устройство уже удалено"

    recreated = client.get(f"/sub/{user['subscription_token']}", headers={"x-hwid": "revoke-phone"})
    assert recreated.status_code == 200
    second_device = db_session.query(VpnUserDevice).filter_by(vpn_user_id=user["id"], status="active").one()
    assert second_device.uuid != old_device_uuid
    assert second_device.uuid in fake_xray_apply[-1]["config"]

    reset = client.post(f"/admin/users/{user['id']}/devices/reset", headers=auth_headers)
    assert reset.status_code == 200
    assert second_device.uuid not in fake_xray_apply[-1]["config"]
    assert db_session.query(VpnUserDevice).filter_by(vpn_user_id=user["id"]).count() == 0


def test_public_connect_can_remove_device_and_same_hwid_registers_again(client, auth_headers, db_session, fake_xray_apply):
    node_payload = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Public remove", "ip_address": "203.0.113.94", "ssh_username": "root", "ssh_password": "secret"},
    ).json()
    node = db_session.get(VpsNode, node_payload["id"])
    node.status = "online"
    db_session.commit()
    user = client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Public", "last_name": "Remove", "username": "public-remove", "device_limit": 1},
    ).json()
    created = client.get(f"/sub/{user['subscription_token']}", headers={"x-hwid": "public-phone"})
    assert created.status_code == 200
    device = db_session.query(VpnUserDevice).filter_by(vpn_user_id=user["id"]).one()
    old_uuid = device.uuid

    removed = client.delete(f"/public/connect/{user['subscription_token']}/devices/{device.id}")
    assert removed.status_code == 200
    assert db_session.query(VpnUserDevice).filter_by(vpn_user_id=user["id"]).count() == 0
    assert old_uuid not in fake_xray_apply[-1]["config"]
    second_remove = client.delete(f"/public/connect/{user['subscription_token']}/devices/{device.id}")
    assert second_remove.status_code == 200
    assert second_remove.json()["message"] == "Устройство уже удалено"

    recreated = client.get(f"/sub/{user['subscription_token']}", headers={"x-hwid": "public-phone"})
    assert recreated.status_code == 200
    new_device = db_session.query(VpnUserDevice).filter_by(vpn_user_id=user["id"]).one()
    assert new_device.uuid != old_uuid
    assert new_device.uuid in recreated.text

    apply_count = len(fake_xray_apply)
    poll = client.get(f"/public/connect/{user['subscription_token']}")
    assert poll.status_code == 200
    assert len(fake_xray_apply) == apply_count


def test_device_remove_apply_failure_rolls_back_active_device(client, auth_headers, db_session, monkeypatch):
    node_payload = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Remove fail", "ip_address": "203.0.113.95", "ssh_username": "root", "ssh_password": "secret"},
    ).json()
    node = db_session.get(VpsNode, node_payload["id"])
    node.status = "online"
    db_session.commit()
    user = client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Remove", "last_name": "Fail", "username": "remove-fail"},
    ).json()
    created = client.get(f"/sub/{user['subscription_token']}", headers={"x-hwid": "remove-fail-phone"})
    assert created.status_code == 200
    device = db_session.query(VpnUserDevice).filter_by(vpn_user_id=user["id"]).one()

    async def failed_apply(self):
        return InstallResult(ok=False, logs=[{"level": "error", "message": "failed"}])

    monkeypatch.setattr(XrayInstaller, "apply_config", failed_apply)
    removed = client.post(f"/admin/users/{user['id']}/devices/{device.id}/revoke", headers=auth_headers)
    assert removed.status_code == 503
    db_session.expire_all()
    assert db_session.query(VpnUserDevice).filter_by(id=device.id, status="active").one()


@pytest.mark.asyncio
async def test_apply_config_timeout_is_controlled(client, auth_headers, db_session, monkeypatch):
    node_payload = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Timeout apply", "ip_address": "203.0.113.96", "ssh_username": "root", "ssh_password": "secret"},
    ).json()
    node = db_session.get(VpsNode, node_payload["id"])
    node.status = "online"
    node.xray_installed = True
    db_session.commit()

    async def slow_apply(self):
        import asyncio

        await asyncio.sleep(0.05)
        return InstallResult(ok=True, logs=[{"message": "late"}])

    monkeypatch.setattr(XrayInstaller, "apply_config", slow_apply)
    summary = await ConfigApplyService(db_session).apply_to_nodes({node.id}, timeout_seconds=0.01)
    assert summary.failed == 1
    assert "Таймаут" in (summary.results[0].error or "")


def test_device_subscription_requires_matching_hwid_and_clash_is_yaml(client, auth_headers, db_session):
    node_payload = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Amsterdam", "location": "Netherlands", "ip_address": "203.0.113.91", "ssh_username": "root", "ssh_password": "secret"},
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
        json={"first_name": "Device", "last_name": "Sub", "username": "device-sub"},
    ).json()
    raw = client.get(f"/sub/{user['subscription_token']}?format=raw", headers={"x-hwid": "device-hwid"})
    assert raw.status_code == 200
    assert "encryption=none" in raw.text
    device = db_session.query(VpnUserDevice).filter_by(vpn_user_id=user["id"]).one()

    assert client.get(f"/sub/device/{device.subscription_token}").status_code == 403
    wrong = client.get(f"/sub/device/{device.subscription_token}", headers={"x-hwid": "other-device"})
    assert wrong.status_code == 403
    assert wrong.text == "Ссылка подписки привязана к другому устройству"

    clash = client.get(f"/sub/{user['subscription_token']}?format=clash", headers={"x-hwid": "device-hwid"})
    assert clash.status_code == 200
    assert clash.headers["profile-title"] == "akfa vpn"
    assert 'filename="akfa-vpn.yaml"' in clash.headers["content-disposition"]
    assert "proxies:" in clash.text
    assert "proxy-groups:" in clash.text
    assert "rules:" in clash.text
    assert "AKFA 🇳🇱 Нидерланды" in clash.text
    assert "device-sub" not in clash.text
    assert user["subscription_token"] not in clash.text

    encoded = client.get(f"/sub/{user['subscription_token']}?format=base64", headers={"x-hwid": "device-hwid"})
    assert encoded.status_code == 200
    assert base64.b64decode(encoded.text).decode("utf-8").startswith("vless://")


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
    created = client.get(
        f"/sub/{user['subscription_token']}?platform=android&client=happ&format=raw",
        headers={"x-hwid": "phone-1", "x-device-os": "Android", "x-device-model": "Samsung S23"},
    )
    assert created.status_code == 200
    response = client.get(f"/admin/users/{user['id']}/subscription-preview")
    assert response.status_code == 200
    assert response.json()["vless_uri"].startswith("vless://")
    assert "xray_json" in response.json()
    assert "sing_box" in response.json()
    plain = client.get(f"/sub/{user['subscription_token']}", headers={"x-hwid": "phone-1"})
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

    response = client.get(f"/sub/{user['subscription_token']}", headers={"x-hwid": "multi-phone"})
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

    both = client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Both", "last_name": "Nodes", "username": "both-nodes", "allowed_node_ids": [first.id, second.id]},
    ).json()
    only = client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Only", "last_name": "A", "username": "only-a", "allowed_node_ids": [first.id]},
    ).json()
    client.get(f"/sub/{both['subscription_token']}", headers={"x-hwid": "both-phone"})
    client.get(f"/sub/{only['subscription_token']}", headers={"x-hwid": "only-phone"})

    first_config = client.get(f"/admin/nodes/{first.id}/config-preview", headers=auth_headers).json()
    second_config = client.get(f"/admin/nodes/{second.id}/config-preview", headers=auth_headers).json()
    first_clients = {client_item["email"] for client_item in first_config["inbounds"][0]["settings"]["clients"]}
    second_clients = {client_item["email"] for client_item in second_config["inbounds"][0]["settings"]["clients"]}
    assert first_clients == {f"akfa_user_{both['id']}_device_1", f"akfa_user_{only['id']}_device_2"}
    assert second_clients == {f"akfa_user_{both['id']}_device_1"}


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
    created = client.get(f"/sub/{user['subscription_token']}", headers={"x-hwid": "ilya-phone"})
    assert created.status_code == 200

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
    client.get(f"/sub/{user['subscription_token']}", headers={"x-hwid": "ru-direct-phone"})

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
    client.get(f"/sub/{user['subscription_token']}", headers={"x-hwid": "full-phone"})

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
    client.get(f"/sub/{user['subscription_token']}", headers={"x-hwid": "block-phone"})

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
    client.get(f"/sub/{user['subscription_token']}", headers={"x-hwid": "full-block-phone"})

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
    client.get(f"/sub/{user['subscription_token']}", headers={"x-hwid": "sing-phone"})

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
    client.get(f"/sub/{user['subscription_token']}", headers={"x-hwid": "sub-block-phone"})

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
    node = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Server Block", "ip_address": "203.0.113.32", "ssh_username": "root", "ssh_password": "secret"},
    ).json()
    db_node = db_session.get(VpsNode, node["id"])
    db_node.status = "online"
    db_session.commit()
    profile = client.post(
        "/admin/access-profiles",
        headers=auth_headers,
        json={"name": "Server block profile", "routing_mode": "full_tunnel", "blocked_domains": ["youtube.com"]},
    ).json()
    user = client.post(
        "/admin/users",
        headers=auth_headers,
        json={
            "first_name": "Server",
            "last_name": "Block",
            "username": "server-block",
            "access_profile_id": profile["id"],
            "allowed_node_ids": [node["id"]],
            "primary_node_id": node["id"],
        },
    ).json()
    client.get(f"/sub/{user['subscription_token']}", headers={"x-hwid": "server-block-phone"})
    db_session.expire_all()

    response = client.get(f"/admin/nodes/{node['id']}/config-preview", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    rules = body["routing"]["rules"]
    assert rules[0] == {"type": "field", "inboundTag": ["api-in"], "outboundTag": "api"}
    assert rules[1] == {"type": "field", "protocol": ["bittorrent"], "outboundTag": "block"}
    assert rules[2] == {
        "type": "field",
            "user": [f"akfa_user_{user['id']}_device_1"],
        "domain": ["regexp:^(.+\\.)?youtube\\.com$"],
        "outboundTag": "block",
    }
