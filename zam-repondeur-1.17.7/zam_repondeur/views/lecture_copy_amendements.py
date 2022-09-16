from typing import Any, List, Optional

from markupsafe import Markup
from pyramid.httpexceptions import HTTPFound
from pyramid.request import Request
from pyramid.response import Response
from pyramid.view import view_config, view_defaults
from sqlalchemy.orm import joinedload, load_only, noload, subqueryload
from webob.multidict import MultiDict

from zam_repondeur.message import Message
from zam_repondeur.models import AVIS, Amendement, Batch
from zam_repondeur.models.amendement import ReponseTuple
from zam_repondeur.resources import LectureResource
from zam_repondeur.services.import_export.common import modify_reponse


@view_defaults(
    context=LectureResource,
    renderer="copy_reponses_amdts.html",
    name="copy_amendements",
)
class CopyAmendements:
    def __init__(self, context: LectureResource, request: Request) -> None:
        self.context = context
        self.request = request
        self.lecture = self.context.model(
            noload("articles"),
            subqueryload("amendements").options(
                load_only(
                    "article_pk",
                    "auteur",
                    "id_identique",
                    "lecture_pk",
                    "mission_titre",
                    "mission_titre_court",
                    "num",
                    "parent_pk",
                    "position",
                    "rectif",
                    "sort",
                ),
                joinedload("user_content").load_only(
                    "avis", "has_reponse", "objet", "reponse_hash"
                ),
                joinedload("location").options(
                    subqueryload("batch")
                    .joinedload("amendements_locations")
                    .joinedload("amendement")
                    .load_only("num", "rectif"),
                    subqueryload("shared_table").load_only("titre"),
                    subqueryload("user_table")
                    .joinedload("user")
                    .load_only("email", "name"),
                ),
            ),
        )

    @view_config(request_method="GET", permission="active")
    def get(self) -> Any:
        amendements = self.get_amendements_from(self.request.GET, "nums")

        self.check_amendements_are_all_on_my_table(amendements)

        default_amdt = self.get_amendement_only_or_first_reponse(amendements)
        comments = (
            Markup(default_amdt.user_content.comments or "") if default_amdt else ""
        )

        return {
            "lecture": self.lecture,
            "dossier_resource": self.context.dossier_resource,
            "current_tab": "table",
            "amendements": amendements,
            "back_url": self.my_table_url,
            "same_reponse": self.check_amendements_have_all_same_reponse_or_empty(
                amendements
            ),
            "avis": AVIS,
            "nums": [amendement.num for amendement in amendements],
            "default_amdt": default_amdt,
            "comments": comments,
        }

    @view_config(request_method="POST", permission="active")
    def post(self) -> Response:
        amendements = list(
            Batch.expanded_batches(self.get_amendements_from(self.request.POST, "nums"))
        )

        self.check_amendements_are_all_on_my_table(amendements)

        shared_reponse: Optional[ReponseTuple] = None
        if self.request.POST.get("same-reponse"):
            shared_reponse = self.get_common_reponse(
                self.request.POST.get("avis"),
                self.request.POST.get("objet"),
                self.request.POST.get("reponse"),
                self.request.POST.get("comments"),
            )
        to_be_updated: List[Amendement] = []
        if shared_reponse is not None:
            for amendement in amendements:
                to_be_updated.append(amendement)

        modify_reponse(
            request=self.request,
            shared_reponse=shared_reponse,
            to_be_updated=to_be_updated,
            edit_avis=bool(self.request.POST.get("switch-avis", None)),
            edit_objet=bool(self.request.POST.get("switch-objet", None)),
            edit_reponse=bool(self.request.POST.get("switch-reponse", None)),
            edit_comments=bool(self.request.POST.get("switch-comments", None)),
        )
        all_amendements = self.get_amendements_from(self.request.POST, "hidden-nums")
        for amendement in all_amendements:
            amendement.stop_editing()

        nums = [num.num_disp for num in Batch.collapsed_batches(amendements)]
        self.request.session.flash(
            Message(
                cls="success",
                text=f"La réponse des amendements suivants a bien été mise à jour : "
                f"{', '.join(nums)}",
            )
        )
        return HTTPFound(location=self.my_table_url)

    def get_common_reponse(
        self, avis: str, objet: str, reponse: str, comments: str
    ) -> ReponseTuple:
        return ReponseTuple(
            avis=avis or "",
            objet=(objet.strip() if objet else ""),
            content=(reponse.strip() if reponse else ""),
            comments=(comments.strip() if comments else ""),
        )

    @property
    def my_table_url(self) -> str:
        table_resource = self.context["tables"][self.request.user.email]
        return self.request.resource_url(table_resource)

    def get_amendements_from(self, source: MultiDict, key: str) -> List[Amendement]:
        return [
            amendement
            for amendement in self.lecture.amendements
            if str(amendement.num) in source.getall(key)
        ]

    def check_amendements_are_all_on_my_table(
        self, amendements: List[Amendement]
    ) -> None:
        are_all_on_my_table = all(
            amendement.location.user_table.user == self.request.user
            if amendement.location.user_table
            else False
            for amendement in amendements
        )
        if are_all_on_my_table:
            return

        message = (
            "Tous les amendements doivent être sur votre espace de travail "
            "pour pouvoir les modifier."
        )
        self.request.session.flash(Message(cls="danger", text=message))
        raise HTTPFound(location=self.my_table_url)

    def check_amendements_have_all_same_reponse_or_empty(
        self, amendements: List[Amendement]
    ) -> bool:
        reponses = (amendement.user_content.as_tuple() for amendement in amendements)
        non_empty_reponses = (reponse for reponse in reponses if not reponse.is_empty)

        if len(set(non_empty_reponses)) > 0:  # all the same (1) or all empty (0)
            return False
        return True

    def get_amendement_only_or_first_reponse(
        self, amendements: List[Amendement]
    ) -> Any:
        for amendement in amendements:
            if not amendement.user_content.as_tuple().is_empty:
                return amendement
        return None


@view_config(context=LectureResource, name="start_editing_copy", renderer="json")
def start_editing(context: LectureResource, request: Request) -> dict:
    nums = request.GET.getall("nums")
    for num in nums:
        for amendement in Batch.expanded_batches(
            [Amendement.get(context.model(joinedload("amendements")), num)]
        ):
            amendement.start_editing()
    return {}


@view_config(context=LectureResource, name="stop_editing_copy", renderer="json")
def stop_editing(context: LectureResource, request: Request) -> dict:
    nums = request.GET.getall("nums")
    for num in nums:
        for amendement in Batch.expanded_batches(
            [Amendement.get(context.model(joinedload("amendements")), num)]
        ):
            amendement.stop_editing()
    return {}
