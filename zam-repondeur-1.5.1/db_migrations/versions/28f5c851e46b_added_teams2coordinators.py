"""Added teams2coordinators

Revision ID: 28f5c851e46b
Revises: 1cfda2dbbece
Create Date: 2020-07-21 08:47:30.273025

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "28f5c851e46b"
down_revision = "1cfda2dbbece"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "teams2coordinators",
        sa.Column("team_pk", sa.Integer(), nullable=False),
        sa.Column("user_pk", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["team_pk"], ["teams.pk"], name=op.f("teams2coordinators_team_pk_fkey")
        ),
        sa.ForeignKeyConstraint(
            ["user_pk"], ["users.pk"], name=op.f("teams2coordinators_user_pk_fkey")
        ),
        sa.PrimaryKeyConstraint("team_pk", "user_pk"),
    )


def downgrade():
    op.drop_table("teams2coordinators")
