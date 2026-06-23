"""Web-context node: build regional context (upcoming events + relevant news).

Events come from the tenant's config; news from configured RSS feeds. Both are
optional and failure-tolerant — partial context beats none. A live holiday-calendar
source can be plugged in here per region (see docs/EXTENDING.md); none ships by default.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from ...integrations.news_rss import fetch_news
from ...log import get_logger
from ...models.region_context import RegionContext, RegionEvent

if TYPE_CHECKING:
    from ...config import Settings
    from ...models.state import PipelineState

logger = get_logger(__name__)

_LOOKAHEAD_DAYS = 60


def _upcoming_events(settings: Settings) -> list[RegionEvent]:
    """Resolve config events to their next occurrence within the lookahead window."""
    today = datetime.now(tz=UTC).date()
    events: list[RegionEvent] = []
    for ev in settings.region.events:
        occ = ev.next_occurrence(today)
        days = (occ - today).days
        if days <= _LOOKAHEAD_DAYS:
            events.append(
                RegionEvent(
                    name=ev.name,
                    event_date=occ,
                    relevance_tags=ev.relevance_tags,
                    social_potential=ev.social_potential,
                    window_days=ev.window_days,
                    note=ev.note,
                    days_until=days,
                )
            )
    events.sort(key=lambda e: e.days_until)
    return events


async def web_context_node(state: PipelineState, *, settings: Settings) -> dict[str, object]:
    """Fetch regional news and resolve upcoming events into a RegionContext."""
    news = await fetch_news(settings.region.news_feeds, settings.region.news_keywords)
    events = _upcoming_events(settings)
    context = RegionContext(
        news_headlines=news,
        upcoming_events=events,
        fetched_at=datetime.now(tz=UTC),
    )
    logger.info("web_context_ok", news=len(news), upcoming_events=len(events))
    return {"region_context": context}
