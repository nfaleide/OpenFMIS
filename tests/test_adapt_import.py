"""ADAPT JSON import tests — service + API round-trip."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.exceptions import ValidationError
from openfmis.services.adapt_import import ADAPTImportService

# ── Sample ADAPT documents ────────────────────────────────────────────────

SAMPLE_GROWER = {
    "type": "Grower",
    "id": str(uuid.uuid4()),
    "name": "Smith Farms",
    "farms": [
        {
            "type": "Farm",
            "id": str(uuid.uuid4()),
            "name": "Home Place",
            "fields": [
                {
                    "type": "Field",
                    "id": str(uuid.uuid4()),
                    "name": "North 40",
                    "fsa_tract": "1234",
                    "fsa_field": "5",
                    "crop_zones": [
                        {
                            "type": "CropZone",
                            "id": str(uuid.uuid4()),
                            "label": "2024",
                            "start_date": "2024-01-01",
                            "end_date": "2024-12-31",
                            "crop_code": "41",
                        }
                    ],
                },
                {
                    "type": "Field",
                    "id": str(uuid.uuid4()),
                    "name": "South 80",
                },
            ],
        }
    ],
}

SAMPLE_FARM = {
    "type": "Farm",
    "id": str(uuid.uuid4()),
    "name": "River Farm",
    "fields": [
        {
            "type": "Field",
            "id": str(uuid.uuid4()),
            "name": "Bottom Field",
        }
    ],
}

SAMPLE_FIELD = {
    "type": "Field",
    "id": str(uuid.uuid4()),
    "name": "Standalone Field",
    "clu_id": "CLU-999",
}


# ── Service tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_import_grower_creates_hierarchy(db_session: AsyncSession):
    svc = ADAPTImportService(db_session)
    result = await svc.import_adapt_json(SAMPLE_GROWER)

    assert result.groups_created == 1
    assert result.regions_created == 1  # one farm
    assert result.fields_created == 2  # two fields
    assert result.crop_years_created == 1
    assert result.mappings_created == 5  # grower + farm + 2 fields + 1 crop zone
    assert result.warnings == []


@pytest.mark.asyncio
async def test_import_grower_into_existing_group(db_session: AsyncSession, test_group):
    svc = ADAPTImportService(db_session)
    result = await svc.import_adapt_json(SAMPLE_GROWER, target_group_id=test_group.id)

    # Should NOT create a new group
    assert result.groups_created == 0
    assert result.regions_created == 1
    assert result.fields_created == 2


@pytest.mark.asyncio
async def test_import_farm_requires_group(db_session: AsyncSession):
    svc = ADAPTImportService(db_session)
    with pytest.raises(ValidationError, match="target_group_id"):
        await svc.import_adapt_json(SAMPLE_FARM)


@pytest.mark.asyncio
async def test_import_farm_into_group(db_session: AsyncSession, test_group):
    svc = ADAPTImportService(db_session)
    result = await svc.import_adapt_json(SAMPLE_FARM, target_group_id=test_group.id)

    assert result.regions_created == 1
    assert result.fields_created == 1


@pytest.mark.asyncio
async def test_import_field_creates_default_region(db_session: AsyncSession, test_group):
    svc = ADAPTImportService(db_session)
    result = await svc.import_adapt_json(SAMPLE_FIELD, target_group_id=test_group.id)

    assert result.fields_created == 1
    assert result.regions_created == 1  # "Imported" default region


@pytest.mark.asyncio
async def test_import_idempotent(db_session: AsyncSession):
    """Importing the same document twice should skip already-mapped entities."""
    svc = ADAPTImportService(db_session)
    r1 = await svc.import_adapt_json(SAMPLE_GROWER)
    assert r1.fields_created == 2

    r2 = await svc.import_adapt_json(SAMPLE_GROWER)
    # Everything should be skipped since ADAPT IDs already mapped
    assert r2.fields_created == 0
    assert r2.skipped >= 2


@pytest.mark.asyncio
async def test_import_unknown_type(db_session: AsyncSession):
    svc = ADAPTImportService(db_session)
    with pytest.raises(ValidationError, match="Unknown ADAPT document type"):
        await svc.import_adapt_json({"type": "Spaceship", "name": "X"})


@pytest.mark.asyncio
async def test_import_field_no_name_skipped(db_session: AsyncSession, test_group):
    svc = ADAPTImportService(db_session)
    data = {
        "type": "Farm",
        "name": "Farm",
        "fields": [{"type": "Field"}],  # no name
    }
    result = await svc.import_adapt_json(data, target_group_id=test_group.id)
    assert result.fields_created == 0
    assert result.skipped == 1
    assert any("no name" in w.lower() for w in result.warnings)


@pytest.mark.asyncio
async def test_import_crop_zone_missing_dates(db_session: AsyncSession, test_group):
    svc = ADAPTImportService(db_session)
    data = {
        "type": "Farm",
        "name": "Farm",
        "fields": [
            {
                "type": "Field",
                "name": "F1",
                "crop_zones": [{"label": "Bad", "type": "CropZone"}],
            }
        ],
    }
    result = await svc.import_adapt_json(data, target_group_id=test_group.id)
    assert result.crop_years_created == 0
    assert any("missing dates" in w.lower() for w in result.warnings)


# ── Round-trip test (export → import) ────────────────────────────────────


@pytest.mark.asyncio
async def test_export_import_roundtrip(
    db_session: AsyncSession, test_group, test_region, test_field
):
    """Export a group, then import the result into a new group with fresh IDs."""
    import json

    from openfmis.models.group import Group
    from openfmis.services.adapt_export import ADAPTExportService

    # Export existing group
    export_svc = ADAPTExportService(db_session)
    exported = await export_svc.export_group(test_group.id)

    # Replace all ADAPT IDs with fresh UUIDs so import treats them as new
    text = json.dumps(exported)
    for _key in ("id",):
        # Find all UUID-like strings and replace each with a fresh one
        import re

        uuid_re = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
        for old_id in set(re.findall(uuid_re, text)):
            text = text.replace(old_id, str(uuid.uuid4()))
    exported = json.loads(text)

    # Create a fresh target group
    new_group = Group(id=uuid.uuid4(), name="Import Target")
    db_session.add(new_group)
    await db_session.flush()

    # Import into it
    import_svc = ADAPTImportService(db_session)
    result = await import_svc.import_adapt_json(exported, target_group_id=new_group.id)

    # Should create at least the region and field
    assert result.regions_created >= 1
    assert result.fields_created >= 1


# ── API tests ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_import_adapt(client, auth_headers, test_group):
    resp = await client.post(
        f"/api/v1/adapt-map/import?target_group_id={test_group.id}",
        json=SAMPLE_FARM,
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["regions_created"] == 1
    assert data["fields_created"] == 1


@pytest.mark.asyncio
async def test_api_import_adapt_invalid_type(client, auth_headers):
    resp = await client.post(
        "/api/v1/adapt-map/import",
        json={"type": "Invalid"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
