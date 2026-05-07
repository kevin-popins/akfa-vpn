"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def json_type():
    return postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "admins",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("totp_secret", sa.String(64), nullable=True),
        sa.Column("role", sa.String(32), nullable=False, server_default="admin"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "access_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("routing_mode", sa.String(64), nullable=False, server_default="ru_direct"),
        sa.Column("direct_domains", json_type(), nullable=False),
        sa.Column("traffic_limit_bytes", sa.BigInteger(), nullable=True),
        sa.Column("expires_in_days", sa.Integer(), nullable=True),
        sa.Column("allowed_nodes", json_type(), nullable=False),
        sa.Column("client_template", sa.String(32), nullable=False, server_default="vless_uri"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "departments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("default_access_profile_id", sa.Integer(), sa.ForeignKey("access_profiles.id"), nullable=True),
    )
    op.create_table(
        "vps_nodes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("ip_address", sa.String(64), nullable=False),
        sa.Column("ssh_port", sa.Integer(), nullable=False, server_default="22"),
        sa.Column("ssh_username", sa.String(120), nullable=False),
        sa.Column("ssh_auth_type", sa.String(32), nullable=False, server_default="password"),
        sa.Column("encrypted_ssh_password", sa.Text(), nullable=True),
        sa.Column("encrypted_private_key", sa.Text(), nullable=True),
        sa.Column("location", sa.String(120), nullable=True),
        sa.Column("public_host", sa.String(255), nullable=True),
        sa.Column("vless_port", sa.Integer(), nullable=False, server_default="443"),
        sa.Column("sni", sa.String(255), nullable=False),
        sa.Column("reality_private_key", sa.String(255), nullable=True),
        sa.Column("reality_public_key", sa.String(255), nullable=True),
        sa.Column("short_id", sa.String(32), nullable=True),
        sa.Column("fingerprint", sa.String(32), nullable=False, server_default="chrome"),
        sa.Column("xray_config_path", sa.String(255), nullable=False, server_default="/usr/local/etc/xray/config.json"),
        sa.Column("xray_service_name", sa.String(80), nullable=False, server_default="xray"),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("last_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("install_log", json_type(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "vpn_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("first_name", sa.String(120), nullable=False),
        sa.Column("last_name", sa.String(120), nullable=False),
        sa.Column("username", sa.String(120), nullable=False, unique=True),
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.id"), nullable=True),
        sa.Column("access_profile_id", sa.Integer(), sa.ForeignKey("access_profiles.id"), nullable=True),
        sa.Column("uuid", sa.String(36), nullable=False, unique=True),
        sa.Column("subscription_token", sa.String(80), nullable=False, unique=True),
        sa.Column("traffic_limit_bytes", sa.BigInteger(), nullable=True),
        sa.Column("used_upload_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("used_download_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("used_total_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "traffic_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("vpn_user_id", sa.Integer(), sa.ForeignKey("vpn_users.id"), nullable=False),
        sa.Column("node_id", sa.Integer(), sa.ForeignKey("vps_nodes.id"), nullable=False),
        sa.Column("upload_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("download_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("admin_id", sa.Integer(), sa.ForeignKey("admins.id"), nullable=True),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.String(80), nullable=True),
        sa.Column("metadata", json_type(), nullable=False),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    for table in [
        "audit_logs",
        "traffic_snapshots",
        "vpn_users",
        "vps_nodes",
        "departments",
        "access_profiles",
        "admins",
    ]:
        op.drop_table(table)
