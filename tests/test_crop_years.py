"""Tests for CropYear CRUD."""

import uuid
from datetime import date

import pytest
import pytest_asyncio

from openfmis.schemas.crop_year import CropYearCreate, CropYearUpdate
from openfmis.services.crop_year import CropYearService


@pytest_asyncio.fixture
async def crop_year_svc(db_session):
    return CropYearService(db_session)


# ── Service tests ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_crop_year(crop_year_svc, test_field):
    data = CropYearCreate(
        field_id=test_field.id,
        label="2025 Corn",
        start_date=date(2025, 4, 1),
        end_date=date(2025, 11, 30),
        crop_code=1,
        tillage="no_till",
    )
    cy = await crop_year_svc.create(data)
    assert cy.id is not None
    assert cy.label == "2025 Corn"
    assert cy.crop_code == 1
    assert cy.tillage == "no_till"


@pytest.mark.asyncio
async def test_list_crop_years(crop_year_svc, test_field):
    for i in range(3):
        await crop_year_svc.create(
            CropYearCreate(
                field_id=test_field.id,
                label=f"Year {i}",
                start_date=date(2023 + i, 1, 1),
                end_date=date(2023 + i, 12, 31),
            )
        )
    items = await crop_year_svc.list_by_field(test_field.id)
    assert len(items) == 3


@pytest.mark.asyncio
async def test_update_crop_year(crop_year_svc, test_field):
    cy = await crop_year_svc.create(
        CropYearCreate(
            field_id=test_field.id,
            label="Original",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
        )
    )
    updated = await crop_year_svc.update(cy.id, CropYearUpdate(label="Renamed"))
    assert updated.label == "Renamed"


@pytest.mark.asyncio
async def test_soft_delete_crop_year(crop_year_svc, test_field):
    cy = await crop_year_svc.create(
        CropYearCreate(
            field_id=test_field.id,
            label="To Delete",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
        )
    )
    await crop_year_svc.soft_delete(cy.id)
    from openfmis.exceptions import NotFoundError

    with pytest.raises(NotFoundError):
        await crop_year_svc.get_by_id(cy.id)


@pytest.mark.asyncio
async def test_date_validation():
    with pytest.raises(ValueError, match="end_date must be after start_date"):
        CropYearCreate(
            field_id=uuid.uuid4(),
            label="Bad Dates",
            start_date=date(2025, 12, 31),
            end_date=date(2025, 1, 1),
        )


@pytest.mark.asyncio
async def test_tillage_validation():
    with pytest.raises(ValueError, match="tillage must be one of"):
        CropYearCreate(
            field_id=uuid.uuid4(),
            label="Bad Tillage",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
            tillage="plow",
        )


# ── API tests ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_create_crop_year(client, auth_headers, test_field):
    resp = await client.post(
        "/api/v1/crop-years",
        json={
            "field_id": str(test_field.id),
            "label": "2025 Soybeans",
            "start_date": "2025-04-15",
            "end_date": "2025-10-31",
            "crop_code": 5,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["label"] == "2025 Soybeans"
    assert data["crop_code"] == 5


@pytest.mark.asyncio
async def test_api_list_crop_years(client, auth_headers, test_field):
    for i in range(2):
        await client.post(
            "/api/v1/crop-years",
            json={
                "field_id": str(test_field.id),
                "label": f"CY {i}",
                "start_date": "2025-01-01",
                "end_date": "2025-12-31",
            },
            headers=auth_headers,
        )
    resp = await client.get(
        f"/api/v1/crop-years?field_id={test_field.id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


@pytest.mark.asyncio
async def test_api_get_crop_year(client, auth_headers, test_field):
    create_resp = await client.post(
        "/api/v1/crop-years",
        json={
            "field_id": str(test_field.id),
            "label": "Get Test",
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
        },
        headers=auth_headers,
    )
    cy_id = create_resp.json()["id"]
    resp = await client.get(f"/api/v1/crop-years/{cy_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == cy_id


@pytest.mark.asyncio
async def test_api_delete_crop_year(client, auth_headers, test_field):
    create_resp = await client.post(
        "/api/v1/crop-years",
        json={
            "field_id": str(test_field.id),
            "label": "Delete Me",
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
        },
        headers=auth_headers,
    )
    cy_id = create_resp.json()["id"]
    resp = await client.delete(f"/api/v1/crop-years/{cy_id}", headers=auth_headers)
    assert resp.status_code == 204
