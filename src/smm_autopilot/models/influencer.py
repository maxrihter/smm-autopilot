from datetime import UTC, datetime

from pydantic import BaseModel, Field


class ViralPost(BaseModel):
    """A single high-engagement post surfaced from influencer analysis."""

    url: str
    caption_snippet: str  # first ~100 chars
    views: int
    engagement_rate: float
    category: str  # discovery category/niche label
    account_username: str
    likes: int = 0
    comments: int = 0


class NicheReport(BaseModel):
    """Aggregated stats for one influencer niche/category."""

    niche_name: str
    category: str
    post_count: int
    avg_engagement_rate: float
    trending_topics: list[str] = Field(default_factory=list)


class InfluencerDigest(BaseModel):
    """influencer_analyzer output — viral posts and niche insights.

    List/dict fields default empty so a bare ``{}`` from an LLM structured-output
    call parses — the caller detects the empty digest and retries.
    """

    top_viral_posts: list[ViralPost] = Field(default_factory=list)
    top_niches: list[NicheReport] = Field(default_factory=list)
    unexpected_trends: list[str] = Field(default_factory=list)
    category_breakdown: dict[str, int] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
