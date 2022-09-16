from typing import List, Set, Tuple

from pyramid.request import Request
from pyramid.view import view_config, view_defaults
from sqlalchemy.orm import joinedload, load_only, noload, subqueryload

from zam_repondeur.models import Amendement, Batch, DBSession, SharedTable, User
from zam_repondeur.models.users import Team
from zam_repondeur.resources import LectureResource


@view_defaults(
    context=LectureResource,
    renderer="transfer_amendements.html",
    name="transfer_amendements",
)
class TransferAmendements:
    def __init__(self, context: LectureResource, request: Request) -> None:
        self.context = context
        self.request = request
        if(request.POST):
            self.from_index = bool(request.POST.get("from_index"))
            self.from_search = bool(request.POST.get("from_search"))
            self.direct_transfer = bool(request.POST.get("direct_transfer"))
            self.amendements_nums: list = self.request.POST.getall("nums")
        elif(request.GET):
            self.from_index = bool(request.GET.get("from_index"))
            self.from_search = bool(request.GET.get("from_search"))
            self.direct_transfer = bool(request.GET.get("direct_transfer"))
            self.amendements_nums: list = self.request.GET.getall("nums")
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

    @view_config(request_method="POST", permission="active")
    def post(self) -> dict:
        from_save = bool(self.request.POST.get("from_save"))
        my_table = self.request.user.table_for(self.lecture)
        amendements = [
            amendement
            for amendement in self.lecture.amendements
            if str(amendement.num) in self.amendements_nums
        ]
        amendements_being_edited = []
        amendements_not_being_edited = []
        amendements_without_table = []
        amendements_with_shared_table = []
        amendements_on_dossier_de_banc = []
        amendements_on_my_table = []
        for amendement in Batch.collapsed_batches(amendements):
            if amendement.location.user_table:
                if amendement.location.user_table.user == self.request.user:
                    amendements_on_my_table.append(amendement)
                else:
                    if amendement.is_being_edited:
                        amendements_being_edited.append(amendement)
                    else:
                        amendements_not_being_edited.append(amendement)
            elif amendement.location.shared_table:
                amendements_with_shared_table.append(amendement)
            elif amendement.position_banc_as_int == 2:
                amendements_on_dossier_de_banc.append(amendement)
            else:
                amendements_without_table.append(amendement)
        amendements_with_table = (
            amendements_being_edited
            + amendements_not_being_edited
            + amendements_with_shared_table
            + amendements_on_my_table
        )
        show_transfer_to_myself = (
            amendements_without_table
            or amendements_with_shared_table
            or amendements_on_dossier_de_banc
            or not all(
                amendement.location.user_table is my_table
                for amendement in amendements_with_table
            )
        )
        show_transfer_to_index = (
            bool(amendements_with_table)
            or bool(amendements_on_dossier_de_banc)
            or bool(amendements_on_my_table)
        )
        return {
            "lecture": self.lecture,
            "dossier_resource": self.context.dossier_resource,
            "current_tab": "index",
            "amendements": amendements,
            "amendements_with_table": amendements_with_table,
            "amendements_being_edited": amendements_being_edited,
            "amendements_not_being_edited": amendements_not_being_edited,
            "amendements_with_shared_table": amendements_with_shared_table,
            "amendements_on_dossier_de_banc": amendements_on_dossier_de_banc,
            "amendements_without_table": amendements_without_table,
            "amendements_on_my_table": amendements_on_my_table,
            "users": self.target_users,
            "target_tables": self.target_tables(amendements_with_shared_table),
            "from_index": int(self.from_index),
            "from_search": int(self.from_search),
            "from_save": from_save,
            "show_transfer_to_index": show_transfer_to_index,
            "show_transfer_to_dossier_de_banc": not all(
                amdt.position_banc_as_int == 2 for amdt in amendements
            ),
            "show_transfer_to_myself": show_transfer_to_myself,
            "back_url": self.back_url,
            "direct_transfer": self.direct_transfer,
        }

    @view_config(request_method="GET", permission="active")
    def get(self) -> dict:
        from_save = bool(self.request.GET.get("from_save"))
        my_table = self.request.user.table_for(self.lecture)
        amendements = [
            amendement
            for amendement in self.lecture.amendements
            if str(amendement.num) in self.amendements_nums
        ]
        amendements_being_edited = []
        amendements_not_being_edited = []
        amendements_without_table = []
        amendements_with_shared_table = []
        amendements_on_dossier_de_banc = []
        amendements_on_my_table = []
        for amendement in Batch.collapsed_batches(amendements):
            if amendement.location.user_table:
                if amendement.location.user_table.user == self.request.user:
                    amendements_on_my_table.append(amendement)
                else:
                    if amendement.is_being_edited:
                        amendements_being_edited.append(amendement)
                    else:
                        amendements_not_being_edited.append(amendement)
            elif amendement.location.shared_table:
                amendements_with_shared_table.append(amendement)
            elif amendement.position_banc_as_int == 2:
                amendements_on_dossier_de_banc.append(amendement)
            else:
                amendements_without_table.append(amendement)
        amendements_with_table = (
            amendements_being_edited
            + amendements_not_being_edited
            + amendements_with_shared_table
            + amendements_on_my_table
        )
        show_transfer_to_myself = (
            amendements_without_table
            or amendements_with_shared_table
            or amendements_on_dossier_de_banc
            or not all(
                amendement.location.user_table is my_table
                for amendement in amendements_with_table
            )
        )
        show_transfer_to_index = (
            bool(amendements_with_table)
            or bool(amendements_on_dossier_de_banc)
            or bool(amendements_on_my_table)
        )
        return {
            "lecture": self.lecture,
            "dossier_resource": self.context.dossier_resource,
            "current_tab": "index",
            "amendements": amendements,
            "amendements_with_table": amendements_with_table,
            "amendements_being_edited": amendements_being_edited,
            "amendements_not_being_edited": amendements_not_being_edited,
            "amendements_with_shared_table": amendements_with_shared_table,
            "amendements_on_dossier_de_banc": amendements_on_dossier_de_banc,
            "amendements_without_table": amendements_without_table,
            "amendements_on_my_table": amendements_on_my_table,
            "users": self.target_users,
            "target_tables": self.target_tables(amendements_with_shared_table),
            "from_index": int(self.from_index),
            "from_search": int(self.from_search),
            "from_save": from_save,
            "show_transfer_to_index": show_transfer_to_index,
            "show_transfer_to_dossier_de_banc": not all(
                amdt.position_banc_as_int == 2 for amdt in amendements
            ),
            "show_transfer_to_myself": show_transfer_to_myself,
            "back_url": self.back_url,
            "direct_transfer": self.direct_transfer,
        }

    @property
    def target_users(self) -> List[Tuple[str, str]]:
        team: Team = self.lecture.dossier.team
        if team is not None:
            users = team.everyone_but_me(self.request.user)
        else:
            users = User.everyone_but_me(self.request.user)
        return [(user.email, str(user)) for user in users]

    def target_tables(
        self, amendements_with_shared_table: List[Amendement]
    ) -> List[SharedTable]:
        shared_tables: Set[SharedTable] = set(
            amendement.location.shared_table
            for amendement in amendements_with_shared_table
            if amendement.location.shared_table
        )
        if len(shared_tables) == 1:
            return SharedTable.all_but_me(list(shared_tables)[0], self.lecture)
        else:
            result: List[SharedTable] = DBSession.query(SharedTable).filter(
                SharedTable.lecture == self.lecture
            )
            return result

    @property
    def back_url(self) -> str:
        url: str = self.request.GET.get("back")
        if url is None:
            return self.request.resource_url(self.context["amendements"])
        return url
