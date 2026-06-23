import re
import unicodedata
from datetime import UTC, datetime

from pydantic import BaseModel, Field, computed_field

# Scoring weights — single source of truth, mirrored in the trend prompt.
WEIGHT_ENGAGEMENT = 0.40
WEIGHT_REACH = 0.35
WEIGHT_DIVERSITY = 0.25


def slugify(text: str, max_length: int = 50) -> str:
    """Make a URL-safe slug for cross-run trend tracking."""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = nfkd.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    return slug[:max_length]


class Trend(BaseModel):
    """A ranked trend with transparent scoring from three independent criteria."""

    rank: int
    title: str
    description: str  # manager-facing summary, in the report language
    post_count: int
    example_posts: list[str] = Field(default_factory=list)
    hook_description: str | None = None

    # Scoring inputs (set by trend_analyzer, refined by synthesis)
    engagement_norm: float = 0.0
    reach_norm: float = 0.0
    diversity_norm: float = 0.0

    # Raw metrics (kept for table transparency)
    engagement_rate: float = 0.0
    views_total: int = 0
    likes_total: int = 0
    source_types: list[str] = Field(default_factory=list)
    top_formats: list[str] = Field(default_factory=list)
    cross_signal_count: int = 1
    branch_boost_count: int = 0
    is_context: bool = False  # general-context trend, not niche-relevant

    # Single-creator concentration signal (a flag for visibility, not a filter)
    dominant_author: str | None = None
    dominant_author_count: int = 0
    dominant_author_total: int = 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_signals(self) -> int:
        """Confirmed signals: base sources + cross-branch boosts."""
        return self.cross_signal_count + self.branch_boost_count

    @computed_field  # type: ignore[prop-decorator]
    @property
    def trend_score(self) -> float:
        """Composite score 0.0-1.0 — one formula, one place."""
        return round(
            WEIGHT_ENGAGEMENT * self.engagement_norm
            + WEIGHT_REACH * self.reach_norm
            + WEIGHT_DIVERSITY * self.diversity_norm,
            3,
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def trend_score_display(self) -> float:
        """Score on a 0-10 scale for display."""
        return round(self.trend_score * 10, 1)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def trend_id(self) -> str:
        """Stable slug for cross-run tracking."""
        return slugify(self.title)


class TrendReport(BaseModel):
    """trend_analyzer output.

    Fields default to empty so a bare ``{}`` returned by an LLM structured-output
    call still parses — the caller then detects the empty result and retries
    rather than crashing on a validation error.
    """

    trends: list[Trend] = Field(default_factory=list)
    analysis_period: str = ""
    total_posts_analyzed: int = 0
    top_formats: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
