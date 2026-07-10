from backend.models.bios import BiosRequirement
from backend.models.drive import Drive, DriveBase, DriveRead
from backend.models.filesystem import BrowseResult, DirEntry, DriveEntry, DrivesResult, FileEntry
from backend.models.software import (
    ImportErrorItem, ImportResult,
    SoftwareCollection, SoftwareCollectionCreate, SoftwareCollectionRead, SoftwareCollectionUpdate,
    SoftwareItem, SoftwareItemRead, SoftwareItemUpdate,
    ScanPreviewItem, ScanStatus,
    collection_to_read, collections_to_read_bulk,
)
from backend.models.environment import BiosCounts, CountTotal, HealthSummary, InstalledCounts, Environment, EnvironmentBase, EnvironmentCreate, EnvironmentHealthCounts, EnvironmentUpdate, EnvironmentRead, StorageStats
from backend.models.profile import Profile, ProfileBase, ProfileCreate, ProfileUpdate, ProfileRead
from backend.models.launch_history import LaunchHistory, LaunchHistoryBase, LaunchHistoryRead
from backend.models.settings import Settings, SettingsPatch
from backend.models.user import User, UserBase, UserRead
from backend.models.media_restriction import MediaRestriction
from backend.models.tag import EntityTag, Tag, TagCreate, TagRead, get_tags_for_entity
from backend.models.emulator_install import EmulatorInstall
from backend.models.metadata_lookup import (
    Developer, Genre, LibraryCollectionGenre, Publisher,
    get_genres_for_collection, get_genres_for_collections,
    get_or_create_developer, get_or_create_genre, get_or_create_publisher,
    set_genres_for_collection,
)

# We do not maintain a __all__ as * wildcard imports are to be avoided per project practices