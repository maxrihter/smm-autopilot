from pydantic import BaseModel, Field


class ComplianceResult(BaseModel):
    """Result of the compliance gate for one content item (brief or idea).

    ``checks`` keys are defined by the compliance prompt/config (e.g. safety,
    brand_tone, platform_policy, legal) — kept generic so each tenant can
    configure its own check set.
    """

    item_title: str
    passed: bool
    checks: dict[str, bool] = Field(default_factory=dict)
    suggestion: str = ""  # empty when passed; a one-sentence fix when failed
