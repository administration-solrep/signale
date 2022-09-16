from typing import Any, List, Optional

from pyramid.httpexceptions import HTTPForbidden, HTTPFound
from pyramid.request import Request
from pyramid.response import Response
from pyramid.view import view_config, view_defaults
from sqlalchemy.orm import joinedload, load_only, noload, subqueryload
from sqlalchemy.orm.exc import NoResultFound

from zam_repondeur.data_sanitize import get_as_email_or_none, get_as_slug_or_none
from zam_repondeur.mails import send_transfer_warnings
from zam_repondeur.message import Message
from zam_repondeur.models import (
    Amendement,
    Batch,
    DBSession,
    SharedTable,
    User,
    UserTable,
)
from zam_repondeur.models.amendement import AmendementTag
from zam_repondeur.models.events.amendement import (
    AmendementTransfere,
    TransfertDossierDeBanc,
)
from zam_repondeur.resources import TableResource


@view_defaults(context=TableResource)
class TableView:
    def __init__(self, context: TableResource, request: Request) -> None:
        self.context = context
        self.request = request
        self.lecture = context.lecture_resource.model(
            subqueryload("amendements")
            .joinedload("user_content")
            .load_only("avis", "objet", "reponse_hash")
        )

    @view_config(request_method="GET", renderer="table_detail.html")
    def get(self) -> dict:
        table = self.context.model(
            subqueryload("amendements_locations").options(
                load_only("amendement_pk"),
                joinedload("amendement").options(
                    load_only(
                        "article_pk",
                        "auteur",
                        "groupe",
                        "id_identique",
                        "lecture_pk",
                        "mission_titre",
                        "num",
                        "parent_pk",
                        "position",
                        "rectif",
                        "sort",
                    ),
                    joinedload("user_content").load_only(
                        "avis", "objet", "reponse_hash"
                    ),
                    joinedload("location").options(
                        load_only("batch_pk"),
                        subqueryload("tags").options(
                            load_only("label", "user_table_pk")
                        ),
                        subqueryload("batch")
                        .joinedload("amendements_locations")
                        .options(
                            load_only("amendement_pk"),
                            joinedload("amendement").load_only("num", "rectif"),
                        ),
                    ),
                    joinedload("article").load_only(
                        "lecture_pk", "type", "num", "mult", "pos"
                    ),
                ),
            )
        )

        history_query = (
            DBSession.query(Amendement)
            .filter(
                Amendement.pk.in_(  # type: ignore
                    amdt.pk for amdt in table.user_table_history
                )
            )
            .options(
                subqueryload("location").options(
                    load_only("amendement_pk"),
                    joinedload("amendement").options(
                        load_only("pk", "num", "rectif",),
                        noload("user_content"),
                        joinedload("location").options(
                            load_only("batch_pk"),
                            noload("tags"),
                            subqueryload("batch")
                            .joinedload("amendements_locations")
                            .options(
                                load_only("amendement_pk"),
                                joinedload("amendement").load_only("num", "rectif"),
                            ),
                        ),
                        joinedload("article").load_only(
                            "lecture_pk", "type", "num", "mult", "pos"
                        ),
                    ),
                )
            )
        )

        return {
            "lecture": self.lecture,
            "lecture_resource": self.context.lecture_resource,
            "dossier_resource": self.context.lecture_resource.dossier_resource,
            "current_tab": "table",
            "table": table,
            "all_amendements": list(set(Batch.expanded_batches(table.amendements))),
            "collapsed_amendements": Batch.collapsed_batches(table.amendements),
            "is_owner": table.user.email == self.request.user.email,
            "table_url": self.request.resource_url(
                self.context.parent[self.request.user.email]
            ),
            "index_url": self.request.resource_url(
                self.context.lecture_resource["amendements"]
            ),
            "check_url": self.request.resource_path(self.context, "check"),
            "history": Batch.collapsed_batches(history_query.all()),
            "tags": sorted(table.tags, key=lambda x: x.label.lower(), reverse=False),  # type: ignore[no-any-return] # noqa
        }

    @view_config(request_method="POST", permission="active")
    def post(self) -> Response:
        """
        Transfer amendement(s) from this table to another one, or back to the index
        Transfer amendement(s) to 'Dossier de banc'
        """
        nums: List[int] = self.request.POST.getall("nums")
        transfert_dossier_de_banc: bool = False
        if "submit-index" in self.request.POST:
            target = ""
        elif "submit-dossier-banc" in self.request.POST:
            target = ""
            transfert_dossier_de_banc = True
        elif "submit-table" in self.request.POST:
            target = self.request.user.email
            if "direct_transfer" in self.request.POST:
                table = self.context.model()
                if target != table.user.email:
                    self.request.session.flash(
                        Message(
                            cls="warning",
                            text="""Le transfert direct doit s'effectuer
                            sur votre espace de travail.""",
                        )
                    )
                    return HTTPFound(location=self.get_back_url)
        else:
            target = self.request.POST.get("target")
            if not target:
                self.request.session.flash(
                    Message(
                        cls="warning", text="Veuillez sélectionner un destinataire."
                    )
                )
                return HTTPFound(
                    location=self.request.resource_url(
                        self.context.lecture_resource,
                        "transfer_amendements",
                        query={"nums": nums},
                    )
                )

        amendements = DBSession.query(Amendement).filter(
            Amendement.lecture == self.lecture, Amendement.num.in_(nums)  # type: ignore
        )

        if transfert_dossier_de_banc:
            self.transfer_dossier_de_banc(amendements)
        else:
            email_warn_amdts = [
                amdt
                for amdt in Batch.collapsed_batches(amendements)
                if amdt.position_banc_as_int == 2
            ]
            self.transfer_amendements_for_work(
                target, amendements,
            )
            send_transfer_warnings(
                self.lecture.dossier.team.coordinators,
                email_warn_amdts,
                self.context.lecture_resource,
                self.request,
            )

        if target != self.request.user.email and self.request.POST.get("from_index"):
            amendements_collection = self.context.lecture_resource["amendements"]
            next_location = self.request.resource_url(amendements_collection)
        else:
            table = self.context.model()
            table_resource = self.context.parent[table.user.email]
            next_location = self.request.resource_url(table_resource)
        return HTTPFound(location=next_location)

    def transfer_dossier_de_banc(self, amendements: List[Amendement]) -> None:
        for amendement in Batch.expanded_batches(amendements):
            self.remove_all_tags(amendement)
            amendement.stop_editing()
            if not amendement.location.date_dossier_de_banc:
                TransfertDossierDeBanc.create(
                    amendement=amendement, request=self.request
                )

    def transfer_amendements_for_work(
        self, target: str, amendements: List[Amendement],
    ) -> None:
        target_user_table = self.get_target_user_table(get_as_email_or_none(target))
        target_shared_table = self.get_target_shared_table(get_as_slug_or_none(target))
        for amendement in Batch.expanded_batches(amendements):
            old = amendement.table_name_with_email
            if target_shared_table:
                if target and amendement.location.shared_table is target_shared_table:
                    continue
                self.remove_all_tags(amendement)
                new = target_shared_table.titre
                amendement.location.shared_table = target_shared_table
                amendement.location.user_table = None
            else:
                if target and amendement.location.user_table is target_user_table:
                    continue
                self.remove_all_tags(amendement)
                new = str(target_user_table.user) if target_user_table else ""
                amendement.location.user_table = target_user_table
                amendement.location.shared_table = None
            amendement.stop_editing()
            amendement.location.date_dossier_de_banc = None
            AmendementTransfere.create(
                amendement=amendement,
                old_value=old,
                new_value=new,
                request=self.request,
            )

    def get_target_user_table(self, target: Optional[str]) -> Optional[UserTable]:
        if target is None:
            return None
        if target == self.request.user.email:
            target_user = self.request.user
        else:
            target_user = DBSession.query(User).filter(User.email == target).one()
        if (
            target_user
            not in self.context.lecture_resource.dossier_resource.dossier.team.users
        ):
            raise HTTPForbidden("Transfert non autorisé")
        return target_user.table_for(self.lecture)

    def get_target_shared_table(self, target: Optional[str]) -> Optional[SharedTable]:
        if target is None:
            return None
        try:
            result: Optional[SharedTable] = (
                DBSession.query(SharedTable)
                .filter(SharedTable.slug == target, SharedTable.lecture == self.lecture)
                .one()
            )
        except NoResultFound:
            raise HTTPForbidden("Corbeille non disponible.")
        return result

    @staticmethod
    def remove_all_tags(amendement: Amendement) -> None:
        if amendement.location.user_table and amendement.location.tags:
            tags: List[AmendementTag] = [tag for tag in amendement.location.tags]
            for tag in tags:
                amendement.location.tags.remove(tag)

    @property
    def get_back_url(self) -> Any:
        if "back" in self.request.POST:
            return self.request.POST.get("back")
        return self.request.resource_url(self.context.lecture_resource, "amendements")


@view_config(context=TableResource, name="check", renderer="json")
def table_check(context: TableResource, request: Request) -> dict:
    table = context.model()
    amendements_as_string = request.GET["current"]
    updated = table.amendements_as_string
    if amendements_as_string != updated:
        return {"updated": updated}
    else:
        return {}


@view_config(context=TableResource, name="add_tag", renderer="json")
def add_tag(context: TableResource, request: Request) -> dict:
    """ id="amdt-num" """

    if request.user != context.model().user:
        request.response.status = 403  # type: ignore
        return {
            "error": f"Vous n'êtes pas autorisé à modifier l'espace \
de travail de {context.model().user}"
        }

    try:
        tag_pk = int(request.json_body["tag_pk"])  # type: ignore
        amdt_num = int(request.json_body["amdt_num"])  # type: ignore
    except Exception:
        request.response.status = 500  # type: ignore
        return {"error": f"Mauvais paramètre"}

    amdt = context.lecture_resource.lecture.find_amendement(amdt_num)

    if amdt:
        if amdt.location not in context.model().amendements_locations:
            request.response.status = 403  # type: ignore
            return {
                "error": f"Vous n'êtes pas autorisé à modifier un amendement \
qui n'est pas sur votre espace de travail"
            }
        tag = (
            DBSession.query(AmendementTag)
            .filter(AmendementTag.pk == tag_pk)
            .one_or_none()
        )
        if tag:
            amdt.location.tags.append(tag)
        else:
            request.response.status = 500  # type: ignore
            return {"error": f'Le tag "{tag_pk}" n\'existe pas'}
    return {}


@view_config(context=TableResource, name="remove_tag", renderer="json")
def remove_tag(context: TableResource, request: Request) -> dict:
    """ id="amdt-num" """

    if request.user != context.model().user:
        request.response.status = 403  # type: ignore
        return {
            "error": f"Vous n'êtes pas autorisé à modifier l'espace \
de travail de {context.model().user}"
        }

    try:
        tag_pk = int(request.json_body["tag_pk"])  # type: ignore
        amdt_num = int(request.json_body["amdt_num"])  # type: ignore
    except Exception:
        request.response.status = 500  # type: ignore
        return {"error": f"Mauvais paramètre"}

    amdt = context.lecture_resource.lecture.find_amendement(amdt_num)

    if amdt:
        if amdt.location not in context.model().amendements_locations:
            request.response.status = 403  # type: ignore
            return {
                "error": f"Vous n'êtes pas autorisé à modifier un amendement \
qui n'est pas sur votre espace de travail"
            }
        tag = (
            DBSession.query(AmendementTag)
            .filter(AmendementTag.pk == tag_pk)
            .one_or_none()
        )
        if tag:
            amdt.location.tags.remove(tag)
        else:
            request.response.status = 500  # type: ignore
            return {"error": f'Le tag "{tag_pk}" n\'existe pas'}
    return {}
