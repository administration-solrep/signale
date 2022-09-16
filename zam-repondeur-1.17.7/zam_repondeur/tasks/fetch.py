"""
NB: make sure tasks.huey.init_huey() has been called before importing this module
"""
import csv
import logging
from http import HTTPStatus
from typing import Any, Dict, Iterable, List, Optional

import transaction
from pyramid.threadlocal import get_current_registry
from pyramid_mailer import get_mailer
from sqlalchemy import and_

from zam_repondeur.exceptions.alert import AlertOnData
from zam_repondeur.mails import send_nouvelles_lecture, send_dossier_archived
from zam_repondeur.models import (
    Chambre,
    DBSession,
    Dossier,
    Lecture,
    MissionSenat,
    Texte,
    User,
    Phase,
    Amendement,
)
from zam_repondeur.models.events.dossier import LecturesRecuperees, ArchiverDossier
from zam_repondeur.models.events.dossiers_list import ArchiverDossiersList
from zam_repondeur.models.events.lecture import (
    AmendementsAJour,
    AmendementsNonRecuperes,
    AmendementsNonTrouves,
    AmendementsRecuperes,
    ArticlesRecuperes,
    LectureCreee,
    RefreshMissionsSenat,
    TexteMisAJour,
    AutomaticDisablingSortAmendements,
    AutomaticDisablingNavette,
)
from zam_repondeur.models.phase import ALL_PHASES
from zam_repondeur.services.data import repository
from zam_repondeur.services.fetch import get_articles
from zam_repondeur.services.fetch.amendements import MAX_404, RemoteSource
from zam_repondeur.services.fetch.an.dossiers.models import DossierRef, LectureRef
from zam_repondeur.services.fetch.http import get_http_session
from zam_repondeur.services.fetch.missions import ID_TXT_MISSIONS
from zam_repondeur.services.fetch.senat.scraping import create_dossier_ref
from zam_repondeur.tasks.huey import huey, init_huey
from zam_repondeur.utils import Timer

logger = logging.getLogger(__name__)


RETRY_DELAY = 5 * 60  # 5 minutes


@huey.task(retries=3, retry_delay=RETRY_DELAY)
def update_dossier(dossier_pk: int, force: bool = False) -> None:
    with huey.lock_task(f"dossier-{dossier_pk}"):
        dossier = DBSession.query(Dossier).get(dossier_pk)
        if dossier is None:
            logger.error(f"Dossier {dossier_pk} introuvable")
            return
        dossier_ref_an = get_dossier_ref_an(dossier)
        if dossier_ref_an:
            dossier.titre_loi = dossier_ref_an.titre_loi
            dossier.urls_loi = dossier_ref_an.urls_loi
            # Do no deactivate if the dossier already had a titre_loi and urls_loi
            # to_keep_activated = dossier.titre_loi and dossier.urls_loi

            if (
                # not to_keep_activated
                # and dossier_ref_an.titre_loi
                dossier_ref_an.titre_loi
                and dossier_ref_an.urls_loi
                and dossier.team
            ):
                dossier.team.active = False
                ArchiverDossier.create(
                    dossier=dossier, active=dossier.team.active, request=None
                )
                ArchiverDossiersList.create(
                    dossier=dossier, active=dossier.team.active, request=None
                )
                registry = get_current_registry()

                send_dossier_archived(
                    dossier=dossier,
                    dossier_url=huey.get_url_dossier_from_ini(dossier.slug),
                    contact_mail_from=registry.settings["zam.contact_mail_from"],
                    mailer=get_mailer(registry),
                    registry=registry,
                )

        # First fetch data from existing lectures, starting with recents.
        for lecture in reversed(dossier.lectures):

            if not lecture.update:
                logger.info(f"lecture {lecture} désactivée pour la mise à jour")
                continue

            # Auto fetch articles only for recent lectures.
            if force or lecture.refreshable_for("articles", huey.settings):
                fetch_articles(lecture.pk)

            # Only fetch amendements for recent lectures.
            if force or lecture.refreshable_for("amendements", huey.settings):
                fetch_amendements(lecture.pk)

        # Then try to create missing lectures.
        create_missing_lectures(dossier.pk)


@huey.task(retries=3, retry_delay=RETRY_DELAY)
def update_dossier2texte(dossier_pk: int) -> None:
    with huey.lock_task(f"dossier-{dossier_pk}"):
        dossier = DBSession.query(Dossier).get(dossier_pk)

        if dossier is None:
            logger.error(f"Dossier {dossier_pk} introuvable")
            return

        dossier_ref_an = get_dossier_ref_an(dossier)
        dossier_ref_senat = get_dossier_ref_senat(dossier)

        if dossier_ref_an:
            for texte in _get_textes_from_lectures_ref(dossier_ref_an.lectures):
                if texte not in dossier.textes:
                    dossier.textes.append(texte)
                    logger.info(
                        f"Ajout du texte pk: {texte.pk} au dossier {dossier.slug}"
                    )

        if dossier_ref_senat:
            for texte in _get_textes_from_lectures_ref(dossier_ref_senat.lectures):
                if texte not in dossier.textes:
                    dossier.textes.append(texte)
                    logger.info(
                        f"Ajout du texte pk: {texte.pk} au dossier {dossier.slug}"
                    )

        if not huey.immediate:
            transaction.commit()
            DBSession.expire_all()


@huey.task(retries=3, retry_delay=RETRY_DELAY)
def fetch_articles(lecture_pk: Optional[int]) -> bool:
    if lecture_pk is None:
        logger.error(f"fetch_articles: lecture_pk is None")
        return False

    with huey.lock_task(f"lecture-{lecture_pk}"):
        lecture = DBSession.query(Lecture).with_for_update().get(lecture_pk)
        if lecture is None:
            logger.error(f"Lecture {lecture_pk} introuvable")
            return False

        changed: bool = get_articles(lecture)
        if changed:
            ArticlesRecuperes.create(lecture=lecture)
        return changed


def fetch_missions_senat(lecture: Lecture) -> bool:
    if not lecture.elligible_mission_senat:
        logger.error(f"Les missions sont destinées aux lectures du SENAT en 2 parties")
        return False

    url_mission = MissionSenat.get_url_missions_senat(lecture)
    if url_mission is None:
        logger.error(f"Pas d'url mission pour {lecture}")
        return False

    # D'abord on essaye avec l'url
    try:
        items = _get_mission_senat_items_from_url(lecture, url_mission)
    except AlertOnData as exception:
        init_huey(get_current_registry().settings)
        from zam_repondeur.tasks.asynchrone import alert_data_task

        logger.exception(
            "La récupération des missions SENAT pour la lecture \
lecture %r, URL %s a échoué",
            lecture,
            url_mission,
        )
        context = {
            "url": exception.url,
            "titre": f"{lecture.dossier.titre} : {lecture}",
            "message": exception.message,
        }
        alert_data_task(context, exception.error, lecture_pk=lecture.pk)
        items = []
    if not items:
        # Pas de mission trouvée on exploite les entrées en `dur` dans le code
        items = _get_mission_senat_items_from_code(lecture)

    if items is None:
        logger.error(f"Pas de mission pour {lecture}")
        return False

    created = False
    for item in items:
        mission_senat = MissionSenat.get(lecture, int(item["id_texte"]))
        if mission_senat is None:
            MissionSenat.create(lecture, item["titre"], int(item["id_texte"]))
            created = True
        elif mission_senat.titre != item["titre"]:
            mission_senat.titre = item["titre"]

    if created:
        RefreshMissionsSenat.create(lecture)
    return created


def _get_mission_senat_items_from_code(
    lecture: Lecture,
) -> Optional[List[Dict[Any, Any]]]:

    id_txt_missions = (
        ID_TXT_MISSIONS.get(f"{lecture.texte.session_str}", {})
        .get(lecture.texte.numero, {})
        .get(lecture.partie)
    )

    if id_txt_missions is not None:
        return [
            {"id_texte": id_txt, "titre": mission.titre}
            for id_txt, mission in id_txt_missions
        ]
    return None


def _get_mission_senat_items_from_url(
    lecture: Lecture, url: str
) -> Optional[List[Dict[Any, Any]]]:

    http_session = get_http_session()
    resp = http_session.get(url)
    if resp.status_code != HTTPStatus.OK:
        logger.error(
            "Récupération des missions de %r, URL %s impossible code HTTP:%s",
            lecture,
            url,
            resp.status_code,
        )
        raise AlertOnData(
            f"Impossible de récupérer les missions SENAT à l'url \
{url} code http:{resp.status_code}",
            "http",
            resp.status_code,
            url=url,
        )

    try:
        text: str = resp.content.decode("cp1252")
        lines = text.splitlines()
        headers = [header.strip() for header in lines[1].split("\t")]
        lines[1] = "\t".join(headers)
        clean_lines = [_clean_tsv_line(line) for line in lines[1:]]
        reader = csv.DictReader(clean_lines, delimiter="\t")

        items = [
            {"id_texte": item["id_texte"], "titre": item["titre"]}
            for item in reader
            if item["session"] == f"{lecture.texte.session_str}"
            and item["num_texte"] == f"{lecture.texte.numero}"
            and item["partie"] == f"{lecture.partie}"
        ]
    except Exception:
        logger.exception(
            "Problème lors du traitement des missions de %r, URL %s",
            lecture,
            url,
            resp.status_code,
        )
        raise AlertOnData(
            f"Problème lors du traitement des missions SENAT de {lecture}, URL {url}",
            "http",
            resp.status_code,
            url=url,
        )
    return items


def _clean_tsv_line(line: str) -> str:
    return "\t".join([value.strip() for value in line.split("\t") if value])


@huey.task(retries=3, retry_delay=RETRY_DELAY)
def fetch_amendements(lecture_pk: Optional[int], max_404: int = MAX_404) -> bool:
    if lecture_pk is None:
        logger.error(f"fetch_amendements: lecture_pk is None")
        return False

    with huey.lock_task(f"lecture-{lecture_pk}"):

        lecture = DBSession.query(Lecture).get(lecture_pk)
        if lecture is None:
            logger.error(f"Lecture {lecture_pk} introuvable")
            return False

        if lecture.elligible_mission_senat:
            logger.info("Récupération des missions de %r", lecture)
            fetch_missions_senat(lecture)

        logger.info("Récupération des amendements de %r", lecture)

        # This allows disabling the prefetching in tests.
        prefetching_enabled = int(huey.settings["zam.http_cache_duration"]) > 0

        source = RemoteSource.get_remote_source_for_chambre(
            chambre=lecture.chambre, prefetching_enabled=prefetching_enabled
        )

        # Allow prefetching of URLs into the requests cached session.
        with Timer() as prepare_timer:
            source.prepare(lecture)
        logger.info("Time to prepare: %.1fs", prepare_timer.elapsed())

        # Collect data about new and updated amendements.
        with Timer() as collect_timer:
            try:
                changes = source.collect_changes(lecture=lecture, max_404=max_404)
            except AlertOnData as exception:
                init_huey(get_current_registry().settings)
                from zam_repondeur.tasks.asynchrone import alert_data_task

                logger.exception(
                    "La récupération des amendements pour la lecture \
                      lecture %r a échoué",
                    lecture,
                )
                context = {
                    "url": exception.url,
                    "titre": f"{lecture.dossier.titre} : {lecture}",
                    "message": exception.message,
                }
                alert_data_task(context, exception.error, lecture_pk=lecture.pk)
        logger.info("Time to collect: %.1fs", collect_timer.elapsed())

        # Then apply the actual changes in a fresh transaction, in order to minimize
        # the duration of database locks (if we hold locks too long, we could have
        # synchronization issues with the webapp, causing unwanted delays for users
        # on some interactive operations).

        # But during tests we want everything to run in a single transaction that
        # we can roll back at the end.
        if not huey.immediate:
            transaction.commit()
            DBSession.expire_all()

        lecture = DBSession.query(Lecture).with_for_update().get(lecture_pk)
        if lecture is None:
            logger.error(f"Lecture {lecture_pk} introuvable")
            return False

        with Timer() as apply_timer:
            amendements, created, errored = source.apply_changes(lecture, changes)
        logger.info("Time to apply: %.1fs", apply_timer.elapsed())

        logger.info(
            "Total time: %.1fs",
            sum(t.elapsed() for t in (prepare_timer, collect_timer, apply_timer)),
        )

        if not amendements:
            AmendementsNonTrouves.create(lecture=lecture)

        if created:
            AmendementsRecuperes.create(lecture=lecture, count=created)

        if errored:
            AmendementsNonRecuperes.create(lecture=lecture, missings=errored)

        changed = bool(amendements and not (created or errored))
        if changed:
            AmendementsAJour.create(lecture=lecture)

        if not lecture.partie:
            nb_amendements = (
                DBSession.query(Amendement.sort)
                .filter(Amendement.lecture_pk == lecture_pk)
                .count()
            )
            if nb_amendements:
                nb_amendements_with_sort = (
                    DBSession.query(Amendement.sort)
                    .filter(
                        and_(
                            Amendement.lecture_pk == lecture_pk,
                            Amendement.sort.isnot(None),
                            Amendement.sort != "",
                        )
                    )
                    .count()
                )
                if nb_amendements_with_sort == nb_amendements and lecture.update:
                    lecture.update = False
                    AutomaticDisablingSortAmendements.create(lecture=lecture)
        return changed


@huey.task()
def create_missing_lectures(
    dossier_pk: int, send_email: bool = True, user_pk: Optional[int] = None
) -> None:
    with huey.lock_task(f"dossier-{dossier_pk}"):
        dossier = DBSession.query(Dossier).get(dossier_pk)
        if dossier is None:
            logger.error(f"Dossier {dossier_pk} introuvable")
            return

        if user_pk is not None:
            user = DBSession.query(User).get(user_pk)
        else:
            user = None

        changed = False
        changed |= create_missing_lectures_an(dossier, user)
        changed |= create_missing_lectures_senat(dossier, user)

        if changed:
            dossier_url = huey.get_url_dossier_from_ini(dossier.slug)
            registry = get_current_registry()
            contact_mail_from = registry.settings["zam.contact_mail_from"]
            mailer = get_mailer(registry)
            LecturesRecuperees.create(
                dossier=dossier, user=user, dossier_url=dossier_url
            )
        if changed and send_email:
            send_nouvelles_lecture(
                dossier, dossier_url, contact_mail_from, mailer, registry,
            )


def create_missing_lectures_an(dossier: Dossier, user: Optional[User]) -> bool:
    # FIXME: error handling

    dossier_ref_an = get_dossier_ref_an(dossier)

    changed = False
    if dossier_ref_an:
        for lecture_ref in dossier_ref_an.lectures:
            if lecture_ref.chambre == Chambre.AN:
                changed |= create_or_update_lecture(dossier, lecture_ref, user)
    return changed


def get_dossier_ref_an(dossier: Dossier) -> Optional[DossierRef]:
    if dossier.an_id:
        return repository.get_opendata_dossier_ref(dossier.an_id)
    else:
        dossier_ref_senat = repository.get_senat_scraping_dossier_ref(dossier.senat_id)
        if dossier_ref_senat is not None:
            return find_matching_dossier_ref_an(dossier_ref_senat)
        else:
            logger.warning(
                f"Aucune référence Sénat trouvée sur le "
                f"dossier {dossier.titre} ({dossier.slug})"
            )
    return None


def find_matching_dossier_ref_an(dossier_ref_senat: DossierRef) -> Optional[DossierRef]:
    # The Sénat dossier_ref usually includes the AN webpage URL, so we try to find
    # an indexed AN dossier_ref with the same AN URL
    an_url = dossier_ref_senat.normalized_an_url
    if an_url:
        dossier_ref = repository.get_opendata_dossier_ref_by_an_url(an_url)
        if dossier_ref:
            return dossier_ref

    # As a fallback, try to find an indexed AN dossier_ref with the same Sénat URL
    senat_url = dossier_ref_senat.normalized_senat_url
    if senat_url:
        dossier_ref = repository.get_opendata_dossier_ref_by_senat_url(senat_url)
        if dossier_ref:
            return dossier_ref
    return None


def create_missing_lectures_senat(dossier: Dossier, user: Optional[User]) -> bool:
    dossier_ref_senat = get_dossier_ref_senat(dossier)

    changed = False
    if dossier_ref_senat is not None:
        for lecture_ref in dossier_ref_senat.lectures:
            if lecture_ref.chambre == Chambre.SENAT:
                changed |= create_or_update_lecture(dossier, lecture_ref, user)
    return changed


def get_dossier_ref_senat(dossier: Dossier) -> Optional[DossierRef]:
    if dossier.senat_id:
        return get_senat_dossier_ref_from_cache_or_scrape(dossier_id=dossier.senat_id)
    else:
        dossier_ref_an = repository.get_opendata_dossier_ref(dossier.an_id)
        if dossier_ref_an is not None:
            return find_matching_dossier_ref_senat(dossier_ref_an)
        else:
            logger.warning(
                f"Aucune référence AN trouvée sur le "
                f"dossier {dossier.titre} ({dossier.slug})"
            )
    return None


def find_matching_dossier_ref_senat(dossier_ref_an: DossierRef) -> Optional[DossierRef]:
    # The AN dossier_ref usually includes the Sénat webpage URL, so we try this first
    senat_url = dossier_ref_an.senat_url
    dossier_id = dossier_ref_an.senat_dossier_id
    if senat_url and dossier_id:
        return get_senat_dossier_ref_from_cache_or_scrape(dossier_id=dossier_id)

    # As a fall back, we index the Sénat dossier_refs by AN webpage URL, so if
    # the information is available in that direction, we can still find it
    an_url = dossier_ref_an.normalized_an_url
    return repository.get_senat_scraping_dossier_ref_by_an_url(an_url)


def get_senat_dossier_ref_from_cache_or_scrape(dossier_id: str) -> DossierRef:
    """
    Get dossier from the Redis cache (if recent) or scrape it
    """
    dossier_ref_senat = repository.get_senat_scraping_dossier_ref(dossier_id)
    if dossier_ref_senat is None:
        dossier_ref_senat = create_dossier_ref(dossier_id)
    return dossier_ref_senat


def create_or_update_lecture(
    dossier: Dossier, lecture_ref: LectureRef, user: Optional[User]
) -> bool:
    changed = False

    lecture_created = False
    lecture_updated = False

    if lecture_ref.chambre != lecture_ref.texte.chambre:
        logger.error(
            f"Impossible d'intégrer la lecture {lecture_ref.titre} dans \
le dossier '{dossier.slug}' car la chambre du texte ne correspond \
pas à la chambre de la lecture"
        )
        return False

    texte = Texte.get_or_create_from_ref(lecture_ref.texte, lecture_ref.chambre)

    lecture = Lecture.get_from_ref(lecture_ref, dossier, texte)
    
    specific_test = False
    if lecture is not None and texte is not None and lecture.chambre == texte.chambre == Chambre.AN:
        specific_test = lecture.texte.legislature <= texte.legislature
    elif lecture is not None and texte is not None and lecture.chambre == texte.chambre == Chambre.SENAT:
        specific_test = lecture.texte.session <= texte.session

    if lecture is not None and lecture.texte is not texte and specific_test:
        # We probably created the Lecture before a new Texte was adopted
        # by the commission. Time to update with the final one!
        TexteMisAJour.create(lecture=lecture, texte=texte)
        lecture_updated = True

    if lecture is None:
        lecture = Lecture.create_from_ref(lecture_ref, dossier, texte)
        LectureCreee.create(lecture=lecture, user=user)
        lecture_created = True

    if lecture_created:
        dossier_lecture: Optional[Lecture] = None
        # disable update on other assembly lecture from a previous or equal phase
        for dossier_lecture in dossier.lectures:
            if (
                dossier_lecture.update
                and dossier_lecture.phase is not Phase.INCONNUE
                and dossier_lecture.chambre != lecture.chambre
                and ALL_PHASES.index(dossier_lecture.phase)
                <= ALL_PHASES.index(lecture.phase)
            ):
                dossier_lecture.update = False
                AutomaticDisablingNavette.create(lecture=lecture)

    if lecture_created or lecture_updated:
        changed = True

        # Make sure the lecture gets its primary key.
        DBSession.flush()

        # Enqueue tasks to fetch missions senat, articles and amendements.
        huey.enqueue_on_transaction_commit(fetch_articles.s(lecture.pk))
        huey.enqueue_on_transaction_commit(fetch_amendements.s(lecture.pk))

    return changed


def _get_textes_from_lectures_ref(lectures_ref: List[LectureRef]) -> Iterable[Texte]:
    for lecture_ref in lectures_ref:
        if lecture_ref.chambre != lecture_ref.texte.chambre:
            logger.error(
                f"Impossible de créer le texte {lecture_ref.texte} attaché à la \
lecture  {lecture_ref.titre} car la chambre du texte ne correspond pas \
à la chambre de la lecture"
            )
            continue
        yield Texte.get_or_create_from_ref(lecture_ref.texte, lecture_ref.chambre)
