"""Tests for PointDataset CRUD, cleaning log, and data validation."""

from datetime import date

import pytest
import pytest_asyncio

from openfmis.schemas.point_dataset import CleaningLogCreate, PointDatasetCreate, PointDatasetUpdate
from openfmis.services.data_validation import validate_rows
from openfmis.services.point_dataset import PointDatasetService


@pytest_asyncio.fixture
async def pd_svc(db_session):
    return PointDatasetService(db_session)


# ── Service tests ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_point_dataset(pd_svc, test_field):
    data = PointDatasetCreate(
        field_id=test_field.id,
        dataset_type="soil_test",
        label="Spring Grid 2025",
        value_column="p_ppm",
        unit="ppm",
        sample_date=date(2025, 3, 15),
        raw_count=120,
        clean_count=108,
    )
    ds = await pd_svc.create(data)
    assert ds.id is not None
    assert ds.dataset_type == "soil_test"
    assert ds.label == "Spring Grid 2025"
    assert ds.raw_count == 120


@pytest.mark.asyncio
async def test_list_datasets_with_filters(pd_svc, test_field):
    for dtype in ("soil_test", "yield", "soil_test"):
        await pd_svc.create(
            PointDatasetCreate(
                field_id=test_field.id,
                dataset_type=dtype,
                label=f"{dtype} test",
            )
        )
    all_ds = await pd_svc.list_datasets(field_id=test_field.id)
    assert len(all_ds) == 3

    soil = await pd_svc.list_datasets(field_id=test_field.id, dataset_type="soil_test")
    assert len(soil) == 2


@pytest.mark.asyncio
async def test_update_dataset(pd_svc, test_field):
    ds = await pd_svc.create(
        PointDatasetCreate(
            field_id=test_field.id,
            dataset_type="yield",
            label="Original",
        )
    )
    updated = await pd_svc.update(ds.id, PointDatasetUpdate(label="Renamed", raw_count=200))
    assert updated.label == "Renamed"
    assert updated.raw_count == 200


@pytest.mark.asyncio
async def test_soft_delete_dataset(pd_svc, test_field):
    ds = await pd_svc.create(
        PointDatasetCreate(
            field_id=test_field.id,
            dataset_type="ec_em",
            label="Delete Me",
        )
    )
    await pd_svc.soft_delete(ds.id)
    from openfmis.exceptions import NotFoundError

    with pytest.raises(NotFoundError):
        await pd_svc.get_by_id(ds.id)


@pytest.mark.asyncio
async def test_cleaning_log(pd_svc, test_field):
    ds = await pd_svc.create(
        PointDatasetCreate(
            field_id=test_field.id,
            dataset_type="soil_test",
            label="With Cleaning",
        )
    )
    await pd_svc.add_cleaning_step(
        ds.id,
        CleaningLogCreate(
            rule_type="iqr",
            parameters={"factor": 1.5},
            points_removed=12,
        ),
    )
    await pd_svc.add_cleaning_step(
        ds.id,
        CleaningLogCreate(
            rule_type="edge_buffer",
            parameters={"meters": 10},
            points_removed=5,
        ),
    )
    logs = await pd_svc.get_cleaning_log(ds.id)
    assert len(logs) == 2
    assert logs[0].rule_type == "iqr"
    assert logs[0].points_removed == 12


# ── Data validation tests ─────────────────────────────────────────────────


class TestDataValidation:
    def test_valid_soil_data(self):
        issues = validate_rows(
            "soil_test",
            [
                {"ph": 6.5, "p_ppm": 25, "k_ppm": 150, "lat": 40.0, "lon": -97.0},
            ],
        )
        assert len(issues) == 0

    def test_soil_out_of_range(self):
        issues = validate_rows(
            "soil_test",
            [
                {"ph": 15.0, "lat": 40.0, "lon": -97.0},
            ],
        )
        assert len(issues) == 1
        assert "outside plausible range" in issues[0].issue

    def test_coordinates_out_of_range(self):
        issues = validate_rows(
            "soil_test",
            [
                {"ph": 6.5, "lat": 200, "lon": -97.0},
            ],
        )
        assert len(issues) == 1
        assert "Latitude" in issues[0].issue

    def test_conus_check(self):
        issues = validate_rows(
            "soil_test",
            [
                {"lat": 10.0, "lon": -97.0},
            ],
            conus_only=True,
        )
        assert len(issues) == 1
        assert "CONUS" in issues[0].issue

    def test_yield_validation(self):
        issues = validate_rows(
            "yield",
            [
                {"yield": 600, "lat": 40.0, "lon": -97.0},
            ],
            unit="bu/ac",
        )
        assert len(issues) == 1

    def test_ec_validation(self):
        issues = validate_rows(
            "ec_em",
            [
                {"ec_shallow": 250, "lat": 40.0, "lon": -97.0},
            ],
        )
        assert len(issues) == 1


# ── API tests ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_create_dataset(client, auth_headers, test_field):
    resp = await client.post(
        "/api/v1/point-datasets",
        json={
            "field_id": str(test_field.id),
            "dataset_type": "soil_test",
            "label": "API Soil Test",
            "value_column": "p_ppm",
            "unit": "ppm",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["dataset_type"] == "soil_test"


@pytest.mark.asyncio
async def test_api_list_datasets(client, auth_headers, test_field):
    await client.post(
        "/api/v1/point-datasets",
        json={
            "field_id": str(test_field.id),
            "dataset_type": "yield",
            "label": "Yield Data",
        },
        headers=auth_headers,
    )
    resp = await client.get(
        f"/api/v1/point-datasets?field_id={test_field.id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_api_cleaning_log(client, auth_headers, test_field):
    create_resp = await client.post(
        "/api/v1/point-datasets",
        json={
            "field_id": str(test_field.id),
            "dataset_type": "soil_test",
            "label": "Cleaning Log Test",
        },
        headers=auth_headers,
    )
    ds_id = create_resp.json()["id"]

    add_resp = await client.post(
        f"/api/v1/point-datasets/{ds_id}/cleaning-log",
        json={
            "rule_type": "iqr",
            "parameters": {"factor": 1.5},
            "points_removed": 10,
        },
        headers=auth_headers,
    )
    assert add_resp.status_code == 201

    log_resp = await client.get(
        f"/api/v1/point-datasets/{ds_id}/cleaning-log",
        headers=auth_headers,
    )
    assert log_resp.status_code == 200
    assert len(log_resp.json()) == 1


@pytest.mark.asyncio
async def test_api_validate_data(client, auth_headers):
    resp = await client.post(
        "/api/v1/point-ingestion/validate",
        json={
            "dataset_type": "soil_test",
            "values": [
                {"ph": 6.5, "p_ppm": 25, "lat": 40.0, "lon": -97.0},
                {"ph": 15.0, "lat": 40.0, "lon": -97.0},
            ],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False
    assert data["total_rows"] == 2
    assert len(data["issues"]) >= 1
