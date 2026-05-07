"""node config apply status

Revision ID: 0007_node_config_apply_status
Revises: 0006_user_node_traffic
Create Date: 2026-04-30
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_node_config_apply_status"
down_revision = "0006_user_node_traffic"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vps_nodes", sa.Column("last_config_applied_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("vps_nodes", sa.Column("last_config_apply_status", sa.String(32), nullable=False, server_default="pending"))
    op.add_column("vps_nodes", sa.Column("last_config_apply_error", sa.Text(), nullable=True))
    op.add_column("vps_nodes", sa.Column("last_config_version", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("vps_nodes", "last_config_version")
    op.drop_column("vps_nodes", "last_config_apply_error")
    op.drop_column("vps_nodes", "last_config_apply_status")
    op.drop_column("vps_nodes", "last_config_applied_at")
