from typing import List

from slugify import slugify
from sqlalchemy import (
    Column,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.orm import backref, column_property, relationship

from .amendement import (
    Amendement,
    AmendementLocation,
    AmendementTag,
    history_association_table,
)
from .base import Base, DBSession
from .lecture import Lecture
from .users import User


class UserTable(Base):
    __tablename__ = "user_tables"
    __table_args__ = (
        Index("ix_user_tables__lecture_pk", "lecture_pk"),
        Index("ix_user_tables__user_pk", "user_pk"),
        UniqueConstraint("user_pk", "lecture_pk"),
    )

    pk: int = Column(Integer, primary_key=True)

    user_pk: int = Column(Integer, ForeignKey("users.pk"), nullable=False)
    user: User = relationship(User, back_populates="tables")

    lecture_pk: int = Column(
        Integer, ForeignKey("lectures.pk", ondelete="cascade"), nullable=False
    )
    lecture: Lecture = relationship(
        Lecture,
        backref=backref(
            "user_tables", cascade="all, delete-orphan", passive_deletes=True
        ),
    )

    amendements_locations = relationship(
        AmendementLocation, back_populates="user_table"
    )

    tags: List[AmendementTag] = relationship(
        AmendementTag, back_populates="user_table", passive_deletes=True
    )

    user_table_history = relationship(
        "Amendement",
        secondary=history_association_table,
        back_populates="amendements_history",
        passive_deletes=True,
    )

    __repr_keys__ = ("pk", "user_pk", "lecture_pk")

    def __lt__(self, other: "UserTable") -> bool:
        return self.user.email < other.user.email

    @classmethod
    def create(cls, user: User, lecture: Lecture) -> "UserTable":
        table = cls(user=user, lecture=lecture)
        DBSession.add(table)
        return table

    @property
    def amendements(self) -> List[Amendement]:
        return sorted(location.amendement for location in self.amendements_locations)

    def add_amendement(self, amendement: Amendement) -> None:
        self.amendements_locations.append(amendement.location)

    @property
    def amendements_as_string(self) -> str:
        return "_".join(str(amendement.num) for amendement in self.amendements)


class SharedTable(Base):
    __tablename__ = "shared_tables"
    __table_args__ = (
        Index("ix_shared_tables__lecture_pk", "lecture_pk"),
        UniqueConstraint("slug", "lecture_pk"),
    )

    pk: int = Column(Integer, primary_key=True)

    titre: str = Column(Text, nullable=False)
    slug: str = Column(Text, nullable=False)

    lecture_pk: int = Column(
        Integer, ForeignKey("lectures.pk", ondelete="cascade"), nullable=False
    )
    lecture: Lecture = relationship(
        Lecture,
        backref=backref(
            "shared_tables", cascade="all, delete-orphan", passive_deletes=True
        ),
    )

    amendements_locations = relationship(
        AmendementLocation, back_populates="shared_table"
    )

    __repr_keys__ = ("pk", "titre", "slug", "lecture_pk")

    nb_amendements = column_property(
        select([func.count(AmendementLocation.pk)])
        .where(AmendementLocation.shared_table_pk == pk)
        .correlate_except(AmendementLocation)
    )

    @classmethod
    def create(cls, titre: str, lecture: Lecture) -> "SharedTable":
        slug = slugify(titre)
        table = cls(titre=titre, slug=slug, lecture=lecture)
        DBSession.add(table)
        return table

    @classmethod
    def all_but_me(
        self, table: "SharedTable", lecture: "Lecture"
    ) -> List["SharedTable"]:
        shared_tables: List["SharedTable"] = DBSession.query(SharedTable).filter(
            SharedTable.slug != table.slug, SharedTable.lecture == lecture
        ).all()
        return shared_tables

    @property
    def amendements(self) -> List[Amendement]:
        return sorted(location.amendement for location in self.amendements_locations)

    def add_amendement(self, amendement: Amendement) -> None:
        self.amendements_locations.append(amendement.location)
