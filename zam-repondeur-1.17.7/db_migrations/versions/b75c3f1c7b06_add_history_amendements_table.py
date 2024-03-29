"""add history amendements table

Revision ID: b75c3f1c7b06
Revises: c0aa6e17377c
Create Date: 2021-01-27 16:45:47.109590

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b75c3f1c7b06"
down_revision = "c0aa6e17377c"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "amendements_history_table",
        sa.Column("user_table_pk", sa.Integer(), nullable=False),
        sa.Column("amendements_pk", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["amendements_pk"],
            ["amendements.pk"],
            name=op.f("amendements_history_table_amendements_pk_fkey"),
            ondelete="cascade",
        ),
        sa.ForeignKeyConstraint(
            ["user_table_pk"],
            ["user_tables.pk"],
            name=op.f("amendements_history_table_user_table_pk_fkey"),
            ondelete="cascade",
        ),
        sa.PrimaryKeyConstraint("user_table_pk", "amendements_pk"),
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("amendements_history_table")
    # ### end Alembic commands ###
