"""External link handling for the Fetch Metadata flow.

A provider link is stored on GameItemBundle.external_links as
{"type", "url", "source": "provider"}. The server never fetches or follows
these URLs; they are only stored and shown, so the one rule enforced here is
that nothing but a plain http(s) URL is ever kept.
"""

from __future__ import annotations

from typing import Iterable, Optional
from urllib.parse import urlsplit

PROVIDER_SOURCE = "provider"
PROVIDER_LINK_CAP = 20
_MAX_URL_LENGTH = 2048
LINK_TYPES = frozenset({"official", "store", "wiki", "social", "trailer", "other"})

# IGDB Website.category enum value to its site name. The name (or the
# Website.type name when IGDB returns one) is what _SITE_LINK_TYPES keys on.
_IGDB_CATEGORY_SITES = {
    1: "official",
    2: "wikia",
    3: "wikipedia",
    4: "facebook",
    5: "twitter",
    6: "twitch",
    8: "instagram",
    9: "youtube",
    10: "iphone",
    11: "ipad",
    12: "android",
    13: "steam",
    14: "reddit",
    15: "itch",
    16: "epicgames",
    17: "gog",
    18: "discord",
    19: "bluesky",
}
_SITE_LINK_TYPES = {
    "official": "official",
    "wikia": "wiki",
    "wikipedia": "wiki",
    "facebook": "social",
    "twitter": "social",
    "twitch": "social",
    "instagram": "social",
    "youtube": "social",
    "reddit": "social",
    "discord": "social",
    "bluesky": "social",
    "iphone": "store",
    "ipad": "store",
    "android": "store",
    "steam": "store",
    "itch": "store",
    "epicgames": "store",
    "gog": "store",
}


def igdb_link_type(category: object, type_name: object) -> str:
    """Link type for one IGDB website: its type name when present, else its
    category enum value, else "other"."""
    site = type_name.strip().lower() if isinstance(type_name, str) else None
    if not site and isinstance(category, int):
        site = _IGDB_CATEGORY_SITES.get(category)
    return _SITE_LINK_TYPES.get(site or "", "other")


def _is_web_url(url: object) -> bool:
    if not isinstance(url, str) or not url or len(url) > _MAX_URL_LENGTH:
        return False
    if any(ch.isspace() or ord(ch) < 32 for ch in url):
        return False
    try:
        parts = urlsplit(url)
        parts.port
    except ValueError:
        return False
    return (
        parts.scheme in ("http", "https") and bool(parts.hostname) and parts.username is None and parts.password is None
    )


def clean_provider_links(raw: Optional[Iterable[object]]) -> list[dict]:
    """*raw* reduced to unique, http(s)-only entries tagged as provider links,
    at most PROVIDER_LINK_CAP. Anything else is dropped."""
    seen: set[str] = set()
    out: list[dict] = []
    for entry in raw or []:
        if not isinstance(entry, dict):
            continue
        url = entry.get("url")
        if not _is_web_url(url) or url in seen:
            continue
        seen.add(url)
        link_type = entry.get("type")
        out.append(
            {
                "type": link_type if link_type in LINK_TYPES else "other",
                "url": url,
                "source": PROVIDER_SOURCE,
            }
        )
        if len(out) == PROVIDER_LINK_CAP:
            break
    return out


def trailer_links(video_urls: Iterable[str]) -> list[dict]:
    return [{"type": "trailer", "url": url} for url in video_urls]


def replace_provider_links(existing: Optional[list[dict]], fetched: list[dict]) -> Optional[list[dict]]:
    """*existing* with every provider-sourced entry replaced by *fetched*.
    Entries not marked source "provider" (added by hand, or stored before the
    marker existed) are kept, except one repeating a fetched URL."""
    fetched_urls = {link["url"] for link in fetched}
    kept = [
        link
        for link in existing or []
        if not (isinstance(link, dict) and link.get("source") == PROVIDER_SOURCE)
        and not (isinstance(link, dict) and link.get("url") in fetched_urls)
    ]
    return (kept + fetched) or None
