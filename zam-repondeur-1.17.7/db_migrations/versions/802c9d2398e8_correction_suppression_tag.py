"""Correction suppression tag

Revision ID: 802c9d2398e8
Revises: a4234817b973
Create Date: 2021-06-03 07:33:22.891048

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "802c9d2398e8"
down_revision = "a4234817b973"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint(
        "amendement_tag_user_table_pk_fkey", "amendement_tag", type_="foreignkey"
    )
    op.create_foreign_key(
        op.f("amendement_tag_user_table_pk_fkey"),
        "amendement_tag",
        "user_tables",
        ["user_table_pk"],
        ["pk"],
        ondelete="CASCADE",
    )


def downgrade():
    op.drop_constraint(
        op.f("amendement_tag_user_table_pk_fkey"), "amendement_tag", type_="foreignkey"
    )
    op.create_foreign_key(
        "amendement_tag_user_table_pk_fkey",
        "amendement_tag",
        "user_tables",
        ["user_table_pk"],
        ["pk"],
    )
