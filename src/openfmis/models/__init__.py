"""SQLAlchemy models — import all models here for Alembic discovery."""

from openfmis.models.adapt_map import ADAPTEntityMap
from openfmis.models.api_key import APIKey
from openfmis.models.base import Base
from openfmis.models.billing import CreditAccount, LedgerEntry, PriceItem
from openfmis.models.clu import CLU
from openfmis.models.core_dataset import CoreDataset
from openfmis.models.crop_year import CropYear
from openfmis.models.equipment import Equipment
from openfmis.models.export_link import ExportLink
from openfmis.models.field import Field
from openfmis.models.field_boundary_version import FieldBoundaryVersion
from openfmis.models.field_event import FieldEvent, FieldEventEntry
from openfmis.models.group import Group
from openfmis.models.logo import Logo
from openfmis.models.photo import EventPhoto, Photo
from openfmis.models.plss import PLSSSection, PLSSTownship
from openfmis.models.plugin import Plugin
from openfmis.models.point_dataset import PointCleaningLog, PointDataset
from openfmis.models.preference import Preference
from openfmis.models.prescription import InterpolationSurface, Prescription
from openfmis.models.privilege import GroupPrivilege, UserPrivilege
from openfmis.models.region import Region, RegionMember
from openfmis.models.sampling import SamplingPlan
from openfmis.models.session_audit import SessionAudit
from openfmis.models.subscription import Subscription
from openfmis.models.sync import SyncConflict, SyncState
from openfmis.models.token_blacklist import TokenBlacklist
from openfmis.models.user import User
from openfmis.services.email_delivery import EmailConfig

__all__ = [
    "APIKey",
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
    "CoreDataset",
    "ExportLink",
    "Plugin",
    "CreditAccount",
    "LedgerEntry",
    "PriceItem",
    "EmailConfig",
    "SamplingPlan",
    "ADAPTEntityMap",
    "CropYear",
    "FieldBoundaryVersion",
    "PointDataset",
    "PointCleaningLog",
    "InterpolationSurface",
    "Prescription",
    "SessionAudit",
    "Subscription",
    "SyncState",
    "SyncConflict",
]
