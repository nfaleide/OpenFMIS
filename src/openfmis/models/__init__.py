"""SQLAlchemy models — import all models here for Alembic discovery."""

from openfmis.models.base import Base
from openfmis.models.batch_analysis import BatchAnalysis
from openfmis.models.billing import CreditAccount, LedgerEntry, PriceItem
from openfmis.models.clu import CLU
from openfmis.models.custom_scene import CustomScene
from openfmis.models.equipment import Equipment
from openfmis.models.field import Field
from openfmis.models.field_event import FieldEvent, FieldEventEntry
from openfmis.models.group import Group
from openfmis.models.logo import Logo
from openfmis.models.photo import EventPhoto, Photo
from openfmis.models.plss import PLSSSection, PLSSTownship
from openfmis.models.plugin import Plugin
from openfmis.models.preference import Preference
from openfmis.models.privilege import GroupPrivilege, UserPrivilege
from openfmis.models.region import Region, RegionMember
from openfmis.models.satshot import AnalysisJob, AnalysisZone, SceneRecord
from openfmis.models.saved_classification import SavedClassification
from openfmis.models.spectral_index import SpectralIndexDefinition
from openfmis.models.token_blacklist import TokenBlacklist
from openfmis.models.user import User
from openfmis.services.email_delivery import EmailConfig
from openfmis.services.scene_notification import NotificationPreference, SceneNotification

__all__ = [
    "Base",
    "User",
    "Group",
    "UserPrivilege",
    "GroupPrivilege",
    "TokenBlacklist",
    "Field",
    "Region",
    "RegionMember",
    "FieldEvent",
    "FieldEventEntry",
    "Photo",
    "EventPhoto",
    "Equipment",
    "Preference",
    "Logo",
    "PLSSTownship",
    "PLSSSection",
    "CLU",
    "Plugin",
    "CreditAccount",
    "LedgerEntry",
    "PriceItem",
    "SceneRecord",
    "AnalysisZone",
    "AnalysisJob",
    "SavedClassification",
    "SceneNotification",
    "NotificationPreference",
    "SpectralIndexDefinition",
    "CustomScene",
    "BatchAnalysis",
    "EmailConfig",
]
