"""Serialize pipeline signals into compact text blocks for the LLM nodes.

Shared by synthesis / strategic / content / ideation so the prompt-input format
is consistent and defined in one place.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import BrandConfig
    from ..models.competitor import CompetitorReport
    from ..models.influencer import InfluencerDigest
    from ..models.region_context import RegionContext
    from ..models.trend import Trend


def brand_block(brand: BrandConfig) -> str:
    lines = [f"Brand: {brand.name}"]
    if brand.region:
        lines.append(f"Region: {brand.region}")
    if brand.positioning:
        lines.append(f"Positioning: {brand.positioning}")
    if brand.audience:
        lines.append(f"Audience: {brand.audience}")
    if brand.tone:
        lines.append(f"Tone: {brand.tone}")
    if brand.ctas:
        lines.append(f"Preferred CTAs: {', '.join(brand.ctas)}")
    lines.append(
        f"Write content in {brand.content_language}; summaries in {brand.report_language}."
    )
    return "\n".join(lines)


def trends_block(trends: list[Trend]) -> str:
    out = []
    for t in trends:
        formats = ", ".join(t.top_formats) or "N/A"
        examples = ", ".join(t.example_posts[:3]) or "none"
        out.append(
            f"[{t.rank}] {t.title} (score {t.trend_score_display}/10)\n"
            f"  {t.description}\n"
            f"  ER {t.engagement_rate:.1%}, {t.post_count} posts, formats: {formats}, "
            f"hook: {t.hook_description or 'none'}\n"
            f"  examples: {examples}"
        )
    return "\n\n".join(out)


def _influencer_block(d: InfluencerDigest) -> str:
    parts = []
    if d.top_niches:
        parts.append(
            "Niches: "
            + ", ".join(f"{n.niche_name} (ER {n.avg_engagement_rate:.1%})" for n in d.top_niches)
        )
    if d.top_viral_posts:
        parts.append(
            "Viral posts:\n"
            + "\n".join(
                f"  @{p.account_username} [{p.category}] "
                f"ER {p.engagement_rate:.1%}: {p.caption_snippet}"
                for p in d.top_viral_posts[:5]
            )
        )
    if d.unexpected_trends:
        parts.append("Unexpected: " + ", ".join(d.unexpected_trends))
    return "\n".join(parts)


def _competitor_block(r: CompetitorReport) -> str:
    out = []
    for c in r.competitors:
        line = (
            f"@{c.username}: freq {c.posting_frequency}, "
            f"ER {c.avg_engagement_rate:.1%}, topics: {', '.join(c.top_topics[:4])}"
        )
        if c.new_campaigns:
            line += f", campaigns: {', '.join(c.new_campaigns)}"
        if c.strategy_shift:
            line += f", shift: {c.strategy_shift}"
        out.append(line)
    return "\n".join(out)


def _region_block(c: RegionContext) -> str:
    parts = []
    if c.upcoming_events:
        parts.append(
            "Upcoming events: "
            + ", ".join(
                f"{e.name} (in {e.days_until}d, {e.social_potential})"
                for e in c.upcoming_events[:5]
            )
        )
    if c.news_headlines:
        parts.append("Relevant news: " + "; ".join(n.title for n in c.news_headlines[:3]))
    return "\n".join(parts)


def signals_summary(
    trends: list[Trend],
    influencer: InfluencerDigest | None,
    competitor: CompetitorReport | None,
    region: RegionContext | None,
) -> str:
    """Combine all available signals into one labeled text block."""
    parts: list[str] = []
    if trends:
        parts.append("=== TRENDS ===\n" + trends_block(trends))
    if influencer:
        parts.append("=== INFLUENCERS ===\n" + _influencer_block(influencer))
    if competitor:
        parts.append("=== COMPETITORS ===\n" + _competitor_block(competitor))
    if region:
        parts.append("=== REGIONAL CONTEXT ===\n" + _region_block(region))
    return "\n\n".join(parts)
