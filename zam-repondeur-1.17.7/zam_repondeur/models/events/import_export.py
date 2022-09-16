from string import Template
from typing import Any, Counter, Optional

from pyramid.request import Request
from pyramid.threadlocal import get_current_registry

from ..dossier import Dossier
from ..lecture import Lecture
from ..users import User
from .dossier import DossierEvent
from .lecture import LectureEvent




class ImportExportLectureEvent(LectureEvent):
    details_template = Template("")

    def __init__(
            self, lecture: Lecture, request: Optional[Request] = None, **kwargs: Any
    ):
        super().__init__(lecture=lecture, request=request, **kwargs)


class ImportExportDossierEvent(DossierEvent):
    details_template = Template("")

    def __init__(
            self, dossier: Dossier, request: Optional[Request] = None, **kwargs: Any
    ):
        super().__init__(dossier=dossier, request=request, **kwargs)


class ReponsesImportees(ImportExportLectureEvent):
    __mapper_args__ = {"polymorphic_identity": "reponses_importees"}
    icon = "document"

    summary_template = Template(
        "<abbr title='$email'>$user</abbr> a importé des réponses d’un fichier CSV."
    )

    def __init__(self, lecture: Lecture, request: Request) -> None:
        super().__init__(lecture=lecture, request=request)

    def apply(self) -> None:
        pass


class ReponsesImporteesJSON(ImportExportLectureEvent):
    __mapper_args__ = {"polymorphic_identity": "reponses_importees_json"}
    icon = "document"

    def __init__(
            self, lecture: Lecture, request: Request, is_async: bool = False
    ) -> None:
        super().__init__(lecture=lecture, request=request)
        self.data["is_async"] = is_async

    @property
    def summary_template(self) -> Template:
        is_async = self.data.get("is_async", False)
        if is_async:
            return Template(
                "<abbr title='$email'>$user</abbr> a fait une demande \
d'import d'un fichier JSON."
            )
        else:
            return Template(
                "<abbr title='$email'>$user</abbr> a importé des réponses d’un \
fichier JSON."
            )

    def apply(self) -> None:
        pass

    @property
    def is_active(self) -> bool:
        is_async = self.data.get("is_async", False)
        return not is_async


class ResultatsImportJSON(ImportExportLectureEvent):
    __mapper_args__ = {"polymorphic_identity": "resultats_import_json"}
    icon = "document"

    def __init__(
            self,
            lecture: Lecture,
            request: Optional[Request],
            counter: Counter,
            **kwargs: Any,
    ) -> None:
        super().__init__(lecture=lecture, request=request, **kwargs)
        self.data["counter"] = counter

    @property
    def summary_template(self) -> Template:
        counter = self.data["counter"]
        message = ""
        if counter["amendements"] or counter["reponses"] or counter["articles"]:
            nb_amdt = (
                f" pour {counter['amendements']} amendement(s)"
                if counter["amendements"]
                else ""
            )
            if counter["reponses"]:
                message += (
                    f"{counter['reponses']} réponse(s) chargée(s) avec succès{nb_amdt}"
                )
                if counter["articles"]:
                    message += (
                        f", {counter['articles']} article(s) chargé(s) avec succès"
                    )
                message += "<br/>"
            elif counter["articles"]:
                message = f"{counter['articles']} article(s) chargé(s) avec succès<br/>"
        else:
            if not counter["reponses_errors"] and not counter["articles_errors"]:
                message += "Aucun élément à importer"

        if counter["reponses_errors"] or counter["articles_errors"]:
            message += "Le fichier de sauvegarde n’a pas pu être chargé :<br/>"
            if counter["reponses_errors"]:
                message += f" pour {counter['reponses_errors']} amendement(s)"
                if counter["articles_errors"]:
                    message += f" et {counter['articles_errors']} article(s)"
                message += "<br/>"
            elif counter["articles_errors"]:
                message += f" pour {counter['articles_errors']} article(s)<br/>"

        return Template(
            f"<abbr title='$email'>$user</abbr> a importé les éléments suivants :<br/>\
{message}"
        )

    def apply(self) -> None:
        pass


class AmendementsRecuperesLiasse(ImportExportLectureEvent):
    __mapper_args__ = {"polymorphic_identity": "amendements_recuperes_liasse"}
    icon = "document"

    @property
    def summary_template(self) -> Template:
        count = self.data["count"]
        base = "<abbr title='$email'>$user</abbr> a importé une liasse XML."
        if count == 1:
            message = "1 nouvel amendement récupéré."
        else:
            message = f"{count} nouveaux amendements récupérés."
        return Template(f"{base} : {message}")

    def __init__(self, lecture: Lecture, count: int, request: Request) -> None:
        super().__init__(lecture=lecture, count=count, request=request)

    def apply(self) -> None:
        pass


class ExportExcel(ImportExportLectureEvent):
    __mapper_args__ = {"polymorphic_identity": "export_excel"}
    icon = "document"

    summary_template = Template(
        "<abbr title='$email'>$user</abbr> a exporté un tableau au format Excel."
    )

    def __init__(self, lecture: Lecture, request: Request) -> None:
        super().__init__(lecture=lecture, request=request)

    def apply(self) -> None:
        pass


class ExportPDF(ImportExportLectureEvent):
    __mapper_args__ = {"polymorphic_identity": "export_pdf"}
    icon = "document"

    def __init__(self, lecture: Lecture, request: Request, nbr_article, **kwargs: Any) -> None:
        super().__init__(lecture=lecture, request=request, nbr_article=nbr_article, **kwargs)
        self.data["nbr_article"] = nbr_article
        self.data["retention"] = int(
            int(get_current_registry().settings["zam.users.export_pdf_duration"])
            / 3600
        )

    @property
    def summary_template(self) -> Template:
        retention = self.data.get("retention", 24)
        nbrArticle = self.data.get("nbr_article")
        if nbrArticle == 1:
            return Template(
                f"<abbr title='{self.user.email}'>{self.user.name}\
                        </abbr> a exporté un dossier au format PDF.")
        else:
            return Template(
                f"L’export généré par <abbr title='{self.user.email}'>{self.user.name}\
            </abbr> est à présent disponible pour {retention}h.")


    def apply(self) -> None:
        pass


class StartExportPDF(ImportExportLectureEvent):
    __mapper_args__ = {"polymorphic_identity": "start_export_pdf"}
    icon = "document"

    summary_template = Template(
        "<abbr title='$email'>$user</abbr> a fait une demande d'export au format PDF."
    )

    def __init__(self, lecture: Lecture, request: Request, **kwargs: Any) -> None:
        super().__init__(lecture=lecture, request=request, **kwargs)

    def apply(self) -> None:
        pass


class ExportJSON(ImportExportLectureEvent):
    __mapper_args__ = {"polymorphic_identity": "export_json"}
    icon = "document"

    summary_template = Template(
        "<abbr title='$email'>$user</abbr> a exporté un fichier technique \
structuré au format JSON."
    )

    def __init__(self, lecture: Lecture, request: Request) -> None:
        super().__init__(lecture=lecture, request=request)

    def apply(self) -> None:
        pass


class ExportDossierZipStart(ImportExportDossierEvent):
    __mapper_args__ = {"polymorphic_identity": "export_dossier_zip_start"}
    icon = "document"

    summary_template = Template(
        "<abbr title='$email'>$user</abbr> a fait une demande d’export complet \
du dossier au format ZIP."
    )

    def __init__(self, dossier: Dossier, request: Request) -> None:
        super().__init__(dossier=dossier, request=request)

    def apply(self) -> None:
        pass


class ExportDossierZipReady(ImportExportDossierEvent):
    __mapper_args__ = {"polymorphic_identity": "export_dossier_zip_ready"}
    icon = "document"

    def __init__(self, dossier: Dossier, user: User) -> None:
        super().__init__(dossier=dossier, request=None, user=user)
        self.data["retention"] = int(
            int(get_current_registry().settings["zam.users.export_dossier_duration"])
            / 3600
        )

    @property
    def summary_template(self) -> Template:
        retention = self.data.get("retention", 24)
        return Template(
            f"L’export généré par <abbr title='{self.user.email}'>{self.user.name}\
</abbr> est à présent disponible pour {retention}h."
        )

    def apply(self) -> None:
        pass


class ImportDossierZipStart(ImportExportDossierEvent):
    __mapper_args__ = {"polymorphic_identity": "import_dossier_zip_start"}
    icon = "document"

    summary_template = Template(
        "<abbr title='$email'>$user</abbr> a fait une demande d’import complet \
du dossier au format ZIP."
    )

    def __init__(self, dossier: Dossier, request: Request) -> None:
        super().__init__(dossier=dossier, request=request)

    def apply(self) -> None:
        pass


class ImportDossierZipEnd(ImportExportDossierEvent):
    __mapper_args__ = {"polymorphic_identity": "import_dossier_zip_end"}
    icon = "document"

    def __init__(
            self,
            dossier: Dossier,
            user: User,
            lecture: str,
            counter: Counter,
            link_lecture: str,
    ) -> None:
        super().__init__(dossier=dossier, request=None, user=user, lecture=lecture)
        self.data["counter"] = counter
        self.data["name_lecture"] = lecture
        self.data["link"] = link_lecture

    @property
    def summary_template(self) -> Template:
        lecture = self.data["name_lecture"]
        counter = self.data["counter"]
        link = self.data["link"]

        message = ""
        if counter["amendements"] or counter["reponses"] or counter["articles"]:
            nb_amdt = (
                f" pour {counter['amendements']} amendement(s)"
                if counter["amendements"]
                else ""
            )
            if counter["reponses"]:
                message += (
                    f"{counter['reponses']} réponse(s) chargée(s) avec succès{nb_amdt}"
                )
                if counter["articles"]:
                    message += (
                        f", {counter['articles']} article(s) chargé(s) avec succès"
                    )
                message += "<br/>"
            elif counter["articles"]:
                message = f"{counter['articles']} article(s) chargé(s) avec succès<br/>"
        else:
            if not counter["reponses_errors"] and not counter["articles_errors"]:
                message += "Aucun élément à importer"

        if counter["reponses_errors"] or counter["articles_errors"]:
            message += "Le fichier de sauvegarde n’a pas pu être chargé :<br/>"
            if counter["reponses_errors"]:
                message += f" pour {counter['reponses_errors']} amendement(s)"
                if counter["articles_errors"]:
                    message += f" et {counter['articles_errors']} article(s)"
                message += "<br/>"
            elif counter["articles_errors"]:
                message += f" pour {counter['articles_errors']} article(s)<br/>"

        return Template(
            f"<abbr title='$email'>$user</abbr> a importé, pour la lecture \
<a href='{link}'>{lecture}</a>, les éléments suivants :<br/>{message}"
        )

    def apply(self) -> None:
        pass


class ImportDossierZipLectureNotFound(ImportExportDossierEvent):
    __mapper_args__ = {"polymorphic_identity": "import_dossier_zip_lecture_not_found"}
    icon = "document"

    def __init__(self, dossier: Dossier, user: User, lecture: Lecture) -> None:
        super().__init__(dossier=dossier, request=None, user=user)
        self.data["lecture"] = f"{lecture}"
        self.data["lecture_json"] = f"{dossier.slug}/{lecture.zip_key}.json"

    @property
    def summary_template(self) -> Template:
        lecture = self.data["lecture"]
        lecture_json = self.data["lecture_json"]
        return Template(
            f"Lors de l’import complet, le fichier json {lecture_json} \
de la lecture {lecture} n’a pas pu être trouvé."
        )

    def apply(self) -> None:
        pass
