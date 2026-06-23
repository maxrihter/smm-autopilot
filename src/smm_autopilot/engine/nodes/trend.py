"""Trend analysis node: cluster posts into ranked, score-transparent trends.

The LLM groups posts into trends and copies in example-post URLs; code then
strips hallucinated URLs, recomputes every metric from the real posts (LLMs are
unreliable at math), classifies niche-vs-context, and ranks. This keeps the
trend scores trustworthy regardless of what the model claims.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from statistics import median
from typing import TYPE_CHECKING, cast

from ...llm import LLMRole
from ...log import get_logger
from ...models.trend import Trend, TrendReport
from ...prompts import load_prompt
from ..metrics import compute_er, post_reach
from ..ranking import apply_dual_ranking, classify_is_context, niche_keywords

if TYPE_CHECKING:
    from ...config import Settings
    from ...llm import LLMRouter
    from ...models.post import Post
    from ...models.state import PipelineState

logger = get_logger(__name__)

_TEMPERATURE = 0.3
_COMPETITOR_SOURCES = {"competitor"}
_MIN_POSTS_PER_TREND = 1
_MAX_POSTS_FOR_TREND_LLM = 150
_AT_MENTION_RE = re.compile(r"@([a-zA-Z0-9._]{1,30})")
_RETRY_HINT = (
    "You MUST return at least 3 trends. Each needs title, description, "
    "example_posts (URLs copied from the input), source_types, top_formats, "
    "hook_description."
)
# Minimal stopword set for keyword-overlap matching (kept small + language-light).
_STOPWORDS: frozenset[str] = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "you",
        "your",
        "are",
        "but",
        "not",
        "this",
        "that",
        "from",
        "have",
        "was",
        "all",
        "can",
        "out",
        "now",
        "new",
        "get",
        "les",
        "des",
        "une",
        "pour",
        "avec",
        "est",
        "dans",
        "qui",
        "que",
    }
)


def _format_post_for_prompt(p: Post) -> str:
    caption = (p.caption or "")[:200]
    reach_line = (
        f"views: {p.videoPlayCount}"
        if p.post_type == "Reel"
        else f"reach_proxy_likes: {p.likesCount}"
    )
    return (
        f"post_id: {p.id}\nurl: {p.url}\ncaption: {caption}\npost_type: {p.post_type}\n"
        f"{reach_line}\nlikes: {p.likesCount}\ncomments: {p.commentsCount}\n"
        f"source: {p.source}\naccount: {p.ownerUsername}"
    )


def _tokenize(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFC", text.lower())
    words = re.split(r"[^a-zà-ÿ0-9]+", normalized)
    return {w for w in words if len(w) >= 3 and w not in _STOPWORDS}


def _assign_posts_to_trends(
    report: TrendReport, posts: list[Post], *, max_per_trend: int = 5
) -> None:
    """Assign real posts to trends by caption keyword overlap (URL fallback)."""
    if not posts or not report.trends:
        return
    post_tokens = {p.url: _tokenize(p.caption or "") for p in posts}
    assignments: list[tuple[int, Post, int, int]] = []
    for t_idx, trend in enumerate(report.trends):
        kw = _tokenize(f"{trend.title} {trend.description}")
        if not kw:
            continue
        for p in posts:
            overlap = len(kw & post_tokens.get(p.url, set()))
            if overlap >= 2:
                assignments.append((t_idx, p, overlap, post_reach(p, 10)))
    assignments.sort(key=lambda x: (x[2], x[3]), reverse=True)

    used: set[str] = set()
    per_trend: dict[int, list[Post]] = {i: [] for i in range(len(report.trends))}
    for t_idx, post, _ov, _eng in assignments:
        if post.url in used or len(per_trend[t_idx]) >= max_per_trend:
            continue
        per_trend[t_idx].append(post)
        used.add(post.url)
    for t_idx, trend in enumerate(report.trends):
        trend.example_posts = [p.url for p in per_trend.get(t_idx, [])]


def _validate_account_mentions(trend: Trend, real_usernames: set[str]) -> None:
    """Strip @mentions the LLM invented (not present in the real matched posts)."""
    if not real_usernames or "@" not in trend.description:
        return
    real = {u.lower() for u in real_usernames}
    trend.description = _AT_MENTION_RE.sub(
        lambda m: m.group(0) if m.group(1).lower() in real else "(similar accounts)",
        trend.description,
    )


def _flag_dominant_author(trend: Trend, matched: list[Post]) -> None:
    """Flag (not reject) a trend dominated by one creator (>=60% of >=2 posts)."""
    if len(matched) < 2:
        return
    counts = Counter(p.ownerUsername for p in matched if p.ownerUsername)
    if not counts:
        return
    top_owner, top_count = counts.most_common(1)[0]
    total = sum(counts.values())
    if top_count / total >= 0.6:
        trend.dominant_author = top_owner
        trend.dominant_author_count = top_count
        trend.dominant_author_total = total


def _recompute_metrics(
    report: TrendReport,
    url_to_post: dict[str, Post],
    *,
    er_cap: float,
    reach_mult: int,
    er_norm_ceiling: float,
) -> None:
    """Override LLM-claimed metrics with ground truth computed from real posts."""
    reach_values: list[int] = []
    for trend in report.trends:
        # de-dupe example_posts (LLMs repeat URLs), preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for u in trend.example_posts:
            if u not in seen:
                seen.add(u)
                unique.append(u)
        trend.example_posts = unique
        matched = [url_to_post[u] for u in trend.example_posts if u in url_to_post]
        trend.post_count = len(matched)
        if not matched:
            trend.engagement_rate = trend.engagement_norm = 0.0
            trend.views_total = trend.likes_total = 0
            reach_values.append(0)
            continue
        med_er = median(compute_er(p, er_cap=er_cap, reach_mult=reach_mult) for p in matched)
        trend.engagement_rate = round(med_er, 4)
        norm = med_er / er_norm_ceiling if er_norm_ceiling > 0 else 0.0
        trend.engagement_norm = round(min(1.0, norm), 3)
        trend.views_total = sum(post_reach(p, reach_mult) for p in matched)
        trend.likes_total = sum(max(0, p.likesCount) for p in matched)
        reach_values.append(trend.views_total + trend.likes_total)

    max_reach = max(reach_values) if reach_values else 1
    for trend, reach in zip(report.trends, reach_values, strict=True):
        trend.reach_norm = round(min(1.0, reach / max_reach), 3) if max_reach > 0 else 0.0
        matched = [url_to_post[u] for u in trend.example_posts if u in url_to_post]
        _validate_account_mentions(trend, {p.ownerUsername for p in matched if p.ownerUsername})
        _flag_dominant_author(trend, matched)


def _validate_trend_report(
    report: TrendReport,
    valid_urls: set[str],
    valid_sources: set[str],
    url_to_post: dict[str, Post],
    posts: list[Post],
    *,
    settings: Settings,
) -> TrendReport:
    """Safety-drop, strip hallucinations, fallback-assign, recompute, classify, rank."""
    # Step 0 — safety backstop: drop trends matching the configured blocklist.
    blocklist = [b.lower() for b in settings.safety_blocklist]
    if blocklist:
        kept = []
        for trend in report.trends:
            text = f"{trend.title} {trend.description}".lower()
            if any(b in text for b in blocklist):
                logger.warning("trend_safety_dropped", title=trend.title)
                continue
            kept.append(trend)
        report.trends[:] = kept

    # Step 1 — strip hallucinated URLs + validate source_types.
    zero_url: list[int] = []
    n_sources = len(valid_sources) or 1
    for i, trend in enumerate(report.trends):
        trend.example_posts = [u for u in trend.example_posts if u in valid_urls]
        trend.source_types = [s for s in trend.source_types if s in valid_sources] or sorted(
            valid_sources
        )
        trend.cross_signal_count = len(trend.source_types)
        trend.diversity_norm = round(trend.cross_signal_count / n_sources, 3)
        if not trend.example_posts:
            zero_url.append(i)

    # Step 1.5 — cross-trend URL dedup (each URL belongs to one trend).
    seen_across: set[str] = set()
    for trend in report.trends:
        unique = [u for u in trend.example_posts if u not in seen_across]
        seen_across.update(unique)
        trend.example_posts = unique
    for i, trend in enumerate(report.trends):
        if not trend.example_posts and i not in zero_url:
            zero_url.append(i)

    # Step 2 — keyword fallback for trends left with 0 URLs.
    if zero_url and posts:
        fallback = TrendReport(trends=[report.trends[i] for i in zero_url])
        used = {u for t in report.trends for u in t.example_posts}
        _assign_posts_to_trends(fallback, [p for p in posts if p.url not in used], max_per_trend=3)

    # Step 3 — recompute metrics from real posts.
    th = settings.thresholds
    _recompute_metrics(
        report,
        url_to_post,
        er_cap=th.er_cap,
        reach_mult=th.likes_to_reach_multiplier,
        er_norm_ceiling=th.er_norm_ceiling,
    )

    # Step 4 — drop trends with no real posts.
    report.trends = [
        t for t in report.trends if t.post_count >= _MIN_POSTS_PER_TREND and t.example_posts
    ]

    # Step 5 + 6 — classify niche-vs-context, then dual-rank.
    classify_is_context(report, niche_keywords(settings))
    apply_dual_ranking(report, th.top_trends_count)
    return report


async def trend_analyzer_node(
    state: PipelineState, *, settings: Settings, router: LLMRouter
) -> dict[str, object]:
    """Analyze filtered (non-competitor) posts into a ranked TrendReport."""
    all_posts: list[Post] = state.get("filtered_posts") or []
    posts = [p for p in all_posts if p.source not in _COMPETITOR_SOURCES]
    if not posts:
        return {"trend_report": None}

    mult = settings.thresholds.likes_to_reach_multiplier
    posts_sorted = sorted(posts, key=lambda p: post_reach(p, mult), reverse=True)[
        :_MAX_POSTS_FOR_TREND_LLM
    ]

    posts_text = "\n\n---\n\n".join(_format_post_for_prompt(p) for p in posts_sorted)
    valid_urls = {p.url for p in posts_sorted}
    valid_sources = {p.source for p in posts_sorted}
    url_to_post = {p.url: p for p in posts_sorted}

    messages = [
        {"role": "system", "content": load_prompt("trend_analyzer_system")},
        {"role": "user", "content": posts_text},
    ]
    try:
        result = cast(
            "TrendReport | None",
            await router.call_resilient(
                LLMRole.ANALYST,
                TrendReport,
                messages,
                nonempty=lambda r: bool(r.trends),
                retry_hint=_RETRY_HINT,
                temperature=_TEMPERATURE,
                label="trend",
            ),
        )
    except Exception:
        logger.exception("trend_analyzer_failed")
        return {"trend_report": None}

    if result is None:
        return {"trend_report": None}
    try:
        result = _validate_trend_report(
            result, valid_urls, valid_sources, url_to_post, posts_sorted, settings=settings
        )
    except Exception:
        logger.exception("trend_validate_failed")
        return {"trend_report": None}
    logger.info("trend_analyzer_complete", trends=len(result.trends))
    return {"trend_report": result}
