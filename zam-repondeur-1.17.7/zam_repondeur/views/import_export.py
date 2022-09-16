import os
import shutil
import uuid
from datetime import date
from operator import itemgetter
from tempfile import NamedTemporaryFile

from pyramid.httpexceptions import HTTPFound
from pyramid.request import Request
from pyramid.response import FileResponse, Response
from pyramid.view import view_config, view_defaults
from sqlalchemy.orm import load_only, noload

from zam_repondeur.message import Message
from zam_repondeur.models import DBSession, SharedTable
from zam_repondeur.models.events.import_export import (
    ExportDossierZipStart,
    ImportDossierZipStart,
)
from zam_repondeur.resources import ImportExportDossier, ImportExportLecture
from zam_repondeur.services.dossiers import dossier_export_repository
from zam_repondeur.services.lectures import lecture_export_pdf_repository
from zam_repondeur.tasks.asynchrone import export_dossier, import_dossier_task


@view_defaults(context=ImportExportDossier)
class ImportExportDossierView:
    def __init__(self, context: ImportExportDossier, request: Request) -> None:
        self.context = context
        self.request = request
        self.dossier = self.context.parent.dossier
        self.dossier_resource = self.context.dossier_resource
        self.user = request.user

    @view_config(request_method="GET", renderer="dossier_import_export.html")
    def get(self) -> Response:
        if not self.has_export_permission:
            self.request.session.flash(
                Message(
                    cls="danger",
                    text="L’accès à cette page est réservé aux personnes autorisées.",
                )
            )
            return HTTPFound(location=self.request.resource_url(self.dossier_resource))
        return {
            "dossier": self.dossier,
            "dossier_resource": self.dossier_resource,
            "active": self.dossier.team.active,
            "current_tab": "import_export",
            "expire_file": dossier_export_repository.has_export_content(self.dossier),
        }

    @view_config(name="export_dossier")
    def export_dossier(self) -> Response:
        if not self.has_export_permission:
            self.request.session.flash(
                Message(
                    cls="danger",
                    text="L’accès à cette fonctionnalité est réservé aux \
personnes autorisées.",
                )
            )
        else:
            ExportDossierZipStart.create(self.dossier, self.request)
            export_dossier(self.dossier.pk, self.user.pk)
            self.request.session.flash(
                Message(
                    cls="success",
                    text="La demande d’export global a été prise en compte.",
                )
            )
        return HTTPFound(location=self.request.resource_url(self.dossier_resource))

    @view_config(request_method="POST", permission="active")
    def post(self) -> Response:
        if not self.user.is_admin:
            self.request.session.flash(
                Message(
                    cls="danger",
                    text="L’accès à cette fonctionnalité est réservé aux \
personnes autorisées.",
                )
            )
            return HTTPFound(location=self.request.resource_url(self.dossier_resource))

        # We cannot just do `if not POST["backup"]`, as FieldStorage does not want
        # to be cast to a boolean.
        if self.request.POST["backup"] == b"":
            self.request.session.flash(
                Message(cls="warning", text="Veuillez d’abord sélectionner un fichier")
            )
            return HTTPFound(location=self.request.resource_url(self.context))

        ImportDossierZipStart.create(self.dossier, self.request)
        upload_folder = self.request.registry.settings["zam.uploads_backup_dir"]
        try:
            input_file = self.request.POST["backup"].file
            file_path = os.path.join(upload_folder, "%s.import_zip" % uuid.uuid4())
            temp_file_path = file_path + "~"
            input_file.seek(0)
            with open(temp_file_path, "wb") as output_file:
                shutil.copyfileobj(input_file, output_file)
            os.rename(temp_file_path, file_path)
            zip_content = open(file_path, "rb").read()
            import_dossier_task(
                zip_content,
                self.dossier.pk,
                self.user.pk,
                self.request.resource_url(self.dossier_resource),
            )
            os.remove(file_path)

            self.request.session.flash(
                Message(
                    cls="success",
                    text="La demande d’import global a été prise en compte.",
                )
            )
        except ValueError as exc:
            self.request.session.flash(Message(cls="danger", text=str(exc)))

        return HTTPFound(location=self.request.resource_url(self.dossier_resource))

    @view_config(
        context=ImportExportDossier,
        name="journal",
        renderer="import_export_dossier_journal.html",
    )
    def journal_dossier(self) -> Response:
        if not self.has_export_permission:
            self.request.session.flash(
                Message(
                    cls="danger",
                    text="L’accès à cette page est réservé aux personnes autorisées.",
                )
            )
            return HTTPFound(location=self.request.resource_url(self.context))

        return {
            "dossier": self.dossier,
            "dossier_resource": self.dossier_resource,
            "current_tab": "import_export",
            "events": self.dossier.import_export_events,
            "today": date.today(),
            "is_admin": self.user.is_admin,
        }

    @property
    def has_export_permission(self) -> bool:
        return bool(self.user.is_admin or self.dossier.team.is_coordinator(self.user))


@view_defaults(context=ImportExportLecture)
class ImportExportLectureView:
    def __init__(self, context: ImportExportLecture, request: Request) -> None:
        self.context = context
        self.request = request
        self.lecture = self.context.parent
        self.lecture_resource = self.context.lecture_resource
        self.user = request.user

    @view_config(request_method="GET", renderer="lecture_import_export.html")
    def get(self) -> dict:
        lecture = self.lecture.model(noload("amendements"))
        shared_tables = (
            DBSession.query(SharedTable)
            .filter(SharedTable.lecture_pk == lecture.pk)
            .options(load_only("lecture_pk", "nb_amendements", "slug", "titre"))
        ).all()
        return {
            "lecture": lecture,
            "dossier_resource": self.lecture.dossier_resource,
            "active": lecture.dossier.team.active,
            "current_tab": "import_export",
            "shared_tables": shared_tables,
            "has_permission": self.has_permission,
            "export_data": sorted(
                lecture_export_pdf_repository.has_export_data(lecture),
                key=itemgetter("created_at"),
                reverse=True,
            ),
        }

    @view_config(request_method="POST")
    def post(self) -> Response:
        lecture = self.lecture.model(noload("amendements"))
        key: str = self.request.POST.get("download-key")
        export = lecture_export_pdf_repository.get_export_data(key=key)
        if not export:
            self.request.session.flash(
                Message(cls="error", text="Le fichier PDF a expiré.")
            )
            return HTTPFound(location=self.request.resource_url(self.context))

        date_str = export["created_at"].strftime("%Y%m%d_%H_%M_%S")
        with NamedTemporaryFile() as file_:
            tmp_file_path = os.path.abspath(file_.name)
            file_.write(export["export_content"])
            response = FileResponse(tmp_file_path)
            attach_name = f"{lecture.url_key}-{date_str}.pdf"
            response.content_type = "application/pdf"
            response.headers[
                "Content-Disposition"
            ] = f'attachment; filename="{attach_name}"'
            return response

    @view_config(
        context=ImportExportLecture,
        name="journal",
        renderer="import_export_lecture_journal.html",

    )
    def journal_lecture(self) -> Response:
        lecture = self.context.parent.lecture

        if not self.has_permission:
            self.request.session.flash(
                Message(
                    cls="danger",
                    text="L’accès à cette page est réservé aux personnes autorisées.",
                )
            )
            return HTTPFound(location=self.request.resource_url(self.context))

        return {
            "lecture": lecture,
            "dossier_resource": self.lecture.dossier_resource,
            "current_tab": "import_export",
            "events": lecture.import_export_events,
            "today": date.today(),
            "has_permission": self.has_permission,
        }

    @property
    def has_permission(self) -> bool:
        return bool(
            self.user.is_admin
            or self.lecture.lecture.dossier.team.is_coordinator(self.user)
        )
