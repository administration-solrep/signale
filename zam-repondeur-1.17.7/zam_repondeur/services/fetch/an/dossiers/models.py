from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional

from zam_repondeur.models.chambre import Chambre
from zam_repondeur.models.phase import Phase
from zam_repondeur.models.texte import TypeTexte


@dataclass(eq=True, frozen=True)
class TexteRef:
    uid: str
    type_: TypeTexte
    chambre: Chambre
    legislature: Optional[int]
    numero: int
    titre_long: str
    titre_court: str
    date_depot: Optional[date]

    @property
    def session(self) -> Optional[int]:
        if self.chambre == Chambre.AN:
            return None
        if not self.date_depot:
            raise NotImplementedError
        # The session changes the first working day of October.
        if self.date_depot.month >= 10:
            return self.date_depot.year
        else:
            return self.date_depot.year - 1


@dataclass
class LectureRef:
    chambre: Chambre
    phase: Phase
    titre: str
    texte: TexteRef
    organe: str
    partie: Optional[int] = None

    @property
    def key(self) -> str:
        return f"{self.texte.uid}-{self.organe}-{self.partie or ''}"

    @property
    def label(self) -> str:
        if self.partie == 1:
            partie = " (première partie)"
        elif self.partie == 2:
            partie = " (seconde partie)"
        else:
            partie = ""
        return " – ".join(
            [self.chambre.value, self.titre, f"Texte Nº {self.texte.numero}{partie}"]
        )


MIN_DATE = date(1900, 1, 1)


DossierRefsByUID = Dict[str, "DossierRef"]


@dataclass
class DossierRef:
    uid: str
    titre: str
    slug: str
    an_url: str
    senat_url: Optional[str]
    lectures: List[LectureRef]
    titre_loi: Optional[str] = None
    urls_loi: Optional[dict[str, str]] = None
    is_plf: bool = False

    def matches(self, other: "DossierRef") -> bool:
        if self.an_url and self.normalized_an_url == other.normalized_an_url:
            return True
        if self.senat_url and self.normalized_senat_url == other.normalized_senat_url:
            return True
        return False

    @property
    def normalized_an_url(self) -> str:
        return self.an_url.replace("/dossiers/alt/", "/dossiers/")

    @property
    def normalized_senat_url(self) -> Optional[str]:
        if self.senat_url is None:
            return None
        return self.senat_url.replace("http://", "https://")

    @property
    def senat_dossier_id(self) -> Optional[str]:
        """
        "http://www.senat.fr/dossier-legislatif/pjl18-677.html" -> "pjl18-677"
        """
        if self.senat_url is None:
            return None
        last_part = self.senat_url.split("/")[-1]
        suffix = len(".html")
        return last_part[:-suffix]
