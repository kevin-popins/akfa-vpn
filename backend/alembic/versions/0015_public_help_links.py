"""add public help links settings

Revision ID: 0015_public_help_links
Revises: 0014_node_traffic
Create Date: 2026-05-05 19:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0015_public_help_links"
down_revision = "0014_node_traffic"
branch_labels = None
depends_on = None


def has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if not has_table("app_settings"):
        op.create_table(
            "app_settings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("key", sa.String(length=120), nullable=False),
            sa.Column("value", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("key", name="uq_app_settings_key"),
        )
        op.create_index("ix_app_settings_key", "app_settings", ["key"], unique=True)


def downgrade() -> None:
    if has_table("app_settings"):
        op.drop_index("ix_app_settings_key", table_name="app_settings")
        op.drop_table("app_settings")
