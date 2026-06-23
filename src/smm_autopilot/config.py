"""Tenant configuration — the dependency-injected ``Settings`` object.

Nodes never read globals or hardcoded brand/region/vertical data; they read a
``Settings`` built from a single ``config/tenant.yaml`` (see the bundled example tenant
in ``templates/tenant.example.yaml``). Secrets (API keys, Apify token) come from the environment,
never from the YAML.
"""

from __future__ import annotations

import calendar
import os
from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

from .llm.config import LLMConfig, default_llm_config


class BrandConfig(BaseModel):
    """Who the tenant is and how it speaks."""

    name: str
    region: str = ""
    content_language: str = "English"  # language the posts/briefs are written in
    report_language: str = "English"  # language of the manager-facing summary
    positioning: str = ""
    audience: str = ""
    tone: str = ""
    ctas: list[str] = Field(default_factory=list)
    forbidden_keywords: list[str] = Field(default_factory=list)


class AccountEntry(BaseModel):
    """A competitor or discovery-target Instagram account."""

    name: str
    instagram_url: str
    note: str = ""


class EventConfig(BaseModel):
    """A recurring or one-off regional event, in config form (month/day)."""

    name: str
    month: int = Field(ge=1, le=12)
    day: int = Field(ge=1, le=31)
    relevance_tags: list[str] = Field(default_factory=list)
    social_potential: str = "medium"
    window_days: int = 14
    note: str = ""

    def next_occurrence(self, today: date) -> date:
        """Next date this event falls on at/after ``today``.

        The day is clamped to the month's length, so a Feb-29 event resolves to
        Feb-28 in a non-leap year instead of being silently dropped.
        """

        def _on(year: int) -> date:
            last_day = calendar.monthrange(year, self.month)[1]
            return date(year, self.month, min(self.day, last_day))

        occ = _on(today.year)
        return occ if occ >= today else _on(today.year + 1)


class RegionConfig(BaseModel):
    """Regional signal sources — events + news feeds (all optional)."""

    timezone: str = "UTC"
    events: list[EventConfig] = Field(default_factory=list)
    news_feeds: list[str] = Field(default_factory=list)
    news_keywords: list[str] = Field(default_factory=list)


class NicheConfig(BaseModel):
    """Vertical relevance — keywords, topics, hashtags, discovery queries."""

    topic_whitelist: list[str] = Field(default_factory=list)
    keywords_l1: list[str] = Field(default_factory=list)  # direct match (high signal)
    keywords_l2: list[str] = Field(default_factory=list)  # adjacent
    keywords_l3: list[str] = Field(default_factory=list)  # tangential
    hashtags: dict[str, list[str]] = Field(default_factory=dict)  # group -> tags
    search_queries: list[str] = Field(default_factory=list)


class Thresholds(BaseModel):
    """Pipeline tunables (counts, ages, engagement floors)."""

    max_posts_per_run: int = 1500
    max_posts_after_filter: int = 250
    max_post_age_days: int = 90
    top_trends_count: int = 10
    briefs_count: int = 3
    min_views_discovery: int = 5000
    min_likes_discovery: int = 2000
    viral_engagement_threshold: float = 0.03
    er_cap: float = 0.5  # hard cap on engagement rate (giveaway/contest outliers)
    er_norm_ceiling: float = 0.1  # ER value that maps to a normalized score of 1.0
    likes_to_reach_multiplier: int = 10  # non-Reel reach proxy = likes * this
    # Source-aware engagement floors: source -> [min_views_reels, min_likes_non_reel].
    engagement_floors: dict[str, list[int]] = Field(
        default_factory=lambda: {
            "discovery_hashtag": [5000, 200],
            "discovery_explore": [10000, 500],
            "keyword": [5000, 200],
            "scrape_target": [10000, 500],
            "competitor": [0, 0],
        }
    )
    default_engagement_floor: list[int] = Field(default_factory=lambda: [20000, 1000])

    @model_validator(mode="after")
    def _check_floors(self) -> Thresholds:
        for floor in [*self.engagement_floors.values(), self.default_engagement_floor]:
            if len(floor) != 2:
                msg = f"engagement floor must be [min_views, min_likes], got {floor!r}"
                raise ValueError(msg)
        if self.er_cap <= 0 or self.er_norm_ceiling <= 0 or self.likes_to_reach_multiplier <= 0:
            msg = "er_cap, er_norm_ceiling, and likes_to_reach_multiplier must be > 0"
            raise ValueError(msg)
        return self

    def engagement_floor(self, source: str) -> tuple[int, int]:
        floor = self.engagement_floors.get(source) or self.default_engagement_floor
        return floor[0], floor[1]


class Settings(BaseModel):
    """The full tenant configuration injected into the pipeline."""

    brand: BrandConfig
    niche: NicheConfig = Field(default_factory=NicheConfig)
    region: RegionConfig = Field(default_factory=RegionConfig)
    competitors: list[AccountEntry] = Field(default_factory=list)
    discovery_targets: list[AccountEntry] = Field(default_factory=list)
    thresholds: Thresholds = Field(default_factory=Thresholds)
    llm: LLMConfig = Field(default_factory=default_llm_config)
    # Substrings that drop a trend outright (hard safety gate at trend stage).
    # The compliance node is the primary safety gate; this is an early backstop.
    safety_blocklist: list[str] = Field(default_factory=list)

    # Runtime secret, injected from the environment (never from YAML).
    apify_token: str = ""


def load_settings(path: str | Path) -> Settings:
    """Load and validate a tenant config YAML, layering in env secrets."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    settings = Settings.model_validate(data)
    if not settings.apify_token:
        settings.apify_token = os.environ.get("APIFY_TOKEN", "")
    return settings


def default_settings(brand_name: str = "Example Brand") -> Settings:
    """A minimal valid Settings for tests/demo wiring."""
    return Settings(brand=BrandConfig(name=brand_name))
