from datetime import UTC, datetime

from pydantic import BaseModel, Field


class CompetitorPost(BaseModel):
    """Key metrics for a single competitor post."""

    url: str
    post_type: str  # Reel | Carousel | Image
    views: int = 0
    likes: int = 0
    comments: int = 0
    engagement_rate: float = 0.0
    caption_preview: str = ""  # first ~120 chars of caption


class CompetitorAnalysis(BaseModel):
    """Analysis of a single competitor account."""

    name: str
    username: str
    posting_frequency: str = ""  # e.g. "3-4 posts/week"
    top_topics: list[str] = Field(default_factory=list)
    content_formats: list[str] = Field(default_factory=list)
    avg_engagement_rate: float = 0.0
    summary: str = ""  # manager-facing summary, in the report language
    new_campaigns: list[str] = Field(default_factory=list)
    strategy_shift: str | None = None
    top_posts: list[CompetitorPost] = Field(default_factory=list)  # best by ER (max ~5)


class CompetitorReport(BaseModel):
    """competitor_analyzer output. Defaults empty so a bare ``{}`` from an LLM
    structured-output call parses cleanly (caller detects empty + retries)."""

    competitors: list[CompetitorAnalysis] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
