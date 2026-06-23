"""Fetch relevant regional news from configured RSS feeds.

Generic: the feed URLs and relevance keywords come from the tenant's region
config. Tolerant — a failing feed is skipped, not fatal. Requires ``feedparser``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import httpx

from ..log import get_logger
from ..models.region_context import NewsItem

logger = get_logger(__name__)


def _matches(text: str, keywords: list[str]) -> bool:
    if not keywords:
        return True
    low = text.lower()
    return any(k.lower() in low for k in keywords)


def _entry_date(entry: object) -> date:
    parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if parsed:
        try:
            return date(parsed.tm_year, parsed.tm_mon, parsed.tm_mday)
        except (ValueError, AttributeError):
            pass
    return datetime.now(tz=UTC).date()


async def fetch_news(
    feeds: list[str],
    keywords: list[str],
    *,
    limit: int = 10,
    timeout: float = 10.0,  # noqa: ASYNC109 — httpx transport timeout, not an asyncio deadline
) -> list[NewsItem]:
    """Fetch and keyword-filter news from the given RSS feeds."""
    if not feeds:
        return []
    try:
        import feedparser  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("news_skipped", reason="feedparser not installed")
        return []

    items: list[NewsItem] = []
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for url in feeds:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                parsed = feedparser.parse(resp.text)
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("news_feed_failed", feed=url, error=str(exc)[:120])
                continue
            source_name = getattr(parsed.feed, "title", url)
            for entry in parsed.entries:
                title = getattr(entry, "title", "")
                summary = getattr(entry, "summary", "")
                if not title or not _matches(f"{title} {summary}", keywords):
                    continue
                items.append(
                    NewsItem(
                        title=title,
                        source=source_name,
                        url=getattr(entry, "link", url),
                        date=_entry_date(entry),
                    )
                )

    items.sort(key=lambda n: n.date, reverse=True)
    logger.info("news_fetched", feeds=len(feeds), items=len(items))
    return items[:limit]
