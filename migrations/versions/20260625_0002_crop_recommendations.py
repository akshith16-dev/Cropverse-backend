"""Add persisted AI crop recommendations."""
from alembic import op
import sqlalchemy as sa

revision = "20260625_0002"
down_revision = "20260624_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crop_recommendations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("farmer_id", sa.UUID(), nullable=False),
        sa.Column("crop_id", sa.UUID(), nullable=False),
        sa.Column("recommendation_type", sa.String(length=50), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("expected_profit", sa.Float(), nullable=False),
        sa.Column("reasons", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["crop_id"], ["crops.id"]),
        sa.ForeignKeyConstraint(["farmer_id"], ["farmers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("crop_recommendations")
