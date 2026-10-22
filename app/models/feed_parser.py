from datetime import datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, synonym

from ._base import Base


class FeedParser(Base):
    __tablename__ = "feed_parser"

    feed_id: Mapped[int] = mapped_column(
        ForeignKey("feed.id", ondelete="CASCADE"), primary_key=True
    )
    next_run_at: Mapped[datetime] = mapped_column("valid_for", DateTime(timezone=True))
    # Compatibility for callers using the old attribute; keep the existing DB column.
    valid_for = synonym("next_run_at")
