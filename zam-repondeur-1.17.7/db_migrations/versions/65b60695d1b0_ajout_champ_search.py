"""Ajout champ search

Revision ID: 65b60695d1b0
Revises: cd821a005eca
Create Date: 2021-02-18 09:42:34.214071

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "65b60695d1b0"
down_revision = "cd821a005eca"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "amendement_user_contents",
        sa.Column("comments_search", sa.Text(), nullable=True),
    )
    op.add_column(
        "amendement_user_contents", sa.Column("objet_search", sa.Text(), nullable=True)
    )
    op.add_column(
        "amendement_user_contents",
        sa.Column("reponse_search", sa.Text(), nullable=True),
    )
    op.add_column("amendements", sa.Column("corps_search", sa.Text(), nullable=True))
    op.add_column("amendements", sa.Column("expose_search", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("amendements", "expose_search")
    op.drop_column("amendements", "corps_search")
    op.drop_column("amendement_user_contents", "reponse_search")
    op.drop_column("amendement_user_contents", "objet_search")
    op.drop_column("amendement_user_contents", "comments_search")
