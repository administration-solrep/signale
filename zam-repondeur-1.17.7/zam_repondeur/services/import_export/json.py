import logging
from collections import Counter
from typing import List, Optional, Set, Tuple

import ujson as json

from zam_repondeur.models import Amendement, Article, DBSession, Lecture, Team, User
from zam_repondeur.models.amendement import DOSSIER_DE_BANC
from zam_repondeur.models.events.import_export import (
    ImportDossierZipEnd,
    ResultatsImportJSON,
)

from .common import create_batches, import_amendement, unbatch_amendements


def import_json_async(
    json_content: str,
    lecture_pk: int,
    user_pk: int,
    import_global: bool = False,
    link_lecture: Optional[str] = None,
) -> Counter:
    user = DBSession.query(User).filter(User.pk == user_pk).one_or_none()
    lecture = Lecture.get_by_pk(lecture_pk)
    if not lecture:
        raise Exception("Import json async impossible de trouver la lecture")
    if not user:
        raise Exception("Import json async impossible de trouver l'utilisateur")
    team = (
        DBSession.query(Team).filter(Team.pk == lecture.dossier.team.pk).one_or_none()
    )
    if not team:
        raise Exception("Import json async impossible de trouver l'équipe")
    amendements = {
        amendement.num: amendement
        for amendement in DBSession.query(Amendement)
        .filter(Amendement.lecture_pk == lecture_pk)
        .all()
    }
    articles = {
        article.sort_key_as_str: article
        for article in DBSession.query(Article)
        .filter(Article.lecture_pk == lecture_pk)
        .all()
    }
    previous_reponse = ""
    counter = Counter(
        {
            "amendements": 0,
            "reponses": 0,
            "articles": 0,
            "reponses_errors": 0,
            "articles_errors": 0,
        }
    )
    backup = json.loads(json_content)
    batch_to_create: Set[Tuple[int, ...]] = set()

    for item in backup.get("amendements", []):
        import_amendement(
            None, lecture, amendements, item, counter, previous_reponse, team, user=user
        )
        if item.get("computed_batch", []):
            try:
                batch_to_create.add(tuple(int(num) for num in item["computed_batch"]))
            except ValueError:
                continue

    for batch in batch_to_create:
        amdts_batch: List[Amendement] = []
        for num in batch:
            amdt = lecture.find_amendement(num)
            if amdt is not None:
                amdts_batch.append(amdt)
        unbatch_amendements(None, amdts_batch, user=user)
        create_batches(None, amdts_batch, user=user)

    for item in backup.get("articles", []):
        try:
            sort_key_as_str = item["sort_key_as_str"]
        except KeyError:
            counter["articles_errors"] += 1
            continue

        article = articles.get(sort_key_as_str)
        if not article:
            logging.warning("Could not find article %r", item)
            counter["articles_errors"] += 1
            continue

        if "title" in item:
            article.user_content.title = item["title"]
        if "presentation" in item:
            article.user_content.presentation = item["presentation"]
        counter["articles"] += 1

    ResultatsImportJSON.create(lecture, None, counter, user=user)

    if import_global:
        ImportDossierZipEnd.create(
            dossier=lecture.dossier,
            user=user,
            lecture=str(lecture),
            counter=counter,
            link_lecture=link_lecture,
        )

    return counter


EXCLUDED_FIELDS = {"first_identique_num"}


def export_json(lecture: Lecture, filename: str,) -> Counter:
    counter = Counter({"amendements": 0, "articles": 0})
    with open(filename, "w", encoding="utf-8-sig") as file_:
        amendements = []
        for amendement in sorted(lecture.amendements):
            amendements.append(export_amendement_for_json(amendement))
            counter["amendements"] += 1
        articles = []
        for article in sorted(lecture.articles):
            articles.append(article.asdict())
            counter["articles"] += 1
        file_.write(
            json.dumps(
                {"amendements": amendements, "articles": articles},
                indent=4,
                default=str,  # type: ignore[call-arg] # noqa
            )
        )
    return counter


def export_amendement_for_json(amendement: Amendement) -> dict:
    data = {k: v for k, v in amendement.asdict().items() if k not in EXCLUDED_FIELDS}
    # Compute batch output
    if amendement.location.batch:
        data["computed_batch"] = [
            amdt.num for amdt in amendement.location.batch.amendements
        ]
    else:
        data["computed_batch"] = []
    if amendement.location.date_dossier_de_banc:
        data["affectation_box"] = DOSSIER_DE_BANC
    data[
        "has_ever_been_on_dossier_de_banc"
    ] = amendement.location.has_ever_been_on_dossier_de_banc
    return data
