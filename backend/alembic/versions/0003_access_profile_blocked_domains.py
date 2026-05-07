"""access profile blocked domains

Revision ID: 0003_blocked_domains
Revises: 0002_user_traffic_online_fields
Create Date: 2026-04-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_blocked_domains"
down_revision = "0002_user_traffic_online_fields"
branch_labels = None
depends_on = None


def json_type():
    return postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.add_column(
        "access_profiles",
        sa.Column("blocked_domains", json_type(), nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade() -> None:
    op.drop_column("access_profiles", "blocked_domains")
