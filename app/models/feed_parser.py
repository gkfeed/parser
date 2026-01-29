from datetime import datetime

from sqlalchemy import ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from ._base import Base


class FeedParser(Base):
    __tablename__ = "feed_parser"

    feed_id: Mapped[int | None] = mapped_column(
        ForeignKey("feed.id", ondelete="CASCADE"), primary_key=True
    )
    valid_for: Mapped[datetime] = mapped_column(DateTime(timezone=True))
