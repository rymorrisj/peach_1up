"""Provider external links (backend/service/metadata_providers/links.py), the
IGDB website mapping, and hiding links from restricted accounts in the game
Read model (backend/models/game.py, backend/core/dependencies.py
is_restricted_account).
"""

import httpx2
import pytest

from backend.service.metadata_providers import links


@pytest.fixture
def db():
    from sqlalchemy.pool import StaticPool
    from sqlmodel import Session, SQLModel, create_engine
    import backend.models  # noqa: F401, registers all table models

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


class TestLinkTypes:
    @pytest.mark.parametrize(
        "category,type_name,expected",
        [
            (1, None, "official"),
            (2, None, "wiki"),
            (3, None, "wiki"),
            (4, None, "social"),
            (5, None, "social"),
            (6, None, "social"),
            (8, None, "social"),
            (9, None, "social"),
            (14, None, "social"),
            (18, None, "social"),
            (19, None, "social"),
            (10, None, "store"),
            (11, None, "store"),
            (12, None, "store"),
            (13, None, "store"),
            (15, None, "store"),
            (16, None, "store"),
            (17, None, "store"),
            (99, None, "other"),
            (None, None, "other"),
            (None, "Steam", "store"),
            (None, "wikipedia", "wiki"),
            (13, "official", "official"),
            (13, "somethingnew", "other"),
        ],
    )
    def test_igdb_site_maps_to_a_link_type(self, category, type_name, expected):
        assert links.igdb_link_type(category, type_name) == expected


class TestCleanProviderLinks:
    def test_only_http_and_https_survive(self):
        out = links.clean_provider_links(
            [
                {"type": "official", "url": url}
                for url in (
                    "https://example.com/a",
                    "http://example.com/b",
                    "javascript:alert(1)",
                    "data:text/html,x",
                    "file:///c:/x",
                    "ftp://example.com/x",
                    "steam://run/1",
                    "//example.com/x",
                    "example.com/x",
                    "",
                    None,
                    5,
                    "https://",
                    "https://user:pw@example.com/",
                    "https://example.com/ a",
                    "https://example.com/\nx",
                    "https://example.com:notaport/",
                    "https://example.com/" + "a" * 2100,
                )
            ]
        )

        assert [link["url"] for link in out] == ["https://example.com/a", "http://example.com/b"]

    def test_entries_are_tagged_as_provider_and_typed(self):
        out = links.clean_provider_links(
            [
                {"type": "store", "url": "https://example.com/s", "source": "manual", "extra": "x"},
                {"type": "weird", "url": "https://example.com/w"},
            ]
        )

        assert out == [
            {"type": "store", "url": "https://example.com/s", "source": "provider"},
            {"type": "other", "url": "https://example.com/w", "source": "provider"},
        ]

    def test_duplicates_collapse_to_the_first_and_the_count_is_capped(self):
        raw = [{"type": "other", "url": f"https://example.com/{n % 40}"} for n in range(100)]

        out = links.clean_provider_links(raw)

        assert len(out) == links.PROVIDER_LINK_CAP
        assert len({link["url"] for link in out}) == links.PROVIDER_LINK_CAP

    @pytest.mark.parametrize("raw", [None, [], ["x"], [None]])
    def test_nothing_usable_gives_an_empty_list(self, raw):
        assert links.clean_provider_links(raw) == []

    def test_trailers_keep_their_type(self):
        assert links.trailer_links(["https://www.youtube.com/watch?v=a"]) == [
            {"type": "trailer", "url": "https://www.youtube.com/watch?v=a"},
        ]


class TestReplaceProviderLinks:
    def test_provider_entries_are_replaced_and_the_rest_kept_in_order(self):
        manual = {"type": "other", "url": "https://me.example/"}
        old = {"type": "official", "url": "https://old.example/", "source": "provider"}
        new = {"type": "wiki", "url": "https://new.example/", "source": "provider"}

        assert links.replace_provider_links([manual, old], [new]) == [manual, new]

    def test_an_unmarked_entry_repeating_a_fetched_url_is_not_duplicated(self):
        legacy = {"type": "trailer", "url": "https://t.example/"}
        new = {"type": "trailer", "url": "https://t.example/", "source": "provider"}

        assert links.replace_provider_links([legacy], [new]) == [new]

    def test_nothing_left_is_none(self):
        assert links.replace_provider_links(None, []) is None
        assert links.replace_provider_links([{"type": "o", "url": "https://x/", "source": "provider"}], []) is None


class TestIgdbWebsites:
    @staticmethod
    def _fake_post(monkeypatch, websites, game=None, fail_websites=None):
        import backend.service.metadata_providers.igdb_provider as igdb

        calls = []

        def _post(path, body):
            calls.append((path, body))
            if path == "websites":
                if fail_websites is not None:
                    raise fail_websites
                return websites
            return [game if game is not None else {"id": 5, "name": "Doom"}]

        monkeypatch.setattr(igdb, "_post", _post)
        return calls

    def test_websites_are_requested_for_the_game_and_mapped(self, db, monkeypatch):
        from backend.service.metadata_providers.igdb_provider import IGDBProvider

        calls = self._fake_post(
            monkeypatch,
            [
                {"url": "https://doom.example/", "category": 1},
                {"url": "https://store.steampowered.com/app/2280", "category": 13},
                {"url": "https://en.wikipedia.org/wiki/Doom", "category": 3},
                {"url": "https://twitter.com/doom", "type": {"id": 5, "type": "twitter"}},
                {"url": "https://example.com/unknown", "category": 99},
            ],
        )

        details = IGDBProvider().get_game_details(5, db)

        websites_query = next(body for path, body in calls if path == "websites")
        assert "where game = 5" in websites_query
        assert details.external_links == [
            {"type": "official", "url": "https://doom.example/", "source": "provider"},
            {"type": "store", "url": "https://store.steampowered.com/app/2280", "source": "provider"},
            {"type": "wiki", "url": "https://en.wikipedia.org/wiki/Doom", "source": "provider"},
            {"type": "social", "url": "https://twitter.com/doom", "source": "provider"},
            {"type": "other", "url": "https://example.com/unknown", "source": "provider"},
        ]

    def test_non_http_schemes_and_duplicates_are_dropped(self, db, monkeypatch):
        from backend.service.metadata_providers.igdb_provider import IGDBProvider

        self._fake_post(
            monkeypatch,
            [
                {"url": "javascript:alert(1)", "category": 1},
                {"url": "steam://run/2280", "category": 13},
                {"url": "ftp://example.com/x", "category": 1},
                {"url": "https://doom.example/", "category": 1},
                {"url": "https://doom.example/", "category": 1},
                {"category": 1},
            ],
        )

        details = IGDBProvider().get_game_details(5, db)

        assert [link["url"] for link in details.external_links] == ["https://doom.example/"]

    def test_videos_stay_trailers_in_video_urls_not_websites(self, db, monkeypatch):
        from backend.service.metadata_providers.igdb_provider import IGDBProvider

        self._fake_post(monkeypatch, [], game={"id": 5, "name": "Doom", "videos": [{"video_id": "abc"}]})

        details = IGDBProvider().get_game_details(5, db)

        assert details.video_urls == ["https://www.youtube.com/watch?v=abc"]
        assert details.external_links == []

    @pytest.mark.parametrize(
        "make_exc",
        [
            lambda: httpx2.ReadTimeout("t"),
            lambda: httpx2.ConnectError("c"),
        ],
    )
    def test_a_websites_failure_does_not_fail_the_details_fetch(self, db, monkeypatch, make_exc):
        from backend.service.metadata_providers.igdb_provider import IGDBProvider

        self._fake_post(monkeypatch, [], fail_websites=make_exc())

        details = IGDBProvider().get_game_details(5, db)

        assert details.title == "Doom"
        assert details.external_links == []


def _user(db, **fields):
    from backend.models.user import UserItem

    user = UserItem(name=fields.pop("name", "user"), **fields)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _bundle(db, **fields):
    from backend.models.game import GameItemBundle

    bundle = GameItemBundle(
        title="Doom",
        platform="dos",
        slug=fields.pop("slug", "doom"),
        content_rating="E",
        external_links=[{"type": "official", "url": "https://doom.example/", "source": "provider"}],
        **fields,
    )
    db.add(bundle)
    db.commit()
    db.refresh(bundle)
    return bundle


class TestLinksHiddenFromRestrictedAccounts:
    @pytest.mark.parametrize(
        "fields,restricted",
        [
            ({"is_owner": True, "max_content_rating": "E"}, False),
            ({}, False),
            ({"can_manage_game": True}, False),
            ({"max_content_rating": "T"}, True),
            ({"block_unrated_media": True}, True),
        ],
    )
    def test_predicate(self, db, fields, restricted):
        from backend.core.dependencies import is_restricted_account

        assert is_restricted_account(_user(db, **fields), db) is restricted

    def test_any_blocklist_row_makes_an_account_restricted(self, db):
        from backend.core.dependencies import is_restricted_account
        from backend.models.media_restriction import MediaRestriction

        user = _user(db)
        other = _bundle(db, slug="other")
        assert is_restricted_account(user, db) is False

        db.add(MediaRestriction(user_item_id=user.id, game_item_bundle_id=other.id))
        db.commit()

        assert is_restricted_account(user, db) is True

    @pytest.mark.parametrize(
        "fields,sees_links",
        [
            ({"is_owner": True}, True),
            ({}, True),
            ({"max_content_rating": "T"}, False),
            ({"block_unrated_media": True}, False),
        ],
    )
    def test_detail_read(self, db, fields, sees_links):
        from backend.models.game import game_item_bundle_to_read

        bundle = _bundle(db)

        read = game_item_bundle_to_read(bundle, db, viewer=_user(db, **fields))

        assert (read.external_links is not None) is sees_links
        if sees_links:
            assert read.external_links[0]["url"] == "https://doom.example/"

    @pytest.mark.parametrize(
        "fields,sees_links",
        [
            ({"is_owner": True}, True),
            ({}, True),
            ({"max_content_rating": "T"}, False),
        ],
    )
    def test_list_read(self, db, fields, sees_links):
        from backend.models.game import game_item_bundles_to_read_bulk

        bundle = _bundle(db)

        (read,) = game_item_bundles_to_read_bulk([bundle], db, viewer=_user(db, **fields))

        assert (read.external_links is not None) is sees_links

    def test_the_stored_links_are_untouched_by_hiding(self, db):
        from backend.models.game import game_item_bundle_to_read

        bundle = _bundle(db)

        game_item_bundle_to_read(bundle, db, viewer=_user(db, max_content_rating="T"))
        db.refresh(bundle)

        assert bundle.external_links == [{"type": "official", "url": "https://doom.example/", "source": "provider"}]
