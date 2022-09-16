"""alert flag dossier et lecture

Revision ID: bf862155d469
Revises: 0bedb59f5ff2
Create Date: 2021-07-29 15:16:52.106891

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "bf862155d469"
down_revision = "0bedb59f5ff2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("dossiers", sa.Column("alert_flag", sa.Boolean(), nullable=True))
    op.execute("UPDATE dossiers  SET alert_flag = false")
    op.alter_column("dossiers", "alert_flag", nullable=False)
    op.add_column("lectures", sa.Column("alert_flag", sa.Boolean(), nullable=True))
    op.execute("UPDATE lectures  SET alert_flag = false")
    op.alter_column("lectures", "alert_flag", nullable=False)


def downgrade():
    op.drop_column("lectures", "alert_flag")
    op.drop_column("dossiers", "alert_flag")
