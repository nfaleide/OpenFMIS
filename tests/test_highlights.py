"""Tests for the highlight working set service + API."""

import uuid

import pytest

from openfmis.services.highlight import (
    HighlightGeometryService,
    HighlightService,
    reset_backend,
    use_memory_backend,
)

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def _use_memory():
    """Force in-memory backend for all highlight tests."""
    use_memory_backend()
    yield
    reset_backend()


# ── HighlightService (set operations) ────────────────────────────────────────


class TestHighlightService:
    async def test_add_and_list(self):
        svc = HighlightService()
        user_id = uuid.uuid4()
        fid1, fid2 = uuid.uuid4(), uuid.uuid4()

        result = await svc.add(user_id, [fid1, fid2])
        assert len(result) == 2
        assert str(fid1) in result
        assert str(fid2) in result

        listed = await svc.list(user_id)
        assert len(listed) == 2

    async def test_remove(self):
        svc = HighlightService()
        user_id = uuid.uuid4()
        fid1, fid2, fid3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

        await svc.add(user_id, [fid1, fid2, fid3])
        remaining = await svc.remove(user_id, [fid2])
        assert len(remaining) == 2
        assert str(fid2) not in remaining

    async def test_clear(self):
        svc = HighlightService()
        user_id = uuid.uuid4()
        await svc.add(user_id, [uuid.uuid4(), uuid.uuid4()])

        await svc.clear(user_id)
        assert await svc.list(user_id) == []

    async def test_count(self):
        svc = HighlightService()
        user_id = uuid.uuid4()
        assert await svc.count(user_id) == 0

        await svc.add(user_id, [uuid.uuid4(), uuid.uuid4()])
        assert await svc.count(user_id) == 2

    async def test_empty_list(self):
        svc = HighlightService()
        assert await svc.list(uuid.uuid4()) == []

    async def test_remove_from_empty(self):
        svc = HighlightService()
        result = await svc.remove(uuid.uuid4(), [uuid.uuid4()])
        assert result == []

    async def test_user_isolation(self):
        svc = HighlightService()
        user1, user2 = uuid.uuid4(), uuid.uuid4()
        fid1, fid2 = uuid.uuid4(), uuid.uuid4()

        await svc.add(user1, [fid1])
        await svc.add(user2, [fid2])

        assert str(fid1) in await svc.list(user1)
        assert str(fid1) not in await svc.list(user2)
        assert str(fid2) in await svc.list(user2)


# ── HighlightGeometryService (spatial operations) ────────────────────────────


class TestHighlightGeometry:
    async def test_merge(self, db_session, test_field):
        geo_svc = HighlightGeometryService(db_session)
        result = await geo_svc.merge([test_field.id])
        assert result is not None
        assert result["type"] in ("Polygon", "MultiPolygon")

    async def test_merge_empty(self, db_session):
        geo_svc = HighlightGeometryService(db_session)
        result = await geo_svc.merge([uuid.uuid4()])
        assert result is None

    async def test_clip(self, db_session, test_field):
        # Clip with a polygon that overlaps the test field
        clip_geom = {
            "type": "Polygon",
            "coordinates": [
                [
                    [-97.005, 40.0],
                    [-97.005, 40.009],
                    [-96.995, 40.009],
                    [-96.995, 40.0],
                    [-97.005, 40.0],
                ]
            ],
        }
        geo_svc = HighlightGeometryService(db_session)
        result = await geo_svc.clip([test_field.id], clip_geom)
        assert result is not None

    async def test_clip_no_overlap(self, db_session, test_field):
        # Clip with a polygon far from the test field
        clip_geom = {
            "type": "Polygon",
            "coordinates": [
                [
                    [-80.0, 30.0],
                    [-80.0, 30.01],
                    [-79.99, 30.01],
                    [-79.99, 30.0],
                    [-80.0, 30.0],
                ]
            ],
        }
        geo_svc = HighlightGeometryService(db_session)
        result = await geo_svc.clip([test_field.id], clip_geom)
        assert result is None

    async def test_hole(self, db_session, test_field):
        # Cut a small hole in the middle
        hole_geom = {
            "type": "Polygon",
            "coordinates": [
                [
                    [-97.005, 40.004],
                    [-97.005, 40.005],
                    [-97.004, 40.005],
                    [-97.004, 40.004],
                    [-97.005, 40.004],
                ]
            ],
        }
        geo_svc = HighlightGeometryService(db_session)
        result = await geo_svc.hole([test_field.id], hole_geom)
        assert result is not None


# ── API endpoint tests ───────────────────────────────────────────────────────


class TestHighlightAPI:
    async def test_get_empty(self, client, auth_headers):
        resp = await client.get("/api/v1/highlights", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["field_ids"] == []
        assert data["count"] == 0

    async def test_add_and_list(self, client, auth_headers, test_field):
        resp = await client.post(
            "/api/v1/highlights",
            json={"field_ids": [str(test_field.id)]},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert str(test_field.id) in data["field_ids"]
        assert data["count"] == 1

        # List
        resp = await client.get("/api/v1/highlights", headers=auth_headers)
        assert resp.json()["count"] == 1

    async def test_remove(self, client, auth_headers, test_field):
        fid2 = uuid.uuid4()
        await client.post(
            "/api/v1/highlights",
            json={"field_ids": [str(test_field.id), str(fid2)]},
            headers=auth_headers,
        )
        resp = await client.request(
            "DELETE",
            "/api/v1/highlights",
            json={"field_ids": [str(fid2)]},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    async def test_clear(self, client, auth_headers, test_field):
        await client.post(
            "/api/v1/highlights",
            json={"field_ids": [str(test_field.id)]},
            headers=auth_headers,
        )
        resp = await client.delete("/api/v1/highlights/all", headers=auth_headers)
        assert resp.status_code == 204

        resp = await client.get("/api/v1/highlights", headers=auth_headers)
        assert resp.json()["count"] == 0

    async def test_merge_endpoint(self, client, auth_headers, test_field):
        await client.post(
            "/api/v1/highlights",
            json={"field_ids": [str(test_field.id)]},
            headers=auth_headers,
        )
        resp = await client.post("/api/v1/highlights/merge", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["geometry"] is not None

    async def test_merge_empty_set(self, client, auth_headers):
        resp = await client.post("/api/v1/highlights/merge", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["geometry"] is None
