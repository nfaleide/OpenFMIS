"""Top-level router — aggregates all v1 sub-routers."""

from fastapi import APIRouter

from openfmis.api.v1.acl import router as acl_router
from openfmis.api.v1.auth import router as auth_router
from openfmis.api.v1.auto_analysis import router as auto_analysis_router
from openfmis.api.v1.batch_analysis import router as batch_analysis_router
from openfmis.api.v1.billing import router as billing_router
from openfmis.api.v1.clu import router as clu_router
from openfmis.api.v1.custom_scenes import router as custom_scenes_router
from openfmis.api.v1.email_config import router as email_config_router
from openfmis.api.v1.equipment import router as equipment_router
from openfmis.api.v1.export_ import router as export_router
from openfmis.api.v1.field_events import router as field_events_router
from openfmis.api.v1.fields import router as fields_router
from openfmis.api.v1.geometry import router as geometry_router
from openfmis.api.v1.groups import router as groups_router
from openfmis.api.v1.health import router as health_router
from openfmis.api.v1.imagery_export import router as imagery_export_router
from openfmis.api.v1.import_ import router as import_router
from openfmis.api.v1.logos import router as logos_router
from openfmis.api.v1.notifications import router as notifications_router
from openfmis.api.v1.pdf_reports import router as pdf_reports_router
from openfmis.api.v1.photos import router as photos_router
from openfmis.api.v1.plss import router as plss_router
from openfmis.api.v1.plugins import router as plugins_router
from openfmis.api.v1.preferences import router as preferences_router
from openfmis.api.v1.regions import router as regions_router
from openfmis.api.v1.satshot import router as satshot_router
from openfmis.api.v1.saved_classifications import router as saved_classifications_router
from openfmis.api.v1.spectral_indices import router as spectral_indices_router
from openfmis.api.v1.tiles import router as tiles_router
from openfmis.api.v1.users import router as users_router
from openfmis.api.v1.vra import router as vra_router
from openfmis.api.v1.zone_editing import router as zone_editing_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(groups_router)
api_router.include_router(acl_router)
api_router.include_router(fields_router)
api_router.include_router(geometry_router)
api_router.include_router(regions_router)
api_router.include_router(field_events_router)
api_router.include_router(photos_router)
api_router.include_router(equipment_router)
api_router.include_router(preferences_router)
api_router.include_router(logos_router)
api_router.include_router(import_router)
api_router.include_router(export_router)
api_router.include_router(plss_router)
api_router.include_router(clu_router)
api_router.include_router(plugins_router)
api_router.include_router(billing_router)
api_router.include_router(satshot_router)
api_router.include_router(tiles_router)
api_router.include_router(zone_editing_router)
api_router.include_router(saved_classifications_router)
api_router.include_router(auto_analysis_router)
api_router.include_router(notifications_router)
api_router.include_router(vra_router)
api_router.include_router(imagery_export_router)
api_router.include_router(pdf_reports_router)
api_router.include_router(spectral_indices_router)
api_router.include_router(custom_scenes_router)
api_router.include_router(batch_analysis_router)
api_router.include_router(email_config_router)
