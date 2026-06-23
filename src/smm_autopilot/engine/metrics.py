"""Shared engagement metrics — one source of truth for ER + reach.

Centralizing the formula here keeps every analyzer node consistent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models.post import Post


def compute_er(post: Post, *, er_cap: float, reach_mult: int) -> float:
    """Format-aware engagement rate, capped.

    Reel with views: (likes+comments)/views. Non-Reel: (likes+comments) over a
    likes*reach_mult reach proxy. Capped at ``er_cap`` to tame giveaway outliers.
    """
    likes = max(0, post.likesCount)
    comments = max(0, post.commentsCount)
    views = max(0, post.videoPlayCount)
    if post.post_type == "Reel" and views > 0:
        return min((likes + comments) / views, er_cap)
    if post.post_type == "Reel":
        return 0.0
    reach = likes * reach_mult
    return min((likes + comments) / reach, er_cap) if reach > 0 else 0.0


def post_reach(post: Post, reach_mult: int) -> int:
    """Format-aware reach: views for Reels, likes*reach_mult otherwise."""
    if post.post_type == "Reel":
        return max(0, post.videoPlayCount)
    return max(0, post.likesCount) * reach_mult
