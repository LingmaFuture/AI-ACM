import os
import tempfile
from pathlib import Path

import httpx
import pytest

test_root = Path(tempfile.mkdtemp(prefix="aiacm-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{test_root / 'test.sqlite3'}"
os.environ["LOCAL_STORAGE_PATH"] = str(test_root / "uploads")
os.environ["STORAGE_BACKEND"] = "local"
os.environ["ENVIRONMENT"] = "development"
os.environ["SYNC_TASKS"] = "true"
os.environ["JUDGE_MODE"] = "local"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["AI_API_KEY"] = ""

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed_database  # noqa: E402


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session", autouse=True)
def initialize_database():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()


@pytest.fixture
async def client(initialize_database):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client


async def create_verified_user(client: httpx.AsyncClient, suffix: str):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"learner-{suffix}@example.com",
            "password": "secure-password-123",
            "display_name": f"学习者{suffix}",
        },
    )
    assert response.status_code == 201, response.text
    token = response.json()["verification_token"]
    verified = await client.get("/api/v1/auth/verify", params={"token": token})
    assert verified.status_code == 200
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": f"learner-{suffix}@example.com", "password": "secure-password-123"},
    )
    assert login.status_code == 200, login.text
    return login.json()["user"]
