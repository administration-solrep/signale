from typing import Optional

from zam_repondeur.models import Lecture
from zam_repondeur.services.fetch.an.dossiers.models import DossierRef, LectureRef

from .parseur import Parseur, ParseurAN
from .parseur_plf import ParseurPLF


def get_parseur(lecture: Lecture) -> Parseur:

    from zam_repondeur.services.data import repository

    dossier_ref: DossierRef = repository.get_opendata_dossier_ref(lecture.dossier.an_id)
    if not dossier_ref:
        return ParseurAN(lecture)

    titre_court: str = get_titre_court(
        dossier_ref, lecture.texte.numero, lecture.organe
    )

    if titre_court.startswith("PLF "):
        return ParseurPLF(lecture)

    return ParseurAN(lecture)


def get_titre_court(dossier_ref: DossierRef, numero: int, organe: str) -> str:
    # TODO Stocker le titre court du texte dans la table texte pour
    # ne pas avoir a allier le chercher
    # ou mettre en place un enum pour les type spécifique a l'AN :
    # PLF Projet de Loi de Finance
    # PLFR Projet de Loi de Finance Rectificative
    # PJLR Projet de loi de réglement des comptes

    lecture_ref: Optional[LectureRef] = _get_lecture_ref(dossier_ref, numero, organe)
    if lecture_ref:
        return lecture_ref.texte.titre_court
    return ""


def _get_lecture_ref(
    dossier_ref: DossierRef, numero: int, organe: str
) -> Optional[LectureRef]:

    for lecture_ref in dossier_ref.lectures:
        if lecture_ref.organe == organe and lecture_ref.texte.numero == numero:
            return lecture_ref
    return None
