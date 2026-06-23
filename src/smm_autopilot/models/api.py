from datetime import datetime

from pydantic import BaseModel, Field


class PipelineRequest(BaseModel):
    """Request body for the optional HTTP server (POST /runs).

    Only used when the ``[server]`` extra is installed; the CLI path constructs
    pipeline state directly.
    """

    dataset_ids: list[str] = Field(min_length=1, max_length=100)
    run_id: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$"
    )  # auto-generated if None
    source_map: dict[str, str] | None = None  # dataset_id -> source label


class PipelineResponse(BaseModel):
    """Response for run-status endpoints."""

    run_id: str
    status: str  # running | completed | failed
    error: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
