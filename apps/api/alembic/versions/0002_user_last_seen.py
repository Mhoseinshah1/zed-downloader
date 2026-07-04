"""add users.last_seen_at (Phase 2)

Revision ID: 0002_user_last_seen
Revises: 0001_initial
Create Date: 2026-07-04

Additive and safe: a nullable column, so it applies cleanly to an existing
populated users table with no backfill and no downtime.
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_user_last_seen"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Guard against re-running against a DB that already has the column
    # (e.g. created via metadata.create_all in a dev/test path).
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("users")}
    if "last_seen_at" not in cols:
        op.add_column("users", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("users")}
    if "last_seen_at" in cols:
        op.drop_column("users", "last_seen_at")
