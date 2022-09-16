"""remove events refresh dossier lecture

Revision ID: d5c409e00a7b
Revises: b75c3f1c7b06
Create Date: 2021-03-10 10:24:57.307784

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "d5c409e00a7b"
down_revision = "b75c3f1c7b06"
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    op.execute(
        "DELETE FROM events WHERE type in ('refresh_dossier', 'refresh_lecture');"
    )
