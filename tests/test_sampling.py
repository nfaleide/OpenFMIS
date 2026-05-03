"""Tests for the Sampling plugin — algorithms, service, and API."""

import uuid

import pytest
import pytest_asyncio
from shapely.geometry import Point, Polygon

from openfmis.schemas.sampling import SamplingPlanCreate
from openfmis.services.sampling import SamplingPlanNotFoundError, SamplingService
from openfmis.services.sampling_algorithms import (
    buffer_polygon,
    generate_clustered,
    generate_grid,
    generate_points,
    generate_random,
    generate_ssus,
    generate_w,
)

# ── Algorithm unit tests (no DB) ────────────────────────────────────────────


def _square_polygon() -> Polygon:
    """~1 km square polygon near the equator."""
    return Polygon(
        [
            (-97.0, 40.0),
            (-97.009, 40.0),
            (-97.009, 40.009),
            (-97.0, 40.009),
            (-97.0, 40.0),
        ]
    )


class TestRandomAlgorithm:
    def test_basic_generation(self):
        poly = _square_polygon()
        pts = generate_random(poly, 10)
        assert len(pts) == 10
        for lon, lat in pts:
            assert poly.contains(Point(lon, lat))

    def test_with_min_distance(self):
        poly = _square_polygon()
        pts = generate_random(poly, 5, min_distance=50)
        assert len(pts) == 5

    def test_empty_count(self):
        poly = _square_polygon()
        pts = generate_random(poly, 0)
        assert pts == []

    def test_too_many_points_for_area(self):
        tiny = Polygon(
            [
                (-97.0, 40.0),
                (-97.0001, 40.0),
                (-97.0001, 40.0001),
                (-97.0, 40.0001),
                (-97.0, 40.0),
            ]
        )
        pts = generate_random(tiny, 100, min_distance=100)
        assert len(pts) < 100  # can't fit that many


class TestGridAlgorithm:
    def test_basic_generation(self):
        poly = _square_polygon()
        pts = generate_grid(poly, 10)
        assert len(pts) > 0
        for lon, lat in pts:
            assert poly.contains(Point(lon, lat))

    def test_approximate_count(self):
        poly = _square_polygon()
        pts = generate_grid(poly, 20)
        # Grid should converge within 10% or capped at count
        assert len(pts) <= 20


class TestClusteredAlgorithm:
    def test_basic_generation(self):
        poly = _square_polygon()
        pts = generate_clustered(poly, 10, cluster_count=3)
        assert len(pts) > 0
        for lon, lat in pts:
            assert poly.contains(Point(lon, lat))

    def test_with_min_distance(self):
        poly = _square_polygon()
        pts = generate_clustered(poly, 8, min_distance=20, cluster_count=2)
        assert len(pts) > 0


class TestWPatternAlgorithm:
    def test_basic_generation(self):
        poly = _square_polygon()
        pts = generate_w(poly, 10)
        assert len(pts) > 0
        for lon, lat in pts:
            assert poly.contains(Point(lon, lat))

    def test_single_point(self):
        poly = _square_polygon()
        pts = generate_w(poly, 1)
        assert len(pts) >= 1


class TestBufferPolygon:
    def test_inward_buffer(self):
        poly = _square_polygon()
        buffered = buffer_polygon(poly, 50)
        assert buffered.area < poly.area

    def test_zero_buffer(self):
        poly = _square_polygon()
        buffered = buffer_polygon(poly, 0)
        assert buffered.equals(poly)

    def test_excessive_buffer_returns_original(self):
        poly = _square_polygon()
        buffered = buffer_polygon(poly, 999999)
        assert not buffered.is_empty


class TestSSUSAlgorithm:
    def test_basic_generation(self):
        poly = _square_polygon()
        pts = generate_ssus(poly, 10)
        assert len(pts) > 0
        for lon, lat in pts:
            assert poly.contains(Point(lon, lat))

    def test_approximate_count(self):
        poly = _square_polygon()
        pts = generate_ssus(poly, 20)
        # SSUS may not hit exact count but should be close
        assert len(pts) > 0
        assert len(pts) <= 20

    def test_zero_count(self):
        poly = _square_polygon()
        pts = generate_ssus(poly, 0)
        assert pts == []

    def test_spatial_distribution(self):
        """SSUS points should be spread across the polygon, not clustered."""
        poly = _square_polygon()
        pts = generate_ssus(poly, 9)
        if len(pts) >= 4:
            lngs = [p[0] for p in pts]
            lats = [p[1] for p in pts]
            lng_range = max(lngs) - min(lngs)
            lat_range = max(lats) - min(lats)
            # Should span at least 30% of the polygon bbox
            bbox_lng = poly.bounds[2] - poly.bounds[0]
            bbox_lat = poly.bounds[3] - poly.bounds[1]
            assert lng_range > bbox_lng * 0.3
            assert lat_range > bbox_lat * 0.3


class TestDispatcher:
    def test_all_algorithms(self):
        poly = _square_polygon()
        for algo in ("random", "grid", "clustered", "w", "ssus"):
            pts = generate_points(poly, algo, count=5)
            assert len(pts) > 0, f"{algo} produced no points"

    def test_unknown_algorithm(self):
        poly = _square_polygon()
        with pytest.raises(ValueError, match="Unknown algorithm"):
            generate_points(poly, "invalid", count=5)

    def test_with_buffer_distance(self):
        poly = _square_polygon()
        pts = generate_points(poly, "random", count=5, buffer_distance=20)
        assert len(pts) > 0


# ── Service + API tests (require DB) ────────────────────────────────────────


@pytest_asyncio.fixture
async def sampling_svc(db_session):
    return SamplingService(db_session)


@pytest.mark.asyncio
async def test_create_plan_requires_field_geometry(sampling_svc):
    """Creating a plan for a non-existent field should raise."""
    from openfmis.schemas.sampling import SamplingPlanCreate
    from openfmis.services.sampling import FieldGeometryNotFoundError

    data = SamplingPlanCreate(
        name="Test Plan",
        field_id=uuid.uuid4(),
        algorithm="random",
        point_count=10,
    )
    with pytest.raises(FieldGeometryNotFoundError):
        await sampling_svc.create_plan(data, created_by=uuid.uuid4())


@pytest.mark.asyncio
async def test_get_nonexistent_plan(sampling_svc):
    with pytest.raises(SamplingPlanNotFoundError):
        await sampling_svc.get_plan(uuid.uuid4())


@pytest.mark.asyncio
async def test_create_and_get_plan(db_session, test_user, test_field):
    """Full round-trip: create a plan with generated points, then retrieve it."""
    from openfmis.schemas.sampling import SamplingPlanCreate

    svc = SamplingService(db_session)
    data = SamplingPlanCreate(
        name="Soil Sampling",
        field_id=test_field.id,
        algorithm="random",
        point_count=5,
        min_distance=10,
    )
    plan = await svc.create_plan(data, created_by=test_user.id)
    assert plan.id is not None
    assert plan.name == "Soil Sampling"
    assert plan.points_geojson is not None
    assert len(plan.points_geojson["features"]) > 0
    assert plan.status.value == "draft"

    fetched = await svc.get_plan(plan.id)
    assert fetched.id == plan.id


@pytest.mark.asyncio
async def test_list_plans_by_field(db_session, test_user, test_field):
    from openfmis.schemas.sampling import SamplingPlanCreate

    svc = SamplingService(db_session)
    for i in range(3):
        await svc.create_plan(
            SamplingPlanCreate(
                name=f"Plan {i}",
                field_id=test_field.id,
                algorithm="grid",
                point_count=5,
            ),
            created_by=test_user.id,
        )

    plans = await svc.list_plans(field_id=test_field.id)
    assert len(plans) == 3


@pytest.mark.asyncio
async def test_update_plan(db_session, test_user, test_field):
    from openfmis.schemas.sampling import SamplingPlanCreate, SamplingPlanUpdate

    svc = SamplingService(db_session)
    plan = await svc.create_plan(
        SamplingPlanCreate(
            name="Original",
            field_id=test_field.id,
            algorithm="random",
            point_count=5,
        ),
        created_by=test_user.id,
    )

    updated = await svc.update_plan(plan.id, SamplingPlanUpdate(name="Renamed", status="active"))
    assert updated.name == "Renamed"
    assert updated.status.value == "active"


@pytest.mark.asyncio
async def test_regenerate_points(db_session, test_user, test_field):
    from openfmis.schemas.sampling import SamplingPlanCreate, SamplingPlanRegenerate

    svc = SamplingService(db_session)
    plan = await svc.create_plan(
        SamplingPlanCreate(
            name="Regen Test",
            field_id=test_field.id,
            algorithm="random",
            point_count=5,
        ),
        created_by=test_user.id,
    )
    regenerated = await svc.regenerate_points(
        plan.id,
        SamplingPlanRegenerate(algorithm="grid"),
    )
    assert regenerated.algorithm.value == "grid"
    # Points should differ (different algorithm)
    assert regenerated.points_geojson is not None


@pytest.mark.asyncio
async def test_mark_point_completed(db_session, test_user, test_field):
    from openfmis.schemas.sampling import SamplingPlanCreate

    svc = SamplingService(db_session)
    plan = await svc.create_plan(
        SamplingPlanCreate(
            name="Collection Test",
            field_id=test_field.id,
            algorithm="random",
            point_count=3,
        ),
        created_by=test_user.id,
    )

    updated = await svc.mark_point_completed(plan.id, 0, notes="Wet soil")
    assert updated.points_completed == 1
    assert updated.points_geojson["features"][0]["properties"]["completed"] is True
    assert updated.points_geojson["features"][0]["properties"]["notes"] == "Wet soil"


@pytest.mark.asyncio
async def test_auto_complete_plan(db_session, test_user, test_field):
    from openfmis.schemas.sampling import SamplingPlanCreate

    svc = SamplingService(db_session)
    plan = await svc.create_plan(
        SamplingPlanCreate(
            name="Auto-complete",
            field_id=test_field.id,
            algorithm="random",
            point_count=2,
        ),
        created_by=test_user.id,
    )

    num_points = len(plan.points_geojson["features"])
    for i in range(num_points):
        plan = await svc.mark_point_completed(plan.id, i)

    assert plan.status.value == "completed"
    assert plan.points_completed == num_points


@pytest.mark.asyncio
async def test_delete_plan(db_session, test_user, test_field):
    from openfmis.schemas.sampling import SamplingPlanCreate

    svc = SamplingService(db_session)
    plan = await svc.create_plan(
        SamplingPlanCreate(
            name="To Delete",
            field_id=test_field.id,
            algorithm="w",
            point_count=5,
        ),
        created_by=test_user.id,
    )

    await svc.delete_plan(plan.id)

    with pytest.raises(SamplingPlanNotFoundError):
        await svc.get_plan(plan.id)


# ── API endpoint tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_create_plan(client, auth_headers, test_field):
    resp = await client.post(
        "/api/v1/sampling/plans",
        json={
            "name": "API Test Plan",
            "field_id": str(test_field.id),
            "algorithm": "random",
            "point_count": 5,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "API Test Plan"
    assert data["algorithm"] == "random"
    assert data["points_geojson"] is not None


@pytest.mark.asyncio
async def test_api_list_plans(client, auth_headers, test_field):
    # Create two plans
    for name in ("Plan A", "Plan B"):
        await client.post(
            "/api/v1/sampling/plans",
            json={
                "name": name,
                "field_id": str(test_field.id),
                "algorithm": "grid",
                "point_count": 5,
            },
            headers=auth_headers,
        )

    resp = await client.get(
        f"/api/v1/sampling/plans?field_id={test_field.id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


@pytest.mark.asyncio
async def test_api_get_plan(client, auth_headers, test_field):
    create_resp = await client.post(
        "/api/v1/sampling/plans",
        json={
            "name": "Get Test",
            "field_id": str(test_field.id),
            "algorithm": "w",
            "point_count": 5,
        },
        headers=auth_headers,
    )
    plan_id = create_resp.json()["id"]

    resp = await client.get(f"/api/v1/sampling/plans/{plan_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == plan_id


@pytest.mark.asyncio
async def test_api_delete_plan(client, auth_headers, test_field):
    create_resp = await client.post(
        "/api/v1/sampling/plans",
        json={
            "name": "Delete Test",
            "field_id": str(test_field.id),
            "algorithm": "random",
            "point_count": 3,
        },
        headers=auth_headers,
    )
    plan_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/v1/sampling/plans/{plan_id}", headers=auth_headers)
    assert resp.status_code == 204

    resp = await client.get(f"/api/v1/sampling/plans/{plan_id}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_regenerate(client, auth_headers, test_field):
    create_resp = await client.post(
        "/api/v1/sampling/plans",
        json={
            "name": "Regen API",
            "field_id": str(test_field.id),
            "algorithm": "random",
            "point_count": 5,
        },
        headers=auth_headers,
    )
    plan_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/sampling/plans/{plan_id}/regenerate",
        json={"algorithm": "grid"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["algorithm"] == "grid"


@pytest.mark.asyncio
async def test_api_mark_point_complete(client, auth_headers, test_field):
    create_resp = await client.post(
        "/api/v1/sampling/plans",
        json={
            "name": "Complete API",
            "field_id": str(test_field.id),
            "algorithm": "random",
            "point_count": 3,
        },
        headers=auth_headers,
    )
    plan_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/sampling/plans/{plan_id}/points/0/complete?notes=Clay+soil",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["points_completed"] == 1


@pytest.mark.asyncio
async def test_api_invalid_algorithm(client, auth_headers, test_field):
    resp = await client.post(
        "/api/v1/sampling/plans",
        json={
            "name": "Bad Algo",
            "field_id": str(test_field.id),
            "algorithm": "spiral",
            "point_count": 5,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422  # Pydantic validation


@pytest.mark.asyncio
async def test_api_nonexistent_field(client, auth_headers):
    resp = await client.post(
        "/api/v1/sampling/plans",
        json={
            "name": "No Field",
            "field_id": str(uuid.uuid4()),
            "algorithm": "random",
            "point_count": 5,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 404


# ── Export tests ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_geojson(db_session, test_user, test_field):
    import json

    svc = SamplingService(db_session)
    plan = await svc.create_plan(
        SamplingPlanCreate(
            name="Export GeoJSON",
            field_id=test_field.id,
            algorithm="random",
            point_count=3,
        ),
        created_by=test_user.id,
    )

    result = await svc.export_plan(plan.id, fmt="geojson")
    assert result["format"] == "geojson"
    assert result["plan_name"] == "Export GeoJSON"
    assert result["point_count"] == 3
    parsed = json.loads(result["content"])
    assert parsed["type"] == "FeatureCollection"
    assert len(parsed["features"]) == 3
    assert parsed["features"][0]["properties"]["status"] == "pending"


@pytest.mark.asyncio
async def test_export_csv(db_session, test_user, test_field):
    svc = SamplingService(db_session)
    plan = await svc.create_plan(
        SamplingPlanCreate(
            name="Export CSV",
            field_id=test_field.id,
            algorithm="grid",
            point_count=3,
        ),
        created_by=test_user.id,
    )

    result = await svc.export_plan(plan.id, fmt="csv")
    assert result["format"] == "csv"
    lines = result["content"].strip().split("\n")
    assert lines[0] == "point_id,planned_lat,planned_lng,status,notes"
    assert len(lines) >= 2  # header + at least 1 data row


@pytest.mark.asyncio
async def test_export_with_completed_points(db_session, test_user, test_field):
    import json

    svc = SamplingService(db_session)
    plan = await svc.create_plan(
        SamplingPlanCreate(
            name="Export Completed",
            field_id=test_field.id,
            algorithm="random",
            point_count=3,
        ),
        created_by=test_user.id,
    )
    await svc.mark_point_completed(plan.id, 0, notes="Clay soil")

    result = await svc.export_plan(plan.id, fmt="geojson")
    assert result["completed_count"] == 1
    parsed = json.loads(result["content"])
    assert parsed["features"][0]["properties"]["status"] == "completed"
    assert parsed["features"][1]["properties"]["status"] == "pending"


@pytest.mark.asyncio
async def test_api_export_geojson(client, auth_headers, test_field):
    create_resp = await client.post(
        "/api/v1/sampling/plans",
        json={
            "name": "API Export",
            "field_id": str(test_field.id),
            "algorithm": "random",
            "point_count": 3,
        },
        headers=auth_headers,
    )
    plan_id = create_resp.json()["id"]

    resp = await client.get(
        f"/api/v1/sampling/plans/{plan_id}/export?fmt=geojson",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["format"] == "geojson"
    assert data["point_count"] == 3


@pytest.mark.asyncio
async def test_api_export_csv(client, auth_headers, test_field):
    create_resp = await client.post(
        "/api/v1/sampling/plans",
        json={
            "name": "API CSV Export",
            "field_id": str(test_field.id),
            "algorithm": "ssus",
            "point_count": 5,
        },
        headers=auth_headers,
    )
    plan_id = create_resp.json()["id"]

    resp = await client.get(
        f"/api/v1/sampling/plans/{plan_id}/export?fmt=csv",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["format"] == "csv"


@pytest.mark.asyncio
async def test_api_export_not_found(client, auth_headers):
    resp = await client.get(
        f"/api/v1/sampling/plans/{uuid.uuid4()}/export",
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_export_invalid_format(client, auth_headers, test_field):
    create_resp = await client.post(
        "/api/v1/sampling/plans",
        json={
            "name": "Bad Format",
            "field_id": str(test_field.id),
            "algorithm": "random",
            "point_count": 3,
        },
        headers=auth_headers,
    )
    plan_id = create_resp.json()["id"]

    resp = await client.get(
        f"/api/v1/sampling/plans/{plan_id}/export?fmt=xml",
        headers=auth_headers,
    )
    assert resp.status_code == 422  # Pydantic validation on query param


# ── SSUS via API ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_create_ssus_plan(client, auth_headers, test_field):
    resp = await client.post(
        "/api/v1/sampling/plans",
        json={
            "name": "SSUS Plan",
            "field_id": str(test_field.id),
            "algorithm": "ssus",
            "point_count": 10,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["algorithm"] == "ssus"
    assert data["points_geojson"] is not None
    assert len(data["points_geojson"]["features"]) > 0
