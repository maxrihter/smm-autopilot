from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class Recommendation(BaseModel):
    """A single strategic recommendation — a full, executable scenario.

    ``scenario`` holds brief-level detail; ``title`` is a short label. Fields are
    lenient (see ``Brief``) — the strategic node drops empty-scenario recs after parsing.
    """

    title: str = ""
    scenario: str = ""  # full executable scenario, in the content language
    rationale: str = ""  # why now, in the report language
    urgency: Literal["high", "medium", "low"] = "medium"
    category: Literal["campaign", "content", "timing", "competitive_gap", "collaboration"] = (
        "content"
    )
    inspired_by: list[str] = Field(default_factory=list)  # post URLs / trend names
    suggested_hook: str = ""
    suggested_cta: str = ""


class ActionPlan(BaseModel):
    """strategic_planner output. Defaults empty so a bare ``{}`` parses cleanly."""

    recommendations: list[Recommendation] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
