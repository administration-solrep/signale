from pyramid.httpexceptions import HTTPFound
from pyramid.request import Request
from pyramid.response import Response
from pyramid.view import view_config, view_defaults

from zam_repondeur.message import Message
from zam_repondeur.models import DBSession, Dossier, Lecture, Parametres
from zam_repondeur.resources import TechniqueCollection
from zam_repondeur.tasks.asynchrone import update_cache


class TechniqueCollectionBase:
    def __init__(self, context: TechniqueCollection, request: Request) -> None:
        self.context = context
        self.request = request


@view_defaults(context=TechniqueCollection, permission="manage")
class GestionTechnique(TechniqueCollectionBase):
    @view_config(request_method="GET", renderer="gestion_technique.html")
    def get(self) -> dict:
        return {
            "current_tab": "technique",
            "system_active": Parametres.get_active_alerts(),
        }

    @view_config(request_method="POST")
    def post(self) -> Response:
        # Check permission user
        if not self.request.user.is_admin:
            self.request.session.flash(
                Message(
                    cls="danger",
                    text="Cette fonctionnalité est réservée aux personnes autorisées.",
                )
            )
            return HTTPFound(location=self.request.resource_url(self.context))

        update_cache(self.request.user.pk)
        self.request.session.flash(
            Message(
                cls="success",
                text="La demande de mise à jour du cache a été prise en compte.",
            )
        )
        return HTTPFound(location=self.request.resource_url(self.context))


@view_defaults(context=TechniqueCollection, permission="manage")
class SwitchAlerts(TechniqueCollectionBase):
    @view_config(request_method="POST", name="switch_alerts")
    def post(self) -> Response:
        # Check permission user
        if not self.request.user.is_admin:
            self.request.session.flash(
                Message(
                    cls="danger",
                    text="Cette fonctionnalité est réservée aux personnes autorisées.",
                )
            )
            return HTTPFound(location=self.request.resource_url(self.context))

        active = Parametres.switch_alerts()
        action: str = "activé" if active else "désactivé"
        self.request.session.flash(
            Message(
                cls="success",
                text=f"Le système des alertes de mise à jour a été {action}.",
            )
        )
        return HTTPFound(location=self.request.resource_url(self.context))


@view_defaults(context=TechniqueCollection, permission="manage")
class ResetAlerts(TechniqueCollectionBase):
    @view_config(request_method="POST", name="reset_alerts")
    def post(self) -> Response:
        # Check permission user
        if not self.request.user.is_admin:
            self.request.session.flash(
                Message(
                    cls="danger",
                    text="Cette fonctionnalité est réservée aux personnes autorisées.",
                )
            )
            return HTTPFound(location=self.request.resource_url(self.context))

        dossiers = DBSession.query(Dossier).all()
        for dossier in dossiers:
            dossier.alert_flag = False
        DBSession.add_all(dossiers)

        lectures = DBSession.query(Lecture).all()
        for lecture in lectures:
            lecture.alert_flag = False
        DBSession.add_all(lectures)

        self.request.session.flash(
            Message(
                cls="success",
                text="Les dossiers en erreurs ont tous été réinitialisés.",
            )
        )
        return HTTPFound(location=self.request.resource_url(self.context))
