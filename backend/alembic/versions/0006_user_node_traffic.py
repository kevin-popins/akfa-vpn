"""user node traffic

Revision ID: 0006_user_node_traffic
Revises: 0005_user_node_access
Create Date: 2026-04-29
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_user_node_traffic"
down_revision = "0005_user_node_access"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_node_traffic",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("vpn_user_id", sa.Integer(), sa.ForeignKey("vpn_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_id", sa.Integer(), sa.ForeignKey("vps_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("upload_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("download_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_raw_upload_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_raw_download_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_online_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("vpn_user_id", "node_id", name="uq_user_node_traffic"),
    )


def downgrade() -> None:
    op.drop_table("user_node_traffic")
