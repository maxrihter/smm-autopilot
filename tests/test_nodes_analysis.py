"""Analysis nodes — offline behavior: skip-on-empty + the code-side
post-processing (trend recompute/rank, competitor top-posts, influencer diversity).
No API keys: the LLM call is never reached for these paths."""

from __future__ import annotations

from datetime import UTC, datetime

from smm_autopilot.config import default_settings
from smm_autopilot.engine.nodes.competitor import _build_top_posts, competitor_analyzer_node
from smm_autopilot.engine.nodes.influencer import _sanitize_and_diversify, influencer_analyzer_node
from smm_autopilot.engine.nodes.trend import _validate_trend_report, trend_analyzer_node
from smm_autopilot.llm import LLMRouter, default_llm_config
from smm_autopilot.models import InfluencerDigest, Post, Trend, TrendReport, ViralPost


def _post(url: str, **kw: object) -> Post:
    data: dict[str, object] = {
        "id": url,
        "url": url,
        "shortCode": url.rsplit("/", 1)[-1],
        "ownerUsername": "acct",
        "timestamp": datetime.now(tz=UTC),
        "source": "discovery_explore",
        "post_type": "Reel",
        "videoPlayCount": 10000,
        "likesCount": 500,
        "commentsCount": 50,
    }
    data.update(kw)
    return Post(**data)  # type: ignore[arg-type]


async def test_analysis_nodes_skip_on_empty() -> None:
    s, r = default_settings(), LLMRouter(default_llm_config())
    inf = await influencer_analyzer_node(
        {"dataset_ids": [], "run_id": "t", "scrape_target_posts": []},
        settings=s,
        router=r,  # type: ignore[arg-type]
    )
    comp = await competitor_analyzer_node(
        {"dataset_ids": [], "run_id": "t", "competitor_posts": []},
        settings=s,
        router=r,  # type: ignore[arg-type]
    )
    trend = await trend_analyzer_node(
        {"dataset_ids": [], "run_id": "t", "filtered_posts": []},
        settings=s,
        router=r,  # type: ignore[arg-type]
    )
    assert inf["influencer_digest"] is None
    assert comp["competitor_report"] is None
    assert trend["trend_report"] is None


def test_influencer_diversity_cap() -> None:
    digest = InfluencerDigest(
        top_viral_posts=[
            ViralPost(
                url=f"u{i}",
                caption_snippet="hi",
                views=1,
                engagement_rate=0.1,
                category="c",
                account_username="same",
            )
            for i in range(5)
        ]
    )
    _sanitize_and_diversify(digest)
    assert len(digest.top_viral_posts) == 2  # capped per account


def test_competitor_top_posts_built_from_real_data() -> None:
    posts = [
        _post("https://a/1", ownerUsername="duo"),
        _post("https://a/2", ownerUsername="duo", videoPlayCount=99999),
    ]
    top = _build_top_posts(posts, er_cap=0.5, reach_mult=10, max_age_days=90)
    assert "duo" in top
    assert len(top["duo"]) == 2


def test_trend_recompute_strips_fake_urls_and_ranks() -> None:
    posts = [
        _post("https://p/1", caption="fresh dog food bowl"),
        _post("https://p/2", caption="puppy training", ownerUsername="b"),
    ]
    url_to_post = {p.url: p for p in posts}
    report = TrendReport(
        trends=[
            Trend(
                rank=99,
                title="Fresh food",
                description="bowls",
                post_count=0,
                example_posts=["https://p/1", "https://p/2", "https://fake/x"],
                source_types=["discovery_explore"],
            )
        ]
    )
    out = _validate_trend_report(
        report,
        {p.url for p in posts},
        {"discovery_explore"},
        url_to_post,
        posts,
        settings=default_settings(),
    )
    t = out.trends[0]
    assert t.post_count == 2  # fake URL dropped, two real posts remain
    assert t.rank == 1
    assert t.engagement_rate > 0
