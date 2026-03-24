import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestHazardsList:
    async def test_list_hazards_limit_exceeds_max(self, client: AsyncClient):
        response = await client.get("/api/v1/hazards/?limit=1000")
        assert response.status_code == 422


@pytest.mark.asyncio
class TestHazardsNearby:
    async def test_nearby_hazards_missing_params(self, client: AsyncClient):
        response = await client.get("/api/v1/hazards/nearby")
        assert response.status_code == 422

    async def test_nearby_hazards_radius_exceeds_max(self, client: AsyncClient):
        response = await client.get(
            "/api/v1/hazards/nearby?lat=19.0760&lon=72.8777&radius_meters=10000"
        )
        assert response.status_code == 422
