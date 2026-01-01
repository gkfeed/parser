from sqlalchemy.orm import Mapped, mapped_column
from ._base import Base


class Feed(Base):
    __tablename__ = "feed"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column()
    url: Mapped[str] = mapped_column()
    type: Mapped[str] = mapped_column()
