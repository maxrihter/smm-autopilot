"""Competitor analysis node: per-account analysis → CompetitorReport.

The LLM does account-level reasoning (topics, campaigns, strategy); top posts are
computed in code from real data so they can't be hallucinated.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast

from ...llm import LLMRole
from ...log import get_logger
from ...models.competitor import CompetitorPost, CompetitorReport
from ...prompts import load_prompt
from ..metrics import compute_er

if TYPE_CHECKING:
    from ...config import Settings
    from ...llm import LLMRouter
    from ...models.post import Post
    from ...models.state import PipelineState

logger = get_logger(__name__)

_TEMPERATURE = 0.3
_MAX_TOP_POSTS = 5
_TOPIC_CYCLE_MIN = 3  # same top_topics across >= N competitors => templated output
_RETRY_HINT = (
    "You MUST analyze EACH competitor account in the input and return them ALL in "
    "`competitors`, each with name, username, top_topics (from real captions), "
    "content_formats, avg_engagement_rate, and an account-specific summary."
)


def _build_top_posts(
    posts: list[Post], *, er_cap: float, reach_mult: int, max_age_days: int
) -> dict[str, list[CompetitorPost]]:
    """Top posts per account by ER, computed from real data (no LLM)."""
    cutoff = datetime.now(tz=UTC) - timedelta(days=max_age_days)
    by_account: dict[str, list[Post]] = defaultdict(list)
    for p in posts:
        ts = p.timestamp if p.timestamp.tzinfo else p.timestamp.replace(tzinfo=UTC)
        if ts >= cutoff:
            by_account[p.ownerUsername].append(p)

    result: dict[str, list[CompetitorPost]] = {}
    for username, account_posts in by_account.items():
        scored = sorted(
            ((compute_er(p, er_cap=er_cap, reach_mult=reach_mult), p) for p in account_posts),
            key=lambda x: x[0],
            reverse=True,
        )
        result[username] = [
            CompetitorPost(
                url=p.url,
                post_type=p.post_type or "Image",
                views=p.videoPlayCount,
                likes=p.likesCount,
                comments=p.commentsCount,
                engagement_rate=round(er, 4),
                caption_preview=(p.caption or "")[:120],
            )
            for er, p in scored[:_MAX_TOP_POSTS]
        ]
    return result


def _validate_report(
    report: CompetitorReport,
    top_posts_by_account: dict[str, list[CompetitorPost]],
    *,
    er_cap: float,
) -> CompetitorReport:
    """Inject code-computed top posts, cap ER, reconcile formats, flag templating."""
    lower_lookup = {k.lower(): v for k, v in top_posts_by_account.items()}
    for comp in report.competitors:
        comp.avg_engagement_rate = min(comp.avg_engagement_rate, er_cap)
        comp.top_posts = lower_lookup.get(comp.username.lower(), [])
        if comp.top_posts:
            actual = sorted({p.post_type for p in comp.top_posts})
            if set(comp.content_formats) != set(actual):
                comp.content_formats = actual
        # Ensure the summary names the account (anti copy-paste across competitors).
        if comp.summary and comp.username.lower() not in comp.summary.lower():
            comp.summary = f"{comp.username}: {comp.summary}"

    _flag_topic_cycle(report)
    return report


def _flag_topic_cycle(report: CompetitorReport) -> None:
    """If >= N competitors share identical top_topics, the LLM likely templated them."""
    signatures: dict[tuple[str, ...], list[str]] = defaultdict(list)
    for comp in report.competitors:
        sig = tuple(sorted(t.strip().lower() for t in comp.top_topics))
        if sig:
            signatures[sig].append(comp.username)
    for sig, users in signatures.items():
        if len(users) >= _TOPIC_CYCLE_MIN:
            logger.warning("competitor_topic_cycle", signature=list(sig), competitors=users)
            for comp in report.competitors:
                if comp.username in users:
                    comp.top_topics = ["topics look templated across accounts — review manually"]


async def competitor_analyzer_node(
    state: PipelineState, *, settings: Settings, router: LLMRouter
) -> dict[str, object]:
    """Analyze competitor posts → CompetitorReport."""
    posts: list[Post] = state.get("competitor_posts") or []
    if not posts:
        return {"competitor_report": None}

    th = settings.thresholds
    posts_text = "\n\n---\n\n".join(
        f"post_id: {p.id}\nurl: {p.url}\ncaption: {p.caption or ''}\n"
        f"views: {p.videoPlayCount}\nlikes: {p.likesCount}\ncomments: {p.commentsCount}\n"
        f"account: {p.ownerUsername}\npost_type: {p.post_type}\n"
        f"timestamp: {p.timestamp.isoformat()}"
        for p in posts
    )
    top_posts_by_account = _build_top_posts(
        posts,
        er_cap=th.er_cap,
        reach_mult=th.likes_to_reach_multiplier,
        max_age_days=th.max_post_age_days,
    )
    messages = [
        {"role": "system", "content": load_prompt("competitor_analyzer_system")},
        {"role": "user", "content": posts_text},
    ]

    try:
        result = cast(
            "CompetitorReport | None",
            await router.call_resilient(
                LLMRole.ANALYST,
                CompetitorReport,
                messages,
                nonempty=lambda r: bool(r.competitors),
                retry_hint=_RETRY_HINT,
                temperature=_TEMPERATURE,
                label="competitor",
            ),
        )
    except Exception:
        logger.exception("competitor_analyzer_failed")
        return {"competitor_report": None}

    if result is None:
        return {"competitor_report": None}
    result = _validate_report(result, top_posts_by_account, er_cap=th.er_cap)
    logger.info("competitor_analyzer_complete", competitors=len(result.competitors))
    return {"competitor_report": result}
