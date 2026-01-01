from sqlalchemy.orm import Mapped, mapped_column
from ._base import Base


class ItemHash(Base):
    __tablename__ = "item_hash"

    id: Mapped[int] = mapped_column(primary_key=True)
    hash: Mapped[str] = mapped_column()
