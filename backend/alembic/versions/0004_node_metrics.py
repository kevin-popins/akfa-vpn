"""node metrics

Revision ID: 0004_node_metrics
Revises: 0003_blocked_domains
Create Date: 2026-04-29
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_node_metrics"
down_revision = "0003_blocked_domains"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vps_nodes", sa.Column("last_raw_inbound_upload_bytes", sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("vps_nodes", sa.Column("last_raw_inbound_download_bytes", sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("vps_nodes", sa.Column("traffic_upload_bytes", sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("vps_nodes", sa.Column("traffic_download_bytes", sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("vps_nodes", sa.Column("traffic_total_bytes", sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("vps_nodes", sa.Column("last_metrics_collected_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("vps_nodes", "last_metrics_collected_at")
    op.drop_column("vps_nodes", "traffic_total_bytes")
    op.drop_column("vps_nodes", "traffic_download_bytes")
    op.drop_column("vps_nodes", "traffic_upload_bytes")
    op.drop_column("vps_nodes", "last_raw_inbound_download_bytes")
    op.drop_column("vps_nodes", "last_raw_inbound_upload_bytes")
