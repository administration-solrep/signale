"""add technical table

Revision ID: a3f51bad5419
Revises: 3ef707f60c3a
Create Date: 2021-11-26 16:03:23.933735

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a3f51bad5419"
down_revision = "3ef707f60c3a"
branch_labels = None
depends_on = None


def upgrade():
    parametres = op.create_table(
        "parametres",
        sa.Column("pk", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("pk"),
    )
    op.bulk_insert(parametres, [{"type": "alert_system_active", "value": "1"}])


def downgrade():
    op.drop_table("parametres")
