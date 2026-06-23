from typing import Literal

from pydantic import BaseModel, Field


class Brief(BaseModel):
    """A content brief generated from a trend. Lands in the report as a draft.

    Fields are intentionally lenient (no hard length/count constraints): a batch
    of briefs is validated atomically, so one malformed item must not discard the
    rest. The content node trims/filters per item after parsing.
    """

    title: str = ""
    format: Literal["Reels", "Carousel", "Story", "Post"] = "Reels"
    # Allowed topic set is per tenant (niche.topic_whitelist), enforced in the
    # content/compliance nodes — a plain string keeps the schema brand-agnostic.
    topic_category: str = ""
    trend_reference: str = ""
    hook: str = ""
    body: str = ""  # the post script, in the tenant's content language
    cta: str = ""
    hashtags: list[str] = Field(default_factory=list)
    summary: str = ""  # short manager-facing summary, in the report language
    approved: bool = False  # draft by default — requires human approval
