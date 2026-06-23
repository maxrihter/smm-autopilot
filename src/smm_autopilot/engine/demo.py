"""Demo mode: run the FULL pipeline on bundled synthetic fixtures, NO API keys.

A ``DemoRouter`` returns deterministic, mutually-consistent canned LLM outputs and
a patched Apify fetch returns synthetic posts — so ``smm-autopilot demo`` exercises
the whole graph end-to-end and writes a real sample report to ``output/``.

Everything here is fictional (the Barkwell brand + dog-content fixtures); it exists
only to show the shape of a real run without spending a cent on APIs.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import patch

import yaml

from ..config import EventConfig, Settings
from ..llm import LLMRouter, default_llm_config
from ..log import get_logger
from ..models.action_plan import Recommendation
from ..models.brief import Brief
from ..models.competitor import CompetitorAnalysis
from ..models.compliance import ComplianceResult
from ..models.influencer import NicheReport, ViralPost
from ..models.marketing_idea import MarketingIdea
from ..models.trend import Trend
from ..storage import Store
from ..templates import example_tenant_yaml
from .pipeline import run_pipeline

if TYPE_CHECKING:
    from ..models.report import Report

logger = get_logger(__name__)


def _url(slug: str) -> str:
    return f"https://www.instagram.com/reel/{slug}/"


def _raw(slug: str, owner: str, caption: str, *, views: int, likes: int) -> dict:
    # No timestamp here — _demo_fetch stamps a fresh one at call time so fixtures
    # never go stale relative to the 90-day age filter.
    return {
        "id": slug,
        "url": _url(slug),
        "shortCode": slug,
        "ownerUsername": owner,
        "type": "Video",
        "videoPlayCount": views,
        "likesCount": likes,
        "commentsCount": max(20, likes // 30),
        "caption": caption,
    }


# --- Synthetic Apify datasets (one list per source) -------------------------
_DATASETS: dict[str, list[dict]] = {
    "demo_discovery": [
        _raw(
            "d1",
            "freshpawsco",
            "POV: first bite of fresh food 🥹 #freshdogfood",
            views=120000,
            likes=9000,
        ),
        _raw(
            "d2",
            "thepupkitchen",
            "Switching to fresh — week one #dognutrition",
            views=84000,
            likes=6100,
        ),
        _raw(
            "d3",
            "rescuedreams",
            "Gotcha day glow-up: 3 months on real food 🐶",
            views=96000,
            likes=11200,
        ),
        _raw(
            "d4",
            "adoptdontshop_",
            "From shelter to spoiled — her gotcha day",
            views=52000,
            likes=7400,
        ),
        _raw(
            "d5",
            "vetdrlemon",
            "Busting a dog-food myth in 30 seconds 🧠 #doghealth",
            views=41000,
            likes=2600,
        ),
        _raw(
            "d6",
            "barkscience",
            "Is grain-free actually better? The 30s answer",
            views=37000,
            likes=3300,
        ),
    ],
    "demo_competitor": [
        _raw(
            "c1", "thefarmersdog", "Real food, real reviews — meet Daisy", views=90000, likes=7200
        ),
        _raw("c2", "thefarmersdog", "Founder story: why we started", views=60000, likes=5100),
        _raw("c3", "ollie", "Fresh recipes, vet-developed 🥩", views=70000, likes=6000),
        _raw("c4", "ollie", "Unboxing the Ollie starter box", views=40000, likes=3000),
    ],
    "demo_targets": [
        _raw("t1", "thedogist", "Every dog has a story ❤️", views=300000, likes=24000),
        _raw("t2", "itsdougthepug", "Treat-catch slow-mo, take 7", views=250000, likes=21000),
        _raw(
            "t3", "tunameltsmyheart", "The face when the bowl is empty", views=180000, likes=15000
        ),
    ],
}
_SOURCE_MAP = {
    "demo_discovery": "discovery_hashtag",
    "demo_competitor": "competitor",
    "demo_targets": "scrape_target",
}

_TREND_TITLES = [
    "Fresh-bowl first-bite reactions",
    "Rescue gotcha-day glow-ups",
    "Vet myth-busting in 30 seconds",
]
_TREND_POSTS = [("d1", "d2"), ("d3", "d4"), ("d5", "d6")]


async def _demo_fetch(_token: str, dataset_id: str) -> list[dict]:
    now = datetime.now(tz=UTC).isoformat()  # fresh at call time, never stale
    return [{**item, "timestamp": now} for item in _DATASETS.get(dataset_id, [])]


# --- Canned, mutually-consistent LLM outputs --------------------------------
def _trends(*, enriched: bool = False) -> list[Trend]:
    out: list[Trend] = []
    for rank, (title, (a, b)) in enumerate(zip(_TREND_TITLES, _TREND_POSTS, strict=True), start=1):
        desc = f"Creators are riding the “{title}” format and it's overperforming."
        if enriched:
            desc += " Echoed by 2 creators; competitors are quiet here."
        out.append(
            Trend(
                rank=rank,
                title=title,
                description=desc,
                post_count=2,
                example_posts=[_url(a), _url(b)],
                source_types=["discovery_hashtag"],
                top_formats=["Reel"],
                hook_description="Strong 3s POV opener",
            )
        )
    return out


def _influencer_kwargs() -> dict:
    return {
        "top_viral_posts": [
            ViralPost(
                url=_url("t1"),
                caption_snippet="Every dog has a story",
                views=300000,
                engagement_rate=0.08,
                category="humor",
                account_username="thedogist",
                likes=24000,
                comments=900,
            ),
            ViralPost(
                url=_url("t2"),
                caption_snippet="Treat-catch slow-mo",
                views=250000,
                engagement_rate=0.085,
                category="humor",
                account_username="itsdougthepug",
                likes=21000,
                comments=700,
            ),
        ],
        "top_niches": [
            NicheReport(
                niche_name="dog humor",
                category="humor",
                post_count=3,
                avg_engagement_rate=0.08,
                trending_topics=["reaction clips", "gotcha day"],
            )
        ],
        "unexpected_trends": ["slow-mo treat catches"],
        "category_breakdown": {"humor": 2, "education": 1},
    }


def _competitor_kwargs() -> dict:
    return {
        "competitors": [
            CompetitorAnalysis(
                name="The Farmer's Dog",
                username="thefarmersdog",
                posting_frequency="4-5 posts/week",
                top_topics=["fresh food", "founder testimonials"],
                content_formats=["Reel"],
                avg_engagement_rate=0.06,
                summary="The Farmer's Dog leans on founder testimonials and fresh-bowl close-ups.",
            ),
            CompetitorAnalysis(
                name="Ollie",
                username="ollie",
                posting_frequency="3-4 posts/week",
                top_topics=["vet-developed recipes", "unboxings"],
                content_formats=["Reel"],
                avg_engagement_rate=0.05,
                summary="Ollie emphasizes vet-developed recipes and starter-box unboxings.",
            ),
        ]
    }


def _action_kwargs() -> dict:
    return {
        "recommendations": [
            Recommendation(
                title="Launch a Gotcha-Day UGC challenge",
                category="campaign",
                urgency="high",
                scenario=(
                    "Invite customers to post their rescue's before/after on fresh food with a "
                    "branded hashtag; reshare the best to Stories daily and gift a sampler to the "
                    "top three."
                ),
                rationale="Rescue content peaks in October — ride Adopt-a-Shelter-Dog Month.",
                inspired_by=[_TREND_TITLES[0]],
            ),
            Recommendation(
                title="Own the first-bite reaction format",
                category="content",
                urgency="high",
                scenario=(
                    "Produce a weekly Reel filming a real dog's first bite of Barkwell, shot POV "
                    "with a 3-second hook and a soft sampler CTA."
                ),
                rationale="The reaction format is the strongest discovery signal this week.",
                inspired_by=[_TREND_TITLES[0]],
            ),
            Recommendation(
                title="Partner with a humor dog creator",
                category="collaboration",
                urgency="medium",
                scenario=(
                    "Brief a humor creator (e.g. a Doug-the-Pug-style account) on a treat-catch "
                    "slow-mo featuring Barkwell treats; co-post and boost the winning cut."
                ),
                rationale="Humor creators drive the highest engagement in the niche right now.",
                inspired_by=[_TREND_TITLES[0]],
            ),
        ]
    }


def _ideas_kwargs() -> dict:
    return {
        "ideas": [
            MarketingIdea(
                idea_type="reel",
                topic_category="product",
                title="First-bite reaction series",
                concept=(
                    "A weekly Reel filming a real dog's first bite of Barkwell — same 3-second POV "
                    "hook, a different dog each week, two ingredient call-outs, soft sampler CTA. "
                    "Build a recognizable format viewers start to anticipate."
                ),
                hook="POV: the first bowl",
                target_audience="new and prospective dog parents",
                based_on="Fresh-bowl first-bite reactions",
                why_now="The reaction format is the strongest discovery signal this week.",
                suggested_hashtags=["#freshdogfood", "#dogparent", "#dogsofinstagram"],
                cta="Try the sampler box",
                viral_score=8.4,
                effort="low",
                priority="must_do",
            ),
            MarketingIdea(
                idea_type="campaign",
                topic_category="rescue_adoption",
                title="Gotcha-Day UGC challenge",
                concept=(
                    "A month-long UGC push: customers post their rescue's before/after on fresh "
                    "food with a branded hashtag; reshare the best to Stories daily and gift a "
                    "sampler to the top three. Time it with Adopt-a-Shelter-Dog Month."
                ),
                hook="Share your gotcha day",
                target_audience="rescue dog parents",
                based_on="Rescue gotcha-day glow-ups",
                why_now="Rescue content peaks in October.",
                suggested_hashtags=["#gotchaday", "#rescuedog", "#adoptdontshop"],
                cta="Share your gotcha day",
                viral_score=7.6,
                effort="medium",
                priority="should_do",
            ),
            MarketingIdea(
                idea_type="collaboration",
                topic_category="pet_parent_life",
                title="Humor-creator treat collab",
                concept=(
                    "Partner with a humor dog creator on a slow-mo treat-catch featuring "
                    "Barkwell treats — their voice, your product placement. Co-post and boost "
                    "the winning cut."
                ),
                hook="Treat-catch, but make it cinematic",
                target_audience="broad dog-lover audience",
                based_on="signal posts (humor creators)",
                why_now="Humor creators drive the highest engagement in the niche right now.",
                suggested_hashtags=["#dogsofinstagram", "#dogtreats", "#doghumor"],
                cta="Meet Barkwell",
                viral_score=8.0,
                effort="medium",
                priority="should_do",
            ),
        ],
        "reasoning": "Lean into the reaction, gotcha-day, and humor formats overperforming.",
    }


def _briefs_kwargs() -> dict:
    return {
        "briefs": [
            Brief(
                title="First-bite reaction Reel",
                format="Reels",
                topic_category="product",
                trend_reference="Fresh-bowl first-bite reactions",
                hook="POV: your dog's first bite of fresh food",
                body=(
                    "Open tight on the dog mid-sniff as the bowl lands. Hard cut to the first "
                    "bite and the tail going. Overlay two ingredient call-outs (real chicken, "
                    "no fillers). End on a happy lick and a soft sampler line. Under 20s, "
                    "upbeat trending audio."
                ),
                cta="Try the sampler box",
                hashtags=["#freshdogfood", "#dogparent", "#dognutrition"],
                summary="Reaction Reel off the week's top discovery format.",
            ),
            Brief(
                title="Gotcha-day glow-up carousel",
                format="Carousel",
                topic_category="rescue_adoption",
                trend_reference="Rescue gotcha-day glow-ups",
                hook="From shelter to spoiled — 3 months on real food",
                body=(
                    "Slide 1: the gotcha-day photo. Slide 2: what changed (coat, energy, weight). "
                    "Slides 3-4: weekly progress shots. Slide 5: the bowl with a soft 'build your "
                    "dog's plan'. Caption tells the rescue story honestly — no health claims."
                ),
                cta="Build your dog's plan",
                hashtags=["#rescuedog", "#gotchaday", "#dogparent"],
                summary="Rescue-story carousel riding the gotcha-day trend.",
            ),
            Brief(
                title="Myth-busting 30s Reel",
                format="Reels",
                topic_category="dog_health",
                trend_reference="Vet myth-busting in 30 seconds",
                hook="'Grain-free is always healthier' — is it?",
                body=(
                    "Text-on-screen or talking head: state the myth, give the 30-second "
                    "nuance (grain-free isn't automatically better — it depends on the dog), "
                    "note that you formulate with a vet. Calm and non-alarmist; end with "
                    "'questions? our team answers'."
                ),
                cta="Talk to our team",
                hashtags=["#doghealth", "#dognutrition", "#dogtok"],
                summary="Educational myth-bust in the vet-content format.",
            ),
        ]
    }


def _compliance_kwargs() -> dict:
    results = [
        ComplianceResult(
            item_title=f"b{i}", passed=True, checks={"safety": True, "brand_tone": True}
        )
        for i in range(3)
    ]
    results += [
        ComplianceResult(
            item_title=f"i{i}", passed=True, checks={"safety": True, "brand_tone": True}
        )
        for i in range(3)
    ]
    return {"results": results}


_BUILDERS: dict[str, Callable[[], dict[str, object]]] = {
    "_FilterOutput": lambda: {"results": []},  # empty -> filter passes everything through
    "TrendReport": lambda: {"trends": _trends()},
    "_TrendList": lambda: {"trends": _trends(enriched=True)},
    "InfluencerDigest": _influencer_kwargs,
    "CompetitorReport": _competitor_kwargs,
    "ActionPlan": _action_kwargs,
    "MarketingIdeaSet": _ideas_kwargs,
    "_BriefList": _briefs_kwargs,
    "_ComplianceOutput": _compliance_kwargs,
}


def _canned(schema: type) -> object:
    builder = _BUILDERS.get(schema.__name__)
    if builder is None:
        return schema()
    return schema(**builder())


class _DemoChain:
    def __init__(self, schema: type) -> None:
        self._schema = schema

    async def ainvoke(self, messages: object) -> object:
        return _canned(self._schema)


class DemoRouter(LLMRouter):
    """An LLMRouter that never calls a provider — returns canned outputs."""

    def __init__(self) -> None:
        super().__init__(default_llm_config())

    def get_structured(
        self, role: object, schema: type, temperature: float = 0.0, *, fallback: bool = False
    ) -> object:
        return _DemoChain(schema)

    async def call_resilient(
        self,
        role: object,
        schema: type,
        messages: list[dict[str, str]],
        *,
        nonempty: object = None,
        retry_hint: str = "",
        temperature: float = 0.0,
        label: str = "?",
    ) -> object | None:
        return _canned(schema)


async def run_demo() -> Report | None:
    """Run the pipeline on bundled fixtures with canned LLM output (no keys)."""
    settings = Settings.model_validate(yaml.safe_load(example_tenant_yaml()))
    settings.apify_token = "demo"  # non-empty; the real fetch is patched out below
    settings.region.news_feeds = []  # hermetic: the demo makes no network calls
    # Inject a near-term event so the regional section always renders in the artifact.
    soon = date.today() + timedelta(days=12)
    settings.region.events = [
        EventConfig(
            name="Barkwell Summer Sampler launch",
            month=soon.month,
            day=soon.day,
            relevance_tags=["product"],
            social_potential="high",
            window_days=21,
        ),
        *settings.region.events,
    ]
    logger.info("demo_start", brand=settings.brand.name)
    with patch("smm_autopilot.engine.nodes.ingestion.fetch_dataset", _demo_fetch):
        return await run_pipeline(
            settings,
            dataset_ids=list(_DATASETS),
            source_map=_SOURCE_MAP,
            run_id="demo",
            router=DemoRouter(),
            store=Store(":memory:"),
        )
