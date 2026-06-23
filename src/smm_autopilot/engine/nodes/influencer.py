"""Influencer analysis node: rank viral creator posts into an InfluencerDigest."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, cast

from ...llm import LLMRole
from ...log import get_logger
from ...models.influencer import InfluencerDigest
from ...prompts import load_prompt
from ..metrics import compute_er

if TYPE_CHECKING:
    from ...config import Settings
    from ...llm import LLMRouter
    from ...models.post import Post
    from ...models.state import PipelineState

logger = get_logger(__name__)

_TEMPERATURE = 0.3
_MAX_VIRAL_PER_ACCOUNT = 2  # diversity cap so one creator doesn't dominate

# Strips leaked input-format lines the LLM sometimes copies into a caption_snippet.
_METADATA_LEAK_RE = re.compile(
    r"^\s*(?:views|likes|comments|account|post_type|timestamp|source|"
    r"engagement_rate|is_viral|post_id|url)\s*:\s*[^\n]*\n?",
    re.IGNORECASE | re.MULTILINE,
)
_RETRY_HINT = (
    "You MUST return at least 3 top_viral_posts. Each needs url, caption_snippet "
    "(real caption text, never metadata), views, likes, comments, engagement_rate, "
    "category, account_username."
)


def _sanitize_and_diversify(digest: InfluencerDigest) -> None:
    """Strip metadata leaks from captions and cap posts per account."""
    for p in digest.top_viral_posts:
        if p.caption_snippet and _METADATA_LEAK_RE.search(p.caption_snippet):
            p.caption_snippet = _METADATA_LEAK_RE.sub("", p.caption_snippet).strip()[:200]

    per_account: dict[str, int] = {}
    kept = []
    for p in digest.top_viral_posts:
        per_account[p.account_username] = per_account.get(p.account_username, 0) + 1
        if per_account[p.account_username] <= _MAX_VIRAL_PER_ACCOUNT:
            kept.append(p)
    digest.top_viral_posts = kept


async def influencer_analyzer_node(
    state: PipelineState, *, settings: Settings, router: LLMRouter
) -> dict[str, object]:
    """Analyze creator/KOL scrape-target posts → InfluencerDigest."""
    posts: list[Post] = state.get("scrape_target_posts") or []
    if not posts:
        return {"influencer_digest": None}

    th = settings.thresholds
    er_cap, reach_mult = th.er_cap, th.likes_to_reach_multiplier
    posts_text = "\n\n---\n\n".join(
        f"post_id: {p.id}\nurl: {p.url}\ncaption: {p.caption or ''}\n"
        f"views: {p.videoPlayCount}\nlikes: {p.likesCount}\ncomments: {p.commentsCount}\n"
        f"account: {p.ownerUsername}\nsource: {p.source}\n"
        f"engagement_rate: {compute_er(p, er_cap=er_cap, reach_mult=reach_mult):.4f}"
        for p in posts
    )
    messages = [
        {"role": "system", "content": load_prompt("influencer_analyzer_system")},
        {"role": "user", "content": posts_text},
    ]

    try:
        result = cast(
            "InfluencerDigest | None",
            await router.call_resilient(
                LLMRole.ANALYST,
                InfluencerDigest,
                messages,
                nonempty=lambda r: bool(r.top_viral_posts),
                retry_hint=_RETRY_HINT,
                temperature=_TEMPERATURE,
                label="influencer",
            ),
        )
    except Exception:
        logger.exception("influencer_analyzer_failed")
        return {"influencer_digest": None}

    if result is None:
        return {"influencer_digest": None}
    _sanitize_and_diversify(result)
    logger.info("influencer_analyzer_complete", viral_posts=len(result.top_viral_posts))
    return {"influencer_digest": result}
