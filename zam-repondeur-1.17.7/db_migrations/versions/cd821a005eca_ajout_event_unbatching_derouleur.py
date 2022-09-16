"""Ajout event unbatching derouleur

Revision ID: cd821a005eca
Revises: b75c3f1c7b06
Create Date: 2021-03-03 13:11:02.747809

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "cd821a005eca"
down_revision = "d5c409e00a7b"
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    op.execute(
        "DELETE FROM events WHERE type in ( \
'amendement_article_update_unbatched', \
'amendement_sort_update_unbatched' )"
    )
