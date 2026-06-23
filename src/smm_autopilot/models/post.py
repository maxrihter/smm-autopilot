from datetime import datetime

from pydantic import BaseModel, model_validator


class Post(BaseModel):
    """A normalized Instagram post from Apify.

    Field names that mirror the Apify API are kept verbatim (videoPlayCount,
    likesCount, ...). ``ownerFullName`` is never stored — personal names must
    not enter pipeline state.
    """

    id: str
    url: str
    shortCode: str
    caption: str | None = None
    videoPlayCount: int = 0
    likesCount: int = 0
    commentsCount: int = 0
    timestamp: datetime
    ownerUsername: str
    source: str  # discovery_explore | discovery_hashtag | competitor | scrape_target
    post_type: str = "unknown"  # Reel | Carousel | Image | unknown
    source_segment: str = ""

    @model_validator(mode="before")
    @classmethod
    def strip_owner_full_name(cls, values: dict) -> dict:
        """Drop ownerFullName so personal names never enter pipeline state."""
        if isinstance(values, dict):
            values.pop("ownerFullName", None)
        return values
