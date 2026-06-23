"""Normalize raw Apify items into ``Post`` objects.

Handles the several Apify actor schemas (profile scraper, hashtag/discovery
actors) plus caption sanitization (prompt-injection + data-blob stripping),
post-type detection, an age filter, and a discovery engagement pre-filter.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import pydantic

from ..log import get_logger
from ..models.post import Post

logger = get_logger(__name__)

_REQUIRED_FIELDS = {"url", "shortCode", "ownerUsername", "timestamp"}
_CAPTION_MAX_LEN = 2000
_DISCOVERY_SOURCES = {"discovery_hashtag", "discovery_explore", "keyword"}

# Caption sanitization patterns.
_INJECTION_PATTERNS = re.compile(
    r"(ignore\s+previous\s+instructions?|system\s*:|assistant\s*:)",
    re.IGNORECASE,
)
_JSON_BLOB_PATTERN = re.compile(r"[\[{][^}\]]{10,}[}\]]")


def sanitize_caption(text: str) -> str:
    """Strip prompt-injection phrases and structured-data blobs; truncate."""
    original_len = len(text)
    sanitized = _JSON_BLOB_PATTERN.sub("", text)
    sanitized = _INJECTION_PATTERNS.sub("", sanitized)
    sanitized = sanitized[:_CAPTION_MAX_LEN]
    if len(sanitized) != original_len:
        logger.warning("caption_sanitized", original_len=original_len, sanitized_len=len(sanitized))
    return sanitized


def _remap_fields(raw: dict) -> dict:
    """Remap alternative Apify actor schemas to the canonical camelCase format."""
    out = dict(raw)

    if "shortCode" in out and "ownerUsername" in out and "videoPlayCount" in out and "type" in out:
        for metric in ("likesCount", "commentsCount", "videoPlayCount"):
            if metric in out and out[metric] is None:
                out[metric] = 0
        return out

    if "shortCode" not in out and "code" in out:
        out["shortCode"] = out["code"]

    if "url" not in out and out.get("shortCode"):
        product = out.get("product_type", "")
        prefix = "reel" if product == "clips" else "p"
        out["url"] = f"https://www.instagram.com/{prefix}/{out['shortCode']}/"

    if "timestamp" not in out:
        if "taken_at_date" in out:
            out["timestamp"] = out["taken_at_date"]
        elif "taken_at_ts" in out:
            out["timestamp"] = datetime.fromtimestamp(out["taken_at_ts"], tz=UTC).isoformat()

    if "ownerUsername" not in out:
        user = out.get("user")
        if isinstance(user, dict) and "username" in user:
            out["ownerUsername"] = user["username"]

    caption = out.get("caption")
    if isinstance(caption, dict):
        out["caption"] = caption.get("text", "")

    if "likesCount" not in out and "like_count" in out:
        out["likesCount"] = out["like_count"] or 0
    if "commentsCount" not in out and "comment_count" in out:
        out["commentsCount"] = out["comment_count"] or 0

    if "videoPlayCount" not in out:
        if "videoViewCount" in out:
            out["videoPlayCount"] = out["videoViewCount"] or 0
        elif "play_count" in out:
            out["videoPlayCount"] = out["play_count"] or 0

    for metric in ("likesCount", "commentsCount", "videoPlayCount"):
        if metric in out and out[metric] is None:
            out[metric] = 0

    if "product_type" not in out and "productType" in out:
        out["product_type"] = out["productType"]

    if "type" not in out:
        product = out.get("product_type", "")
        if product == "clips" or out.get("media_format") == "video":
            out["type"] = "Reel"
        elif out.get("media_type") == 8:
            out["type"] = "Carousel"

    return out


def _detect_post_type(raw: dict) -> str:
    """Detect Reel | Carousel | Image from one of several actor schemas."""
    raw_type = str(raw.get("type", "")).lower()
    if raw_type in ("video", "reel"):
        return "Reel"
    if raw_type == "sidecar":
        return "Carousel"
    if raw_type == "image":
        return "Image"
    if raw.get("product_type") == "clips" or raw.get("productType") == "clips":
        return "Reel"
    if (raw.get("videoPlayCount") or 0) > 0 or (raw.get("videoViewCount") or 0) > 0:
        return "Reel"
    if raw.get("childPosts") or raw.get("sidecarChildren"):
        return "Carousel"
    return "Image"


def _clamp(value: object, url: object) -> int:
    """Coerce a metric to a non-negative int (Apify returns -1 when IG hides counts)."""
    if not isinstance(value, (int, float, str)):
        return 0
    try:
        v = int(value)
    except (TypeError, ValueError):
        return 0
    if v < 0:
        logger.warning("negative_metric_clamped", original=v, url=url)
        return 0
    return v


def normalize_post(
    raw: dict,
    source: str,
    source_segment: str = "",
    *,
    max_post_age_days: int = 90,
) -> Post | None:
    """Normalize one raw Apify dict into a ``Post`` (None on missing/invalid)."""
    raw = _remap_fields(raw)
    if not _REQUIRED_FIELDS.issubset(raw.keys()):
        missing = _REQUIRED_FIELDS - raw.keys()
        logger.warning("normalize_missing_fields", missing=list(missing), url=raw.get("url"))
        return None

    try:
        timestamp = datetime.fromisoformat(str(raw["timestamp"]).replace("Z", "+00:00"))
        ts_aware = timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=UTC)
        cutoff = datetime.now(tz=UTC) - timedelta(days=max_post_age_days)
        if ts_aware < cutoff:
            return None

        raw_caption = raw.get("caption")
        post = Post(
            id=raw.get("id") or raw.get("shortCode", ""),
            url=raw["url"],
            shortCode=raw["shortCode"],
            caption=sanitize_caption(raw_caption) if raw_caption else None,
            videoPlayCount=_clamp(raw.get("videoPlayCount", 0), raw.get("url")),
            likesCount=_clamp(raw.get("likesCount", 0), raw.get("url")),
            commentsCount=_clamp(raw.get("commentsCount", 0), raw.get("url")),
            timestamp=timestamp,
            ownerUsername=raw["ownerUsername"],
            source=source,
            post_type=_detect_post_type(raw),
            source_segment=source_segment,
        )
    except (pydantic.ValidationError, KeyError, ValueError) as exc:
        logger.warning("normalize_failed", url=raw.get("url"), error=str(exc))
        return None

    return post


def normalize_batch(
    raw_items: list[dict],
    source: str,
    source_segment: str = "",
    *,
    max_post_age_days: int = 90,
    min_views_discovery: int = 5000,
    min_likes_discovery: int = 2000,
) -> list[Post]:
    """Normalize a batch of raw items.

    Discovery sources are pre-filtered by a views/likes floor before normalization
    (format-aware: Reels by views, others by likes). Profile-scraped sources
    (competitor, scrape_target) bypass that floor.
    """
    items = raw_items
    low_views_skipped = 0
    if source in _DISCOVERY_SOURCES:
        items = []
        for item in raw_items:
            views = (
                item.get("videoPlayCount")
                or item.get("videoViewCount")
                or item.get("play_count")
                or 0
            )
            likes = item.get("likesCount") or item.get("like_count") or 0
            if views >= min_views_discovery or likes >= min_likes_discovery:
                items.append(item)
            else:
                low_views_skipped += 1

    posts = [
        normalize_post(item, source, source_segment, max_post_age_days=max_post_age_days)
        for item in items
    ]
    valid = [p for p in posts if p is not None]
    logger.info(
        "normalize_batch",
        source=source,
        total=len(raw_items),
        normalized=len(valid),
        skipped=len(items) - len(valid),
        low_views_skipped=low_views_skipped,
    )
    return valid
