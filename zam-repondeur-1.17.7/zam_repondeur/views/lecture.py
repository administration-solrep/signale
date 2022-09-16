from datetime import date
from typing import Dict, List

from pyramid.httpexceptions import HTTPFound
from pyramid.request import Request
from pyramid.response import Response
from pyramid.view import view_config, view_defaults
from sqlalchemy.orm import joinedload, load_only, noload, subqueryload

from zam_repondeur.message import Message
from zam_repondeur.models import DBSession, Lecture, SharedTable, get_one_or_create
from zam_repondeur.models.amendement import DOSSIER_DE_BANC
from zam_repondeur.models.events.lecture import RefreshLecture, SharedTableCreee
from zam_repondeur.resources import LectureResource, SharedTableCollection
from zam_repondeur.services.clean import clean_all_html
from zam_repondeur.tasks.fetch import fetch_amendements


@view_config(context=LectureResource, name="manual_refresh", permission="active")
def manual_refresh(context: LectureResource, request: Request) -> Response:
    lecture = context.model()
    if not request.user.is_admin and not lecture.dossier.team.is_coordinator(
        request.user
    ):
        request.session.flash(
            Message(
                cls="error",
                text="Le rafraichissement manuel des données "
                "est réservé aux personnes autorisées.",
            )
        )
        return HTTPFound(location=request.resource_url(context, "journal"))

    fetch_amendements(lecture.pk)
    # The progress is initialized even if the task is async for early feedback
    # to users and ability to disable the refresh button.
    # The total is doubled because we need to handle the dry_run.
    total = len(lecture.amendements) * 2 if lecture.amendements else 100
    lecture.set_fetch_progress(1, total)

    RefreshLecture(lecture=lecture, request=request)

    request.session.flash(
        Message(cls="success", text="Rafraîchissement des amendements en cours.")
    )
    amendements_collection = context["amendements"]
    return HTTPFound(location=request.resource_url(amendements_collection))


@view_config(context=LectureResource, name="journal", renderer="lecture_journal.html")
def lecture_journal(context: LectureResource, request: Request) -> Response:
    lecture = context.model(noload("amendements"), noload("articles"))
    allowed_to_refresh = request.user.is_admin or lecture.dossier.team.is_coordinator(
        request.user
    )
    return {
        "lecture": lecture,
        "dossier_resource": context.dossier_resource,
        "active": lecture.dossier.team.active,
        "current_tab": "journal",
        "today": date.today(),
        "settings": request.registry.settings,
        "allowed_to_refresh": allowed_to_refresh,
    }


@view_config(context=SharedTableCollection, renderer="lecture_corbeilles.html")
def lecture_corbeilles(context: SharedTableCollection, request: Request) -> Response:
    lecture = context.lecture_resource.model(
        noload("articles"),
        subqueryload("amendements").options(
            load_only("article_pk", "id_identique", "lecture_pk", "auteur", "sort"),
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
    stats = lecture.get_dossier_de_banc_stats()
    progress = 0
    total = sum(stats.values())
    if total:
        progress = int(stats[2] / total * 100)

    shared_tables = (
        DBSession.query(SharedTable)
        .filter(SharedTable.lecture_pk == lecture.pk)
        .options(load_only("lecture_pk", "nb_amendements", "slug", "titre"))
    ).all()
    return {
        "lecture": lecture,
        "dossier_resource": context.parent.dossier_resource,
        "active": lecture.dossier.team.active,
        "current_tab": "corbeilles",
        "shared_tables": shared_tables,
        "progress": progress,
        "total": total,
        "affiche_dossier_de_banc": total > 0,
        "current": stats[2],
    }


@view_config(context=LectureResource, name="progress_status", renderer="json")
def progress_status(context: LectureResource, request: Request) -> dict:
    lecture = context.model(noload("amendements"))
    return lecture.get_fetch_progress() or {}


@view_defaults(
    context=LectureResource, name="import_corbeilles", renderer="import_corbeilles.html"
)
class LectureImportCorbeilles:
    def __init__(self, context: LectureResource, request: Request) -> None:
        self.context = context
        self.request = request
        self.lecture = context.model(
            load_only("pk"), noload("articles"), noload("amendements"),
        )
        self.lectures = sorted(self.other_lectures)

    @view_config(request_method="GET", permission="active")
    def get(self) -> dict:
        return {
            "lecture": self.lecture,
            "dossier_resource": self.context.dossier_resource,
            "active": self.lecture.dossier.team.active,
            "current_tab": "corbeilles",
            "lectures": self.lectures,
            "shared_tables": self.all_shared_tables,
        }

    @view_config(request_method="POST", permission="active")
    def post(self) -> Response:
        if "corbeilles" not in self.request.POST:
            self.request.session.flash(
                Message(
                    cls="warning",
                    text=(
                        f"Pour pouvoir effectuer cette action, \
                    il faut sélectionner au moins une corbeille."
                    ),
                )
            )
            return HTTPFound(
                location=self.request.resource_url(self.context, "import_corbeilles")
            )

        corbeilles: List[str] = self.request.POST.getall("corbeilles")
        alert_reserved_name: List[str] = []
        alert_exists: List[str] = []
        success_created: List[str] = []
        for corbeille in corbeilles:
            titre = clean_all_html(corbeille)
            created: bool = False
            reserved_table_name: bool = titre.upper() == DOSSIER_DE_BANC.upper()
            if not reserved_table_name:
                table, created = get_one_or_create(
                    SharedTable, titre=titre, lecture=self.lecture
                )
            if created:
                SharedTableCreee.create(
                    lecture=self.lecture, titre=titre, request=self.request
                )
                success_created.append(titre)
            elif reserved_table_name:
                alert_reserved_name.append(titre)
            else:
                alert_exists.append(titre)

        alerts: List[str] = []
        if alert_reserved_name:
            alerts.append(
                f"Erreur d'import des corbeilles « {', '.join(alert_reserved_name)} » : \
le nom « {DOSSIER_DE_BANC} » est réservé…"
            )
        if alert_exists:
            alerts.append(
                f"Erreur d'import des corbeilles « {', '.join(alert_exists)} » : \
le nom existe déjà…"
            )

        if alerts:
            self.request.session.flash(
                Message(cls="warning", text=f"{'<br>'.join(alerts)}",)
            )
        else:
            self.request.session.flash(
                Message(
                    cls="success",
                    text=f"Les corbeilles « {', '.join(success_created)} » \
ont été créées avec succès.",
                )
            )

        return HTTPFound(
            location=self.request.resource_url(
                self.context, "corbeilles", anchor="shared-tables"
            )
        )

    @property
    def other_lectures(self) -> List[Lecture]:
        return [
            lecture
            for lecture in self.lecture.dossier.lectures
            if lecture != self.lecture
        ]

    @property
    def all_shared_tables(self) -> Dict[int, List[SharedTable]]:
        return {
            lecture.pk: (
                DBSession.query(SharedTable).filter(
                    SharedTable.lecture_pk == lecture.pk
                )
            ).all()
            for lecture in self.lectures
        }
