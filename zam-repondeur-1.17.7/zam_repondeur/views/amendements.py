from datetime import date
from typing import Any, Dict

from markupsafe import Markup
from pyramid.httpexceptions import HTTPFound
from pyramid.request import Request
from pyramid.response import Response
from pyramid.view import view_config, view_defaults
from sqlalchemy.orm import noload

from zam_repondeur.decorator import reify
from zam_repondeur.message import Message
from zam_repondeur.models import AVIS, Batch
from zam_repondeur.models.events.amendement import (
    AvisAmendementModifie,
    CommentsAmendementModifie,
    ConfirmResponseAmendement,
    ObjetAmendementModifie,
    ReponseAmendementModifiee,
)
from zam_repondeur.resources import AmendementResource
from zam_repondeur.services.clean import clean_html, clean_tinymce
from zam_repondeur.utils import add_url_fragment, add_url_params


@view_defaults(
    context=AmendementResource, name="amendement_edit", renderer="amendement_edit.html"
)
class AmendementEdit:
    def __init__(self, context: AmendementResource, request: Request) -> None:
        self.context = context
        self.request = request
        self.amendement = context.model()
        self.amendements = list(Batch.expanded_batches([self.amendement]))
        self.lecture = self.amendement.lecture
        self.my_table_resource = self.context.lecture_resource["tables"][
            self.request.user.email
        ]
        self.is_on_my_table = (
            self.amendement.location.user_table
            and self.amendement.location.user_table.user == self.request.user
        )

    @view_config(request_method="GET")
    def get(self) -> dict:
        check_url = self.request.resource_path(self.my_table_resource, "check")
        return {
            "dossier_resource": self.context.lecture_resource.dossier_resource,
            "lecture": self.lecture,
            "amendement": self.amendement,
            "amendements": self.amendements,
            "current_tab": "",
            "active": self.lecture.dossier.team.active,
            "avis": AVIS,
            "table": self.amendement.location.user_table,
            "is_on_my_table": self.is_on_my_table,
            "back_url": self.back_url,
            "submit_url": self.submit_url,
            "check_url": check_url,
            "my_table_url": self.my_table_url,
            "transfer_url": self.request.resource_url(
                self.context.lecture_resource,
                "transfer_amendements",
                query={"nums": self.amendement.num, "from_index": 1},
            ),
            "reponses": self.amendement.article.grouped_displayable_amendements(),
            "amendement_precedent": self.amendement.previous_amendement,
            "amendement_suivant": self.amendement.next_amendement,
            "is_on_dossier_banc": self.amendement.position_banc_as_int == 2,
            "comments": Markup(self.amendement.user_content.comments or ""),
        }

    @view_config(request_method="POST", permission="active")
    def post(self) -> Response:
        avis = self.request.POST.get("avis", "")
        objet = clean_tinymce(self.request.POST.get("objet", ""))
        reponse = clean_tinymce(self.request.POST.get("reponse", ""))
        comments = clean_html(self.request.POST.get("comments", ""))

        avis_changed = avis != (self.amendement.user_content.avis or "")
        objet_changed = objet != (self.amendement.user_content.objet or "")
        reponse_changed = reponse != (self.amendement.user_content.reponse or "")
        comments_changed = comments != (self.amendement.user_content.comments or "")

        if "confirm-response" in self.request.POST:

            for amendement in self.amendements:
                ConfirmResponseAmendement.create(
                    amendement=amendement, request=self.request
                )
                amendement.stop_editing()

            self.request.session.flash(
                Message(cls="success", text="L'avertissement a bien été supprimé.")
            )
            return HTTPFound(location=self.request.resource_url(self.context.parent))

        if not self.is_on_my_table:
            message = (
                "Les modifications n’ont PAS été enregistrées "
                "car l’amendement n’est plus sur votre espace de travail."
            )
            if self.amendement.location.user_table:
                message += (
                    f" Il est actuellement sur l'espace de travail de "
                    f"{self.amendement.location.user_table.user}."
                )
            self.request.session.flash(Message(cls="danger", text=message))
            return HTTPFound(location=self.my_table_url)

        for amendement in self.amendements:
            if avis_changed:
                AvisAmendementModifie.create(
                    amendement=amendement, avis=avis, request=self.request
                )

            if objet_changed:
                ObjetAmendementModifie.create(
                    amendement=amendement, objet=objet, request=self.request
                )

            if reponse_changed:
                ReponseAmendementModifiee.create(
                    amendement=amendement, reponse=reponse, request=self.request
                )

            if comments_changed:
                CommentsAmendementModifie.create(
                    amendement=amendement, comments=comments, request=self.request
                )

            amendement.stop_editing()

        self.request.session.flash(
            Message(cls="success", text="Les modifications ont bien été enregistrées.")
        )
        if "save-and-transfer" in self.request.POST:
            return HTTPFound(
                location=self.request.resource_url(
                    self.context.lecture_resource,
                    "transfer_amendements",
                    query={
                        "nums": [amendement.num for amendement in self.amendements],
                        "from_save": 1,
                        "back": self.back_url,
                    },
                )
            )
        elif "save-and-stay" in self.request.POST:
            return HTTPFound(
                location=self.request.resource_url(self.context, "amendement_edit")
            )
        else:
            self.request.session["highlighted_amdt"] = self.amendements[0].slug
            return HTTPFound(location=f"{self.my_table_url}#{self.amendements[0].slug}")

    @reify
    def back_url(self) -> str:
        url: str = self.request.GET.get("back")
        if url is None or not url.startswith("/"):
            url = self.my_table_url
        return add_url_fragment(url, self.amendements[0].slug)

    @property
    def submit_url(self) -> str:
        return add_url_params(self.request.path, back=self.back_url)

    @property
    def my_table_url(self) -> str:
        return self.request.resource_url(self.my_table_resource)


@view_config(
    context=AmendementResource, name="journal", renderer="amendement_journal.html"
)
def amendement_journal(context: AmendementResource, request: Request) -> Dict[str, Any]:
    lecture = context.lecture_resource.model(noload("amendements"), noload("articles"))
    return {
        "lecture": lecture,
        "dossier_resource": context.lecture_resource.dossier_resource,
        "active": lecture.dossier.team.active,
        "current_tab": "journal",
        "amendement": context.model(),
        "today": date.today(),
        "back_url": request.resource_url(context, "amendement_edit"),
    }


@view_config(context=AmendementResource, name="start_editing", renderer="json")
def start_editing(context: AmendementResource, request: Request) -> dict:
    for amendement in Batch.expanded_batches([context.model()]):
        amendement.start_editing()
    return {}


@view_config(context=AmendementResource, name="stop_editing", renderer="json")
def stop_editing(context: AmendementResource, request: Request) -> dict:
    for amendement in Batch.expanded_batches([context.model()]):
        amendement.stop_editing()
    return {}


@view_config(
    context=AmendementResource, name="get_objet", renderer="json", permission="view"
)
def amendement_objet(context: AmendementResource, request: Request) -> dict:
    try:
        amendement = context.model()
        request.response.status = 200  # type: ignore # noqa
        return {"num": amendement.num, "objet": amendement.user_content.objet}
    except Exception:
        request.response.status = 404  # type: ignore # noqa
        return {
            "error": "L'amendement n'existe pas ou vous n'avez pas les droits \
requis pour y accéder."
        }
