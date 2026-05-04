import pyotp

from app.models import Admin


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_login_and_me(client):
    response = client.post("/auth/login", json={"email": "admin@example.com", "password": "StrongPass123"})
    assert response.status_code == 200
    assert response.json()["requires_2fa"] is False

    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "admin@example.com"


def test_login_rejects_bad_password(client):
    response = client.post("/auth/login", json={"email": "admin@example.com", "password": "bad"})
    assert response.status_code == 401


def test_totp_setup_start_does_not_enable_or_require_2fa(client, db_session):
    login = client.post("/auth/login", json={"email": "admin@example.com", "password": "StrongPass123"})
    assert login.status_code == 200
    start = client.post("/auth/2fa/setup/start", json={})
    assert start.status_code == 200
    me_before_confirm = client.get("/auth/me")
    assert me_before_confirm.status_code == 200
    assert me_before_confirm.json()["totp_enabled"] is False
    admin = db_session.query(Admin).filter_by(email="admin@example.com").one()
    assert admin.pending_totp_secret == start.json()["secret"]
    assert admin.totp_secret is None
    assert admin.totp_enabled is False
    assert admin.totp_confirmed_at is None

    client.post("/auth/logout")
    next_login = client.post("/auth/login", json={"email": "admin@example.com", "password": "StrongPass123"})
    assert next_login.status_code == 200
    assert next_login.json()["requires_2fa"] is False
    assert next_login.json()["csrf_token"]


def test_totp_confirm_valid_code_enables_and_next_login_requires_2fa(client, db_session):
    client.post("/auth/login", json={"email": "admin@example.com", "password": "StrongPass123"})
    secret = client.post("/auth/2fa/setup/start", json={}).json()["secret"]
    code = pyotp.TOTP(secret).now()

    confirm = client.post("/auth/2fa/setup/confirm", json={"code": code})
    assert confirm.status_code == 200
    assert confirm.json()["admin"]["totp_enabled"] is True
    me_after_confirm = client.get("/auth/me")
    assert me_after_confirm.status_code == 200
    assert me_after_confirm.json()["totp_enabled"] is True
    admin = db_session.query(Admin).filter_by(email="admin@example.com").one()
    assert admin.totp_secret == secret
    assert admin.pending_totp_secret is None
    assert admin.totp_enabled is True
    assert admin.totp_confirmed_at is not None

    client.post("/auth/logout")
    login = client.post("/auth/login", json={"email": "admin@example.com", "password": "StrongPass123"})
    assert login.status_code == 200
    assert login.json()["requires_2fa"] is True
    assert login.json()["login_token"]

    verify = client.post("/auth/2fa/verify", json={"login_token": login.json()["login_token"], "code": pyotp.TOTP(secret).now()})
    assert verify.status_code == 200
    assert verify.json()["csrf_token"]


def test_totp_confirm_invalid_code_keeps_pending_and_disabled(client, db_session):
    client.post("/auth/login", json={"email": "admin@example.com", "password": "StrongPass123"})
    secret = client.post("/auth/2fa/setup/start", json={}).json()["secret"]
    confirm = client.post("/auth/2fa/setup/confirm", json={"code": "000000"})
    assert confirm.status_code == 401
    admin = db_session.query(Admin).filter_by(email="admin@example.com").one()
    assert admin.pending_totp_secret == secret
    assert admin.totp_secret is None
    assert admin.totp_enabled is False


def test_totp_disable_clears_active_and_pending(client, db_session):
    client.post("/auth/login", json={"email": "admin@example.com", "password": "StrongPass123"})
    first_secret = client.post("/auth/2fa/setup/start", json={}).json()["secret"]
    confirm = client.post("/auth/2fa/setup/confirm", json={"code": pyotp.TOTP(first_secret).now()})
    assert confirm.status_code == 200
    csrf_headers = {"X-CSRF-Token": confirm.json()["csrf_token"]}
    pending = client.post("/auth/2fa/setup/start", json={}).json()["secret"]
    assert pending != first_secret

    disabled = client.post("/auth/2fa/disable", headers=csrf_headers, json={"password": "StrongPass123"})
    assert disabled.status_code == 200
    admin = db_session.query(Admin).filter_by(email="admin@example.com").one()
    assert admin.totp_secret is None
    assert admin.pending_totp_secret is None
    assert admin.totp_enabled is False
    assert admin.totp_confirmed_at is None


def test_repeated_totp_setup_start_replaces_pending_without_enabling(client, db_session):
    client.post("/auth/login", json={"email": "admin@example.com", "password": "StrongPass123"})
    first = client.post("/auth/2fa/setup/start", json={}).json()["secret"]
    second = client.post("/auth/2fa/setup/start", json={}).json()["secret"]
    assert second != first
    admin = db_session.query(Admin).filter_by(email="admin@example.com").one()
    assert admin.pending_totp_secret == second
    assert admin.totp_secret is None
    assert admin.totp_enabled is False
