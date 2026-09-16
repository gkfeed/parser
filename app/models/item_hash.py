from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ._base import Base


class ItemHash(Base):
    __tablename__ = "item_hash"
    __table_args__ = (UniqueConstraint("feed_id", "hash"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    hash: Mapped[str] = mapped_column()
    feed_id: Mapped[int | None] = mapped_column(
        ForeignKey("feed.id", ondelete="CASCADE")
    )
