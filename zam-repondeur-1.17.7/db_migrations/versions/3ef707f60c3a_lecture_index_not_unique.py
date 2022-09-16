"""Lecture Index Not Unique

Revision ID: 3ef707f60c3a
Revises: e3c689a632bf
Create Date: 2021-11-19 08:35:52.633688

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "3ef707f60c3a"
down_revision = "e3c689a632bf"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index("ix_lectures__texte_pk__partie__organe", table_name="lectures")
    op.create_index(
        "ix_lectures__texte_pk__partie__organe",
        "lectures",
        ["texte_pk", "partie", "organe"],
        unique=False,
    )


def downgrade():
    # On ne repasse pas l'index en unique=True
    op.drop_index("ix_lectures__texte_pk__partie__organe", table_name="lectures")
    op.create_index(
        "ix_lectures__texte_pk__partie__organe",
        "lectures",
        ["texte_pk", "partie", "organe"],
        unique=False,
    )
