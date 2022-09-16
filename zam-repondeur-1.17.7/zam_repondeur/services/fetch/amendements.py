import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, NamedTuple, Optional

from zam_repondeur.models import (
    Amendement,
    Article,
    Chambre,
    Lecture,
    get_one_or_create,
    get_one_or_none,
)
from zam_repondeur.models.amendement import UNBATCHING_SORTS
from zam_repondeur.models.division import SubDiv
from zam_repondeur.models.events.amendement import (
    AmendementIrrecevable,
    AmendementRectifie,
    AmendementTransfere,
    BatchUnset,
    CorpsAmendementModifie,
    ExposeAmendementModifie,
)
from zam_repondeur.models.events.lecture import (
    AmendementArticleUpdateUnbatched,
    AmendementSortUpdateUnbatched,
)

logger = logging.getLogger(__name__)


# When trying to discover amendements published but not yet included in the list,
# we can't try all possible numbers, so we'll stop after a string of 404s
MAX_404 = 30


class Source:
    @staticmethod
    def update_attributes(amendement: Amendement, **values: Any) -> None:
        for name, value in values.items():
            if getattr(amendement, name) != value:
                setattr(amendement, name, value)

    @staticmethod
    def update_rectif(amendement: Amendement, rectif: int) -> None:
        if rectif != amendement.rectif:
            AmendementRectifie.create(amendement=amendement, rectif=rectif)

    @staticmethod
    def update_sort(amendement: Amendement, sort: str) -> None:

        if sort != amendement.sort:
            unbatching_sorts = [
                key for key in UNBATCHING_SORTS.keys() if key in sort.lower()
            ]
            if amendement.location.batch and unbatching_sorts:
                key = unbatching_sorts[0]
                status = UNBATCHING_SORTS[key]
                AmendementSortUpdateUnbatched.create(
                    lecture=amendement.lecture,
                    amdt_num=f"{amendement.num}",
                    status=status,
                )
                BatchUnset.create(amendement=amendement, request=None)
            if "irrecevable" in sort.lower():
                AmendementIrrecevable.create(amendement=amendement, sort=sort)
                # Put the amendement back to the index?
                if amendement.location.user_table is not None:
                    AmendementTransfere.create(
                        amendement=amendement,
                        old_value=str(amendement.location.user_table.user),
                        new_value="",
                    )
                    amendement.location.user_table = None
            else:
                amendement.sort = sort

    @staticmethod
    def update_corps(amendement: Amendement, corps: str) -> None:
        if corps != amendement.corps:
            CorpsAmendementModifie.create(amendement=amendement, corps=corps)

    @staticmethod
    def update_expose(amendement: Amendement, expose: str) -> None:
        if expose != amendement.expose:
            ExposeAmendementModifie.create(amendement=amendement, expose=expose)


class FetchResult(NamedTuple):
    amendements: List[Amendement]
    created: int
    errored: List[str]

    @classmethod
    def create(
        cls,
        amendements: List[Amendement] = [],
        created: int = 0,
        errored: List[str] = [],
    ) -> "FetchResult":
        return cls(amendements=amendements, created=created, errored=errored)

    def __add__(self: "FetchResult", other: object) -> "FetchResult":
        if not isinstance(other, FetchResult):
            raise TypeError
        return FetchResult(
            amendements=self.amendements + other.amendements,
            created=self.created + other.created,
            errored=self.errored + other.errored,
        )


class CollectedChanges(NamedTuple):
    """
    Changes found by the collect phase
    """

    derouleur_fetch_success: bool
    position_changes: Dict[int, Optional[int]]
    actions: List["Action"]
    unchanged: List[int]
    errored: List[str]

    @classmethod
    def create(
        cls,
        derouleur_fetch_success: bool = True,
        position_changes: Optional[Dict[int, Optional[int]]] = None,
        actions: Optional[List["Action"]] = None,
        unchanged: Optional[List[int]] = None,
        errored: Optional[List[str]] = None,
    ) -> "CollectedChanges":
        if position_changes is None:
            position_changes = {}
        if actions is None:
            actions = []
        if unchanged is None:
            unchanged = []
        if errored is None:
            errored = []
        return cls(
            derouleur_fetch_success, position_changes, actions, unchanged, errored
        )


class Action(ABC):
    @abstractmethod
    def apply(self, lecture: Lecture) -> FetchResult:
        pass


class CreateOrUpdateAmendement(Action):
    def __init__(
        self,
        subdiv: SubDiv,
        parent_num_raw: str,
        rectif: int,
        position: Optional[int],
        id_discussion_commune: Optional[int],
        id_identique: Optional[int],
        matricule: str,
        groupe: str,
        auteur: str,
        mission_titre: Optional[str],
        mission_titre_court: Optional[str],
        corps: str,
        expose: str,
        sort: str,
    ):
        self.subdiv = subdiv
        self.parent_num_raw = parent_num_raw
        self.rectif = rectif
        self.position = position
        self.id_discussion_commune = id_discussion_commune
        self.id_identique = id_identique
        self.matricule = matricule
        self.groupe = groupe
        self.auteur = auteur
        self.mission_titre = mission_titre
        self.mission_titre_court = mission_titre_court
        self.corps = corps
        self.expose = expose
        self.sort = sort

    def _get_article(self, lecture: Lecture) -> Article:
        article: Article
        created: bool
        article, created = get_one_or_create(
            Article,
            lecture=lecture,
            type=self.subdiv.type_,
            num=self.subdiv.num,
            mult=self.subdiv.mult,
            pos=self.subdiv.pos,
        )
        return article

    def _get_parent(self, lecture: Lecture, article: Article) -> Optional[Amendement]:
        parent_num, parent_rectif = Amendement.parse_num(self.parent_num_raw)
        if not parent_num:
            return None
        parent: Optional[Amendement]
        parent, _ = get_one_or_none(Amendement, lecture=lecture, num=parent_num,)
        return parent


class CreateAmendement(CreateOrUpdateAmendement):
    def __init__(self, num: int, **kwargs: Any):
        super().__init__(**kwargs)
        self.num = num

    def __repr__(self) -> str:
        return f"<CreateAmendement(num={self.num})>"

    def apply(self, lecture: Lecture) -> FetchResult:
        article = self._get_article(lecture)
        parent = self._get_parent(lecture, article)

        amendement = Amendement.create(
            lecture=lecture,
            article=article,
            parent=parent,
            position=self.position,
            num=self.num,
            rectif=self.rectif,
            id_discussion_commune=self.id_discussion_commune,
            id_identique=self.id_identique,
            matricule=self.matricule,
            groupe=self.groupe,
            auteur=self.auteur,
            mission_titre=self.mission_titre,
            mission_titre_court=self.mission_titre_court,
            corps=self.corps,
            expose=self.expose,
            sort=self.sort,
        )

        return FetchResult.create(amendements=[amendement], created=1)


class UpdateAmendement(CreateOrUpdateAmendement):
    def __init__(self, amendement_num: int, **kwargs: Any):
        super().__init__(**kwargs)
        self.amendement_num = amendement_num

    def __repr__(self) -> str:
        return f"<UpdateAmendement(num={self.amendement_num})>"

    def apply(self, lecture: Lecture) -> FetchResult:
        amendement = lecture.find_amendement(self.amendement_num)
        if amendement is None:
            return FetchResult.create(errored=[str(self.amendement_num)])

        article = self._get_article(lecture)
        parent = self._get_parent(lecture, article)

        if amendement.location.batch and amendement.article.pk != article.pk:
            AmendementArticleUpdateUnbatched.create(
                lecture=amendement.lecture,
                amdt_num=f"{amendement.num}",
                article_num=f"{article._num_disp}",
            )
            BatchUnset.create(amendement=amendement, request=None)

        position = self.position
        if lecture.chambre == Chambre.AN and not self.position:
            # On ne passe pas la valaeur de la position a None
            # pour les amendements AN
            position = amendement.position

        Source.update_rectif(amendement, self.rectif)
        Source.update_sort(amendement, self.sort)
        Source.update_corps(amendement, self.corps)
        Source.update_expose(amendement, self.expose)
        Source.update_attributes(
            amendement,
            article=article,
            parent=parent,
            position=position,
            id_discussion_commune=self.id_discussion_commune,
            id_identique=self.id_identique,
            matricule=self.matricule,
            groupe=self.groupe,
            auteur=self.auteur,
            mission_titre=self.mission_titre,
            mission_titre_court=self.mission_titre_court,
        )

        return FetchResult.create(amendements=[amendement])


class RemoteSource(Source):
    def __init__(self, prefetching_enabled: bool = True):
        self.prefetching_enabled = prefetching_enabled

    def prepare(self, lecture: Lecture) -> None:
        pass

    def fetch(self, lecture: Lecture) -> FetchResult:
        changes = self.collect_changes(lecture)
        return self.apply_changes(lecture, changes)

    def collect_changes(
        self, lecture: Lecture, max_404: int = MAX_404
    ) -> CollectedChanges:
        raise NotImplementedError()

    def apply_changes(self, lecture: Lecture, changes: CollectedChanges) -> FetchResult:
        raise NotImplementedError()

    @classmethod
    def get_remote_source_for_chambre(
        cls, chambre: Chambre, prefetching_enabled: bool = True
    ) -> "RemoteSource":
        from zam_repondeur.services.fetch.an.amendements import AssembleeNationale
        from zam_repondeur.services.fetch.senat.amendements import Senat

        if chambre == Chambre.AN:
            return AssembleeNationale(prefetching_enabled=prefetching_enabled)
        if chambre == Chambre.SENAT:
            return Senat(prefetching_enabled=prefetching_enabled)
        raise NotImplementedError
