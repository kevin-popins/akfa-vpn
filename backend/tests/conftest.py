import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.security import _login_attempts, hash_password
from app.db.session import get_db
from app.main import app
from app.models import Admin, Base


@pytest.fixture()
def db_session():
    settings.environment = "test"
    _login_attempts.clear()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    db.add(Admin(email="admin@example.com", password_hash=hash_password("StrongPass123"), role="super_admin"))
    db.commit()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(client):
    response = client.post("/auth/login", json={"email": "admin@example.com", "password": "StrongPass123"})
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}
