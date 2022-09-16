"""Script to remove events created by coordinateur/contributeur ( Lot 4 )

Revision ID: f7998c17ca7c
Revises: 28f5c851e46b
Create Date: 2020-09-28 10:17:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "f7998c17ca7c"
down_revision = "28f5c851e46b"
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    op.execute(
        "DELETE FROM events WHERE type in ( \
'invitation_coordinateur_envoyee', \
'passe_en_coordinateur', \
'passe_en_contributeur' )"
    )
