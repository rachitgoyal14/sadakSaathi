import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestAuthRegister:
    async def test_register_missing_fields(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/register", json={
            "name": "Test",
            "phone": "+919876543211",
        })
        assert response.status_code == 422

    async def test_register_short_password(self, client: AsyncClient, test_rider_data):
        test_rider_data["password"] = "123"
        response = await client.post("/api/v1/auth/register", json=test_rider_data)
        assert response.status_code == 422


@pytest.mark.asyncio
class TestAuthLogin:
    async def test_login_invalid_format(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/login", json={})
        assert response.status_code == 422


@pytest.mark.asyncio
class TestAuthMe:
    async def test_get_me_unauthenticated(self, client: AsyncClient):
        response = await client.get("/api/v1/auth/me")
        assert response.status_code in [401, 403]

    async def test_get_me_invalid_token(self, client: AsyncClient):
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid_token"}
        )
        assert response.status_code in [401, 403]


@pytest.mark.asyncio
class TestAuthLocation:
    async def test_update_location_unauthenticated(self, client: AsyncClient, test_location):
        response = await client.patch(
            f"/api/v1/auth/me/location?lat={test_location['lat']}&lon={test_location['lon']}"
        )
        assert response.status_code in [401, 403]
