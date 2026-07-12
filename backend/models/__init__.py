from backend.models.bios import BiosRequirement
from backend.models.drive import Drive, DriveBase, DriveRead
from backend.models.filesystem import BrowseResult, DirEntry, DriveEntry, DrivesResult, FileEntry
from backend.models.app import (
    AppItemBundle, AppItemBundleCreate, AppItemBundleRead, AppItemBundleUpdate,
    AppItem, AppItemRead, AppItemUpdate,
    app_item_bundle_to_read, app_item_bundles_to_read_bulk,
)
from backend.models.game import (
    ImportErrorItem, ImportResult,
    GameItemBundle, GameItemBundleCreate, GameItemBundleRead, GameItemBundleUpdate,
    GameItem, GameItemRead, GameItemUpdate,
    ScanPreviewItem, ScanStatus,
    game_item_bundle_to_read, game_item_bundles_to_read_bulk,
)
from backend.models.environment import BiosCounts, CountTotal, HealthSummary, InstalledCounts, EnvironmentItem, EnvironmentItemBase, EnvironmentItemCreate, EnvironmentItemHealthCounts, EnvironmentItemUpdate, EnvironmentItemRead, StorageStats
from backend.models.media import (
    LinkedGameRef,
    MediaItemBundle, MediaItemBundleCreate, MediaItemBundleRead, MediaItemBundleUpdate,
    MediaItem, MediaItemCreate, MediaItemRead, MediaItemUpdate,
    MediaLink, MediaLinkCreate, MediaLinkRead,
    media_item_bundle_to_read,
    media_item_bundle_to_read_bulk,
    item_to_read as media_item_to_read,
    items_to_read_bulk as media_items_to_read_bulk,
)
from backend.models.profile import Profile, ProfileBase, ProfileCreate, ProfileUpdate, ProfileRead
from backend.models.launch_history import LaunchHistory, LaunchHistoryBase, LaunchHistoryRead
from backend.models.settings import Settings, SettingsPatch
from backend.models.user import User, UserBase, UserRead
from backend.models.media_restriction import MediaRestriction
from backend.models.tag import EntityTag, Tag, TagCreate, TagRead, get_tags_for_entity
from backend.models.emulator_install import EmulatorInstall
from backend.models.rom_pack import RomPackItem, RomPackItemRead
from backend.models.controller_mapping import (
    ControllerMapping, ControllerMappingBase, ControllerMappingCreate,
    ControllerMappingRead, ControllerMappingUpdate, mapping_to_read as controller_mapping_to_read,
)
from backend.models.metadata_lookup import (
    Developer, Genre, GameItemBundleGenre, Publisher,
    get_genres_for_game_item_bundle, get_genres_for_game_item_bundles,
    get_or_create_developer, get_or_create_genre, get_or_create_publisher,
    set_genres_for_game_item_bundle,
)

# We do not maintain a __all__ as * wildcard imports are to be avoided per project practices