"""Missions SENAT

Revision ID: e3c689a632bf
Revises: 9265a7b98683
Create Date: 2021-09-09 08:50:19.428568

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e3c689a632bf"
down_revision = "9265a7b98683"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "missions_senat",
        sa.Column("pk", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("lecture_pk", sa.Integer(), nullable=True),
        sa.Column("titre", sa.Text(), nullable=True),
        sa.Column("id_texte", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["lecture_pk"], ["lectures.pk"], name=op.f("missions_senat_lecture_pk_fkey")
        ),
        sa.PrimaryKeyConstraint("pk"),
        sa.UniqueConstraint(
            "id_texte",
            "lecture_pk",
            name=op.f("missions_senat_id_texte_lecture_pk_key"),
        ),
    )
    op.create_index(
        "ix_missions_senat_lecture_pk__id_texte",
        "missions_senat",
        ["lecture_pk", "id_texte"],
        unique=True,
    )
    op.drop_constraint("events_lecture_pk_fkey", "events", type_="foreignkey")
    op.create_foreign_key(
        op.f("events_lecture_pk_fkey"), "events", "lectures", ["lecture_pk"], ["pk"]
    )


def downgrade():
    op.drop_constraint(op.f("events_lecture_pk_fkey"), "events", type_="foreignkey")
    op.create_foreign_key(
        "events_lecture_pk_fkey",
        "events",
        "lectures",
        ["lecture_pk"],
        ["pk"],
        ondelete="CASCADE",
    )
    op.drop_index("ix_missions_senat_lecture_pk__id_texte", table_name="missions_senat")
    op.drop_table("missions_senat")
    op.execute("DELETE FROM events WHERE type in ('refresh_missions_senat_lecture');")
