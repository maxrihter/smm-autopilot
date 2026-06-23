"""Ingestion node: Apify datasets -> flatten -> delta filter -> normalize -> route.

Delta tracking (per-account scrape state) applies only to profile sources
(``scrape_target``). Discovery sources are always ingested fresh. Durable dedup +
delta state live in the SQLite ``Store`` (injected), so there is no DB connection
to manage here.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from ...integrations.apify_client import fetch_dataset
from ...log import get_logger
from ...models.post import Post
from ...storage import Store, filter_new_posts_by_delta
from ..normalize import normalize_batch

if TYPE_CHECKING:
    from ...config import Settings, Thresholds
    from ...models.state import PipelineState

logger = get_logger(__name__)

# Sources that require per-account delta tracking (profile scrapers). Competitors
# are intentionally excluded — the analyzer wants each competitor's top recent
# posts every run, even if already seen.
_DELTA_TRACKED_SOURCES: frozenset[str] = frozenset({"scrape_target"})

# Source label -> PipelineState field.
_SEGMENT_FIELD: dict[str, str] = {
    "scrape_target": "scrape_target_posts",
    "competitor": "competitor_posts",
    "discovery_explore": "discovery_posts",
    "discovery_hashtag": "discovery_posts",
    "brand_ugc": "brand_ugc_posts",
    "discovery": "discovery_posts",
    "keyword": "discovery_posts",
}


def _flatten_profile_items(raw_items: list[dict]) -> list[dict]:
    """Profile-scraper items nest posts under ``latestPosts`` — flatten them."""
    flat: list[dict] = []
    for item in raw_items:
        posts = item.get("latestPosts")
        if isinstance(posts, list) and posts:
            username = item.get("username") or ""
            for post in posts:
                if "ownerUsername" not in post and username:
                    post["ownerUsername"] = username
                flat.append(post)
        else:
            flat.append(item)
    return flat


def _normalize(raw_items: list[dict], source: str, th: Thresholds) -> list[Post]:
    return normalize_batch(
        raw_items,
        source=source,
        source_segment=source,
        max_post_age_days=th.max_post_age_days,
        min_views_discovery=th.min_views_discovery,
        min_likes_discovery=th.min_likes_discovery,
    )


def _ingest_profile_source(
    raw_items: list[dict],
    source: str,
    store: Store,
    profile_posts_by_account: dict[str, list[Post]],
    th: Thresholds,
) -> list[Post]:
    """Delta-filter a profile source per account, then normalize."""
    by_username: dict[str, list[dict]] = defaultdict(list)
    for item in raw_items:
        by_username[item.get("ownerUsername") or "__unknown__"].append(item)

    known = [u for u in by_username if u != "__unknown__"]
    account_urls = [f"https://www.instagram.com/{u}/" for u in known]
    last_scraped = store.get_last_scraped(account_urls)

    filtered_raw: list[dict] = list(by_username.get("__unknown__", []))
    for username in known:
        account_url = f"https://www.instagram.com/{username}/"
        filtered_raw.extend(
            filter_new_posts_by_delta(by_username[username], account_url, last_scraped)
        )

    posts = _normalize(filtered_raw, source, th)
    for post in posts:
        profile_posts_by_account[f"https://www.instagram.com/{post.ownerUsername}/"].append(post)
    return posts


def _update_profile_scrape_states(
    profile_posts_by_account: dict[str, list[Post]], store: Store
) -> None:
    updates: list[tuple[str, str, int]] = []
    for account_url, posts in profile_posts_by_account.items():
        if not posts:
            continue
        latest = max(posts, key=lambda p: p.timestamp)
        updates.append((account_url, latest.shortCode, len(posts)))
    if updates:
        store.update_scrape_state(updates)


def _deduplicate_by_url(posts: list[Post], store: Store) -> list[Post]:
    if not posts:
        return posts
    new_urls = set(store.filter_new_urls([p.url for p in posts]))
    new_posts = [p for p in posts if p.url in new_urls]
    if new_urls:
        store.mark_urls_seen(list(new_urls))
    logger.info("url_dedup", seen=len(posts) - len(new_posts), new=len(new_posts))
    return new_posts


async def ingestion_node(
    state: PipelineState, *, settings: Settings, store: Store
) -> dict[str, object]:
    """Fetch Apify datasets, delta-filter, normalize, and route posts by source."""
    dataset_ids = state["dataset_ids"]
    source_map = state.get("source_map") or {}
    th = settings.thresholds

    all_posts: list[Post] = []
    profile_posts_by_account: dict[str, list[Post]] = defaultdict(list)

    for dataset_id in dataset_ids:
        raw_items = _flatten_profile_items(await fetch_dataset(settings.apify_token, dataset_id))
        source = source_map.get(dataset_id)
        if source is None:
            logger.warning("dataset_no_source_map", dataset_id=dataset_id)
            source = "discovery_explore"
        if source in _DELTA_TRACKED_SOURCES:
            posts = _ingest_profile_source(raw_items, source, store, profile_posts_by_account, th)
        else:
            posts = _normalize(raw_items, source, th)
        all_posts.extend(posts)

    if profile_posts_by_account:
        _update_profile_scrape_states(profile_posts_by_account, store)

    # Competitor posts bypass URL dedup — the analyzer wants their top posts every run.
    competitor_posts = [p for p in all_posts if p.source == "competitor"]
    other_posts = [p for p in all_posts if p.source != "competitor"]
    new_posts = _deduplicate_by_url(other_posts, store) + competitor_posts

    if len(new_posts) > th.max_posts_per_run:
        logger.warning("ingestion_cap", total=len(new_posts), cap=th.max_posts_per_run)
        new_posts = sorted(new_posts, key=lambda p: p.timestamp, reverse=True)[
            : th.max_posts_per_run
        ]

    segments: dict[str, list[Post]] = {
        "scrape_target_posts": [],
        "competitor_posts": [],
        "discovery_posts": [],
        "brand_ugc_posts": [],
    }
    for post in new_posts:
        field = _SEGMENT_FIELD.get(post.source_segment, "discovery_posts")
        segments.get(field, segments["discovery_posts"]).append(post)

    raw_posts_excluding_ugc = [p for p in new_posts if p.source_segment != "brand_ugc"]
    logger.info(
        "ingestion_complete",
        datasets=len(dataset_ids),
        after_dedup=len(new_posts),
        scrape_target=len(segments["scrape_target_posts"]),
        competitor=len(segments["competitor_posts"]),
        discovery=len(segments["discovery_posts"]),
    )
    return {"raw_posts": raw_posts_excluding_ugc, **segments}
