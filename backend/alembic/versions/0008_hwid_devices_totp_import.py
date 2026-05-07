"""hwid devices totp and xray import

Revision ID: 0008_hwid_devices_totp_import
Revises: 0013_hwid_hard_mode
Create Date: 2026-05-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008_hwid_devices_totp_import"
down_revision = "0013_hwid_hard_mode"
branch_labels = None
depends_on = None


def json_type():
    return postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    if not has_column("admins", "totp_secret_encrypted"):
        op.add_column("admins", sa.Column("totp_secret_encrypted", sa.Text(), nullable=True))
    if not has_column("admins", "totp_enabled"):
        op.add_column("admins", sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    if not has_column("admins", "totp_required"):
        op.add_column("admins", sa.Column("totp_required", sa.Boolean(), nullable=False, server_default=sa.false()))
    if not has_column("admins", "totp_confirmed_at"):
        op.add_column("admins", sa.Column("totp_confirmed_at", sa.DateTime(timezone=True), nullable=True))
    if not has_column("admins", "recovery_codes_hash"):
        op.add_column("admins", sa.Column("recovery_codes_hash", json_type(), nullable=True))

    if not has_column("vps_nodes", "xray_installed"):
        op.add_column("vps_nodes", sa.Column("xray_installed", sa.Boolean(), nullable=False, server_default=sa.false()))
    if not has_column("vps_nodes", "managed_mode"):
        op.add_column("vps_nodes", sa.Column("managed_mode", sa.String(32), nullable=False, server_default="akfa_owned"))
    if not has_column("vps_nodes", "inbound_tag"):
        op.add_column("vps_nodes", sa.Column("inbound_tag", sa.String(120), nullable=True))
    if not has_column("vps_nodes", "import_status"):
        op.add_column("vps_nodes", sa.Column("import_status", sa.String(64), nullable=True))
    if not has_column("vps_nodes", "imported_config"):
        op.add_column("vps_nodes", sa.Column("imported_config", json_type(), nullable=True))
    if not has_column("vps_nodes", "imported_inbound"):
        op.add_column("vps_nodes", sa.Column("imported_inbound", json_type(), nullable=True))

    if not has_column("vpn_users", "device_limit"):
        op.add_column("vpn_users", sa.Column("device_limit", sa.Integer(), nullable=False, server_default="5"))

    if "vpn_user_devices" not in table_names():
        op.create_table(
            "vpn_user_devices",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("vpn_user_id", sa.Integer(), sa.ForeignKey("vpn_users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(160), nullable=True),
            sa.Column("display_name", sa.String(255), nullable=True),
            sa.Column("uuid", sa.String(36), nullable=False, unique=True),
            sa.Column("subscription_token", sa.String(80), nullable=False, unique=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="active"),
            sa.Column("hwid_hash", sa.String(64), nullable=True),
            sa.Column("hwid_masked", sa.String(64), nullable=True),
            sa.Column("hwid_bound_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("platform", sa.String(32), nullable=True),
            sa.Column("client_name", sa.String(64), nullable=True),
            sa.Column("device_model", sa.String(160), nullable=True),
            sa.Column("os_version", sa.String(80), nullable=True),
            sa.Column("app_version", sa.String(80), nullable=True),
            sa.Column("user_agent", sa.Text(), nullable=True),
            sa.Column("created_ip", sa.String(64), nullable=True),
            sa.Column("ip_address", sa.String(64), nullable=True),
            sa.Column("last_ip_address", sa.String(64), nullable=True),
            sa.Column("upload_bytes", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("download_bytes", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("total_bytes", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("last_raw_upload_bytes", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("last_raw_download_bytes", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("last_seen_delta_bytes", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_subscribed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("vpn_user_id", "hwid_hash", name="uq_vpn_user_device_hwid"),
        )
    existing_indexes = index_names("vpn_user_devices")
    if "ix_vpn_user_devices_vpn_user_id" not in existing_indexes:
        op.create_index("ix_vpn_user_devices_vpn_user_id", "vpn_user_devices", ["vpn_user_id"])
    if "ix_vpn_user_devices_uuid" not in existing_indexes:
        op.create_index("ix_vpn_user_devices_uuid", "vpn_user_devices", ["uuid"])
    if "ix_vpn_user_devices_subscription_token" not in existing_indexes:
        op.create_index("ix_vpn_user_devices_subscription_token", "vpn_user_devices", ["subscription_token"])
    if "ix_vpn_user_devices_status" not in existing_indexes:
        op.create_index("ix_vpn_user_devices_status", "vpn_user_devices", ["status"])
    if "ix_vpn_user_devices_hwid_hash" not in existing_indexes:
        op.create_index("ix_vpn_user_devices_hwid_hash", "vpn_user_devices", ["hwid_hash"])


def inspector():
    return sa.inspect(op.get_bind())


def table_names() -> set[str]:
    return set(inspector().get_table_names())


def has_column(table: str, column: str) -> bool:
    if table not in table_names():
        return False
    return column in {item["name"] for item in inspector().get_columns(table)}


def index_names(table: str) -> set[str]:
    if table not in table_names():
        return set()
    return {item["name"] for item in inspector().get_indexes(table)}


def downgrade() -> None:
    op.drop_index("ix_vpn_user_devices_hwid_hash", table_name="vpn_user_devices")
    op.drop_index("ix_vpn_user_devices_status", table_name="vpn_user_devices")
    op.drop_index("ix_vpn_user_devices_subscription_token", table_name="vpn_user_devices")
    op.drop_index("ix_vpn_user_devices_uuid", table_name="vpn_user_devices")
    op.drop_index("ix_vpn_user_devices_vpn_user_id", table_name="vpn_user_devices")
    op.drop_table("vpn_user_devices")
    op.drop_column("vpn_users", "device_limit")
    for column in ["imported_inbound", "imported_config", "import_status", "inbound_tag", "managed_mode", "xray_installed"]:
        op.drop_column("vps_nodes", column)
    for column in ["recovery_codes_hash", "totp_confirmed_at", "totp_required", "totp_enabled", "totp_secret_encrypted"]:
        op.drop_column("admins", column)
