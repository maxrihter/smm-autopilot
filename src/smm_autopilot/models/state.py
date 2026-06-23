from typing import NotRequired, TypedDict

from .action_plan import ActionPlan
from .brief import Brief
from .competitor import CompetitorReport
from .compliance import ComplianceResult
from .influencer import InfluencerDigest
from .marketing_idea import MarketingIdeaSet
from .post import Post
from .region_context import RegionContext
from .report import Report
from .trend import Trend, TrendReport


class PipelineState(TypedDict):
    """LangGraph pipeline state (TypedDict — required by LangGraph).

    Required keys are provided at invoke time; NotRequired keys are filled by
    nodes as the graph runs.
    """

    # --- Required at invoke ---
    dataset_ids: list[str]
    run_id: str
    source_map: NotRequired[dict[str, str]]  # dataset_id -> source label

    # --- Computed by nodes ---
    raw_posts: NotRequired[list[Post]]
    filtered_posts: NotRequired[list[Post]]
    trends: NotRequired[list[Trend]]
    briefs: NotRequired[list[Brief]]
    approved_briefs: NotRequired[list[Brief]]
    compliance_results: NotRequired[list[ComplianceResult]]
    rejected_briefs: NotRequired[list[str]]  # titles only
    rejected_ideas: NotRequired[list[str]]
    report: NotRequired[Report]
    pipeline_status: NotRequired[str]  # "empty_filter" | "all_rejected" | ...
    error: NotRequired[str]
    cleanup_done: NotRequired[bool]

    # --- Segmented posts ---
    scrape_target_posts: NotRequired[list[Post]]  # creator/KOL scrape targets
    competitor_posts: NotRequired[list[Post]]
    discovery_posts: NotRequired[list[Post]]
    brand_ugc_posts: NotRequired[list[Post]]  # branded-hashtag UGC (monitoring only)

    # --- Analysis outputs ---
    influencer_digest: NotRequired[InfluencerDigest]
    competitor_report: NotRequired[CompetitorReport]
    region_context: NotRequired[RegionContext]
    action_plan: NotRequired[ActionPlan]
    trend_report: NotRequired[TrendReport]
    marketing_ideas: NotRequired[MarketingIdeaSet | None]
