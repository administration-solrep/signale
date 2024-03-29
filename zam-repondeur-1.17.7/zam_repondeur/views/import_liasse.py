import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from pyramid.httpexceptions import HTTPFound
from pyramid.request import Request
from pyramid.response import Response
from pyramid.view import view_config

from zam_repondeur.message import Message
from zam_repondeur.models import DBSession
from zam_repondeur.models.events.import_export import AmendementsRecuperesLiasse
from zam_repondeur.resources import ImportExportLecture
from zam_repondeur.services.import_export.liasse_xml import (
    LectureDoesNotMatch,
    import_liasse_xml,
)

logger = logging.getLogger(__name__)


@view_config(context=ImportExportLecture, name="import_liasse_xml", permission="active")
def upload_liasse_xml(context: ImportExportLecture, request: Request) -> Response:
    lecture = context.parent.model()
    user = request.user

    # Check permission user (admin or coordinator)
    if not user.is_admin and not lecture.dossier.team.is_coordinator(user):
        request.session.flash(
            Message(
                cls="danger",
                text="L’import de liasses est réservé aux personnes autorisées.",
            )
        )
        return HTTPFound(location=request.resource_url(context))

    try:
        liasse_field = request.POST["liasse"]
    except KeyError:
        request.session.flash(
            Message(cls="warning", text="Veuillez d’abord sélectionner un fichier")
        )
        return HTTPFound(location=request.resource_url(context))

    if liasse_field == b"":
        request.session.flash(
            Message(cls="warning", text="Veuillez d’abord sélectionner un fichier")
        )
        return HTTPFound(location=request.resource_url(context))

    # Backup uploaded file to make troubleshooting easier
    backup_path = get_backup_path(request)
    if backup_path is not None:
        save_uploaded_file(liasse_field, backup_path)

    try:
        amendements, errors = import_liasse_xml(liasse_field.file, lecture)
    except ValueError:
        logger.exception("Erreur d'import de la liasse XML")
        request.session.flash(
            Message(cls="danger", text="Le format du fichier n’est pas valide.")
        )
        return HTTPFound(location=request.resource_url(context))
    except LectureDoesNotMatch as exc:
        request.session.flash(
            Message(
                cls="danger",
                text=f"La liasse correspond à une autre lecture ({exc.lecture_fmt}).",
            )
        )
        return HTTPFound(location=request.resource_url(context))

    if errors:
        if len(errors) == 1:
            what = "l'amendement"
        else:
            what = "les amendements"
        uids = ", ".join(uid for uid, cause in errors)
        request.session.flash(
            Message(cls="warning", text=f"Impossible d'importer {what} {uids}.")
        )

    if len(amendements) == 0:
        request.session.flash(
            Message(
                cls="warning",
                text="Aucun amendement valide n’a été trouvé dans ce fichier.",
            )
        )
        return HTTPFound(location=request.resource_url(context))

    if len(amendements) == 1:
        message = "1 nouvel amendement récupéré (import liasse XML)."
    else:
        message = (
            f"{len(amendements)} nouveaux amendements récupérés (import liasse XML)."
        )
    request.session.flash(Message(cls="success", text=message))
    AmendementsRecuperesLiasse.create(
        lecture=lecture, count=len(amendements), request=request
    )
    DBSession.add(lecture)
    return HTTPFound(location=request.resource_url(context.parent["amendements"]))


def get_backup_path(request: Request) -> Optional[Path]:
    backup_dir: Optional[str] = request.registry.settings.get("zam.uploads_backup_dir")
    if not backup_dir:
        return None
    backup_path = Path(backup_dir)
    backup_path.mkdir(parents=True, exist_ok=True)
    return backup_path


def save_uploaded_file(form_field: Any, backup_dir: Path) -> None:
    form_field.file.seek(0)
    timestamp = datetime.utcnow().isoformat(timespec="seconds")
    sanitized_filename = os.path.basename(form_field.filename)
    backup_filename = Path(backup_dir) / f"liasse-{timestamp}-{sanitized_filename}"
    with backup_filename.open("wb") as backup_file:
        shutil.copyfileobj(form_field.file, backup_file)
    logger.info("Uploaded file saved to %s", backup_filename)
    form_field.file.seek(0)
