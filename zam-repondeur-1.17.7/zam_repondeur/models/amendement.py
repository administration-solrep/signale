import re
from datetime import date, datetime
from typing import (
    TYPE_CHECKING,
    Dict,
    Iterable,
    List,
    NamedTuple,
    Optional,
    Set,
    Tuple,
    Union,
)

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Table,
    Text,
    UniqueConstraint,
    case,
    func,
)
from sqlalchemy.orm import backref, column_property, relationship

from zam_repondeur.constants import GROUPS_COLORS
from zam_repondeur.decorator import reify
from zam_repondeur.services.amendements import repository as amendements_repository
from zam_repondeur.services.clean import clean_all_for_search

from .base import Base, DBSession
from .batch import Batch
from .division import ADJECTIFS_MULTIPLICATIFS

# Make these types available to mypy, but avoid circular imports
if TYPE_CHECKING:
    from .article import Article  # noqa
    from .lecture import Lecture  # noqa
    from .table import SharedTable, UserTable  # noqa
    from .users import User  # noqa

DOSSIER_DE_BANC = "Dossier de banc"
ADD = "add"
AVIS = [
    "Favorable",
    "Défavorable",
    "Favorable sous réserve de",
    "Retrait",
    "Retrait au profit de",
    "Retrait sinon rejet",
    "Retrait sous réserve de",
    "Sagesse",
    "Satisfait donc rejet",
]
IRRECEVABLE = {
    "titre": "Irrecevable",
    "statut": "Irr.",
    "class": "grey",
}
RETIRE = {
    "titre": "Retiré",
    "statut": "Ret.",
    "class": "grey",
}
TOMBE = {
    "titre": "Tombé",
    "statut": "Tombé",
    "class": "grey",
}
GOUVERNEMENTAL = {
    "titre": "Gouvernemental",
    "statut": "Gouv.",
    "class": "blue",
}
REJETE = {
    "titre": "Rejeté",
    "statut": "Rejeté",
    "class": "grey",
}
NON_SOUTENU = {
    "titre": "Non soutenu",
    "statut": "Non soutenu",
    "class": "grey",
}
ADOPTE = {
    "titre": "Adopté",
    "statut": "Adopté",
    "class": "blue",
}
SORT = (
    IRRECEVABLE,
    RETIRE,
    TOMBE,
    GOUVERNEMENTAL,
    REJETE,
    NON_SOUTENU,
    ADOPTE,
)
UNBATCHING_SORTS = {
    sort["titre"].lower(): sort["titre"] for sort in (IRRECEVABLE, RETIRE, TOMBE)
}
SEARCHING_SORTS = {
    sort["titre"].lower(): sort["titre"]
    for sort in (IRRECEVABLE, RETIRE, TOMBE, REJETE, NON_SOUTENU, ADOPTE)
}


GroupingKey = Tuple[str, str, str, str]

history_association_table = Table(
    "amendements_history_table",
    Base.metadata,
    Column(
        "user_table_pk",
        Integer,
        ForeignKey("user_tables.pk", ondelete="cascade"),
        primary_key=True,
    ),
    Column(
        "amendements_pk",
        Integer,
        ForeignKey("amendements.pk", ondelete="cascade"),
        primary_key=True,
    ),
)

tag_association_table = Table(
    "amendement_location2tag",
    Base.metadata,
    Column("tag_pk", Integer, ForeignKey("amendement_tag.pk"), primary_key=True),
    Column(
        "amendement_location_pk",
        Integer,
        ForeignKey("amendement_location.pk", ondelete="cascade"),
        primary_key=True,
    ),
)


class ReponseTuple(NamedTuple):
    avis: str
    objet: str
    content: str
    comments: str

    @property
    def is_empty(self) -> bool:
        return (
            self.avis == ""
            and self.objet == ""
            and self.content == ""
            and self.comments == ""
        )


class AmendementUserContent(Base):
    __tablename__ = "amendement_user_contents"
    __table_args__ = (
        Index(
            "ix_amendement_user_contents__amendement_pk", "amendement_pk", unique=True
        ),
    )

    pk: int = Column(Integer, primary_key=True)
    avis: Optional[str] = Column(Text, nullable=True)
    objet: Optional[str] = Column(Text, nullable=True)
    reponse: Optional[str] = Column(Text, nullable=True)
    comments: Optional[str] = Column(Text, nullable=True)

    # Contenu pour la recherche
    objet_search: Optional[str] = Column(Text, nullable=True)
    reponse_search: Optional[str] = Column(Text, nullable=True)
    comments_search: Optional[str] = Column(Text, nullable=True)

    amendement_pk: int = Column(
        Integer, ForeignKey("amendements.pk", ondelete="cascade"), nullable=False
    )
    amendement: "Amendement" = relationship("Amendement", back_populates="user_content")

    __repr_keys__ = ("pk", "amendement_pk", "avis")

    @property
    def is_redactionnel(self) -> bool:
        return (
            self.avis == "Favorable"
            and self.objet is not None
            and "rédactionnel" in self.objet.lower()
            and not self.has_reponse
        )

    has_objet: bool = column_property(func.trim(objet).notin_(["", "<p></p>"]))

    has_reponse: bool = column_property(func.trim(reponse).notin_(["", "<p></p>"]))

    @property
    def favorable(self) -> bool:
        if self.avis is None:
            return False
        return self.avis.startswith("Favorable")

    @property
    def sagesse(self) -> bool:
        if self.avis is None:
            return False
        return self.avis == "Sagesse" or self.avis == "Satisfait donc rejet"

    def similaire(self, other: "AmendementUserContent") -> bool:
        """
        Same answer (with maybe some whitespace differences)
        """
        return self.reponse_hash == other.reponse_hash

    reponse_hash: str = column_property(
        func.md5(
            case([(avis.is_(None), "")], else_=avis)  # type: ignore
            + case([(objet.is_(None), "")], else_=func.trim(objet))  # type: ignore
            + case([(reponse.is_(None), "")], else_=func.trim(reponse))  # type: ignore
        )
    )

    def as_tuple(self) -> ReponseTuple:
        return ReponseTuple(
            avis=self.avis or "",
            objet=(self.objet.strip() if self.objet else ""),
            content=(self.reponse.strip() if self.reponse else ""),
            comments=(self.comments.strip() if self.comments else ""),
        )

    @property
    def is_answered(self) -> bool:
        return (
            self.avis is not None or self.objet is not None or self.reponse is not None
        )


class AmendementTag(Base):
    __tablename__ = "amendement_tag"
    __table_args__ = (
        UniqueConstraint("user_table_pk", "label", name="_label_by_user_table_pk"),
    )

    pk: int = Column(Integer, primary_key=True)

    label: str = Column(Text, nullable=False)

    user_table_pk: int = Column(
        Integer, ForeignKey("user_tables.pk", ondelete="CASCADE"), nullable=True
    )
    user_table: "Optional[UserTable]" = relationship("UserTable", back_populates="tags")

    locations: "List[AmendementLocation]" = relationship(
        "AmendementLocation",
        secondary=tag_association_table,
        backref="amendement_tag",
        passive_deletes=True,
    )
    __repr_keys__ = ("pk", "label")

    @classmethod
    def get_or_create(cls, label: str, user_table: "UserTable") -> "AmendementTag":
        tag: "Optional[AmendementTag]" = (
            DBSession.query(cls)
            .filter(cls.label == label, cls.user_table == user_table)
            .one_or_none()
        )
        if not tag:
            tag = cls(label=label, user_table=user_table)
            DBSession.add(tag)
        return tag

    @classmethod
    def get(cls, label: str, user_table: "UserTable") -> "Optional[AmendementTag]":
        tag: "Optional[AmendementTag]" = (
            DBSession.query(cls)
            .filter(cls.label == label, cls.user_table == user_table)
            .one_or_none()
        )
        return tag


class AmendementLocation(Base):
    __tablename__ = "amendement_location"
    __table_args__ = (
        Index("ix_amendement_location__amendement_pk", "amendement_pk", unique=True),
    )

    pk: int = Column(Integer, primary_key=True)
    amendement_pk: int = Column(
        Integer, ForeignKey("amendements.pk", ondelete="cascade"), nullable=False
    )
    amendement: "Amendement" = relationship("Amendement", back_populates="location")

    user_table_pk: int = Column(Integer, ForeignKey("user_tables.pk"), nullable=True)
    user_table: "Optional[UserTable]" = relationship(
        "UserTable", back_populates="amendements_locations"
    )
    shared_table_pk: int = Column(
        Integer, ForeignKey("shared_tables.pk"), nullable=True
    )
    shared_table: "Optional[SharedTable]" = relationship(
        "SharedTable", back_populates="amendements_locations"
    )
    batch_pk: int = Column(Integer, ForeignKey("batches.pk"), nullable=True)
    batch: Optional[Batch] = relationship(Batch, back_populates="amendements_locations")

    date_dossier_de_banc: Optional[datetime] = Column(DateTime, nullable=True)
    has_ever_been_on_dossier_de_banc: bool = Column(
        Boolean, nullable=False, default=False
    )

    tags: "List[AmendementTag]" = relationship(
        "AmendementTag", secondary=tag_association_table, backref="amendement_location"
    )

    __repr_keys__ = ("pk", "amendement_pk")

    @property
    def get_current_tags(self) -> List[AmendementTag]:
        return [tag for tag in self.tags if tag.user_table_pk == self.user_table_pk]


class Amendement(Base):
    VERY_BIG_NUMBER = 999_999_999
    __tablename__ = "amendements"
    __table_args__ = (
        Index("ix_amendements__lecture_pk", "lecture_pk"),
        Index("ix_amendements__parent_pk", "parent_pk"),
        UniqueConstraint("num", "lecture_pk"),
        UniqueConstraint("position", "lecture_pk"),
    )

    pk: int = Column(Integer, primary_key=True)
    created_at: datetime = Column(DateTime, nullable=False)

    # Meta informations.
    num: int = Column(Integer, nullable=False)
    rectif: int = Column(Integer, nullable=False, default=0)
    auteur: Optional[str] = Column(Text, nullable=True)
    matricule: Optional[str] = Column(Text, nullable=True)
    groupe: Optional[str] = Column(Text, nullable=True)
    date_depot: Optional[date] = Column(Date, nullable=True)
    sort: Optional[str] = Column(Text, nullable=True)
    mission_titre: Optional[str] = Column(Text, nullable=True)
    mission_titre_court: Optional[str] = Column(Text, nullable=True)
    modified: bool = Column(Boolean, nullable=False)

    # Ordre et regroupement lors de la discussion.
    position: Optional[int] = Column(Integer, nullable=True)
    id_discussion_commune: Optional[int] = Column(Integer, nullable=True)
    id_identique: Optional[int] = Column(Integer, nullable=True)

    # Contenu.
    expose: Optional[str] = Column(Text, nullable=True)  # exposé sommaire
    corps: Optional[str] = Column(Text, nullable=True)  # alias dispositif (légistique)
    resume: Optional[str] = Column(Text, nullable=True)  # résumé du corps
    alinea: Optional[str] = Column(Text, nullable=True)  # libellé de l'alinéa ciblé

    # Contenu pour la recherche
    expose_search: Optional[str] = Column(Text, nullable=True)  # exposé sommaire
    corps_search: Optional[str] = Column(
        Text, nullable=True
    )  # alias dispositif (légistique)

    # Relations.
    parent_pk: Optional[int] = Column(
        Integer, ForeignKey("amendements.pk"), nullable=True
    )
    parent_rectif: Optional[int] = Column(Integer, nullable=True)
    parent: Optional["Amendement"] = relationship(
        "Amendement",
        uselist=False,
        remote_side=[pk],
        backref=backref("children"),
        post_update=True,
    )

    lecture_pk: int = Column(Integer, ForeignKey("lectures.pk", ondelete="cascade"))
    lecture: "Lecture" = relationship("Lecture", back_populates="amendements")

    article_pk: int = Column(Integer, ForeignKey("articles.pk"))
    article: "Article" = relationship("Article", back_populates="amendements")

    location: AmendementLocation = relationship(  # technically it's Optional
        AmendementLocation,
        back_populates="amendement",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    user_content: AmendementUserContent = relationship(  # technically it's Optional
        AmendementUserContent,
        back_populates="amendement",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    events = relationship(
        "Event",
        order_by="Event.created_at.desc()",
        cascade="all, delete-orphan",
        passive_deletes=True,
        backref="amendement",
    )

    amendements_history = relationship(
        "UserTable",
        secondary=history_association_table,
        back_populates="user_table_history",
        cascade="all, delete",
    )

    __repr_keys__ = ("pk", "num", "rectif", "lecture_pk", "article_pk", "parent_pk")

    @classmethod
    def get(cls, lecture: "Lecture", num: int) -> "Amendement":
        amendement: "Amendement" = DBSession.query(cls).filter_by(
            lecture=lecture, num=num
        ).one()
        return amendement

    @classmethod
    def create(  # type: ignore
        cls,
        lecture,
        article,
        num: int,
        rectif: int = 0,
        auteur: str = "",
        groupe: str = "",
        matricule: Optional[str] = None,
        date_depot: Optional[date] = None,
        sort: Optional[str] = None,
        position: Optional[int] = None,
        id_discussion_commune: Optional[int] = None,
        id_identique: Optional[int] = None,
        expose: Optional[str] = None,
        corps: Optional[str] = None,
        resume: Optional[str] = None,
        alinea: Optional[str] = None,
        parent: Optional["Amendement"] = None,
        batch: Optional[Batch] = None,
        mission_titre: Optional[str] = None,
        mission_titre_court: Optional[str] = None,
        avis: Optional[str] = None,
        objet: Optional[str] = None,
        reponse: Optional[str] = None,
        comments: Optional[str] = None,
        modified: bool = False,
    ) -> "Amendement":
        now = datetime.utcnow()
        expose_search = clean_all_for_search(expose or "")
        corps_search = clean_all_for_search(corps or "")
        amendement = cls(
            lecture=lecture,
            article=article,
            num=num,
            rectif=rectif,
            auteur=auteur,
            matricule=matricule,
            groupe=groupe,
            date_depot=date_depot,
            sort=sort,
            position=position,
            id_discussion_commune=id_discussion_commune,
            id_identique=id_identique,
            expose=expose,
            expose_search=expose_search,
            corps=corps,
            corps_search=corps_search,
            resume=resume,
            alinea=alinea,
            parent=parent,
            mission_titre=mission_titre,
            mission_titre_court=mission_titre_court,
            created_at=now,
            modified=modified,
        )
        location = AmendementLocation(amendement=amendement, batch=batch)
        objet_search = clean_all_for_search(objet or "")
        reponse_search = clean_all_for_search(reponse or "")
        comments_search = clean_all_for_search(comments or "")
        user_content = AmendementUserContent(
            amendement=amendement,
            avis=avis,
            objet=objet,
            objet_search=objet_search,
            reponse=reponse,
            reponse_search=reponse_search,
            comments=comments,
            comments_search=comments_search,
        )
        DBSession.add(location)
        DBSession.add(user_content)
        return amendement

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Amendement):
            return NotImplemented
        return self.sort_key < other.sort_key

    @reify
    def sort_key(self) -> Tuple[bool, int, "Article", int]:
        return (
            self.is_abandoned,
            self.position or self.VERY_BIG_NUMBER,
            self.article,
            self.num,
        )

    @reify
    def num_str(self) -> str:
        return str(self.num)

    @reify
    def num_disp(self) -> str:
        text = self.num_str
        if self.rectif > 0:
            text += " rect."
        if self.rectif > 1:
            if self.rectif not in self._RECTIF_TO_SUFFIX:
                raise NotImplementedError
            text += " "
            text += self._RECTIF_TO_SUFFIX[self.rectif]
        return text

    def __str__(self) -> str:
        return self.num_disp

    @property
    def couleur_groupe(self) -> str:
        return GROUPS_COLORS.get(self.groupe or "", "#ffffff")

    @property
    def slug(self) -> str:
        return f'amdt-{self.num_disp.replace(" ", "-").replace(".", "")}'

    _RECTIF_TO_SUFFIX = {
        2: "bis",
        3: "ter",
        4: "quater",
        5: "quinquies",
        6: "sexies",
        7: "septies",
        8: "octies",
        9: "nonies",
        10: "decies",
        11: "undecies",
        12: "duodecies",
        13: "terdecies",
        14: "quaterdecies",
        15: "quindecies",
        16: "sexdecies",
        17: "septdecies",
        18: "octodecies",
        19: "novodecies",
        20: "vicies",
        21: "unvicies",
        22: "duovicies",
        23: "tervicies",
        24: "quatervicies",
        25: "quinvicies",
        26: "sexvicies",
        27: "septvicies",
        28: "duodetrecies",
        29: "undetricies",
        30: "tricies",
    }

    _NUM_RE = re.compile(
        r"""
            (?P<prefix>[A-Z\|\-]*)
            (?P<num>\d+)
            (?P<rect>\ rect\.(?:\ (?P<suffix>\w+))?)?
        """,
        re.VERBOSE,
    )

    @staticmethod
    def parse_num(text: str) -> Tuple[int, int]:
        if text == "":
            return 0, 0

        mo = Amendement._NUM_RE.match(text)
        if mo is None:
            raise ValueError(f"Cannot parse amendement number '{text}'")
        elif mo.group("prefix") in ["A-", "B-", "COORD-"]:
            raise ValueError(
                f"Cannot parse amendement number '{text}' (second deliberation)"
            )
        num = int(mo.group("num"))
        if mo.group("rect") is None:
            rectif = 0
        else:
            suffix = mo.group("suffix")
            if suffix is None:
                rectif = 1
            else:
                if suffix in ADJECTIFS_MULTIPLICATIFS:
                    rectif = ADJECTIFS_MULTIPLICATIFS[suffix]
                else:
                    raise ValueError(f"Cannot parse amendement number '{text}'")
        return (num, rectif)

    @reify
    def gouvernemental(self) -> bool:
        return self.auteur == "LE GOUVERNEMENT"

    @reify
    def is_withdrawn(self) -> bool:
        if not self.sort:
            return False
        return "retiré" in self.sort.lower()

    @reify
    def is_tombé(self) -> bool:
        if not self.sort:
            return False
        return self.sort.lower() == "tombé"

    @reify
    def is_irrecevable(self) -> bool:
        if not self.sort:
            return False
        return "irrecevable" in self.sort.lower()

    @reify
    def is_abandoned_before_seance(self) -> bool:
        if not self.sort:
            return False
        return self.is_irrecevable or self.is_withdrawn

    @reify
    def is_abandoned_during_seance(self) -> bool:
        if not self.sort:
            return False
        return self.is_tombé or self.is_withdrawn

    @reify
    def is_abandoned(self) -> bool:
        return self.is_abandoned_before_seance or self.is_abandoned_during_seance

    @reify
    def is_displayable(self) -> bool:
        return (
            bool(self.user_content.avis) or self.gouvernemental
        ) and not self.is_abandoned

    @property
    def is_sous_amendement(self) -> bool:
        return self.parent_pk is not None
    
    
    @property
    def discussion_commune(self) -> bool:
        return self.id_discussion_commune is not None
    
    @property
    def all_discussion_communes(self) -> List["Amendement"]:
        return sorted(self._set_of_all_discussion_communes )
    
    @property
    def _set_of_all_discussion_communes(self) -> Set["Amendement"]:
        return (
            self.lecture.discussion_communes_map[self.num]
            - self.lecture.abandoned_amendements
            - {self} 
        )
    
    @property
    def first_discussion_commune_num(self) -> Optional[int]:
        if self.id_discussion_commune is None:
            return None
        return next(amdt.num for amdt in sorted(self.lecture.discussion_communes_map[self.num]))
    
    @property
    def _set_of_displayable_discussion_commune(self) -> Set["Amendement"]:
        return (
            self._set_of_all_discussion_communes
            - self.lecture.not_displayable_amendements
            - set(self.location.batch.amendements if self.location.batch else [])
        )
        
    @property
    def displayable_discussion_commune(self) -> List["Amendement"]:
        return list(self._set_of_displayable_discussion_commune)

    

    @property
    def identique(self) -> bool:
        return self.id_identique is not None

    @property
    def all_identiques(self) -> List["Amendement"]:
        return sorted(self._set_of_all_identiques)

    @property
    def _set_of_all_identiques(self) -> Set["Amendement"]:
        return (
            self.lecture.identiques_map[self.num]
            - self.lecture.abandoned_amendements
            - {self} 
        )

    @property
    def first_identique_num(self) -> Optional[int]:
        if self.id_identique is None:
            return None
        return next(amdt.num for amdt in sorted(self.lecture.identiques_map[self.num]))

    @property
    def _set_of_displayable_identiques(self) -> Set["Amendement"]:
        return (
            self._set_of_all_identiques
            - self.lecture.not_displayable_amendements
            - set(self.location.batch.amendements if self.location.batch else [])
        )

    @property
    def displayable_identiques(self) -> List["Amendement"]:
        return list(self._set_of_displayable_identiques)

    @property
    def similaires(self) -> List["Amendement"]:
        return sorted(self._set_of_similaires)

    @property
    def _set_of_similaires(self) -> Set["Amendement"]:
        similaires = self.lecture.similaires_map[self.num]
        return {
            amdt
            for amdt in similaires
            if (amdt.num != self.num and amdt.is_displayable)
        }

    def reponse_similaire(self, other: "Amendement") -> bool:
        return self.user_content.similaire(other.user_content)

    @property
    def displayable_identiques_are_similaires(self) -> bool:
        return self._set_of_displayable_identiques == self._set_of_similaires

    def grouped_displayable_children(
        self,
    ) -> Iterable[Tuple[GroupingKey, List["Amendement"]]]:
        return self.article.group_amendements(
            amdt for amdt in self.children if amdt.is_displayable
        )

    @property
    def table_name(self) -> str:
        if self.location.shared_table:
            return self.location.shared_table.titre or ""
        elif self.location.user_table:
            return (
                self.location.user_table.user.name
                or self.location.user_table.user.email
            )
        elif self.location.date_dossier_de_banc:
            return DOSSIER_DE_BANC
        else:
            return ""

    @property
    def table_name_with_email(self) -> str:
        if self.location.shared_table:
            return self.location.shared_table.titre or ""
        elif self.location.user_table:
            return str(self.location.user_table.user)  # Contains email.
        elif self.location.date_dossier_de_banc:
            return DOSSIER_DE_BANC
        else:
            return ""

    @property
    def position_banc_as_int(self) -> int:
        """
        0 -> l'amendement n'a jamais été dans le dossier de banc
        1 -> l'amenedemnt a été dans le dossier de banc
        2 -> l'amendement est uniquement dans le dossier de banc
        """
        if self.location.date_dossier_de_banc:
            return 2
        if self.location.has_ever_been_on_dossier_de_banc:
            return 1
        else:
            return 0

    @property
    def alt_message_for_position(self) -> Optional[str]:
        if self.position_banc_as_int != 1:
            return None
        if self.location.shared_table:
            return f"L'amendement a été transféré de la corbeille \
« {DOSSIER_DE_BANC} » vers la corbeille « {self.table_name} »"
        if self.location.user_table:
            return f"L'amendement a été transféré de la corbeille \
« {DOSSIER_DE_BANC} » vers l'espace de travail de l'utilisateur « {self.table_name} »"
        return f"L'amendement a été transféré de la corbeille \
« {DOSSIER_DE_BANC} » vers le dérouleur"

    @property
    def is_being_edited(self) -> bool:
        return bool(amendements_repository.get_last_activity_time(self.pk))

    @property
    def previous_amendement(self) -> Optional["Amendement"]:
        sorted_amendements: List[Amendement] = sorted(self.article.amendements)
        previous_index = sorted_amendements.index(self) - 1
        if previous_index < 0:
            return None
        return sorted_amendements[previous_index]

    @property
    def next_amendement(self) -> Optional["Amendement"]:
        sorted_amendements: List[Amendement] = sorted(self.article.amendements)
        next_index = sorted_amendements.index(self) + 1
        if next_index >= len(sorted_amendements):
            return None
        return sorted_amendements[next_index]

    def start_editing(self) -> None:
        if not self.location.user_table:
            return
        amendements_repository.start_editing(self.pk, self.location.user_table.user.pk)

    def stop_editing(self) -> None:
        amendements_repository.stop_editing(self.pk)

    def asdict(self) -> dict:
        result: Dict[str, Union[str, int, date]] = {
            "num": self.num,
            "rectif": self.rectif or "",
            "sort": self.sort or "",
            "matricule": self.matricule or "",
            "gouvernemental": self.gouvernemental,
            "auteur": self.auteur or "",
            "groupe": self.groupe or "",
            "expose": self.expose or "",
            "corps": self.corps or "",
            "resume": self.resume or "",
            "objet": self.user_content.objet or "",
            "avis": self.user_content.avis or "",
            "reponse": self.user_content.reponse or "",
            "comments": self.user_content.comments or "",
            "parent": self.parent and self.parent.num_disp or "",
            "chambre": str(self.lecture.chambre),
            "num_texte": self.lecture.texte.numero,
            "organe": self.lecture.organe,
            "legislature": self.lecture.texte.legislature or "",
            "session": self.lecture.texte.session_str or "",
            "article": self.article.format(),
            "article_titre": self.article.user_content.title or "",
            "article_order": self.article.sort_key_as_str,
            "position": self.position or "",
            "id_discussion_commune": self.id_discussion_commune or "",
            "id_identique": self.id_identique or "",
            "first_identique_num": self.first_identique_num or "",
            "alinea": self.alinea or "",
            "date_depot": self.date_depot or "",
            "affectation_email": (
                self.location.user_table and self.location.user_table.user.email or ""
            ),
            "affectation_name": (
                self.location.user_table and self.location.user_table.user.name or ""
            ),
            "affectation_box": (
                self.location.shared_table and self.location.shared_table.titre or ""
            ),
        }
        return result

    @property
    def is_modified(self) -> bool:
        # If amdt is abandoned we should not show it as
        # a modified amendement anymore
        if self.modified:
            return not self.is_abandoned and self.modified
        return False

    @property
    def can_be_filtered(self) -> bool:
        return bool(
            not self.is_abandoned_before_seance
            and (self.user_content.avis or self.gouvernemental)
        )

    @property
    def get_status_sort(self) -> Dict[str, str]:
        if self.is_abandoned_before_seance:
            if self.is_withdrawn:
                return SORT[1]
            elif self.is_irrecevable:
                return SORT[0]
        elif self.is_abandoned_during_seance:
            if self.is_withdrawn:
                return SORT[1]
            elif self.is_tombé:
                return SORT[2]
        elif self.gouvernemental:
            return SORT[3]
        return {}

    def can_be_transferred_directly(self, user: "User") -> bool:
        return bool(
            self.position_banc_as_int != 2
            and not self.is_being_edited
            and (
                not self.location.user_table
                or (self.location.user_table and self.location.user_table.user == user)
            )
        )
