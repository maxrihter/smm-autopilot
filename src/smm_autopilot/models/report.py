from datetime import UTC, datetime

from pydantic import BaseModel, Field

from .action_plan import ActionPlan
from .brief import Brief
from .competitor import CompetitorReport
from .compliance import ComplianceResult
from .influencer import InfluencerDigest
from .marketing_idea import MarketingIdeaSet
from .post import Post
from .region_context import RegionContext
from .trend import Trend, TrendReport


class Report(BaseModel):
    """Internal pipeline output: trends + briefs + the full intelligence set.

    This is the engine's native object. The language-neutral, output-facing
    deliverable (Markdown / JSON) is rendered from this in the report node.
    """

    run_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    trends: list[Trend] = Field(default_factory=list)
    briefs: list[Brief] = Field(default_factory=list)
    total_posts_scraped: int = 0
    total_posts_filtered: int = 0

    trend_report: TrendReport | None = None
    influencer_digest: InfluencerDigest | None = None
    competitor_report: CompetitorReport | None = None
    region_context: RegionContext | None = None
    action_plan: ActionPlan | None = None
    marketing_ideas: MarketingIdeaSet | None = None
    compliance_results: list[ComplianceResult] = Field(default_factory=list)
    brand_ugc_posts: list[Post] = Field(default_factory=list)
    rejected_briefs: list[str] = Field(default_factory=list)
    rejected_ideas: list[str] = Field(default_factory=list)
