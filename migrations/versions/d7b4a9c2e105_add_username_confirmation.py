"""add username confirmation for Google signups

Revision ID: d7b4a9c2e105
Revises: c91a6d7e8f02
Create Date: 2026-07-27 04:12:00

"""
from alembic import op
import sqlalchemy as sa


revision = "d7b4a9c2e105"
down_revision = "c91a6d7e8f02"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("username_confirmed", sa.Boolean(), nullable=True)
        )

    op.execute(sa.text('UPDATE "user" SET username_confirmed = 1'))
    op.execute(
        sa.text(
            'UPDATE "user" SET username_confirmed = 0 '
            "WHERE google_sub IS NOT NULL AND password_hash IS NULL"
        )
    )

    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.alter_column(
            "username_confirmed",
            existing_type=sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        )


def downgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("username_confirmed")
