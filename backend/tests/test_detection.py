import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestYoloEndpoint:
    async def test_yolo_no_image(self, client: AsyncClient):
        response = await client.post("/api/v1/detect/yolo")
        assert response.status_code == 422

    async def test_yolo_invalid_file_type(self, client: AsyncClient):
        files = {"image": ("test.txt", b"not an image", "text/plain")}
        response = await client.post("/api/v1/detect/yolo", files=files)
        assert response.status_code == 400


@pytest.mark.asyncio
class TestDetectionReport:
    async def test_detection_report_missing_required_fields(self, client: AsyncClient):
        form_data = {
            "rider_id": "test-rider",
        }
        response = await client.post("/api/v1/detect/report", data=form_data)
        assert response.status_code == 422
