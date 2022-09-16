from datetime import date, datetime
from typing import Optional

from pyramid.httpexceptions import HTTPFound
from pyramid.request import Request
from pyramid.response import Response
from pyramid.view import view_config, view_defaults

from zam_repondeur.data_sanitize import get_as_int_or_none
from zam_repondeur.mails import send_manage_admins
from zam_repondeur.message import Message
from zam_repondeur.models import DBSession, User
from zam_repondeur.models.events.admin import AdminGrant, AdminRevoke
from zam_repondeur.resources import AdminsCollection


class AdminsCollectionBase:
    def __init__(self, context: AdminsCollection, request: Request) -> None:
        self.context = context
        self.request = request


@view_defaults(context=AdminsCollection, permission="manage")
class AdminsList(AdminsCollectionBase):
    @view_config(request_method="GET", renderer="admins_list.html")
    def get(self) -> dict:
        admins = self.context.models()
        last_event = self.context.events().first()
        if last_event:
            last_event_datetime = last_event.created_at
            last_event_timestamp = (
                last_event_datetime - datetime(1970, 1, 1)
            ).total_seconds()
        else:
            last_event_datetime = None
            last_event_timestamp = None
        return {
            "admins": admins,
            "current_tab": "admins",
            "last_event_datetime": last_event_datetime,
            "last_event_timestamp": last_event_timestamp,
        }


@view_defaults(context=AdminsCollection, permission="manage")
class AdminsRemove(AdminsCollectionBase):
    @view_config(request_method="POST")
    def post(self) -> Response:
        user_pk: Optional[int] = get_as_int_or_none(self.request.POST["user_pk"])

        if user_pk is None:
            message = "Erreur lors du traitement de l'action."
            self.request.session.flash(Message(cls="error", text=message))
            return HTTPFound(location=self.request.resource_url(self.context))

        if self.request.user.pk == user_pk:
            message = "Vous ne pouvez pas vous retirer du statut d’administrateur."
            self.request.session.flash(Message(cls="warning", text=message))
            return HTTPFound(location=self.request.resource_url(self.context))

        user = DBSession.query(User).filter_by(pk=user_pk).first()
        AdminRevoke.create(target=user, request=self.request)

        # Send mail
        send_manage_admins(is_grant=False, request=self.request, user=user)

        self.request.session.flash(
            Message(
                cls="success", text=("Droits d’administration retirés avec succès.")
            )
        )
        return HTTPFound(location=self.request.resource_url(self.context))


@view_defaults(context=AdminsCollection, name="add", permission="manage")
class AdminsAddForm(AdminsCollectionBase):
    @view_config(request_method="GET", renderer="admins_add.html")
    def get(self) -> dict:
        users = DBSession.query(User).all()
        return {"current_tab": "admins", "users": users}

    @view_config(request_method="POST")
    def post(self) -> Response:
        user_pk: Optional[int] = get_as_int_or_none(self.request.POST.get("user_pk"))
        if user_pk is None:
            self.request.session.flash(
                Message(
                    cls="warning",
                    text="Veuillez saisir une personne dans le menu déroulant.",
                )
            )
            return HTTPFound(location=self.request.resource_url(self.context, "add"))
        user = DBSession.query(User).filter_by(pk=user_pk).first()
        AdminGrant.create(target=user, request=self.request)

        # Send mail
        send_manage_admins(is_grant=True, request=self.request, user=user)

        self.request.session.flash(
            Message(
                cls="success", text=("Droits d’administration ajoutés avec succès.")
            )
        )
        return HTTPFound(location=self.request.resource_url(self.context))


@view_config(
    context=AdminsCollection,
    permission="manage",
    name="journal",
    renderer="admins_journal.html",
)
def admins_journal(context: AdminsCollection, request: Request) -> Response:
    events = context.events().all()
    return {"events": events, "today": date.today(), "current_tab": "admins"}
