"""Plain helpers shared by the Accept All tests."""

_BOX = "https://cdn.thegamesdb.net/images/original/boxart/front/1.jpg"


def _url(n: int) -> str:
    return f"https://cdn.thegamesdb.net/images/original/screenshots/{n}.jpg"


def _game(db, title="Doom"):
    from backend.models.game import GameItemBundle

    game = GameItemBundle(title=title, platform="dos", slug=title.lower())
    db.add(game)
    db.commit()
    db.refresh(game)
    return game


def _assets(*urls, types=None):
    from backend.service.metadata_providers import MetadataAsset

    types = types or ["screenshot"] * len(urls)
    return [MetadataAsset(url=u, type=t) for u, t in zip(urls, types)]


def _counts(db):
    from backend.models.media import MediaItem, MediaItemBundle, MediaLink

    return db.query(MediaItem).count(), db.query(MediaItemBundle).count(), db.query(MediaLink).count()


def _game_with_discs(db, count=1, display=None):
    from backend.models.game import GameItem

    game = _game(db)
    leaves = []
    for number in range(1, count + 1):
        leaf = GameItem(
            game_item_bundle_id=game.id, file_path=f"/library/games/doom/disc{number}.iso", disc_number=number
        )
        db.add(leaf)
        db.commit()
        db.refresh(leaf)
        leaves.append(leaf)
    if display is not None:
        game.display_disk_id = leaves[display].id
        db.commit()
    return game, leaves
