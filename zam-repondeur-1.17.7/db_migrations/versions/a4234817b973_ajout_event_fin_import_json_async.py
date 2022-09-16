"""Ajout event Fin import JSON async

Revision ID: a4234817b973
Revises: 455557a83789
Create Date: 2021-05-03 08:46:38.307234

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "a4234817b973"
down_revision = "455557a83789"
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    op.execute("DELETE FROM events WHERE type in ( 'resultats_import_json' )")
