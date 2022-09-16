"""Cascade association location2tag

Revision ID: 0bedb59f5ff2
Revises: 802c9d2398e8
Create Date: 2021-06-08 14:48:44.243801

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "0bedb59f5ff2"
down_revision = "802c9d2398e8"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint(
        "amendement_location2tag_amendement_location_pk_fkey",
        "amendement_location2tag",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("amendement_location2tag_amendement_location_pk_fkey"),
        "amendement_location2tag",
        "amendement_location",
        ["amendement_location_pk"],
        ["pk"],
        ondelete="cascade",
    )


def downgrade():
    op.drop_constraint(
        op.f("amendement_location2tag_amendement_location_pk_fkey"),
        "amendement_location2tag",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "amendement_location2tag_amendement_location_pk_fkey",
        "amendement_location2tag",
        "amendement_location",
        ["amendement_location_pk"],
        ["pk"],
    )
