"""Add alert modified amendement column

Revision ID: 145f83238f7c
Revises: 7fe4040136f8
Create Date: 2020-09-02 14:31:50.544884
Merge UPDATE 2020-11-30
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "145f83238f7c"
down_revision = "7fe4040136f8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "amendements", sa.Column("modified", sa.Boolean(), nullable=True),
    )
    op.execute("UPDATE amendements SET modified = false")
    op.alter_column("amendements", "modified", nullable=False)


def downgrade():
    op.drop_column("amendements", "modified")
