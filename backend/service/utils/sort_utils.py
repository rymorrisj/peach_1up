from __future__ import annotations

from fastapi import HTTPException

_SORT_OPTIONS = {"title", "date_added"}


def apply_bundle_sort(query, model, sort: str | None):
    """Order a Software-domain bundle list query.

    Shared by game_item_bundles.py, apps.py, and media.py's list endpoints,
    all three of which query a bundle model with a `title`, `created_at`, and
    `id` column. sort=None preserves the pre-existing default (order_by(id),
    insertion order) so omitting the param is a no-op for existing callers.
    "title" sorts alphabetically; "date_added" sorts newest first. Both break
    ties on id for stable pagination across requests.
    """
    if sort is None:
        return query.order_by(model.id)
    if sort not in _SORT_OPTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sort value: {sort!r}. Must be one of {sorted(_SORT_OPTIONS)}.",
        )
    if sort == "title":
        return query.order_by(model.title, model.id)
    return query.order_by(model.created_at.desc(), model.id.desc())
