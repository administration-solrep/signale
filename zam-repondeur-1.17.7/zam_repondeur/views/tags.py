from markupsafe import Markup
from pyramid.httpexceptions import HTTPFound
from pyramid.request import Request
from pyramid.response import Response
from pyramid.view import view_config, view_defaults
from sqlalchemy import asc

from zam_repondeur.data_sanitize import get_as_int_or_none
from zam_repondeur.message import Message
from zam_repondeur.models import DBSession
from zam_repondeur.models.amendement import AmendementTag
from zam_repondeur.resources import TagsCollection
from zam_repondeur.services.clean import clean_all_html


@view_defaults(context=TagsCollection)
class TagsCollectionView:
    def __init__(self, context: TagsCollection, request: Request) -> None:
        self.context = context
        self.request = request
        self.user_table = context.user_table_resource.model()
        self.lecture = self.user_table.lecture
        self.lecture_resource = self.context.user_table_resource.lecture_resource

    @view_config(request_method="GET", renderer="table_tags.html")
    def get(self) -> dict:
        tags = (
            DBSession.query(AmendementTag)
            .filter(AmendementTag.user_table == self.user_table)
            .order_by(asc(AmendementTag.label))
            .all()
        )
        return {
            "tags": tags,
            "lecture": self.lecture,
            "dossier_resource": self.lecture_resource.dossier_resource,
            "current_tab": "table",
        }


@view_defaults(context=TagsCollection)
class TagAddForm:
    def __init__(self, context: TagsCollection, request: Request) -> None:
        self.context = context
        self.request = request
        self.user_table = context.user_table_resource.model()
        self.lecture = self.user_table.lecture

    @view_config(request_method="POST", name="add")
    def post(self) -> Response:
        label_not_clean = self.request.POST.get("label").strip()
        label_cleaned = clean_all_html(label_not_clean)
        label = Markup(label_cleaned).striptags()
        if not label:
            self.request.session.flash(
                Message(
                    cls="error",
                    text=(f"Erreur : vous devez renseigner un nom pour créer le tag."),
                )
            )
        else:
            tags_with_label = (
                DBSession.query(AmendementTag)
                .filter(
                    AmendementTag.user_table == self.user_table,
                    AmendementTag.label == label,
                )
                .all()
            )
            if tags_with_label:
                self.request.session.flash(
                    Message(cls="error", text=(f"Le tag « {label} » existe déjà."),)
                )
            else:
                tag = AmendementTag.get_or_create(
                    label=label, user_table=self.user_table
                )
                self.request.session.flash(
                    Message(
                        cls="success",
                        text=(f"Tag « {tag.label} » ajouté à l'espace de travail."),
                    )
                )

        return HTTPFound(location=self.request.resource_url(self.context))


@view_defaults(context=TagsCollection)
class TagEditForm:
    def __init__(self, context: TagsCollection, request: Request) -> None:
        self.context = context
        self.request = request
        self.user_table = context.user_table_resource.model()
        self.lecture = self.user_table.lecture

    @view_config(request_method="POST", name="edit")
    def post(self) -> Response:
        pk = get_as_int_or_none(self.request.POST.get("pk"))
        label_not_clean = self.request.POST.get("label").strip()
        label_cleaned = clean_all_html(label_not_clean)
        label = Markup(label_cleaned).striptags()

        tag = (
            DBSession.query(AmendementTag).filter(AmendementTag.pk == pk).one_or_none()
        )

        if not label:
            self.request.session.flash(
                Message(
                    cls="error",
                    text=(
                        f"Erreur : vous devez renseigner un nom pour modifier le tag."
                    ),
                )
            )
            return HTTPFound(location=self.request.resource_url(self.context))
        else:
            if "submit-edit" in self.request.POST:
                tags_with_label = (
                    DBSession.query(AmendementTag)
                    .filter(
                        AmendementTag.user_table == self.user_table,
                        AmendementTag.label == label,
                    )
                    .all()
                )
                if tags_with_label:
                    self.request.session.flash(
                        Message(cls="error", text=(f"Le tag « {label} » existe déjà."),)
                    )
                    return HTTPFound(location=self.request.resource_url(self.context))

                if not tag:
                    self.request.session.flash(
                        Message(cls="error", text=(f"Problème lors du traitement."),)
                    )
                    return HTTPFound(location=self.request.resource_url(self.context))

                tag.label = label
                DBSession.add(tag)
                self.request.session.flash(
                    Message(cls="success", text=(f"Tag « {tag.label} » modifié."),)
                )

        if "submit-delete" in self.request.POST:
            if not tag:
                self.request.session.flash(
                    Message(cls="error", text=(f"Problème lors du traitement."),)
                )
                return HTTPFound(location=self.request.resource_url(self.context))

            DBSession.delete(tag)
            self.request.session.flash(
                Message(cls="success", text=(f"Tag « {label} » supprimé."),)
            )

        return HTTPFound(location=self.request.resource_url(self.context))
