"""Add account recovery quotas and revocable login sessions.

Revision ID: e6c840d39a12
Revises: d7b4a9c2e105
"""
from alembic import op
import sqlalchemy as sa

revision = "e6c840d39a12"
down_revision = "d7b4a9c2e105"
branch_labels = None
depends_on = None


def upgrade():
    # App startup may have already applied the SQLite compatibility schema.
    inspector = sa.inspect(op.get_bind())
    if "session_token" not in {column["name"] for column in inspector.get_columns("user")}:
        op.add_column("user", sa.Column("session_token", sa.String(64), nullable=True))
    if not inspector.has_table("account_recovery_throttle"):
        op.create_table(
            "account_recovery_throttle",
            sa.Column("key", sa.String(64), primary_key=True),
            sa.Column("expires_at", sa.Integer(), nullable=False),
            sa.Column("attempts", sa.Integer(), nullable=False),
        )
        op.create_index(
            "ix_account_recovery_throttle_expires_at",
            "account_recovery_throttle", ["expires_at"],
        )


def downgrade():
    op.drop_table("account_recovery_throttle")
    with op.batch_alter_table("user") as batch_op:
        batch_op.drop_column("session_token")
