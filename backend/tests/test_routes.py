import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestRoutes:
    async def test_get_route_options_missing_body(self, client: AsyncClient):
        response = await client.post("/api/v1/routes/options", json={})
        assert response.status_code == 422


@pytest.mark.asyncio
class TestHealthEndpoints:
    async def test_root_endpoint(self, client: AsyncClient):
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "status" in data
