from backend.schemas.tag import TagBase, TagCreate, TagUpdate, TagRead
from backend.schemas.profile import ProfileBase, ProfileCreate, ProfileUpdate, ProfileRead
from backend.schemas.platform import PlatformBase, PlatformCreate, PlatformUpdate, PlatformRead
from backend.schemas.library import LibraryItemBase, LibraryItemCreate, LibraryItemUpdate, LibraryItemRead
from backend.schemas.snapshot import SnapshotBase, SnapshotCreate, SnapshotRead
from backend.schemas.launch_history import LaunchHistoryBase, LaunchHistoryRead
from backend.schemas.user_profile import (
    UserProfileBase, UserProfileCreate, UserProfileUpdate, UserProfileRead,
    ProfilePermissionsBase, ProfilePermissionsUpdate, ProfilePermissionsRead,
    ContentRatingBase, ContentRatingCreate, ContentRatingRead,
)
from backend.schemas.settings import SettingsRead, SettingsPatch

__all__ = [
    "TagBase", "TagCreate", "TagUpdate", "TagRead",
    "ProfileBase", "ProfileCreate", "ProfileUpdate", "ProfileRead",
    "PlatformBase", "PlatformCreate", "PlatformUpdate", "PlatformRead",
    "LibraryItemBase", "LibraryItemCreate", "LibraryItemUpdate", "LibraryItemRead",
    "SnapshotBase", "SnapshotCreate", "SnapshotRead",
    "LaunchHistoryBase", "LaunchHistoryRead",
    "UserProfileBase", "UserProfileCreate", "UserProfileUpdate", "UserProfileRead",
    "ProfilePermissionsBase", "ProfilePermissionsUpdate", "ProfilePermissionsRead",
    "ContentRatingBase", "ContentRatingCreate", "ContentRatingRead",
    "SettingsRead", "SettingsPatch",
]
