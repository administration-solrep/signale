"""Add titre_loi and urls_loi to Dossier

Revision ID: 4f517bb53d67
Revises: a3f51bad5419
Create Date: 2022-06-13 08:33:44.107959

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy_utils import JSONType


# revision identifiers, used by Alembic.
revision = "4f517bb53d67"
down_revision = "a3f51bad5419"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("dossiers", sa.Column("titre_loi", sa.Text(), nullable=True))
    op.add_column("dossiers", sa.Column("urls_loi", JSONType(), nullable=True))


def downgrade():
    op.drop_column("dossiers", "urls_loi")
    op.drop_column("dossiers", "titre_loi")
