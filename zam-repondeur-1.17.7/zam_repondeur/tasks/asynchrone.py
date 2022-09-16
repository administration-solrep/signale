"""
NB: make sure tasks.huey.init_huey() has been called before importing this module
"""
import logging
import os
import shutil
from io import BytesIO, TextIOWrapper
from os.path import basename
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Dict, List, Optional, Tuple
from zipfile import ZIP_DEFLATED, ZipFile

from pyramid.threadlocal import get_current_registry
from pyramid_mailer import get_mailer
from sqlalchemy.orm import joinedload

from zam_repondeur.mails import (
    send_alert,
    send_dossier_deleted,
    send_export_dossier_notification,
    send_export_pdf_notification,
    send_import_dossier_notification,
    send_update_cache_completed,
)
from zam_repondeur.models import Article, DBSession, Dossier, Lecture, Parametres, User
from zam_repondeur.models.events.dossier import DossierSupprime
from zam_repondeur.models.events.dossiers_list import DossiersListSupprime
from zam_repondeur.models.events.import_export import (
    ExportDossierZipReady,
    ExportPDF,
    StartExportPDF,
    ImportDossierZipLectureNotFound,
)
from zam_repondeur.services.data import repository
from zam_repondeur.services.import_export.json import export_json, import_json_async
from zam_repondeur.services.import_export.pdf import (
    write_pdf,
    WritePdfSplitMode,
    WritePdfGEnerationMode,
)
from zam_repondeur.services.import_export.xlsx import (
    export_xlsx,
    get_user_list_workbook,
)
from zam_repondeur.tasks.huey import huey

logger = logging.getLogger(__name__)

RETRY_DELAY = 5 * 60  # 5 minutes


@huey.task(retries=3, retry_delay=RETRY_DELAY)
def export_dossier(dossier_pk: int, user_pk: int) -> None:
    from zam_repondeur.services.dossiers import dossier_export_repository

    with huey.lock_task(f"dossier-{dossier_pk}"):
        dossier = (
            DBSession.query(Dossier)
            .options(
                joinedload(Dossier.lectures)
                .joinedload(Lecture.articles)
                .joinedload(Article.amendements)
            )
            .filter(Dossier.pk == dossier_pk)
            .one_or_none()
        )
        if not dossier:
            logger.error(f"Dossier: {dossier_pk} introuvable")
            return
        user = DBSession.query(User).filter(User.pk == user_pk).one_or_none()
        if not user:
            logger.error(f"User: {user_pk} introuvable")
            return
        registry = get_current_registry()
        upload_path = registry.settings["zam.uploads_backup_dir"]
        folder_path = f"{upload_path}/{dossier.slug}"
        Path(folder_path).mkdir(parents=True, exist_ok=True)
        usuers_wb = get_user_list_workbook(dossier.team, f"{dossier.slug}")
        usuers_wb.save(f"{folder_path}/Equipe-{dossier.slug}.xlsx")
        split_mode = int(
            registry.settings.get(
                "zam.write_pdf.split_mode", WritePdfSplitMode.MULTIPLE_PDF_AT_ONCE,
            )
        )
        generation_mode = int(
            registry.settings.get(
                "zam.write_pdf.generation_mode", WritePdfGEnerationMode.CMDLINE
            )
        )
        for lecture in dossier.lectures:
            logger.info(
                f"Export lecture {lecture.zip_key} split_mode={split_mode}"
                f" generation_mode={generation_mode}"
            )
            export_xlsx(f"{folder_path}/{lecture.zip_key}.xlsx", lecture.amendements)
            export_json(lecture, f"{folder_path}/{lecture.zip_key}.json")
            write_pdf(
                context={
                    "lecture": lecture,
                    "articles": [a for a in lecture.articles if a.type],
                },
                filename=f"{folder_path}/{lecture.zip_key}.pdf",
                registry=registry,
                split_mode=split_mode,
                generation_mode=generation_mode,
            )

        # create a ZipFile compressed object
        # https://docs.python.org/fr/3/library/zipfile.html#zipfile.ZIP_DEFLATED
        with ZipFile(f"{folder_path}.zip", "w", compression=ZIP_DEFLATED) as zipObj:
            logger.info(f"Export Création du zip")
            zipObj.write(
                f"{folder_path}/Equipe-{dossier.slug}.xlsx",
                basename(f"{dossier.slug}/Equipe-{dossier.slug}.xlsx"),
            )
            for lecture in dossier.lectures:
                logger.info(f"Ajout de la lecture {lecture.zip_key} dans l'archive")
                for extension in ["xlsx", "pdf", "json"]:
                    zipObj.write(
                        f"{folder_path}/{lecture.zip_key}.{extension}",
                        f"{dossier.slug}/{lecture.zip_key}.{extension}",
                    )

        # Upload content to redis
        logger.info(f"Ajout de l'archive {dossier.slug}.zip dans redis")
        export_zip = open(f"{folder_path}.zip", "rb")
        dossier_export_repository.set_export_content(dossier, export_zip.read())
        export_zip.close()

        try:
            shutil.rmtree(folder_path)
        except OSError as e:
            print("Error: %s : %s" % (folder_path, e.strerror))

        try:
            os.remove(f"{folder_path}.zip")
        except OSError as e:
            print("Error: %s : %s" % (f"{folder_path}.zip", e.strerror))

        # Envoi du mail
        dossier_url = huey.get_url_dossier_from_ini(dossier.slug)
        send_export_dossier_notification(registry, dossier_url, user, dossier)
        ExportDossierZipReady.create(dossier, user)


@huey.task(retries=3, retry_delay=RETRY_DELAY)
def export_lecture_pdf(
    lecture_pk: int, user_pk: int, articles_pk: List[int] = []
) -> None:
    from zam_repondeur.services.lectures import lecture_export_pdf_repository

    lecture = Lecture.get_by_pk(lecture_pk)
    user = DBSession.query(User).filter(User.pk == user_pk).one_or_none()
    if not lecture:
        logger.error(f"Lecture {lecture_pk} introuvable")
        return

    if not user:
        logger.error(f"Utilisateur: {user_pk} introuvable")
        return
    articles = [
        DBSession.query(Article).filter(Article.pk == pk).one_or_none()
        for pk in articles_pk
    ]
    articles = list(filter(lambda a: a is not None, articles))
    articles_str = [f"{article}" for article in articles]
    if not articles:
        articles = [article for article in lecture.articles]
    key = lecture_export_pdf_repository._export_lecture_pdf_key(lecture, articles_str)
    with huey.lock_task(f"{key}"):
        registry = get_current_registry()
        with NamedTemporaryFile() as file_:
            tmp_file_path = os.path.abspath(file_.name)
            write_pdf(
                context={"lecture": lecture, "articles": articles},
                filename=tmp_file_path,
                registry=registry,
                split_mode=int(
                    registry.settings.get(
                        "zam.write_pdf.split_mode",
                        WritePdfSplitMode.MULTIPLE_PDF_AT_ONCE,
                    )
                ),
                generation_mode=int(
                    registry.settings.get(
                        "zam.write_pdf.generation_mode", WritePdfGEnerationMode.CMDLINE
                    )
                ),
            )
            lecture_export_pdf_repository.set_export_content(
                lecture, user, file_.read(), articles=articles_str
            )
        # Envoi du mail et ajout du message dans le journal
        dossier_url = huey.get_url_dossier_from_ini(lecture.dossier.slug)
        lecture_url = f"{dossier_url}/lectures/{lecture.url_key}"
        send_export_pdf_notification(registry, lecture_url, user, lecture)
        ExportPDF.create(lecture=lecture, request=None, user=user, nbr_article=len(articles_pk))


@huey.task(retries=3, retry_delay=RETRY_DELAY)
def alert_data_task(
    context: Dict[str, str],
    error: Tuple[str, int],
    lecture_pk: Optional[int] = None,
    dossier_pk: Optional[int] = None,
) -> None:
    if not Parametres.get_active_alerts():
        logger.info(
            f"L'alerte {error} : {context} est ignorée car le système \
d'alertes est désactivé"
        )
        return

    logger.info(f"Traitement de l'alerte {error} : {context}")
    registry = get_current_registry()
    (type_, code) = error
    try:
        exclude_codes = [
            int(value)
            for value in registry.settings.get(f"zam.exlude_errors.{type_}", "").split(
                ","
            )
        ]
    except ValueError:
        logger.error(
            f"Entiers invalides dans le fichier de configuration pour \
zam.exlude_errors.{type_}"
        )
        exclude_codes = []
    if code in exclude_codes:
        logger.info(f"L'alerte {error} : {context} est ignorée")
        return
    if lecture_pk is not None:
        with huey.lock_task(f"lecture-{lecture_pk}"):
            lecture = Lecture.get_by_pk(lecture_pk)
            if not lecture:
                logger.error(f"Lecture {lecture_pk} introuvable")
                return
            context["dossier_url"] = huey.get_url_dossier_from_ini(lecture.dossier.slug)
            if not lecture.alert_flag:
                send_alert(registry, context)
            lecture.alert_flag = True
    if dossier_pk is not None:
        with huey.lock_task(f"dossier-{dossier_pk}"):
            dossier = (
                DBSession.query(Dossier).filter(Dossier.pk == dossier_pk).one_or_none()
            )
            if not dossier:
                logger.error(f"Dossier: {dossier_pk} introuvable")
                return
            context["dossier_url"] = huey.get_url_dossier_from_ini(dossier.slug)
            if not dossier.alert_flag:
                send_alert(registry, context)
            dossier.alert_flag = True


@huey.task(retries=3, retry_delay=RETRY_DELAY)
def import_dossier_task(
    zip_content: bytes, dossier_pk: int, user_pk: int, link_dossier: str
) -> None:
    with huey.lock_task(f"dossier-{dossier_pk}"):
        dossier = (
            DBSession.query(Dossier).filter(Dossier.pk == dossier_pk).one_or_none()
        )
        if not dossier:
            logger.error(f"Dossier: {dossier_pk} introuvable")
            return
        user = DBSession.query(User).filter(User.pk == user_pk).one_or_none()
        if not user:
            logger.error(f"Utilisateur: {user_pk} introuvable")
            return

        imports_json = []
        with ZipFile(BytesIO(zip_content)) as zip_file:
            for lecture in dossier.lectures:
                link_lecture = f"{link_dossier}lectures/{lecture.url_key}/amendements"
                file_name = f"{dossier.slug}/{lecture.zip_key}.json"
                if file_name not in zip_file.namelist():
                    ImportDossierZipLectureNotFound.create(dossier, user, lecture)
                    logger.warning(
                        f"Pas de json trouvé pour la lecture {lecture.zip_key}"
                    )
                else:
                    json_file = TextIOWrapper(
                        zip_file.open(file_name), encoding="utf-8"
                    )
                    content = json_file.read()
                    # https://www.howtosolutions.net/2019/04/python-fixing-unexpected-
                    # utf-8-bom-error-when-loading-json-data/
                    decoded = content.encode().decode("utf-8-sig")
                    logger.info(
                        f"Création de l'import asynchrone de la \
lecture {lecture.zip_key}"
                    )
                    imports_json.append((decoded, lecture.pk, link_lecture))
        # Lancement de l'import global
        import_global_json_task(user.pk, dossier.pk, imports_json)


@huey.task(retries=3, retry_delay=RETRY_DELAY)
def import_json_task(json_content: str, lecture_pk: int, user_pk: int,) -> None:
    with huey.lock_task(f"lecture-{lecture_pk}"):
        counter = import_json_async(json_content, lecture_pk, user_pk)
        logger.info(f"Résultat de l'import asynchrone {counter}")


@huey.task(retries=3, retry_delay=RETRY_DELAY)
def import_global_json_task(
    user_pk: int, dossier_pk: int, imports_json: List[Tuple[str, int, str]]
) -> None:

    try:
        json_content, lecture_pk, link_lecture = imports_json.pop()
    except IndexError:
        logger.info(f"Fin de l'import global asynchrone")
        dossier = (
            DBSession.query(Dossier).filter(Dossier.pk == dossier_pk).one_or_none()
        )
        if not dossier:
            logger.error(f"Dossier: {dossier_pk} introuvable")
            return
        user = DBSession.query(User).filter(User.pk == user_pk).one_or_none()
        if not user:
            logger.error(f"Utilisateur: {user_pk} introuvable")
            return
        # Envoi du mail
        registry = get_current_registry()
        dossier_url = huey.get_url_dossier_from_ini(dossier.slug)
        send_import_dossier_notification(registry, dossier_url, user, dossier)
        return

    with huey.lock_task(f"lecture-{lecture_pk}"):
        counter = import_json_async(
            json_content, lecture_pk, user_pk, True, link_lecture
        )
        logger.info(f"Résultat de l'import asynchrone {counter}")

    import_global_json_task(user_pk, dossier_pk, imports_json)


@huey.task(retries=3, retry_delay=RETRY_DELAY)
def dossier_delete_task(dossier_pk: int, user_pk: int) -> None:
    with huey.lock_task(f"dossier-{dossier_pk}"):
        dossier = DBSession.query(Dossier).get(dossier_pk)
        user = DBSession.query(User).filter(User.pk == user_pk).one_or_none()

        if dossier is None:
            logger.error(f"Dossier {dossier_pk} introuvable")
            return

        if user is None:
            logger.error(f"User {user_pk} introuvable")
            return

        DBSession.delete(dossier.team)
        for lecture in dossier.lectures:
            DBSession.delete(lecture)
        DBSession.flush()
        DossierSupprime.create(dossier=dossier, user=user)
        DossiersListSupprime.create(dossier=dossier, user=user)

        registry = get_current_registry()
        contact_mail_from = registry.settings["zam.contact_mail_from"]
        mailer = get_mailer(registry)
        send_dossier_deleted(
            dossier, user, contact_mail_from, mailer, registry,
        )


@huey.task(retries=3, retry_delay=RETRY_DELAY)
def update_cache(user_pk: int) -> None:
    with huey.lock_task(f"update_cache"):
        user = DBSession.query(User).filter(User.pk == user_pk).one_or_none()
        repository.load_data()
        logger.info(f"Mise à jour du cache terminée.")
        send_update_cache_completed(get_current_registry(), user)
