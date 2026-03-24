import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"


@pytest.fixture(scope="session")
def event_loop():
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_db_session():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def mock_get_db(mock_db_session):
    async def _get_db():
        yield mock_db_session
    return _get_db


@pytest.fixture
async def client(mock_get_db):
    from app.main import app
    from app.dependencies import get_db
    
    app.dependency_overrides[get_db] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def test_rider_data():
    import uuid
    return {
        "name": "Test Rider",
        "phone": f"+919876543{str(uuid.uuid4())[:4]}",
        "email": "test@example.com",
        "password": "testpass123",
        "platform": "android",
        "city": "Mumbai",
    }


@pytest.fixture
def test_location():
    return {
        "lat": 19.0760,
        "lon": 72.8777,
    }


@pytest.fixture
def test_detection_data(test_location):
    return {
        "rider_id": "test-rider-id",
        "latitude": test_location["lat"],
        "longitude": test_location["lon"],
        "detection_method": "camera",
        "confidence": 0.85,
        "severity": "S2",
        "pothole_type": "dry",
        "speed_kmh": 40.0,
    }
