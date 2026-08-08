"""add Google login and email verification

Revision ID: c91a6d7e8f02
Revises: fbb6c9e0f113
Create Date: 2026-07-27 03:10:00

"""
from alembic import op
import sqlalchemy as sa


revision = "c91a6d7e8f02"
down_revision = "fbb6c9e0f113"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("email_verified", sa.Boolean(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("email_verified_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("verification_sent_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("google_sub", sa.String(length=255), nullable=True)
        )
        batch_op.create_unique_constraint(
            "uq_user_google_sub",
            ["google_sub"],
        )

    # Existing members already proved account ownership through the old login flow.
    # Grandfather them in so this deployment never locks out an existing account.
    op.execute(
        sa.text(
            'UPDATE "user" '
            "SET email_verified = 1, "
            "email_verified_at = COALESCE(email_verified_at, CURRENT_TIMESTAMP)"
        )
    )

    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.alter_column(
            "email_verified",
            existing_type=sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        )


def downgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_constraint("uq_user_google_sub", type_="unique")
        batch_op.drop_column("google_sub")
        batch_op.drop_column("verification_sent_at")
        batch_op.drop_column("email_verified_at")
        batch_op.drop_column("email_verified")
