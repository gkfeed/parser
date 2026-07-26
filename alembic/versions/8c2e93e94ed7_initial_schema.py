"""Initial schema

Revision ID: 8c2e93e94ed7
Revises:
Create Date: 2026-06-09 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8c2e93e94ed7"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "feed",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "item",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("feed_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("link", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "feed_parser",
        sa.Column("feed_id", sa.Integer(), nullable=False),
        sa.Column("valid_for", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["feed_id"], ["feed.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("feed_id"),
    )
    op.create_table(
        "item_hash",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("hash", sa.String(), nullable=False),
        sa.Column("feed_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["feed_id"], ["feed.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("item_hash")
    op.drop_table("feed_parser")
    op.drop_table("item")
    op.drop_table("feed")
