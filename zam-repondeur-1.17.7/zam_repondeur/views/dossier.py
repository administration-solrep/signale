import os
from datetime import date
from tempfile import NamedTemporaryFile

from pyramid.httpexceptions import HTTPFound
from pyramid.request import Request
from pyramid.response import FileResponse, Response
from pyramid.view import view_config, view_defaults
from sqlalchemy.orm import subqueryload

from zam_repondeur.message import Message
from zam_repondeur.models import DBSession, Dossier, Lecture
from zam_repondeur.models.events.dossier import RefreshDossier
from zam_repondeur.models.events.lecture import ChangeUpdateStatus
from zam_repondeur.resources import DossierResource
from zam_repondeur.tasks.asynchrone import dossier_delete_task
from zam_repondeur.tasks.fetch import update_dossier


class DossierViewBase:
    def __init__(self, context: DossierResource, request: Request) -> None:
        self.context = context
        self.request = request
        self.dossier = context.dossier


@view_defaults(context=DossierResource)
class DossierView(DossierViewBase):
    @view_config(request_method="GET", renderer="dossier_item.html")
    def get(self) -> Response:
        contact_emails = self.request.registry.settings["zam.contact_mail"]
        if self.dossier.team.coordinators:
            contact_emails = ";".join(
                contact.email for contact in self.dossier.team.coordinators
            )
        return {
            "dossier": self.dossier,
            "dossier_resource": self.context,
            "current_tab": "dossier",
            "lectures": sorted(self.dossier.lectures),
            "allowed_to_delete": self.request.has_permission("delete", self.context),
            "contact_mailto": f"mailto:{contact_emails}",
        }

    @view_config(request_method="POST", permission="delete")
    def post(self) -> Response:
        dossier_delete_task(self.dossier.pk, self.request.user.pk)
        self.request.session.flash(
            Message(
                cls="success", text="La demande de suppression a été prise en compte."
            )
        )
        return HTTPFound(location=self.request.resource_url(self.context.parent))


@view_config(context=DossierResource, name="journal", renderer="dossier_journal.html")
def dossier_journal(context: DossierResource, request: Request) -> Response:
    dossier = context.model(
        subqueryload("events").joinedload("user").load_only("email", "name")
    )
    allowed_to_refresh = request.has_permission("refresh_dossier", context)
    return {
        "dossier": dossier,
        "dossier_resource": context,
        "today": date.today(),
        "current_tab": "journal",
        "allowed_to_refresh": allowed_to_refresh,
    }


@view_config(context=DossierResource, name="download_export")
def dossier_export(context: DossierResource, request: Request) -> Response:
    from zam_repondeur.services.dossiers import dossier_export_repository

    dossier = context.model()
    export = dossier_export_repository.get_export_data(dossier)
    if not export:
        request.session.flash(
            Message(cls="error", text="L'export dans le cache a expiré.")
        )
        return HTTPFound(location=request.resource_url(context))

    date_str = export["created_at"].strftime("%Y_%m_%d_%H_%M")

    with NamedTemporaryFile() as file_:
        tmp_file_path = os.path.abspath(file_.name)
        file_.write(export["export_content"])
        response = FileResponse(tmp_file_path)
        attach_name = f"{dossier.slug}-{date_str}.zip"
        response.content_type = "application/zip"
        response.headers[
            "Content-Disposition"
        ] = f'attachment; filename="{attach_name}"'
        return response


@view_config(context=DossierResource, name="manual_refresh", permission="active")
def manual_refresh(context: DossierResource, request: Request) -> Response:
    dossier = context.dossier
    if not request.user.is_admin:
        request.session.flash(
            Message(
                cls="error",
                text="Le rafraichissement manuel des données "
                "est réservé aux personnes autorisées.",
            )
        )
        return HTTPFound(location=request.resource_url(context, "journal"))

    update_dossier(dossier.pk, force=True)

    RefreshDossier(dossier=dossier, request=request)

    request.session.flash(
        Message(cls="success", text="Rafraîchissement des lectures en cours.")
    )
    return HTTPFound(location=request.resource_url(context))


@view_defaults(
    context=DossierResource,
    name="change_lecture_update_status",
    permission="set_lecture_update",
)
class LectureChangeUpdateForm(DossierViewBase):
    @view_config(request_method="POST")
    def post(self) -> Response:
        lecture_pk: str = self.request.POST.get("pk")
        lecture = DBSession.query(Lecture).filter(Lecture.pk == lecture_pk).one()

        actions = {True: "activée", False: "désactivée"}
        lecture.update = not lecture.update
        action = actions[lecture.update]

        ChangeUpdateStatus.create(
            lecture=lecture, update=lecture.update, request=self.request
        )

        self.request.session.flash(
            Message(
                cls="success", text=(f"La mise à jour de {lecture} a été {action}."),
            )
        )
        return HTTPFound(location=self.request.resource_url(self.context))


@view_defaults(
    context=DossierResource, name="disable_alert", permission="set_dossier_alert",
)
class DossierDisableAlert(DossierViewBase):
    @view_config(request_method="POST")
    def post(self) -> Response:
        is_dossier: int = int(self.request.POST.get("is_dossier"))
        back_url: str = self.request.POST.get("back_url")
        pk: str = self.request.POST.get("pk")

        if is_dossier:
            element = DBSession.query(Dossier).filter(Dossier.pk == pk).one()
            message = f"le dossier {element.titre}"
        else:
            element = DBSession.query(Lecture).filter(Lecture.pk == pk).one()
            message = f"la lecture {element}"

        element.alert_flag = False
        DBSession.add(element)

        self.request.session.flash(
            Message(
                cls="success", text=f"L’alerte pour {message} a bien été supprimée.",
            )
        )
        return HTTPFound(location=back_url)
