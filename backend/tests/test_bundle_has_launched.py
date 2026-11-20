"""Tests for GameItemBundleRead.has_launched (_bundle_has_launched in
backend/models/game.py): true when any LaunchHistory row exists for the bundle,
set on the single-bundle read only and left None on list (bulk) reads so a list
adds no per-bundle query.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import event


@pytest.fixture
def db():
    from sqlalchemy.pool import StaticPool
    from sqlmodel import SQLModel, Session, create_engine
    import backend.models  # noqa: F401, registers all table models

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _bundle(db, slug="doom", **overrides):
    from backend.models.game import GameItem, GameItemBundle

    kwargs = dict(title=slug.title(), file_path=f"/library/games/dos/{slug}", era="dos", slug=slug)
    kwargs.update(overrides)
    bundle = GameItemBundle(**kwargs)
    db.add(bundle)
    db.commit()
    db.refresh(bundle)
    db.add(GameItem(
        game_item_bundle_id=bundle.id, disc_number=1, file_path=f"/library/games/dos/{slug}/{slug}.exe",
    ))
    db.commit()
    db.refresh(bundle)
    return bundle


def _launch(db, bundle_id, **overrides):
    from backend.models.launch_history import LaunchHistory

    kwargs = dict(
        game_item_bundle_id=bundle_id,
        emulator_slug="dosbox-x",
        started_at=datetime.now(timezone.utc),
    )
    kwargs.update(overrides)
    row = LaunchHistory(**kwargs)
    db.add(row)
    db.commit()
    return row


def _statements_during(db, fn):
    statements: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", _record)
    try:
        result = fn()
    finally:
        event.remove(engine, "before_cursor_execute", _record)
    return result, statements


class TestHasLaunchedOnDetailRead:
    def test_false_with_no_history(self, db):
        from backend.models.game import game_item_bundle_to_read

        assert game_item_bundle_to_read(_bundle(db), db).has_launched is False

    def test_true_with_a_clean_history_row(self, db):
        from backend.models.game import game_item_bundle_to_read

        bundle = _bundle(db)
        _launch(db, bundle.id, ended_at=datetime.now(timezone.utc), exit_code=0)

        assert game_item_bundle_to_read(bundle, db).has_launched is True

    def test_true_when_the_only_row_has_an_error_message(self, db):
        from backend.models.game import game_item_bundle_to_read

        bundle = _bundle(db)
        _launch(
            db, bundle.id, error_message="Launch timed out after 30s.", exit_code=-1,
            ended_at=datetime.now(timezone.utc),
        )

        assert game_item_bundle_to_read(bundle, db).has_launched is True

    def test_true_for_a_row_that_never_ended(self, db):
        from backend.models.game import game_item_bundle_to_read

        bundle = _bundle(db)
        _launch(db, bundle.id)

        assert game_item_bundle_to_read(bundle, db).has_launched is True

    def test_only_this_bundles_history_counts(self, db):
        from backend.models.game import game_item_bundle_to_read

        launched = _bundle(db, slug="doom")
        untouched = _bundle(db, slug="quake")
        _launch(db, launched.id)

        assert game_item_bundle_to_read(launched, db).has_launched is True
        assert game_item_bundle_to_read(untouched, db).has_launched is False

    def test_a_history_row_for_no_bundle_does_not_count(self, db):
        from backend.models.game import game_item_bundle_to_read

        bundle = _bundle(db)
        _launch(db, None)

        assert game_item_bundle_to_read(bundle, db).has_launched is False

    def test_detail_read_costs_one_extra_query(self, db):
        from backend.models.game import game_item_bundle_to_read

        bundle = _bundle(db)
        _, statements = _statements_during(db, lambda: game_item_bundle_to_read(bundle, db))

        assert sum("launch_history" in s for s in statements) == 1


class TestListReadsAddNoPerBundleQuery:
    def test_bulk_read_leaves_has_launched_none(self, db):
        from backend.models.game import game_item_bundles_to_read_bulk

        bundles = [_bundle(db, slug=f"game{n}") for n in range(3)]
        _launch(db, bundles[0].id)

        reads = game_item_bundles_to_read_bulk(bundles, db)

        assert [r.has_launched for r in reads] == [None, None, None]

    def test_bulk_read_never_queries_launch_history(self, db):
        from backend.models.game import game_item_bundles_to_read_bulk

        bundles = [_bundle(db, slug=f"game{n}") for n in range(5)]
        _launch(db, bundles[0].id)

        _, statements = _statements_during(db, lambda: game_item_bundles_to_read_bulk(bundles, db))

        assert not any("launch_history" in s for s in statements)

    def test_bulk_read_still_computes_era_review_and_era_confirmed(self, db):
        from backend.models.game import game_item_bundles_to_read_bulk

        confirmed = _bundle(db, slug="a", era_confirmed=True)
        unconfirmed = _bundle(db, slug="b")

        reads = game_item_bundles_to_read_bulk([confirmed, unconfirmed], db)

        assert [r.era_review for r in reads] == ["confirmed", "unreviewed"]
        assert [r.era_confirmed for r in reads] == [True, False]
