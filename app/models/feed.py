from sqlalchemy import Enum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.parser_id import ParserId

from ._base import Base


class Feed(Base):
    __tablename__ = "feed"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column()
    url: Mapped[str] = mapped_column()
    type: Mapped[ParserId] = mapped_column(
        Enum(
            ParserId,
            values_callable=lambda ids: [parser_id.value for parser_id in ids],
            native_enum=False,
            length=None,
            validate_strings=True,
        )
    )
