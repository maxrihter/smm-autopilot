"""Trigger Apify Instagram scrapers from tenant config — the CLI's replacement
for an external workflow-orchestration layer.

Fires one actor run per source group (competitors, discovery targets, niche
hashtags) in parallel, then returns ``(dataset_ids, source_map)`` for the pipeline.
Actor ids + result limits are sensible Instagram defaults; see docs/SETUP.md for
the warmed-account + cookies setup a live run needs.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from ..integrations.apify_client import run_actor
from ..log import get_logger

if TYPE_CHECKING:
    from ..config import AccountEntry, Settings

logger = get_logger(__name__)

_PROFILE_ACTOR = "apify/instagram-profile-scraper"
_HASHTAG_ACTOR = "apify/instagram-hashtag-scraper"
_RESULTS_LIMIT_PROFILE = 20
_RESULTS_LIMIT_HASHTAG = 50


def _username(entry: AccountEntry) -> str:
    """Extract the handle from a profile URL, dropping any query/fragment/path tail.

    Robust to natural copy-paste like ``https://www.instagram.com/foo/?igsh=...``.
    """
    path = urlparse(entry.instagram_url.strip()).path
    return path.strip("/").split("/")[0].lstrip("@")


async def _profile_dataset(
    token: str, entries: list[AccountEntry], *, source: str
) -> tuple[str, str] | None:
    usernames = [u for u in (_username(e) for e in entries) if u]
    if not usernames:
        return None
    # resultsLimit may be ignored by some profile-actor builds; the real volume/cost
    # backstop is thresholds.max_posts_per_run (enforced in ingestion).
    dataset_id = await run_actor(
        token, _PROFILE_ACTOR, {"usernames": usernames, "resultsLimit": _RESULTS_LIMIT_PROFILE}
    )
    return dataset_id, source


async def _hashtag_dataset(token: str, hashtags: dict[str, list[str]]) -> tuple[str, str] | None:
    tags = [h.lstrip("#") for group in hashtags.values() for h in group]
    if not tags:
        return None
    dataset_id = await run_actor(
        token,
        _HASHTAG_ACTOR,
        {"hashtags": tags, "resultsLimit": _RESULTS_LIMIT_HASHTAG, "resultsType": "posts"},
    )
    return dataset_id, "discovery_hashtag"


async def collect_datasets(settings: Settings) -> tuple[list[str], dict[str, str]]:
    """Scrape all configured sources and return (dataset_ids, source_map)."""
    token = settings.apify_token
    if not token:
        msg = (
            "APIFY_TOKEN is required for a live run (set it in .env); use `demo` for a no-keys run."
        )
        raise RuntimeError(msg)

    results = await asyncio.gather(
        _profile_dataset(token, settings.competitors, source="competitor"),
        _profile_dataset(token, settings.discovery_targets, source="scrape_target"),
        _hashtag_dataset(token, settings.niche.hashtags),
    )
    dataset_ids: list[str] = []
    source_map: dict[str, str] = {}
    for item in results:
        if item is None:
            continue
        dataset_id, source = item
        dataset_ids.append(dataset_id)
        source_map[dataset_id] = source
    logger.info("scrape_collected", datasets=len(dataset_ids))
    return dataset_ids, source_map
