import logging
from collections import Counter
from typing import Dict, List, Optional

from pyramid.request import Request

from zam_repondeur.models import (
    Amendement,
    Batch,
    Lecture,
    SharedTable,
    Team,
    User,
    get_one_or_create,
)
from zam_repondeur.models.amendement import DOSSIER_DE_BANC, ReponseTuple
from zam_repondeur.models.events.amendement import (
    AmendementTransfere,
    AvisAmendementModifie,
    BatchSet,
    BatchUnset,
    CommentsAmendementModifie,
    ObjetAmendementModifie,
    ReponseAmendementModifiee,
    TransfertDossierDeBanc,
)
from zam_repondeur.services.clean import clean_html
from zam_repondeur.utils import normalize_avis, normalize_num, normalize_reponse


def import_amendement(
    request: Optional[Request],
    lecture: Lecture,
    amendements: Dict[int, Amendement],
    item: dict,
    counter: Counter,
    previous_reponse: str,
    team: Team,
    user: Optional[User] = None,
) -> None:
    # On commence par incrémenter le compte d'amendements
    counter["amendements"] += 1

    try:
        numero = item["num"]
        avis = item["avis"] or ""
        objet = item["objet"] or ""
        reponse = item["reponse"] or ""
        has_ever_been_on_dossier_de_banc = (
            item["has_ever_been_on_dossier_de_banc"] or False
        )

    except KeyError:
        counter["reponses_errors"] += 1
        return

    try:
        num = normalize_num(numero)
    except ValueError:
        logging.warning("Invalid amendement number %r", numero)
        counter["reponses_errors"] += 1
        return

    amendement = amendements.get(num)
    if not amendement:
        logging.warning("Could not find amendement number %r", num)
        counter["reponses_errors"] += 1
        return

    changed: bool = False
    avis = normalize_avis(avis)
    if avis != (amendement.user_content.avis or ""):
        AvisAmendementModifie.create(
            amendement=amendement, avis=avis, request=request, user=user
        )
        changed = True

    objet = clean_html(objet)
    if objet != (amendement.user_content.objet or ""):
        ObjetAmendementModifie.create(
            amendement=amendement, objet=objet, request=request, user=user
        )
        changed = True

    reponse = clean_html(normalize_reponse(reponse, previous_reponse))
    if reponse != (amendement.user_content.reponse or ""):
        ReponseAmendementModifiee.create(
            amendement=amendement, reponse=reponse, request=request, user=user
        )
        changed = True

    if "comments" in item:
        comments = clean_html(item["comments"])
        if comments != (amendement.user_content.comments or ""):
            CommentsAmendementModifie.create(
                amendement=amendement, comments=comments, request=request, user=user
            )
            changed = True

    # Il y a eu au moins une réponse modifiée, on incrémente le compte des réponses
    if changed:
        counter["reponses"] += 1

    # Order matters:
    # first has_ever_been_on_dossier_de_banc flag
    # if amdt is on Dossier de Banc we bypass affectation_*
    # if there is a box *and* an email, the amendement will be
    # transfered to the box then to the user who has precedence.
    amendement.location.has_ever_been_on_dossier_de_banc = (
        has_ever_been_on_dossier_de_banc
    )
    dossier_de_banc = (
        "affectation_box" in item
        and item["affectation_box"].lower() == DOSSIER_DE_BANC.lower()
    )
    affectation_box = "affectation_box" in item and item["affectation_box"]
    affectation_email = "affectation_email" in item and item["affectation_email"]

    if dossier_de_banc:
        # Set du flag pour être sûr que la donnée sera cohérente
        amendement.location.has_ever_been_on_dossier_de_banc = True
        if not amendement.location.date_dossier_de_banc:
            TransfertDossierDeBanc.create(
                amendement=amendement, request=request, user=user
            )
    else:
        if affectation_box:
            _transfer_to_box_amendement_on_import(
                request, lecture, amendement, item, user
            )

        if affectation_email:
            _transfer_to_user_amendement_on_import(
                request, lecture, amendement, item, user
            )

    # Si aucune affection prévoir le transfert au dérouleur
    # depuis le Dossier de banc
    if not (affectation_box or affectation_email):
        if amendement.location.date_dossier_de_banc:
            _transfer_from_banc_to_derouleur(request, lecture, amendement, item, user)

    previous_reponse = reponse


def _transfer_from_banc_to_derouleur(
    request: Optional[Request],
    lecture: Lecture,
    amendement: Amendement,
    item: dict,
    user: Optional[User] = None,
) -> None:

    old = amendement.table_name_with_email
    new = ""

    amendement.location.shared_table = None
    amendement.location.user_table = None
    amendement.location.date_dossier_de_banc = None
    amendement.location.has_ever_been_on_dossier_de_banc = True

    AmendementTransfere.create(
        amendement=amendement, old_value=old, new_value=new, request=request, user=user
    )


def _transfer_to_box_amendement_on_import(
    request: Optional[Request],
    lecture: Lecture,
    amendement: Amendement,
    item: dict,
    user: Optional[User] = None,
) -> None:
    shared_table, created = get_one_or_create(
        SharedTable, titre=item["affectation_box"], lecture=lecture
    )

    if amendement.location.shared_table is shared_table:
        return

    old = amendement.table_name_with_email
    new = shared_table.titre

    amendement.location.shared_table = shared_table
    amendement.location.user_table = None
    amendement.location.date_dossier_de_banc = None

    AmendementTransfere.create(
        amendement=amendement, old_value=old, new_value=new, request=request, user=user
    )


def _transfer_to_user_amendement_on_import(
    request: Optional[Request],
    lecture: Lecture,
    amendement: Amendement,
    item: dict,
    request_user: Optional[User] = None,
) -> None:
    email = User.normalize_email(item["affectation_email"])

    if not User.email_is_well_formed(email):
        logging.warning("Invalid email address %r", email)
        return

    user, created = get_one_or_create(User, email=email)
    if created:
        affectation_name = User.normalize_name(item["affectation_name"])
        user.name = affectation_name if affectation_name != "" else email
        if lecture.dossier.team:
            user.teams.append(lecture.dossier.team)

    user_table = user.table_for(lecture)
    if amendement.location.user_table is user_table:
        return

    old = amendement.table_name_with_email
    new = str(user)

    amendement.location.user_table = user_table
    amendement.location.shared_table = None
    amendement.location.date_dossier_de_banc = None

    AmendementTransfere.create(
        amendement=amendement,
        old_value=old,
        new_value=new,
        request=request,
        user=request_user,
    )


def unbatch_amendements(
    request: Optional[Request],
    amendements: List[Amendement],
    user: Optional[User] = None,
) -> None:
    get_all_amendements = Batch.expanded_batches(amendements)
    for amendement in get_all_amendements:
        if amendement.location.batch:
            BatchUnset.create(amendement=amendement, request=request, user=user)


def create_batches(
    request: Optional[Request],
    amendements: List[Amendement],
    shared_reponse: Optional[ReponseTuple] = None,
    user: Optional[User] = None,
) -> None:
    batch = Batch.create()
    to_be_updated: List[Amendement] = []
    for amendement in amendements:
        if amendement.location.batch:
            BatchUnset.create(amendement=amendement, request=request, user=user)
        BatchSet.create(
            amendement=amendement,
            batch=batch,
            amendements_nums=[amendement.num for amendement in amendements],
            request=request,
            user=user,
        )
        if shared_reponse is not None:
            to_be_updated.append(amendement)
        else:
            reponse = amendement.user_content.as_tuple()
            if not reponse.is_empty:
                shared_reponse = reponse
            else:
                to_be_updated.append(amendement)

    modify_reponse(
        request, shared_reponse=shared_reponse, to_be_updated=to_be_updated, user=user
    )


def modify_reponse(
    request: Optional[Request],
    shared_reponse: Optional[ReponseTuple] = None,
    to_be_updated: List[Amendement] = [],
    user: Optional[User] = None,
    edit_avis: bool = True,
    edit_objet: bool = True,
    edit_reponse: bool = True,
    edit_comments: bool = True,
) -> None:
    if shared_reponse is not None and to_be_updated:
        for amendement in to_be_updated:
            if (
                edit_avis
                and (amendement.user_content.avis or "") != shared_reponse.avis
            ):
                AvisAmendementModifie.create(
                    amendement=amendement,
                    avis=shared_reponse.avis,
                    request=request,
                    user=user,
                )
            if (
                edit_objet
                and (amendement.user_content.objet or "") != shared_reponse.objet
            ):
                ObjetAmendementModifie.create(
                    amendement=amendement,
                    objet=shared_reponse.objet,
                    request=request,
                    user=user,
                )
            if (
                edit_reponse
                and (amendement.user_content.reponse or "") != shared_reponse.content
            ):
                ReponseAmendementModifiee.create(
                    amendement=amendement,
                    reponse=shared_reponse.content,
                    request=request,
                    user=user,
                )
            if (
                edit_comments
                and (amendement.user_content.comments or "") != shared_reponse.comments
            ):
                CommentsAmendementModifie.create(
                    amendement=amendement,
                    comments=shared_reponse.comments,
                    request=request,
                    user=user,
                )
