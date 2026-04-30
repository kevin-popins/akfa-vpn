"""user traffic online fields

Revision ID: 0002_user_traffic_online_fields
Revises: 0001_initial
Create Date: 2026-04-29
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_user_traffic_online_fields"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vpn_users", sa.Column("last_raw_upload_bytes", sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("vpn_users", sa.Column("last_raw_download_bytes", sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("vpn_users", sa.Column("last_seen_delta_bytes", sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("vpn_users", sa.Column("last_traffic_collected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("vpn_users", sa.Column("last_online_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("vpn_users", "last_online_at")
    op.drop_column("vpn_users", "last_traffic_collected_at")
    op.drop_column("vpn_users", "last_seen_delta_bytes")
    op.drop_column("vpn_users", "last_raw_download_bytes")
    op.drop_column("vpn_users", "last_raw_upload_bytes")
