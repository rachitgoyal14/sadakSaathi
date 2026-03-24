import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestAlertsActive:
    async def test_get_active_alerts_missing_params(self, client: AsyncClient):
        response = await client.get("/api/v1/alerts/active")
        assert response.status_code == 422

    async def test_get_active_alerts_invalid_radius(self, client: AsyncClient):
        response = await client.get(
            "/api/v1/alerts/active?lat=19.0760&lon=72.8777&radius_meters=5000"
        )
        assert response.status_code == 422
