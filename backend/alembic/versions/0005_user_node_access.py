"""user node access

Revision ID: 0005_user_node_access
Revises: 0004_node_metrics
Create Date: 2026-04-29
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_user_node_access"
down_revision = "0004_node_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vpn_users", sa.Column("primary_node_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_vpn_users_primary_node_id", "vpn_users", "vps_nodes", ["primary_node_id"], ["id"])
    op.create_table(
        "vpn_user_nodes",
        sa.Column("vpn_user_id", sa.Integer(), sa.ForeignKey("vpn_users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("node_id", sa.Integer(), sa.ForeignKey("vps_nodes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("vpn_user_id", "node_id", name="uq_vpn_user_node"),
    )
    op.execute(
        """
        INSERT INTO vpn_user_nodes (vpn_user_id, node_id)
        SELECT u.id, n.id
        FROM vpn_users u
        CROSS JOIN vps_nodes n
        WHERE u.status = 'active' AND n.status = 'online'
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE vpn_users
        SET primary_node_id = first_nodes.node_id
        FROM (
            SELECT vpn_user_id, MIN(node_id) AS node_id
            FROM vpn_user_nodes
            GROUP BY vpn_user_id
        ) AS first_nodes
        WHERE vpn_users.id = first_nodes.vpn_user_id
        """
    )


def downgrade() -> None:
    op.drop_table("vpn_user_nodes")
    op.drop_constraint("fk_vpn_users_primary_node_id", "vpn_users", type_="foreignkey")
    op.drop_column("vpn_users", "primary_node_id")
