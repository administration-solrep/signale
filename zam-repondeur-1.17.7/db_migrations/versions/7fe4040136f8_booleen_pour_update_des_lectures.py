"""Booleen pour update des lectures

Revision ID: 7fe4040136f8
Revises: f7998c17ca7c
Create Date: 2020-11-16 14:09:07.526246

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "7fe4040136f8"
down_revision = "f7998c17ca7c"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("lectures", sa.Column("update", sa.Boolean(), nullable=True))
    op.execute("UPDATE lectures SET update = true")
    op.alter_column("lectures", "update", nullable=False)


def downgrade():
    op.drop_column("lectures", "update")
    op.execute(
        "DELETE FROM events WHERE type in ( \
'change_update_status')"
    )
