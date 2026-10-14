"""Widen scenario model-version labels used by historical real-data packs.

Revision ID: 0003_scenario_model_version
Revises: 0002_polygonal_geometry
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_scenario_model_version"
down_revision = "0002_polygonal_geometry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "scenarios",
        "model_version",
        existing_type=sa.String(length=64),
        type_=sa.String(length=255),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Descriptive model labels in the historical packs can exceed 64 characters.
    # Narrowing would risk truncating valid provenance, so keep the widened column.
    return
