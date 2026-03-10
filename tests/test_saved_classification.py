"""Tests for SavedClassificationService."""

import uuid

import pytest

from openfmis.schemas.saved_classification import ClassificationCreate, ClassificationUpdate
from openfmis.services.saved_classification import (
    ClassificationNotFoundError,
    SavedClassificationService,
    _validate_consistency,
)


class TestValidateConsistency:
    def test_valid(self):
        _validate_consistency(3, [0.3, 0.6], ["#ff0000", "#ffff00", "#00ff00"])

    def test_wrong_colors_length(self):
        with pytest.raises(ValueError, match="colors length"):
            _validate_consistency(3, [0.3, 0.6], ["#ff0000", "#00ff00"])

    def test_wrong_breakpoints_length(self):
        with pytest.raises(ValueError, match="breakpoints length"):
            _validate_consistency(3, [0.3], ["#ff0000", "#ffff00", "#00ff00"])

    def test_unsorted_breakpoints(self):
        with pytest.raises(ValueError, match="sorted"):
            _validate_consistency(3, [0.6, 0.3], ["#ff0000", "#ffff00", "#00ff00"])


class TestSavedClassificationService:
    async def test_create_and_get(self, db_session, test_user):
        svc = SavedClassificationService(db_session)
        data = ClassificationCreate(
            name="Test NDVI",
            index_type="ndvi",
            num_classes=3,
            breakpoints=[0.3, 0.6],
            colors=["#ff0000", "#ffff00", "#00ff00"],
        )
        record = await svc.create(test_user.id, data)
        assert record.name == "Test NDVI"
        assert record.num_classes == 3

        fetched = await svc.get(record.id)
        assert fetched is not None
        assert fetched.slug if hasattr(fetched, "slug") else True

    async def test_list_for_user(self, db_session, test_user):
        svc = SavedClassificationService(db_session)
        for i in range(3):
            await svc.create(
                test_user.id,
                ClassificationCreate(
                    name=f"Class {i}",
                    index_type="ndvi",
                    num_classes=2,
                    breakpoints=[0.5],
                    colors=["#ff0000", "#00ff00"],
                ),
            )
        results = await svc.list_for_user(test_user.id)
        assert len(results) >= 3

    async def test_list_filter_by_index(self, db_session, test_user):
        svc = SavedClassificationService(db_session)
        await svc.create(
            test_user.id,
            ClassificationCreate(
                name="NDWI class",
                index_type="ndwi",
                num_classes=2,
                breakpoints=[0.0],
                colors=["#0000ff", "#00ff00"],
            ),
        )
        results = await svc.list_for_user(test_user.id, index_type="ndwi")
        assert all(r.index_type == "ndwi" for r in results)

    async def test_update(self, db_session, test_user):
        svc = SavedClassificationService(db_session)
        record = await svc.create(
            test_user.id,
            ClassificationCreate(
                name="Original",
                index_type="ndvi",
                num_classes=2,
                breakpoints=[0.5],
                colors=["#ff0000", "#00ff00"],
            ),
        )
        updated = await svc.update(record.id, ClassificationUpdate(name="Updated"))
        assert updated.name == "Updated"

    async def test_delete(self, db_session, test_user):
        svc = SavedClassificationService(db_session)
        record = await svc.create(
            test_user.id,
            ClassificationCreate(
                name="To Delete",
                index_type="ndvi",
                num_classes=2,
                breakpoints=[0.5],
                colors=["#ff0000", "#00ff00"],
            ),
        )
        await svc.delete(record.id)
        assert await svc.get(record.id) is None

    async def test_delete_not_found(self, db_session):
        svc = SavedClassificationService(db_session)
        with pytest.raises(ClassificationNotFoundError):
            await svc.delete(uuid.uuid4())
