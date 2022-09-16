import os
from tempfile import NamedTemporaryFile
from typing import List

from pyramid.httpexceptions import HTTPBadRequest, HTTPFound
from pyramid.request import Request
from pyramid.response import FileResponse, Response
from pyramid.view import view_config, view_defaults
from sqlalchemy.orm import joinedload, load_only, subqueryload

from zam_repondeur.message import Message
from zam_repondeur.models import Batch
from zam_repondeur.models.events.import_export import ExportExcel, ExportJSON, ExportPDF, StartExportPDF
from zam_repondeur.resources import ImportExportLecture, LectureResource
from zam_repondeur.services.import_export.json import export_json
from zam_repondeur.services.import_export.pdf import (
    write_pdf,
    write_pdf_multiple,
    WritePdfSplitMode,
    WritePdfGEnerationMode,
)
from zam_repondeur.services.import_export.xlsx import export_xlsx
from zam_repondeur.tasks.asynchrone import export_lecture_pdf

DOWNLOAD_FORMATS = {
    "json": "application/json",
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


AMDT_OPTIONS = [
    joinedload("user_content"),
    joinedload("location").options(
        joinedload("user_table").joinedload("user").load_only("email", "name")
    ),
    joinedload("article").options(
        load_only("lecture_pk", "mult", "num", "pos", "type"),
        joinedload("user_content"),
    ),
]

EXPORT_OPTIONS = [
    subqueryload("amendements").options(*AMDT_OPTIONS),
    subqueryload("articles").joinedload("user_content"),
]

PDF_OPTIONS = [
    joinedload("dossier").load_only("titre"),
    subqueryload("articles").options(
        joinedload("user_content"),
        subqueryload("amendements").options(
            subqueryload("children"),
            joinedload("user_content").defer("comments"),
            *AMDT_OPTIONS,
        ),
    ),
]


@view_defaults(context=ImportExportLecture)
class Downloads:
    def __init__(self, context: ImportExportLecture, request: Request) -> None:
        self.context = context
        self.request = request

    @view_config(request_method="POST", name="download_amendements")
    def post(self) -> Response:
        fmt: str = self.request.POST.get("format")

        if fmt not in DOWNLOAD_FORMATS.keys():
            raise HTTPBadRequest(f'Invalid value "{fmt}" for "format" param')

        options = PDF_OPTIONS if fmt == "pdf" else EXPORT_OPTIONS
        lecture = self.context.parent.model(*options)

        with NamedTemporaryFile() as file_:
            tmp_file_path = os.path.abspath(file_.name)

            if fmt == "json":
                export_json(lecture=lecture, filename=tmp_file_path)
                ExportJSON.create(lecture=lecture, request=self.request)
            elif fmt == "xlsx":
                export_xlsx(filename=tmp_file_path, amendements=lecture.amendements)
                ExportExcel.create(lecture=lecture, request=self.request)
            elif fmt == "pdf":
                StartExportPDF.create(lecture=lecture, request=None, user=self.request.user)
                form_art = self.request.POST.getall("articles") or ["all"]
                articles = (
                    []
                    if "all" in form_art
                    else [a for a in sorted(lecture.articles) if a.url_key in form_art]
                )
                if len(articles) != 1 and len(lecture.articles) > 1:
                    # On a exporté tous les articles ou plusieurs,
                    # l'export passe en asynchrone
                    export_lecture_pdf(
                        lecture.pk,
                        self.request.user.pk,
                        articles_pk=[a.pk for a in articles],
                    )
                    self.request.session.flash(
                        Message(
                            cls="success",
                            text="Votre demande d’export du dossier de banc a bien été \
prise en compte. Vous recevrez un courriel dès que le document sera disponible au \
téléchargement.",
                        )
                    )
                    return HTTPFound(location=self.request.resource_url(self.context))
                # Synchrone, force le mode complet, in process
                write_pdf(
                    context={"lecture": lecture, "articles": articles},
                    filename=tmp_file_path,
                    registry=self.request.registry,
                    split_mode=int(WritePdfSplitMode.WHOLE),
                    generation_mode=int(WritePdfGEnerationMode.INLINE),
                )
                ExportPDF.create(lecture=lecture, request=self.request, nbr_article=len(articles))
            response = FileResponse(tmp_file_path)
            attach_name = (
                f"lecture-{lecture.chambre}-{lecture.texte.numero}-"
                f"{lecture.organe}.{fmt}"
            )
            response.content_type = DOWNLOAD_FORMATS[fmt]
            response.headers[
                "Content-Disposition"
            ] = f'attachment; filename="{attach_name}"'

            return response


@view_config(context=LectureResource, name="export_pdf")
def export_pdf(context: LectureResource, request: Request) -> Response:

    lecture = context.model(*PDF_OPTIONS)

    try:
        nums: List[int] = [int(num) for num in request.params.getall("nums")]
    except ValueError:
        raise HTTPBadRequest()

    amendements = [
        amendement
        for amendement in (lecture.find_amendement(num) for num in nums)
        if amendement is not None
    ]
    expanded_amendements = list(Batch.expanded_batches(amendements))

    with NamedTemporaryFile() as file_:

        tmp_file_path = os.path.abspath(file_.name)

        write_pdf_multiple(
            amendements=amendements, filename=tmp_file_path, registry=request.registry,
        )

        response = FileResponse(tmp_file_path)
        attach_name = (
            f"amendement{'s' if len(expanded_amendements) > 1 else ''}-"
            f"{','.join(str(amdt.num) for amdt in expanded_amendements)}-"
            f"{lecture.chambre}-{lecture.texte.numero}-"
            f"{lecture.organe}.pdf"
        )
        response.content_type = "application/pdf"
        response.headers[
            "Content-Disposition"
        ] = f'attachment; filename="{attach_name}"'
        return response
