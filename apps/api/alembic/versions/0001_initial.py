"""initial schema — all 16 tables from the current models

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-03

NOTE: this bootstrap migration intentionally uses Base.metadata.create_all
(the spec allows it for the first revision). Every migration AFTER this one
must be generated with `alembic revision --autogenerate`.
"""
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app import models  # noqa: F401 — registers every table
    from app.database import Base

    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    from app import models  # noqa: F401
    from app.database import Base

    Base.metadata.drop_all(bind=op.get_bind())
