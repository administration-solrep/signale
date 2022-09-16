"""Ajout Dossier de banc

Revision ID: c0aa6e17377c
Revises: d34231284b19
Create Date: 2021-01-08 07:21:40.172862

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c0aa6e17377c"
down_revision = "9c1f8e962399"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "amendement_location",
        sa.Column("date_dossier_de_banc", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "amendement_location",
        sa.Column("has_ever_been_on_dossier_de_banc", sa.Boolean(), nullable=True),
    )
    op.execute(
        "UPDATE amendement_location SET has_ever_been_on_dossier_de_banc = false"
    )
    op.alter_column(
        "amendement_location", "has_ever_been_on_dossier_de_banc", nullable=False
    )


def downgrade():
    op.drop_column("amendement_location", "date_dossier_de_banc")
    op.drop_column("amendement_location", "has_ever_been_on_dossier_de_banc")
    op.execute("DELETE FROM events WHERE type in ( 'transfert_dossier_de_banc' );")
