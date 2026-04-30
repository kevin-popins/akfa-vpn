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
