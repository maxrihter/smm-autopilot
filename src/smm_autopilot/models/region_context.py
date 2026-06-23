from datetime import date, datetime

from pydantic import BaseModel, Field


class RegionEvent(BaseModel):
    """A cultural/seasonal event relevant for content planning."""

    name: str
    event_date: date
    relevance_tags: list[str] = Field(default_factory=list)
    social_potential: str = "medium"  # high | medium | low
    window_days: int = 14  # days before the event to start creating content
    note: str = ""
    days_until: int = 0  # computed at load time


class NewsItem(BaseModel):
    """A single relevant regional news headline."""

    title: str
    source: str
    url: str
    date: date
    significance_score: float = 0.0  # higher = more relevant; used for sorting


class RegionContext(BaseModel):
    """Regional context: trending keywords, news, upcoming events."""

    trending_keywords: list[str] = Field(default_factory=list)
    news_headlines: list[NewsItem] = Field(default_factory=list)
    upcoming_events: list[RegionEvent] = Field(default_factory=list)
    fetched_at: datetime
