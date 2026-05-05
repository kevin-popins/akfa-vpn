"""allow node-level traffic snapshots without user

Revision ID: 0014_node_traffic
Revises: 0009_pending_totp_secret
Create Date: 2026-05-05 12:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0014_node_traffic"
down_revision = "0009_pending_totp_secret"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("traffic_snapshots", "vpn_user_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.alter_column("traffic_snapshots", "vpn_user_id", existing_type=sa.Integer(), nullable=False)
