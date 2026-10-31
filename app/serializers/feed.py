from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict

from app.core.parser_id import ParserId


class Feed(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    id: int
    title: str
    url: str
    type: ParserId


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


class FeedResult(BaseModel):
    items: list[Item]
    retry_at: AwareDatetime | None = None
