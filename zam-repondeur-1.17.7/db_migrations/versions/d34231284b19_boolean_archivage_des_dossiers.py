"""Boolean archivage des dossiers

Revision ID: d34231284b19
Revises: 145f83238f7c
Create Date: 2020-12-03 13:47:01.526585

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "d34231284b19"
down_revision = "145f83238f7c"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("teams", sa.Column("active", sa.Boolean(), nullable=True))
    op.execute("UPDATE teams SET active = true")
    op.alter_column("teams", "active", nullable=False)


def downgrade():
    op.drop_column("teams", "active")
    op.execute("DELETE FROM events WHERE type in ( 'archiver_dossier' );")
