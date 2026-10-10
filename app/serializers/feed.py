from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel


class Feed(BaseModel):
    id: int
    title: str
    url: str
    type: str


class Item(BaseModel):
    title: str
    text: str
    date: datetime
    link: str
    guid: str | None = None
    hash: str | None = None


class FeedFailure(BaseModel):
    error_type: Literal["feed_unavailable"]
    reason: str
    retry_at: AwareDatetime | None = None
