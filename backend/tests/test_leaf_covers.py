"""effective_display_leaf: the disc whose cover the card shows."""

from types import SimpleNamespace

from backend.service.games.leaf_covers import effective_display_leaf


def _bundle(item_ids, display=None, launch=None):
    return SimpleNamespace(
        display_disk_id=display,
        launch_disk_id=launch,
        items=[SimpleNamespace(id=i) for i in item_ids],
    )


def test_display_disc_wins_over_launch_disc():
    assert effective_display_leaf(_bundle([1, 2, 3], display=3, launch=2)).id == 3


def test_falls_back_to_launch_disc_when_display_unset():
    assert effective_display_leaf(_bundle([1, 2, 3], launch=2)).id == 2


def test_falls_back_to_first_disc_when_neither_is_set():
    assert effective_display_leaf(_bundle([4, 5])).id == 4


def test_falls_back_to_first_disc_when_the_id_matches_no_disc():
    assert effective_display_leaf(_bundle([4, 5], display=99)).id == 4


def test_none_when_there_are_no_discs():
    assert effective_display_leaf(_bundle([], display=1)) is None
