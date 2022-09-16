from datetime import datetime, timedelta
from itertools import groupby
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    desc,
    func,
    select,
)
from sqlalchemy.orm import Query, column_property, joinedload, relationship

from zam_repondeur.decorator import reify

from .amendement import Amendement
from .article import Article
from .base import Base, DBSession
from .chambre import Chambre
from .division import SubDiv
from .dossier import Dossier
from .events.base import Event, LastEventMixin
from .organe import ORGANE_SENAT, ORGANES_SEANCE_PUBLIQUE
from .phase import Phase
from .texte import Texte

class Lecture(Base, LastEventMixin):
    __tablename__ = "lectures"
    __table_args__ = (
        Index(
            "ix_lectures__texte_pk__partie__organe",
            "texte_pk",
            "partie",
            "organe",
            unique=False,
        ),
    )

    pk = Column(Integer, primary_key=True)
    created_at: datetime = Column(DateTime)

    dossier_pk = Column(Integer, ForeignKey("dossiers.pk"))
    dossier: "Dossier" = relationship("Dossier", back_populates="lectures")

    texte_pk = Column(Integer, ForeignKey("textes.pk"))
    texte: Texte = relationship(Texte, back_populates="lectures")

    partie: Optional[int] = Column(Integer, nullable=True)  # only for PLF

    phase: Phase = Column(Enum(Phase), nullable=False)
    chambre: Chambre = Column(Enum(Chambre))
    organe: str = Column(Text)

    titre: str = Column(Text)

    update: bool = Column(Boolean, default=True, nullable=False)

    alert_flag: bool = Column(Boolean, default=False, nullable=False)

    amendements: List[Amendement] = relationship(
        Amendement,
        order_by=(Amendement.position, Amendement.num),
        back_populates="lecture",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    nb_amendements = column_property(
        select([func.count(Amendement.pk)])
        .where(Amendement.lecture_pk == pk)
        .correlate_except(Amendement)
    )

    articles: List[Article] = relationship(
        Article,
        back_populates="lecture",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    events = relationship(
        "Event",
        order_by="Event.created_at.desc()",
        cascade="all, delete-orphan",
        backref="lecture",
    )

    missions_senat = relationship(
        "MissionSenat", back_populates="lecture", cascade="all, delete-orphan"
    )

    __repr_keys__ = ("pk", "chambre", "organe", "partie")

    def __lt__(self, other: "Lecture") -> bool:
        return self.sort_key < other.sort_key

    @property
    def sort_key(self) -> Tuple[datetime, bool, int]:
        return (
            self.texte.date_depot,
            self.organe in ORGANES_SEANCE_PUBLIQUE,
            self.partie or 0,
        )

    @property
    def journal_events(self) -> List[Event]:
        # Import des events ici pour éviter les boucle d'import
        from .events.lecture import LectureJournalEvent

        query = (
            DBSession.query(LectureJournalEvent)
            .filter(LectureJournalEvent.lecture_pk == self.pk)
            .order_by(desc(LectureJournalEvent.created_at))
        )
        events: List[Event] = [evt for evt in query.all()]
        return events

    @property
    def import_export_events(self) -> List[Event]:
        # Import des events ici pour éviter les boucle d'import
        from .events.import_export import ImportExportLectureEvent

        query = (
            DBSession.query(ImportExportLectureEvent)
            .filter(ImportExportLectureEvent.lecture_pk == self.pk)
            .order_by(desc(ImportExportLectureEvent.created_at))
        )
        events: List[Event] = [evt for evt in query.all()]
        return events

    def __str__(self) -> str:
        return ", ".join(
            [
                self.format_chambre(),
                self.format_session_or_legislature(),
                self.format_organe(),
                self.format_num_lecture(),
                self.format_texte(),
            ]
        )

    def format_chambre(self) -> str:
        return str(self.chambre.value)

    def format_session_or_legislature(self) -> str:
        if self.chambre == Chambre.AN:
            return f"{self.texte.legislature}e législature"
        else:
            return f"session {self.texte.session_str}"

    def format_organe(self) -> str:
        from zam_repondeur.services.data import repository  # avoid circular imports

        result: str = self.organe
        organe_data = repository.get_opendata_organe(self.organe)
        if organe_data is not None:
            result = organe_data["libelle"]
        return self.rewrite_organe(result)

    def rewrite_organe(self, label: str) -> str:
        if label in {
            "Assemblée nationale de la 14ème législature",
            "Assemblée nationale de la 15ème législature",
            "Assemblée nationale de la 16ème législature",
            "Sénat ( 5ème République )",
        }:
            return "Séance publique"
        if label.startswith("Commission"):
            return label
        if label:
            return f"Commission des {label.lower()}"
        return "Commissions"

    def format_num_lecture(self) -> str:
        num_lecture, _ = self.titre.split(" – ", 1)
        return str(num_lecture.strip())

    def format_texte(self) -> str:
        if self.partie == 1:
            partie = " (1re partie)"
        elif self.partie == 2:
            partie = " (2nde partie)"
        else:
            partie = ""
        return f"texte nº\u00a0{self.texte.numero}{partie}"

    @property
    def is_commission(self) -> bool:
        return self.organe not in ORGANES_SEANCE_PUBLIQUE

    @property
    def has_missions(self) -> bool:
        return bool(self.partie and self.partie == 2)

    @property
    def displayable(self) -> bool:
        return any(amd.is_displayable for amd in self.amendements)

    def refreshable_for(self, kind: str, settings: Dict[str, str]) -> bool:
        return bool(
            datetime.utcnow().date() - self.texte.date_depot
            <= timedelta(days=int(settings.get(f"zam.refresh.{kind}") or 30))
        )

    @classmethod
    def all(cls) -> List["Lecture"]:
        lectures: List["Lecture"] = (
            DBSession.query(cls)
            .options(joinedload("amendements"))
            .order_by(desc(cls.created_at))
            .all()
        )
        return lectures

    @classmethod
    def get_by_pk(cls, pk: int) -> Optional["Lecture"]:
        lecture: Optional["Lecture"] = DBSession.query(cls).get(pk)
        return lecture

    @classmethod
    def get(
        cls,
        slug: str,
        chambre: Chambre,
        session_or_legislature: str,
        num_texte: int,
        partie: Optional[int],
        organe: str,
        *options: Any,
    ) -> Optional["Lecture"]:
        query = (
            DBSession.query(cls)
            .join(Texte)
            .join(Dossier)
            .filter(
                cls.chambre == chambre,
                cls.partie == partie,
                cls.organe == organe,
                Texte.chambre == chambre,
                Texte.numero == num_texte,
                Dossier.slug == slug,
            )
            .options(*options)
        )
        if chambre == Chambre.AN:
            query = query.filter(Texte.legislature == int(session_or_legislature))
        elif chambre == Chambre.SENAT:
            query = query.filter(
                Texte.session == int(session_or_legislature.split("-")[0])
            )
        else:
            raise ValueError("Invalid value for chambre")
        res: Optional["Lecture"] = query.first()
        return res

    @classmethod
    def exists(
        cls,
        dossier: "Dossier",
        texte: "Texte",
        partie: Optional[int],
        phase: Phase,
        chambre: Chambre,
        organe: str,
    ) -> bool:
        query = cls._query_helper(
            dossier=dossier,
            texte=texte,
            partie=partie,
            phase=phase,
            chambre=chambre,
            organe=organe,
        )
        res: bool = DBSession.query(query.exists()).scalar()
        return res

    @classmethod
    def create(
        cls,
        phase: Phase,
        texte: "Texte",
        titre: str,
        organe: str,
        dossier: "Dossier",
        partie: Optional[int] = None,
    ) -> "Lecture":
        now = datetime.utcnow()
        chambre = texte.chambre
        lecture = cls(
            phase=phase,
            chambre=chambre,
            texte=texte,
            titre=titre,
            organe=organe,
            dossier=dossier,
            partie=partie,
            created_at=now,
        )
        DBSession.add(lecture)
        return lecture

    @classmethod
    def create_from_ref(
        cls, lecture_ref: Any, dossier: "Dossier", texte: "Texte"
    ) -> "Lecture":
        lecture = cls.create(
            dossier=dossier,
            phase=lecture_ref.phase,
            organe=lecture_ref.organe,
            texte=texte,
            partie=lecture_ref.partie,
            titre=lecture_ref.titre,
        )
        return lecture

    @classmethod
    def get_from_ref(
        cls, lecture_ref: Any, dossier: "Dossier", texte: "Texte"
    ) -> Optional["Lecture"]:
        """
        Find an existing Lecture matching a LectureRef
        """

        lecture: Optional["Lecture"]

        # We don't use the Texte for matching, as the Lecture may have
        # been created too early, with a temporary one (texte déposé
        # vs. texte de la commission).
        query = cls._query_helper(
            dossier=dossier,
            partie=lecture_ref.partie,
            phase=lecture_ref.phase,
            chambre=lecture_ref.chambre,
            organe=lecture_ref.organe,
        )
        lecture = query.one_or_none()
        if lecture is not None:
            return lecture

        # In the case of Sénat commission, also try matching without the organe, as the
        # Lecture may have been created from scraping data, without this information.
        if lecture_ref.chambre == Chambre.SENAT and lecture_ref.organe != ORGANE_SENAT:
            query = cls._query_helper(
                dossier=dossier,
                partie=lecture_ref.partie,
                phase=lecture_ref.phase,
                chambre=lecture_ref.chambre,
            )
            query = query.filter(cls.organe != ORGANE_SENAT)  # NOT séance publique
            lecture = query.one_or_none()
            return lecture

        return None

    @classmethod
    def _query_helper(
        cls,
        dossier: "Dossier",
        partie: Optional[int],
        phase: Phase,
        chambre: Chambre,
        texte: Optional["Texte"] = None,
        organe: Optional[str] = None,
    ) -> Query:
        query = DBSession.query(cls).filter(
            cls.dossier == dossier,
            cls.partie == partie,
            cls.phase == phase,
            cls.chambre == chambre,
        )
        if texte is not None:
            query = query.filter(cls.texte == texte)
        if organe is not None:
            query = query.filter(cls.organe == organe)
        return query

    @property
    def elligible_mission_senat(self) -> bool:
        return self.chambre == Chambre.SENAT and self.partie is not None

    @property
    def url_key(self) -> str:
        if self.partie is not None:
            partie = f"-{self.partie}"
        else:
            partie = ""
        return ".".join(
            [
                self.chambre.name.lower(),
                self._session_or_legislature,
                f"{self.texte.numero}{partie}",
                self.organe,
            ]
        )

    @property
    def zip_key(self) -> str:
        if self.partie is not None:
            partie = f"-{self.partie}"
        else:
            partie = ""
        values = [
            self.chambre.name.lower(),
            self._session_or_legislature,
            f"{self.texte.numero}{partie}",
        ]
        if self.organe:
            values.append(self.organe)
        return "-".join(values)

    @property
    def _session_or_legislature(self) -> str:
        if self.texte.chambre == Chambre.AN:
            return str(self.texte.legislature)
        assert self.texte.session_str is not None  # nosec (mypy hint)
        return self.texte.session_str

    def find_article(self, subdiv: SubDiv) -> Optional[Article]:
        article: Article
        for article in self.articles:
            if article.matches(subdiv):
                return article
        return None

    def find_or_create_article(self, subdiv: SubDiv) -> Tuple[Article, bool]:
        article = self.find_article(subdiv)
        created = False
        if article is None:
            article = Article.create(
                lecture=self,
                type=subdiv.type_,
                num=subdiv.num,
                mult=subdiv.mult,
                pos=subdiv.pos,
            )
            created = True
        return article, created

    def find_amendement(self, num: int) -> Optional[Amendement]:
        amendement: Amendement
        for amendement in self.amendements:
            if amendement.num == num:
                return amendement
        return None

    def find_or_create_amendement(
        self, num: int, article: Article
    ) -> Tuple[Amendement, bool]:
        amendement = self.find_amendement(num)
        created = False
        if amendement is None:
            amendement = Amendement.create(lecture=self, article=article, num=num)
            created = True
        return amendement, created

    @reify
    def abandoned_amendements(self) -> Set[Amendement]:
        return {amdt for amdt in self.amendements if amdt.is_abandoned}

    @reify
    def not_displayable_amendements(self) -> Set[Amendement]:
        return {amdt for amdt in self.amendements if not amdt.is_displayable}

    @reify
    def identiques_map(self) -> Dict[int, Set[Amendement]]:
        return self._build_map(key=lambda amdt: amdt.id_identique or uuid4().int)
    
    @reify
    def discussion_communes_map(self) -> Dict[int, Set[Amendement]]:
        return self._build_map(key=lambda amdt: amdt.id_discussion_commune or uuid4().int)

    @reify
    def similaires_map(self) -> Dict[int, Set[Amendement]]:
        return self._build_map(key=lambda amdt: amdt.user_content.reponse_hash or "")

    def _build_map(self, key: Callable) -> Dict[int, Set[Amendement]]:
        res = {}
        for _, g in groupby(sorted(self.amendements, key=key), key=key):
            identiques = set(g)
            discussion_communes = set(g)
            for amdt in identiques:
                res[amdt.num] = identiques
            for amdt in discussion_communes:
                res[amdt.num] = discussion_communes
        return res
    

    def set_fetch_progress(self, current: int, total: int) -> None:
        from zam_repondeur.services.progress import repository  # avoid circular imports

        return repository.set_fetch_progress(str(self.pk), current, total)

    def reset_fetch_progress(self) -> None:
        from zam_repondeur.services.progress import repository  # avoid circular imports

        return repository.reset_fetch_progress(str(self.pk))

    def get_fetch_progress(self) -> Optional[Dict[str, int]]:
        from zam_repondeur.services.progress import repository  # avoid circular imports

        return repository.get_fetch_progress(str(self.pk))

    def get_dossier_de_banc_stats(self) -> Dict[int, int]:
        stats = {0: 0, 1: 0, 2: 0}
        for amendement in self.amendements:
            stats[amendement.position_banc_as_int] += 1
        return stats


HYPHEN_SPLIT = (
    "budget annexe",
    "comptes spécial",
    "compte spécial",
    "articles non rattachés",
)


class MissionSenat(Base):
    __tablename__ = "missions_senat"
    __table_args__ = (
        Index(
            "ix_missions_senat_lecture_pk__id_texte",
            "lecture_pk",
            "id_texte",
            unique=True,
        ),
        UniqueConstraint("id_texte", "lecture_pk"),
    )

    pk = Column(Integer, primary_key=True)
    created_at: datetime = Column(DateTime)

    lecture_pk = Column(Integer, ForeignKey("lectures.pk"))
    lecture: "Lecture" = relationship("Lecture", back_populates="missions_senat")

    titre: str = Column(Text)

    id_texte: int = Column(Integer)

    def __lt__(self, other: "MissionSenat") -> bool:
        return self.sort_key < other.sort_key

    @property
    def sort_key(self) -> Tuple[int, Optional[int], int]:
        return (
            int(self.lecture.texte.numero),
            self.lecture.partie,
            self.id_texte,
        )

    def __repr__(self) -> str:
        return f"<missionSenat {self.id_texte}:{self.titre_court} \
lecture_pk:{self.lecture.pk}>"

    def __str__(self) -> str:
        return f"Mission Senat {self.id_texte}:{self.titre_court} \
lecture_pk:{self.lecture.pk}"

    @classmethod
    def get(cls, lecture: "Lecture", id_texte: int) -> Optional["MissionSenat"]:
        mission_senat: "MissionSenat" = DBSession.query(cls).filter_by(
            lecture=lecture, id_texte=id_texte
        ).one_or_none()
        return mission_senat

    @classmethod
    def create(  # type: ignore
        cls, lecture, titre: str, id_texte: int,
    ) -> "MissionSenat":
        now = datetime.utcnow()
        mission_senat = cls(
            created_at=now, lecture=lecture, titre=titre, id_texte=id_texte,
        )
        return mission_senat

    @classmethod
    def get_url_missions_senat(cls, lecture: "Lecture") -> Optional[str]:
        if lecture.elligible_mission_senat:
            return f"http://www.senat.fr/amendements/{lecture.texte.session_str}\
/{lecture.texte.numero}/PLF-ids-techniques.csv"
        return None

    @reify
    def titre_court(self) -> str:
        if self.titre is None:
            return ""
        for hyphen_split in HYPHEN_SPLIT:
            if hyphen_split in self.titre.lower():
                return self.titre.split("-")[1].strip()
        if self.titre.startswith("Mission "):
            return self.titre.split("Mission ")[1].strip()
        return self.titre.strip()
