"""Add AI usage tracking table."""
from alembic import op
import sqlalchemy as sa

revision = "add_ai_usage_001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_usage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("response", sa.Text(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("api_cost", sa.Float(), nullable=False),
        sa.Column("user_cost", sa.Float(), nullable=False),
        sa.Column("profit", sa.Float(), nullable=False),
        sa.Column("session_id", sa.String()),
        sa.Column("created_at", sa.DateTime()),
    )


def downgrade():
    op.drop_table("ai_usage")
