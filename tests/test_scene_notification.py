"""Tests for SceneNotificationService."""

import pytest

from openfmis.models.field import Field
from openfmis.models.group import Group
from openfmis.services.scene_notification import SceneNotificationService

FIELD_WKT = "SRID=4326;MULTIPOLYGON(((-96.0 41.0, -95.9 41.0, -95.9 41.1, -96.0 41.1, -96.0 41.0)))"


@pytest.fixture
async def field_and_user(db_session, test_user):
    group = Group(name="Test Group")
    db_session.add(group)
    await db_session.flush()

    field = Field(
        name="Notif Field",
        geometry=FIELD_WKT,
        area_acres=100.0,
        version=1,
        is_current=True,
        group_id=group.id,
    )
    db_session.add(field)
    await db_session.flush()
    return field, test_user


class TestSceneNotificationService:
    async def test_notify_users(self, db_session, field_and_user):
        field, user = field_and_user
        svc = SceneNotificationService(db_session)
        notifs = await svc.notify_users_for_scene("S2_NOTIF_001", [(user.id, field.id)])
        assert len(notifs) == 1
        assert notifs[0].scene_id == "S2_NOTIF_001"
        assert notifs[0].viewed is False

    async def test_dedup_notifications(self, db_session, field_and_user):
        field, user = field_and_user
        svc = SceneNotificationService(db_session)
        await svc.notify_users_for_scene("S2_DUP", [(user.id, field.id)])
        dupes = await svc.notify_users_for_scene("S2_DUP", [(user.id, field.id)])
        assert len(dupes) == 0

    async def test_list_for_user(self, db_session, field_and_user):
        field, user = field_and_user
        svc = SceneNotificationService(db_session)
        await svc.notify_users_for_scene("S2_LIST_1", [(user.id, field.id)])
        await svc.notify_users_for_scene("S2_LIST_2", [(user.id, field.id)])
        items, total = await svc.list_for_user(user.id)
        assert total >= 2

    async def test_unread_filter(self, db_session, field_and_user):
        field, user = field_and_user
        svc = SceneNotificationService(db_session)
        _notifs = await svc.notify_users_for_scene("S2_UNREAD", [(user.id, field.id)])
        items, total = await svc.list_for_user(user.id, unread_only=True)
        assert total >= 1

    async def test_mark_viewed(self, db_session, field_and_user):
        field, user = field_and_user
        svc = SceneNotificationService(db_session)
        notifs = await svc.notify_users_for_scene("S2_VIEW", [(user.id, field.id)])
        count = await svc.mark_viewed([notifs[0].id])
        assert count == 1

    async def test_set_visibility(self, db_session, field_and_user):
        field, user = field_and_user
        svc = SceneNotificationService(db_session)
        notifs = await svc.notify_users_for_scene("S2_VIS", [(user.id, field.id)])
        count = await svc.set_visibility([notifs[0].id], False)
        assert count == 1

    async def test_preferences(self, db_session, test_user):
        svc = SceneNotificationService(db_session)
        pref = await svc.set_preferences(test_user.id, email_enabled=False)
        assert pref.email_enabled is False

        fetched = await svc.get_preferences(test_user.id)
        assert fetched is not None
        assert fetched.email_enabled is False

        await svc.clear_preferences(test_user.id)
        assert await svc.get_preferences(test_user.id) is None
