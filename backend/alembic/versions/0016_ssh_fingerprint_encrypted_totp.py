"""add ssh host fingerprints and encrypted pending totp

Revision ID: 0016_ssh_fingerprint_totp
Revises: 0015_public_help_links
Create Date: 2026-05-13 20:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0016_ssh_fingerprint_totp"
down_revision = "0015_public_help_links"
branch_labels = None
depends_on = None


def has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    if not has_column("vps_nodes", "ssh_host_key_fingerprint"):
        op.add_column("vps_nodes", sa.Column("ssh_host_key_fingerprint", sa.String(length=128), nullable=True))
    if not has_column("admins", "pending_totp_secret_encrypted"):
        op.add_column("admins", sa.Column("pending_totp_secret_encrypted", sa.Text(), nullable=True))


def downgrade() -> None:
    if has_column("admins", "pending_totp_secret_encrypted"):
        op.drop_column("admins", "pending_totp_secret_encrypted")
    if has_column("vps_nodes", "ssh_host_key_fingerprint"):
        op.drop_column("vps_nodes", "ssh_host_key_fingerprint")
