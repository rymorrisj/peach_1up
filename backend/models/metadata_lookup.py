from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, ForeignKey, Integer, String, UniqueConstraint
from sqlmodel import Field, SQLModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class Genre(SQLModel, table=True):
    """Provider-resolved genre, joinable onto GameItemBundle (many-to-many).

    Unique on (provider, external_id) for the fast cache-hit path used by a
    provider's own ID resolution loop. name also carries its own unique
    constraint so a genre already known under one provider's ID is reused —
    by exact name match only, no fuzzy matching, instead of duplicated when
    a second provider later resolves the same concept under a different ID.
    """
    __tablename__ = "genres"
    __table_args__ = (UniqueConstraint("provider", "external_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    provider: str = Field(sa_column=Column(String, nullable=False, index=True))
    external_id: Optional[int] = Field(default=None, sa_column=Column(Integer, nullable=True))
    name: str = Field(sa_column=Column(String, nullable=False, unique=True, index=True))


class GameItemBundleGenre(SQLModel, table=True):
    """Join row: one per (bundle, genre) pair. Real FK, not polymorphic —
    genre only ever applies to GameItemBundle, unlike EntityTag's tags."""
    __tablename__ = "game_item_bundle_genres"
    __table_args__ = (UniqueConstraint("game_item_bundle_id", "genre_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    game_item_bundle_id: int = Field(
        sa_column=Column(Integer, ForeignKey("game_item_bundles.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    genre_id: int = Field(
        sa_column=Column(Integer, ForeignKey("genres.id", ondelete="CASCADE"), nullable=False, index=True)
    )


class Developer(SQLModel, table=True):
    """Provider ID -> name cache, used internally by a provider's resolver
    only. Never joined onto GameItemBundle, the resolved name is written
    into GameItemBundle.developer as a plain string, same as publisher."""
    __tablename__ = "developers"
    __table_args__ = (UniqueConstraint("provider", "external_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    provider: str = Field(sa_column=Column(String, nullable=False, index=True))
    external_id: int = Field(sa_column=Column(Integer, nullable=False))
    name: str = Field(sa_column=Column(String, nullable=False))


class Publisher(SQLModel, table=True):
    """Same shape and purpose as Developer, for publisher names."""
    __tablename__ = "publishers"
    __table_args__ = (UniqueConstraint("provider", "external_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    provider: str = Field(sa_column=Column(String, nullable=False, index=True))
    external_id: int = Field(sa_column=Column(Integer, nullable=False))
    name: str = Field(sa_column=Column(String, nullable=False))


def get_or_create_genre(
    db: "Session", name: str, *, provider: Optional[str] = None, external_id: Optional[int] = None
) -> Genre:
    """Resolve a Genre row, creating one if no match exists.

    Two call shapes: a provider's ID-resolution loop passes provider+external_id
    for a true cache-hit lookup; enrich_entity() (which only has a name, no
    provider bookkeeping) passes name only. Both paths fall back to a name
    match before creating a new row, so the same genre never duplicates across
    providers or call sites.
    """
    if provider is not None and external_id is not None:
        existing = db.query(Genre).filter(
            Genre.provider == provider, Genre.external_id == external_id
        ).first()
        if existing:
            return existing

    existing_by_name = db.query(Genre).filter(Genre.name == name).first()
    if existing_by_name:
        return existing_by_name

    genre = Genre(provider=provider or "manual", external_id=external_id, name=name)
    db.add(genre)
    db.flush()
    return genre


def get_or_create_developer(db: "Session", provider: str, external_id: int, name: str) -> Developer:
    existing = db.query(Developer).filter(
        Developer.provider == provider, Developer.external_id == external_id
    ).first()
    if existing:
        return existing
    developer = Developer(provider=provider, external_id=external_id, name=name)
    db.add(developer)
    db.flush()
    return developer


def get_or_create_publisher(db: "Session", provider: str, external_id: int, name: str) -> Publisher:
    existing = db.query(Publisher).filter(
        Publisher.provider == provider, Publisher.external_id == external_id
    ).first()
    if existing:
        return existing
    publisher = Publisher(provider=provider, external_id=external_id, name=name)
    db.add(publisher)
    db.flush()
    return publisher


def get_genres_for_game_item_bundle(bundle_id: int, db: "Session") -> list[str]:
    from sqlalchemy import select as _select

    rows = db.execute(
        _select(Genre.name)
        .join(GameItemBundleGenre, GameItemBundleGenre.genre_id == Genre.id)
        .where(GameItemBundleGenre.game_item_bundle_id == bundle_id)
        .order_by(Genre.name)
    ).scalars().all()
    return list(rows)


def get_genres_for_game_item_bundles(bundle_ids: list[int], db: "Session") -> dict[int, list[str]]:
    """Bulk variant of get_genres_for_game_item_bundle, one query for many bundles."""
    if not bundle_ids:
        return {}
    from sqlalchemy import select as _select

    rows = db.execute(
        _select(GameItemBundleGenre.game_item_bundle_id, Genre.name)
        .join(Genre, GameItemBundleGenre.genre_id == Genre.id)
        .where(GameItemBundleGenre.game_item_bundle_id.in_(bundle_ids))
        .order_by(GameItemBundleGenre.game_item_bundle_id, Genre.name)
    ).all()
    result: dict[int, list[str]] = {}
    for bundle_id, name in rows:
        result.setdefault(bundle_id, []).append(name)
    return result


def set_genres_for_game_item_bundle(db: "Session", bundle_id: int, names: list[str], *, provider: Optional[str] = None) -> None:
    """Replace-all write: delete this bundle's existing genre links, then
    re-link to (get-or-create) a Genre row for each name. Matches how every
    other enrich_entity() field is a full overwrite, not a merge."""
    db.query(GameItemBundleGenre).filter(
        GameItemBundleGenre.game_item_bundle_id == bundle_id
    ).delete()
    for name in names:
        genre = get_or_create_genre(db, name, provider=provider)
        db.add(GameItemBundleGenre(game_item_bundle_id=bundle_id, genre_id=genre.id))
