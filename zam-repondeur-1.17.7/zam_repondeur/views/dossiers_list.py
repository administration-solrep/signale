from datetime import date
from typing import Any, Iterable, List, Optional, Tuple

from pyramid.httpexceptions import HTTPBadRequest, HTTPFound
from pyramid.request import Request
from pyramid.response import Response
from pyramid.view import view_config, view_defaults
from pyramid_mailer import get_mailer
from sqlalchemy.orm import joinedload

from zam_repondeur.mails import send_coordinator_invitations, sort_emails
from zam_repondeur.message import Message
from zam_repondeur.models import Actualite, DBSession, Dossier, Team, User
from zam_repondeur.models.events.dossier import (
    DossierActive,
    InvitationCoordinateurEnvoyee,
)
from zam_repondeur.models.events.dossiers_list import DossiersListActive
from zam_repondeur.resources import DossierCollection
from zam_repondeur.tasks.fetch import create_missing_lectures
from zam_repondeur.views.dossier_invite import (
    DossierInviteAction,
    get_message_from_invitation_result,
)


class DossierCollectionBase:
    def __init__(self, context: DossierCollection, request: Request) -> None:
        self.context = context
        self.request = request
        self.dossiers = context.models(joinedload("team"), joinedload("textes"))
        self.actualite = Actualite.get()


@view_defaults(context=DossierCollection)
class DossierList(DossierCollectionBase):
    def get_pagination(self, my_dossiers: List[Dossier]) -> Tuple[dict, int, int, bool]:
        try:
            page_index = int(self.request.GET.get("page", 1)) - 1
        except Exception:
            page_index = 0

        seuil = int(self.request.registry.settings["zam.seuil_pagination_dossiers"])
        pagination = len(my_dossiers) > seuil

        if pagination:
            page_supp = 1 if (len(my_dossiers) % seuil) > 0 else 0
            nb_pages = len(my_dossiers) // seuil + page_supp

            # Vérification des bornes
            if page_index < 0 or page_index >= nb_pages:
                page_index = 0

            index_debut = seuil * page_index
            index_fin = seuil * (page_index + 1)

            pages_param_label = [(f"{x}", f"{x}") for x in range(1, nb_pages + 1)]

            pagination_data = {
                "previous": self.get_previous(page_index, pages_param_label),
                "first": self.get_first(page_index, pages_param_label),
                "first_elipse": self.get_first_ellipse(page_index, nb_pages),
                "pages": self.get_pages(page_index, pages_param_label),
                "last_elipse": self.get_last_ellipse(
                    pages_param_label, page_index, nb_pages
                ),
                "last": self.get_last(page_index, pages_param_label),
                "next": self.get_next(page_index, pages_param_label),
            }
        else:
            pagination_data = {}
            index_debut = 0
            index_fin = seuil
        return pagination_data, index_debut, index_fin, pagination

    def get_first(
        self, page_index: int, pages_param_label: List[Tuple[str, str]]
    ) -> Optional[dict]:
        if page_index < 3 or len(pages_param_label) < 8:
            return None
        param, label = pages_param_label[0]
        return {
            "param": "page",
            "value": f"{param}",
            "label": f"{label}",
        }

    def get_last(
        self, page_index: int, pages_param_label: List[Tuple[str, str]]
    ) -> Optional[dict]:
        if len(pages_param_label) - page_index - 1 < 4 or len(pages_param_label) < 8:
            return None
        param, label = pages_param_label[-1]
        return {
            "param": "page",
            "value": f"{param}",
            "label": f"{label}",
        }

    def get_next(
        self, page_index: int, pages_param_label: List[Tuple[str, str]]
    ) -> Optional[dict]:
        if page_index == len(pages_param_label) - 1:
            return None
        param, label = pages_param_label[page_index + 1]
        return {
            "param": "page",
            "value": f"{param}",
            "title": "Dossiers suivants",
        }

    def get_previous(
        self, page_index: int, pages_param_label: List[Tuple[str, str]]
    ) -> Optional[dict]:
        if page_index == 0:
            return None
        param, label = pages_param_label[page_index - 1]
        return {
            "param": "page",
            "value": f"{param}",
            "title": "Dossiers précédents",
        }

    def get_pages(
        self,
        page_index: int,
        pages_param_label: List[Tuple[str, str]],
        page_range: int = 1,
    ) -> List[dict]:
        index_min = 0
        index_max = len(pages_param_label)

        if index_max < 8:
            range_min = index_min
            range_max = index_max
        else:
            supp_min, supp_max = 0, 1
            if page_index == 3:
                supp_min = 1
            elif page_index == index_max - 3:
                supp_max = 2
            range_min = max(page_index - page_range - supp_min, index_min)
            range_max = min(page_index + page_range + supp_max, index_max)

            if page_index < 3:
                range_min = index_min
            elif page_index > index_max - 5:
                range_max = index_max

        pages = []
        for i in range(range_min, range_max):
            param, label = pages_param_label[i]
            pages.append(
                {
                    "param": "page",
                    "value": f"{param}",
                    "label": f"{label}",
                    "current": i == page_index,
                }
            )
        return pages

    def get_first_ellipse(self, index: int, nb_pages: int) -> Any:
        if nb_pages > 7:
            return index > 3
        return False

    def get_last_ellipse(
        self, pages_param_label: List[Tuple[str, str]], index: int, nb_pages: int
    ) -> Any:
        if nb_pages > 7:
            return len(pages_param_label) - index - 1 > 3
        return False

    @property
    def get_actualite(self) -> Any:
        if self.actualite:
            return self.actualite
        return None


class DossierListActive(DossierList):
    @view_config(request_method="GET", renderer="dossiers_list.html")
    def get(self) -> dict:
        my_dossiers = [
            dossier
            for dossier in self.dossiers
            if dossier.team
            and dossier.team.active
            and (self.request.user.is_admin or dossier.team in self.request.user.teams)
        ]
        all_my_dossiers = [
            dossier
            for dossier in self.dossiers
            if dossier.team
            and (self.request.user.is_admin or dossier.team in self.request.user.teams)
        ]

        pagination = self.get_pagination(my_dossiers)

        return {
            "all_dossiers": all_my_dossiers,
            "dossiers": my_dossiers,
            "index_debut": pagination[1],
            "index_fin": pagination[2],
            "allowed_to_activate": self.request.has_permission(
                "activate", self.context
            ),
            "current_tab": "dossiers",
            "affichage_pagination_dossiers": pagination[3],
            "pagination_data": pagination[0],
            "actualite": self.get_actualite,
        }


class DossierListNotActive(DossierList):
    @view_config(
        request_method="GET", name="archives", renderer="dossiers_list_archives.html"
    )
    def get(self) -> dict:
        my_dossiers = [
            dossier
            for dossier in self.dossiers
            if dossier.team
            and not dossier.team.active
            and (self.request.user.is_admin or dossier.team in self.request.user.teams)
        ]

        pagination = self.get_pagination(my_dossiers)

        return {
            "all_dossiers": my_dossiers,
            "dossiers": my_dossiers,
            "index_debut": pagination[1],
            "index_fin": pagination[2],
            "allowed_to_activate": self.request.has_permission(
                "activate", self.context
            ),
            "current_tab": "archives",
            "affichage_pagination_dossiers": pagination[3],
            "pagination_data": pagination[0],
            "actualite": self.get_actualite,
        }


class DossierListJournal(DossierList):
    @view_config(
        request_method="GET", name="journal", renderer="dossiers_list_journal.html"
    )
    def get(self) -> dict:

        events = self.context.events().all()

        return {
            "events": events,
            "today": date.today(),
            "current_tab": "journal",
        }


@view_defaults(context=DossierCollection, permission="view")
class DossierAskInviteForm(DossierCollectionBase):
    def __init__(self, context: DossierCollection, request: Request) -> None:
        self.context = context
        self.request = request
        self.dossiers = context.models(
            joinedload("team", innerjoin=True), joinedload("textes")
        )

    def _get_tuple_titre_contact_subject(
        self, default_contact: str, dossiers: List[Dossier]
    ) -> Iterable[Tuple[str, str, str]]:
        for dossier in dossiers:
            contact_emails = default_contact
            if dossier.team.coordinators:
                contact_emails = ";".join(
                    contact.email for contact in dossier.team.coordinators
                )
            yield (
                dossier.titre_long
                if self.request.user.is_admin
                else dossier.titre_semilong,
                f"{contact_emails}",
                f"SIGNALE : Demande d’invitation au dossier législatif \
« {dossier.titre} »",
            )


class DossierAskInviteFormActive(DossierAskInviteForm):
    @view_config(
        request_method="GET", name="demande_invitation", renderer="dossiers_invit.html"
    )
    def get(self) -> dict:
        activated_dossiers = [
            dossier
            for dossier in self.dossiers
            if self.request.user not in dossier.team.users and dossier.team.active
        ]
        default_contact = self.request.registry.settings["zam.contact_mail"]
        return {
            "list_mailto": list(
                self._get_tuple_titre_contact_subject(
                    default_contact, activated_dossiers
                )
            ),
            "current_tab": "archives",
        }


class DossierAskInviteFormNotActive(DossierAskInviteForm):
    @view_config(
        request_method="GET",
        name="demande_invitation_archives",
        renderer="dossiers_invit_archives.html",
    )
    def get(self) -> dict:
        activated_dossiers = [
            dossier
            for dossier in self.dossiers
            if self.request.user not in dossier.team.users and not dossier.team.active
        ]
        default_contact = self.request.registry.settings["zam.contact_mail"]
        return {
            "list_mailto": list(
                self._get_tuple_titre_contact_subject(
                    default_contact, activated_dossiers
                )
            ),
            "current_tab": "dossiers",
        }


@view_defaults(context=DossierCollection, name="add", permission="activate")
class DossierAddForm(DossierCollectionBase, DossierInviteAction):
    @view_config(request_method="GET", renderer="dossiers_add.html")
    def get(self) -> dict:
        available_dossiers = [
            dossier for dossier in self.dossiers if dossier.textes and not dossier.team
        ]
        return {"available_dossiers": available_dossiers, "current_tab": "dossiers_add"}

    @view_config(request_method="POST")
    def post(self) -> Response:
        dossier_slug = self._get_dossier_slug()

        if not dossier_slug:
            self.request.session.flash(
                Message(cls="error", text="Ce dossier n’existe pas.")
            )
            return HTTPFound(location=self.request.resource_url(self.context))

        dossier = Dossier.get(slug=dossier_slug)

        if dossier is None:
            self.request.session.flash(
                Message(cls="error", text="Ce dossier n’existe pas.")
            )
            return HTTPFound(location=self.request.resource_url(self.context))

        if dossier.team:
            self.request.session.flash(
                Message(cls="warning", text="Ce dossier appartient à une autre équipe…")
            )
            return HTTPFound(location=self.request.resource_url(self.context))

        # Only consider well formed addresses from allowed domains
        bad_emails, clean_emails = sort_emails(self.request.POST.get("emails"))

        if not clean_emails:
            message = "Aucun email valide"
            message += "<br><br>"
            message += "Un ou plusieurs coordinateurs doit être choisi \
avant de pouvoir ajouter ce dossier"
            self.request.session.flash(Message(cls="error", text=message,))
            return HTTPFound(location=self.request.resource_url(self.context, "add"))

        # Create user accounts if needed
        new_users, existing_users = self._find_or_create_users(clean_emails)
        users_to_invite = new_users + existing_users

        if not users_to_invite:
            message = "Aucun coordinateur valide trouvé"
            message += "<br><br>"
            message += "Un ou plusieurs coordinateurs doit être choisi \
avant de pouvoir ajouter ce dossier"
            self.request.session.flash(Message(cls="error", text=message,))
            return HTTPFound(location=self.request.resource_url(self.context, "add"))

        team = Team.create(name=dossier.slug)
        dossier.team = team
        for admin in DBSession.query(User).filter(
            User.admin_at.isnot(None)  # type: ignore
        ):
            admin.teams.append(team)
        team.add_coordinators(users_to_invite)

        # Enqueue task to asynchronously add the lectures
        create_missing_lectures(
            dossier_pk=dossier.pk, send_email=False, user_pk=self.request.user.pk
        )

        DossierActive.create(dossier=dossier, request=self.request)
        DossiersListActive.create(dossier=dossier, request=self.request)

        # get commons mail values
        mailer = get_mailer(self.request)
        url_dossier = self.request.resource_url(self.context[dossier.url_key])
        contact_mail_from = self.request.registry.settings["zam.contact_mail_from"]

        invitations_sent = 0
        invitations_sent += send_coordinator_invitations(
            mailer,
            self.request.user,
            users_to_invite,
            contact_mail_from,
            dossier.titre,
            url_dossier,
            self.request.registry,
        )

        for user in users_to_invite:
            InvitationCoordinateurEnvoyee.create(
                dossier=dossier, email=user.email, request=self.request
            )

        cls, message = get_message_from_invitation_result(
            invitations_sent, [], bad_emails
        )
        message += "<br><br>"
        message += "Dossier créé avec succès, lectures en cours de création."

        self.request.session.flash(Message(cls=cls, text=message,))
        return HTTPFound(
            location=self.request.resource_url(self.context[dossier.url_key])
        )

    def _get_dossier_slug(self) -> str:
        try:
            dossier_slug = self.request.POST["dossier"] or ""
        except KeyError:
            raise HTTPBadRequest
        return dossier_slug
