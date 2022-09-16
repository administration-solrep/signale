from typing import Any, Optional

from inscriptis import get_text

from zam_repondeur.models import Amendement
from zam_repondeur.models.amendement import DOSSIER_DE_BANC

# NB: dict key order is used for spreadsheet columns order (Python 3.6+)
FIELDS = {
    "article": "Num article",
    "article_titre": "Titre article",
    "num": "Num amdt",
    "rectif": "Rectif",
    "parent": "Parent (sous-amdt)",
    "computed_batch": "Allotissement",
    "auteur": "Auteur",
    "groupe": "Groupe",
    "gouvernemental": "Gouvernemental",
    "corps": "Corps amdt",
    "expose": "Exposé amdt",
    "first_identique_num": "Identique",
    "avis": "Avis du Gouvernement",
    "objet": "Objet amdt",
    "reponse": "Réponse",
    "comments": "Commentaires",
    "affectation_email": "Affectation (email)",
    "affectation_name": "Affectation (nom)",
    "affectation_box": "Affectation (Corbeille)",
    "sort": "Sort",
    "has_ever_been_on_dossier_de_banc": "A été dans le Dossier de Banc",
}


COLUMN_NAME_TO_FIELD = {col: attr for attr, col in FIELDS.items()}


def column_name_to_field(column_name: str) -> Optional[str]:
    return COLUMN_NAME_TO_FIELD.get(column_name)


HEADERS = FIELDS.values()


HTML_FIELDS = ["corps", "expose", "objet", "reponse", "comments"]

BOOL_FIELDS = ["has_ever_been_on_dossier_de_banc"]


def export_amendement_for_spreadsheet(amendement: Amendement) -> dict:
    data: dict = {k: v for k, v in amendement.asdict().items() if k in FIELDS}
    for field_name in HTML_FIELDS:
        if data[field_name] is not None:
            data[field_name] = html_to_text(data[field_name])
    # Compute batch output
    if amendement.location.batch:
        data["computed_batch"] = ",".join(
            f"{amdt.num}" for amdt in amendement.location.batch.amendements
        )
    else:
        data["computed_batch"] = ""
    if amendement.location.date_dossier_de_banc:
        data["affectation_box"] = DOSSIER_DE_BANC
    data[
        "has_ever_been_on_dossier_de_banc"
    ] = amendement.location.has_ever_been_on_dossier_de_banc

    return {k: convert_boolean(v) for k, v in data.items()}


def convert_boolean(value: Any) -> Any:
    if value is True:
        return "Oui"
    elif value is False:
        return "Non"
    else:
        return value


def html_to_text(html: str) -> str:
    text: str = get_text(html).strip()
    return text
