from datetime import datetime
from typing import Any, List, Optional

from more_itertools import unique_everseen
from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Table,
    Text,
    desc,
)
from sqlalchemy.orm import joinedload, relationship

from .base import Base, DBSession
from .events.base import LastEventMixin

association_table = Table(
    "dossiers2textes",
    Base.metadata,
    Column("dossier_pk", Integer, ForeignKey("dossiers.pk"), primary_key=True),
    Column("texte_pk", Integer, ForeignKey("textes.pk"), primary_key=True),
)


class Dossier(Base, LastEventMixin):
    __tablename__ = "dossiers"
    __table_args__ = (CheckConstraint("an_id IS NOT NULL OR senat_id IS NOT NULL"),)

    pk = Column(Integer, primary_key=True)

    an_id = Column(Text, nullable=True, unique=True)
    senat_id = Column(Text, nullable=True, unique=True)

    titre = Column(Text, nullable=False)  # TODO: make it unique?
    slug: str = Column(Text, nullable=False, unique=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    modified_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    team = relationship("Team", uselist=False, back_populates="dossier")
    textes = relationship(
        "Texte",
        secondary="dossiers2textes",
        backref="textes",
        order_by="Texte.date_depot.desc()",
    )
    lectures = relationship(
        "Lecture", back_populates="dossier", cascade="all, delete-orphan"
    )

    events = relationship(
        "Event",
        order_by="Event.created_at.desc()",
        cascade="all, delete-orphan",
        backref="dossier",
    )

    __repr_keys__ = ("pk", "slug", "titre", "an_id", "senat_id", "team")

    @property
    def url_key(self) -> str:
        return self.slug

    @property
    def titre_long(self) -> str:
        if not self.textes:
            return f"{self.titre}"
        numeros = ", ".join(
            [
                f"{numero}"
                for numero in unique_everseen((texte.numero for texte in self.textes))
            ]
        )
        return f"{self.titre} – Textes : {numeros}"

    @classmethod
    def all(cls) -> List["Dossier"]:
        dossiers: List["Dossier"] = (
            DBSession.query(cls)
            .options(joinedload("lectures"))
            .order_by(desc(cls.created_at))
            .all()
        )
        return dossiers

    @classmethod
    def create(
        cls,
        titre: str,
        slug: str,
        an_id: Optional[str] = None,
        senat_id: Optional[str] = None,
    ) -> "Dossier":
        if an_id is None and senat_id is None:
            raise ValueError("You must provide at least one of 'an_id' and 'senat_id'")
        now = datetime.utcnow()
        base_slug = slug
        counter = 1
        while True:
            if counter > 1:
                slug = f"{base_slug}-{counter}"
            existing = DBSession.query(cls).filter_by(slug=slug).first()
            if existing is None:
                break
            counter += 1
        dossier = cls(
            an_id=an_id,
            senat_id=senat_id,
            titre=titre,
            slug=slug,
            created_at=now,
            modified_at=now,
        )
        DBSession.add(dossier)
        return dossier

    @classmethod
    def get(cls, slug: str, *options: Any) -> Optional["Dossier"]:
        res: Optional["Dossier"] = DBSession.query(cls).filter(
            cls.slug == slug
        ).options(*options).first()
        return res

    @classmethod
    def exists(cls, slug: str) -> bool:
        res: bool = DBSession.query(
            DBSession.query(cls).filter(cls.slug == slug).exists()
        ).scalar()

        return res
