import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine

from main import app
from database.session import get_session


TEST_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False}
)


def override_get_session():
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        yield session


app.dependency_overrides[get_session] = override_get_session


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


@pytest.fixture
def test_user():
    return {
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpass123",
        "full_name": "Test User",
        "role": "employee"
    }