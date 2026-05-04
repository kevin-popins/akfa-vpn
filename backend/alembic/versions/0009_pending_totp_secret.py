"""add pending totp secret

Revision ID: 0009_pending_totp_secret
Revises: 0008_hwid_devices_totp_import
Create Date: 2026-05-04
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_pending_totp_secret"
down_revision = "0008_hwid_devices_totp_import"
branch_labels = None
depends_on = None


def has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if not has_column("admins", "pending_totp_secret"):
        op.add_column("admins", sa.Column("pending_totp_secret", sa.String(length=64), nullable=True))


def downgrade() -> None:
    if has_column("admins", "pending_totp_secret"):
        op.drop_column("admins", "pending_totp_secret")
