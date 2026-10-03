"""Allow real-data polygon layers to contain Polygon or MultiPolygon geometries.

Revision ID: 0002_polygonal_geometry
Revises: 0001_baseline
"""

from alembic import op

revision = "0002_polygonal_geometry"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


_TABLES = ("buildings", "sectors", "population_zones")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table in _TABLES:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN geom "
            "TYPE geometry(GEOMETRY,4326) USING geom::geometry"
        )


def downgrade() -> None:
    # A strict POLYGON typmod cannot safely represent valid MultiPolygon source features.
    # Keep the generic polygonal-compatible geometry type rather than dropping data.
    return
