from pyramid.httpexceptions import HTTPFound
from pyramid.request import Request
from pyramid.response import Response
from pyramid.view import view_config

from zam_repondeur.message import Message
from zam_repondeur.models.events.import_export import ReponsesImportees
from zam_repondeur.resources import ImportExportLecture
from zam_repondeur.services.import_export.csv import CSVImportError, import_csv


@view_config(
    context=ImportExportLecture,
    name="import_csv",
    request_method="POST",
    permission="active",
)
def upload_csv(context: ImportExportLecture, request: Request) -> Response:
    lecture = context.parent.model()
    user = request.user

    # Check permission user (admin or coordinator)
    if not user.is_admin and not lecture.dossier.team.is_coordinator(user):
        request.session.flash(
            Message(
                cls="danger",
                text="L’import de saisies est réservé aux personnes autorisées.",
            )
        )
        return HTTPFound(location=request.resource_url(context))

    next_url = request.resource_url(context.parent["amendements"])

    # We cannot just do `if not POST["reponses"]`, as FieldStorage does not want
    # to be cast to a boolean.
    if request.POST["reponses"] == b"":
        request.session.flash(
            Message(cls="warning", text="Veuillez d’abord sélectionner un fichier")
        )
        return HTTPFound(location=request.resource_url(context))

    try:
        counter = import_csv(
            request=request,
            reponses_file=request.POST["reponses"].file,
            lecture=lecture,
            amendements={
                amendement.num: amendement for amendement in lecture.amendements
            },
            team=lecture.dossier.team,
        )
    except CSVImportError as exc:
        request.session.flash(Message(cls="danger", text=str(exc)))
        return HTTPFound(location=next_url)

    if counter["reponses"]:
        request.session.flash(
            Message(
                cls="success",
                text=f"{counter['reponses']} réponse(s) chargée(s) avec succès",
            )
        )
        ReponsesImportees.create(lecture=lecture, request=request)

    if counter["reponses_errors"]:
        request.session.flash(
            Message(
                cls="warning",
                text=(
                    f"{counter['reponses_errors']} réponse(s) "
                    "n’ont pas pu être chargée(s). "
                    "Pour rappel, il faut que le fichier CSV contienne au moins "
                    "les noms de colonnes suivants « Num amdt », "
                    "« Avis du Gouvernement », « Objet amdt », « Réponse » "
                    "et « A été dans le Dossier de Banc »."
                ),
            )
        )

    return HTTPFound(location=next_url)
