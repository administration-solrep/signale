"""remove events import export global

Revision ID: 9265a7b98683
Revises: bf862155d469
Create Date: 2021-09-03 12:49:35.382978

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "9265a7b98683"
down_revision = "bf862155d469"
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    op.execute(
        "DELETE FROM events WHERE type in ("
        "'export_dossier_zip_start', "
        "'export_dossier_zip_ready', "
        "'import_dossier_zip_start', "
        "'import_dossier_zip_end', "
        "'import_dossier_zip_lecture_not_found'"
        ");"
    )
