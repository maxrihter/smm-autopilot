from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

IdeaType = Literal[
    "reel", "carousel", "static_post", "story_series", "promo", "collaboration", "campaign"
]
Priority = Literal["must_do", "should_do", "nice_to_have", "experimental"]


class MarketingIdea(BaseModel):
    """A single marketing idea tied to a research signal.

    Lenient fields (see ``Brief``) — the ideation node clamps viral_score, trims
    hashtags, and drops empty-concept ideas after parsing.
    """

    idea_type: IdeaType = "reel"
    topic_category: str = ""  # one of the tenant's configured topics
    title: str = ""
    concept: str = ""  # full concept: scenario, structure, mechanics
    hook: str = ""
    target_audience: str = ""
    based_on: str = ""  # research signal: trend title, competitor gap, event name
    why_now: str = ""
    suggested_hashtags: list[str] = Field(default_factory=list)
    cta: str = ""
    viral_score: float = 0.0
    effort: Literal["low", "medium", "high"] = "medium"
    priority: Priority = "should_do"
    event_reference: str | None = None


class MarketingIdeaSet(BaseModel):
    """marketing_ideation output — a variable number of ideas."""

    ideas: list[MarketingIdea] = Field(default_factory=list)
    reasoning: str = ""  # brief explanation of the ideation strategy
    generated_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class IdeaPatch(BaseModel):
    """Compliance-revision patch: the LLM returns ONLY the fields that need
    changing (all optional); the patch is merged over the original by the pipeline."""

    title: str | None = None
    concept: str | None = None
    hook: str | None = None
    target_audience: str | None = None
    based_on: str | None = None
    why_now: str | None = None
    suggested_hashtags: list[str] | None = None
    cta: str | None = None
    viral_score: float | None = None
    effort: Literal["low", "medium", "high"] | None = None
    priority: Priority | None = None
    event_reference: str | None = None
    idea_type: IdeaType | None = None
    topic_category: str | None = None
