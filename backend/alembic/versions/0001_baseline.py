"""Baseline schema (all ARGUS tables, PostGIS geometry columns in production).

Revision ID: 0001_baseline
Revises:
"""

from alembic import op

import app.models  # noqa: F401
from app.db.base import Base

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind())
