"""Health endpoint smoke tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_health_ready(client: AsyncClient):
    resp = await client.get("/api/v1/health/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "postgis" in data
