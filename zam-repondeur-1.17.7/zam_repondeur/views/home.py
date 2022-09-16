import logging
import os
import shutil
import urllib
import uuid
from datetime import datetime
from tempfile import NamedTemporaryFile

from pathvalidate import sanitize_filename
from pyramid.httpexceptions import HTTPFound
from pyramid.request import Request
from pyramid.response import FileResponse, Response
from pyramid.security import NO_PERMISSION_REQUIRED
from pyramid.view import view_config

from zam_repondeur.message import Message
from zam_repondeur.models import Actualite, DBSession
from zam_repondeur.resources import Root
from zam_repondeur.services.clean import clean_tinymce

logger = logging.getLogger(__name__)


@view_config(context=Root)
def home(context: Root, request: Request) -> Response:
    return HTTPFound(location=request.resource_url(context["dossiers"]))


@view_config(
    route_name="manuel_utilisateur",
    permission=NO_PERMISSION_REQUIRED,
    request_method="GET",
)
def manuel_utilisateur(request: Request) -> Response:
    back_url = request.GET.get("back")
    try:
        tmp_file_path = os.path.join(
            os.path.dirname(__file__),
            os.path.join(request.registry.settings["zam.chemin_manuel_utilisateur"]),
        )
        response = FileResponse(tmp_file_path)

        response.content_type = "application/pdf"
        response.headers[
            "Content-Disposition"
        ] = f'attachment; filename="{os.path.basename(tmp_file_path)}"'
        return response

    except FileNotFoundError as error:
        logger.error(f"{error}")
        request.session.flash(
            Message(cls="danger", text="Le manuel d'utilisation n'existe pas")
        )
        return HTTPFound(location=back_url)


@view_config(
    route_name="actualite",
    permission="manage_actu",
    request_method="POST",
    context=Root,
)
def post_actualite(request: Request) -> Response:
    message: str = clean_tinymce(request.POST.get("message"))
    pj_changed: int = int(request.POST.get("pj_changed"))
    back_url = request.POST.get("back")
    max_upload_size = int(request.registry.settings["zam.actualites.max_upload_size"])

    if (
        "piece_jointe" in request.POST
        and request.POST["piece_jointe"] != b""
        and pj_changed
    ):
        file_name = request.POST["piece_jointe"].filename
        input_file = request.POST["piece_jointe"].file
        content_type = request.POST["piece_jointe"].type
        size = request.POST["piece_jointe"].bytes_read

        final_name = str(sanitize_filename(file_name))

        # Vérification de la taille du fichier qui ne doit pas dépasser la
        # valeur de zam.actualites.max_upload_size
        if size > max_upload_size:
            message = (
                f"Erreur : La pièce jointe utilisée pour le bandeau des "
                f"actualités dépasse la taille autorisée : "
                f"{int(max_upload_size / 1000000)} Mo"
            )
            logger.error(message)
            request.session.flash(Message(cls="danger", text=message))
            return HTTPFound(location=back_url)

        # Vérification du format de la pièce jointe
        if content_type != "application/pdf":
            message = (
                "Erreur : Seul le format PDF est autorisé pour la "
                "pièce jointe du bandeau des actualités."
            )
            logger.error(message)
            request.session.flash(Message(cls="danger", text=message))
            return HTTPFound(location=back_url)

        file_path = os.path.join("/tmp", "%s.pj" % uuid.uuid4())

        temp_file_path = file_path + "~"

        # Finally write the data to a temporary file
        input_file.seek(0)
        with open(temp_file_path, "wb") as output_file:
            shutil.copyfileobj(input_file, output_file)

        # Now that we know the file has been fully saved to disk move it into place.
        os.rename(temp_file_path, file_path)

        # Before save, truncate table. Then, save it.
        Actualite.remove()
        Actualite.create(
            message=message,
            piece_jointe=open(file_path, "rb"),
            file_name=final_name,
            content_type=content_type,
        )

        # Remove temporary file from disk
        os.remove(file_path)

    else:
        actualite = Actualite.get()
        if actualite:
            actualite.message = message
            actualite.created_at = datetime.utcnow()
            if pj_changed:
                # Dans ce cas, il n'y a aucune pj dans le POST,
                # on le supprime donc en base
                actualite.file_name = None
                actualite.file_content_type = None
                actualite.file_data = None
        else:
            # Aucune actualité en base, aucune pj, on crée juste le message
            Actualite.create(message=message,)

    logger.info("Le bandeau des actualités a été mis à jour")
    request.session.flash(
        Message(cls="success", text="Le bandeau des actualités a été mis à jour")
    )
    return HTTPFound(location=back_url)


@view_config(
    route_name="actualite_piece_jointe",
    permission=NO_PERMISSION_REQUIRED,
    request_method="GET",
)
def get_actualite_piece_jointe(request: Request) -> Response:
    actualite = DBSession.query(Actualite).first()

    with NamedTemporaryFile(mode="wb") as file_:

        tmp_file_path = os.path.abspath(file_.name)
        file_.write(actualite.file_data)
        file_.seek(0)

        response = FileResponse(tmp_file_path)
        file_name = ".".join(f"{actualite.file_name}".split(".")[:-1])
        attach_name = urllib.parse.quote_plus(f"{file_name}")
        response.content_type = actualite.file_content_type
        response.headers[
            "Content-Disposition"
        ] = f"attachment; filename*=\"UTF-8''{attach_name}.pdf\""
        return response


@view_config(
    route_name="actualite_delete",
    permission="manage_actu",
    request_method="GET",
    context=Root,
)
def delete_actualite(request: Request) -> Response:
    back_url = request.GET.get("back")
    try:
        Actualite.remove()
        logger.info("Le bandeau des actualités a été supprimé avec succès")
        request.session.flash(
            Message(
                cls="success",
                text="Le bandeau des actualités a été supprimé avec succès",
            )
        )
        return HTTPFound(location=back_url)
    except Exception as error:
        logger.error(f"{error}")
        request.session.flash(
            Message(
                cls="danger",
                text="Erreur : le bandeau des actualités n'a pas pu être supprimé",
            )
        )
        return HTTPFound(location=back_url)
