import os
import shutil
import uuid

from pyramid.httpexceptions import HTTPFound
from pyramid.request import Request
from pyramid.response import Response
from pyramid.view import view_config
from sqlalchemy.orm import joinedload

from zam_repondeur.message import Message
from zam_repondeur.models.events.import_export import ReponsesImporteesJSON
from zam_repondeur.resources import ImportExportLecture
from zam_repondeur.tasks.asynchrone import import_json_task


@view_config(
    context=ImportExportLecture,
    name="import_backup",
    request_method="POST",
    permission="active",
)
def upload_json(context: ImportExportLecture, request: Request) -> Response:
    lecture = context.parent.model(joinedload("articles"))
    user = request.user

    # Check permission user (admin or coordinator)
    if not user.is_admin and not lecture.dossier.team.is_coordinator(user):
        request.session.flash(
            Message(
                cls="danger",
                text="L’import de fichiers techniques structurés est \
réservé aux personnes autorisées.",
            )
        )
        return HTTPFound(location=request.resource_url(context))

    next_url = request.resource_url(context.parent["amendements"])

    # We cannot just do `if not POST["backup"]`, as FieldStorage does not want
    # to be cast to a boolean.
    if request.POST["backup"] == b"":
        request.session.flash(
            Message(cls="warning", text="Veuillez d’abord sélectionner un fichier")
        )
        return HTTPFound(location=request.resource_url(context))

    upload_folder = request.registry.settings["zam.uploads_backup_dir"]
    try:
        input_file = request.POST["backup"].file
        file_path = os.path.join(upload_folder, "%s.import_json" % uuid.uuid4())
        temp_file_path = file_path + "~"
        input_file.seek(0)
        with open(temp_file_path, "wb") as output_file:
            shutil.copyfileobj(input_file, output_file)
        os.rename(temp_file_path, file_path)
        json_content = open(file_path, "rb").read().decode("utf-8-sig")
        import_json_task(
            json_content, lecture.pk, request.user.pk,
        )
        os.remove(file_path)
    except ValueError as exc:
        request.session.flash(Message(cls="danger", text=str(exc)))
        return HTTPFound(location=next_url)

    ReponsesImporteesJSON.create(lecture, request, is_async=True)
    request.session.flash(
        Message(
            cls="success",
            text="La demande d'importation a bien \
été prise en compte.",
        )
    )
    return HTTPFound(location=next_url)
