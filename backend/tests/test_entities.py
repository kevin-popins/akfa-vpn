import io
import json
import tarfile
import time
import asyncio

from sqlalchemy.orm import sessionmaker

import app.services.node_action_jobs as node_action_jobs
from app.services.ssh_installer import InstallResult, READ_ONLY_CHECK_COMMANDS, XrayInstaller


def wait_node_job(client, headers, job_id: str, timeout: float = 5.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        response = client.get(f"/admin/node-actions/{job_id}", headers=headers)
        assert response.status_code == 200
        last = response.json()
        if last["status"] not in {"pending", "running"}:
            return last
        time.sleep(0.05)
    raise AssertionError(f"job did not finish: {last}")


def patch_node_job_session(monkeypatch, db_session):
    JobSessionLocal = sessionmaker(bind=db_session.get_bind(), autoflush=False, autocommit=False, expire_on_commit=False)
    monkeypatch.setattr(node_action_jobs, "SessionLocal", JobSessionLocal)
    node_action_jobs._jobs.clear()
    node_action_jobs._running_install_by_node.clear()


def test_departments_profiles_users_nodes_flow(client, auth_headers):
    profile = client.post(
        "/admin/access-profiles",
        headers=auth_headers,
        json={"name": "Офис", "description": "Для сотрудников", "routing_mode": "ru_direct"},
    )
    assert profile.status_code == 200
    profile_id = profile.json()["id"]

    department = client.post(
        "/admin/departments",
        headers=auth_headers,
        json={"name": "Продажи", "default_access_profile_id": profile_id},
    )
    assert department.status_code == 200

    node = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={
            "name": "Moscow-1",
            "ip_address": "203.0.113.10",
            "ssh_username": "root",
            "ssh_password": "secret",
            "sni": "www.microsoft.com",
            "fingerprint": "chrome",
        },
    )
    assert node.status_code == 200
    assert "encrypted_ssh_password" not in node.text

    user = client.post(
        "/admin/users",
        headers=auth_headers,
        json={
            "first_name": "Анна",
            "last_name": "Иванова",
            "username": "anna.ivanova",
            "department_id": department.json()["id"],
            "access_profile_id": profile_id,
        },
    )
    assert user.status_code == 200
    assert user.json()["uuid"]


def test_seed_default_profiles_creates_full_vpn_and_ru_direct(client, auth_headers):
    response = client.post("/admin/seed/default-profile", headers=auth_headers)
    assert response.status_code == 200
    profiles = {profile["name"]: profile for profile in response.json()}
    assert set(profiles) == {"Полный VPN", "Российские сервисы напрямую"}
    assert profiles["Полный VPN"]["routing_mode"] == "full_tunnel"
    assert profiles["Полный VPN"]["direct_domains"] == []
    assert profiles["Российские сервисы напрямую"]["routing_mode"] == "ru_direct"
    assert "wbbasket.ru" in profiles["Российские сервисы напрямую"]["direct_domains"]
    assert "chizhik.club" in profiles["Российские сервисы напрямую"]["direct_domains"]
    assert profiles["Полный VPN"]["blocked_domains"] == []
    assert profiles["Российские сервисы напрямую"]["blocked_domains"] == []


def test_access_profile_blocked_domains_are_normalized(client, auth_headers):
    response = client.post(
        "/admin/access-profiles",
        headers=auth_headers,
        json={
            "name": "Blocked",
            "routing_mode": "ru_direct",
            "blocked_domains": [" YouTube.COM. ", "", "youtube.com", "YOUTU.BE", "googlevideo.com"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["blocked_domains"] == ["youtube.com", "youtu.be", "googlevideo.com"]


def test_access_profile_blocked_domains_reject_protocols_paths_and_spaces(client, auth_headers):
    bad_values = ["https://youtube.com/reels", "youtube.com/reels", "you tube.com"]
    for value in bad_values:
        response = client.post(
            "/admin/access-profiles",
            headers=auth_headers,
            json={"name": f"Bad {value}", "routing_mode": "full_tunnel", "blocked_domains": [value]},
        )
        assert response.status_code == 422


def test_node_dry_run_logs_commands(client, auth_headers):
    created = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Dry", "ip_address": "203.0.113.11", "ssh_username": "root", "ssh_password": "secret", "sni": "www.microsoft.com"},
    )
    response = client.post(f"/admin/nodes/{created.json()['id']}/dry-run", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["install_log"]
    assert "secret" not in str(response.json()["install_log"])


def test_node_default_sni_is_recommended_candidate(client, auth_headers):
    response = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Default SNI", "ip_address": "203.0.113.12", "ssh_username": "root", "ssh_password": "secret"},
    )
    assert response.status_code == 200
    assert response.json()["sni"] == "www.googletagmanager.com"
    assert response.json()["fingerprint"] == "chrome"
    assert response.json()["reality_public_key"]
    assert response.json()["short_id"]


def test_node_rejects_empty_sni(client, auth_headers):
    response = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Bad SNI", "ip_address": "203.0.113.13", "ssh_username": "root", "ssh_password": "secret", "sni": ""},
    )
    assert response.status_code == 422


def test_node_rejects_sni_with_scheme(client, auth_headers):
    response = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={
            "name": "Bad SNI",
            "ip_address": "203.0.113.14",
            "ssh_username": "root",
            "ssh_password": "secret",
            "sni": "https://www.googletagmanager.com",
        },
    )
    assert response.status_code == 422


def test_node_rejects_sni_with_path(client, auth_headers):
    response = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={
            "name": "Bad SNI",
            "ip_address": "203.0.113.15",
            "ssh_username": "root",
            "ssh_password": "secret",
            "sni": "www.googletagmanager.com/path",
        },
    )
    assert response.status_code == 422


def test_user_maintenance_actions(client, auth_headers):
    user = client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Иван", "last_name": "Петров", "username": "ivan"},
    ).json()
    old_uuid = user["uuid"]
    old_token = user["subscription_token"]

    disabled = client.post(f"/admin/users/{user['id']}/disable", headers=auth_headers)
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "disabled"

    enabled = client.post(f"/admin/users/{user['id']}/enable", headers=auth_headers)
    assert enabled.status_code == 200
    assert enabled.json()["status"] == "active"

    new_uuid = client.post(f"/admin/users/{user['id']}/regenerate-uuid", headers=auth_headers)
    assert new_uuid.status_code == 200
    assert new_uuid.json()["uuid"] != old_uuid

    new_token = client.post(f"/admin/users/{user['id']}/regenerate-subscription", headers=auth_headers)
    assert new_token.status_code == 200
    assert new_token.json()["subscription_token"] != old_token

    reset = client.post(f"/admin/users/{user['id']}/reset-traffic", headers=auth_headers)
    assert reset.status_code == 200
    assert reset.json()["used_total_bytes"] == 0


def test_connection_check_command_allowlist_is_read_only():
    joined = "\n".join(READ_ONLY_CHECK_COMMANDS)
    assert "apt-get" not in joined
    assert "install-release.sh" not in joined
    assert "cat >" not in joined
    assert "mkdir" not in joined
    assert "cp " not in joined
    assert "chmod" not in joined
    assert "systemctl restart" not in joined
    assert "systemctl enable" not in joined
    assert "ufw" not in joined


def test_real_install_plan_is_only_place_with_mutating_install_commands(client, auth_headers):
    node = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Plan", "ip_address": "203.0.113.16", "ssh_username": "root", "ssh_password": "secret"},
    ).json()
    dry_run = client.post(f"/admin/nodes/{node['id']}/dry-run", headers=auth_headers)
    assert dry_run.status_code == 200
    logs = dry_run.json()["install_log"]
    assert any("apt-get update" in str(log.get("command")) for log in logs)
    assert all(log["message"] == "Сухой запуск: команда не выполнялась" for log in logs if log.get("command"))
    assert all(log["exit_code"] is None for log in logs)
    assert any("chmod 644 /usr/local/etc/xray/config.json" in str(log.get("command")) for log in logs)
    assert "install -m 600" not in str(logs)


def test_delete_node_removes_akfa_record(client, auth_headers):
    node = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Delete", "ip_address": "203.0.113.17", "ssh_username": "root", "ssh_password": "secret"},
    ).json()
    response = client.delete(f"/admin/nodes/{node['id']}", headers=auth_headers)
    assert response.status_code == 200
    assert "не трогает Xray" in response.json()["message"]
    missing = client.get(f"/admin/nodes/{node['id']}")
    assert missing.status_code == 404


def test_verify_endpoint_handles_failed_status(client, auth_headers, monkeypatch):
    node = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Verify", "ip_address": "203.0.113.18", "ssh_username": "root", "ssh_password": "secret"},
    ).json()

    async def fake_verify(self):
        return InstallResult(
            ok=False,
            logs=[
                {
                    "level": "error",
                    "command": "systemctl status xray --no-pager -l",
                    "message": "Код выхода: 3",
                    "stdout": "",
                    "stderr": "failed",
                    "exit_code": 3,
                    "mutating": False,
                }
            ],
        )

    monkeypatch.setattr(XrayInstaller, "verify", fake_verify)
    response = client.post(f"/admin/nodes/{node['id']}/verify", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["install_log"][0]["exit_code"] == 3


def test_install_failure_returns_error_and_does_not_mark_xray_installed(client, auth_headers, db_session, monkeypatch):
    patch_node_job_session(monkeypatch, db_session)
    node = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Install timeout", "ip_address": "203.0.113.20", "ssh_username": "root", "ssh_password": "secret"},
    ).json()

    async def fake_install(self):
        return InstallResult(
            ok=False,
            logs=[
                {
                    "level": "error",
                    "command": "DEBIAN_FRONTEND=noninteractive apt-get update -o Acquire::ForceIPv4=true",
                    "message": "Таймаут выполнения SSH-команды",
                    "stderr": "apt-get update превысил таймаут 180 секунд",
                    "exit_code": 124,
                    "mutating": True,
                }
            ],
        )

    monkeypatch.setattr(XrayInstaller, "install", fake_install)
    response = client.post(f"/admin/nodes/{node['id']}/install", headers=auth_headers)
    assert response.status_code == 202
    job = wait_node_job(client, auth_headers, response.json()["job_id"])
    assert job["status"] == "failed"
    assert "Установка Xray не завершена" in job["error"]

    from app.models import VpsNode

    saved = db_session.get(VpsNode, node["id"])
    db_session.refresh(saved)
    assert saved.status == "failed"
    assert saved.xray_installed is False


def test_install_success_marks_node_online(client, auth_headers, db_session, monkeypatch):
    patch_node_job_session(monkeypatch, db_session)
    node = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Install success", "ip_address": "203.0.113.21", "ssh_username": "root", "ssh_password": "secret"},
    ).json()

    async def fake_install(self):
        return InstallResult(ok=True, logs=[{"level": "info", "message": "Действие завершено успешно"}])

    monkeypatch.setattr(XrayInstaller, "install", fake_install)
    response = client.post(f"/admin/nodes/{node['id']}/install", headers=auth_headers)
    assert response.status_code == 202
    job = wait_node_job(client, auth_headers, response.json()["job_id"])
    assert job["status"] == "success"
    assert job["result"]["status"] == "online"
    assert job["result"]["xray_installed"] is True

    from app.models import VpsNode

    saved = db_session.get(VpsNode, node["id"])
    db_session.refresh(saved)
    assert saved.status == "online"
    assert saved.xray_installed is True


def test_install_commands_have_longer_timeouts(client, auth_headers):
    node = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Timeouts", "ip_address": "203.0.113.22", "ssh_username": "root", "ssh_password": "secret"},
    ).json()
    from app.models import VpsNode

    installer = XrayInstaller(VpsNode(**{k: v for k, v in node.items() if k in {"name", "ip_address", "ssh_port", "ssh_username", "sni", "fingerprint", "vless_port", "public_host", "xray_config_path", "xray_service_name"}}))
    assert installer._timeout_for_command("DEBIAN_FRONTEND=noninteractive apt-get update -o Acquire::ForceIPv4=true") >= 180
    assert installer._timeout_for_command("DEBIAN_FRONTEND=noninteractive apt-get install -y curl") >= 180
    assert installer._timeout_for_command("bash -c \"$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)\" @ install") >= 180


def test_second_install_while_running_reuses_existing_job(client, auth_headers, db_session, monkeypatch):
    patch_node_job_session(monkeypatch, db_session)
    node = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Install running", "ip_address": "203.0.113.23", "ssh_username": "root", "ssh_password": "secret"},
    ).json()

    async def slow_install(self):
        await asyncio.sleep(0.25)
        return InstallResult(ok=True, logs=[{"level": "info", "message": "done"}])

    monkeypatch.setattr(XrayInstaller, "install", slow_install)
    first = client.post(f"/admin/nodes/{node['id']}/install", headers=auth_headers)
    second = client.post(f"/admin/nodes/{node['id']}/install", headers=auth_headers)
    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["job_id"] == first.json()["job_id"]
    assert wait_node_job(client, auth_headers, first.json()["job_id"])["status"] == "success"


def test_apply_config_plan_does_not_reinstall_binary(client, auth_headers):
    node = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Apply Plan", "ip_address": "203.0.113.19", "ssh_username": "root", "ssh_password": "secret"},
    ).json()
    from app.models import VpsNode

    installer = XrayInstaller(VpsNode(**{k: v for k, v in node.items() if k in {"name", "ip_address", "ssh_port", "ssh_username", "sni", "fingerprint", "vless_port", "public_host", "xray_config_path", "xray_service_name"}}))
    plan = "\n".join(installer.apply_config_plan_commands())
    assert "apt-get" not in plan
    assert "install-release.sh" not in plan
    assert ".akfa.bak" in plan
    assert "systemctl restart" in plan


def test_user_create_triggers_apply_config_for_online_node(client, auth_headers, db_session, monkeypatch):
    node_payload = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Online apply", "ip_address": "203.0.113.30", "ssh_username": "root", "ssh_password": "secret"},
    ).json()
    from app.models import VpsNode

    node = db_session.get(VpsNode, node_payload["id"])
    node.status = "online"
    node.install_log = [{"message": "Начата реальная установка Xray"}]
    db_session.commit()
    calls = []

    async def fake_apply(self):
        calls.append([user.username for user in self.users])
        return InstallResult(ok=True, logs=[{"message": "applied"}])

    monkeypatch.setattr(XrayInstaller, "apply_config", fake_apply)
    response = client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Auto", "last_name": "Sync", "username": "auto.sync"},
    )
    assert response.status_code == 200
    assert calls and "auto.sync" in calls[-1]


def test_verified_online_node_gets_default_user_binding_and_config_client(client, auth_headers, db_session, monkeypatch):
    node_payload = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Verified apply", "ip_address": "203.0.113.33", "ssh_username": "root", "ssh_password": "secret"},
    ).json()
    from app.models import VpnUser, VpsNode
    from app.services.xray_config import render_server_config

    node = db_session.get(VpsNode, node_payload["id"])
    node.status = "online"
    node.install_log = [
        {"message": "Выполняется команда", "command": "systemctl status xray --no-pager -l", "exit_code": 0},
        {"message": "Код выхода: 0", "command": "jq empty /usr/local/etc/xray/config.json", "exit_code": 0},
        {"message": "Код выхода: 0", "command": "ss -tulpn | grep ':443' || true", "exit_code": 0},
    ]
    db_session.commit()
    calls = []

    async def fake_apply(self):
        calls.append([user.username for user in self.users])
        return InstallResult(ok=True, logs=[{"message": "applied"}])

    monkeypatch.setattr(XrayInstaller, "apply_config", fake_apply)
    response = client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Verified", "last_name": "Client", "username": "verified-client"},
    )
    assert response.status_code == 200
    user = response.json()
    assert user["allowed_node_ids"] == [node.id]
    assert user["primary_node_id"] == node.id
    assert calls and "verified-client" in calls[-1]
    subscription = client.get(f"/sub/{user['subscription_token']}", headers={"x-hwid": "verified-client-phone"})
    assert subscription.status_code == 200

    db_session.expire_all()
    config = json.loads(render_server_config(db_session.get(VpsNode, node.id), db_session.query(VpnUser).all()))
    clients = config["inbounds"][0]["settings"]["clients"]
    assert clients[0]["email"] == f"akfa_user_{user['id']}_device_1"
    assert clients[0]["id"] != user["uuid"]


def test_user_create_persists_and_reports_apply_failure(client, auth_headers, db_session, monkeypatch):
    node_payload = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Online fail", "ip_address": "203.0.113.31", "ssh_username": "root", "ssh_password": "secret"},
    ).json()
    from app.models import VpsNode, VpnUser

    node = db_session.get(VpsNode, node_payload["id"])
    node.status = "online"
    node.install_log = [{"message": "Начата реальная установка Xray"}]
    db_session.commit()

    async def fake_apply(self):
        return InstallResult(ok=False, logs=[{"message": "failed"}])

    monkeypatch.setattr(XrayInstaller, "apply_config", fake_apply)
    response = client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Bad", "last_name": "Sync", "username": "bad.sync"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "bad.sync"
    assert body["apply_status"]["failed"] == 1
    assert body["apply_status"]["results"][0]["status"] == "failed"
    assert db_session.query(VpnUser).filter_by(username="bad.sync").first() is not None


def test_user_create_with_apply_warning_returns_structured_success_not_false_500(client, auth_headers, db_session, monkeypatch):
    node_payload = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Warning apply", "ip_address": "203.0.113.35", "ssh_username": "root", "ssh_password": "secret"},
    ).json()
    from app.models import VpsNode, VpnUser

    node = db_session.get(VpsNode, node_payload["id"])
    node.status = "online"
    node.install_log = [{"message": "Начата реальная установка Xray"}]
    db_session.commit()

    async def fake_apply(self):
        return InstallResult(ok=False, logs=[{"level": "error", "message": "controlled warning"}])

    monkeypatch.setattr(XrayInstaller, "apply_config", fake_apply)
    response = client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Apply", "last_name": "Warning", "username": "apply.warning"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "apply.warning"
    assert body["apply_status"]["ok"] is False
    assert body["apply_status"]["failed"] == 1
    assert "controlled warning" in body["apply_status"]["results"][0]["error"]
    assert "controlled warning" in body["apply_error"]
    assert db_session.query(VpnUser).filter_by(username="apply.warning").first() is not None


def test_user_create_duplicate_username_returns_clear_error(client, auth_headers, db_session):
    first = client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Dup", "last_name": "User", "username": "duplicate-user"},
    )
    assert first.status_code == 200
    second = client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Dup", "last_name": "Again", "username": "duplicate-user"},
    )
    assert second.status_code == 409
    assert second.json()["detail"] == "Пользователь с таким логином уже существует"


def test_user_create_same_idempotency_key_returns_same_success(client, auth_headers, db_session):
    headers = {**auth_headers, "X-Idempotency-Key": "create-user-same-request"}
    payload = {"first_name": "Same", "last_name": "Request", "username": "same-request-user"}
    first = client.post("/admin/users", headers=headers, json=payload)
    assert first.status_code == 200
    second = client.post("/admin/users", headers=headers, json=payload)
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["username"] == "same-request-user"


def test_user_create_with_idempotency_requires_and_accepts_csrf(client, auth_headers):
    response = client.post(
        "/admin/users",
        headers={**auth_headers, "X-Idempotency-Key": "csrf-create-ok"},
        json={"first_name": "Csrf", "last_name": "Ok", "username": "csrf-create-ok"},
    )
    assert response.status_code == 200
    assert response.json()["username"] == "csrf-create-ok"

    duplicate = client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Csrf", "last_name": "Dup", "username": "csrf-create-ok"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "Пользователь с таким логином уже существует"

    missing_csrf = client.post(
        "/admin/users",
        headers={"X-Idempotency-Key": "csrf-missing"},
        json={"first_name": "No", "last_name": "Csrf", "username": "csrf-missing"},
    )
    assert missing_csrf.status_code == 403
    assert missing_csrf.json()["detail"] == "Неверный CSRF-токен"


def test_delete_user_response_is_parseable_and_repeated_delete_is_ok(client, auth_headers):
    user = client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Delete", "last_name": "Parse", "username": "delete-parse"},
    ).json()
    response = client.delete(f"/admin/users/{user['id']}", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Пользователь помечен как удаленный"
    assert "apply_status" in body
    repeated = client.delete(f"/admin/users/{user['id']}", headers=auth_headers)
    assert repeated.status_code == 200
    assert repeated.json()["message"] == "Пользователь уже удален"


def test_user_create_reports_unhandled_apply_exception_as_warning(client, auth_headers, db_session, monkeypatch):
    node_payload = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Online exception", "ip_address": "203.0.113.32", "ssh_username": "root", "ssh_password": "secret"},
    ).json()
    from app.models import VpsNode, VpnUser
    from app.services.config_apply import ConfigApplyService

    node = db_session.get(VpsNode, node_payload["id"])
    node.status = "online"
    node.install_log = [{"message": "Начата реальная установка Xray"}]
    db_session.commit()

    async def broken_apply(self, *args, **kwargs):
        raise RuntimeError("ssh timeout")

    monkeypatch.setattr(ConfigApplyService, "apply_to_nodes", broken_apply)
    response = client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Warn", "last_name": "Create", "username": "warn.create"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "warn.create"
    assert body["apply_status"]["ok"] is False
    assert body["apply_status"]["failed"] == 1
    assert "ssh timeout" in body["apply_status"]["results"][0]["error"]
    assert db_session.query(VpnUser).filter_by(username="warn.create").first() is not None


def test_user_update_validates_limit_and_reports_apply_status(client, auth_headers, db_session, monkeypatch):
    node_payload = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Update apply", "ip_address": "203.0.113.34", "ssh_username": "root", "ssh_password": "secret"},
    ).json()
    from app.models import VpnUserDevice, VpsNode

    node = db_session.get(VpsNode, node_payload["id"])
    node.status = "online"
    node.install_log = [{"message": "Начата реальная установка Xray"}]
    db_session.commit()
    calls = []

    async def fake_apply(self):
        calls.append(self.node.id)
        return InstallResult(ok=True, logs=[{"message": "applied"}])

    monkeypatch.setattr(XrayInstaller, "apply_config", fake_apply)
    user = client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Edit", "last_name": "User", "username": "edit.user", "device_limit": 3},
    ).json()
    client.get(f"/sub/{user['subscription_token']}", headers={"x-hwid": "edit-device-1"})
    client.get(f"/sub/{user['subscription_token']}", headers={"x-hwid": "edit-device-2"})
    assert db_session.query(VpnUserDevice).filter_by(vpn_user_id=user["id"], status="active").count() == 2

    too_low = client.put(
        f"/admin/users/{user['id']}",
        headers=auth_headers,
        json={**user, "device_limit": 1},
    )
    assert too_low.status_code == 400
    assert too_low.json()["detail"] == "Нельзя установить лимит меньше текущего количества активных устройств."

    updated = client.put(
        f"/admin/users/{user['id']}",
        headers=auth_headers,
        json={
            "first_name": "Edited",
            "last_name": "Person",
            "username": "edited.user",
            "department_id": None,
            "access_profile_id": None,
            "traffic_limit_bytes": 1073741824,
            "device_limit": 2,
            "expires_at": None,
            "status": "disabled",
            "allowed_node_ids": [node.id],
            "primary_node_id": node.id,
        },
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["first_name"] == "Edited"
    assert body["username"] == "edited.user"
    assert body["device_limit"] == 2
    assert body["status"] == "disabled"
    assert body["apply_status"]["ok"] is True
    assert calls


def test_node_update_keeps_subscription_token_and_changes_vless_params(client, auth_headers, db_session, monkeypatch):
    from app.models import VpsNode

    node_payload = client.post(
        "/admin/nodes",
        headers=auth_headers,
        json={"name": "Reality Edit", "ip_address": "203.0.113.71", "ssh_username": "root", "ssh_password": "secret"},
    ).json()
    node = db_session.get(VpsNode, node_payload["id"])
    node.status = "online"
    node.reality_public_key = "public"
    node.reality_private_key = "private"
    node.short_id = "abcdef1234567890"
    node.xray_installed = True
    db_session.commit()

    async def fake_apply(self):
        return InstallResult(ok=True, logs=[{"message": "applied"}])

    monkeypatch.setattr(XrayInstaller, "apply_config", fake_apply)
    user = client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Reality", "last_name": "Edit", "username": "reality-edit"},
    ).json()
    token = user["subscription_token"]

    response = client.put(
        f"/admin/nodes/{node.id}",
        headers=auth_headers,
        json={
            "name": "Reality Edit",
            "ip_address": "203.0.113.71",
            "location": "Paris",
            "public_host": "vpn.example.com",
            "vless_port": 8443,
            "sni": "www.cloudflare.com",
            "fingerprint": "firefox",
            "xray_config_path": "/usr/local/etc/xray/config.json",
            "xray_service_name": "xray",
        },
    )
    assert response.status_code == 200
    assert user["subscription_token"] == token

    subscription = client.get(f"/sub/{token}", headers={"x-hwid": "reality-edit-phone"})
    assert subscription.status_code == 200
    parsed = subscription.text
    assert "vpn.example.com:8443" in parsed
    assert "sni=www.cloudflare.com" in parsed
    assert "fp=firefox" in parsed


def test_backup_export_and_import_roundtrip(client, auth_headers):
    user = client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Backup", "last_name": "User", "username": "backup-user"},
    ).json()
    export_response = client.get("/admin/backup/export", headers=auth_headers)
    assert export_response.status_code == 200
    raw = export_response.content
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        manifest = json.loads(archive.extractfile("manifest.json").read().decode("utf-8"))
        database = json.loads(archive.extractfile("database.json").read().decode("utf-8"))
    assert manifest["app"] == "AKFA"
    assert manifest["backup_version"] == 1
    assert any(row["username"] == "backup-user" for row in database["users"])

    extra = client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Extra", "last_name": "User", "username": "extra-user"},
    ).json()
    assert extra["id"] != user["id"]
    restore_response = client.post(
        "/admin/backup/import",
        headers=auth_headers,
        files={"file": ("akfa-backup-test.tar.gz", raw, "application/gzip")},
    )
    assert restore_response.status_code == 200
    restored = restore_response.json()["restored"]
    assert restored["users"] == 1
    users = client.get("/admin/users", headers=auth_headers).json()
    assert [item["username"] for item in users] == ["backup-user"]


def test_deleted_users_are_hidden_from_user_list_and_dashboard(client, auth_headers):
    active = client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Active", "last_name": "User", "username": "active.user"},
    ).json()
    deleted = client.post(
        "/admin/users",
        headers=auth_headers,
        json={"first_name": "Deleted", "last_name": "User", "username": "deleted.user"},
    ).json()

    delete_response = client.delete(f"/admin/users/{deleted['id']}", headers=auth_headers)
    assert delete_response.status_code == 200

    users = client.get("/admin/users", headers=auth_headers)
    assert users.status_code == 200
    usernames = [user["username"] for user in users.json()]
    assert "active.user" in usernames
    assert "deleted.user" not in usernames

    hidden_detail = client.get(f"/admin/users/{deleted['id']}", headers=auth_headers)
    assert hidden_detail.status_code == 404

    dashboard = client.get("/admin/dashboard", headers=auth_headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["users_total"] == 1
    assert dashboard.json()["users_active"] == 1
    assert active["username"] == "active.user"

    analytics = client.get("/admin/traffic/overview", headers=auth_headers)
    assert analytics.status_code == 200
    analytics_usernames = [user["username"] for user in analytics.json()]
    assert "active.user" in analytics_usernames
    assert "deleted.user" not in analytics_usernames


def test_collect_now_updates_admin_from_actual_xray_json_and_ignores_deleted(client, auth_headers, db_session, monkeypatch):
    from app.models import VpnUser, VpsNode

    node = VpsNode(name="Real node", ip_address="203.0.113.50", ssh_username="root", status="online")
    stale = VpsNode(name="Draft node", ip_address="203.0.113.51", ssh_username="root", status="draft")
    admin_user = VpnUser(
        first_name="Admin",
        last_name="User",
        username="admin",
        uuid="00000000-0000-0000-0000-000000000101",
        subscription_token="admin-token",
    )
    deleted_kvn = VpnUser(
        first_name="Deleted",
        last_name="Kvn",
        username="kvn",
        uuid="00000000-0000-0000-0000-000000000102",
        subscription_token="kvn-token",
        status="deleted",
    )
    deleted_kevin = VpnUser(
        first_name="Kevin",
        last_name="Popins",
        username="Kevin-Popins",
        uuid="00000000-0000-0000-0000-000000000103",
        subscription_token="kevin-token",
        status="deleted",
    )
    db_session.add_all([node, stale, admin_user, deleted_kvn, deleted_kevin])
    db_session.commit()

    async def fake_statsquery(selected_node):
        assert selected_node.id == node.id
        return {
            "node_id": selected_node.id,
            "command": "/usr/local/bin/xray api statsquery --server=127.0.0.1:10085",
            "exit_code": 0,
            "stdout": '{"stat":[{"name":"user>>>admin>>>traffic>>>uplink","value":2131193},{"name":"user>>>admin>>>traffic>>>downlink","value":13488058},{"name":"user>>>kvn>>>traffic>>>uplink","value":777}]}',
            "stderr": "",
            "stdout_preview": "json",
            "stderr_preview": "",
        }

    monkeypatch.setattr("app.services.traffic.run_xray_statsquery", fake_statsquery)
    response = client.post("/admin/traffic/collect-now", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["updated_users"] == 1
    assert body["matched_users"] == ["admin"]
    assert body["selected_nodes"] == [node.id]
    assert body["unmatched_xray_emails"] == ["kvn"]
    assert "Xray отдаёт статистику для kvn" in " ".join(body["errors"])

    db_session.refresh(admin_user)
    db_session.refresh(deleted_kvn)
    assert admin_user.used_upload_bytes == 2131193
    assert admin_user.used_download_bytes == 13488058
    assert admin_user.used_total_bytes == 15619251
    assert admin_user.last_raw_upload_bytes == 2131193
    assert admin_user.last_raw_download_bytes == 13488058
    assert admin_user.last_traffic_collected_at is not None
    assert deleted_kvn.used_total_bytes == 0
    assert deleted_kevin.used_total_bytes == 0

    async def fake_second_statsquery(selected_node):
        return {
            "node_id": selected_node.id,
            "command": "/usr/local/bin/xray api statsquery --server=127.0.0.1:10085",
            "exit_code": 0,
            "stdout": '{"stat":[{"name":"user>>>admin>>>traffic>>>uplink","value":2365411},{"name":"user>>>admin>>>traffic>>>downlink","value":14168288}]}',
            "stderr": "",
            "stdout_preview": "json",
            "stderr_preview": "",
        }

    monkeypatch.setattr("app.services.traffic.run_xray_statsquery", fake_second_statsquery)
    second = client.post("/admin/traffic/collect-now", headers=auth_headers)
    assert second.status_code == 200
    assert second.json()["updated_users"] == 1
    db_session.refresh(admin_user)
    assert admin_user.used_upload_bytes == 2365411
    assert admin_user.used_download_bytes == 14168288
    assert admin_user.used_total_bytes == 16533699
    assert admin_user.last_online_at is not None


def test_collect_now_without_active_nodes_returns_warning(client, auth_headers, db_session):
    from app.models import VpsNode

    db_session.add(VpsNode(name="Draft only", ip_address="203.0.113.52", ssh_username="root", status="draft"))
    db_session.commit()
    response = client.post("/admin/traffic/collect-now", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["updated_users"] == 0
    assert body["message"] == "Нет установленной активной ноды для сбора статистики"
    assert body["selected_nodes"] == []


def test_debug_collect_contains_before_after_values(client, auth_headers, db_session, monkeypatch):
    from app.models import VpnUser, VpsNode

    node = VpsNode(name="Debug node", ip_address="203.0.113.53", ssh_username="root", status="online")
    user = VpnUser(
        first_name="Debug",
        last_name="User",
        username="debug-admin",
        uuid="00000000-0000-0000-0000-000000000104",
        subscription_token="debug-admin-token",
    )
    db_session.add_all([node, user])
    db_session.commit()

    async def fake_statsquery(selected_node):
        return {
            "node_id": selected_node.id,
            "command": "/usr/local/bin/xray api statsquery --server=127.0.0.1:10085",
            "exit_code": 0,
            "stdout": '{"stat":[{"name":"user>>>debug-admin>>>traffic>>>uplink","value":10},{"name":"user>>>debug-admin>>>traffic>>>downlink","value":20}]}',
            "stderr": "",
            "stdout_preview": "json",
            "stderr_preview": "",
        }

    monkeypatch.setattr("app.services.traffic.run_xray_statsquery", fake_statsquery)
    response = client.post("/admin/traffic/debug-collect", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["commands"][0]["command"] == "/usr/local/bin/xray api statsquery --server=127.0.0.1:10085"
    assert body["raw_xray_stats"][0]["name"] == "user>>>debug-admin>>>traffic>>>uplink"
    user_diag = body["akfa_users"][0]
    assert user_diag["before"]["used_total_bytes"] == 0
    assert user_diag["after"]["used_total_bytes"] == 30
    assert body["db_committed"] is True
