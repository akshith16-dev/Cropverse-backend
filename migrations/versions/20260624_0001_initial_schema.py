"""Initial Cropverse schema.

This baseline migration mirrors the SQLAlchemy models without changing the
runtime models. It is safe for new production databases; for an existing
database, stamp this revision after confirming the schema already exists:

    alembic stamp 20260624_0001
"""
from alembic import op

from db import Base
import models  # noqa: F401 - load all model classes into Base.metadata

revision = "20260624_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
