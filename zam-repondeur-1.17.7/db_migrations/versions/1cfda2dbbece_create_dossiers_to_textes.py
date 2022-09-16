"""create dossiers to textes

Revision ID: 1cfda2dbbece
Revises: 16b0715d5eee
Create Date: 2020-07-02 12:26:24.588891

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "1cfda2dbbece"
down_revision = "16b0715d5eee"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "dossiers2textes",
        sa.Column("dossier_pk", sa.Integer(), nullable=False),
        sa.Column("texte_pk", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["dossier_pk"],
            ["dossiers.pk"],
            name=op.f("dossiers2textes_dossier_pk_fkey"),
        ),
        sa.ForeignKeyConstraint(
            ["texte_pk"], ["textes.pk"], name=op.f("dossiers2textes_texte_pk_fkey")
        ),
        sa.PrimaryKeyConstraint("dossier_pk", "texte_pk"),
    )
    op.create_unique_constraint(op.f("dossiers_slug_key"), "dossiers", ["slug"])
    op.drop_index("ix_dossiers__slug", table_name="dossiers")
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_index("ix_dossiers__slug", "dossiers", ["slug"], unique=True)
    op.drop_constraint(op.f("dossiers_slug_key"), "dossiers", type_="unique")
    op.drop_table("dossiers2textes")
    # ### end Alembic commands ###